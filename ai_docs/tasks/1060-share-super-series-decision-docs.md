# TASK-1060 — Decyzja D-564 i dokumentacja widoku serii dla odbiorcy linku

## Status

`todo`

## Goal

D-564 zapisana w dzienniku decyzji, a wymagania, kontrakt API, model danych i
model zagrożeń opisują trasy serii udostępnienia, `seriesId` w markerach,
aktora sesji i modal odbiorcy.

## Context

Plan `ai_docs/delivery/SHARE_SUPER_GAME_SERIES_EXECUTION_PLAN_20261018.md`,
sekcje 3–4. Decyzja operatora z czatu (2026-10-18) rozszerza D-535 i D-548.

## Dependencies / entry conditions

- Treść decyzji ustalona w planie; można wykonać równolegle z kodem.
- Fakt: indeks `DECISION_LOG.md` ma dokładnie 30 wierszy (najnowsza D-563);
  wiersz D-534 przechodzi na początek `decisions/DECISION_INDEX_ARCHIVE.md`.

## Recommended execution

`claude-fable-5-1` / `medium` (warunkowo). Bez audytu.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`, `ai_docs/README.md`
  („Reguła aktualizacji”)
- `ai_docs/process/DECISION_LOG.md` (reguły nagłówka)
- D-535, D-536, D-537, D-548 (panel) w `decisions/DECISION_LOG_2026.md`

## Scope

- `decisions/DECISION_LOG_2026.md`: wpis `## D-564 — Super symbol serii
  definiowany także przez odbiorcę linku udostępniania` na początku.
- `DECISION_LOG.md`: wiersz D-564 na górze; D-534 do archiwum indeksu.
- `requirements/ADMIN_APP.md`: „Udostępnianie wyszukiwania online” (modal
  serii odbiorcy) i „Sekcja „Supergry”” (wspólny komponent, `definedBy`).
- `architecture/API_CONTRACT.md`: „Publiczna powierzchnia udostępniania”
  (trasy, modele, `seriesId`, `superGameTriggerCount`, kody błędów, `PUT`)
  i „Serie supergry” (aktor).
- `security/REMOTE_REVIEWER_THREAT_MODEL.md`: allowlista + `PUT`, `seriesId`
  jako dopuszczony identyfikator, aktor audytu.
- `architecture/DATA_MODEL.md`: `defined_by` = `local-admin` albo
  `board-search-share:<session_id>`.

## Out of scope

- Kod; `CODE_MAP` (regeneruje TASK-1058 i TASK-1059).

## Acceptance criteria

- [ ] `npm run docs:check` zielone (30 wierszy indeksu, linki kotwic, budżety).
- [ ] Każdy z pięciu dokumentów opisuje nowy stan w sekcji właścicielskiej,
      bez kopiowania pełnej reguły.

## Expected files

- `ai_docs/process/decisions/DECISION_LOG_2026.md`,
  `ai_docs/process/DECISION_LOG.md`,
  `ai_docs/process/decisions/DECISION_INDEX_ARCHIVE.md`,
  `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/architecture/API_CONTRACT.md`,
  `ai_docs/architecture/DATA_MODEL.md`,
  `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`.

## Verification

```powershell
# D:\game_predicotr, timeout 120 s
npm run docs:check
npm run format:check
```

## Risks / open questions

- Nagłówek archiwum indeksu może wymagać aktualizacji zakresu numerów.

## Outcome

Wypełnia agent po pracy.
