# -*- coding: utf-8 -*-
"""Validateur de rapport du skill lemlist-check-and-import (19/11/2026, Diego : « un validateur de complétude, plus jamais de rapport gonflé »).

Un rapport qui échoue ici NE S'AFFICHE PAS : l'agent le corrige d'abord. Code de sortie 1 = refusé.

Règles vérifiées :
  1. chaque contrôle attendu au moment donné (report_manifest.py) est présent EXACTEMENT une fois ; aucun doublon, aucun ID inconnu ou d'un autre moment ;
  2. une seule numérotation : aucune ligne « Check 14 », « 17/27 », « C1-FR » (une ligne par ID, FR et NL se disent dans le constat) ;
  3. le statut est exactement ✅ 🔴 ⚠️ ❓ 🖐️ ou N/A (rien d'autre dans la cellule) ; « non exécuté » n'est pas un statut ;
  4. un ✅ ne cache aucune réserve (exception, dérogation, non vérifié, à confirmer, partiel, accepté par) ; un N/A donne sa raison ;
  5. chaque ligne a un constat qui commence par « En clair : » (une phrase compréhensible par quelqu'un qui ne connaît ni Lemlist ni le process : ce qu'on vérifie, pourquoi c'est bon ou pas), puis « Preuve : » avec le détail technique ;
  6. la ligne « X contrôles attendus, X exécutés, X sans objet » et la ligne « Bilan : ✅ n · 🔴 n … » tombent juste sur les lignes réelles ;
  7. le verdict vient APRÈS tous les contrôles ; PRÊT interdit s'il reste un 🔴 ou un ❓ ; le tableau « Actions à prendre » vient APRÈS le verdict
     et mentionne chaque ID resté 🔴 ⚠️ ❓ ou 🖐️ ;
  8. un input déjà répondu (--answered I4,I5,...) ne se rouvre pas en ❓ sauf constat contenant « nouveau fait ».

Usage : python validate_report.py --report rapport.md --moment precheck [--existing-campaign] [--no-blacklist] [--no-extra-fields] [--no-linkedin] [--no-ab] [--answered I4,I5,I6,I7,I8]
"""
import argparse, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_manifest as rm

ID_RE = re.compile(r"^(?:[1-9]|[12]\d|3[0-7])$")
SUFFIXED_RE = re.compile(r"^\d+\s*[-/·]\s*\S+")
OLD_RE = re.compile(r"^(check|contrôle|controle)\s*\d", re.I)
RESERVE_RE = re.compile(r"exception|waiver|to confirm|not verified|not rechecked|partial|accepted by", re.I)
MISSING_RE = re.compile(r"\b([1-9]\d*)\s+(?:values?\s+)?(?:empty|missing|absent|incomplete|not covered)\b", re.I)
NEGATIVE_RE = re.compile(r"\b(?:except|but|however)\b|\b(?:missing|empty|incomplete|not covered|gap|error|anomaly)\b", re.I)


def norm_status(s):
    s = s.replace("️", "").strip()
    for st in rm.STATUSES:
        if s == st.replace("️", ""):
            return st
    return None


def cells(line):
    parts = [c.strip() for c in line.strip().strip("|").split("|")]
    return parts


def clean_id(c):
    return c.replace("*", "").replace("`", "").strip()


def green_contradiction(check_id, constat):
    """Return the suspicious fragment when a PASS sentence contradicts itself."""
    m = RESERVE_RE.search(constat) or MISSING_RE.search(constat)
    if m:
        return m.group(0)
    # Remove explicit zero/absence statements before looking for negative wording.
    cleaned = re.sub(r"\b0\s+(?:[\w-]+\s+){0,3}(?:empty|missing|absent|errors?|anomalies|gaps?)\b", "", constat, flags=re.I)
    cleaned = re.sub(r"\b(?:no|without)\s+(?:[\w-]+\s+){0,3}(?:missing|empty|error|anomaly|gap|problem)\b", "", cleaned, flags=re.I)
    m = NEGATIVE_RE.search(cleaned)
    if m:
        return m.group(0)
    # L11 contains mandatory company-field coverage: partial ratios cannot be green.
    if check_id == "L11":
        for got, total in re.findall(r"\b(\d+)\s*/\s*(\d+)\b", constat):
            if int(total) > 0 and int(got) < int(total):
                return "%s/%s" % (got, total)
    return None


def validate(text, moment, blacklist=True, extra_fields=True, linkedin=True, ab=True, existing_campaign=False, answered=()):
    errors = []
    lines = text.splitlines()
    exp = rm.expected(moment, blacklist, extra_fields, linkedin, ab, existing_campaign)

    # report landmarks
    verdict_idx = next((i for i, l in enumerate(lines) if re.match(r"^\W*Verdict\s*:", l.strip().replace("*", ""), re.I) or re.match(r"^\**\s*Verdict\s*:", l.strip(), re.I)), None)
    actions_idx = next((i for i, l in enumerate(lines) if re.search(r"Actions to take", l, re.I) and l.lstrip().startswith("#")), None)
    if verdict_idx is None:
        errors.append("verdict absent (« Verdict : **[PRÊT POUR L'ÉTAPE SUIVANTE | BLOQUÉ] — raison.** » après tous les contrôles)")
    if actions_idx is None:
        errors.append("missing 'Actions to take' table")
    limit = min([x for x in (verdict_idx, actions_idx) if x is not None] or [len(lines)])

    rows = {}      # id -> (status, constat, nom)
    row_positions = {}
    seen = []
    last_check_line = -1
    for i, l in enumerate(lines[:limit]):
        if not l.strip().startswith("|"):
            continue
        c = cells(l)
        if len(c) < 3:
            continue
        first = clean_id(c[0])
        if first in ("#", "---:", "---", "Check", "Control", "Mailbox") or set(first) <= set("-: "):
            continue
        if SUFFIXED_RE.match(first):
            errors.append("line %d: suffixed check ID %s; use one row per check" % (i + 1, first))
            continue
        if ID_RE.match(first):
            last_check_line = i
            seen.append(first)
            if first in rows:
                continue
            status = norm_status(c[2]) if len(c) > 2 else None
            constat = " | ".join(c[3:]).strip() if len(c) > 3 else ""
            if status is None:
                errors.append("%s : statut invalide « %s » (✅ 🔴 ⚠️ ❓ 🖐️ ou N/A, rien d'autre dans la cellule)" % (first, c[2] if len(c) > 2 else ""))
            rows[first] = (status, constat, c[1] if len(c) > 1 else "")
            row_positions[first] = i
        elif OLD_RE.match(first):
            errors.append("line %d: write the numeric check ID only, not %s" % (i + 1, first))

    # 1. présence exacte
    for i in exp:
        n = seen.count(i)
        if n == 0:
            errors.append("missing expected check %s" % i)
        elif n > 1:
            errors.append("%s en double (%d lignes)" % (i, n))
    for i in set(seen):
        if i not in exp:
            errors.append("%s n'a pas sa place à ce moment (« %s »)" % (i, moment))

    # 3 à 5 : contenu des lignes
    for i, (st, constat, nom) in rows.items():
        if st is None:
            continue
        if st == "N/A":
            if len(constat) < 10:
                errors.append("%s : N/A sans raison (écrire « N/A — raison »)" % i)
            continue
        if len(constat) < 15:
            errors.append("%s : constat vide ou sans preuve" % i)
        elif not constat.lstrip("* ").startswith("In plain English:"):
            errors.append("%s: finding must start with 'In plain English:' and then include 'Evidence:'" % i)
        if st != "N/A" and "Evidence:" not in constat:
            errors.append("%s: missing Evidence: label" % i)
        contradiction = green_contradiction(i, constat) if st == "✅" else None
        if contradiction:
            errors.append("%s : ✅ qui cache une réserve (« %s ») : mettre ⚠️, ❓ ou 🔴" % (i, contradiction))
        if st == "❓":
            for inp, chk in rm.INPUT_TO_CHECK.items():
                if chk == i and inp in answered and "nouveau fait" not in constat.lower():
                    errors.append("%s : ❓ sur un input déjà répondu (%s) : citer la réponse de Diego, ou écrire « nouveau fait : … »" % (i, inp))

    # totals
    counts = {s: 0 for s in rm.STATUSES}
    for i, (st, _, _) in rows.items():
        if st in counts and i in exp:
            counts[st] += 1
    m = re.search(r"(\d+)\s+checks expected\s*,\s*(\d+)\s+executed\s*,\s*(\d+)\s+not applicable", text, re.I)
    if not m:
        errors.append("missing 'X checks expected, X executed, X not applicable' line")
    else:
        att, exe, so = map(int, m.groups())
        if att != len(exp):
            errors.append("total annoncé %d ≠ %d contrôles attendus à ce moment" % (att, len(exp)))
        if exe + so != att:
            errors.append("%d exécutés + %d sans objet ≠ %d attendus" % (exe, so, att))
        if so != counts["N/A"]:
            errors.append("%d sans objet annoncés ≠ %d lignes N/A" % (so, counts["N/A"]))
    b = re.search(r"Summary\s*:\s*(.+)", text, re.I)
    if not b:
        errors.append("missing Summary line")
    else:
        got = {}
        for sym, n in re.findall(r"(✅|🔴|⚠️?|❓|🖐️?|N/A)\s*(\d+)", b.group(1)):
            if norm_status(sym) in got:
                errors.append("Bilan : le statut %s apparaît deux fois" % sym)
            got[norm_status(sym)] = int(n)
        for st in rm.STATUSES:
            if got.get(st, 0) != counts[st]:
                errors.append("Bilan : %s annoncé %d, lignes réelles %d" % (st, got.get(st, 0), counts[st]))

    # 7 : ordre et verdict
    if verdict_idx is not None:
        if last_check_line > verdict_idx:
            errors.append("un contrôle apparaît après le verdict")
        v = lines[verdict_idx].upper()
        ready = "READY FOR THE NEXT STEP" in v
        blocked = "BLOCKED" in v
        if not ready and not blocked:
            errors.append("invalid verdict: use exactly READY FOR THE NEXT STEP or BLOCKED")
        if ready and (counts["🔴"] or counts["❓"]):
            errors.append("verdict PRÊT alors qu'il reste %d 🔴 et %d ❓" % (counts["🔴"], counts["❓"]))
        if blocked and not (counts["🔴"] or counts["❓"]):
            errors.append("verdict BLOQUÉ sans aucun 🔴 ni ❓")
    if verdict_idx is not None and actions_idx is not None and actions_idx < verdict_idx:
        errors.append("'Actions to take' must come after the verdict")
    if actions_idx is not None:
        action_rows = []
        for line in lines[actions_idx + 1:]:
            if not line.strip().startswith("|"):
                continue
            c = cells(line)
            if len(c) == 5 and c[0] not in ("#", "---:") and not set(c[0]) <= set("-: "):
                action_rows.append(c)
        for i, (st, _, _) in rows.items():
            if st in ("🔴", "⚠️", "❓", "🖐️"):
                matches = [c for c in action_rows if re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(i), c[2])]
                if not matches:
                    errors.append("%s (%s) missing from the 'Actions to take' table" % (i, st))
                elif not any(norm_status(c[1]) == st for c in matches):
                    errors.append("%s : niveau de l'action différent du statut %s" % (i, st))
                elif any(len(c[3].strip()) < 2 or len(c[4].strip()) < 5 for c in matches):
                    errors.append("%s : responsable ou action exacte manquant" % i)
    return errors


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--moment", required=True, choices=["precheck", "post_draft", "post_import"])
    ap.add_argument("--no-blacklist", action="store_true")
    ap.add_argument("--no-extra-fields", action="store_true")
    ap.add_argument("--no-linkedin", action="store_true")
    ap.add_argument("--no-ab", action="store_true")
    ap.add_argument("--existing-campaign", action="store_true")
    ap.add_argument("--answered", default="", help="inputs déjà répondus, ex. I4,I5,I6,I7,I8")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    text = Path(a.report).read_text(encoding="utf-8")
    errs = validate(text, a.moment, not a.no_blacklist, not a.no_extra_fields, not a.no_linkedin, not a.no_ab, a.existing_campaign,
                    tuple(x.strip() for x in a.answered.split(",") if x.strip()))
    if errs:
        print("RAPPORT REFUSÉ : %d défaut(s). Le corriger avant de l'afficher." % len(errs))
        for e in errs:
            print(" - " + e)
        return 1
    print("REPORT ACCEPTED: expected checks, totals, verdict and actions are consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
