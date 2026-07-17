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
Transferts / Activités     →  Détection d'exceptions        →  KPIs par domaine (vols, hôtels…)
```

---

## 2. Stack technique

| Couche | Technologie | Rôle |
|---|---|---|
| **Frontend** | Next.js 16 (App Router) + React 19 + Tailwind v4 | Interface (dashboard, sources, master list, rapports) |
| **i18n** | next-intl | 3 langues : fr (défaut), nl, en |
| **Backend** | FastAPI (Python 3.12) | API REST, orchestration de la consolidation |
| **Base de données** | Supabase (PostgreSQL + Auth + Storage) | Données, authentification JWT, stockage des fichiers |
| **Parsing** | pandas + openpyxl + xlrd | Lecture .xlsx / .xls / .csv, multi-feuilles |
| **Matching flou** | rapidfuzz | Rapprochement de noms (token_set_ratio, etc.) |
| **IA** | Google Gemini (gemini-1.5-flash) | Résumés narratifs de l'analyse qualité |
| **Déploiement API** | Railway (`railway up`) | https://vo-event-max-api-production.up.railway.app |
| **Déploiement Web** | Vercel (`vercel --prod`) | Alias web-beta |
| **Monorepo** | Turborepo (npm workspaces) | apps/* + packages/* |

---

## 3. Structure du monorepo

```
vo-event-max/
├── apps/
│   ├── web/                          # Frontend Next.js
│   │   └── src/
│   │       ├── app/[locale]/         # Pages (App Router, préfixe de langue)
│   │       │   ├── login/            # Connexion (Supabase Auth)
│   │       │   ├── settings/
│   │       │   └── events/[eventId]/ # Espace de travail d'un événement :
│   │       │       ├── dashboard/    #   KPIs, avancement consolidation, qualité
│   │       │       ├── sources/      #   Import de fichiers + mapping des colonnes
│   │       │       ├── participants/ #   Fiches participants consolidées
│   │       │       ├── master-list/  #   Master list détaillée (vols, hôtels…)
│   │       │       ├── flights/  hotels/  transfers/  activities/
│   │       │       ├── exceptions/   #   Anomalies détectées
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
│       │   ├── files.py              #   upload, analyse, mapping, suppression
│       │   ├── consolidation.py      #   déclenchement + suivi des runs
│       │   ├── participants.py       #   master list, fiches, verrouillage de champs
│       │   ├── flights/hotels/transfers/activities.py
│       │   ├── exports.py  reports.py
│       │   ├── communications.py  mail_connection.py  email_agent.py
│       │   └── sharing.py            #   partage de projets entre utilisateurs
│       ├── services/                 # Logique métier (le cœur du système)
│       │   ├── file_service.py       #   lecture tabulaire intelligente (en-têtes, multi-feuilles)
│       │   ├── mapping_service.py    #   suggestion de mapping colonnes → champs canoniques
│       │   ├── consolidation_service.py  # LE pipeline (matching, dédoublonnage, extraction)
│       │   ├── exception_service.py  #   détection d'anomalies (12 types)
│       │   ├── master_list_service.py#   construction master list + analyse qualité
│       │   ├── export_service.py     #   export Excel multi-onglets
│       │   ├── deletion_service.py  audit_service.py  campaign_service.py …
│       │   └── …
│       ├── models/schemas.py         # Schémas Pydantic (validation entrées/sorties)
│       └── tests/                    # pytest (52 tests, TestClient + fake Supabase)
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
│   │   └── 003_sharing.sql           #   partage de projets (project_members)
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
└── projects (1 client = 1 projet)
    ├── project_members        ← partage : accès viewer/editor, restreignable par événement
    └── events (1 événement = 1 espace de travail)
        ├── uploaded_files     ← fichiers importés + column_mapping validé
        │   └── source_records ← CHAQUE ligne de chaque feuille, avec raw_data (brut)
        │                        et normalized_data (après mapping). ID déterministe
        │                        par (fichier, feuille, ligne) → ré-imports idempotents.
        ├── participants       ← LA fiche consolidée (1 par personne)
        │                        registration_source_id → ligne d'origine
        │                        locked_fields → champs protégés contre le ré-import
        ├── flights            ← segments de vol extraits (clé : participant+n°vol+date)
        ├── hotels + hotel_nights ← hébergement par nuit
        ├── transfers  activities + participant_activities
        ├── consolidation_runs ← historique des runs + stats
        ├── exceptions         ← anomalies (enum de 12 types, sévérité, contexte)
        ├── communications     ← campagnes email
        └── change_log         ← audit de chaque modification
```

Points importants :
- **`source_records` est la mémoire brute** : rien n'est perdu, tout est retraçable à la ligne source.
- **`participants` est la vérité consolidée** : le matching relie chaque source_record à un participant.
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
                             services/*.py  (logique métier)
                                ▼
                             Supabase (PostgreSQL + Storage)
```

- Le frontend ne parle **jamais** directement à la base : tout passe par `lib/api.ts` → FastAPI.
- La consolidation tourne en **BackgroundTask** FastAPI : le front la déclenche puis **poll**
  le statut du run (polling résilient : tolère les erreurs transitoires, recharge le dashboard à la fin).
- Les écritures lourdes sont **batchées** (chunks de 100-200) pour ne pas saturer PostgREST
  (limite ~1000 lignes par select, URLs bornées).

---

## 6. Le pipeline de consolidation (`consolidation_service.run_consolidation`)

C'est le cœur du produit. Étapes dans l'ordre :

1. **Chargement** des fichiers mappés de l'événement.
2. **Lecture multi-feuilles** : la 1ʳᵉ feuille utilise le mapping validé par l'humain ;
   les feuilles secondaires (rooming, departures…) sont **auto-mappées** (seuil de confiance 0.6).
3. **Insertion des source_records** avec **IDs déterministes** (uuid5 fichier+feuille+ligne) :
   re-consolider réécrit les mêmes lignes au lieu d'empiler des copies.
4. **Construction des profils** depuis la feuille primaire uniquement + **dédoublonnage**
   (email exact, puis noms normalisés : accents, surnoms « (Judy) », espaces/tirets, fuzzy).
5. **Upsert des participants** (fusion non destructive : les champs verrouillés sont préservés).
6. **Auto-guérison** (self-healing, à chaque run) :
   - purge des **copies périmées** de source_records ;
   - purge des **participants « bidon »** (intitulés de départements pris pour des noms :
     « Commercial Operations », « R&D »…) ;
   - **assainissement des liens** : un record dont le nom contredit clairement le participant
     lié est délié (héritage de contaminations passées) ;
   - **matching** de tous les records non liés : code participant → email (sauf email
     « contact partagé » contredit par le nom) → nom exact/fort/sous-ensemble/fuzzy →
     nom de famille unique (nom légal vs nom d'usage) ; sinon création d'un « client » ;
   - **fusion des fantômes** : les fiches doublons sans email sont fusionnées dans la fiche
     inscrite (désambiguïsation par prénom, email local-part « jieyu.zhang@ », typos).
7. **Détection d'exceptions** (12 types : passeport expiré, vol sans participant, doublon
   d'email, dates incohérentes, champs manquants…).
8. **Extraction des domaines** depuis TOUS les records liés (masterfile combiné supporté) :
   vols (clé participant+n°vol+date, choix du segment le plus riche, suppression des
   segments obsolètes), nuits d'hôtel (dates ISO, DD/MM, plages texte « Arrival 03/02 -
   departure 06/02 », colonnes par nuit « 26-janv »), transferts, activités.
9. **Statuts de complétude** recalculés (complete / incomplete / conflict).
10. **Fichiers marqués traités**, **stats du run** enregistrées, **change_log** alimenté.

**Garantie clé : déterminisme.** Deux runs sur les mêmes fichiers produisent le même résultat
(tri stable des records, clés d'upsert déterministes, préférence reproductible du « meilleur » segment).

---

## 7. L'intelligence d'import & de mapping

### Lecture de fichier (`file_service.read_tabular`)
- Formats : `.xlsx`, `.xls`, `.csv` (délimiteur auto-détecté) — compatible tous OS/appareils.
- **Détection de la ligne d'en-tête** par scoring (cellules « libellés » vs « données »).
- **Colonnes sans nom** : le contenu est analysé pour déduire un nom (Email, Téléphone,
  N° de vol, Code PNR, Date…).
- Multi-feuilles : toutes les feuilles sont lues (`read_all_sheets`).

### Suggestion de mapping (`mapping_service.suggest_mapping`)
- Synonymes multilingues par champ canonique + **fuzzy matching** sur les en-têtes
  (fautes d'orthographe tolérées).
- **Détecteurs de contenu** : téléphone, PNR, code IATA, passeport, heure, date, booléen.
- **Garde-fous** appris des bugs réels :
  - une colonne Oui/Non n'est **jamais** proposée comme identifiant (`id`) ;
  - `passport_expiry` / `date_of_birth` exigent un **indice dans l'en-tête**
    (jamais déduits du seul contenu) ;
  - attribution globale : un champ canonique n'est proposé qu'à **une seule** colonne.
- **Champs personnalisés** : l'utilisateur peut créer ses propres colonnes de mapping
  (réutilisables par événement), qui deviennent de vraies colonnes de la master list et de l'export.

---

## 8. Master list, analyse qualité & export

- `master_list_service.build_master_rows` : une ligne riche par participant — identité,
  profil (région, fonction, passeport avec garde de plausibilité…), **résumé de vol réel**
  (n°, aéroports, horaires), hôtel (nom, check-in/out), transferts, activités, champs personnalisés.
- `build_analysis` : score qualité pondéré, dimensions (contact, voyage, hébergement…),
  distributions, **recommandations concrètes**, résumé narratif IA (Gemini).
- `export_service` : Excel multi-onglets — Master List enrichie + « Analyse Qualité » + « Conseils ».

---

## 9. Sécurité & partage

- **Auth** : Supabase Auth (JWT vérifié serveur à chaque requête via `get_current_user`).
- **Rôles** : `admin` / `pm` (staff : accès à tout le tenant) ; `client` / `viewer` (accès restreint).
- **Garde centrale** : `verify_event_access(event_id, user, supabase, write=False)` est appelée
  par **tous** les endpoints d'événement — vérifie l'appartenance à l'organisation, le partage,
  et le niveau lecture/écriture (35 endpoints de mutation exigent `write=True`).
- **Partage de projets** (`project_members`, migration `003_sharing.sql`) :
  - partage par **projet entier** ou restreint à **certains événements** (`event_ids`) ;
  - niveaux **Lecture** (consultation) / **Édition** (import, mapping, consolidation) ;
  - avec des **utilisateurs existants** (par email) — liens/emails d'invitation prévus ensuite ;
  - UI : bouton « Partager » sur chaque projet → `ShareProjectModal`.
- **RGPD** : `dietary_requirements` (donnée sensible) réservé aux rôles admin/pm.

---

## 10. Déploiement & vérification

| Étape | Commande |
|---|---|
| Tests backend | `cd apps/api && pytest` (52 tests) |
| Tests matching | `cd packages/matching-engine && pytest` (44 tests) |
| TypeScript | `cd apps/web && npx tsc --noEmit` |
| Lint | `cd apps/web && npx eslint .` |
| Déploiement API | `cd apps/api && railway up --detach` |
| Déploiement Web | `cd apps/web && vercel --prod --yes` puis `vercel alias set …` |
| Migrations SQL | copier `docs/migrations/00X_*.sql` dans le SQL editor Supabase |

> ⚠️ Ni Railway ni Vercel ne se déploient automatiquement sur `git push` — le déploiement est manuel.

En plus des tests unitaires, le projet est validé par des **harnais E2E** avec un
FakeSupabase en mémoire qui rejouent des scénarios réels du masterfile LivaNova :
import multi-feuilles, departures NOM/Prénom, contamination par codes pollués,
fusion de fantômes, assainissement des liens, extraction déterministe des vols.

---

## 11. Historique de fiabilisation (leçons intégrées au code)

Le moteur a été durci itérativement contre des bugs découverts sur le **vrai masterfile client** :

| Problème rencontré | Solution intégrée |
|---|---|
| Un `id` = « Yes » reliait 44 vols à une personne | Codes non plausibles ignorés + règle mapping anti-booléen |
| Vols différents à chaque run (même source) | Tri stable + clé datée + choix reproductible du segment le plus riche |
| Doublons « Tony/Ruizhe Tang » (nom légal vs usage) | Fusion des fantômes par nom de famille + email local-part |
| « Depart Date6 » mappé sur l'expiration passeport | Champs sensibles exigent un indice d'en-tête |
| Emails d'organisateur répétés sur les rooming lists | Le nom prime sur un email « contact partagé » |
| Départements pris pour des noms (« R&D », « Comex ») | Lexique `_is_junk_name` + purge + relink par email |
| Copies de records empilées à chaque run | IDs déterministes + purge des copies périmées |

Chaque correctif est couvert par un test, et le pipeline est **auto-guérissant** :
relancer une consolidation répare les données héritées des anciens bugs.
