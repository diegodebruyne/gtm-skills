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
7. A skipped or unavailable check is not green. Use `❓`, `🖐️`, or `N/A` with a reason; never mark it `✅`.

## Mandatory input gate

<!-- CONTRACT:INPUT_GATE:NO_CHECK_BEFORE_RESOLVED -->
Before any audit, quality check, bundled script, enrichment, or Lemlist API/MCP call, create an input register containing every item below. Mark each item `RESOLVED`, `MISSING`, `CONFLICT`, or `N/A` with a reason and its source.

| ID | Required input |
|---|---|
| I1 | Exact sequence, source and language variant(s) |
| I2 | Exact lead file/source |
| I3 | Exact scope: sheet, view, filters and expected lead count |
| I4 | Whether personal email addresses are allowed and supported by consent |
| I5 | Policy for people and companies already present in Lemlist (people: never re-contacted; companies: `all`, `replied`, `interested` or `none`) |
| I6 | Blacklist source(s), or explicit confirmation that none applies |
| I7 | Maximum contacts per company |
| I8 | Required fields, custom variables, mapping and routing rules |
| I9 | Target campaign(s): new or existing, with names or IDs |
| I10 | Target Lemlist team/account and available access |
| I11 | Sender(s) per campaign |
| I12 | Schedule, timezone and required campaign settings or labels |

Resolve values already supplied by the user or unambiguously present in the named source; do not ask twice. During input discovery, inspect only the minimum metadata needed to resolve the register, such as sheet names and headers. Do not evaluate lead quality, duplicates, blacklists, copy, campaign health, or account contents yet.

<!-- CONTRACT:INPUT_GATE:ASK_ONCE_AND_STOP -->
If any item is `MISSING` or `CONFLICT`, ask for all unresolved inputs in one numbered message, recommend a safe default where useful, then **STOP**. No partial pre-check is allowed. No check starts until all I1-I12 inputs are `RESOLVED` or explicitly `N/A` with a reason.

Show the completed input register before beginning the audit. Answers to input questions resolve context only: they do not authorize creating a draft, importing leads, or launching a campaign.

## Use the bundled scripts

Resolve paths relative to this skill directory and keep every generated report outside it.

- Before enrichment or import, run `scripts/blacklist_and_dedup_check.py` on the exact CSV/XLSX batch and `scripts/dedupe_before_pay.py` against the Lemlist account.
- Run `scripts/final_check.py` on the exported campaign, pushed-field mapping and optional downstream-field mapping.
- Run `scripts/variable_junction_check.py` on every distinct variable value in the batch.
- Run `scripts/render_gap_check.py` after Liquid rendering to cover every branch and Whitespace & paragraph rendering.
- Use `scripts/account_control.py` for account-wide duplicates and email/company coherence.
- Use `scripts/import_leads.py` for the guarded dry-run/import/read-back workflow. `--apply` always requires `--approval` containing the explicit approval for that exact batch.
- Use `scripts/company_dedupe.py` for the company-level policy chosen in I5 (match = same full domain or same company LinkedIn page; a domain shared by several properties only informs).
- Use `scripts/progression.py` to keep the 8-step progress table (see below).
- Use `scripts/campaign_end_date.py` to simulate sender capacity and completion dates.
- Use `scripts/verify_no_loss.py` to reconcile source and final outputs.

Read `README.md` for concrete commands and dependencies. A script failure, unavailable input or skipped script must use `❓`, `🖐️`, or `N/A` with a reason, never `✅`.

## One numbering, one manifest, one validator

A report uses only the IDs **L, C, E, D, P** (40 checks, see [references/checklist.md](references/checklist.md)). One ID = one row: never `C1-FR`, never `17/27`, never two IDs merged. Languages are mentioned inside the finding.

Before showing any report:

1. Run `scripts/report_manifest.py --moment <precheck|post_draft|post_import> [--existing-campaign] [--no-blacklist] [--no-extra-fields] [--no-linkedin] [--no-ab]`. It prints the exact skeleton: the checks expected at that moment.
2. Fill one row per ID with a status and evidence. **Every finding starts with `In plain words:`** (one sentence anybody can follow: what is checked, why it is fine or not) **then `Evidence:`** (the technical detail). "Not run" is not a status: use `❓` (a decision is needed), `🖐️` (a human check is needed) or `N/A - reason`. A `✅` may not contain an exception, a missing value, incomplete coverage, an unverified claim or a waiver; it may only cite a dated decision of the user ("decision by <name> on dd/mm").
3. The check NAME is always a column (`# | Check | Result | Evidence and finding`). Never show a shortened or reformatted version of the validated report.
4. Write the report first as a private draft outside the skill directory, then run `scripts/finalize_report.py --draft <draft.md> --output <final.md> --moment <moment> [same options] --answered I4,I5,I6,I7,I8`. Show only the generated final file. If it is refused, fix the draft and rerun.
5. Report layout, in this order: sections Leads, Sequence and copy, Senders, then `### E1 detail: mailboxes` (7 columns: mailbox, score, spam rate, warm-up, connection, DNS/blacklist, verdict); a `Summary:` line (`✅ n · 🔴 n · ⚠️ n · ❓ n · 🖐️ n · N/A n`); the line `X checks expected, X executed, X not applicable`; the `Verdict:` line (`READY FOR THE NEXT STEP` or `BLOCKED`); then `### Actions to take`, one row for every `🔴 ⚠️ ❓ 🖐️` (never a row without an action).
6. An input already answered (I4 -> L5, I5 -> L4, I6 -> L9, I7 -> L8, I8 -> L10) is not reopened as `❓`: the report quotes the user's answer. Only a `❓` starting with `new fact:` is allowed.
7. A deviation (cap, missing field, excluded mailbox) is never taken by the agent: it is a `❓` with the agent's proposal.
8. An anomaly outside the batch and the target campaigns goes in a section "Good to know, outside the scope of this import" and does not change the verdict.

## Do not re-run everything when corrections are settled together

1. One complete check (all IDs of the moment) per batch, once. Open decisions are grouped in ONE message, answered together, then all corrections are applied together.
2. After the decided corrections, verify only what changed: (a) a line-by-line comparison of old and new files proves that ONLY the decided changes happened; (b) re-read live only the checks those corrections touch; (c) update, inside the report already validated, only the affected rows (new status, dated decision cited) and rerun the validator. Unchanged rows keep their original evidence and date.
3. A complete re-run happens only if the user asks, or if the batch, the target campaigns or the sequence change in a way that was not decided.
4. Totals of the final batch are recomputed and stated as they are, never copied from an earlier announcement.
5. After the corrections the user sees "ready" or "not ready" in three lines, with the full report attached.

## Workflow

### 1. Audit copy and leads together

Only after the mandatory input gate is open, read [references/checklist.md](references/checklist.md) and run every applicable check against the actual sequence and the exact lead batch. Render Liquid branches with representative and empty values. Scan the full Lemlist account for existing people before recommending import.

Return the finalized report, then show the resolved sequence tree and ask for approval to create or update the draft.

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

After explicit import approval, import with deduplication enabled. Read the leads back and compare every required field with the approved source. Confirm counts, routing and CRM synchronization where applicable. Preview every message for a representative sample that covers all branches, plus at least 25 leads (more when the batch is large).

### 5. Launch gate

Show the final checklist with no unresolved blocking issue. State the expected start and completion dates, sender capacity and offer the optional reply test described below. Ask for a separate explicit launch approval. Never launch implicitly.

## Automatic chaining and progress table

The workflow has 8 fixed steps tracked by `scripts/progression.py`: 1 check the copy and the leads, 2 create the campaigns (only if they do not exist), 3 import dossier, 4 approval to import, 5 import, 6 post-import checks (+ optional reply test), 7 approval to launch, 8 launch.

1. At the start of a run: `python scripts/progression.py init --dir <run>`. Whenever a step changes: `progression.py set --dir <run> --step <n> --state <done|in_progress|todo|waiting_user|not_needed> --note "<figure or quote>"`.
2. Show the output of `progression.py show` at the top of EVERY message to the user, with the next step. The user never has to ask "where are we?".
3. Everything that is not an approval chains on its own: when a step is done, start the next one in the same turn. Never ask "shall I continue?".
4. Only allowed stops: the three approvals; an open decision (`❓`, grouped in one message); an action only the user can do, given with the exact steps.
5. An approval is set to `done` only with the user's own words in `--note` (the script refuses otherwise). It is never inferred from "continue", "ok" on something else, or silence, and it covers only the action it names.
6. When a background agent works, the step stays `in_progress`; the main agent validates the returned report itself before announcing anything, then says "ready to launch" or "not ready" in three lines with the report attached.
7. Each message ends with the next action in one sentence.
8. A light touch of humor (one short line, prefixed by an emoji, printed by `progression.py set`) and a paraphrased line from Marcus Aurelius' Meditations follow each successful step. Never on an error, a blocker or a serious decision, never inside a report, never to play down a risk. The quotes are paraphrases written from memory, always labelled as such.

## Step 7 of 8 (optional): one last tip before launching

The **reply test is an optional final recommendation, not one of the 40 checks**. It is always advised, never imposed and never blocking. Its purpose is not technical (P3 already checked renders live): the person using the skill puts themselves in the prospect's shoes and answers one question: **"would I reply to this email?"**

The agent proposes it with this message, plain words, no jargon:

1. Title: **Step 7 of 8 (optional): one last tip before launching.**
2. Two sentences of status (leads are in Lemlist, nothing was sent).
3. The advice: send yourself the email and read it as the prospect (optional).
4. Why: a script cannot tell whether an email makes you want to reply; seen in a real inbox you notice it is too long, a text block is too heavy, bold is missing, the first sentence does not hook; you also see the real rendering (signature, photo, GIF, PS, mobile layout); it is the last free chance to fix things before everyone receives it.
5. How, in 2 minutes: open the campaign in Lemlist, Sequence tab; send a test of email 1 to your own address; read it asking "would I reply?"; **never click Launch or Review**, that would send to the whole batch.
6. "Tell me: fine as it is, or what you would change. You can skip this test."
7. Then the launch approval request, with the exact number of leads and their split, and "nothing leaves before your word".

The reply test never enters the validated report and never blocks the launch. Record the user's answer separately as an optional recommendation outcome.

## Report statuses

- `✅`: executed with evidence and compliant.
- `🔴`: must be corrected before the next mutation.
- `⚠️`: verified risk that does not block the next gate.
- `❓`: requires an explicit user choice.
- `🖐️`: requires inbox or UI verification.
- `N/A`: not applicable, with a reason.
