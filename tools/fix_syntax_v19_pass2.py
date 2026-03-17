# -*- coding: utf-8 -*-
"""
fix_syntax_v19_pass2.py — Second passage de corrections
Traite les cas résiduels non couverts par le pass 1
"""
import json, re, sys

CORPUS_PATH = "dictionnaires/corpus_ivr.json"

def fix_pass2(text):
    if not text:
        return text

    # 1. Double caman (artefact du pass 1 : "jì caman kosɛbɛ" → "jì caman caman")
    text = text.replace('caman caman', 'caman')

    # 2. I b'a fɛ après }} (salutations avec météo contextuel)
    text = text.replace("}} I b'a fɛ", "}} Aw b'a fɛ")

    # 3. Instruction lowercase : ", i ka [verb]" → ", aw ye [verb]"
    #    Negative lookahead pour éviter ", i ka i ka" (possessif doublé)
    text = re.sub(r', i ka (?!i ka )', ', aw ye ', text)

    # 4. Cas spécial manioc_kosheni_prevention : "aw ye i ka foro" → "aw ye aw ta foro"
    #    (le i ka ici est possessif, pas instruction)
    text = text.replace('aw ye i ka foro', 'aw ye aw ta foro')

    # 5. "Ka i ka [nom]" (début de proposition avec possessif) → "Ka aw ta [nom]"
    text = re.sub(r'\bKa i ka (\w)', lambda m: 'Ka aw ta ' + m.group(1), text)

    return text


def main():
    with open(CORPUS_PATH, 'r', encoding='utf-8') as f:
        corpus = json.load(f)

    changed = 0
    for entry in corpus['entries']:
        original = entry.get('reponse_bambara', '')
        fixed = fix_pass2(original)
        if fixed != original:
            entry['reponse_bambara'] = fixed
            changed += 1

    with open(CORPUS_PATH, 'w', encoding='utf-8') as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)

    sys.stdout.buffer.write((
        f"Pass 2 OK — Entrees modifiees: {changed}\n"
    ).encode('utf-8'))


if __name__ == '__main__':
    main()
