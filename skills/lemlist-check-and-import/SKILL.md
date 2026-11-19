---
name: lemlist-check-and-import
description: Audit a lead list and outbound sequence, create or verify a Lemlist draft, import the approved lead batch, and prepare launch only after separate human approvals. Use before importing or launching a Lemlist campaign.
---

# Lemlist Check & Import

Run one workflow from source data to launch readiness. Never treat a successful API response as proof: read the resulting state back and compare it with the approved input.

## Safety contract

1. Keep API keys in environment variables or an uncommitted `.env` file.
2. Write reports and exports outside this skill directory.
3. Never create or modify a Lemlist campaign before showing the audit and receiving explicit approval for the draft.
4. Approval to create the draft does not authorize importing leads.
5. Approval to import a specific batch does not authorize launching it.
6. Never delete, pause or overwrite existing leads without separate explicit approval.
7. A skipped or unavailable check is not green. Mark it `NOT RUN` and explain why.

## Inputs

Resolve or ask for:

- the exact sequence and language variants;
- the exact lead source and scope;
- the target Lemlist team and campaign;
- the blacklist source, if any;
- the maximum contacts per company;
- whether personal addresses are permitted and supported by consent;
- required custom fields and routing rules;
- senders, schedule and timezone.

## Use the bundled scripts

Resolve paths relative to this skill directory and keep every generated report outside it.

- Before enrichment or import, run `scripts/blacklist_and_dedup_check.py` on the exact CSV/XLSX batch and `scripts/dedupe_before_pay.py` against the Lemlist account.
- Run `scripts/final_check.py` on the exported campaign, pushed-field mapping and optional downstream-field mapping.
- Run `scripts/variable_junction_check.py` on every distinct variable value in the batch.
- Run `scripts/render_gap_check.py` after Liquid rendering to cover every branch and Whitespace & paragraph rendering.
- Use `scripts/account_control.py` for account-wide duplicates and email/company coherence.
- Use `scripts/import_leads.py` for the guarded dry-run/import/read-back workflow. `--apply` always requires `--approval` containing the explicit approval for that exact batch.
- Use `scripts/campaign_end_date.py` to simulate sender capacity and completion dates.
- Use `scripts/verify_no_loss.py` to reconcile source and final outputs.

Read `README.md` for concrete commands and dependencies. A script failure, unavailable input or skipped script must appear as `NOT RUN`, never `PASS`.

## Workflow

### 1. Audit copy and leads together

Read [references/checklist.md](references/checklist.md) and run every applicable check against the actual sequence and the exact lead batch. Render Liquid branches with representative and empty values. Scan the full Lemlist account for existing people before recommending import.

Return a table with `#`, `Check`, `Status`, `Evidence`, and `Action`. Then show the resolved sequence tree and ask for approval to create or update the draft.

### 2. Create or verify the draft

After explicit draft approval, create or update only the campaign structure. Keep it paused and import no leads. Read back sequence steps, conditions, delays, settings, labels, schedule and senders. Report any mismatch.

### 3. Prepare the import package

Re-run batch duplicates, account-wide duplicates and blacklist checks immediately before import. Show:

- campaign IDs;
- exact lead counts per campaign;
- field mapping;
- exclusions and reasons;
- a stable fingerprint of the approved input file.

Ask for approval to import this exact batch.

### 4. Import and verify

After explicit import approval, import with deduplication enabled. Read the leads back and compare every required field with the approved source. Confirm counts, routing and CRM synchronization where applicable. Preview every message for a representative sample that covers all branches, plus at least 50 leads when the batch is large enough.

### 5. Launch gate

Show the final checklist with no unresolved blocking issue. State the expected start and completion dates, sender capacity and remaining human tests. Ask for a separate explicit launch approval. Never launch implicitly.

## Report statuses

- `PASS`: executed with evidence and compliant.
- `BLOCK`: must be corrected before the next mutation.
- `DECISION`: requires an explicit user choice.
- `HUMAN TEST`: requires inbox or UI verification.
- `NOT RUN`: unavailable or not applicable, with a reason.
