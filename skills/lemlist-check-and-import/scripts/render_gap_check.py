#!/usr/bin/env python3
"""Controle des blancs et sauts de ligne APRES rendu Liquid, sur tous les leads reels d'une campagne.

Pourquoi : un `{% if %}` ouvert dans un paragraphe et fermé dans un autre
produisait, selon la branche, une ligne vide en trop ou un paragraphe vide. Le texte brut ne le montre pas ;
l'utilisateur l'a vu dans l'editeur Lemlist. Ce script rend CHAQUE email et CHAQUE variante A/B pour CHAQUE lead
de la campagne, regroupe les leads par "signature de branche" (valeurs des variables testees dans les conditions)
et signale, par signature :
  - paragraphe vide (<p></p>) ;
  - deux lignes vides de suite (<p><br></p><p><br></p>) ;
  - double espace entre deux mots ;
  - espace avant une virgule ou un point ;
  - espace ou &nbsp; en debut/fin de paragraphe ou de point de liste ;
  - balise Liquid ou {{variable}} encore visible ;
  - ligne vide en debut ou en fin d'email ;
  - ligne vide manquante ou lignes vides multiples entre la formule de politesse et la signature.

Lecture seule : aucun appel d'ecriture.

Usage :
  python render_gap_check.py --campaign-ids FR=cam_xxx,NL=cam_yyy --key-env LEMLIST_KEY_CLIENT
"""
import argparse, collections, html, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import account_control as ac

sys.stdout.reconfigure(encoding="utf-8")


def js(x):
    return json.loads(x) if isinstance(x, str) else x


def _cond(c, v):
    def one(p):
        m = re.match(r'\s*(\w+)\s*(==|!=)\s*(?:"([^"]*)"|(blank))\s*$', p)
        if not m:
            raise ValueError("condition non geree : " + p)
        k, op, s, b = m.groups()
        val = str(v.get(k) or "")
        r = (val == "") if b else (val == s)
        return r if op == "==" else not r
    return all(one(p) for p in re.split(r"\s+and\s+", c.strip()))


def render(t, v):
    out, stack = [], []
    for tk in re.split(r"(\{%.*?%\}|\{\{.*?\}\})", t, flags=re.S):
        if tk.startswith("{%"):
            m = re.match(r"\{%\s*(if|elsif|else|endif)\s*(.*?)\s*%\}", tk, re.S)
            kw, c = m.groups()
            if kw == "if":
                r = _cond(c, v); stack.append([r, r])
            elif kw == "elsif":
                s = stack[-1]; r = (not s[0]) and _cond(c, v); s[1] = r; s[0] = s[0] or r
            elif kw == "else":
                s = stack[-1]; s[1] = not s[0]; s[0] = True
            else:
                stack.pop()
        elif tk.startswith("{{"):
            if all(s[1] for s in stack):
                k = tk.strip("{} ").strip()
                out.append("[signature]" if k == "signature" else str(v.get(k) or ""))
        elif all(s[1] for s in stack):
            out.append(tk)
    return "".join(out)


def anomalies(h):
    found = []
    blocks = re.findall(r"<(p|li)\b[^>]*>(.*?)</\1>", h, flags=re.S)
    prev_empty = False
    for i, (tag, inner) in enumerate(blocks):
        has_text = bool(re.sub(r"<[^>]+>|&nbsp;|\s", "", inner))
        has_img = "<img" in inner
        is_br = (not has_text) and (not has_img) and "<br" in inner
        if not has_text and not is_br and not has_img:
            found.append("paragraphe vide")
        if is_br and prev_empty:
            found.append("deux lignes vides de suite")
        prev_empty = is_br
        raw = re.sub(r"^(<[^>]+>)+|(<[^>]+>)+$", "", inner)
        if has_text and (re.match(r"^(\s|&nbsp;)+", raw) or re.search(r"(\s|&nbsp;)+$", raw)):
            found.append("espace en debut/fin de " + ("point de liste" if tag == "li" else "paragraphe"))
        visible = html.unescape(re.sub(r"<[^>]+>", "", inner)).replace("\u00a0", " ")
        if re.search(r"\S[ \t]{2,}\S", visible):
            found.append("double espace entre deux mots")
        if re.search(r"[ \t]+[,.]", visible):
            found.append("espace avant virgule ou point")
    if blocks and not re.sub(r"<[^>]+>|&nbsp;|\s", "", blocks[0][1]):
        found.append("ligne vide en debut d'email")
    if blocks and not re.sub(r"<[^>]+>|&nbsp;|\s", "", blocks[-1][1]):
        found.append("ligne vide en fin d'email")
    for i, (_, inner) in enumerate(blocks):
        if "[signature]" not in inner:
            continue
        previous = blocks[i - 1][1] if i > 0 else ""
        previous_has_text = bool(re.sub(r"<[^>]+>|&nbsp;|\s", "", previous))
        previous_is_blank_line = (not previous_has_text) and "<br" in previous
        if not previous_is_blank_line:
            found.append("ligne vide manquante avant signature")
        elif i > 1:
            before_previous = blocks[i - 2][1]
            before_previous_has_text = bool(re.sub(r"<[^>]+>|&nbsp;|\s", "", before_previous))
            before_previous_is_blank_line = (not before_previous_has_text) and "<br" in before_previous
            if before_previous_is_blank_line:
                found.append("plus d'une ligne vide avant signature")
    if re.search(r"\{%|%\}|\{\{|\}\}", h):
        found.append("balise Liquid visible")
    return sorted(set(found))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign-ids", required=True)
    ap.add_argument("--key-env", required=True)
    ap.add_argument("--env-file", help="fichier .env local non committé ; inutile si --key-env existe déjà dans l'environnement")
    a = ap.parse_args()
    api = ac.Lemlist(ac.key_from_env(a.key_env, a.env_file))
    total = 0
    for lab, cid in (x.split("=") for x in a.campaign_ids.split(",")):
        seq = js(api.call("GET", f"/campaigns/{cid}/sequences")[1])
        steps = []
        for sq in (seq.values() if isinstance(seq, dict) else seq):
            if not isinstance(sq, dict):
                continue
            sid = sq.get("_id") or sq.get("id")
            for i, s in enumerate(sq.get("steps", []), 1):
                stp = s.get("_id") or s.get("id")
                steps.append((i, "A", s.get("message") or "", s.get("subject") or ""))
                if s.get("abTest") or s.get("emailTemplateBId"):
                    st, r = api.call("GET", f"/sequences/{sid}/steps/{stp}/ab-test")
                    r = js(r) if st == 200 else {}
                    if isinstance(r, dict) and r.get("message"):
                        steps.append((i, "B", r["message"], r.get("subject") or ""))
        leads = api.leads(cid)
        res = collections.defaultdict(lambda: collections.defaultdict(list))
        for (i, ab, msg, sub) in steps:
            vars_used = sorted(set(re.findall(r"\{%\s*(?:if|elsif)\s+([^%]*?)\s*%\}", msg + sub)))
            keys = sorted({m for c in vars_used for m in re.findall(r"(\w+)\s*(?:==|!=)", c)})
            for l in leads:
                v = {k: ("" if x is None else str(x)) for k, x in l.items()}
                sig = ", ".join(f"{k}={'vide' if not v.get(k) else (v[k] if k in ('emailType', 'employee_count_category') else 'rempli')}" for k in keys)
                for what, body in (("corps", msg), ("objet", f"<p>{sub}</p>")):
                    try:
                        problems = anomalies(render(body, v)) if what == "corps" else \
                            (["balise Liquid visible"] if re.search(r"\{%|\{\{", render(sub, v)) else [])
                    except ValueError as e:
                        problems = [str(e)]
                    for p in problems:
                        res[(i, ab, what, p)][sig].append(l.get("email"))
        print(f"== {lab} ({cid}) : {len(leads)} leads, {len(steps)} emails/variantes rendus")
        if not res:
            print("   OK : espacement propre, ligne vide avant signature et aucune balise visible")
        for (i, ab, what, p), sigs in sorted(res.items()):
            n = sum(len(x) for x in sigs.values()); total += n
            ex = next(iter(sigs.items()))
            print(f"   ANOMALIE email {i}{ab} ({what}) : {p} | {n} leads | branche : {ex[0] or '-'} | ex. {ex[1][0]}")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
