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

for section in ["Safety contract", "Inputs", "Workflow", "Report statuses"]:
    if section not in skill_text:
        errors.append(f"missing section: {section}")

numbers = [int(x) for x in re.findall(r"(?m)^(\d+)\. ", checklist_text)]
if numbers != list(range(1, 38)):
    errors.append("checklist must contain exactly checks 1 through 37")

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
]:
    if not (root / "scripts" / script).is_file():
        errors.append(f"missing script: {script}")

if errors:
    print("CONTRACT INVALID")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("CONTRACT VALID: public skill, 37 checks, executable scripts present")
