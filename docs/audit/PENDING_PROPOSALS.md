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
