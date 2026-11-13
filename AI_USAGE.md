# AI Usage Disclosure

## Tools used

ChatGPT (OpenAI).

## What I used them for

I used ChatGPT to understand the assignment requirements, plan the SQLite architecture, generate initial Python implementations, develop normalization tests, troubleshoot Python and PowerShell errors, and create report-generation and validation commands.

I also used ChatGPT to help prepare and review the submission documentation.

## What I wrote or decided myself

I selected Assignment A, configured the local development environment, generated the sample datasets, executed the pipeline, investigated errors, ran tests, checked the generated reports, and reviewed the submission requirements.

## Where the AI was wrong or unhelpful

An earlier suggested modification to the reporting module introduced an indentation-related syntax error. I detected the issue through Python compilation, replaced the affected module with a corrected version, and verified that it compiled and generated reports successfully.

Some suggested downloadable files were also unavailable, so I used the code provided directly in the conversation.

## How I verified AI-generated code

- Ran 11 normalization tests successfully.
- Compiled and executed the reporting module.
- Generated all five required reports.
- Checked that batch totals and bucket counts reconcile.
- Verified that connected-call counts do not exceed total-call counts.
- Reconciled duplicate-lead statistics against database totals.
- Re-ingested both data drops and confirmed that lead and event counts remained unchanged.

These checks validate important functionality but do not constitute exhaustive end-to-end testing.