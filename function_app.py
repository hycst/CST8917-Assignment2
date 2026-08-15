import azure.functions as func
import azure.durable_functions as df
from datetime import timedelta
import json

import os
import smtplib
from email.message import EmailMessage

app = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="expenses", methods=["POST"])
@app.durable_client_input(client_name="client")
async def start_expense(
    req: func.HttpRequest,
    client
) -> func.HttpResponse:

    expense = req.get_json()

    instance_id = await client.start_new(
        "expense_orchestrator",
        None,
        expense
    )

    return client.create_check_status_response(
        req,
        instance_id
    )

@app.activity_trigger(input_name="expense")
def validate_expense(expense: dict):

    required_fields = [
        "employeeName",
        "employeeEmail",
        "amount",
        "category",
        "description",
        "managerEmail"
    ]

    valid_categories = [
        "travel",
        "meals",
        "supplies",
        "equipment",
        "software",
        "other"
    ]

    # Check required fields
    missing_fields = []

    for field in required_fields:
        if field not in expense or expense[field] in [None, ""]:
            missing_fields.append(field)

    if missing_fields:
        return {
            "valid": False,
            "error": "Missing required fields",
            "missingFields": missing_fields
        }

    # Check category
    category = str(expense["category"]).lower()

    if category not in valid_categories:
        return {
            "valid": False,
            "error": "Invalid category",
            "validCategories": valid_categories
        }

    # Check amount
    try:
        amount = float(expense["amount"])

        if amount < 0:
            return {
                "valid": False,
                "error": "Amount cannot be negative"
            }

    except (ValueError, TypeError):
        return {
            "valid": False,
            "error": "Amount must be a number"
        }

    return {
        "valid": True
    }


@app.activity_trigger(input_name="outcome")
def process_outcome(outcome: dict):

    expense = outcome["expense"]

    return {
        "status": outcome["status"],
        "approvalType": outcome["approvalType"],
        "escalated": outcome["escalated"],
        "employeeName": expense["employeeName"],
        "employeeEmail": expense["employeeEmail"],
        "amount": expense["amount"],
        "category": expense["category"],
        "description": expense["description"]
    }


@app.orchestration_trigger(context_name="context")
def expense_orchestrator(context: df.DurableOrchestrationContext):

    expense = context.get_input()

    # Step 1: Validate the expense
    validation_result = yield context.call_activity(
        "validate_expense",
        expense
    )

    if not validation_result["valid"]:
        return {
            "status": "validation_error",
            "details": validation_result
        }

    # Step 2: Auto-approve expenses under $100
    amount = float(expense["amount"])





    if amount < 100:
        outcome = {
            "status": "approved",
            "approvalType": "auto-approved",
            "escalated": False,
            "expense": expense
        }

        final_result = yield context.call_activity(
            "process_outcome",
            outcome
        )

        notification_result = yield context.call_activity(
            "send_notification",
            final_result
        )

        final_result["notification"] = notification_result

        return final_result



    

    # Step 3: Manager approval required for expenses >= $100
    approval_event = context.wait_for_external_event("ManagerDecision")

    deadline = context.current_utc_datetime + timedelta(seconds=60)

    timeout_task = context.create_timer(deadline)

    winner = yield context.task_any([
        approval_event,
        timeout_task
    ])

    # Manager responded before timeout
    if winner == approval_event:
        timeout_task.cancel()

        decision_data = approval_event.result

        # External event payload may arrive as a JSON string
        if isinstance(decision_data, str):
            try:
                decision_data = json.loads(decision_data)
            except json.JSONDecodeError:
                decision_data = {
                    "decision": decision_data
                }

        decision = str(
            decision_data.get("decision", "")
        ).lower()

        if decision == "approve":
            outcome = {
                "status": "approved",
                "approvalType": "manager-approved",
                "escalated": False,
                "expense": expense
            }

        elif decision == "reject":
            outcome = {
                "status": "rejected",
                "approvalType": "manager-rejected",
                "escalated": False,
                "expense": expense
            }

        else:
            outcome = {
                "status": "rejected",
                "approvalType": "invalid-manager-decision",
                "escalated": False,
                "expense": expense
            }

    # No manager response before timeout
    else:
        outcome = {
            "status": "approved",
            "approvalType": "timeout-auto-approved",
            "escalated": True,
            "expense": expense
        }

    final_result = yield context.call_activity(
        "process_outcome",
        outcome
    )

    notification_result = yield context.call_activity(
        "send_notification",
        final_result
    )

    final_result["notification"] = notification_result

    return final_result



@app.route(
    route="expenses/{instance_id}/decision",
    methods=["POST"]
)
@app.durable_client_input(client_name="client")
async def manager_decision(req: func.HttpRequest, client):

    instance_id = req.route_params.get("instance_id")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            "Invalid JSON body",
            status_code=400
        )

    decision = body.get("decision", "").lower()

    if decision not in ["approve", "reject"]:
        return func.HttpResponse(
            "Decision must be 'approve' or 'reject'",
            status_code=400
        )

    await client.raise_event(
        instance_id,
        "ManagerDecision",
        {
            "decision": decision
        }
    )

    return func.HttpResponse(
        f"Manager decision '{decision}' sent to orchestration {instance_id}",
        status_code=200
    )

# Email notification
@app.activity_trigger(input_name="notification")
def send_notification(notification: dict):

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    sender_email = os.environ.get("SENDER_EMAIL")

    employee_email = notification["employeeEmail"]
    employee_name = notification["employeeName"]
    status = notification["status"]
    approval_type = notification["approvalType"]
    escalated = notification["escalated"]
    amount = notification["amount"]
    category = notification["category"]
    description = notification["description"]

    # Create readable status text
    if escalated:
        subject = "Expense Approved - Escalated"
        outcome_text = (
            "Your expense was automatically approved because "
            "no manager response was received before the timeout. "
            "The expense has been flagged as escalated."
        )

    elif status == "approved":
        subject = "Expense Approved"
        outcome_text = "Your expense request has been approved."

    elif status == "rejected":
        subject = "Expense Rejected"
        outcome_text = "Your expense request has been rejected."

    else:
        subject = "Expense Request Update"
        outcome_text = f"Your expense request status is: {status}."

    body = f"""
Hello {employee_name},

{outcome_text}

Expense Details:
Amount: ${amount}
Category: {category}
Description: {description}

Approval Type: {approval_type}
Escalated: {escalated}

Thank you,
Expense Approval System
"""

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender_email
    message["To"] = employee_email
    message.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()

            if smtp_username and smtp_password:
                server.login(
                    smtp_username,
                    smtp_password
                )

            server.send_message(message)

        return {
            "emailSent": True,
            "recipient": employee_email,
            "subject": subject
        }

    except Exception as ex:
        return {
            "emailSent": False,
            "recipient": employee_email,
            "error": str(ex)
        }



#expense_orchestrator = df.Orchestrator.create(expense_orchestrator)

