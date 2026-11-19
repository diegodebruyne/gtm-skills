"""Import de leads dans Lemlist depuis le terminal (partie D du skill lemlist-check-and-import), avec contrôle D0 intégré.

Fait seul : (1) valide que TOUTES les clés sont des propriétés natives Lemlist (liste officielle dans
references/lemlist_native_fields.md) ou une des 6 variables hors natif autorisées ; (2) contrôle D0 : doublons sur toutes les campagnes
du compte (email, URL LinkedIn, nom + entreprise), plafond par entreprise (3, 5 en exception), email qui appartient à
l'entreprise ; (3) importe les leads restants dans la bonne campagne (deduplicate=true) ; (4) relit Lemlist et compare
CHAMP PAR CHAMP ce qui a été envoyé ; (5) en mode --update-existing, complète les champs natifs VIDES des leads déjà présents
(rattrapage), sans jamais écraser une valeur existante.
Ne lance jamais une campagne, ne supprime rien, ne relance rien.

Entrée : JSON, liste d'objets. Clés obligatoires : "campaign" ("FR" ou "EN", clés de --campaign-ids), "email" ou "linkedinUrl", "firstName",
"companyName". Toutes les autres clés : natives ou variables autorisées uniquement.

    python import_leads.py --input ready.json --campaign-ids FR=cam_xxx,EN=cam_yyy --key-env LEMLIST_KEY_CLIENT --out <dossier-run>/import                 # dry-run
    python import_leads.py --input ready.json --campaign-ids ... --key-env ... --out <dossier-run>/import --apply                                      # import
    python import_leads.py --input backfill.json --campaign-ids ... --key-env ... --out <dossier-run>/import --apply --update-existing                 # rattrapage
"""
import argparse, collections, json, re, sys, time, urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import account_control as ac

SKILL_ROOT = Path(__file__).resolve().parent.parent


def external_output_path(raw):
    """Refuse de mélanger les résultats d'un run avec le code du skill."""
    out = Path(raw).expanduser().resolve()
    try:
        out.relative_to(SKILL_ROOT)
    except ValueError:
        return out
    raise SystemExit(
        f"STOP : le dossier de sortie doit être hors du skill ({SKILL_ROOT}). "
        "Utilise un dossier privé dédié au run."
    )

sys.stdout.reconfigure(encoding="utf-8")

NATIVE_CONTACT = {"email", "firstName", "lastName", "jobTitle", "phone", "linkedinUrl", "linkedinUrlSalesNav", "picture", "jobDescription",
                  "timezone", "industry", "languages", "location", "skills", "summary", "tagline"}
NATIVE_COMPANY = {"companyName", "companyDomain", "companyLinkedinUrl", "companyLinkedinUrlSalesNav", "companyPicture", "companyIndustry",
                  "companySubIndustry", "companyLocation", "companyHeadquarters", "companySize", "companyEmployeeCount", "companyEmployeeGrowth",
                  "companyRevenue", "companyType", "companyDescription", "companyTagline", "companySpecialties", "companyFoundedOn", "companyTechnologies"}
NON_NATIVE_VARS = {"personaTier", "emailType", "gender", "salutation", "colleaguename1", "colleaguename2", "source", "importBatch"}
CONTROL_KEYS = {"campaign"}
FORBIDDEN = {"CompanyLinkedinUrl": "companyLinkedinUrl", "leadLocation": "location"}
PERSONAL_DOMAINS = {"gmail.com", "googlemail.com", "yahoo.com", "yahoo.fr", "yahoo.be", "hotmail.com", "hotmail.fr", "hotmail.be", "outlook.com", "outlook.be", "outlook.fr", "live.com", "live.be", "live.fr", "icloud.com", "me.com", "msn.com", "skynet.be", "telenet.be", "proximus.be", "scarlet.be", "voo.be", "gmx.com", "gmx.net", "protonmail.com", "proton.me", "aol.com"}
ALLOWED = NATIVE_CONTACT | NATIVE_COMPANY | NON_NATIVE_VARS | CONTROL_KEYS


def _norm_value(k, v):
    """Lemlist normalise certaines valeurs a l'import (14/10/2026 : be./nl.linkedin.com -> www., %C3%A9 -> e accent, all.accor.com -> accor.com).
    La relecture compare donc les valeurs normalisees, sinon 61 faux ecarts sur 141 fiches."""
    v = urllib.parse.unquote(str(v or "").strip())
    if k in ("linkedinUrl", "companyLinkedinUrl", "linkedinUrlSalesNav", "companyLinkedinUrlSalesNav"):
        v = re.sub(r"^https?://[a-z]{2,3}\.linkedin\.com", "https://www.linkedin.com", v).rstrip("/").lower()
    if k == "companyDomain":
        v = re.sub(r"^(www|all)\.", "", v.lower())
    return v


def _same(k, got, sent):
    """True quand la valeur relue DIFFERE de la valeur envoyee (apres normalisation Lemlist)."""
    return _norm_value(k, got) != _norm_value(k, sent)


def validate_keys(rows):
    bad = collections.Counter()
    for r in rows:
        for k in r:
            if k not in ALLOWED:
                bad[k] += 1
    if bad:
        msg = []
        for k, n in bad.items():
            msg.append(f"  - '{k}' ({n} lignes)" + (f" : utiliser '{FORBIDDEN[k]}'" if k in FORBIDDEN else " : pas une propriété native Lemlist ni une variable autorisée (voir references/lemlist_native_fields.md)"))
        raise SystemExit("CLÉS REFUSÉES (on ne crée pas de propriété hors natif) :\n" + "\n".join(msg))


def norm_li_company(u):
    return re.sub(r"^https?://[a-z]{2}\.linkedin\.com", "https://www.linkedin.com", u or "")


def person_key(r):
    nm = ac.norm((r.get("firstName") or "") + (r.get("lastName") or "")).replace(" ", "")
    co = ac.li_slug(r.get("companyLinkedinUrl"), "company") or ac.norm(r.get("companyDomain") or "")
    return (nm + "|" + co) if nm and co and len(nm) > 5 else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--campaign-ids", required=True, help="FR=cam_xxx,EN=cam_yyy")
    ap.add_argument("--key-env", required=True)
    ap.add_argument("--env-file", help="fichier .env local non committé ; inutile si --key-env existe déjà dans l'environnement")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--approval", help="OBLIGATOIRE avec --apply : texte de l'autorisation explicite d'importer ce lot exact")
    ap.add_argument("--update-existing", action="store_true", help="rattrapage : complète les champs natifs vides des leads déjà dans Lemlist")
    ap.add_argument("--only-ids", help="import_done.json d'un lot : en rattrapage, ne touche QUE les fiches de ce lot (14/10/2026 : 5 fiches deja lancees avaient recu par erreur la balise du lot du jour)")
    ap.add_argument("--exception", action="append", default=[])
    ap.add_argument("--require-company-description", action="store_true", help="retire les leads dont companyDescription est vide")
    ap.add_argument("--blocked-company-type", action="append", default=[], help="companyType à retirer ; option répétable")
    ap.add_argument("--extra-vars", default="", help="variables custom propres à cette campagne, séparées par des virgules")
    ap.add_argument("--allow-same-person-other-address", action="store_true", help="la meme personne deja dans le compte (meme LinkedIn ou meme nom+entreprise) est importee si l'ADRESSE est differente : UNIQUEMENT apres accord du user (ex. la salutation 'ou la personne qui ouvre ce mail' couvre le cas). Meme adresse = toujours retiree.")
    ap.add_argument("--keep-personal-emails", action="store_true", help="garde les adresses perso (gmail, yahoo, hotmail...) : UNIQUEMENT apres accord explicite du user, et seulement pour une base CRM de gens qui ont opt in. En outbound cold, une adresse perso n'est ni appropriee ni legale.")
    ap.add_argument("--max-per-company", type=int, default=3)
    ap.add_argument("--hard-max-per-company", type=int, default=5)
    ap.add_argument("--out", required=True, help="dossier privé du run, obligatoirement hors du dossier du skill")
    a = ap.parse_args()
    out = external_output_path(a.out)
    if a.apply and not (a.approval or "").strip():
        sys.exit("STOP: --approval \"<explicit approval for this exact batch>\" is required with --apply.")

    ALLOWED.update(x.strip() for x in a.extra_vars.split(",") if x.strip())
    cids = dict(x.split("=") for x in a.campaign_ids.split(","))
    rows = json.load(open(a.input, encoding="utf-8"))
    validate_keys(rows)
    for r in rows:
        if r.get("campaign") not in cids: raise SystemExit(f"campagne inconnue : {r.get('campaign')}")
        if not (r.get("email") or r.get("linkedinUrl")): raise SystemExit("chaque ligne doit avoir un email ou un linkedinUrl")
        if r.get("companyLinkedinUrl"): r["companyLinkedinUrl"] = norm_li_company(r["companyLinkedinUrl"])

    api = ac.Lemlist(ac.key_from_env(a.key_env, a.env_file))
    existing = []
    for c in api.campaigns():
        for x in api.leads(c["_id"]):
            x["_campaign_id"], x["_campaign"] = c["_id"], c.get("name", "")
            existing.append(x)
    by_email = {(x.get("email") or "").lower(): x for x in existing if x.get("email")}
    by_li = {ac.li_slug(x.get("linkedinUrl"), "in"): x for x in existing if ac.li_slug(x.get("linkedinUrl"), "in")}
    by_person = {person_key(x): x for x in existing if person_key(x)}
    print(f"compte : {len(existing)} fiches déjà dans Lemlist")

    out.mkdir(parents=True, exist_ok=True)

    # ---------------- rattrapage : champs natifs vides des leads existants ----------------
    if a.update_existing:
        plan, nomatch = [], []
        only_ids = {d["id"] for d in json.load(open(a.only_ids, encoding="utf-8")).values() if d.get("id")} if a.only_ids else None
        for r in rows:
            x = (by_email.get((r.get("email") or "").lower()) or by_li.get(ac.li_slug(r.get("linkedinUrl"), "in")) or by_person.get(person_key(r)))
            if not x: nomatch.append(r.get("email") or r.get("linkedinUrl")); continue
            if only_ids is not None and x["_id"] not in only_ids: continue
            upd = {k: v for k, v in r.items() if k not in CONTROL_KEYS and v not in ("", None) and not str(x.get(k) or "").strip()}
            if upd: plan.append((x, upd))
        print(f"rattrapage : {len(plan)} fiches à compléter, {len(nomatch)} lignes sans fiche correspondante")
        cnt = collections.Counter(k for _, u in plan for k in u)
        print("champs complétés :", dict(cnt))
        if a.apply:
            ok = 0
            for x, upd in plan:
                st, _ = api.call("PATCH", f"/campaigns/{x['_campaign_id']}/leads/{x['_id']}", upd)
                ok += (st == 200); time.sleep(0.35)
            print(f"mises à jour réussies : {ok}/{len(plan)}")
        (out / "rattrapage.json").write_text(json.dumps({"complete": [(x["_id"], list(u)) for x, u in plan], "sans_fiche": nomatch}, ensure_ascii=False, indent=1), encoding="utf-8")
        return

    # ---------------- D0 : contrôle avant import ----------------
    try:
        sys.path.insert(0, str(ac.EMAIL_WATERFALL_DIR)); import email_waterfall as ew
    except Exception:
        ew = None
    cnt = collections.Counter()
    for x in existing:
        # Plafond par campagne : on ne compte que les fiches
        # des campagnes visées par cet import (ex. FR + EN d'une même ligne Campaigns planning). Le dédoublonnage des PERSONNES,
        # lui, reste sur tout le compte.
        if x.get("_campaign_id") not in cids.values(): continue
        k = ac.li_slug(x.get("companyLinkedinUrl") or x.get("CompanyLinkedinUrl"), "company") or (x.get("companyDomain") or "").lower()
        if k: cnt[k] += 1
    keep, drop, seen = [], collections.defaultdict(list), set()
    exc = {e.lower() for e in a.exception}
    for r in rows:
        nm = f"{r.get('firstName','')} {r.get('lastName','')}".strip()
        e, l, pk = (r.get("email") or "").lower(), ac.li_slug(r.get("linkedinUrl"), "in"), person_key(r)
        if a.allow_same_person_other_address:
            if e and e in by_email: drop["déjà dans Lemlist (même adresse)"].append(nm); continue
        elif (e and e in by_email) or (l and l in by_li) or (pk and pk in by_person): drop["déjà dans Lemlist"].append(nm); continue
        if (e and e in seen) or (l and l in seen): drop["doublon dans la liste"].append(nm); continue
        if a.require_company_description and not (r.get("companyDescription") or "").strip():
            drop["companyDescription vide"].append(nm or r.get("companyName")); continue
        if (r.get("companyType") or "") in set(a.blocked_company_type):
            drop["companyType bloqué : " + r["companyType"]].append(nm or r.get("companyName")); continue
        ck = ac.li_slug(r.get("companyLinkedinUrl"), "company") or (r.get("companyDomain") or "").lower()
        if e and ew and r.get("companyDomain"):
            ok, _ = ew.belongs_to_company(e, r["companyDomain"])
            if ok is False and a.keep_personal_emails and e.rsplit("@", 1)[1] in PERSONAL_DOMAINS: ok = True
            if ok is False:
                ed = e.rsplit("@", 1)[1]
                if not (ac.group_ok(ed, (r.get("companyName") or "") + " " + r["companyDomain"]) or ac.same_brand(ed, r["companyDomain"].lower()) or ac.web_evidence(ed, r["companyDomain"].lower())[0]):
                    drop["email hors entreprise"].append(f"{nm} <{e}>"); continue
        cap = a.hard_max_per_company if ck in exc else a.max_per_company
        if ck and cnt[ck] >= cap and ck not in exc: drop["plafond entreprise"].append(f"{nm} ({ck}: {cnt[ck]})"); continue
        if ck: cnt[ck] += 1
        seen |= {x for x in (e, l) if x}; keep.append(r)
    print(f"D0 : {len(rows)} en entrée, {len(keep)} importables")
    for k, v in drop.items(): print(f"  retirés - {k} : {len(v)} {v[:10]}")
    (out / "d0.json").write_text(json.dumps({"importables": len(keep), "retires": drop}, ensure_ascii=False, indent=1), encoding="utf-8")
    fills = collections.Counter(k for r in keep for k, v in r.items() if v not in ("", None))
    print("champs remplis sur les importables :", {k: f"{n}/{len(keep)}" for k, n in sorted(fills.items())})
    empties = [k for k in sorted(NATIVE_CONTACT | NATIVE_COMPANY) if fills.get(k, 0) == 0]
    print("champs natifs JAMAIS remplis dans ce lot (à vérifier : donnée indisponible ou oubli ?) :", empties)
    if not a.apply: print("dry-run : rien importé (ajouter --apply)"); return

    # ---------------- import ----------------
    done, res = {}, collections.Counter()
    for r in keep:
        body = {k: v for k, v in r.items() if k not in CONTROL_KEYS and v not in ("", None)}
        cid = cids[r["campaign"]]
        path = f"/campaigns/{cid}/leads/{urllib.parse.quote(r['email'].lower())}?deduplicate=true" if r.get("email") else f"/campaigns/{cid}/leads/?deduplicate=true"
        st, txt = api.call("POST", path, body)
        try: lid = json.loads(txt).get("_id")
        except Exception: lid = None
        key = (r.get("email") or r.get("linkedinUrl")).lower()
        done[key] = {"campaign": r["campaign"], "http": st, "id": lid, "detail": "" if st in (200, 201) else txt[:150]}
        res[(r["campaign"], st)] += 1; time.sleep(0.4)
    (out / "import_done.json").write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    print("import :", dict(res))

    # ---------------- relecture champ par champ ----------------
    time.sleep(8)
    after = {}
    for c in api.campaigns():
        if c["_id"] in cids.values():
            for x in api.leads(c["_id"]): after[x["_id"]] = x
    mism, ok = [], 0
    for r in keep:
        d = done[(r.get("email") or r.get("linkedinUrl")).lower()]
        x = after.get(d["id"])
        if not x: mism.append((r.get("email"), "fiche introuvable")); continue
        bad = [k for k, v in r.items() if k not in CONTROL_KEYS and v not in ("", None) and _same(k, x.get(k), v)]
        if bad: mism.append((r.get("email") or r.get("linkedinUrl"), bad))
        else: ok += 1
    print(f"vérification : {ok}/{len(keep)} fiches identiques à ce qui a été envoyé ; écarts : {len(mism)}")
    for m in mism[:15]: print("  écart", m)


if __name__ == "__main__":
    main()
