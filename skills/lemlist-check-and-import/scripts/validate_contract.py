from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]
skill = root / "SKILL.md"
checklist = root / "references" / "checklist.md"
errors = []

if not skill.is_file():
    errors.append("missing SKILL.md")
if not checklist.is_file():
    errors.append("missing references/checklist.md")

skill_text = skill.read_text(encoding="utf-8") if skill.is_file() else ""
checklist_text = checklist.read_text(encoding="utf-8") if checklist.is_file() else ""

for section in ["Safety contract", "Mandatory input gate", "Workflow", "Report statuses"]:
    if section not in skill_text:
        errors.append(f"missing section: {section}")

gate_markers = [
    "<!-- CONTRACT:INPUT_GATE:NO_CHECK_BEFORE_RESOLVED -->",
    "<!-- CONTRACT:INPUT_GATE:ASK_ONCE_AND_STOP -->",
]
for marker in gate_markers:
    if marker not in skill_text:
        errors.append(f"missing mandatory input-gate marker: {marker}")

input_ids = re.findall(r"(?m)^\| (I\d+) \|", skill_text)
expected_input_ids = [f"I{i}" for i in range(1, 13)]
if input_ids != expected_input_ids:
    errors.append("mandatory input register must contain exactly I1 through I12 in order")

gate_phrases = [
    "Before any audit, quality check, bundled script, enrichment, or Lemlist API/MCP call",
    "ask for all unresolved inputs in one numbered message",
    "then **STOP**",
    "No partial pre-check is allowed",
    "do not authorize creating a draft, importing leads, or launching a campaign",
]
for phrase in gate_phrases:
    if phrase not in skill_text:
        errors.append(f"missing mandatory input-gate rule: {phrase}")

gate_position = skill_text.find(gate_markers[0])
workflow_position = skill_text.find("## Workflow")
if gate_position == -1 or workflow_position == -1 or gate_position > workflow_position:
    errors.append("mandatory input gate must appear before the workflow")

sys.path.insert(0, str(root / "scripts"))
import report_manifest as rm

documented = re.findall(r"(?m)^- \*\*([LCEDP]\d+(?:bis)?) ", checklist_text)
if sorted(documented) != sorted(rm.CHECKS):
    missing = sorted(set(rm.CHECKS) - set(documented))
    extra = sorted(set(documented) - set(rm.CHECKS))
    errors.append("checklist and report_manifest.py disagree (missing: %s, unknown: %s)" % (missing, extra))
if len(rm.CHECKS) != 41:
    errors.append("expected 41 checks in the manifest, found %d" % len(rm.CHECKS))

for script in [
    "account_control.py",
    "blacklist_and_dedup_check.py",
    "campaign_end_date.py",
    "dedupe_before_pay.py",
    "final_check.py",
    "format_message.py",
    "import_leads.py",
    "render_gap_check.py",
    "variable_junction_check.py",
    "verify_no_loss.py",
    "report_manifest.py",
    "validate_report.py",
    "finalize_report.py",
    "test_validate_report.py",
    "company_dedupe.py",
    "test_company_dedupe.py",
    "progression.py",
]:
    if not (root / "scripts" / script).is_file():
        errors.append(f"missing script: {script}")

if errors:
    print("CONTRACT INVALID")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("CONTRACT VALID: 12-input hard gate, 41 checks (L/C/E/D/P), executable scripts present")
