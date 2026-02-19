"""
WOURI - Collecteur HuggingFace (phrases parallèles Bambara-Français)
Source: oza75/bambara-mt
"""
import json
import urllib.request
from .base_collector import BaseCollector, CollectedEntry, CollectedPhrase


class HuggingFaceCollector(BaseCollector):
    """Collecte des phrases parallèles depuis HuggingFace"""

    # API HuggingFace datasets
    BASE_URL = "https://datasets-server.huggingface.co/rows"
    DATASET = "oza75/bambara-mt"
    # URL alternative si l'API principale echoue
    ALT_URLS = [
        "https://huggingface.co/api/datasets/oza75/bambara-mt/parquet/default/train/0.parquet",
    ]

    @property
    def source_name(self) -> str:
        return "huggingface"

    def _fetch_raw(self) -> str:
        """Telecharge les donnees depuis l'API HuggingFace"""
        all_rows = []
        offset = 0
        batch_size = 100

        # Essayer l'API rows standard
        while offset < 5000:
            url = (
                f"{self.BASE_URL}"
                f"?dataset={self.DATASET}"
                f"&config=default&split=train"
                f"&offset={offset}&length={batch_size}"
            )
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "WOURI-Dictionary-Builder/1.0",
                    "Accept": "application/json",
                })
                with urllib.request.urlopen(req, timeout=30) as response:
                    data = json.loads(response.read().decode("utf-8"))

                rows = data.get("rows", [])
                if not rows:
                    break

                all_rows.extend(rows)
                offset += batch_size
                if offset % 500 == 0:
                    print(f"[huggingface] {len(all_rows)} lignes...")

            except Exception as e:
                if offset == 0:
                    print(f"[huggingface] API rows indisponible: {e}")
                    return self._fetch_via_search()
                break

        if not all_rows:
            return self._fetch_via_search()

        return json.dumps(all_rows)

    def _fetch_via_search(self) -> str:
        """Methode alternative: chercher les fichiers du dataset"""
        print("[huggingface] Tentative via API search...")
        try:
            url = f"https://huggingface.co/api/datasets/{self.DATASET}"
            req = urllib.request.Request(url, headers={
                "User-Agent": "WOURI-Dictionary-Builder/1.0",
            })
            with urllib.request.urlopen(req, timeout=30) as response:
                info = json.loads(response.read().decode("utf-8"))
            print(f"[huggingface] Dataset info: {info.get('id', 'unknown')}")

            # Essayer de lister les fichiers parquet
            url2 = f"https://huggingface.co/api/datasets/{self.DATASET}/parquet"
            req2 = urllib.request.Request(url2, headers={
                "User-Agent": "WOURI-Dictionary-Builder/1.0",
            })
            with urllib.request.urlopen(req2, timeout=30) as response:
                parquet_info = json.loads(response.read().decode("utf-8"))
            print(f"[huggingface] Parquet info disponible")
            return json.dumps({"parquet_info": parquet_info, "rows": []})

        except Exception as e:
            print(f"[huggingface] Dataset non accessible: {e}")
            return json.dumps([])

    def _parse_entries(self, raw_data: str) -> list[CollectedEntry]:
        """Extrait les mots uniques des phrases"""
        rows = json.loads(raw_data)
        # On extrait les mots des phrases, pas les entrées individuelles
        # Les phrases sont traitées dans _parse_phrases
        return []

    def _parse_phrases(self, raw_data: str) -> list[CollectedPhrase]:
        """Extrait les phrases parallèles"""
        rows = json.loads(raw_data)
        phrases = []

        for row in rows:
            row_data = row.get("row", {})
            bam = row_data.get("bambara", "").strip()
            fr = row_data.get("french", "").strip()

            if not bam or not fr:
                # Essayer d'autres noms de colonnes
                bam = row_data.get("bm", row_data.get("source", "")).strip()
                fr = row_data.get("fr", row_data.get("target", "")).strip()

            if bam and fr and len(bam) > 2 and len(fr) > 2:
                phrases.append(CollectedPhrase(
                    bam=bam,
                    fr=fr,
                    source=self.source_name,
                ))

        return phrases
