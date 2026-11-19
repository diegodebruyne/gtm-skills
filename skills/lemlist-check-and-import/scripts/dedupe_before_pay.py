#!/usr/bin/env python3
"""Porte anti-doublon AVANT toute étape payante (Icypeas, Apify, cascade d'emails).

Pourquoi : les doublons doivent être détectés avant l'enrichissement payant, pas seulement au contrôle final.
l'enrichissement. Ce script compare chaque contact aux leads DÉJÀ présents dans TOUTES les campagnes du
client (actives, en pause, en review) et sort ceux qui sont connus, avec le motif. Il est gratuit :
uniquement des GET Lemlist, aucun crédit, aucune écriture.

Règles de rapprochement, de la plus sûre à la moins sûre :
  1. même slug de profil LinkedIn (www., be., nl. ignorés)
  2. même email
  3. même nom complet ET même entreprise (slug LinkedIn société, domaine ou nom normalisé)
Un nom complet identique avec une autre entreprise n'est PAS un doublon : le contact reste, signalé « homonyme ».
EXCEPTION, "probable duplicate": same full name AND same job title (AND same city when both are known) in another company of the account
is very probably the SAME person (a profile exported without public link or exact company). The exact rules cannot link them, so these are never
kept silently: they are listed in <prefix>_probables.json for the user to decide.

Entrée  : JSON, liste d'objets avec firstName, lastName, linkedinUrl, email, companyName,
          companyDomain, companyLinkedinUrl (les variantes en snake_case sont acceptées).
Sorties : <prefix>_new.json (à enrichir), <prefix>_known.json (déjà dans Lemlist, avec motif et campagne),
          résumé affiché.

Usage : python dedupe_before_pay.py --input contacts.json --key-env LEMLIST_API_KEY --env-file <fichier-local> --out-prefix run
"""
import argparse, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import account_control as ac


def g(r, *names):
    low = {k.lower(): v for k, v in r.items()}
    for n in names:
        v = low.get(n.lower())
        if v:
            return str(v).strip()
    return ""


def fullname(r):
    return ac.norm(g(r, "firstName", "first_name", "prenom") + g(r, "lastName", "last_name", "nom")).replace(" ", "").replace("-", "")


def co_keys(r):
    keys = set()
    s = ac.li_slug(g(r, "companyLinkedinUrl", "CompanyLinkedinUrl", "company_linkedin_url", "linkedin_company"), "company")
    if s:
        keys.add("li:" + s)
    d = ac.norm(g(r, "companyDomain", "company_domain", "domaine")).replace("www.", "")
    if d:
        keys.add("dom:" + d)
    n = re.sub(r"[^a-z0-9]", "", ac.norm(g(r, "companyName", "company_name", "entreprise")))
    if len(n) > 3:
        keys.add("nm:" + n)
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--key-env", required=True)
    ap.add_argument("--env-file", help="fichier .env local non committé ; inutile si --key-env existe déjà dans l'environnement")
    ap.add_argument("--out-prefix", required=True)
    a = ap.parse_args()

    rows = json.loads(Path(a.input).read_text(encoding="utf-8"))
    api = ac.Lemlist(ac.key_from_env(a.key_env, a.env_file))

    by_slug, by_email, by_name = {}, {}, {}
    n_leads = 0
    for c in api.campaigns():
        cname = c.get("name", c.get("_id"))
        for l in api.leads(c.get("_id")):
            n_leads += 1
            ref = {"campaign": cname, "email": g(l, "email"), "name": (g(l, "firstName") + " " + g(l, "lastName")).strip(),
                   "title": ac.norm(g(l, "jobTitle", "job_title", "poste")), "city": ac.norm((g(l, "location", "companyLocation") or "").split(",")[0]).strip()}
            s = ac.li_slug(g(l, "linkedinUrl"), "in")
            if s:
                by_slug.setdefault(s, ref)
            if ref["email"]:
                by_email.setdefault(ref["email"].lower(), ref)
            fn = fullname(l)
            if len(fn) > 5:
                by_name.setdefault(fn, []).append((co_keys(l), ref))

    new, known, homonyms, probables = [], [], 0, []
    for r in rows:
        s = ac.li_slug(g(r, "linkedinUrl", "linkedin", "linkedin_url"), "in")
        em = g(r, "email").lower()
        fn = fullname(r)
        hit, why = None, ""
        if s and s in by_slug:
            hit, why = by_slug[s], "même profil LinkedIn"
        elif em and em in by_email:
            hit, why = by_email[em], "même email"
        elif len(fn) > 5 and fn in by_name:
            mine = co_keys(r)
            for theirs, ref in by_name[fn]:
                if mine & theirs:
                    hit, why = ref, "même nom complet et même entreprise"
                    break
            else:
                my_title = ac.norm(g(r, "jobTitle", "job_title", "poste"))
                my_city = ac.norm((g(r, "location", "companyLocation", "ville") or "").split(",")[0]).strip()
                prob = None
                for theirs, ref in by_name[fn]:
                    if my_title and my_title == ref.get("title") and (not my_city or not ref.get("city") or my_city == ref["city"]):
                        prob = ref
                        break
                if prob:
                    probables.append(dict(r, motif="same full name, same job title and same city", deja_dans=prob["campaign"], lead_existant=prob["name"]))
                r = dict(r, _note="homonyme dans Lemlist (autre entreprise), conservé" if not prob else "PROBABLE duplicate (same name, title, city): user decision")
                homonyms += 1
        if hit:
            known.append(dict(r, motif=why, deja_dans=hit["campaign"], lead_existant=hit["name"]))
        else:
            new.append(r)

    Path(a.out_prefix + "_new.json").write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(a.out_prefix + "_known.json").write_text(json.dumps(known, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(a.out_prefix + "_probables.json").write_text(json.dumps(probables, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Leads Lemlist lus (toutes campagnes) : {n_leads}")
    print(f"Contacts en entrée : {len(rows)} | à enrichir : {len(new)} | déjà connus (retirés avant paiement) : {len(known)} | homonymes conservés : {homonyms}")
    if probables:
        print(f"PROBABLE duplicates (same name, title and city, other company): {len(probables)}: the user decides, never kept silently")
        for k in probables[:15]:
            print(f"  ? {g(k,'firstName')} {g(k,'lastName')} ({g(k,'companyName')}): {k['motif']} ({k['deja_dans']})")
    for k in known[:15]:
        print(f"  - {g(k,'firstName')} {g(k,'lastName')} ({g(k,'companyName')}) : {k['motif']} ({k['deja_dans']})")


if __name__ == "__main__":
    main()
