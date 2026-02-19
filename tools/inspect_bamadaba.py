"""Inspecte le format du fichier Bamadaba"""
import sys
import re
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

req = urllib.request.Request(
    'https://raw.githubusercontent.com/maslinych/bamadaba/master/bamadaba.txt',
    headers={'User-Agent': 'WOURI/1.0'}
)
with urllib.request.urlopen(req, timeout=60) as r:
    data = r.read().decode('utf-8')

lines = data.split('\n')
print(f'Total lignes: {len(lines)}')

# Compter les balises
tags = Counter()
backslash = chr(92)  # \
for line in lines:
    if line and line[0] == backslash:
        parts = line.split(' ', 1)
        tags[parts[0]] += 1

print('\n=== TOP 30 BALISES ===')
for tag, count in tags.most_common(30):
    print(f'  {tag}: {count}')

# Montrer 3 entrées complètes
print('\n=== 3 ENTREES COMPLETES ===')
entry_lines = []
entry_count = 0
for line in lines[6:]:
    if line.startswith(backslash + 'lx '):
        if entry_lines and entry_count < 3:
            print(f'\n--- Entrée {entry_count+1} ---')
            for el in entry_lines:
                print(f'  {el}')
            entry_count += 1
        entry_lines = [line]
    elif entry_lines:
        entry_lines.append(line)

    if entry_count >= 3:
        break

# Chercher spécifiquement les balises de traduction française
print('\n=== BALISES AVEC TEXTE FRANCAIS (exemples) ===')
fr_tags = [t for t in tags if 'f' in t.lower() or 'g' in t.lower() or 'd' in t.lower()]
for tag in fr_tags[:10]:
    print(f'\n{tag} ({tags[tag]} occurrences):')
    count = 0
    for line in lines:
        if line.startswith(tag + ' '):
            content = line[len(tag)+1:]
            print(f'  -> {content[:80]}')
            count += 1
            if count >= 3:
                break
