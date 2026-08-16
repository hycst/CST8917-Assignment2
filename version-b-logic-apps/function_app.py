import azure.functions as func
import datetime
import json
import logging


app = func.FunctionApp(
    http_auth_level=func.AuthLevel.ANONYMOUS
)


@app.route(
    route="validate-expense",
    methods=["POST"]
)
def validate_expense(req: func.HttpRequest) -> func.HttpResponse:

    try:
        expense = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({
                "valid": False,
                "error": "Invalid JSON body"
            }),
            mimetype="application/json",
            status_code=400
        )

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

    # Check missing fields
    missing_fields = []

    for field in required_fields:
        if field not in expense or expense[field] in [None, ""]:
            missing_fields.append(field)

    if missing_fields:
        return func.HttpResponse(
            json.dumps({
                "valid": False,
                "error": "Missing required fields",
                "missingFields": missing_fields
            }),
            mimetype="application/json",
            status_code=200
        )

    # Check category
    category = str(expense["category"]).lower()

    if category not in valid_categories:
        return func.HttpResponse(
            json.dumps({
                "valid": False,
                "error": "Invalid category",
                "validCategories": valid_categories
            }),
            mimetype="application/json",
            status_code=200
        )

    # Check amount
    try:
        amount = float(expense["amount"])

        if amount < 0:
            return func.HttpResponse(
                json.dumps({
                    "valid": False,
                    "error": "Amount cannot be negative"
                }),
                mimetype="application/json",
                status_code=200
            )

    except (ValueError, TypeError):
        return func.HttpResponse(
            json.dumps({
                "valid": False,
                "error": "Amount must be a number"
            }),
            mimetype="application/json",
            status_code=200
        )

    return func.HttpResponse(
        json.dumps({
            "valid": True,
            "expense": expense
        }),
        mimetype="application/json",
        status_code=200
    )