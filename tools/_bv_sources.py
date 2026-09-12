"""Classes Source ABC du validateur bambara."""
import json
import logging
import re
from abc import ABC, abstractmethod
from collections import Counter
from pathlib import Path
import requests

import _bv_text

logger = logging.getLogger(__name__)

_tokeniser_simple = _bv_text._tokeniser_simple


class Source(ABC):
    """Interface pour une source de validation bambara/dioula.

    Une source produit un `Counter` (terme → score). Pour les sources TF-IDF,
    le score est `round(tf_rate / idf_rate * 100)` ; pour les listes (scrapers
    HTTP) une couche d'adaptation reste a definir en PR ulterieure.
    """

    name: str
    weight: int

    @abstractmethod
    def load(self) -> None:
        """Charge les donnees en memoire (cache `_loaded`, idempotent)."""

    @abstractmethod
    def find(self, concept_fr: str) -> Counter:
        """Retourne `{terme: score}` pour ce concept. `Counter()` vide si rien."""


class TfidfSource(Source):
    """Source TF-IDF generique sur 2 fichiers texte alignes (paires fr/dyu).

    Encapsule l'etat (paires + cache freq globale) en attribut d'instance.
    Anciennement reparti sur 4 globals module-level (`_baye_fr`, `_baye_bam`,
    `_baye_loaded`, `_baye_global_freq`) repetes par source.
    """

    def __init__(
        self,
        name: str,
        fr_path: Path,
        dyu_path: Path,
        weight: int,
        min_global: int,
        min_match_lignes: int,
    ):
        self.name = name
        self.fr_path = fr_path
        self.dyu_path = dyu_path
        self.weight = weight
        self.min_global = min_global
        self.min_match_lignes = min_match_lignes
        # Etat interne (anciennement globals)
        self._fr: list[str] = []
        self._dyu: list[str] = []
        self._global_freq: Counter = Counter()
        self._loaded = False
        # Garde-fou idempotence pour les sources qui concatenent plusieurs
        # fichiers via `append_split()` (cas Bayelemabaga, 3 splits).
        # Sans ce flag, appeler 2x une fonction d'orchestration externe
        # (ex: _bayelemabaga_load_all_splits) dupliquerait le corpus en
        # memoire → TF-IDF fausse. Fix review issue #233 PR 1 MAJOR-1.
        self._all_splits_loaded: bool = False

    def load(self) -> None:
        if self._loaded:
            return
        if self.fr_path.exists() and self.dyu_path.exists():
            with open(self.fr_path, encoding="utf-8") as f:
                self._fr = f.readlines()
            with open(self.dyu_path, encoding="utf-8") as f:
                self._dyu = f.readlines()
        self._loaded = True
        logger.info(f"[VAL] {self.name}: {len(self._fr)} paires chargees")

    def append_split(self, fr_path: Path, dyu_path: Path) -> None:
        """Ajoute un split additionnel a la source apres `load()`.

        Cas d'usage : Bayelemabaga est splitte en 3 dossiers (train/test/valid).
        `load()` charge le 1er split, `append_split()` ajoute les suivants.

        Invalide automatiquement le cache `_global_freq` pour qu'il soit
        recalcule sur l'ensemble du corpus au prochain `find()`. Fix review
        issue #233 PR 1 MAJOR-2 (encapsulation : remplace l'acces direct aux
        attributs prives `_fr`/`_dyu`/`_global_freq` depuis l'exterieur).
        """
        if not fr_path.exists() or not dyu_path.exists():
            return
        with open(fr_path, encoding="utf-8") as f:
            self._fr.extend(f.readlines())
        with open(dyu_path, encoding="utf-8") as f:
            self._dyu.extend(f.readlines())
        # Invalider le cache global_freq pour recalcul au prochain find()
        self._global_freq = Counter()

    def find(self, concept_fr: str) -> Counter:
        self.load()

        concept = concept_fr.lower()

        # Match en mot entier pour eviter les faux positifs
        # (ex: "mais" comme substring de "mais aussi").
        def _match(ligne_fr: str) -> bool:
            return bool(re.search(r"\b" + re.escape(concept) + r"\b", ligne_fr.lower()))

        lignes_match = [dyu for fr, dyu in zip(self._fr, self._dyu) if _match(fr)]

        if len(lignes_match) < self.min_match_lignes:
            return Counter()

        # TF : frequence dans les lignes matchant
        tf: Counter = Counter()
        for ligne in lignes_match:
            tf.update(_tokeniser_simple(ligne))

        # Cache freq globale (calculee une seule fois)
        if not self._global_freq:
            logger.info(f"[VAL] Calcul frequence globale {self.name} (une fois)...")
            for ligne in self._dyu:
                self._global_freq.update(_tokeniser_simple(ligne))
            logger.info(
                f"[VAL] {self.name} vocabulaire: {len(self._global_freq)} mots uniques"
            )

        n_match = len(lignes_match)
        n_total = max(len(self._dyu), 1)

        scores: Counter = Counter()
        for terme, freq_match in tf.items():
            freq_global = self._global_freq.get(terme, 0)
            if freq_global < self.min_global:
                continue
            if freq_match < 1:
                continue
            tf_rate = freq_match / n_match
            idf_rate = freq_global / n_total
            ratio = tf_rate / idf_rate
            scores[terme] = max(1, round(ratio * 100))

        return scores


class HttpScraperSource(Source):
    """Source HTTP : fetch d'une URL + extraction fenetre autour du concept.

    Issue #233 PR 3 : unifie les 4 scrapers HTTP (`_bamadaba`, `_voa_bambara`,
    `_bambara_org`, `_bamanankan_org`) qui partageaient la meme structure
    (`requests.get` → check 200 → `_extraire_fenetre`) avec uniquement
    l'URL, la fenetre, le User-Agent et un check pre-extraction qui variaient.

    Harmonisation des inconsistances historiques :
      - User-Agent Mozilla par defaut (Bamadaba n'en avait pas, les 3 autres si)
      - `pre_extraction_check=True` reproduit le test `concept in r.text` de
        Bamadaba ; les 3 autres scrapers passaient direct a `_extraire_fenetre`.

    Retourne `Counter` (uniformite avec TfidfSource) plutot que `list[str]`,
    ce qui permet a `trouver_meilleur_terme()` de dispatcher par TYPE plutot
    que par NOM (fix MAJOR-3 archi review PR 1).
    """

    DEFAULT_USER_AGENT = "Mozilla/5.0"

    def __init__(
        self,
        name: str,
        url_builder,  # Callable[[str], tuple[str, dict | None]]
        weight: int,
        fenetre: int,
        extraire_fenetre,  # Callable[[str, str, int], list[str]]
        user_agent: str = DEFAULT_USER_AGENT,
        pre_extraction_check: bool = False,
        timeout: int = 10,
    ):
        self.name = name
        self.url_builder = url_builder
        self.weight = weight
        self.fenetre = fenetre
        # Injecte : l'extraction a besoin du lexique de reference, que ce
        # module ne connait pas. L'appelant fournit la fonction liee
        # (cf. `_bv_registry.extraire_fenetre`). Evite toute dependance
        # remontante vers les modules de chargement de corpus.
        self.extraire_fenetre = extraire_fenetre
        self.user_agent = user_agent
        self.pre_extraction_check = pre_extraction_check
        self.timeout = timeout

    def load(self) -> None:
        """No-op : les sources HTTP n'ont pas de pre-loading (fetch a chaque find)."""

    def find(self, concept_fr: str) -> Counter:
        url, params = self.url_builder(concept_fr)
        try:
            r = requests.get(
                url,
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
            )
            if r.status_code != 200:
                return Counter()
            # Check pre-extraction optionnel (utilise par Bamadaba pour eviter
            # de scanner des pages qui ne contiennent pas du tout le concept).
            if self.pre_extraction_check and concept_fr.lower() not in r.text.lower():
                return Counter()
            termes = self.extraire_fenetre(r.text, concept_fr, fenetre=self.fenetre)
            return Counter(termes)
        except Exception as e:
            logger.debug(f"[VAL] {self.name}: {e}")
            return Counter()


class LookupSource(Source):
    """Source de lookup direct dans un dictionnaire JSON structure.

    Issue #233 PR 4 : finalise la migration OCP en convertissant la derniere
    source legacy (`agri_dict`) vers le pattern Source ABC. Avant cette PR,
    `_agri_dict_lookup()` retournait `list[str]`, forcant le dispatcher
    `trouver_meilleur_terme()` a garder une branche `else` legacy. Apres :
    toutes les sources retournent `Counter`, dispatcher uniforme = OCP 100%.

    Exemple de structure JSON supportee (agri_dict.json) :
        {
          "cultures": {
            "riz":   {"bambara": "malo", "variante": "kini"},
            "manioc": {"bambara": "bananku"}
          }
        }

    Score : Counter[terme] = 1 pour chaque match (presence binary, pas TF-IDF).
    Logique de confiance : `weight` au registre fait monter le score final
    via la multiplication dans `trouver_meilleur_terme()`.
    """

    def __init__(
        self,
        name: str,
        json_path: Path,
        weight: int,
        entries_root: str = "cultures",
        key_field: str = "bambara",
        variante_field: str = "variante",
    ):
        self.name = name
        self.json_path = json_path
        self.weight = weight
        self.entries_root = entries_root
        self.key_field = key_field
        self.variante_field = variante_field
        # Etat interne (anciennement globals _agri_dict, _agri_loaded)
        self._dict: dict[str, str] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        if not self.json_path.exists():
            self._loaded = True
            return
        with open(self.json_path, encoding="utf-8") as fp:
            data = json.load(fp)
        for concept, info in data.get(self.entries_root, {}).items():
            terme = info.get(self.key_field)
            if terme:
                self._dict[concept.lower()] = terme
            variante = info.get(self.variante_field)
            if variante:
                self._dict[f"{concept.lower()}__variante"] = variante
        self._loaded = True
        logger.info(f"[VAL] {self.name}: {len(self._dict)} concepts charges")

    def find(self, concept_fr: str) -> Counter:
        self.load()
        concept = concept_fr.lower()
        result: Counter = Counter()
        if concept in self._dict:
            result[self._dict[concept]] = 1
        variante_key = f"{concept}__variante"
        if variante_key in self._dict:
            result[self._dict[variante_key]] = 1
        return result

