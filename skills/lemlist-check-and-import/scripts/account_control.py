"""Contrôle d'un compte Lemlist (étape D0 du skill lemlist-check-and-import), sans intervention humaine.

Fait seul, dans cet ordre :
  1. exporte TOUTES les campagnes du compte (toutes les fiches, y compris pausées et terminées) ;
  2. DOUBLONS : regroupe les fiches de la même personne (email OU URL LinkedIn OU nom + entreprise), choisit la fiche à
     garder selon les règles du skill, METS EN PAUSE les autres si elles envoient encore (réversible), liste les fiches à
     supprimer (la suppression d'un lead est irréversible : jamais faite par ce script) ;
  3. EMAIL <-> ENTREPRISE : classe chaque email (appartient / groupe ou marque connue / suspect) ; les suspects qui n'ont
     pas encore été contactés sont mis en pause ; les autres sont seulement rapportés ;
  4. PLAFOND PAR ENTREPRISE : compte les contacts par entreprise, toutes campagnes confondues (3, 5 en exception).

Par défaut : lecture seule (dry-run). `--apply` active les mises en pause. Jamais de suppression, jamais de relance.

    python account_control.py --key-env LEMLIST_KEY_CLIENT --out <dossier-run>/rapport_controle
    python account_control.py --key-env LEMLIST_KEY_CLIENT --out <dossier-run>/rapport_controle --apply
"""
import argparse, base64, collections, csv, io, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

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

INTENT_STATES = {"emailsReplied", "linkedinReplied", "emailsInterested", "linkedinInterested", "meetingBooked"}
INTENT_STATUS = {"interested"}
SENDING = {"inProgress", "review"}          # fiches qui peuvent encore envoyer ou vont envoyer
STOPPED = {"paused", "done", "unsubscribed", "bounced", "failed", "skipped"}

# Familles de groupes : domaine email du groupe + marques (mots présents dans le nom / domaine de l'entreprise).
# Un email du domaine du groupe sur une entreprise de la famille peut être accepté.
# Compléter au fil des cas, jamais par intuition : une famille doit être vérifiable.
FAMILIES = [
    ({"accor.com", "accorhotels.com", "all.accor.com"}, ["accor", "ibis", "mercure", "novotel", "sofitel", "pullman", "mgallery", "swissotel", "fairmont", "raffles", "mama shelter", "25hours"]),
    ({"marriott.com"}, ["marriott", "sheraton", "westin", "ritz", "courtyard", "renaissance", "aloft", "moxy", "w hotel", "le meridien", "autograph"]),
    ({"ihg.com", "ihgplc.com"}, ["ihg", "holiday inn", "voco", "crowne plaza", "intercontinental", "kimpton", "indigo", "even hotels", "hotel indigo"]),
    ({"radissonhotels.com", "radissonblu.com", "radisson.com"}, ["radisson", "park inn", "park plaza"]),
    ({"valk.com", "vandervalk.nl"}, ["valk"]),
    ({"nh-hotels.com", "minorhotels.com", "nh-collection.com", "anantara.com"}, ["nh ", "nh-", "nh collection", "minor", "anantara", "tivoli"]),
    ({"mohg.com", "mandarinoriental.com"}, ["mandarin oriental"]),
    ({"discoverasr.com", "the-ascott.com", "ascott.com"}, ["ascott", "citadines", "somerset"]),
    ({"hilton.com"}, ["hilton", "doubletree", "hampton", "waldorf", "conrad", "curio", "canopy"]),
    ({"wyndham.com", "wyndhamhotels.com"}, ["wyndham", "dolce", "tryp", "ramada", "days inn"]),
    ({"bestwestern.com", "bestwestern.be"}, ["best western"]),
]


def norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def key_from_env(name, env_file=None):
    v = os.environ.get(name)
    if v:
        return v
    configured_file = env_file or os.environ.get("LEMLIST_ENV_FILE")
    if not configured_file:
        raise SystemExit(
            f"{name} introuvable dans l'environnement. "
            "Définis la variable ou fournis --env-file <chemin>."
        )
    env_path = Path(configured_file).expanduser().resolve()
    if not env_path.is_file():
        raise SystemExit(f"Fichier .env introuvable : {env_path}")
    txt = env_path.read_text(encoding="utf-8")
    m = re.search(r"^" + re.escape(name) + r"\s*=\s*(\S+)", txt, re.M)
    if not m:
        raise SystemExit(f"{name} introuvable dans l'environnement ou {env_path}")
    return m.group(1).strip("\"'")


class Lemlist:
    def __init__(self, key):
        self.auth = "Basic " + base64.b64encode((":" + key).encode()).decode()

    def call(self, method, path, body=None, tries=3):
        url = "https://api.lemlist.com/api" + path
        for i in range(tries):
            rq = urllib.request.Request(url, data=(json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)),
                                        headers={"Authorization": self.auth, "Content-Type": "application/json"}, method=method)
            try:
                with urllib.request.urlopen(rq, timeout=60) as r:
                    return r.status, r.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(5 * (i + 1)); continue
                return e.code, e.read().decode("utf-8", "replace")
            except Exception as e:
                time.sleep(2)
        return 0, "network error"

    def campaigns(self):
        st, txt = self.call("GET", "/campaigns?limit=100")
        d = json.loads(txt)
        return d if isinstance(d, list) else d.get("campaigns", [])

    def leads(self, cid):
        st, txt = self.call("GET", f"/campaigns/{cid}/export/leads?state=all")
        return list(csv.DictReader(io.StringIO(txt))) if st == 200 else []

    def pause(self, email, cid):
        return self.call("POST", f"/leads/pause/{urllib.parse.quote(email)}?campaignId={cid}")


def campaign_lang(name):
    m = re.search(r"[-–]\s*(FR|NL|EN)\s*$", name or "", re.I)
    return m.group(1).upper() if m else None


def lead_lang(r, camp_lang):
    """Langue du CONTACT (pas de l'entreprise) : champ `languages` de la fiche, sinon None."""
    v = (r.get("languages") or "").strip().upper()
    return {"FR": "FR", "NL": "NL", "EN": "EN"}.get(v)


def target_campaign_for(lang):
    return {"FR": "FR", "NL": "EN", "EN": "EN"}.get(lang)


def li_slug(u, kind):
    m = re.search(r"linkedin\.com/" + kind + r"/([^/?#]+)", (u or "").lower())
    return m.group(1) if m else ""


def has_intent(r):
    return r.get("status") in INTENT_STATUS or r.get("lastState") in INTENT_STATES or bool((r.get("lastRepliedDate") or "").strip())


def find_groups(rows):
    parent = {}
    def f(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        a, b = f(a), f(b)
        if a != b: parent[a] = b
    for i, r in enumerate(rows):
        keys = []
        e = (r.get("email") or "").lower().strip()
        if e: keys.append(("e", e))
        l = li_slug(r.get("linkedinUrl"), "in")
        if l: keys.append(("l", l))
        nm = norm((r.get("firstName") or "") + (r.get("lastName") or "")).replace(" ", "")
        co = li_slug(r.get("companyLinkedinUrl") or r.get("CompanyLinkedinUrl"), "company") or norm(r.get("companyDomain"))
        if nm and co and len(nm) > 5: keys.append(("n", nm + "|" + co))
        for k in keys: union(("i", i), k)
    g = collections.defaultdict(list)
    for i, r in enumerate(rows): g[f(("i", i))].append(r)
    return [v for v in g.values() if len(v) > 1]


def decide_duplicates(group):
    """Retourne dict(keep, lose=[...], note). Règles du skill : 1 intent, 2 meilleure langue du contact, 3 fiche active,
    4 fiche la plus avancée. Deux fiches avec intent : on ne touche à rien (prévenir le reply manager)."""
    intents = [r for r in group if has_intent(r)]
    if len(intents) >= 2:
        return {"keep": None, "lose": [], "note": "REPLIED_BOTH: plusieurs fiches avec intent, ne rien supprimer, prévenir le reply manager"}
    if len(intents) == 1:
        keep = intents[0]; why = "intent"
    else:
        cands = group
        langs = {lead_lang(r, None) for r in group} - {None}
        why = ""
        if len(langs) == 1:
            want = target_campaign_for(langs.pop())
            ok = [r for r in group if r["_campaign_lang"] == want]
            if len(ok) == 1:
                keep = ok[0]; why = f"langue du contact -> campagne {want}"
            else:
                ok = None
        else:
            ok = None
        if not why:
            act = [r for r in group if r.get("status") in SENDING]
            if len(act) == 1:
                keep = act[0]; why = "seule fiche active"
            else:
                keep = max(group, key=lambda r: int(r.get("lastExecutedStepNumber") or 0)); why = "fiche la plus avancée"
    return {"keep": keep, "lose": [r for r in group if r is not keep], "note": why}


def group_ok(email_dom, comp_text):
    ct = norm(comp_text)
    for doms, brands in FAMILIES:
        if email_dom in doms or any(email_dom.endswith("." + d) for d in doms):
            if any(b in ct for b in brands):
                return True
    return False


def same_brand(email_dom, comp_dom):
    a = re.sub(r"[^a-z0-9]", "", norm(email_dom.split(".")[0] if "." in email_dom else email_dom))
    b = re.sub(r"[^a-z0-9]", "", norm(comp_dom.split(".")[0] if "." in comp_dom else comp_dom))
    return bool(a and b and len(min(a, b, key=len)) >= 5 and (a in b or b in a))


UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def fetch_page(domain):
    """(hote final, titre, texte minuscule) de la page d'accueil, sans credit (HTTP direct). ('', '', '') si injoignable."""
    for scheme in ("https://", "http://"):
        try:
            rq = urllib.request.Request(scheme + domain, headers=UA)
            with urllib.request.urlopen(rq, timeout=12) as r:
                html = r.read(300000).decode("utf-8", "replace")
                host = urllib.parse.urlparse(r.geturl()).netloc.lower().replace("www.", "")
                m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
                return host, (m.group(1).strip().lower() if m else ""), html.lower()
        except Exception:
            continue
    return "", "", ""


def root_label(d):
    d = d.lower().replace("www.", "")
    parts = d.split(".")
    return re.sub(r"[^a-z0-9]", "", parts[-3] if len(parts) >= 3 and parts[-2] in ("co", "com") else parts[0])


def web_evidence(email_dom, comp_dom):
    """Preuve que les deux domaines sont la meme entite, SANS credit. Retourne (True/False, raison)."""
    eh, et, etxt = fetch_page(email_dom)
    ch, ct, ctxt = fetch_page(comp_dom)
    if not eh and not ch:
        return False, "aucun des deux sites joignable"
    er, cr = root_label(email_dom), root_label(comp_dom)
    if eh and (eh.endswith(comp_dom) or root_label(eh) == cr):
        return True, f"{email_dom} redirige vers {eh}"
    if ch and (ch.endswith(email_dom) or root_label(ch) == er):
        return True, f"{comp_dom} redirige vers {ch}"
    if etxt and (comp_dom in etxt or (len(cr) >= 6 and cr in etxt)):
        return True, f"le site {email_dom} cite {comp_dom}"
    if ctxt and (email_dom in ctxt or (len(er) >= 6 and er in ctxt)):
        return True, f"le site {comp_dom} cite {email_dom}"
    return False, "aucune preuve web de lien entre les deux domaines"


def add_alias(a, b, aliases_file):
    if aliases_file is None:
        return
    try:
        data = json.loads(aliases_file.read_text(encoding="utf-8")) if aliases_file.exists() else {"groups": []}
    except Exception:
        data = {"groups": []}
    groups = data.setdefault("groups", [])
    for g in groups:
        if a in g or b in g:
            for x in (a, b):
                if x not in g: g.append(x)
            break
    else:
        groups.append([a, b])
    aliases_file.parent.mkdir(parents=True, exist_ok=True)
    aliases_file.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-env", required=True, help="nom de la variable .env contenant la clé Lemlist du compte")
    ap.add_argument("--env-file", help="fichier .env local non committé ; inutile si --key-env existe déjà dans l'environnement")
    ap.add_argument("--email-waterfall-dir", help="dossier optionnel contenant email_waterfall.py")
    ap.add_argument("--aliases-file", help="fichier JSON optionnel où mémoriser les alias de domaines validés")
    ap.add_argument("--out", required=True, help="dossier privé du run, obligatoirement hors du dossier du skill")
    ap.add_argument("--apply", action="store_true", help="met en pause les fiches en trop (réversible) ; jamais de suppression")
    ap.add_argument("--max-per-company", type=int, default=3)
    ap.add_argument("--hard-max-per-company", type=int, default=5)
    ap.add_argument("--exception", action="append", default=[], help="entreprise/groupe dispensé du plafond après validation utilisateur ; répétable")
    a = ap.parse_args()
    out = external_output_path(a.out)

    api = Lemlist(key_from_env(a.key_env, a.env_file))
    camps = api.campaigns()
    rows = []
    for c in camps:
        rs = api.leads(c["_id"])
        for r in rs:
            r["_campaign_id"], r["_campaign"], r["_campaign_lang"] = c["_id"], c.get("name", ""), campaign_lang(c.get("name", ""))
        rows += rs
        print(f"{c.get('name','?')[:50]:<50} {len(rs):>5} fiches")
    print("total:", len(rows), "fiches,", len(camps), "campagnes")

    ew = None
    email_waterfall_dir = a.email_waterfall_dir or os.environ.get("EMAIL_WATERFALL_DIR")
    if email_waterfall_dir:
        try:
            sys.path.insert(0, str(Path(email_waterfall_dir).expanduser().resolve()))
            import email_waterfall as ew
        except Exception as exc:
            print(f"AVERTISSEMENT : email-waterfall indisponible ({exc}); contrôle de domaine simplifié.")
    aliases_file = Path(a.aliases_file).expanduser().resolve() if a.aliases_file else None

    web_cache = {}
    report = {"duplicates": [], "emails": [], "per_company": []}
    to_pause = []

    # 2. doublons
    for g in find_groups(rows):
        d = decide_duplicates(g)
        entry = {"person": f"{g[0].get('firstName','')} {g[0].get('lastName','')}".strip(), "company": g[0].get("companyName"),
                 "decision": d["note"], "keep": (d["keep"] or {}).get("_id"), "actions": []}
        for r in d["lose"]:
            act = "deja arretee" if r.get("status") in STOPPED else "pause"
            entry["actions"].append({"lead": r["_id"], "campaign": r["_campaign"], "status": r.get("status"), "action": act, "a_supprimer_par_un_humain": True})
            if act == "pause": to_pause.append((r.get("email"), r["_campaign_id"], r["_id"]))
        report["duplicates"].append(entry)

    # 3. email <-> entreprise
    for r in rows:
        e = (r.get("email") or "").lower().strip()
        if "@" not in e: continue
        ed, cd = e.rsplit("@", 1)[1], (r.get("companyDomain") or "").lower().replace("www.", "")
        verdict, why = None, ""
        if ew:
            ok, why = ew.belongs_to_company(e, cd)
            verdict = "ok" if ok else ("suspect" if ok is False else "non evaluable")
        else:
            verdict = "ok" if (ed == cd or ed.endswith("." + cd)) else "suspect"
        if verdict == "suspect":
            if group_ok(ed, (r.get("companyName") or "") + " " + cd):
                verdict, why = "groupe connu", "famille de groupe"
            elif same_brand(ed, cd):
                verdict, why = "meme marque", "meme marque, autre domaine"
        if verdict == "suspect":
            ok_web, why_web = web_evidence(ed, cd) if (ed, cd) not in web_cache else web_cache[(ed, cd)]
            web_cache[(ed, cd)] = (ok_web, why_web)
            if ok_web:
                verdict, why = "verifie par le web", why_web
                if a.apply: add_alias(ed, cd, aliases_file)
                report["emails"].append({"lead": r["_id"], "email": e, "company_domain": cd, "company": r.get("companyName"),
                                         "status": r.get("status"), "campaign": r["_campaign"], "action": "OK : alias declare (" + why_web + ")", "why": why_web})
                continue
            if r.get("status") in INTENT_STATUS or has_intent(r):
                act = "rapporte seulement (a repondu / interesse : ne jamais toucher)"
            elif r.get("status") in SENDING:
                act = "pause (email sans lien prouve avec l'entreprise)"; to_pause.append((e, r["_campaign_id"], r["_id"]))
            else:
                act = "deja arretee, rapportee"
            report["emails"].append({"lead": r["_id"], "email": e, "company_domain": cd, "company": r.get("companyName"),
                                     "status": r.get("status"), "campaign": r["_campaign"], "action": act, "why": why_web})

    # 4. plafond par entreprise
    co = collections.defaultdict(list)
    for r in rows:
        k = li_slug(r.get("companyLinkedinUrl") or r.get("CompanyLinkedinUrl"), "company") or (r.get("companyDomain") or "").lower()
        if k: co[k].append(r)
    for k, v in co.items():
        n = len({(x.get("email") or li_slug(x.get("linkedinUrl"), "in")) for x in v})
        if n > a.max_per_company and k in {x.lower() for x in a.exception}:
            report.setdefault("exceptions_validees", []).append({"company": k, "contacts": n})
        elif n > a.max_per_company:
            report["per_company"].append({"company": k, "contacts": n, "niveau": "au-dessus du seuil dur" if n > a.hard_max_per_company else "au-dessus de l'ideal",
                                          "contacts_detail": [f"{x.get('firstName','')} {x.get('lastName','')} ({x['_campaign_lang']}, {x.get('status')})" for x in v]})

    # mises en pause (réversibles), jamais de suppression ni de relance
    done_pause = []
    if a.apply:
        seen = set()
        for email, cid, lid in to_pause:
            if lid in seen: continue
            seen.add(lid)
            st, _ = api.pause(email, cid)
            done_pause.append({"lead": lid, "email": email, "http": st}); time.sleep(0.4)
    report["pauses_appliquees"] = done_pause
    report["pauses_prevues"] = len({t[2] for t in to_pause})
    out.mkdir(parents=True, exist_ok=True)
    (out / "rapport.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nDOUBLONS:", len(report["duplicates"]), "| EMAILS SUSPECTS:", len(report["emails"]), "| ENTREPRISES AU-DESSUS DU SEUIL:", len(report["per_company"]),
          "| PAUSES", "appliquees" if a.apply else "prevues (dry-run)", ":", len(done_pause) if a.apply else report["pauses_prevues"])
    print("rapport:", out / "rapport.json")


if __name__ == "__main__":
    main()
