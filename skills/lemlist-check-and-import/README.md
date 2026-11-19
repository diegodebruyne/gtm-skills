# Lemlist Check & Import

A Claude Code skill that audits an outbound sequence and its lead batch before creating a Lemlist draft, importing leads or preparing launch.

It includes a 37-point checklist covering data quality, targeting, Liquid variables, sequence architecture, duplicate and blacklist checks, senders, deliverability settings, capacity, previews and post-import verification.

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
- `verify_no_loss.py`: source-to-output record reconciliation.

Install the optional XLSX dependency with:

```bash
python -m pip install -r requirements.txt
```

Run the included local demonstrations:

```bash
python scripts/blacklist_and_dedup_check.py --leads examples/leads-demo.csv --email-col email --linkedin-col linkedinUrl --vat-col vat --company-col companyName --blacklist examples/blacklist-demo.json

python scripts/variable_junction_check.py --template examples/template-demo.json --leads examples/variables-demo.csv --out /tmp/variable-report.csv
```

The examples are intentionally faulty so the scripts produce findings.

When a source file contains operational tracking columns that must not be sent to Lemlist, pass their exact names with `--ignore-fields "column one,column two"`. Use `--extra-vars` only for intentional Lemlist custom fields.

## Important

The skill separates three approvals:

1. create or update the draft;
2. import the exact lead batch;
3. launch the campaign.

One approval never implies the next.
