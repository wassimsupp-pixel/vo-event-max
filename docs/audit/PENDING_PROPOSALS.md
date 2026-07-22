# Propositions en attente de validation humaine

Ce fichier liste UNIQUEMENT les changements touchant :
- la logique métier du moteur de matching (scoring, seuils, tie-breaking, auto-décision),
- la structure de la base de données (schéma, migrations, contraintes).

Rien ici n'est appliqué au code. Chaque entrée décrit le problème, l'impact, et un correctif proposé,
pour validation humaine avant toute implémentation.

---

## PROP-001 [CRITIQUE] — L'IA fusionne des participants de façon autonome, sans validation humaine

**Statut : violation confirmée du principe non-négociable énoncé dans le brief d'audit.**

### Où
- `apps/api/services/consolidation_service.py`, fonction `detect_ambiguous_duplicate_participants`, ligne **2854** :
  ```python
  if verdict["decision"] == "fusionner" and verdict["confidence"] >= 75:
      if _merge_participant_into(supabase, loser["id"], winner["id"]):
          merged_ids.add(loser["id"])
          auto_merged += 1
          ...  # log_change avec reason="ai_arbitration" — un journal, pas une porte d'approbation
  ```
- `verdict` vient de `apps/api/services/arbitration_service.py::arbitrate_pair()` (ligne 56), qui appelle
  un LLM (`ai_service.ai_json`) pour juger si deux fiches participant représentent la même personne.
- `_merge_participant_into` (`consolidation_service.py` ligne 2626) est **destructif et irréversible** :
  il réassigne tous les vols/hôtels/transferts/activités du "perdant" vers le "gagnant" puis
  **supprime définitivement** la fiche du perdant (`DELETE FROM participants`). Aucun mécanisme
  d'annulation dans l'UI.

### Ce qui se passe concrètement
Cette fonction tourne automatiquement à **chaque consolidation** (étape 6f de `run_consolidation`).
Pour chaque paire de participants dont le nom est "ambigu" (score rapidfuzz 78-93), le LLM est appelé.
Si le LLM répond `"fusionner"` avec une confiance auto-déclarée ≥ 75 %, la fusion s'exécute
**immédiatement, sans qu'aucun humain n'ait rien vu ni validé**. Le `log_change` qui suit n'est qu'une
trace d'audit après coup (visible dans l'Historique des modifications de l'export) — ce n'est pas une
porte d'approbation.

Le chemin **humain** existe bel et bien (`match_candidates` + dashboard "Fusions à vérifier", résolu via
`arbitration_service.resolve_candidate`), mais il n'est emprunté QUE pour les verdicts `"incertain"` ou
`"fusionner"` avec confiance < 75. Le brief indique explicitement : *"l'IA ne décide jamais de manière
autonome des résultats sur les données des participants"* — ce chemin à confiance ≥ 75 % est exactement
ce cas de figure.

### Impact
- Un faux positif du LLM (nom proche, entreprise similaire, mais réellement deux personnes différentes)
  entraîne la **suppression silencieuse et permanente** d'une fiche participant réelle, avec fusion de
  ses vols/hôtel/transferts/activités dans le mauvais profil.
- Aucune notification, aucun écran de confirmation, aucune option d'annulation dans le produit actuel.
- La seule façon de s'en apercevoir est de lire l'Historique des modifications de l'export Excel et de
  reconnaître `reason="ai_arbitration"` — peu probable en usage normal.
- Le confidence score est **auto-déclaré par le LLM lui-même** (`arbitration_service.py` ligne 92-96,
  aucune calibration externe) — rien ne garantit qu'une confiance de 75 corresponde réellement à un taux
  d'erreur acceptable.
- Point positif partiel : les appels LLM utilisent `temperature: 0` (`ai_service.py` lignes 112, 146),
  ce qui rend le comportement quasi-déterministe en pratique (mais un LLM à température 0 n'est pas
  garanti bit-à-bit reproductible d'un run à l'autre selon le fournisseur — nuance à noter, pas la
  faille principale).

### Correctif proposé (à valider avant implémentation)
Supprimer la branche d'auto-fusion : **tout** verdict `"fusionner"` — quel que soit le niveau de
confiance — doit passer par `ARB.create_candidate(...)` (file d'attente `match_candidates`) au lieu
d'appeler `_merge_participant_into` directement. Concrètement :

```python
if verdict["decision"] == "fusionner" and verdict["confidence"] >= 75:
    if _merge_participant_into(...):
        ...
elif verdict["decision"] == "separer":
    continue
else:
    if ARB.create_candidate(...):
        candidates += 1
```
devient :
```python
if verdict["decision"] == "separer":
    continue
else:  # "fusionner" (quelle que soit la confiance) ou "incertain" -> revue humaine obligatoire
    if ARB.create_candidate(supabase, event_id, run_id, loser, winner, score, verdict):
        candidates += 1
```

Effet secondaire à anticiper : le volume de la file "Fusions à vérifier" augmentera (les cas
haute-confiance qui étaient auto-fusionnés apparaîtront désormais dans le dashboard). C'est le
comportement recherché — un humain doit voir passer CHAQUE fusion, même évidente pour l'IA. Le
`ai_confidence` déjà stocké sur `match_candidates` (ligne 153 de `arbitration_service.py`) permet de
trier/prioriser la file par confiance décroissante côté UI si le volume devient gênant.

**Je n'ai PAS appliqué ce correctif** — conformément à la consigne, il touche la logique métier du
moteur de matching et attend validation humaine explicite avant implémentation.

---

## PROP-002 [MAJEUR] — **APPLIQUÉ le 2026-07-22, validation explicite reçue en chat.** Ordre non-déterministe des enregistrements alimentant le matcher : les égalités de score pouvaient être tranchées différemment d'un run à l'autre

### Où
`apps/api/services/consolidation_service.py`, `run_consolidation` étape 3, lignes **1057-1070** :
```python
for ci in range(0, len(primary_ids), 200):
    chunk = primary_ids[ci:ci + 200]
    sr_resp = supabase.table("source_records").select("id, normalized_data").in_("id", chunk).execute()
    for sr in sr_resp.data or []:
        pr = ParticipantRecord(sr["id"], sr.get("normalized_data") or {})
        if source_type in ("registration", "masterfile"):
            registrations.append(pr)
        ...
```

### Problème
`WHERE id IN (...)` (via PostgREST `.in_()`) ne garantit **aucun ordre de retour** correspondant à
l'ordre de la liste `chunk` — Postgres renvoie les lignes selon le plan d'exécution qu'il choisit, pas
selon l'ordre du IN-list. `primary_ids` lui-même vient du retour d'un `.upsert()` (ligne ~298 de
`mapping_service.py`, `parse_and_insert_source_records`), dont l'ordre de retour n'est pas non plus
garanti égal à l'ordre des lignes du fichier source.

`registrations` (et `fcm_records`) sont donc construits dans un ordre qui peut varier d'une
consolidation à l'autre, **pour les mêmes données sources**.

### Pourquoi ça affecte le moteur de matching
Dans `match_sources` (même fichier, ligne 260-265) :
```python
for reg in registrations:
    name_score = _compute_name_score(fcm, reg)
    if name_score > best_score:   # strictement supérieur -> premier rencontré gagne en cas d'égalité
        best_score = name_score
        best_reg = reg
```
En cas d'**égalité parfaite** de score entre deux fiches d'inscription pour un même enregistrement FCM
(ex. deux personnes différentes portant le même nom complet — cas réel et plausible sur un grand
événement), c'est la première rencontrée dans `registrations` qui l'emporte. Si l'ordre de
`registrations` n'est pas stable, **la même situation peut être résolue différemment selon le run** —
directement contraire à l'exigence "même input → même output, toujours" du brief d'audit.

### Correctif proposé
Trier explicitement les lignes récupérées avant de les ajouter à `registrations`/`fcm_records`, sur une
clé stable — par exemple par `id` du `source_record`, ou mieux, préserver l'ordre de `chunk` (l'ordre
d'upsert lui-même) en réordonnant `sr_resp.data` selon la position de chaque ligne dans `chunk` après
récupération. Exemple minimal (ne change ni le scoring ni les seuils, seulement l'ordre d'entrée) :
```python
order = {id_: i for i, id_ in enumerate(chunk)}
for sr in sorted(sr_resp.data or [], key=lambda r: order.get(r["id"], 0)):
    ...
```

**Statut : appliqué.** Correctif implémenté tel que décrit ci-dessus (`consolidation_service.py:1057-1073`),
après validation humaine explicite reçue en chat le 2026-07-22 (le correctif ne touche à aucun poids ni
seuil, uniquement à l'ordre d'entrée). Build frontend et 113 tests backend vérifiés au vert après
application. PROP-001 reste, lui, en attente — non validé, non appliqué.
