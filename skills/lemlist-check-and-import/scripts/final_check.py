#!/usr/bin/env python3
"""Mechanical checks for the sequence-final-check skill.

Pure local processor — no network calls, no API keys. Consumes JSON dumps
that Claude produces via MCP tool calls (Lemlist connector + Clay), and
prints a structured Markdown report.

Inputs (paths passed as CLI args):
  --campaign campaign.json    Lemlist campaign + sequences dump
  --push push_config.json     What Lemlist variable names actually get a value
                               when Clay pushes a lead (see SKILL.md). This is
                               the critical input — see "Correction de
                               modélisation, 2026-08-10" below.
  --downstream downstream.json  Optional. Expected Lemlist lead field names
                               consumed by a client's reply-routing automation.

Usage:
  python final_check.py --campaign campaign.json --push push_config.json [--downstream downstream.json]

Correction de modélisation (2026-08-10, cas réel ExampleCo) : la v1 de ce
script comparait les variables {{...}} de la séquence Lemlist aux NOMS DE
COLONNES CLAY. C'est la mauvaise couche — le nom d'une colonne Clay n'a
souvent rien à voir avec le nom de la variable Lemlist qu'elle alimente (ex:
colonne Clay "Salutation (NL/FR" -> clé Lemlist envoyée "salutation", alors
que le template utilise "{{salutations}}" -> mismatch réel, jamais détecté
par la v1). Ce qui détermine le nom réel d'une variable côté Lemlist, c'est
la clé envoyée par l'action Clay "Add Lead to Campaign" (champs standards +
Custom Fields), pas le nom de la colonne source. `check_variables_exist`
compare donc désormais contre `push_config.json`, pas contre les colonnes Clay.
"""

import argparse
import io
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Plain interpolation: {{ variable }}
LIQUID_VAR_RE = re.compile(r'\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}')
# Lemlist inline-default syntax: {{ variable: "fallback text" }}
LIQUID_VAR_DEFAULT_RE = re.compile(r'\{\{\s*([a-zA-Z0-9_.]+)\s*:\s*"')
# Variable referenced inside a condition: {% if var ... %} / {% elsif var ... %}
LIQUID_IF_VAR_RE = re.compile(r'\{%-?\s*(?:if|els?if)\s+([a-zA-Z0-9_.]+)', re.IGNORECASE)
# "if VAR == blank ... {% endif %}" — VAR is protected because the block only
# renders when VAR IS blank (i.e. the surrounding copy handles the empty case).
LIQUID_IF_BLANK_RE = re.compile(
    r'\{%-?\s*if\s+([a-zA-Z0-9_.]+)\s*==\s*blank\s*-?%\}(.*?)\{%-?\s*endif\s*-?%\}',
    re.IGNORECASE | re.DOTALL,
)
# "if/elsif COND(s) != blank %} ... {{VAR}} ... {% elsif/else/endif %}" — a
# VAR is protected if it's only interpolated inside a branch whose condition
# guards THAT SAME var as "!= blank" (single or compound with "and", e.g. the
# common Lemlist cascading-greeting idiom: "if salutations != blank and
# lastName != blank ... elsif firstName != blank ... else ...").
LIQUID_IF_NOT_BLANK_SEGMENT_RE = re.compile(
    r'\{%-?\s*(?:if|els?if)\s+(.*?)-?%\}(.*?)(?=\{%-?\s*(?:els?if|else|endif))',
    re.IGNORECASE | re.DOTALL,
)
LIQUID_NOT_BLANK_VAR_RE = re.compile(r'([a-zA-Z0-9_.]+)\s*!=\s*blank', re.IGNORECASE)
PLACEHOLDER_RE = re.compile(r'\b(TODO|PLACEHOLDER|XXX|TBD)\b', re.IGNORECASE)
UNSUBSCRIBE_TOKENS = ('{{unsubscribeLink}}', '{{unsubscribe}}', 'unsubscribe')

# Lemlist system variables that always resolve, never sourced from a Clay
# custom field — excluded from the "must exist as a pushed variable" check.
DEFAULT_BUILTIN_VARS = {'unsubscribeUrl', 'unsubscribeLink', 'unsubscribe', 'signature', 'sender.firstName'}


def load(path):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    with p.open(encoding='utf-8') as f:
        return json.load(f)


def is_email_step(step):
    return str(step.get('type', '')).lower() == 'email'


def step_text(step):
    return str(step.get('message') or step.get('text') or step.get('body') or '')


def all_email_steps(campaign):
    out = []
    for seq in campaign.get('sequences', []):
        for step in seq.get('steps', []):
            if is_email_step(step):
                out.append((seq.get('id', seq.get('name', '?')), step))
    return out


def extract_all_variables(campaign):
    """All distinct variable names referenced anywhere in the sequence copy —
    plain interpolations, inline-default interpolations, and condition
    variables from {% if/elsif %}."""
    all_vars = set()
    for seq in campaign.get('sequences', []):
        for step in seq.get('steps', []):
            text = step_text(step) + ' ' + (step.get('subject') or '')
            all_vars |= set(LIQUID_VAR_RE.findall(text))
            all_vars |= set(LIQUID_VAR_DEFAULT_RE.findall(text))
            all_vars |= set(LIQUID_IF_VAR_RE.findall(text))
    all_vars -= {'unsubscribeLink', 'unsubscribe'}
    return all_vars


# ── Individual checks ──────────────────────────────────────────────────────

def check_variables_exist(campaign, push):
    """THE core check (the user, 2026-08-10, cas réel colleagueName1/2) — every
    variable referenced in the copy (interpolation OR condition) must be a
    variable Lemlist actually receives a value for. Compared against
    push_config.json, NOT Clay column names (see module docstring)."""
    used_vars = extract_all_variables(campaign)
    if not used_vars:
        return {'id': 'variables_existent', 'ok': [], 'issues': []}
    if push is None:
        return {'id': 'variables_existent', 'ok': [], 'issues': [f"Pas de push_config fourni — impossible de vérifier si {sorted(used_vars)} sont réellement envoyées à Lemlist."]}
    builtins = set(push.get('builtin_fields', DEFAULT_BUILTIN_VARS))
    pushed = {f.get('lemlist_field', '').strip() for f in push.get('field_sources', [])}
    available = builtins | pushed
    available_lower = {v.lower() for v in available}
    issues, ok = [], []
    for var in sorted(used_vars):
        if var.lower() in available_lower:
            ok.append(f"{{{{{var}}}}} → envoyée par le push Clay")
        else:
            issues.append(f"{{{{{var}}}}} utilisée dans la séquence Lemlist mais AUCUNE variable de ce nom n'est envoyée par le push Clay ({push.get('workflow_name', 'Add Lead to Campaign')}) — va rendre vide (ou toujours la branche else d'un {{% if %}}) pour chaque lead.")
    return {'id': 'variables_existent', 'ok': ok, 'issues': issues}


def check_subjects(campaign):
    issues, ok = [], []
    for seq_id, step in all_email_steps(campaign):
        subject = (step.get('subject') or '').strip()
        is_thread_reply = step.get('subject') is None or subject == ''
        if is_thread_reply:
            continue
        if PLACEHOLDER_RE.search(subject):
            issues.append(f"seq {seq_id}: objet contient un placeholder non résolu → \"{subject}\"")
        else:
            ok.append(f"seq {seq_id}: objet \"{subject}\"")
    return {'id': 'objet', 'ok': ok, 'issues': issues}


def check_delays(campaign):
    """delay=0 after the first step is only suspicious for message-sending
    steps (email/linkedinSend/linkedinInvite/...). A 'conditional' step
    (branch gate, e.g. hasEmailAddress/linkedinInviteAccepted) legitimately
    has delay=0 when its delayType is 'waitUntil' — that's not a wait window,
    it's an indefinite branch wait, so 0 is correct, not a bug."""
    issues, ok = [], []
    for seq in campaign.get('sequences', []):
        steps = seq.get('steps', [])
        for i, step in enumerate(steps):
            if i == 0:
                continue
            step_type = str(step.get('type', '')).lower()
            delay = step.get('delay')
            if step_type == 'conditional':
                continue
            if delay in (0, None, ''):
                issues.append(f"seq {seq.get('id', '?')} step {i+1} ({step.get('type')}): delay={delay!r} — vérifier que c'est voulu")
            else:
                ok.append(f"seq {seq.get('id', '?')} step {i+1}: delay={delay}")
    return {'id': 'delai', 'ok': ok, 'issues': issues}


def check_senders(campaign):
    senders = campaign.get('senders', [])
    if not senders:
        return {'id': 'sender', 'ok': [], 'issues': ['Aucun sender assigné à la campagne.']}
    names = [s.get('email') or s.get('name') or str(s) for s in senders]
    return {'id': 'sender', 'ok': [f"Sender(s) assigné(s) : {', '.join(names)} — à confirmer que c'est le(s) bon(s)"], 'issues': []}


def check_open_tracking(campaign):
    tracking = campaign.get('tracking', {})
    track_opens = tracking.get('trackOpens')
    if track_opens is None and 'disableTrackOpen' in campaign:
        track_opens = not campaign.get('disableTrackOpen')
    if track_opens is True:
        return {'id': 'open_tracking', 'ok': [], 'issues': ['Open tracking est ACTIF — devrait être désactivé (sauf déjà confirmé délivrabilité correcte).']}
    if track_opens is False:
        return {'id': 'open_tracking', 'ok': ['Open tracking désactivé.'], 'issues': []}
    return {'id': 'open_tracking', 'ok': [], 'issues': ['Statut du tracking introuvable dans le dump — à vérifier manuellement dans Campaign Settings.']}


def check_liquid_fallbacks(campaign, push=None):
    """Every plain {{variable}} interpolation should have a visible fallback:
    - a {% if var == blank %}...{% endif %} block (var protected because the
      block only renders when var IS blank), or
    - a {% if/elsif var != blank %}...{{var}}...{% endif %} guard where var is
      only interpolated inside its own non-blank branch (the common Lemlist
      cascading-greeting idiom), or
    - Lemlist's inline {{var: "default"}} syntax (always renders something).
    Aggregated per SEQUENCE, not per step — a variable used identically across
    3 steps of the same sequence is one finding, not three (the user, 2026-08-10:
    noisy duplicate lines make the report harder to scan). Builtins (signature,
    unsubscribe*) are excluded — Lemlist always resolves them, unprotected-ness
    doesn't apply."""
    builtins = set((push or {}).get('builtin_fields', DEFAULT_BUILTIN_VARS))
    issues, ok = [], []
    for seq in campaign.get('sequences', []):
        seq_protected, seq_plain = set(), set()
        for step in seq.get('steps', []):
            text = step_text(step) + ' ' + (step.get('subject') or '')
            if not text.strip():
                continue
            for m in LIQUID_IF_BLANK_RE.finditer(text):
                seq_protected.add(m.group(1))
            for m in LIQUID_IF_NOT_BLANK_SEGMENT_RE.finditer(text):
                condition, segment = m.group(1), m.group(2)
                guarded_vars = set(LIQUID_NOT_BLANK_VAR_RE.findall(condition))
                for var in guarded_vars:
                    if re.search(r'\{\{\s*' + re.escape(var) + r'\s*\}\}', segment):
                        seq_protected.add(var)
            seq_protected |= set(LIQUID_VAR_DEFAULT_RE.findall(text))
            seq_plain |= set(LIQUID_VAR_RE.findall(text)) - {'unsubscribeLink', 'unsubscribe'} - builtins
        unprotected = sorted(seq_plain - seq_protected)
        for var in unprotected:
            default_example = '{{' + var + ': "default"}}'
            issues.append(f"seq {seq.get('id', '?')}: variable {{{{{var}}}}} sans fallback visible (ni \"if {var} == blank\", ni \"if {var} != blank\" avec interpolation à l'intérieur, ni {default_example}) — vérifier si elle peut être vide")
        for var in sorted(seq_plain & seq_protected):
            ok.append(f"seq {seq.get('id', '?')}: {{{{{var}}}}} a un fallback")
    return {'id': 'variables_liquid_fallback', 'ok': ok, 'issues': issues}


def check_field_source_emptiness(push):
    """Emptiness on the Clay column that actually feeds each pushed Lemlist
    field, per push_config.json's field_sources[].empty_count/total_rows
    (populated by Claude via a Clay query per field, only where relevant)."""
    if push is None:
        return {'id': 'variables_non_vides', 'ok': [], 'issues': ['Pas de push_config fourni — check non exécuté.']}
    issues, ok = [], []
    checked_any = False
    for f in push.get('field_sources', []):
        empty = f.get('empty_count')
        total = f.get('total_rows')
        if empty is None or total is None:
            continue
        checked_any = True
        label = f"{f.get('lemlist_field')} (colonne Clay \"{f.get('clay_column')}\")"
        if empty > 0:
            issues.append(f"{label}: {empty}/{total} lignes vides ({round(100*empty/total)}%)")
        else:
            ok.append(f"{label}: 0/{total} lignes vides")
    if not checked_any:
        issues.append("Aucune colonne source vérifiée pour l'emptiness — ajouter empty_count/total_rows sur les field_sources pertinents dans push_config.json.")
    return {'id': 'variables_non_vides', 'ok': ok, 'issues': issues}


def check_ab_testing(campaign):
    """Real sequence-level A/B = 2+ TOP-LEVEL sequences (Sequence A / Sequence
    B), not branch sub-sequences reached via a 'conditional' step's
    conditions[].sequenceId (hasEmailAddress, linkedinInviteAccepted, etc —
    normal multichannel branching, not A/B). A sequence referenced as a
    branch target is excluded from the top-level count."""
    seqs = campaign.get('sequences', [])
    branch_targets = set()
    for seq in seqs:
        for step in seq.get('steps', []):
            for cond in step.get('conditions', []) or []:
                if cond.get('sequenceId'):
                    branch_targets.add(cond['sequenceId'])
    top_level = [s for s in seqs if s.get('steps') and s.get('id') not in branch_targets]
    if len(top_level) <= 1:
        return {'id': 'ab_testing', 'ok': ["Une seule séquence top-level active — pas d'A/B au niveau séquence (les autres séquences sont des branches conditionnelles normales, pas des variantes A/B)."], 'issues': []}
    return {
        'id': 'ab_testing',
        'ok': [],
        'issues': [f"{len(top_level)} séquences TOP-LEVEL non-vides détectées (A/B au niveau séquence) — confirmer que c'est intentionnel et que les deux variantes sont complètes, pas juste un message isolé A/B testé."],
    }


def check_unsubscribe(campaign):
    """Regle the user 03/11/2026 : ligne de desinscription dans le CORPS a partir de l'email 2 ; jamais dans l'email 1.
    (La signature du sender n'est pas lisible ici : a verifier via l'apercu / get_inbox_conversation.)"""
    ok, issues, n_seq = [], [], 0
    for seq in campaign.get('sequences', []):
        emails = [s for s in seq.get('steps', []) if is_email_step(s)]
        sid = seq.get('id', seq.get('name', '?'))
        if not emails:
            continue
        n_seq += 1
        first_has = any(t.lower() in step_text(emails[0]).lower() for t in UNSUBSCRIBE_TOKENS)
        if first_has:
            issues.append(f"Email 1 contient une desinscription (seq {sid}) : a retirer, elle commence a l'email 2.")
        for k, st in enumerate(emails[1:], start=2):
            if any(t.lower() in step_text(st).lower() for t in UNSUBSCRIBE_TOKENS):
                ok.append(f"Email {k} : desinscription presente (seq {sid}).")
            else:
                issues.append(f"Email {k} sans desinscription (seq {sid}).")
    if not n_seq:
        return {'id': 'unsubscribe', 'ok': [], 'issues': ['Aucun step email trouve.']}
    ok.append("Signature du sender a verifier a la main : elle ne doit PAS contenir la ligne.")
    return {'id': 'unsubscribe', 'ok': ok, 'issues': issues}


def check_downstream_fields(push, downstream):
    """Cross-check: fields consumed by a client's reply-routing automation
    are actually pushed by Clay (same push_config.json as check_variables_exist)."""
    if downstream is None:
        return {'id': 'downstream_automation', 'ok': [], 'issues': [], 'skipped': True}
    if push is None:
        return {'id': 'downstream_automation', 'ok': [], 'issues': ['Workflow trouvé mais pas de push_config fourni pour comparer.']}
    pushed = {f.get('lemlist_field', '').strip().lower() for f in push.get('field_sources', [])}
    workflow_name = downstream.get('workflow_name', '?')
    required = downstream.get('required_fields', [])
    issues, ok = [], []
    for field in required:
        if field.strip().lower() in pushed:
            ok.append(f"champ \"{field}\" (attendu par \"{workflow_name}\") bien poussé par Clay")
        else:
            issues.append(f"champ \"{field}\" attendu par le workflow \"{workflow_name}\" jamais poussé par Clay — l'automatisation de routing des réponses risque de casser silencieusement")
    return {'id': 'downstream_automation', 'ok': ok, 'issues': issues}


# Numbering is sequential in the rendered report (1, 2, 3...) — never
# referred to by id alone in output (the user, 2026-08-10: "numérote bien tes
# points pour que les échanges soient plus clairs").
CHECK_LABELS = {
    'variables_existent': "Chaque variable {{...}} de la séquence est réellement poussée par Clay",
    'objet': "Objet de chaque email rempli, pas de placeholder",
    'delai': "Délai entre steps (pas de 0 inattendu)",
    'sender': "Sender(s) assigné(s)",
    'open_tracking': "Open tracking désactivé",
    'variables_liquid_fallback': "Variables {{...}} avec fallback visible",
    'variables_non_vides': "Colonnes Clay qui alimentent une variable poussée : aucune ligne vide",
    'ab_testing': "A/B testing au niveau séquence",
    'unsubscribe': "Desinscription dans le corps des emails 2+, absente de l'email 1",
    'downstream_automation': "Champs attendus par l'automatisation reply-routing du client",
}

MANUAL_ONLY = [
    "Sync CRM — pousser un lead réel depuis Clay, vérifier la mise à jour côté CRM et l'absence de doublons entreprise (mapping domaine).",
    "Cleaning prénom — vérifier visuellement la qualité du cleaning (ex: pas de \"A.\" résiduel) sur un échantillon.",
    "Overview — passer en revue plusieurs dizaines d'emails dans l'onglet \"To Launch\", se les envoyer à soi-même.",
    "Photos — vérifier que les photos de profil sont bien importées dans Zapmail/Mailpool pour chaque adresse.",
    "Interest management — vérifier que le prompt \"Category\" IA gère bien le nouveau CTA (ex: réponses par chiffre).",
    "Make — vérifier que les automatisations Make sont bien configurées.",
    "MUST — ne valider que 5 leads d'abord, attendre l'envoi complet, vérifier avant de lancer le reste.",
    "user Checklist — Copy : angle validé, CCC relu, validation interne/client — jugement humain, jamais coché à la place du user.",
]


def run(campaign, push, downstream):
    return [
        check_variables_exist(campaign, push),
        check_subjects(campaign),
        check_delays(campaign),
        check_senders(campaign),
        check_open_tracking(campaign),
        check_liquid_fallbacks(campaign, push),
        check_field_source_emptiness(push),
        check_ab_testing(campaign),
        check_unsubscribe(campaign),
        check_downstream_fields(push, downstream),
    ]


def render_report(checks, campaign_name):
    lines = [f"# Sequence Final Check — {campaign_name}", '']
    blocking = []
    n = 0
    for c in checks:
        if c.get('skipped'):
            continue
        n += 1
        label = CHECK_LABELS.get(c['id'], c['id'])
        status = '⚠️' if c['issues'] else '✅'
        lines.append(f"**{n}. {status} {label}**")
        for issue in c['issues']:
            lines.append(f"   - {issue}")
            blocking.append(f"{n}. {issue}")
        for ok_item in c['ok']:
            lines.append(f"   - ✅ {ok_item}")
        lines.append('')

    lines.append("**Non vérifiable par API — reste à la charge du user** 🖐️")
    for i, item in enumerate(MANUAL_ONLY, start=1):
        lines.append(f"   M{i}. {item}")
    lines.append('')

    lines.append("## Conclusion")
    if blocking:
        lines.append(f"⚠️ **Bloquant avant test 5 leads** ({len(blocking)} point(s)) :")
        for b in blocking:
            lines.append(f"   - {b}")
    else:
        lines.append("✅ Tous les checks automatiques sont passés. Reste la liste 🖐️ manuelle ci-dessus avant le test 5 leads.")
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--campaign', required=True)
    ap.add_argument('--push', required=False)
    ap.add_argument('--downstream', required=False)
    args = ap.parse_args()

    campaign = load(args.campaign)
    if campaign is None:
        print(f"ERROR: campaign file not found or invalid: {args.campaign}", file=sys.stderr)
        sys.exit(1)
    push = load(args.push)
    downstream = load(args.downstream)

    checks = run(campaign, push, downstream)
    report = render_report(checks, campaign.get('name', '?'))
    print(report)


if __name__ == '__main__':
    main()
