# -*- coding: utf-8 -*-
"""Preuve d'absence de perte après la refonte de SKILL.md.

Lit SKILL.legacy.md, découpe en phrases, normalise (minuscules, espaces et sauts de ligne supprimés,
puces retirées) et vérifie que CHAQUE phrase de plus de 25 caractères se retrouve dans le nouveau
SKILL.md ou dans un fichier de references/. Lecture seule.

Usage : python scripts/verify_no_loss.py [--min-len 25]
"""
import os, re, sys, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BULLET = re.compile(r'^\s*(?:[-*•]\s+|\d+\.\s+)')

def norm(s):
    return re.sub(r'\s+', '', s.lower())

def corpus_of(paths):
    parts = []
    for p in paths:
        with open(p, encoding='utf-8') as f:
            for line in f:
                parts.append(norm(BULLET.sub('', line)))
    return ''.join(parts)

def sentences(path):
    out = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = BULLET.sub('', line.rstrip('\n'))
            for s in re.split(r'(?<=[.!?])["»”)*]*\s+', line):
                if s.strip():
                    out.append(s.strip())
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-len', type=int, default=25)
    a = ap.parse_args()
    legacy = os.path.join(ROOT, 'SKILL.legacy.md')
    new_files = [os.path.join(ROOT, 'SKILL.md')]
    refdir = os.path.join(ROOT, 'references')
    for fn in sorted(os.listdir(refdir)):
        if fn.endswith('.md'):
            new_files.append(os.path.join(refdir, fn))
    corpus = corpus_of(new_files)
    checked, missing = 0, []
    for s in sentences(legacy):
        n = norm(s)
        if len(n) <= a.min_len:
            continue
        checked += 1
        if n not in corpus:
            missing.append(s)
    print('Fichiers cibles :', ', '.join(os.path.relpath(p, ROOT) for p in new_files))
    print('Phrases vérifiées :', checked)
    print('Phrases manquantes :', len(missing))
    for s in missing:
        print(' - ', s[:300])
    sys.exit(1 if missing else 0)

if __name__ == '__main__':
    main()
