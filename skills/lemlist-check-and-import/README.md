# Lemlist Check & Import

A Claude Code skill that audits an outbound sequence and its lead batch before creating a Lemlist draft, importing leads or preparing launch.

It includes a 41-check checklist with one numbering (L leads, C sequence and copy, E senders, D draft settings, P post-import) covering data quality, targeting, Liquid variables, sequence architecture, duplicate and blacklist checks, senders, deliverability settings, capacity, previews and post-import verification.

Every report is built from a manifest and refused by a validator unless it is complete: one row per check, a plain-words explanation before the evidence, honest statuses, exact totals, a verdict and an action table. A progress table shows the 8 workflow steps and chains them automatically; the only mandatory stops are the three approvals.

## Install

Copy this folder to:

```text
~/.claude/skills/lemlist-check-and-import
```

Restart Claude Code or open a new session, then ask it to use `lemlist-check-and-import` before importing or launching a Lemlist campaign.

## Credentials

Prefer a connected Lemlist MCP server. For scripts or direct API calls, provide the key through an environment variable or an uncommitted `.env` file based on `.env.example`.

Never commit a real API key, lead export, blacklist, campaign report or client dataset.

## Included scripts

The package includes executable checks in `scripts/`:

- `blacklist_and_dedup_check.py`: blacklist, duplicate and contacts-per-company checks on CSV/XLSX files;
- `dedupe_before_pay.py`: account-wide Lemlist duplicate check before paid enrichment;
- `variable_junction_check.py`: variable joins, missing fallbacks and malformed rendered phrases;
- `render_gap_check.py`: Whitespace & paragraph rendering across Liquid branches;
- `final_check.py`: local sequence, variable, unsubscribe and downstream-field checks;
- `account_control.py`: account-wide duplicates and email/company coherence;
- `import_leads.py`: guarded import, read-back and field-by-field comparison;
- `campaign_end_date.py`: sending-capacity and completion-date simulation;
- `format_message.py`: consistent Lemlist HTML and LinkedIn formatting;
- `verify_no_loss.py`: source-to-output record reconciliation;
- `report_manifest.py`, `validate_report.py`, `finalize_report.py`: the single check numbering, the report validator and the finalizer that only writes an accepted report;
- `company_dedupe.py`: company-level duplicates with a policy (`all`, `replied`, `interested`, `none`); a match is the same full domain or the same company LinkedIn page;
- `progression.py`: the 8-step progress table (an approval is marked done only with the user's own words).

Install the optional XLSX dependency with:

```bash
python -m pip install -r requirements.txt
```

Run the self-tests:

```bash
python scripts/test_validate_report.py
python scripts/test_company_dedupe.py
python scripts/validate_contract.py
```

Run the included local demonstrations:

```bash
python scripts/blacklist_and_dedup_check.py --leads examples/leads-demo.csv --email-col email --linkedin-col linkedinUrl --vat-col vat --company-col companyName --blacklist examples/blacklist-demo.json

python scripts/variable_junction_check.py --template examples/template-demo.json --leads examples/variables-demo.csv --out /tmp/variable-report.csv
```

The examples are intentionally faulty so the scripts produce findings.

When a source file contains operational tracking columns that must not be sent to Lemlist, pass their exact names with `--ignore-fields "column one,column two"`. Use `--extra-vars` only for intentional Lemlist custom fields.

## Important

The skill separates three approvals (and offers one optional, never blocking, reply test before launch):

1. create or update the draft;
2. import the exact lead batch;
3. launch the campaign.

One approval never implies the next.
