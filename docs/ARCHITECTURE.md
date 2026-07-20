# VO Event MAX — Comment le projet a été réalisé & structure

> **Event Intelligence V1** — plateforme de gestion événementielle white-label (VO Communication Group).
> Elle ingère les fichiers clients (masterfiles Excel, listes de vols, rooming lists, transferts, activités),
> **consolide** toutes les informations en une fiche unique par participant, détecte les anomalies,
> et produit une master list + des rapports de qualité exportables.

---

## 1. Vue d'ensemble

Le principe central : **« chaque information appartient à une personne »**.
Peu importe combien de fichiers sont importés (10 fichiers avec le même nom/prénom/email),
le moteur regroupe tout sur une seule fiche participant, en gérant les doublons, les noms
légaux vs noms d'usage (« Tony » vs « Ruizhe » Tang), les fautes de frappe et les colonnes mal nommées.

```
Fichiers Excel/CSV du client          Plateforme                        Livrables
─────────────────────────    ─────────────────────────────    ─────────────────────────
Masterfile multi-feuilles  →  Import → Analyse → Mapping    →  Master list détaillée
Liste de vols (FCM)        →  Consolidation (matching,      →  Analyse qualité + conseils
Rooming list (villas)      →  dédoublonnage, extraction)    →  Export Excel multi-onglets
Transferts / Activités     →  Arbitrage IA des doublons     →  KPIs par domaine (vols, hôtels…)
                           →  Détection d'exceptions        →  Fusions & champs à compléter
```

**Deux règles non négociables**, qui expliquent la plupart des choix techniques :

1. **Le moteur ne réécrit pas les données.** Il remappe des **en-têtes** et regroupe des lignes.
   Une valeur n'est modifiée que si c'est un artefact de lecture (ex. `4777.0` d'Excel).
2. **Rien n'est perdu.** Toute colonne porteuse de données est conservée, au pire comme champ
   personnalisé (« catch-all A→Z »), et chaque ligne source reste consultable.

---

## 2. Stack technique

| Couche | Technologie | Rôle |
|---|---|---|
| **Frontend** | Next.js 16 (App Router) + React 19 + Tailwind v4 | Interface (dashboard, sources, master list, rapports) |
| **i18n** | next-intl | 3 langues : fr (défaut), nl, en |
| **Backend** | FastAPI (Python 3.12) | API REST, orchestration de la consolidation |
| **Base de données** | Supabase (PostgreSQL + Auth + Storage) | Données, authentification JWT, stockage des fichiers |
| **Parsing** | pandas + openpyxl + xlrd | Lecture .xlsx / .xls / .csv, multi-feuilles |
| **Matching flou** | rapidfuzz | Rapprochement de noms (token_set_ratio, ratio…) |
| **IA — texte/raisonnement** | NVIDIA NIM · `nvidia/nemotron-3-ultra-550b-a55b` | Mapping ambigu, arbitrage de fusions, résumés |
| **IA — vision** | NVIDIA NIM · `meta/llama-3.2-90b-vision-instruct` | Analyse d'affiches / PDF (PyMuPDF + Pillow) |
| **IA — secours** | OpenAI puis Gemini (`gemini-2.5-flash`) | Bascule automatique si NVIDIA indisponible |
| **Aéroports** | airportsdata (hors-ligne) | Codes IATA → nom d'aéroport / ville |
| **Déploiement API** | Railway (`railway up`) | https://vo-event-max-api-production.up.railway.app |
| **Déploiement Web** | Vercel (`vercel --prod`) | Alias web-beta |
| **Monorepo** | Turborepo (npm workspaces) | apps/* + packages/* |

**Passerelle IA unique** (`services/ai_service.py`) : tout appel IA passe par `ai_text()` / `ai_json()`,
qui essaient NVIDIA → OpenAI → Gemini. Chaque provider est **désactivé pour le process** en cas de
401/403, et **chaque appel est borné par un timeout** (mapping 60 s, arbitrage 30 s, vision 120 s) pour
qu'un modèle lent ne bloque jamais l'application. Nemotron-3 Ultra est un modèle de **raisonnement** :
sa chaîne de pensée arrive dans un champ `reasoning_content` distinct, donc `content` reste du JSON propre.

---

## 3. Structure du monorepo

```
vo-event-max/
├── apps/
│   ├── web/                          # Frontend Next.js
│   │   └── src/
│   │       ├── app/[locale]/         # Pages (App Router, préfixe de langue)
│   │       │   ├── login/            # Connexion (Supabase Auth)
│   │       │   ├── settings/         # Profil, langue + REGROUPEMENT D'ÉVÉNEMENTS
│   │       │   └── events/[eventId]/ # Espace de travail d'un événement :
│   │       │       ├── dashboard/    #   KPIs, avancement consolidation, qualité
│   │       │       ├── sources/      #   Import + revue de mapping (formats inédits)
│   │       │       ├── participants/ #   Liste + fiche détaillée [participantId]
│   │       │       ├── master-list/  #   Master list détaillée (vols, hôtels…)
│   │       │       ├── flights/  hotels/  transfers/  activities/
│   │       │       ├── exceptions/   #   Anomalies + « Champs manquants »
│   │       │       ├── match-review/ #   « Fusions à vérifier » (arbitrage doublons)
│   │       │       ├── communications/ # Campagnes email (Gmail OAuth)
│   │       │       └── reports/      #   Analyse qualité + export Excel
│   │       ├── components/
│   │       │   ├── layout/           # AppLayout, Sidebar, EventSelector
│   │       │   └── ui/               # KPICard, ConcernedParticipants, ShareProjectModal…
│   │       ├── lib/api.ts            # Client API typé (un seul point d'accès au backend)
│   │       └── messages/{fr,nl,en}.json  # Traductions
│   │
│   └── api/                          # Backend FastAPI
│       ├── main.py                   # App FastAPI + enregistrement des routers
│       ├── dependencies.py           # Auth JWT, rôles, verify_event_access (garde central)
│       ├── config.py                 # Variables d'environnement
│       ├── routers/                  # 1 fichier = 1 domaine d'endpoints REST
│       │   ├── events.py             #   projets + événements (CRUD, listing filtré)
│       │   ├── files.py              #   upload, preview, mapping, suppression
│       │   ├── consolidation.py      #   déclenchement + suivi des runs
│       │   ├── participants.py       #   master list, fiches, verrouillage de champs
│       │   ├── matching.py           #   candidats de fusion + décision humaine
│       │   ├── event_grouping.py     #   événements similaires + fusion d'événements
│       │   ├── flights/hotels/transfers/activities.py
│       │   ├── exports.py  reports.py
│       │   ├── communications.py  mail_connection.py  email_agent.py
│       │   └── sharing.py            #   partage de projets entre utilisateurs
│       ├── services/                 # Logique métier (le cœur du système)
│       │   ├── ai_service.py         #   passerelle IA unique (NVIDIA → OpenAI → Gemini)
│       │   ├── file_service.py       #   lecture tabulaire intelligente (en-têtes, multi-feuilles)
│       │   ├── mapping_service.py    #   mapping colonnes → champs + rapport + auto-réparation
│       │   ├── consolidation_service.py  # LE pipeline (matching, dédoublonnage, extraction)
│       │   ├── arbitration_service.py#   arbitrage IA des doublons ambigus
│       │   ├── event_grouping_service.py # détection + fusion d'événements similaires
│       │   ├── exception_service.py  #   détection d'anomalies
│       │   ├── master_list_service.py#   construction master list + analyse qualité
│       │   ├── geo.py                #   IATA → nom d'aéroport / ville
│       │   ├── poster_service.py     #   analyse d'affiches/PDF (vision)
│       │   ├── export_service.py     #   export Excel multi-onglets
│       │   └── deletion_service.py  audit_service.py  campaign_service.py …
│       ├── models/schemas.py         # Schémas Pydantic (validation entrées/sorties)
│       └── tests/                    # pytest (TestClient + fake Supabase)
│
├── packages/
│   └── matching-engine/              # Moteur de matching réutilisable (Python pur)
│       ├── normalizer.py             #   normalisation noms/emails/téléphones
│       ├── matcher.py                #   règles de scoring certain/probable/à vérifier
│       └── tests/                    #   44 tests
│
├── docs/
│   ├── schema.sql                    # Schéma PostgreSQL complet (source de vérité)
│   ├── migrations/                   # Migrations à exécuter dans Supabase SQL editor
│   │   ├── 002_communications.sql
│   │   ├── 003_sharing.sql           #   partage de projets (project_members)
│   │   └── 004_arbitration_and_review.sql # match_candidates + statut 'review' + mapping_report
│   ├── DEPLOYMENT.md  column-mapping-reference.md  …
│   └── ARCHITECTURE.md               # ← ce document
│
├── turbo.json  package.json          # Orchestration monorepo
└── docker-compose.yml
```

---

## 4. Modèle de données (PostgreSQL / Supabase)

Hiérarchie multi-tenant :

```
organizations (tenant)
└── users (rôles : admin | pm | client | viewer)
├── column_mapping_templates  ← MÉMOIRE DES FORMATS (org-wide) : signature d'en-têtes → mapping validé
└── projects (1 client = 1 projet)
    ├── project_members        ← partage : accès viewer/editor, restreignable par événement
    └── events (1 événement = 1 espace de travail)
        ├── uploaded_files     ← fichiers importés + column_mapping validé
        │   │                    import_status : pending → (review →) mapped → processed
        │   │                    mapping_report : {colonne: {champ, confiance, source, needs_split}}
        │   └── source_records ← CHAQUE ligne de chaque feuille, avec raw_data (brut)
        │                        et normalized_data (après mapping). ID déterministe
        │                        par (fichier, feuille, ligne) → ré-imports idempotents.
        ├── participants       ← LA fiche consolidée (1 par personne)
        │                        registration_source_id → ligne d'origine
        │                        locked_fields → champs protégés contre le ré-import
        ├── flights            ← segments de vol extraits (clé : participant+n°vol+date)
        ├── hotels + hotel_nights ← hébergement par NUIT occupée (check-out = dernière nuit + 1)
        ├── transfers  activities + participant_activities
        ├── match_candidates   ← doublons ambigus à trancher (avis IA + décision humaine)
        ├── consolidation_runs ← historique des runs + stats
        ├── exceptions         ← anomalies (enum de types, sévérité, contexte)
        ├── communications     ← campagnes email
        └── change_log         ← audit de chaque modification
```

Points importants :
- **`source_records` est la mémoire brute** : rien n'est perdu, tout est retraçable à la ligne source.
- **`participants` est la vérité consolidée** : le matching relie chaque source_record à un participant.
- **`hotel_nights` stocke les nuits réellement occupées** (check-in … check-out − 1). Le check-out
  affiché est donc **la dernière nuit + 1 jour** — c'est une reconstruction, pas une colonne stockée.
- L'API utilise la **clé service-role** de Supabase et applique ses propres contrôles d'accès
  (JWT vérifié à chaque requête, garde `verify_event_access` sur chaque endpoint).

---

## 5. Comment les modules sont connectés

```
Navigateur (Next.js)
   │  fetch + JWT Supabase
   ▼
lib/api.ts  ──────────────►  FastAPI (Railway)
                                │ dependencies.py : get_current_user (JWT)
                                │                   verify_event_access (org + partage + lecture/écriture)
                                ▼
                             routers/*.py   (validation Pydantic, HTTP)
                                ▼
                             services/*.py  (logique métier)  ──► ai_service (NVIDIA/OpenAI/Gemini)
                                ▼
                             Supabase (PostgreSQL + Storage)
```

- Le frontend ne parle **jamais** directement à la base : tout passe par `lib/api.ts` → FastAPI.
- **L'upload répond instantanément.** Le mapping IA (lent) et la consolidation tournent en
  **BackgroundTask** FastAPI ; le front **poll** ensuite le statut du run.
- Les écritures lourdes sont **batchées** (chunks de 100-200) pour ne pas saturer PostgREST
  (limite ~1000 lignes par select, URLs bornées).

---

## 6. Le pipeline de consolidation (`consolidation_service.run_consolidation`)

C'est le cœur du produit. Étapes dans l'ordre :

0. **Auto-réparation des mappings stockés** (`repair_stored_mappings`) — *avant* toute relecture,
   car un `column_mapping` enregistré est réutilisé tel quel à chaque run (voir §7).
1. **Chargement** des fichiers mappés de l'événement.
2. **Purge des exceptions** de l'événement : elles décrivent l'état *actuel*, pas l'historique.
3. **Lecture multi-feuilles** : la feuille primaire utilise le mapping du fichier ; les feuilles
   secondaires (rooming, departures…) sont auto-mappées.
4. **Insertion des source_records** avec **IDs déterministes** (uuid5 fichier+feuille+ligne) :
   re-consolider réécrit les mêmes lignes au lieu d'empiler des copies.
5. **Construction des profils** + **dédoublonnage** (email exact, puis noms normalisés).
6. **Upsert des participants** (fusion non destructive : les champs verrouillés sont préservés).
7. **Auto-guérison** (self-healing, à chaque run) :
   - purge des **copies périmées** de source_records ;
   - purge des **participants « bidon »** (« Commercial Operations », « R&D »…) ;
   - **assainissement des liens** contredits par le nom ;
   - **matching** des records non liés : code → email (sauf email « contact partagé »
     contredit par le nom) → nom exact/fort/sous-ensemble/fuzzy → nom de famille unique ;
   - **fusion des fantômes** : fiches doublons sans email fusionnées dans la fiche inscrite ;
   - **arbitrage IA des doublons ambigus** (§8).
8. **Détection d'exceptions** (§10).
9. **Extraction des domaines** depuis TOUS les records liés : vols, nuits d'hôtel, transferts,
   activités — chacun avec ses replis pour les fichiers **partiels** (§11).
10. **Statuts de complétude** recalculés, **fichiers marqués traités**, **stats + change_log**.

**Garantie clé : déterminisme.** Deux runs sur les mêmes fichiers produisent le même résultat
(tri stable des records, clés d'upsert déterministes, préférence reproductible du « meilleur » segment).

**Corollaire important :** un correctif de moteur ne nettoie pas les données déjà en base ;
il faut **une** relance de consolidation par événement. Les seules corrections immédiates sont
celles calculées à l'affichage (ex. le check-out hôtel).

---

## 7. L'intelligence d'import & de mapping

### Lecture de fichier (`file_service.read_tabular`)
- Formats : `.xlsx`, `.xls`, `.csv` (délimiteur auto-détecté) — compatible tous OS/appareils.
- **Détection de la ligne d'en-tête** par scoring (cellules « libellés » vs « données »).
- **Colonnes sans nom** : le contenu est analysé pour déduire un nom.
- Multi-feuilles : toutes les feuilles sont lues (`read_all_sheets`).

### Mapping (`mapping_service.build_mapping_with_report`)

Trois couches, dans cet ordre :

1. **Heuristiques déterministes** (`suggest_mapping`) — synonymes multilingues + fuzzy sur les
   en-têtes + **détecteurs de contenu** (téléphone, PNR, IATA, passeport, heure, date, booléen).
2. **Passe IA** sur les seules colonnes non résolues (`ai_refine_mapping_detailed`) : le LLM rend,
   par colonne, `{champ, confiance 0-100, needs_split}`.
3. **Catch-all A→Z** : toute colonne restante porteuse de données devient un **champ personnalisé**
   — aucune information n'est jamais abandonnée.

Le tout produit aussi un **rapport par colonne** (`mapping_report`) : champ retenu, **confiance**,
**source** (heuristique / IA / perso) et **`needs_split`** (colonne fusionnée type « Nom complet »,
séparée en prénom/nom en aval).

### Garde-fous (tous appris de bugs réels)

- **L'en-tête prime sur le contenu.** Une colonne qui *nomme* un champ bat une colonne qui y
  *ressemble*. Sans ça, un `Conf #` de 9 chiffres passait pour un téléphone et volait le champ
  `phone` à la vraie colonne `Telephone`.
- Une colonne **Oui/Non** n'est jamais proposée comme identifiant.
- `passport_expiry` / `date_of_birth` exigent un **indice dans l'en-tête**.
- Un en-tête de **confirmation/réservation/référence** ne peut jamais devenir `phone`.
- Un en-tête nommant **une autre entité** (« Nom de l'hôtel », « Nom compagnie ») ne peut jamais
  devenir le nom d'une personne.
- **Attribution globale** : un champ canonique n'est attribué qu'à **une seule** colonne.
- ⚠️ Les motifs d'en-tête sont **ancrés sur les frontières de mots** : un `tel` non ancré matche
  aussi « ho**tel** » et remappait la colonne hôtel sur le téléphone.

### Mémoire des formats & revue au premier format inédit

- Chaque fichier reçoit une **signature de format** = `sha1(source_type + en-têtes normalisés triés)`.
- Un format **déjà validé** est retrouvé dans `column_mapping_templates` (**au niveau de
  l'organisation**, donc partagé par tous les projets) → le mapping est appliqué **en silence**.
- Un format **jamais vu** met le fichier en statut **`review`** : l'utilisateur confirme le mapping
  **une seule fois** (écran de revue avec confiance par colonne + drapeau « à splitter »), puis le
  format est mémorisé et ne sera plus jamais redemandé.
- La revue est pré-remplie avec le **mapping complet** (catch-all inclus) : confirmer ne peut pas
  perdre de colonnes.
- **Dégradation propre** : tant que la migration 004 n'est pas passée, le statut `review` n'existe
  pas → le mapping reste 100 % automatique, rien ne casse.

### Auto-réparation (`repair_stored_mappings`)

Un `column_mapping` enregistré est réutilisé **verbatim** à chaque consolidation : corriger les
heuristiques ne suffit donc pas à réparer l'existant. L'étape 0 du pipeline corrige les mappings
déjà stockés (référence de réservation sur `phone`, vraie colonne téléphone reléguée en champ
perso, nom d'hôtel posé sur le nom de la personne). L'opération est **idempotente**.

---

## 8. Dédoublonnage, arbitrage IA & fusions

Après consolidation, le moteur cherche les **fiches qui désignent la même personne**.

| Situation | Traitement |
|---|---|
| Doublon évident, fiche « maigre » sans email | **Fusion automatique** (fusion des fantômes) |
| Noms proches (78-93 %), emails identiques ou absents | **L'IA tranche** : fusionner / séparer / incertain + justification |
| Noms proches + **deux emails réels différents** | **Personnes différentes** — réglé sans appel IA |
| Nom **quasi identique** + deux emails différents | **Mis en attente de décision humaine** — jamais fusionné tout seul |

- Un verdict IA « fusionner » avec **confiance ≥ 75** fusionne immédiatement (tracé dans l'audit) ;
  tout le reste part dans le dashboard **« Fusions à vérifier »**.
- **Le test d'identité n'utilise pas le score flou.** `token_set_ratio` renvoie **100 %** dès qu'un
  jeu de mots est *inclus* dans l'autre : « Lin Lin » (un seul token) matchait « Chenyang Lin » à
  100 %. `_same_person_name` exige donc des **jeux de mots égaux**, ou une inclusion avec **au
  moins 2 mots** (« Melcy Romero » ⊂ « Melcy Romero Trujillo » = même personne).
- **Fusion sélective** : dans le dashboard, chaque champ divergent (email, téléphone, société,
  nationalité) est **cliquable** — l'utilisateur choisit la valeur qui survit. Indispensable ici,
  car la fiche conservée porte souvent l'email de la **personne qui a réservé**, pas du voyageur.
- Les candidats **en attente sont purgés et recalculés à chaque run** (comme les exceptions) :
  une carte produite par une ancienne règle ne peut pas survivre éternellement. Les candidats
  **résolus** ne sont jamais touchés.
- **Bornage** : 25 appels IA max par run, 100 candidats max — la détection reste rapide sur les
  gros événements (comparaison par blocs sur les 3 premières lettres du nom de famille).

---

## 9. Regroupement d'événements similaires

Un même événement revient souvent sous plusieurs orthographes
(« INNOVATION SUMMIT », « 2026 GLOBAL INNOVATION SUMMIT », « 026INNOVATIONSUMMIT »…).

- `event_grouping_service` normalise les noms (accents, ponctuation, mots creux) et calcule une
  similarité = **max(token_set_ratio, ratio de la forme sans espaces ni chiffres)** — c'est cette
  seconde forme qui rapproche « 026INNOVATIONSUMMIT » de « Innovation Summit ».
- Clustering **union-find** (seuil 82). Au-dessus de 92 le signal suffit ; en dessous, **le LLM
  confirme** que les noms désignent bien le même événement.
- L'écran **Paramètres** liste les groupes détectés, l'événement à conserver étant marqué ⭐.
- **Rien n'est fusionné sans confirmation.** `POST /events/merge` (managers/admins, dans
  l'organisation seulement) réassigne toutes les tables enfant vers l'événement canonique,
  supprime les doublons, puis relance une consolidation pour dédoublonner les personnes.

---

## 10. Exceptions & qualité

Une exception doit être **réelle et actionnable**. Trois familles :

| Famille | Forme | Exemple |
|---|---|---|
| **Couverture** | **Une** carte agrégée avec le nombre + les noms | « 37 participants sans vol » |
| **Champs manquants** | Par participant, **triés en sous-catégories** (Email, Téléphone, Nationalité, Régime) avec un bouton **« Ajouter »** qui ouvre la fiche et **cible le champ** (`?field=`) | « Fiche de X incomplète » |
| **Anomalies** | Par cas, avec résolution | Dates incohérentes, format invalide, divergence de nom entre sources |

Ce qui n'est **volontairement pas** une exception :

- **Un second numéro de téléphone.** Une inscription et une agence de voyage ont couramment deux
  numéros valides pour la même personne : c'est une info de contact en plus, pas une erreur.
  Les deux restent visibles dans les données sources.
- **Une différence de format.** `+1 513 376 1196` et `5133761196` sont le même numéro ;
  `LivaNova Inc.` et `LIVANOVA` la même société ; `LivaNova France` est une précision, pas une
  contradiction. Les comparaisons ignorent casse, ponctuation et suffixes juridiques.
- **Les doublons de personnes**, qui vivent désormais dans le dashboard « Fusions à vérifier »
  et non dans le flot d'exceptions.

Restent surveillées les divergences de **société / nationalité** : elles peuvent trahir une
**fusion erronée** de deux personnes.

---

## 11. Master list, vols, hôtels & export

- `master_list_service.build_master_rows` : une ligne riche par participant — identité, profil,
  **résumé de vol réel** (n°, aéroports en clair, horaires), hôtel (nom, check-in/out, nuits),
  transferts, activités, champs personnalisés.
- `build_analysis` : score qualité pondéré, dimensions, distributions, **recommandations
  concrètes**, résumé narratif IA (optionnel, jamais bloquant pour la page).
- `export_service` : Excel multi-onglets — Master List enrichie + « Analyse Qualité » + « Conseils ».
- La page **Vols** regroupe **une ligne par passager**, ses segments étiquetés **Aller / Retour** :
  un aller-retour n'apparaît plus comme deux lignes.

**Extraction robuste des fichiers partiels** — les fichiers réels sont incomplets, l'extraction
ne doit pas les jeter :

- **Vols** : horaires **12 h AM/PM** et heures à un chiffre supportés ; une valeur d'heure n'est
  jamais lue comme une date ; l'arrivée retombe sur la date de départ (vol du même jour) ;
  le n° de vol est nettoyé (`4777.0` → `4777`, `TURKISH AIRLINES INC. 4777` → `4777`) ce qui fait
  **fusionner les doublons** ; les segments périmés sont supprimés.
- **Transferts** : créés dès qu'il existe **un signal** (un lieu, une heure de prise en charge ou
  un type). Le bout manquant retombe sur l'aéroport puis la ville de l'événement, sans jamais
  produire un « X → X ». Les transferts extraits périmés sont supprimés à chaque run — les
  navettes **calculées** par le dispatcher (liées à un vol) ne sont jamais touchées.
- **Hôtels** : `hotel_nights` = nuits occupées ; le **check-out affiché = dernière nuit + 1 jour**.

---

## 12. Sécurité & partage

- **Auth** : Supabase Auth (JWT vérifié serveur à chaque requête via `get_current_user`).
- **Rôles** : `admin` / `pm` (staff : accès à tout le tenant) ; `client` / `viewer` (accès restreint).
- **Garde centrale** : `verify_event_access(event_id, user, supabase, write=False)` est appelée
  par **tous** les endpoints d'événement — appartenance à l'organisation, partage, niveau
  lecture/écriture. La fusion d'événements exige en plus un rôle manager/admin.
- **Partage de projets** (`project_members`, migration `003_sharing.sql`) :
  - partage par **projet entier** ou restreint à **certains événements** (`event_ids`) ;
  - niveaux **Lecture** / **Édition** ; avec des **utilisateurs existants** (par email) ;
  - UI : bouton « Partager » sur chaque projet → `ShareProjectModal`.
- **RGPD** : `dietary_requirements` (donnée sensible) réservé aux rôles admin/pm.
- La table `match_candidates` a RLS activé sans policy publique : seule l'API (service-role) y accède.

---

## 13. Déploiement & vérification

| Étape | Commande |
|---|---|
| Tests backend | `cd apps/api && pytest` |
| Tests matching | `cd packages/matching-engine && pytest` (44 tests) |
| TypeScript | `cd apps/web && npx tsc --noEmit` |
| Lint | `cd apps/web && npx eslint src` |
| Build web | `cd apps/web && npm run build` |
| Déploiement API | `cd apps/api && railway up --detach` |
| Déploiement Web | `cd apps/web && vercel --prod --yes` puis `vercel alias set …` |
| Migrations SQL | copier `docs/migrations/00X_*.sql` dans le SQL editor Supabase |

> ⚠️ Ni Railway ni Vercel ne se déploient automatiquement sur `git push` — le déploiement est manuel.
> ⚠️ Les migrations ne sont **pas** appliquées automatiquement : `004_arbitration_and_review.sql`
> doit être exécutée pour activer l'arbitrage et la revue de format (le code fonctionne sans, en mode dégradé).

En plus des tests unitaires, le projet est validé par une vingtaine de **harnais E2E** avec un
FakeSupabase en mémoire qui rejouent des scénarios réels du masterfile client : import
multi-feuilles, departures NOM/Prénom, contamination par codes pollués, fusion de fantômes,
extraction déterministe des vols, transferts partiels, arbitrage de doublons, revue de mapping.

*État connu :* `tests/test_api.py::test_upload_rejects_oversized_file` échoue actuellement
(400 au lieu de 413). Le fichier trop volumineux est **toujours rejeté** — seul le code diffère,
la couche multipart interceptant désormais la requête en amont du handler.

---

## 14. Historique de fiabilisation (leçons intégrées au code)

Le moteur a été durci itérativement contre des bugs découverts sur les **vrais fichiers clients**.
Chaque ligne est couverte par un test ; le pipeline est **auto-guérissant** (relancer une
consolidation répare les données héritées).

| Problème rencontré | Solution intégrée |
|---|---|
| Un `id` = « Yes » reliait 44 vols à une personne | Codes non plausibles ignorés + règle mapping anti-booléen |
| Vols différents à chaque run (même source) | Tri stable + clé datée + choix reproductible du segment le plus riche |
| Doublons « Tony/Ruizhe Tang » (nom légal vs usage) | Fusion des fantômes par nom de famille + email local-part |
| « Depart Date6 » mappé sur l'expiration passeport | Champs sensibles exigent un indice d'en-tête |
| Emails d'organisateur répétés sur les rooming lists | Le nom prime sur un email « contact partagé » |
| Départements pris pour des noms (« R&D », « Comex ») | Lexique `_is_junk_name` + purge + relink par email |
| Copies de records empilées à chaque run | IDs déterministes + purge des copies périmées |
| Crash consolidation : `has_flight` NULL | Les 4 drapeaux booléens sont toujours écrits sur un upsert mixte |
| **Un `Conf #` volait le champ téléphone** (→ des centaines de « conflits de données ») | **L'en-tête prime sur la déduction par contenu** + une référence n'est jamais un téléphone |
| « Nom de l'hôtel » pouvait écraser le **nom de famille** | Un en-tête nommant une autre entité ne peut pas devenir un nom de personne |
| Un motif `tel` non ancré remappait « ho**tel** » sur le téléphone | Motifs d'en-tête ancrés sur les frontières de mots |
| **99 % des horaires à `00:00`** | Parsing des heures **12 h AM/PM** et à un chiffre |
| Dates d'arrivée corrompues (date par défaut) | Une heure n'est jamais lue comme une date ; repli sur la date de départ |
| `4777.0` et `AIRLINE 4777` comptés comme 2 vols | Nettoyage du n° de vol → les doublons fusionnent |
| Fichier transfert **ignoré** (0 transfert créé) | Extraction dès qu'il existe un signal + replis sur les lieux manquants |
| Transferts empilés à chaque run, « MFM → MFM » | Suppression des transferts extraits périmés + repli aéroport ↔ hôtel |
| **Check-out affiché avec un jour de retard** | Check-out = dernière nuit occupée **+ 1 jour** |
| Un 2ᵉ téléphone comptait comme conflit | `phone` retiré des conflits ; société/nationalité comparées sur leur cœur de sens |
| **« Lin Lin » fusionnable avec « Chenyang Lin » à 100 %** | Test d'identité strict sur les jeux de mots (le score flou récompense les inclusions) |
| Cartes de fusion obsolètes persistantes | Candidats en attente purgés et recalculés à chaque run |
| Mapping erroné figé dans un fichier déjà importé | `repair_stored_mappings` en étape 0 du pipeline (idempotent) |
| Page mapping imposée à chaque import | Revue **une seule fois par format inédit**, puis mémorisée org-wide |
| IA lente bloquant l'interface | Mapping + consolidation en tâche de fond, timeouts par appel, modèle de raisonnement rapide |
