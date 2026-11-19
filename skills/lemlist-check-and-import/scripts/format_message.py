# -*- coding: utf-8 -*-
"""
Formatte le corps d'un step email ou LinkedIn pour Lemlist, avec un espacement
correct et systematique entre paragraphes.

Regle (Etape 4a du skill) : avec `margin: 0px` sur chaque <p>, Lemlist ne met
AUCUN espace automatique entre paragraphes cote email. Idem cote LinkedIn en
texte brut : un seul \n ne cree pas de ligne visuellement separee dans le
rendu final. Sans separateur explicite entre CHAQUE paragraphe, tout le texte
s'ecrase en bloc compact.

Ce module supprime le risque d'oubli manuel : il ajoute un separateur entre
CHAQUE paire de paragraphes par defaut, et seules les paires listees dans
`tight_after` restent collees (ex: items de liste A/B/C/D/E entre eux, ou
"Best," juste avant la signature).

Usage :
    from format_message import build_email_html, build_linkedin_message

    html = build_email_html([
        "{% if firstName != blank %}Hello {{firstName}},{% else %}Hello,{% endif %}",
        "I noticed the custom furniture in your hotel's pictures...",
        "Best,",
        "{{signature}}",
    ], tight_after={2})  # index 2 = pas de saut apres "Best,"

    text = build_linkedin_message([
        "Hello {{firstName}},",
        "I emailed you about your furniture sourcing...",
        "Would it be useful?",
    ])  # aucun tight_after -> saut de ligne partout, comportement par defaut
"""

P_OPEN = '<p style="margin: 0px; box-sizing: border-box;">'
P_CLOSE = '</p>'
BR_PARAGRAPH = '<p style="margin: 0px; box-sizing: border-box;"><br style="box-sizing: border-box;"></p>'


def build_email_html(paragraphs, tight_after=None):
    """
    paragraphs: liste de chaines (contenu brut d'un paragraphe, Liquid inclus,
                images <img> incluses telles quelles).
    tight_after: set d'indices (0-based) apres lesquels NE PAS inserer de
                 paragraphe vide. Par defaut : aucun -> un espace partout.
    Retourne le HTML complet pret a passer dans `message` pour un step email.
    """
    tight_after = set(tight_after or [])
    parts = []
    n = len(paragraphs)
    for i, para in enumerate(paragraphs):
        parts.append(f"{P_OPEN}{para}{P_CLOSE}")
        if i < n - 1 and i not in tight_after:
            parts.append(BR_PARAGRAPH)
    return "".join(parts)


def build_linkedin_message(paragraphs, tight_after=None):
    """
    Meme principe pour un step LinkedIn (linkedinSend/linkedinInvite), en
    texte brut avec \n\n entre paragraphes par defaut, \n simple seulement
    pour les paires listees dans tight_after.
    """
    tight_after = set(tight_after or [])
    parts = []
    n = len(paragraphs)
    for i, para in enumerate(paragraphs):
        parts.append(para)
        if i < n - 1:
            parts.append("\n" if i in tight_after else "\n\n")
    return "".join(parts)


def audit_spacing(html_or_text, is_html=True):
    """
    Verification post-hoc : compte les paragraphes/lignes et les separateurs
    trouves, pour detecter un bloc qui serait reste sans AUCUN separateur
    (signal d'un formatage qui sera rendu incorrectement par Lemlist).

    Retourne un dict {paragraph_count, separator_count, ratio} - un ratio
    proche de 0 sur un message de plus de 3 paragraphes est suspect.
    """
    if is_html:
        paragraph_count = html_or_text.count("<p style=")
        separator_count = html_or_text.count(BR_PARAGRAPH)
    else:
        # un \n\n compte comme un separateur ; un \n simple ne compte pas
        separator_count = html_or_text.count("\n\n")
        paragraph_count = len([p for p in html_or_text.split("\n") if p.strip()])
    return {
        "paragraph_count": paragraph_count,
        "separator_count": separator_count,
        "suspect": paragraph_count > 3 and separator_count == 0,
    }


if __name__ == "__main__":
    # Auto-test rapide
    html = build_email_html(
        ["A", "B", "C", "Best,", "{{signature}}"],
        tight_after={3},
    )
    assert html.count(BR_PARAGRAPH) == 3, "3 separateurs attendus (A-B, B-C, C-Best) et aucun avant la signature"

    text = build_linkedin_message(["A", "B", "C"])
    assert text == "A\n\nB\n\nC", "separateur \\n\\n attendu partout par defaut"

    print("OK - format_message.py auto-test passed")
