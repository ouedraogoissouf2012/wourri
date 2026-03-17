# -*- coding: utf-8 -*-
"""
fix_syntax_v19_pass3.py — Corrections ciblées finales (possessifs + cas spéciaux)
"""
import json, sys

CORPUS_PATH = "dictionnaires/corpus_ivr.json"

# Corrections exactes par id : (pattern_exact, remplacement)
FIXES = {
    'mais_vente_001': [
        ('sani i ka a fara sugu ma', 'sani aw ka a fara sugu ma'),
    ],
    'arachide_stockage_001': [
        ('sani i ka a don grenier la', 'sani aw ka a don grenier la'),
    ],
    'arachide_diagnostic_001': [
        ('— i ka drenaj labɛn', '— aw ye drenaj labɛn'),
    ],
    'manioc_vente_001': [
        ('wala i ka a kɛ gari ye', 'wala aw ye a kɛ gari ye'),
    ],
    'cacao_vente_001': [
        ('Aw ye i ka kakawo', 'Aw ye aw ta kakawo'),
    ],
    'generic_fallback_001': [
        ('N bɛ i dɛmɛ i ka sɛnɛ ko la', 'N bɛ aw dɛmɛ aw ta sɛnɛ ko la'),
        ('Aw ye i ka ɲinini wele fɔ cogo wɛrɛ', 'Aw ye aw ta ɲinini wele fɔ cogo wɛrɛ'),
    ],
    'manioc_kosheni_symptomes_001': [
        ('Ni i ye i ka bananku', 'Ni aw ye aw ta bananku'),
    ],
    'manioc_kosheni_prevention_001': [
        ('Kalo kelen kelen, i ka i ka foro kɔlɔsi ka kosheni ɲini',
         'Kalo kelen kelen, aw ye aw ta foro kɔlɔsi ka kosheni ɲini'),
        ('Ni i ye kosheni daminɛ ye', 'Ni aw ye kosheni daminɛ ye'),
    ],
    'mangue_limogo_diagnostic_001': [
        ('Ni i ye i ka maŋoro bana ye', 'Ni aw ye aw ta maŋoro bana ye'),
        ('bɔ i ka foro la', 'bɔ aw ta foro la'),
    ],
}


def main():
    with open(CORPUS_PATH, 'r', encoding='utf-8') as f:
        corpus = json.load(f)

    changed = 0
    for entry in corpus['entries']:
        eid = entry['id']
        if eid in FIXES:
            t = entry.get('reponse_bambara', '')
            for old, new in FIXES[eid]:
                t = t.replace(old, new)
            if t != entry.get('reponse_bambara', ''):
                entry['reponse_bambara'] = t
                changed += 1

    with open(CORPUS_PATH, 'w', encoding='utf-8') as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)

    sys.stdout.buffer.write(
        f"Pass 3 OK — Entrees modifiees: {changed}\n".encode('utf-8')
    )


if __name__ == '__main__':
    main()
