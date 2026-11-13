---
title: TASK-1201 — Obrysy symboli z zatwierdzonych siatek
status: done
last_updated: 2026-11-13
---

# TASK-1201 — Obrysy symboli z zatwierdzonych siatek

## Status

`done`

## Goal

Operator zatwierdza obrysy symboli masowo w osobnym oknie Admina, w którym obrysem
jest pole jego zatwierdzonej siatki, zamiast rysować 15 obrysów ręcznie na planszę.

## Context

Ręczne „Etykiety zawartości zdjęć” wymagały ok. 10 minut na planszę (4 rogi dla każdego
z 15 pól). Operator rysuje siatkę na granicach symboli i sprawdza, czy symbole się w niej
mieszczą, więc pola zatwierdzonej siatki są już obrysami. Prototyp poza aplikacją
(`artifacts/symbol-outlines-20261113`) dał 210 zatwierdzonych plansz Mumie A2 (210 × 200).
Operator: „dodaj ten ekran żeby się pokazywał zamiast »Etykiet zawartości zdjęć« a tamten
oznacz do usunięcia”, „otwiera się w nowym oknie”, „jak klikam cały kafelek to się
zaznacza”, „usuń na samym końcu jak starczy Ci tokenów”. Decyzja: D-608.

## Dependencies / entry conditions

- Istniejący zapis `writeGridCellContentReference` (`origin=manual`, `humanApproval=true`)
  i zasada akceptacji geometrii z D-606.
- Fakt: 596 plansz Mumie A2 ma zatwierdzoną przez człowieka, pełną siatkę 24 punktów.

## Recommended execution

Claude Opus 5.5, reasoning medium (bieżąca sesja z pełnym kontekstem prototypu); bez
dodatkowego review (polecenie operatora „wykonuj wszystkie zadania”, brak planu z audytem).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- [D-606](../../process/decisions/DECISION_LOG_2026.md#d-606--domyślny-zakres-uczenia-korekt-importy-z-etykietami-i-kohortami)
- [D-608](../../process/decisions/DECISION_LOG_2026.md#d-608--obrysy-symboli-z-zatwierdzonych-siatek)
- `ai_docs/architecture/API_CONTRACT.md`, `ai_docs/requirements/ADMIN_APP.md`

## Scope

- GET `content-outline-proposals` (odczyt, stronicowanie, widoki todo/approved/all).
- OpenAPI, wygenerowany klient, wrapper i test żądania.
- Okno Admina `/symbol-outlines?gameId=` z kafelkami, zaznaczaniem kliknięciem i
  masowym zatwierdzaniem; przycisk w Geometrii V3 zamiast „Etykiety zawartości zdjęć”.

## Out of scope

- Usunięcie kodu starego edytora zwykłych etykiet (osobny task).
- Zmiany zapisu etykiet, treningu, ślepego pomiaru i migracje.

## Acceptance criteria

- [x] Lista zwraca tylko plansze z ludzką akceptacją bieżącej geometrii, pełną siatką
  i bieżącym źródłem; obrysy to 15 pól siatki w kolejności planszy.
- [x] Siatka nieużywalna daje `cells=null`, nigdy częściową propozycję.
- [x] Zatwierdzenie wysyła istniejący zapis z `expectedRevision` z listy.
- [x] Okno otwiera się w nowej karcie; kliknięcie kafelka zaznacza, lupa powiększa.
- [x] Zaznaczenie obejmuje plansze z wielu stron.

## Expected files

- Nowe: `services/api/src/game_predictor_api/domain/grid_content_outline_proposals.py`
  (`outline_proposal_cells`), `storage/grid_content_outline_proposals.py`
  (`list_outline_proposals`), `apps/admin/src/app/symbol-outlines/page.tsx`,
  `apps/admin/src/features/model-quality/symbol-outline-{review.tsx,state.ts,review.css}`.
- Zmienione: router `api/grid_cell_content.py`, schematy `ContentOutlineProposal*`,
  protokół `ContentRepository`, repozytorium, `packages/admin-api-client`
  (`listGridContentOutlineProposals`, `imageGeometryCompletenessSourceUrl`),
  `grid-model-workspace.tsx`, `globals.css`.

## Test cases

- Pola siatki → 15 widocznych obrysów, przycięcie do kadru, brak częściowej propozycji.
- Propozycja jest poprawnym zatwierdzonym `ContentWriteCommand`.
- HTTP: domyślne todo/48/0, walidacja `view`, `limit` 1–60, `offset` ≥ 0, no-store.
- Admin: view box, komenda zatwierdzenia, blokada zatwierdzonych i nieużywalnych,
  przełączanie i zaznaczanie strony, adres okna.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_content_outline_proposals.py
npm run test --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

## Risks / open questions

- Obrys to pole siatki, więc symbol wystający poza pole nie zostanie wykryty; operator
  zatwierdza tylko plansze, na których obrysy obejmują całe symbole.

## Outcome

Commit: v1.7.628 (hash dopisuje kolejny commit).

### Changed

- Backend: czysta funkcja `outline_proposal_cells`, zapytanie `list_outline_proposals`
  (kandydaci = reguła akceptacji D-606, bez nieużywalnych pól, bez wycofanych i
  usuniętych źródeł; najnowsza rewizja etykiety przez `LATERAL`), route GET
  `content-outline-proposals`, schematy `ContentOutlineProposal*`.
- Klient: OpenAPI, wygenerowany klient, `listGridContentOutlineProposals`,
  `imageGeometryCompletenessSourceUrl` (istniejący GET całego zdjęcia gry).
- Admin: okno `/symbol-outlines`, przycisk „Obrysy symboli z siatek” w Geometrii V3
  zamiast „Etykiety zawartości zdjęć”; stary edytor zostaje w kodzie do usunięcia.

### Verification results

- `pytest test_grid_content_outline_proposals.py test_grid_cell_content_requests.py
  test_grid_cell_content.py` (kod gałęzi, bez editable findera): 25 passed.
- `admin-api-client` test: 168/168; tsc PASS.
- Admin `node --test test/*.test.mjs`: 864/864; `tsc` z klientem gałęzi PASS; eslint
  zmienionych plików PASS.
- ruff check/format zmienionych plików PASS; mypy zmienionych modułów bez nowych błędów
  (14 zastanych błędów w niezwiązanych plikach, m.in. `source_purge`).
- Odczyt na bazie operatora (transakcja READ ONLY, kod gałęzi): Mumie A2 todo 386 /
  approved 210 (razem 596), 48 pozycji na stronę, 0 nieużywalnych, ~0,3 s.

### Not completed

- Okna nie sprawdzono w przeglądarce: API na :8000 działa z `main` bez nowego endpointu,
  a uruchamianie usług należy do operatora. Weryfikacja po scaleniu i restarcie API/Admin.
- `next build` nieuruchomiony (typecheck i `next typegen` PASS).

### Documentation updates

- D-608 (pełny wpis i indeks), `API_CONTRACT.md`, `ADMIN_APP.md`, `CURRENT_STATE.md`.

### Recommended next task

- Usunięcie starego edytora zwykłych etykiet zawartości (decyzja D-608).
