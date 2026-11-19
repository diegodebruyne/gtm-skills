#!/usr/bin/env python3
"""Pre-import safeguard checks for a leads source file (CSV or XLSX).

Sequence checks do not inspect the raw lead file. This script closes that
gap by checking blacklists, duplicates and company saturation locally.

Pure local processor — no network calls, no API keys, no MCP dependency.
Point it at:
  --leads      the leads file about to be imported (CSV or XLSX)
  --blacklist  a JSON array of normalized VAT/company numbers (e.g. the
               client's Sheet1 export, one string per entry — normalize
               with the same BE+10-digits convention before passing it in)

Column names vary per client/export, so they are passed explicitly rather
than guessed — a wrong guess here is worse than no check at all.

Usage:
  python blacklist_and_dedup_check.py \
    --leads leads.csv \
    --email-col Final_email \
    --linkedin-col Personal_LinkedIn \
    --vat-col VAT_Number_Final \
    --blacklist sheet1_vats.json
"""

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

VAT_RE = re.compile(r'^(BE)?0?(\d{9,10})$', re.IGNORECASE)


def normalize_vat(s):
    """Normalize a Belgian VAT number: strip separators, pad to 10 digits, prefix BE."""
    if not s:
        return None
    s = str(s).strip()
    if not s:
        return None
    cleaned = re.sub(r'[\s.]', '', s)
    m = VAT_RE.match(cleaned)
    if not m:
        return None
    digits = m.group(2)
    if len(digits) == 9:
        digits = '0' + digits
    if len(digits) != 10:
        return None
    return 'BE' + digits


def sniff_delimiter(sample):
    try:
        return csv.Sniffer().sniff(sample, delimiters=',;\t').delimiter
    except csv.Error:
        return ','


def load_rows(path, sheet=None):
    """Returns (header: list[str], rows: list[list[str]]). Supports .csv
    (auto-sniffed delimiter, utf-8-sig) and .xlsx (named sheet, or the
    active/first sheet if --sheet isn't given — a multi-sheet workbook like
    a lemlist-mission-export output has 'Summary' as the active sheet, not
    the leads data, so always pass --sheet for those), first row header,
    values as strings."""
    p = Path(path)
    if p.suffix.lower() in ('.xlsx', '.xlsm'):
        try:
            from openpyxl import load_workbook
        except ImportError:
            print("ERROR: openpyxl required for .xlsx input — pip install openpyxl", file=sys.stderr)
            sys.exit(1)
        wb = load_workbook(p, read_only=True, data_only=True)
        if sheet:
            if sheet not in wb.sheetnames:
                print(f"ERROR: sheet '{sheet}' not found. Available: {wb.sheetnames}", file=sys.stderr)
                sys.exit(1)
            ws = wb[sheet]
        else:
            ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header = [str(c) if c is not None else '' for c in next(rows_iter)]
        rows = [['' if c is None else str(c) for c in r] for r in rows_iter]
        return header, rows
    raw = p.read_text(encoding='utf-8-sig', errors='replace')
    delim = sniff_delimiter(raw[:4096])
    reader = csv.reader(io.StringIO(raw), delimiter=delim)
    header = next(reader)
    rows = list(reader)
    return header, rows


def col_index(header, name, required=True):
    if name is None:
        return None
    try:
        return header.index(name)
    except ValueError:
        if required:
            print(f"ERROR: column '{name}' not found in header: {header}", file=sys.stderr)
            sys.exit(1)
        return None


def check_duplicates(rows, idx, label, normalize=lambda v: v.strip().lower() if v else ''):
    values = [normalize(r[idx]) for r in rows if idx < len(r) and normalize(r[idx])]
    counts = Counter(values)
    dupes = {v: c for v, c in counts.items() if c > 1}
    return {
        'label': label,
        'total_non_empty': len(values),
        'unique': len(counts),
        'duplicate_values': len(dupes),
        'duplicate_rows': sum(dupes.values()),
        'examples': list(dupes.items())[:15],
    }


def check_leads_per_company(rows, key_idx, company_idx, ideal_max=3, hard_max=5):
    """Company over-saturation check: the no-spamming rule is
    ideally max 3, hard cap 5 contacts per company in a given leads file.
    Grouped by a company key (VAT recommended — more reliable than company
    name, which varies across rows for the same entity, e.g. "Multi" vs
    "Multi.engineering" for the same VAT)."""
    counts = Counter()
    names = {}
    for r in rows:
        key = r[key_idx].strip() if key_idx < len(r) and r[key_idx] else None
        if not key:
            continue
        counts[key] += 1
        if company_idx is not None and company_idx < len(r) and r[company_idx]:
            names.setdefault(key, r[company_idx])
    over_hard = {k: c for k, c in counts.items() if c > hard_max}
    over_ideal = {k: c for k, c in counts.items() if ideal_max < c <= hard_max}
    return {
        'over_hard': sorted(((names.get(k, k), c) for k, c in over_hard.items()), key=lambda x: -x[1]),
        'over_ideal_count': len(over_ideal),
        'total_companies': len(counts),
        'ideal_max': ideal_max,
        'hard_max': hard_max,
    }


def check_blacklist(rows, header, vat_idx, company_idx, blacklist_set):
    flagged = []
    for r in rows:
        raw_vat = r[vat_idx] if vat_idx is not None and vat_idx < len(r) else None
        norm = normalize_vat(raw_vat)
        if norm and norm in blacklist_set:
            company = r[company_idx] if company_idx is not None and company_idx < len(r) else ''
            flagged.append({'vat': norm, 'company': company, 'row': r})
    return flagged


def render_report(dup_checks, blacklist_flagged, blacklist_size, leads_path, per_company=None):
    lines = [f"# Pre-import safeguard check — {Path(leads_path).name}", '']

    if per_company is not None:
        lines.append("## Contacts par entreprise (no-spamming)")
        if per_company['over_hard']:
            lines.append(f"🔴 **{len(per_company['over_hard'])} entreprise(s) au-dessus du seuil dur ({per_company['hard_max']})** sur {per_company['total_companies']} entreprises :")
            for name, c in per_company['over_hard'][:30]:
                lines.append(f"   - {name or '(nom vide)'} — {c} contacts")
            if len(per_company['over_hard']) > 30:
                lines.append(f"   - ... et {len(per_company['over_hard']) - 30} de plus")
        else:
            lines.append(f"✅ Aucune entreprise au-dessus du seuil dur ({per_company['hard_max']}) sur {per_company['total_companies']} entreprises.")
        if per_company['over_ideal_count']:
            lines.append(f"🟡 {per_company['over_ideal_count']} entreprise(s) entre {per_company['ideal_max']+1} et {per_company['hard_max']} contacts (au-dessus de l'idéal de {per_company['ideal_max']}, mais sous le seuil dur) — à revoir si possible, pas bloquant.")
        lines.append('')

    lines.append("## Blacklist cross-check")
    if blacklist_size is None:
        lines.append("⚠️ Pas de fichier blacklist fourni — check non exécuté. Toujours croiser contre `Sheet1` avant un import cold.")
    elif blacklist_flagged:
        companies = sorted({(f['vat'], f['company']) for f in blacklist_flagged})
        lines.append(f"🔴 **{len(companies)} entreprise(s) blacklistée(s) trouvée(s)** ({len(blacklist_flagged)} ligne(s) au total) sur {blacklist_size} VAT en blacklist :")
        for vat, company in companies[:30]:
            lines.append(f"   - {company or '(nom vide)'} — {vat}")
        if len(companies) > 30:
            lines.append(f"   - ... et {len(companies) - 30} de plus")
    else:
        lines.append(f"✅ Aucun recoupement avec la blacklist ({blacklist_size} VAT vérifiées).")
    lines.append('')

    lines.append("## Doublons")
    for c in dup_checks:
        lines.append(f"**{c['label']}**")
        if c['duplicate_values'] == 0:
            lines.append(f"   - ✅ 0 doublon ({c['unique']} valeurs uniques / {c['total_non_empty']} non-vides)")
        else:
            lines.append(f"   - ⚠️ {c['duplicate_values']} valeur(s) en doublon, {c['duplicate_rows']} ligne(s) concernée(s) sur {c['total_non_empty']} non-vides")
            for val, count in c['examples']:
                lines.append(f"     - {val} × {count}")
            if c['duplicate_values'] > len(c['examples']):
                lines.append(f"     - ... et {c['duplicate_values'] - len(c['examples'])} de plus")
        lines.append('')

    lines.append("## Conclusion")
    blocking = bool(blacklist_flagged) or any(c['duplicate_values'] > 0 for c in dup_checks) or bool(per_company and per_company['over_hard'])
    if blocking:
        lines.append("⚠️ **Corrections nécessaires avant import** — retirer les lignes blacklistées et dédupliquer avant de pousser vers Lemlist.")
    else:
        lines.append("✅ Rien à corriger sur ces deux points avant import.")
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--leads', required=True, help='CSV or XLSX file about to be imported')
    ap.add_argument('--sheet', required=False, help='Sheet name for .xlsx input (defaults to the active sheet — pass this explicitly for multi-sheet workbooks like a lemlist-mission-export output, where the active sheet is "Summary", not the leads data)')
    ap.add_argument('--email-col', required=False, help='Exact header name of the email column')
    ap.add_argument('--linkedin-col', required=False, help='Exact header name of the personal LinkedIn URL column')
    ap.add_argument('--vat-col', required=False, help='Exact header name of the VAT/company-number column')
    ap.add_argument('--company-col', required=False, help='Exact header name of the company-name column (only used for readable output on blacklist hits and the per-company check)')
    ap.add_argument('--blacklist', required=False, help='JSON file: array of normalized VAT strings (e.g. exported from the client Sheet1)')
    ap.add_argument('--company-key-col', required=False, help='Exact header name of the column to group contacts by company for the no-spamming check (VAT recommended — more reliable than company name for the same entity spelled differently across rows). Defaults to --vat-col if omitted.')
    ap.add_argument('--ideal-max-per-company', type=int, default=3, help='Ideal max contacts per company before flagging as a soft warning (default 3).')
    ap.add_argument('--hard-max-per-company', type=int, default=5, help='Hard max contacts per company before flagging as blocking (default 5).')
    args = ap.parse_args()

    if not args.email_col and not args.linkedin_col:
        print("ERROR: pass at least --email-col or --linkedin-col to run a duplicate check.", file=sys.stderr)
        sys.exit(1)

    header, rows = load_rows(args.leads, sheet=args.sheet)

    dup_checks = []
    if args.email_col:
        idx = col_index(header, args.email_col)
        dup_checks.append(check_duplicates(rows, idx, f'Email ("{args.email_col}")'))
    if args.linkedin_col:
        idx = col_index(header, args.linkedin_col)
        dup_checks.append(check_duplicates(rows, idx, f'LinkedIn URL ("{args.linkedin_col}")',
                                            normalize=lambda v: v.strip().rstrip('/').lower() if v else ''))

    blacklist_flagged = []
    blacklist_size = None
    if args.blacklist:
        with open(args.blacklist, encoding='utf-8') as f:
            blacklist_set = set(json.load(f))
        blacklist_size = len(blacklist_set)
        if not args.vat_col:
            print("ERROR: --blacklist requires --vat-col.", file=sys.stderr)
            sys.exit(1)
        vat_idx = col_index(header, args.vat_col)
        company_idx = col_index(header, args.company_col, required=False) if args.company_col else None
        blacklist_flagged = check_blacklist(rows, header, vat_idx, company_idx, blacklist_set)

    per_company = None
    key_col = args.company_key_col or args.vat_col
    if key_col:
        key_idx = col_index(header, key_col)
        company_idx2 = col_index(header, args.company_col, required=False) if args.company_col else None
        per_company = check_leads_per_company(rows, key_idx, company_idx2, args.ideal_max_per_company, args.hard_max_per_company)

    report = render_report(dup_checks, blacklist_flagged, blacklist_size, args.leads, per_company)
    print(report)


if __name__ == '__main__':
    main()
