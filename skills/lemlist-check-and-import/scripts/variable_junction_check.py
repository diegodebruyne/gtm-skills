#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Etape 7 de lemlist-check-and-import : controle de SENS des variables, sur 100 % des leads, sans credit, sans appel reseau.

Ce que ca attrape (ex. reel : la variable vaut "chemin de" et le texte de la copy continue par "de" : "...le chemin de de ...") :
  - mot doublé a la jonction (fin du texte + debut de la valeur, ou fin de la valeur + debut du texte)
  - article / preposition en trop ou qui se suivent (de + de, de + du, la + le, de + la...)
  - élision oubliee (de + Alice -> d'Alice ; que + il -> qu'il)
  - majuscule/minuscule incoherente apres un point ou en debut de phrase
  - ponctuation doublee (valeur finissant par "." puis "." ou ",")
  - valeur vide (sans repli), espaces en trop, restes techniques ({{, {%, undefined, null, NaN, #N/A, [object)
Entrees
  --template  fichier JSON : liste de {"step": "email 1", "subject": "...", "body": "..."} (texte brut des steps, tel que renvoye par
              get_campaign_sequences), ou un fichier texte unique (un seul step)
  --leads     CSV des leads (un export search_campaign_leads) : une colonne par variable, nom insensible a la casse
Sortie
  --out report.csv : une ligne par (step, variable, valeur distincte) a probleme : severite, raison, nb de leads touches, contexte.
Severite BLOQUANT = erreur quasi certaine ; A RELIRE = possible selon la langue, un humain ou l'agent tranche.
Le script ne corrige rien. Il ne remplace pas la preview (preview_email) : il couvre TOUTES les valeurs, la preview couvre le rendu.
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict

BUILTIN_VARS = {"signature", "unsubscribeUrl", "unsubscribeLink", "sender.firstName"}

FUNC = {"de", "du", "des", "d", "la", "le", "les", "l", "un", "une", "a", "au", "aux", "chez", "que", "qu", "en", "sur", "pour", "avec", "dans",
        "het", "een", "van", "voor", "bij", "op", "in", "met", "naar", "the", "of", "to", "for", "at", "an", "and", "et", "en", "ou"}
ELIDE = {"de", "que", "le", "la", "je", "ne", "se", "ce", "me", "te", "si"}
BAD_TOKENS = ("{{", "}}", "{%", "%}", "undefined", "null", "nan", "#n/a", "n/a", "[object", "#ref", "#value", "error")
VAR = re.compile(r"\{\{\s*([A-Za-z0-9_\.]+)\s*(?:\|[^}]*)?\}\}")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9']+", " ", s).strip()


def words(s):
    return [w for w in re.split(r"[\s']+", norm(s)) if w]


def html_to_text(s):
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&nbsp;", " ").replace("&amp;", "&")


def contexts(text):
    """Pour chaque {{variable}} du texte : (nom, texte litteral a gauche, texte litteral a droite, a_un_repli)."""
    t = html_to_text(text)
    t = re.sub(r"\{%.*?%\}", "¦", t, flags=re.S)  # une balise Liquid = frontiere inconnue
    out = []
    for m in VAR.finditer(t):
        left = t[max(0, m.start() - 80): m.start()]
        right = t[m.end(): m.end() + 80]
        left = left.split("¦")[-1].split("{{")[-1].split("}}")[-1]
        right = right.split("¦")[0].split("{{")[0]
        out.append((m.group(1).lower(), left, right, "default" in m.group(0).lower()))
    return out


def check(value, left, right, has_default):
    """Renvoie une liste de (severite, raison)."""
    res = []
    v = str(value if value is not None else "")
    if not v.strip():
        return [] if has_default else [("A RELIRE", "valeur vide sans repli (default) : le texte autour peut devenir incomplet")]
    if v != v.strip():
        res.append(("A RELIRE", "espace en trop au debut ou a la fin de la valeur"))
    if "  " in v:
        res.append(("A RELIRE", "double espace dans la valeur"))
    low = v.lower()
    if any(tok in low for tok in BAD_TOKENS):
        res.append(("BLOQUANT", "reste technique dans la valeur (variable non resolue, null, undefined, #N/A...)"))
    vw, lw, rw = words(v), words(left), words(right)
    if vw and lw and lw[-1] == vw[0]:
        res.append(("BLOQUANT", f"mot double a la jonction (avant la variable) : '{lw[-1]} {vw[0]}'"))
    if vw and rw and vw[-1] == rw[0]:
        res.append(("BLOQUANT", f"mot double a la jonction (apres la variable) : '{vw[-1]} {rw[0]}'"))
    if vw and lw and lw[-1] in FUNC and vw[0] in FUNC and lw[-1] != vw[0]:
        res.append(("A RELIRE", f"deux mots outils qui se suivent : '{lw[-1]} {vw[0]}'"))
    if vw and rw and vw[-1] in FUNC and rw[0] in FUNC and vw[-1] != rw[0]:
        res.append(("A RELIRE", f"deux mots outils qui se suivent : '{vw[-1]} {rw[0]}'"))
    if lw and vw and lw[-1] in ELIDE and left.rstrip().lower().endswith(lw[-1]) and left.endswith(" ") and re.match(r"[aeiouyhàâéèêëîïôùû]", v.strip().lower()):
        res.append(("A RELIRE", f"elision possible : '{lw[-1]} {v.strip().split()[0]}' -> {lw[-1][:-1] if lw[-1] in ('de','que','le','la','je','ne','se','ce','me','te') else lw[-1]}'..."))
    lt = left.rstrip()
    if (lt == "" or lt[-1] in ".!?\n") and v.strip()[:1].islower():
        res.append(("A RELIRE", "la valeur commence par une minuscule en debut de phrase"))
    if v.rstrip().endswith((".", "!", "?")) and right.lstrip()[:1] in (".", ",", ";", "!", "?"):
        res.append(("BLOQUANT", "ponctuation doublee apres la valeur"))
    if right[:1] not in (" ", "\n", "", ".", ",", ";", ":", "!", "?", ")", " ") and v.rstrip() == v and not v.endswith("'"):
        res.append(("A RELIRE", "la valeur est collee au mot suivant (pas d'espace ni de ponctuation)"))
    if left[-1:] not in (" ", "\n", "", "(", "'", " ", "\"") and not v.startswith(" "):
        res.append(("A RELIRE", "la valeur est collee au mot precedent (pas d'espace)"))
    return res


def load_templates(path):
    raw = open(path, encoding="utf-8").read()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("steps") or [data]
        return [{"step": d.get("step") or d.get("name") or f"step {i+1}", "text": (d.get("subject") or "") + "\n" + (d.get("body") or d.get("message") or d.get("html") or "")} for i, d in enumerate(data)]
    except ValueError:
        return [{"step": "step 1", "text": raw}]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", required=True)
    ap.add_argument("--leads", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    steps = load_templates(a.template)
    leads = list(csv.DictReader(open(a.leads, encoding="utf-8-sig")))
    cols = {k.lower(): k for k in (leads[0].keys() if leads else [])}
    issues = defaultdict(lambda: {"n": 0, "ctx": ""})
    missing = set()
    for st in steps:
        for var, left, right, dflt in contexts(st["text"]):
            if var in BUILTIN_VARS:
                continue
            col = cols.get(var)
            if not col:
                missing.add((st["step"], var)); continue
            counts = defaultdict(int)
            for r in leads: counts[r.get(col, "")] += 1
            for val, n in counts.items():
                for sev, why in check(val, left, right, dflt):
                    key = (st["step"], var, val, sev, why)
                    issues[key]["n"] += n
                    issues[key]["ctx"] = f"...{left.strip()[-45:]} [{val}] {right.strip()[:45]}..."
    rows = [dict(step=k[0], variable=k[1], valeur=k[2], severite=k[3], raison=k[4], leads_touches=v["n"], contexte=v["ctx"]) for k, v in issues.items()]
    rows.sort(key=lambda r: (r["severite"] != "BLOQUANT", -r["leads_touches"]))
    with open(a.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["severite", "step", "variable", "valeur", "leads_touches", "raison", "contexte"])
        w.writeheader(); w.writerows({k: r[k] for k in w.fieldnames} for r in rows)
    print(json.dumps({"leads": len(leads), "steps": len(steps), "bloquants": sum(r["severite"] == "BLOQUANT" for r in rows), "a_relire": sum(r["severite"] == "A RELIRE" for r in rows),
                      "variables_du_texte_absentes_du_csv": sorted(f"{s}:{v}" for s, v in missing), "sortie": a.out}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
