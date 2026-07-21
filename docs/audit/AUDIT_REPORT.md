# Audit VO Event Max — Nuit du 2026-07-21/22

Statut : **Terminé pour cette session.** Branche : `audit/nuit-2026-07-21` (jamais `main`).
Rien n'a été déployé, aucune variable d'environnement modifiée, aucun push vers Vercel/Render.

Voir aussi `docs/audit/PENDING_PROPOSALS.md` — les 2 propositions touchant le moteur de matching,
**non appliquées**, en attente de ta validation.

---

## A. Résumé exécutif

| Sévérité | Nombre | Détail |
|---|---|---|
| **Critique** | 1 | PROP-001 — fusion IA autonome sans validation humaine (documenté, non corrigé) |
| **Majeur** | 2 | PROP-002 — ordre non-déterministe des égalités de score (documenté, non corrigé) · Bug de contrat statut/stats consolidation (**corrigé** sur cette branche) |
| **Mineur** | 3 | Dépendances obsolètes (python-dotenv, postcss transitif) · Modèle Pydantic `ConsolidationStats` désynchronisé (**corrigé**) · OAuth `state` non signé sur mail_connection (déjà connu, non corrigé — trop risqué à corriger à l'aveugle) |
| **Style** | ~47 | 45 warnings ESLint (imports inutilisés, pattern `setState` dans `useEffect`) + 2 variables Python assignées jamais utilisées (dead code, impact nul vérifié) |

**Le point le plus important de cet audit** est la section D — une vraie violation du principe non-négociable
énoncé dans le brief a été trouvée dans le moteur de fusion de doublons assisté par IA. Elle est documentée
en détail dans `PENDING_PROPOSALS.md` (PROP-001) et n'a **pas** été corrigée directement, conformément à la consigne.

Deux bugs de contrat frontend/backend (statut de consolidation) ont été trouvés, corrigés, testés et commités
sur cette branche : ils ne touchent ni au scoring du moteur de matching ni au schéma de la base de données.

---

## B. Liste détaillée des problèmes

### B1 [CRITIQUE] — Fusion de participants auto-décidée par l'IA sans validation humaine
**Statut : documenté seulement (PROP-001), non corrigé.**
- Fichier : `apps/api/services/consolidation_service.py:2854` (appelant `arbitration_service.py::arbitrate_pair`)
- Description : quand le LLM d'arbitrage répond `"fusionner"` avec une confiance auto-déclarée ≥ 75, la fusion
  (irréversible — suppression de la fiche "perdante") s'exécute immédiatement, sans qu'aucun humain ne la voie.
- Impact : un faux positif du LLM supprime silencieusement et définitivement une vraie fiche participant.
- Correctif proposé : voir PROP-001 dans `PENDING_PROPOSALS.md` — router TOUT verdict `"fusionner"` vers la
  file `match_candidates` (revue humaine), quelle que soit la confiance.

### B2 [MAJEUR] — Ordre non-déterministe des données alimentant le matcher
**Statut : documenté seulement (PROP-002), non corrigé.**
- Fichier : `apps/api/services/consolidation_service.py:1057-1070`
- Description : `registrations`/`fcm_records` sont construits via `.select().in_(chunk)` après un `.upsert()` —
  aucun des deux n'est garanti par PostgREST/Postgres de préserver l'ordre d'entrée. `match_sources` tranche
  les égalités de score par "premier rencontré dans la liste gagne" — un ordre instable peut donc faire
  gagner une fiche différente d'un run à l'autre, pour des données identiques.
- Preuve empirique : nouveau test `test_exact_score_tie_is_broken_by_list_order_not_by_any_other_signal`
  (`apps/api/tests/test_api.py`) — mêmes deux candidats, même égalité de score, ordre d'entrée inversé →
  gagnant inversé.
- Correctif proposé : voir PROP-002 — trier explicitement les lignes récupérées avant construction des listes.

### B3 [MAJEUR] — Bug de contrat statut/stats de consolidation (**corrigé sur cette branche**)
- Fichiers : `apps/web/src/lib/api.ts`, `apps/web/src/app/[locale]/events/[eventId]/dashboard/page.tsx`,
  `apps/web/src/app/[locale]/events/[eventId]/master-list/page.tsx`, `apps/api/models/schemas.py`
- Description : le type frontend `ConsolidationRun.status` autorisait `'pending' | 'running' | 'done' | 'error'`,
  mais la contrainte Postgres réelle (`docs/schema.sql`) n'écrit jamais que `'running' | 'completed' | 'failed'`.
  Corriger le type a fait apparaître, via l'erreur de compilation TypeScript, **deux bugs réellement actifs** :
  1. `dashboard/page.tsx` : `if (updated.status === 'done')` ne se déclenchait JAMAIS → **chaque consolidation
     réussie affichait un bandeau d'erreur rouge**, alors que les données étaient correctement traitées.
  2. `master-list/page.tsx` : la boucle de polling ne cassait JAMAIS sur une vraie fin de consolidation →
     **le bouton "Lancer la consolidation" restait bloqué en état "en cours" indéfiniment** après un succès,
     jusqu'à rechargement manuel de la page.
- Correctif appliqué : types corrigés (`status`, forme réelle de `stats`), comparaisons corrigées vers
  `'completed'`/`'failed'`, modèle Pydantic `ConsolidationStats` resynchronisé avec le dict réel +
  `extra="allow"` en filet de sécurité. Build frontend vérifié propre, 113 tests backend passent.
- Commit : `c84caf9`.

### B4 [MINEUR] — Dépendances obsolètes
- `python-dotenv==1.0.1` (requirements.txt : `>=1.0.0`) — vulnérabilité connue (PYSEC-2026-2270), correctif en
  1.2.2. Risque réel faible (fichier `.env` local, non contrôlé par un attaquant), mais mise à jour triviale
  recommandée.
- `postcss < 8.5.10` (dépendance transitive de Next.js, XSS via sortie CSS non échappée, sévérité modérée
  selon `npm audit`) — le correctif suggéré par npm (downgrade Next.js vers la v9) est manifestement erroné
  pour ce projet ; à surveiller lors de la prochaine mise à jour de Next.js plutôt qu'à corriger isolément.
- **Note de méthode** : `pip-audit` sur cet environnement Python a initialement remonté 39 vulnérabilités
  dans des paquets (`pillow`, `pypdf`, `python-jose`, `cryptography`, `httplib2`, `ecdsa`, `pyasn1`) — vérifié
  qu'AUCUN de ces paquets n'appartient réellement à `requirements.txt` ni à ses dépendances transitives
  (`pip show --Required-by` confirme qu'ils viennent d'autres projets installés globalement sur cette
  machine). Ils ne sont **pas** reportés ici pour éviter un faux signal — mais cela confirme aussi l'absence
  d'environnement virtuel dédié pour ce backend (voir section E).

### B5 [MINEUR] — Modèle Pydantic `ConsolidationStats` désynchronisé du dict réel (**corrigé**, voir B3)
Inclus dans le commit `c84caf9`. Impact réel vérifié comme nul avant correction (le seul endpoint qui
construit ce modèle le fait avant que `stats` existe), mais latent — aurait pu perdre des champs
silencieusement si le modèle avait été réutilisé ailleurs.

### B6 [MINEUR] — OAuth `state` non signé (mail_connection) — déjà connu, non corrigé
- `apps/api/services/mail_connection_service.py:57,101` — TODOs explicites dans le code.
- Non traité cette nuit : nécessite un test live du flux OAuth pour valider un correctif sans risquer de
  casser la connexion boîte mail en production — hors de portée d'une correction à l'aveugle.

### B7 [STYLE] — Imports inutilisés / code mort (Python, via `pyflakes`)
24 imports inutilisés répartis sur `dependencies.py`, `models/schemas.py`, plusieurs routers et services
(liste complète disponible via `python -m pyflakes apps/api`). Deux variables locales assignées jamais
utilisées (`export_service.py:60` `max_len`, `email_agent_service.py:117` `name_str`) — vérifiées
individuellement : **aucun impact fonctionnel**, code mort pur dans les deux cas.

### B8 [STYLE] — Warnings ESLint (frontend)
45 warnings, 0 erreur (`npx eslint src`) : imports inutilisés (`Zap`, `Folder`, `CheckSquare`, `Eye`,
`setVehicle`, `defaultStepKeys`, `_`), et le pattern `useEffect(() => { load() }, [...])` (appel de fetch au
montage) flaggé par la règle plus récente `react-hooks/set-state-in-effect` — pattern utilisé de façon
cohérente et délibérée dans une dizaine de pages de ce projet ; à évaluer comme choix d'équipe plutôt qu'à
corriger page par page sans discussion.

---

## C. Résultats des tests de scénarios

| Scénario | Résultat | Statut |
|---|---|---|
| Datasets valides (300 participants, 600 vols, 600 transferts — événement réel testé cette semaine) | Traité correctement, déterministe à l'exécution (voir réserve D2) | ✅ |
| Champs vides / nulls dans les fichiers sources | Gérés explicitement (`_has_real_date`, fallbacks documentés dans `mapping_service.py`/`consolidation_service.py`) | ✅ |
| Doublons de participants (email identique) | Détecté par `detect_duplicate_emails`/`detect_duplicate_participant_emails`, exceptions générées | ✅ |
| Quasi-doublons ambigus (noms proches) | Arbitrage IA + revue humaine — **mais fusion auto-exécutée si confiance ≥75** | ⚠️ voir B1/PROP-001 |
| Fichiers Excel malformés (colonnes manquantes/renommées) | Auto-mapping heuristique + auto-réparation (`repair_stored_mappings`, 8 règles) déjà durcis lors d'un audit précédent cette semaine (voir note ci-dessous) | ✅ |
| Égalités de score parfaites (ties) | Tranchées de façon déterministe *pour un ordre de liste fixé*, mais cet ordre lui-même n'est pas garanti stable d'un run à l'autre | ⚠️ voir B2/PROP-002 |
| Poids/seuils extrêmes | Pas de poids exposés à l'utilisateur (seuils `SCORE_CERTAIN_THRESHOLD=95`/`SCORE_PROBABLE_THRESHOLD=75` codés en dur, non paramétrables) — surface d'attaque "poids extrême" inexistante côté utilisateur | ✅ (non applicable) |
| Concurrence (plusieurs utilisateurs, mêmes données) | Plusieurs races corrigées lors d'un audit précédent cette semaine (verrous conditionnels sur `email_proposals`, `match_candidates`, garde anti-concurrence `is_consolidation_running`) ; testé via `TestConsolidationConcurrencyGuard`, `TestMatchCandidateResolveRace`, `TestDeleteFileConcurrencyGuard` | ✅ |
| Injection SQL | Aucune requête SQL brute trouvée (`grep .rpc(` vide) — tout passe par le query builder Supabase (paramétré par construction) | ✅ |
| XSS frontend | Aucun `dangerouslySetInnerHTML` dans tout `apps/web/src` — React échappe par défaut | ✅ |
| Contrôle d'accès inter-événements | `verify_event_access` audité en profondeur lors d'un audit précédent cette semaine (IDOR corrigés sur email-agent, export, participants globaux) | ✅ |
| Panne Supabase / timeout | La plupart des appels DB sont enveloppés en `try/except` avec logging + dégradation (ex. `repair_stored_mappings`, `_infer_event_city` : échec silencieux, comportement par défaut sûr) | ✅ |
| Erreur d'upload Excel | Validation de taille/format déjà en place (`TestFileUpload`) | ✅ |

**Note** : les lignes marquées "audit précédent cette semaine" correspondent à des corrections déjà commitées
et déployées sur `main` avant cette session (IDOR, races, mapping auto-réparé, injection de formule Excel) —
elles ne sont pas re-détaillées ici mais ont été vérifiées toujours actives en lisant le code courant.

---

## D. Points spécifiques au moteur de matching

### D1. Déterminisme
Le matcher lui-même (`_compute_name_score`, `match_sources`) est une fonction pure : mêmes entrées → même
sortie, toujours (rapidfuzz est déterministe, pas de composant aléatoire). **Mais** les entrées qu'il reçoit
(`registrations`, `fcm_records`) ne sont pas garanties dans un ordre stable d'un run à l'autre — voir B2/PROP-002.
Concrètement : pour la quasi-totalité des cas réels (scores non-égaux), le résultat est parfaitement
reproductible. Le risque ne se matérialise que sur une égalité EXACTE de score, un cas rare mais réel
(ex. deux personnes homonymes sur un même événement).

L'arbitrage IA (`arbitration_service.arbitrate_pair`) utilise `temperature: 0`, ce qui le rend
quasi-déterministe en pratique, sans garantie absolue de reproductibilité bit-à-bit selon le fournisseur LLM.

### D2. Respect du principe "l'IA ne décide jamais seule"
**Violation confirmée** — voir B1/PROP-001. Le chemin déterministe (email exact, seuils fixes) n'est PAS
concerné : c'est une règle transparente et reproductible, pas un jugement d'IA, et le produit ne pourrait pas
fonctionner comme outil de consolidation automatique sans ce niveau d'automatisation déterministe de base
(sinon chaque correspondance email exacte devrait être validée à la main, ce qui viderait l'outil de sa valeur).
Le problème est spécifiquement l'auto-fusion pilotée par LLM à confiance ≥75, qui, elle, EST un jugement d'IA
appliqué à une opération destructive sans confirmation humaine.

### D3. Gestion des égalités (ties)
Voir B2/D1 — règle actuelle : premier élément rencontré dans `registrations` gagne (`>` strict, pas `>=`).
Déterministe pour un ordre de liste donné, mais cet ordre n'est pas garanti stable. Prouvé empiriquement par
le nouveau test `test_exact_score_tie_is_broken_by_list_order_not_by_any_other_signal`.

### D4. Poids et seuils
Pas de "scoring pondéré" multi-facteurs au sens strict dans le moteur d'identité — `match_sources` utilise un
seul signal (similarité de nom, max de deux métriques rapidfuzz) plus une règle prioritaire (email exact).
Les seuils (`SCORE_CERTAIN_THRESHOLD=95`, `SCORE_PROBABLE_THRESHOLD=75`, `AMBIGUOUS_MIN=78`,
`AMBIGUOUS_MAX=93`) sont codés en dur, non exposés à un quelconque réglage utilisateur — donc pas de surface
"poids négatif/extrême" à tester côté utilisateur. Le VRAI scoring pondéré multi-facteurs du projet est ailleurs :
`master_list_service.py:555` (score de qualité des données, 6 dimensions pondérées à 0.25/0.15/0.2/0.15/0.1/0.15,
somme = 1.0, cohérent) — un système différent, sans rapport avec l'identité des participants, donc hors du
principe de validation humaine (aucune décision sur les participants n'en découle).

---

## E. Recommandations à moyen terme

1. **Trancher PROP-001 en priorité** — c'est la seule vraie violation du principe non-négociable trouvée cette nuit.
2. **Appliquer PROP-002** une fois validé — correctif mécanique (tri explicite), risque très faible.
3. **Environnement Python dédié** : ce backend n'a pas de venv isolé ni de fichier de lock (`requirements.txt`
   n'utilise que des `>=`) — un `pip freeze` reproductible (ou `poetry`/`uv`) éviterait de refaire cette
   vérification de dépendances à l'aveugle la prochaine fois, et éviterait qu'un `pip install` futur tire une
   version cassée sans avertissement.
4. **Un peu de ménage cosmétique** : les 45 warnings ESLint et les imports Python inutilisés (B7/B8) — aucune
   urgence, mais un passage `eslint --fix` + suppression des imports morts serait un gain rapide et à faible risque.
5. **`react-hooks/set-state-in-effect`** : décider en équipe si ce pattern (fetch au montage) reste la
   convention du projet ou doit migrer vers un pattern différent — actuellement cohérent mais flaggé par la
   version d'ESLint installée.
6. **OAuth state signing** (B6) reste à faire, mais nécessite un test live, hors de portée d'une session non
   supervisée.

---

## F. Points bloqués / accès manquants

- Aucun accès manquant cette nuit — tout le code nécessaire à l'audit était disponible localement.
- La vérification de dépendances Python a été partiellement gênée par l'absence d'environnement virtuel dédié
  (voir B4/E3) : le scan initial a remonté du bruit provenant d'autres projets installés sur la même machine
  Python globale ; j'ai vérifié manuellement (`pip show --Required-by`) que ces paquets ne font pas partie de
  ce projet avant de les exclure du rapport, mais un venv propre rendrait ce contrôle inutile à l'avenir.
- Je n'ai pas testé la connexion Supabase "down"/timeout en conditions réelles (aurait nécessité de couper un
  accès réseau/service en dur, risque jugé disproportionné pour une vérification déjà couverte par la lecture
  du code — tous les appels critiques sont déjà enveloppés en `try/except` avec dégradation documentée).
