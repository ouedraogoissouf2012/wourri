"""
Téléchargement robuste des datasets HuggingFace (FR↔Dioula/Bambara)
- Findora/hf_fr_dioula_full : 20 513 paires FR↔Dioula CI (Apache 2.0)
- FrancophonIA/bambara-french : 77 307 paires Bambara↔FR (MIT)

Fonctionnalités:
- Sauvegarde incrémentale (reprend là où ça s'est arrêté)
- Rate limiting avec backoff exponentiel sur HTTP 429
- Progress visible
"""

import urllib.request
import urllib.error
import urllib.parse
import json
import time
import os
import sys

BASE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'hf_datasets')
os.makedirs(BASE_DIR, exist_ok=True)

HF_API = "https://datasets-server.huggingface.co/rows"

DATASETS = [
    {
        "id": "Findora/hf_fr_dioula_full",
        "config": "default",
        "split": "train",
        "output": "findora_fr_dioula.json",
        "total": 20513,
        "batch": 100,
    },
    {
        "id": "FrancophonIA/bambara-french",
        "config": "default",
        "split": "train",
        "output": "francophonia_bambara_french.json",
        "total": 77307,
        "batch": 100,
    },
]


def load_progress(filepath):
    """Charge les données déjà téléchargées."""
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"  Reprise: {len(data)} lignes déjà téléchargées")
        return data
    return []


def save_progress(filepath, data):
    """Sauvegarde les données courantes."""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_rows(dataset_id, config, split, offset, length, retries=5):
    """Télécharge un batch de lignes avec backoff exponentiel."""
    url = (
        f"{HF_API}?dataset={urllib.parse.quote(dataset_id)}"
        f"&config={config}&split={split}"
        f"&offset={offset}&length={length}"
    )

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (compatible; wourri-downloader/1.0)')
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data.get('rows', [])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = (2 ** attempt) * 10  # 10s, 20s, 40s, 80s, 160s
                print(f"  HTTP 429 — attente {wait}s (tentative {attempt+1}/{retries})...")
                time.sleep(wait)
            elif e.code == 404:
                print(f"  HTTP 404 — dataset ou config introuvable")
                return None
            else:
                print(f"  HTTP {e.code}: {e.reason}")
                time.sleep(5)
        except Exception as ex:
            print(f"  Erreur: {ex}")
            time.sleep(10)
    return []


def extract_row(row_data, dataset_id):
    """Extrait les champs utiles d'une ligne selon le dataset."""
    row = row_data.get('row', {})
    if 'Findora' in dataset_id:
        return {
            "fr": row.get("source", row.get("fr", "")),
            "dioula": row.get("target", row.get("dioula", "")),
        }
    elif 'FrancophonIA' in dataset_id:
        return {
            "bambara": row.get("bambara", row.get("bam", "")),
            "fr": row.get("french", row.get("fr", "")),
        }
    return row


def download_dataset(ds_config):
    ds_id = ds_config["id"]
    output_file = os.path.join(BASE_DIR, ds_config["output"])
    total = ds_config["total"]
    batch = ds_config["batch"]
    config = ds_config["config"]
    split = ds_config["split"]

    print(f"\n{'='*60}")
    print(f"Dataset: {ds_id}")
    print(f"Sortie: {output_file}")
    print(f"Total attendu: {total} lignes")

    # Charge la progression existante
    rows = load_progress(output_file)
    offset = len(rows)

    if offset >= total:
        print(f"  Déjà complet ({offset}/{total} lignes) — skip")
        return rows

    delay_base = 3  # secondes entre batches normaux

    while offset < total:
        remaining = total - offset
        length = min(batch, remaining)

        batch_rows = fetch_rows(ds_id, config, split, offset, length)

        if batch_rows is None:
            print(f"  Arrêt: dataset inaccessible")
            break

        if not batch_rows:
            print(f"  Batch vide à offset {offset} — fin probable")
            break

        for row_data in batch_rows:
            rows.append(extract_row(row_data, ds_id))

        offset += len(batch_rows)

        # Sauvegarde toutes les 500 lignes
        if offset % 500 == 0 or offset >= total:
            save_progress(output_file, rows)

        pct = offset / total * 100
        print(f"  {offset}/{total} lignes ({pct:.1f}%)...", end='\r')

        # Délai entre batches
        time.sleep(delay_base)

    # Sauvegarde finale
    save_progress(output_file, rows)
    print(f"\n  DONE: {len(rows)} lignes sauvegardées dans {output_file}")
    return rows


def print_sample(rows, dataset_id, n=5):
    """Affiche quelques exemples."""
    print(f"\nExemples ({dataset_id}):")
    for row in rows[:n]:
        line = str(row).encode('ascii', 'replace').decode()
        print(f"  {line}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    for ds in DATASETS:
        if target == "all" or target in ds["id"].lower():
            rows = download_dataset(ds)
            if rows:
                print_sample(rows, ds["id"])

    print("\nTéléchargements terminés.")
