# CST8917 Assignment 2 --- Compare & Contrast: Dual Implementation of an Expense Approval Workflow


------------------------------------------------------------------------

## 1. Project Overview

This project implements the same expense approval workflow using two
different Azure serverless orchestration approaches:

-   **Version A:** Azure Durable Functions using Python
-   **Version B:** Azure Logic Apps with Azure Service Bus and Azure
    Functions

The purpose of the assignment is to compare a code-first orchestration
approach with a visual/declarative orchestration approach based on
direct implementation experience.

Both versions implement the same business rules so that their
development experience, testability, error handling, human interaction,
observability, and cost can be compared fairly.

------------------------------------------------------------------------

## 2. Expense Approval Business Rules

Each expense request contains employee name, employee email, amount,
category, description, and manager email.

  -----------------------------------------------------------------------
  Rule                                Behaviour
  ----------------------------------- -----------------------------------
  Validation                          Reject requests with missing
                                      required fields or invalid
                                      categories

  Valid Categories                    `travel`, `meals`, `supplies`,
                                      `equipment`, `software`, `other`

  Amount \< \$100                     Automatically approved

  Amount \>= \$100                    Manager approval required

  Manager Approves                    Expense is approved

  Manager Rejects                     Expense is rejected

  No Manager Response                 Expense is automatically approved
                                      and marked as escalated

  Notification                        Employee receives an email
                                      containing the final outcome
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 3. Version A --- Azure Durable Functions

## 3.1 Overview

Version A implements the expense workflow using **Azure Durable
Functions with the Python v2 programming model**.

The implementation uses an HTTP client/starter function, Durable
orchestrator, activity functions, external events, durable timer, and
SMTP email notification.

The main entry point is:

``` text
POST /api/expenses
```

The client function starts a new instance of the `expense_orchestrator`.

### Architecture

``` text
HTTP Expense Request
        |
        v
start_expense
        |
        v
expense_orchestrator
        |
        v
validate_expense
        |
        +---------------- Validation Error
        |
        v
Check Amount
   /             \
< $100          >= $100
  |                |
  v                v
Auto Approve    Wait for ManagerDecision
                   |
             +-----+------+
             |            |
         Response       Timeout
             |            |
      Approve/Reject   Auto-Approve
                          +
                       Escalated
             \            /
              v          v
              process_outcome
                    |
                    v
             send_notification
```

## 3.2 Design Decisions

### Validation Activity

The `validate_expense` activity verifies that all required fields exist
and checks whether the category is supported. Keeping validation in an
activity function separates business validation from orchestration
logic.

### Automatic Approval

If the expense amount is below `$100`, the orchestrator immediately
creates an approved outcome without waiting for a manager.

### Human Interaction Pattern

For expenses of `$100` or more, the orchestrator waits for the external
event `ManagerDecision`.

A separate HTTP endpoint simulates the manager response:

``` text
POST /api/expenses/{instance_id}/decision
```

The request contains either `{"decision": "approve"}` or
`{"decision": "reject"}`.

### Durable Timeout

The orchestrator creates a durable timer while waiting for the manager
decision. For demonstration and testing, the timeout was configured to
approximately 60 seconds.

The orchestrator waits for either the manager response or the durable
timer. If the timer completes first, the expense is automatically
approved and `escalated` is set to `true`.

This demonstrates the Durable Functions **Human Interaction pattern**.

### Email Notification

After the final outcome is determined, an activity function sends an
email to the employee using SMTP. The notification indicates whether the
expense was automatically approved, manager approved, manager rejected,
or approved after timeout and escalated.

## 3.3 Version A Test Scenarios

The `test-durable.http` file contains tests for all six required
scenarios.

  \#   Scenario                              Expected Result
  ---- ------------------------------------- -----------------------------
  1    Valid expense under \$100             Auto-approved
  2    Expense \>= \$100, manager approves   Approved
  3    Expense \>= \$100, manager rejects    Rejected
  4    Expense \>= \$100, no response        Auto-approved and escalated
  5    Missing required field                Validation error
  6    Invalid category                      Validation error

During testing, Durable Functions status endpoints were useful for
viewing orchestration state and final output.

## 3.4 Challenges --- Version A

One challenge was understanding how Durable Functions handles
asynchronous orchestration and external events. For manager approval, I
needed to start the orchestration, obtain the instance ID, send a second
HTTP request to the manager decision endpoint, and raise the
`ManagerDecision` external event before the durable timer expired.

I also experienced local startup problems when Azurite was not running.
Durable Functions uses Azure Storage for orchestration state, so the
local Functions host could not start correctly when the storage emulator
was unavailable.

Another challenge was email notification configuration. SMTP
configuration must be stored in environment variables instead of being
hard-coded into source code.

Despite these challenges, the code-first implementation made it
relatively easy to understand exactly which branch was executed.

------------------------------------------------------------------------

# 4. Version B --- Logic Apps + Service Bus

## 4.1 Overview

Version B implements the same workflow using a visual/declarative
serverless architecture.

The main Azure components are Azure Service Bus queue, Azure Logic App,
Azure Function for expense validation, Microsoft 365 email connector,
Azure Service Bus topic, and filtered topic subscriptions.

### Architecture

``` text
Expense Request
      |
      v
Service Bus Queue
      |
      v
Logic App Trigger
      |
      v
Azure Function
Validate Expense
      |
      v
Validation Condition
   /           \
Invalid        Valid
  |              |
  v              v
Error Email   Check Amount
              /        \
          < $100       >= $100
             |             |
             v             v
        Auto Approve   Manager Approval
                           |
                     +-----+------+
                     |            |
                  Response      Timeout
                     |            |
                Approve/Reject  Escalated
                     \            /
                      v          v
                    Final Outcome
                         |
                  +------+------+
                  |             |
                  v             v
             Service Bus       Email
                Topic        Notification
```

## 4.2 Service Bus Queue

Incoming expense requests are placed in a Service Bus queue. The Logic
App uses **When a message is received in a queue (auto-complete)** as
its trigger. This provides asynchronous messaging between the request
producer and the workflow.

## 4.3 Azure Function Validation

Instead of implementing all validation directly inside the Logic App, I
created an Azure Function named `validate-expense`.

The Logic App calls this Function and evaluates the returned result. The
validation Function checks required fields, valid expense category,
numeric amount, and negative amounts. This keeps detailed validation
logic in Python while using Logic Apps for workflow orchestration.

## 4.4 Manager Approval Approach

For expenses of `$100` or more, Version B uses Logic Apps email/approval
capabilities to request a manager decision.

This differs from Durable Functions. Durable Functions naturally
supports an external event combined with a durable timer. In Logic Apps,
I needed to design the approval workflow using actions, conditions, and
timeout handling.

The workflow determines whether the manager approves, rejects, or does
not respond before the timeout. A timeout results in automatic approval
with the expense flagged as escalated.

## 4.5 Service Bus Topic and Subscriptions

The workflow uses a Service Bus topic for expense outcomes. Filtered
subscriptions represent Approved, Rejected, and Escalated outcomes.

This demonstrates publish/subscribe messaging and allows different
consumers to receive only the outcomes they are interested in.

## 4.6 Logic Apps Testing

The same six business scenarios were tested.

  \#   Scenario                              Expected Result
  ---- ------------------------------------- ------------------
  1    Expense under \$100                   Auto-approved
  2    Expense \>= \$100, manager approves   Approved
  3    Expense \>= \$100, manager rejects    Rejected
  4    No manager response                   Escalated
  5    Missing required field                Validation error
  6    Invalid category                      Validation error

The Logic App **Run History** was especially useful because I could
visually inspect the trigger execution, validation Function, conditions,
True/False branches, email actions, and action inputs and outputs.

I also verified the workflow by checking the emails received by the
employee.

## 4.7 Challenges --- Version B

Version B was visually easier to follow, but several data-handling
issues took time to troubleshoot.

The Service Bus trigger provided message content using Base64-encoded
`ContentData`. Therefore, the Logic App needed to correctly decode and
parse the message before accessing fields such as `employeeName`,
`employeeEmail`, `amount`, `category`, `description`, and
`managerEmail`.

I encountered errors while using JSON expressions when the message had
not been correctly decoded or when the input was already treated as an
object.

I also encountered a `BadRequest` while sending a validation error email
because the `To` value evaluated to `null`. This showed that dynamic
values must be selected carefully, especially when validation itself
fails.

The Logic App run history was useful for troubleshooting because the
graphical view showed exactly which action or condition failed.

------------------------------------------------------------------------

# 5. Comparison Analysis

## 5.1 Development Experience

The two implementations provided very different development experiences.

Durable Functions is code-first. Most of the workflow was implemented in
Python, including validation, branching, durable timers, external
events, outcome processing, and notifications. This required more
knowledge of programming and the Durable Functions execution model, but
it gave me direct control over the workflow.

Logic Apps was more visual. The designer clearly showed the trigger,
actions, conditions, and branches. It was easier to see the overall
workflow without reading code. Adding a connector or condition was also
relatively fast.

However, visual development did not mean that Logic Apps was always
easier. I spent significant time troubleshooting expressions, Base64
Service Bus content, JSON parsing, dynamic content, and null values. A
small data-format problem could cause a later action to fail.

For this project, Logic Apps was faster for visualizing the workflow,
while Durable Functions gave me more confidence in the detailed program
logic.

## 5.2 Testability

Durable Functions was easier for local testing.

I could run the Functions host with `func start` and use
`test-durable.http` to send requests directly from VS Code.

The six scenarios could be reproduced using HTTP requests. For manager
approval and rejection, I could start an orchestration, obtain its
instance ID, and send an external event through the manager decision
endpoint. This approach could also be extended with automated Python
tests.

Logic Apps testing depended more heavily on deployed Azure resources.
Testing the complete workflow required Service Bus, the Logic App, API
connections, the validation Function, and email connections.

The Logic App Run History was excellent for inspection, but the overall
workflow was less convenient for local automated testing. Therefore,
Durable Functions provided the better testing experience for this
project.

## 5.3 Error Handling

Durable Functions provided more explicit programmatic control over
errors.

Validation errors could be represented directly as structured Python
dictionaries. The orchestrator could inspect the result and immediately
choose the appropriate workflow path. Durable Functions also provides
durable state, retries, timers, and orchestration history that can
support recovery from failures.

Logic Apps provides built-in action status information and visually
identifies failed actions. This made troubleshooting easy when an action
failed. For example, I could open the failed email action and inspect
its inputs and outputs.

However, some failures were caused by expressions or null dynamic
values, and debugging them required examining the exact runtime data.

I found Logic Apps better for visually locating failures, while Durable
Functions gave me more control over how failures should be handled.

## 5.4 Human Interaction Pattern

This was one of the clearest differences between the two
implementations.

Durable Functions provided a natural solution through
`wait_for_external_event()` combined with `create_timer()`.

The orchestrator waits for whichever occurs first: the manager response
or the timeout. This directly models the business requirement.

For Logic Apps, manager interaction had to be designed using
email/approval actions, conditions, and timeout handling. It works, but
it requires more workflow configuration.

For this specific long-running approval scenario, I found Durable
Functions more natural because waiting for an external human event is
part of its orchestration model.

## 5.5 Observability

Logic Apps was stronger in immediate visual observability.

Run History displays every action in the workflow and clearly indicates
success, failure, or skipped actions. I could click an action and
inspect its inputs and outputs. This was extremely useful when debugging
conditions and email actions.

Durable Functions provides orchestration status and runtime logs. The
status endpoint showed whether an instance was running or completed and
displayed its final output.

Durable Functions observability is powerful but more developer-oriented.
Logic Apps provides a more accessible visual representation. For
operations teams or users who prefer visual monitoring, Logic Apps has
an advantage.

## 5.6 Cost

Both solutions use consumption-based Azure services, but their cost
models are different.

For approximately **100 expenses per day**, both approaches should have
relatively low execution costs because the workload is small.

Durable Functions costs are primarily related to Azure Functions
executions, function execution duration, Azure Storage operations used
to maintain durable state, and email infrastructure.

Logic Apps costs depend on trigger executions, number of workflow
actions, connector executions, Service Bus operations, and Azure
Function validation calls.

At approximately **10,000 expenses per day**, the number of actions and
messages becomes more important. A Logic App may execute many billable
actions for each expense, especially for manager approval workflows.

Durable Functions also generates multiple executions and storage
operations for orchestration checkpoints, activities, timers, and
external events.

The exact cost depends on region, pricing tier, execution time, number
of workflow actions, and connector selection. For production planning,
both architectures should be modeled using the Azure Pricing Calculator
rather than assuming that one approach is always cheaper.

------------------------------------------------------------------------

# 6. Recommendation

For this expense approval system, I would choose **Azure Durable
Functions** for a production implementation if the development team is
comfortable with Python and code-based serverless applications.

The main reason is the human interaction requirement. Expenses of `$100`
or more must wait for a manager decision while also maintaining a
timeout. Durable Functions models this requirement naturally using an
external event and a durable timer. The orchestrator can wait without
requiring a continuously running process, and workflow state is
maintained by the Durable Functions framework.

I also preferred Durable Functions for testability. I could run the
application locally, send requests from `test-durable.http`, inspect
orchestration status, and reproduce manager approval, rejection, and
timeout scenarios. The code-first design also provides more flexibility
for complex business rules and future automated testing.

However, I would choose **Logic Apps** when the workflow is
integration-heavy, needs rapid development, or must be maintained by a
team that benefits from a visual workflow designer. Logic Apps provides
excellent visual run history and managed connectors for services such as
Service Bus and Microsoft 365.

Therefore, my choice depends on the problem. For complex, stateful,
long-running application logic, I prefer Durable Functions. For
integration-focused workflows with strong visual monitoring and many
managed connectors, Logic Apps can be the better solution.

------------------------------------------------------------------------

# 7. Lessons Learned

This assignment helped me understand that two serverless technologies
can implement the same business requirement but provide very different
development experiences.

The most important lessons I learned were:

-   Durable Functions provides a natural model for stateful and
    long-running workflows.
-   External events and durable timers are effective for human
    interaction scenarios.
-   Logic Apps provides excellent visual observability.
-   Service Bus enables reliable asynchronous communication between
    components.
-   Message encoding and JSON structure are important when integrating
    Service Bus with Logic Apps.
-   Dynamic values can become `null`, especially when processing invalid
    input.
-   Validation should be designed early and tested independently.
-   Local testing is easier when business logic is implemented in code.
-   Serverless does not remove complexity; it changes where that
    complexity is managed.

If I implemented the project again, I would define the JSON message
schema earlier, test each integration independently before building the
full workflow, and add more automated tests.

------------------------------------------------------------------------

# 8. Repository Structure

``` text
CST8917-Assignment2/
├── README.md
├── version-a-durable-functions/
│   ├── function_app.py
│   ├── requirements.txt
│   ├── host.json
│   ├── local.settings.example.json
│   └── test-durable.http
├── version-b-logic-apps/
│   ├── function_app.py
│   ├── requirements.txt
│   ├── local.settings.example.json
│   ├── test-expense.http
│   └── screenshots/
└── presentation/
    ├── slides.pptx
    └── video-link.md
```

------------------------------------------------------------------------

# 9. Security

Sensitive configuration information is not committed to this repository.

The following file should be excluded from Git:

``` text
local.settings.json
```

Secrets such as SMTP passwords, Azure Storage connection strings,
Service Bus connection strings, API keys, and Azure credentials must not
be committed.

Use `local.settings.example.json` with placeholder values instead.

------------------------------------------------------------------------

# 10. References

-   Microsoft Learn. **Durable Functions overview.**\
    https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-overview

-   Microsoft Learn. **Human interaction in Durable Functions.**\
    https://learn.microsoft.com/azure/azure-functions/durable/durable-functions-overview#human

-   Microsoft Learn. **Azure Logic Apps documentation.**\
    https://learn.microsoft.com/azure/logic-apps/

-   Microsoft Learn. **Azure Service Bus documentation.**\
    https://learn.microsoft.com/azure/service-bus-messaging/

-   Microsoft Learn. **Azure Functions documentation.**\
    https://learn.microsoft.com/azure/azure-functions/

-   Microsoft Azure. **Azure Pricing Calculator.**\
    https://azure.microsoft.com/pricing/calculator/

------------------------------------------------------------------------

# 11. AI Disclosure

Generative AI tools, including ChatGPT, were used during this assignment
as a learning and development aid.

AI assistance was used for:

-   Explaining Azure Durable Functions and Logic Apps concepts
-   Debug the configuration errors
-   Reviewing error messages during testing

All implementation decisions, Azure resource configuration, testing,
debugging, screenshots, demonstrations, and final submission were
reviewed and completed by the student.

------------------------------------------------------------------------

# 12. Presentation

Slides: 

#### ScreenShot:
https://github.com/hycst/CST8917-Assignment2/tree/main/version-b-logic-apps/screenshot
https://github.com/hycst/CST8917-Assignment2/tree/main/version-a-durable-functions/screenshot


####  Demo Video: 

#####  Assignment 2 Video Part 1:
https://youtu.be/dpXarlo_fDc

##### Assignment 2 Video Part 2: (Version 1)
https://youtu.be/8_nKFAl03Ec

#####  Assignment 2 Video Part 2: (Version 2)
https://youtu.be/uxNfofaKUh0


The project presentation demonstrates both implementations and compares
their development experience, testability, error handling, human
interaction, observability, and cost.

**Presentation slides:** `presentation/slides.pptx`

**Video demonstration:** See `presentation/video-link.md`
