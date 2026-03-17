# -*- coding: utf-8 -*-
"""
fix_syntax_v19.py — Révision syntaxe CI dioula du corpus IVR
v1.8 → v1.9

Corrections appliquées :
1. kosɛbɛ → caman  (intensificateur Mali → CI)
2. lajɛ → filɛ     (verbe "regarder/récolter" Mali → CI)
3. I ka [verb] → Aw ye [verb]  (impératif singulier → pluriel respectueux CI)
4. I b'a fɛ → Aw b'a fɛ  (interrogatif respectueux)
5. I ni X tɔ! → Alu ni X!  (salutation initiation CI)
6. i ka sɛnɛ dɛmɛbaga → aw ta sɛnɛ dɛmɛbaga  (possessif CI: ta not ka)
7. I ka i ka sɛnɛ → replace possessive correctly
"""
import json
import re
import sys

CORPUS_PATH = "dictionnaires/corpus_ivr.json"

def fix_bambara(text):
    if not text:
        return text

    # 1. kosɛbɛ → caman (intensificateur Mali → CI)
    text = text.replace('kosɛbɛ', 'caman')

    # 2. lajɛ → filɛ (toutes formes : lajɛ, lajɛli, lajɛlen)
    text = text.replace('lajɛ', 'filɛ')

    # 3. Salutation initiation : I ni X tɔ! → Alu ni X!
    text = text.replace('I ni sɔgɔma tɔ!', 'Alu ni sɔgɔma!')
    text = text.replace('I ni tilefɛ tɔ!', 'Alu ni tilefɛ!')
    text = text.replace('I ni wulafɛ tɔ!', 'Alu ni wulafɛ!')
    text = text.replace('I ni sufɛ tɔ!', 'Alu ni sufɛ!')

    # 4. Possessif CI : i ka sɛnɛ dɛmɛbaga → aw ta sɛnɛ dɛmɛbaga
    text = text.replace('i ka sɛnɛ dɛmɛbaga', 'aw ta sɛnɛ dɛmɛbaga')
    # generic_hors_sujet: i ka sɛnɛ ko ɲini → aw ta sɛnɛ ko ɲini
    text = text.replace('i ka sɛnɛ ko ɲini', 'aw ta sɛnɛ ko ɲini')

    # 5. Interrogatif : I b'a fɛ → Aw b'a fɛ (après ponctuation ou en début)
    text = re.sub(r"(?<=[.!?] )I b'a fɛ", "Aw b'a fɛ", text)
    text = re.sub(r"^I b'a fɛ", "Aw b'a fɛ", text)
    # I b'a fɛ mun koo la (generic_salutation_001)
    text = text.replace("I b'a fɛ mun koo la", "Aw b'a fɛ mun koo la")

    # 6. Impératif : I ka [verb] → Aw ye [verb]
    #    Cible uniquement le "I" majuscule en début de phrase ou après . ! ?
    #    Le "i ka" minuscule (possessif) est préservé
    text = re.sub(r'(?<=[.!?] )I ka ', 'Aw ye ', text)
    text = re.sub(r'^I ka ', 'Aw ye ', text)

    return text


def main():
    with open(CORPUS_PATH, 'r', encoding='utf-8') as f:
        corpus = json.load(f)

    old_version = corpus['version']
    corpus['version'] = '1.9'
    corpus['correction_v1.9'] = (
        '2026-03-17 — Révision syntaxe CI dioula: '
        'kosɛbɛ→caman, lajɛ→filɛ (verbe CI), '
        'I ka (impératif)→Aw ye (respectueux pluriel CI), '
        'I ni X tɔ→Alu ni X (salutation CI initiation), '
        'i ka (possessif)→aw ta (possessif CI).'
    )

    changed = 0
    for entry in corpus['entries']:
        original = entry.get('reponse_bambara', '')
        fixed = fix_bambara(original)
        if fixed != original:
            entry['reponse_bambara'] = fixed
            changed += 1

    with open(CORPUS_PATH, 'w', encoding='utf-8') as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)

    sys.stdout.buffer.write((
        f"OK: {old_version} -> {corpus['version']}\n"
        f"Entrees modifiees: {changed}/{len(corpus['entries'])}\n"
    ).encode('utf-8'))


if __name__ == '__main__':
    main()
