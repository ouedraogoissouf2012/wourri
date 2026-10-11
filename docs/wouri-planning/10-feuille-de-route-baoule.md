# 10 — Feuille de route baoulé et besoins associés

**ADC / African Digit Consulting · WOURI**
Document de présentation à la direction · 11 octobre 2026 · Horizon : 12 semaines

> **Note de méthode** : chaque affirmation de ce document est **vérifiée dans le code ou dans
> les résultats de mesure du projet**. Les points non vérifiés sont signalés comme tels.

---

## 1. Où nous en sommes vraiment

### 1.1 Ce qui est déjà acquis — et qui ne sera pas refait

| Acquis | Preuve |
|---|---|
| **Interfaces locuteurs** : ajout, relecture, correction de phrases et de voix | `app/routers/provider_baoule.py`, `app/routers/speaker.py`, ADR-0034 |
| **Circuit de validation** : file de tâches, décision, promotion | `app/services/improvement_queue.py`, `baoule_corpus.py`, ADR-0031/0033 |
| **Collecte de corpus baoulé** en Bronze, cloisonnée du dioula | `app/services/baoule_provider.py` (issue #443 **fermée**) |
| **Expérimentations Kaggle** menées et documentées | `finetune/colab/` — 7 notebooks versionnés |

**Aucun budget de reconstruction n'est demandé** : cet outillage existe et fonctionne.

### 1.2 Le résultat que nous pouvons déjà présenter

Contrairement à ce qu'une lecture rapide pourrait laisser croire, **les expérimentations
baoulé ne sont pas « à consolider » : elles ont produit des chiffres publiés.**

Source : `docs/benchmarks/0003-asr-baoule-evaluation-results.md`

| Modèle évalué | Paramètres | **CER** | WER | Échantillons |
|---|---|---|---|---|
| Omnilingual ASR CTC 300M | 300 M | 26,0 % | 67,6 % | 290 |
| **Omnilingual ASR CTC 1B** | **1 Md** | **22,1 %** | **56,7 %** | **290** |

Un modèle candidat concurrent a été écarté parce qu'il **ne produisait pas réellement du
baoulé**. Le modèle retenu est celui qui obtient le meilleur CER **tout en produisant
effectivement de la langue cible**.

➡️ **Décision prise et tracée** : ADR-0036, **accepté** — le modèle 1 Md est la base de
travail. Un premier essai d'entraînement mécanique a été exécuté avec succès (#474).

### 1.3 Un avantage juridique à faire valoir

🔑 **ADR-0036 indique que le modèle baoulé retenu bénéficie d'une licence permissive.**

C'est un point important à porter devant la direction : la **voix dioula actuellement en
production** repose, elle, sur des poids que la documentation du projet qualifie de
**non commerciaux** (ADR-0034, ADR-0002, ADR-0003 — question ouverte et **non tranchée**).

➡️ **Le chantier baoulé démarre donc sur une base juridiquement plus saine que l'existant.**
Ce n'est pas un détail : c'est un argument en faveur de l'investissement.

---

## 2. Ce que signifie réellement un CER de 22 %

Il faut être honnête sur la portée de ce chiffre, car il sera interprété.

**Un CER de 22 % signifie qu'environ un caractère sur cinq est erroné.**

| Ce que cela permet aujourd'hui | Ce que cela ne permet PAS |
|---|---|
| Reconnaître une **intention** dans un domaine restreint (une question agricole parmi un nombre limité de cas) | La **dictée libre** ou la transcription fidèle |
| Détecter des mots-clés métier (culture, action, période) | Restituer une phrase mot pour mot |
| Servir de **socle améliorable** par fine-tune | Être présenté comme « le baoulé fonctionne » |

➡️ **Conclusion à porter** : le baoulé est au stade d'une **base de travail mesurée et
viable**, pas d'un produit fini. C'est exactement le stade où un investissement court produit
le plus d'effet — et c'est pourquoi les 12 prochaines semaines comptent.

---

## 3. Le verrou à lever en priorité

🔴 **Aujourd'hui, aucun agriculteur ne peut utiliser le baoulé — même si le modèle était
parfait.**

La raison est simple et vérifiée : **le moteur ne détecte pas la langue de lui-même**, et
l'accueil WhatsApp ne propose pas le baoulé. Un utilisateur ne peut donc pas se déclarer
baoulophone (issue **#477**, ouverte).

```
Modèle ASR baoulé (CER 22 %)  ──X──  aucun agriculteur
                                │
                      il manque la PORTE D'ENTRÉE (#477)
```

➡️ **Tant que #477 n'est pas livré, tout euro et toute heure investis dans l'ASR, le NLU ou le
TTS baoulé restent sans effet pour l'utilisateur final.** C'est pourquoi ce chantier est placé
en premier, avant même la poursuite de l'entraînement.

---

## 4. Feuille de route baoulé — 12 semaines

La structure reprend volontairement le découpage déjà présenté à la direction.

### Semaines 1–2 · Capitaliser et sécuriser

| Chantier | Livrable | Charge |
|---|---|---|
| **BAO-0** — Inventaire consolidé des acquis | Un document unique : corpus collecté, notebooks, modèles, résultats, limites | 1 j |
| **QUA-2** — Contrôle de la séparation des locuteurs | Découpage entraînement / validation / test **versionné**, sans recouvrement de locuteurs | 3 j |

> ⚠️ **Pourquoi QUA-2 dès le début** : si un même locuteur apparaît des deux côtés du
> découpage, **le CER de 22,1 % est surestimé**. Ce contrôle n'a pas encore été fait. Il doit
> précéder tout nouvel entraînement, sans quoi nous mesurerions une amélioration fictive.

### Semaines 3–5 · Ouvrir la porte et fiabiliser

| Chantier | Livrable | Charge |
|---|---|---|
| **BAO-1 (#477)** — Déclaration de langue | L'agriculteur choisit le baoulé ; préférence persistée ; repli honnête tant que le contenu manque | 3 j |
| **BAO-5** — Alignement texte–audio du corpus | Contrôle de l'alignement des enregistrements du traducteur ; anomalies corrigées | 3 j |
| **QUA-3** — Consentement des enregistrements | Document de consentement, registre, conditions de réutilisation | 2 j |

> 🔴 **QUA-3 est un point juridique, pas un confort** : des voix ont déjà été collectées auprès
> d'un traducteur et de locuteurs. Aucun document de consentement n'a été trouvé dans le dépôt.
> À régulariser **avant** toute nouvelle collecte ou publication de corpus.

### Semaines 6–9 · Améliorer le modèle

| Chantier | Livrable | Charge |
|---|---|---|
| **BAO-2 (#474)** — Fine-tune complet + mesure | CER post-entraînement mesuré **sur le même jeu** (n=290) et comparé aux 22,1 % | 5 j |
| **BAO-3 (#475)** — NLU baoulé | Reconnaissance d'intention sur les cas agricoles les plus fréquents | 4 j |

**Critère d'acceptation de BAO-2** : le résultat est publié **même s'il est négatif**. Un
entraînement qui n'améliore pas, documenté, évite de refaire la même tentative et oriente la
suivante. C'est ainsi que progresse un travail de R&D.

### Semaines 10–12 · Intégrer et décider

| Chantier | Livrable | Charge |
|---|---|---|
| **BAO-6** — Essai agricole bout-en-bout | Un parcours réel : question vocale baoulé → compréhension → réponse | 3 j |
| **BAO-7** — Bilan et trajectoire | Qualité mesurée, coûts consommés, décision sur la suite (dont le TTS) | 2 j |

### Reporté hors période, en toute transparence

| Chantier | Raison |
|---|---|
| **BAO-4 (#476)** — TTS baoulé (voix de sortie) | 5 j estimés, incertitude élevée (système tonal). **Sans porte d'entrée (#477) ni compréhension (#475), une voix ne sert personne.** À instruire au trimestre suivant. |

**Charge baoulé totale sur 12 semaines : 26 jours**, à l'intérieur de l'enveloppe globale de
42 jours planifiés (le reste couvrant la maintenance du dioula et les risques critiques).

---

## 5. Jalons et preuves présentables

| Fin de | Ce qui sera montré | Preuve apportée |
|---|---|---|
| **S2** | Inventaire des acquis + découpage de données contrôlé | Le CER de référence est **fiable**, non surestimé |
| **S5** | Un agriculteur choisit le baoulé sur WhatsApp | Démonstration en direct |
| **S9** | CER après entraînement, comparé aux 22,1 % | Chiffre mesuré sur le même jeu |
| **S12** | Un parcours agricole complet en baoulé | Démonstration + bilan de coûts |

---

## 6. Besoins — ce qui est demandé

### 6.1 Budget technique

| Poste | Mensuel | 3 mois |
|---|---|---|
| Outils de développement assisté | 100 USD | 300 USD |
| Calcul GPU à la demande | 50 USD | 150 USD |
| Gestion et validation des données | **0 USD** (déjà en place) | **0 USD** |
| **Total** | **150 USD** | **450 USD** |

⚠️ **Réserve honnête sur le GPU** : 50 USD/mois est **juste** pour l'entraînement d'un modèle
de 1 milliard de paramètres. Un entraînement qui échoue et doit être relancé consomme le budget
du mois sans produire de résultat — cela s'est déjà produit sur ce projet.

**Proposition** : utiliser **prioritairement les ressources gratuites** (Kaggle, Colab), déjà
maîtrisées sur le projet, et réserver l'enveloppe comme **filet de sécurité** et pour les
reprises. Si deux tentatives échouent, un arbitrage complémentaire sera demandé — pas avant.

> 🔍 Les tarifs des plateformes de calcul varient selon les machines et la disponibilité.
> **Aucun montant ne doit être engagé sans vérification auprès du fournisseur au moment de
> l'achat.**

### 6.2 Temps dédié

Affectation prioritaire de **70 à 80 %** du temps professionnel à WOURI pendant 3 mois.

Concrètement, le plan retient **4 jours de chantiers par semaine**, le cinquième étant réservé
aux incidents, à la maintenance du dioula en production et à la documentation.

> **Ce qui est demandé n'est pas un effort supplémentaire, mais de la protection** : que les
> sollicitations extérieures soient arbitrées en début de semaine et **remplacent** un
> chantier plutôt que de s'y ajouter. Sans cette règle, le planning est faux dès la deuxième
> semaine.

### 6.3 🔴 La ressource la plus critique — et la moins budgétée

**Le temps des locuteurs natifs.**

| Chantier | Dépend d'un locuteur |
|---|---|
| BAO-5 (alignement texte–audio) | ✅ |
| BAO-3 (NLU baoulé) | ✅ |
| BAO-6 (essai agricole) | ✅ |
| QUA-3 (consentement) | ✅ |

Une règle du projet est **non négociable** et doit être rappelée à la direction :
**aucun contenu linguistique n'est inventé** — ni par un développeur, ni par une intelligence
artificielle. Toute phrase est validée par un locuteur natif (ADR-0031).

➡️ **Sans disponibilité garantie de locuteurs baoulé, ces quatre chantiers glissent — et aucun
budget de calcul ne compense cela.** C'est le vrai facteur limitant du projet.

---

## 7. Décisions demandées à la direction

| # | Décision | Échéance | Recommandation |
|---|---|---|---|
| **1** | **Temps prioritaire** (70–80 %) pendant 3 mois | Semaine 1 | Valider, avec la règle d'arbitrage hebdomadaire |
| **2** | **Budget technique** plafonné à 150 USD/mois | Semaine 1 | Valider ; ressources gratuites utilisées en premier |
| **3** | **Disponibilité de locuteurs baoulé** : volume et modalités | Semaine 1 | Indispensable — 4 chantiers en dépendent |
| **4** | **Rémunération des locuteurs** : bénévole ou rémunérée | Semaine 2 | À trancher explicitement |
| **5** | **Consentement et réutilisation** des enregistrements | Semaine 2 | À trancher avant toute nouvelle collecte |
| **6** | **Report du TTS baoulé** au trimestre suivant | Semaine 1 | Accepter — sans porte d'entrée, une voix ne sert personne |
| **7** | Suivi **hebdomadaire** + démonstration **bimensuelle** | Semaine 1 | Valider |

---

## 8. En résumé pour la direction

1. **Le baoulé n'est pas à son point de départ.** Les interfaces, la collecte et les
   expérimentations existent ; les modèles ont été **comparés sur des chiffres** et le
   meilleur a été retenu par une décision écrite.
2. **Nous avons un résultat mesuré** — CER 22,1 % sur 290 échantillons. C'est une base de
   travail viable, pas un produit fini, et nous le disons clairement.
3. **Le modèle retenu a une licence permissive**, contrairement à la voix dioula actuelle dont
   le statut commercial reste à trancher. Le baoulé part sur une base plus saine.
4. **Un seul verrou bloque tout** : sans la déclaration de langue (#477), aucun travail baoulé
   n'atteint un agriculteur. Trois jours de développement lèvent ce verrou.
5. **Ce qui est demandé** : 450 USD sur le trimestre, du temps protégé, et surtout
   **l'accès à des locuteurs baoulé**.

---

*Document établi à partir de l'audit technique du 11 octobre 2026. Détails et preuves :
[03 — audit langues et ML](03-audit-langues-ml.md), [05 — feuille de route](05-roadmap-12-semaines.md),
[08 — risques et décisions](08-risques-et-decisions.md).*
