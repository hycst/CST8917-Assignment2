# Version A --- Durable Functions Expense Approval Workflow

## Overview

This project implements **Version A** of an expense approval workflow
using **Azure Durable Functions with Python**. It validates expense
requests, automatically approves expenses under \$100, waits for manager
approval for expenses of \$100 or more, handles manager rejection, and
uses a Durable Timer for timeout/escalation. Final outcomes generate
email notifications through SMTP and are tested with Mailtrap.

## Workflow

1.  Submit an expense through the HTTP endpoint.
2.  Validate required fields and category.
3.  Expenses under \$100 are automatically approved.
4.  Expenses of \$100 or more wait for a `ManagerDecision` external
    event.
5.  The manager can approve or reject the request.
6.  If no manager response arrives before the timeout, the expense is
    automatically approved and marked as escalated.
7.  Process the final outcome.
8.  Send an email notification to the employee.

For local demonstration, the manager-response timeout is **60 seconds**.

## Azure Functions

-   `start_expense` --- HTTP trigger that starts the orchestration.
-   `expense_orchestrator` --- Durable orchestrator coordinating the
    workflow.
-   `validate_expense` --- Activity that validates the expense.
-   `process_outcome` --- Activity that processes the final result.
-   `send_notification` --- Activity that sends an SMTP email.
-   `manager_decision` --- HTTP endpoint that raises the
    `ManagerDecision` external event.

## Approval Logic

  -----------------------------------------------------------------------
  Condition                           Result
  ----------------------------------- -----------------------------------
  Amount \< \$100                     Auto-approved

  Amount \>= \$100 + manager approves Manager-approved

  Amount \>= \$100 + manager rejects  Rejected

  Amount \>= \$100 + no response      Auto-approved and escalated
  before timeout                      

  Required field missing              Validation error

  Invalid category                    Validation error
  -----------------------------------------------------------------------

Valid categories: `travel`, `meals`, `supplies`, `equipment`,
`software`, and `other`.

## Email Notifications

The application uses SMTP for email notifications and Mailtrap Email
Testing during local development. Verified subjects include: -
`Expense Approved` - `Expense Rejected` - `Expense Approved - Escalated`

SMTP credentials belong only in `local.settings.json`, which is excluded
from Git.

## Project Structure

``` text
Version_Durable_Function/
├── .gitignore
├── .vscode/
│   └── extensions.json
├── function_app.py
├── host.json
├── local.settings.example.json
├── requirements.txt
└── test-durable.http
```

Local `.venv`, `local.settings.json`, Python cache files, and
Azurite-generated storage files are not committed.

## Prerequisites

-   Python
-   Azure Functions Core Tools
-   Azurite
-   Visual Studio Code
-   Azure Functions extension
-   REST Client extension
-   Mailtrap Email Testing account for SMTP testing

## Local Configuration

Create `local.settings.json` using `local.settings.example.json` as the
template:

``` json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "SMTP_HOST": "sandbox.smtp.mailtrap.io",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "YOUR_SMTP_USERNAME",
    "SMTP_PASSWORD": "YOUR_SMTP_PASSWORD",
    "SENDER_EMAIL": "your-email@example.com"
  }
}
```

Never commit `local.settings.json`.

## Setup and Run

### 1. Create and activate a virtual environment

``` powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

``` powershell
pip install -r requirements.txt
```

### 3. Start Azurite

Start Azurite before the Functions host. Durable Functions uses local
storage through:

``` text
AzureWebJobsStorage=UseDevelopmentStorage=true
```

### 4. Start Azure Functions

``` powershell
func start
```

Main local endpoints:

``` text
POST http://localhost:7071/api/expenses
POST http://localhost:7071/api/expenses/{instance_id}/decision
```

## Testing

Use `test-durable.http` with the VS Code REST Client extension.

### Test 1 --- Under \$100: Auto-approval

Expected:

``` text
status: approved
approvalType: auto-approved
escalated: false
```

### Test 2 --- Manager Approval

Start an expense of \$100 or more, copy its instance ID into the
decision request, and send:

``` json
{
  "decision": "approve"
}
```

Expected:

``` text
status: approved
approvalType: manager-approved
escalated: false
```

### Test 3 --- Manager Rejection

Start a new expense of \$100 or more and send:

``` json
{
  "decision": "reject"
}
```

Expected:

``` text
status: rejected
approvalType: manager-rejected
escalated: false
```

### Test 4 --- Timeout / Escalation

Start an expense of \$100 or more and do not send a manager decision.
After the 60-second local timeout, expected:

``` text
status: approved
approvalType: timeout-auto-approved
escalated: true
```

### Test 5 --- Missing Required Field

Expected:

``` text
status: validation_error
error: Missing required fields
```

### Test 6 --- Invalid Category

Expected:

``` text
status: validation_error
error: Invalid category
```

## Verified Results

Local testing verified: - Auto-approval - Manager approval - Manager
rejection - Durable Timer timeout - Timeout auto-approval and
escalation - Missing-field validation - Invalid-category validation -
SMTP notification activity - Mailtrap receipt of approval, rejection,
and escalation emails

## Security

Sensitive and generated local files are excluded through `.gitignore`,
including:

``` text
local.settings.json
.venv/
__pycache__/
__blobstorage__/
__queuestorage__/
__tablestorage__/
__azurite_db*__.json
AzuriteConfig
```

Use `local.settings.example.json` for configuration documentation
without exposing credentials.

## Technologies

Azure Functions, Azure Durable Functions, Python, Azurite, REST Client,
SMTP, Mailtrap Email Testing, and Git.
