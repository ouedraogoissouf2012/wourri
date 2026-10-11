# 06 — Budget et ressources (3 mois)

**Date** : 2026-10-11 · Horizon : S1 à S12.

> ⚠️ **Avertissement de méthode** : aucun tarif de fournisseur cloud n'est présenté ici comme
> vérifié. Les montants ci-dessous sont **les hypothèses fournies dans la mission** ou des
> postes marqués **à chiffrer**. Avant tout engagement, confirmer les prix auprès des
> fournisseurs, sur une source à jour.

## 1. Budget demandé — hypothèses de la mission

| Poste | Mensuel | 3 mois | Nature |
|---|---|---|---|
| Codage agentique | 100 USD | **300 USD** | Hypothèse fournie |
| GPU cloud à la demande | 50 USD | **150 USD** | Hypothèse fournie |
| **Total demandé** | **150 USD** | **450 USD** | |

## 2. Coûts déjà couverts

| Poste | État | Preuve |
|---|---|---|
| Hébergement (VPS Contabo + Dokploy) | ✅ **En service** | ADR-0026, déploiement en production |
| Base PostgreSQL + pgvector | ✅ **En service** | `docker-compose.prod.yml` |
| Plateforme locuteurs / atelier LQE | ✅ **En service** | ADR-0033, `app/routers/lqe.py`, service `wourilqe` déployé |
| Interfaces d'ajout et de correction | ✅ **En service** | ADR-0034, `provider_baoule`, `speaker` |
| Données déjà collectées | ✅ **Disponibles** | `data/hf_datasets/`, Common Voice `dyu` et `bci` |
| CI/CD GitHub Actions | ✅ **En service** | 5 workflows sur `APIPy` |

> Conformément à la consigne, **aucun nouvel abonnement n'est proposé** : la plateforme
> locuteurs et la gestion des données existent déjà et n'ont pas à être reconstruites.
> 🔍 **Montant réel de ces postes : non vérifié dans cette mission** (nécessite l'accès à la
> facturation).

## 3. Adéquation du budget GPU au plan

Le plan comporte **deux chantiers nécessitant du GPU** :

| Chantier | Besoin | Intensité |
|---|---|---|
| **DIO-1** (benchmark ASR dioula) | Inférence sur ≥ 20 audios, 3 fournisseurs | Faible — quelques heures |
| **BAO-2** (fine-tune ASR baoulé 1B) | Entraînement complet | **Élevée — plusieurs heures de GPU puissant, avec risque de reprise** |
| QUA-1 (mesure planifiée) | Inférence périodique | Faible à modérée, **récurrente** |

🔴 **Alerte budgétaire honnête** : **50 USD/mois est serré pour BAO-2.** Un fine-tune d'un
modèle **1B** qui échoue et doit être relancé — ce qui est arrivé sur ce projet, cf.
l'historique Kaggle — consomme le budget du mois sans produire de résultat.

**Trois options, à arbitrer par le manager :**

| Option | Description | Conséquence |
|---|---|---|
| **A** (recommandée) | Utiliser d'abord les offres gratuites (Kaggle / Colab) pour BAO-2, le budget servant de **filet** | Coût maîtrisé ; dépendance aux quotas gratuits et aux interruptions |
| **B** | Concentrer le budget GPU sur **un seul mois** (celui de S7–S8) | 150 USD disponibles au moment utile, 0 les autres mois |
| **C** | Augmenter le budget GPU | À justifier seulement si A et B échouent |

Le projet a **déjà** une pratique Kaggle/Colab documentée (`finetune/colab/`, 7 notebooks) :
l'option A s'appuie sur l'existant, elle n'est pas théorique.

## 4. Coûts inconnus — à chiffrer avant engagement

| Poste | Pourquoi inconnu | Quand il devient nécessaire |
|---|---|---|
| **Avis juridique sur les licences ML** | Hors compétence technique ; aucun devis | **LIC-1, semaine 1** — avant toute commercialisation |
| Appels LLM (DeepSeek) | Facturation à l'usage, volume non mesuré ici | Déjà en service ; à suivre |
| Stockage des sauvegardes | Dépend de la rétention choisie | **INF-2, semaine 1** |
| Temps de locuteurs natifs (dioula, baoulé) | Rémunéré ou bénévole ? **Non tranché** | DIO-1, BAO-3, AGR-2 |

🔴 **Le temps de locuteur est la ressource la plus critique et la moins budgétée.**
Quatre chantiers en dépendent (DIO-1, BAO-3, AGR-2, QUA-3). Sans disponibilité garantie, ces
chantiers glissent — **et aucun budget GPU ne compense cela**.

## 5. Besoins conditionnels

| Condition | Besoin déclenché |
|---|---|
| Si LIC-1 impose de changer de modèle TTS | Chantier supplémentaire non estimé — **potentiellement majeur** |
| Si BAO-2 échoue deux fois | GPU supplémentaire, ou report de l'axe baoulé |
| Si le volume d'agriculteurs croît fortement | Révision de l'hébergement et des quotas LLM |
| Si les enregistrements existants n'ont pas de consentement | Campagne de régularisation (temps, pas argent) |

## 6. Synthèse

| | Montant 3 mois |
|---|---|
| Demandé et justifié par le plan | **450 USD** |
| Déjà couvert | Hébergement, plateforme, données (montant non vérifié ici) |
| **À chiffrer avant décision** | Avis juridique · temps de locuteurs · stockage sauvegardes |

Le budget demandé est **cohérent avec le plan**, à une réserve près : le GPU est **juste**
pour BAO-2. L'option A (gratuit d'abord, budget en filet) permet de tenir sans augmentation.
