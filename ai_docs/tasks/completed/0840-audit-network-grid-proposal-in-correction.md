---
title: TASK-0840 — siatka sieci jako propozycja w korekcie Reviewera i kolejka plansz z audytu
status: done
last_updated: 2026-10-04
---

# TASK-0840 — siatka sieci jako propozycja w korekcie Reviewera

## Status

`done`

## Goal

Operator poprawia 975 plansz 777 wskazanych przez audyt TASK-0831 w
istniejącym ekranie korekty siatki Reviewera, gdzie siatka `neural_grid`
jest wczytana jako gotowa propozycja do akceptacji albo lekkiej poprawki,
a plansze są podawane kolejno z listy audytu — bez ręcznego oznaczania
„Zła siatka” w Weryfikacji symboli i bez rysowania siatek od zera.

## Context

Audyt TASK-0831 (`ai_docs/quality/SILENT_GRID_AUDIT_777_20261004.md`):
975 plansz z zapisaną siatką przesuniętą albo przekrzywioną (660 werdyktów
operatora, 315 z reguły zbudowanej na jego werdyktach), 237 z nich ma
decyzje symboli (490 komórek). Dane audytu:
`C:\Users\tuszy\Documents\game_predictor_vision_data\silent-grid-audit\777-20261004\`
(`review\correction-worklist.csv`, `review\decisions.json`,
`review\rule-verdicts.json`, `suspects.json`, `network-*.jsonl` z węzłami
sieci per plansza, `cases.json`). Operator zaakceptował 2026-10-04
propozycję siatki sieci w korekcie Reviewera. Masowe oznaczanie „Zła
siatka” w bazie **nie** zostało zatwierdzone — kolejka ma działać bez niego.

## Dependencies / entry conditions

- Gałąź `feat/grid-engine-v3` zawiera niewdrożoną migrację `0140`
  (TASK-0830). Wdrożenie tego zadania nastąpi razem z przejściem `0140`,
  po zakończeniu pracy operatora z symbolami. Zadanie nie dodaje migracji,
  chyba że analiza wykaże, że bez niej się nie da — wtedy stop i opis.
- Istniejąca korekta siatki: ekran Reviewera (kolejka korekty, podgląd,
  zapis rewizji geometrii planszy przez API, symbole w korekcie D-488),
  endpointy `image_grid_reviews` / korekty planszy w API. Zapis korekty
  przechodzi istniejącą ścieżką (bramka kompletności D-484/D-485,
  unieważnienie wycinków i decyzji symboli przy zmianie geometrii).

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Zmiana Reviewera i API (nowe źródło
propozycji, nowa kolejka) przy zapisie danych produkcyjnych przez
istniejącą ścieżkę. Audyt zawieszony decyzją operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/quality/SILENT_GRID_AUDIT_777_20261004.md`
- `ai_docs/tasks/completed/0831-silent-grid-error-audit-777.md`
- `ai_docs/process/DECISION_LOG.md` (D-462, D-484, D-485, D-488)
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md` (allowlista proxy)
- `ai_docs/architecture/API_CONTRACT.md`, `ai_docs/requirements/ADMIN_APP.md`

## Scope

1. **Import listy audytu do API** jako niezmiennego artefaktu: komenda
   (`scripts/…`) wczytuje `correction-worklist.csv` i węzły sieci dla tych
   plansz z danych audytu, weryfikuje je z bieżącą rewizją geometrii
   planszy w bazie (tylko odczyt; plansza zmieniona po audycie = pozycja
   oznaczona „nieaktualna”, bez propozycji) i zapisuje plik propozycji z
   sumą kontrolną w `ARTIFACT_ROOT` (bez nowej tabeli).
2. **Kolejka „Poprawki z audytu siatek”** w Reviewerze (tryb lokalny):
   plansze z pliku w kolejności z listy (najpierw te z decyzjami symboli),
   postęp, pominięcie, przejście dalej; plansza znika z kolejki, gdy jej
   bieżąca rewizja geometrii jest nowsza niż w pliku (czyli została
   poprawiona). Stan kolejki wyliczany, bez zapisu w bazie.
3. **Propozycja sieci w ekranie korekty:** przy otwarciu planszy z tej
   kolejki narożniki/siatka są wstępnie ustawione na siatkę sieci
   (przeliczoną do przestrzeni, w której pracuje edytor); operator widzi
   też obecną (złą) siatkę jako cienki kontur; akceptuje albo poprawia i
   zapisuje istniejącą ścieżką korekty. Zapis oznacza pochodzenie
   (`audit-network-proposal`) w audycie/zdarzeniu, jeżeli istniejący
   kontrakt ma na to miejsce; bez zmiany schematu.
4. **API pionem:** endpointy tylko do odczytu dla kolejki i propozycji;
   OpenAPI, klient, wrapper, test żądania; proxy Reviewera — trasy tylko w
   trybie lokalnym, nie na liście tras udostępnianych przez tunel, chyba
   że model zagrożeń to dopuszcza (opisz decyzję).
5. Testy (API, Reviewer, test interakcji ekranu), dokumentacja Admin/
   Reviewer, wpis w przewodniku operatora.

## Out of scope

- Masowe oznaczanie „Zła siatka” w bazie, migracje, zmiany ścieżki zapisu
  geometrii, automatyczne poprawianie bez operatora, inne gry.

## Acceptance criteria

- [x] Kolejka pokazuje plansze z listy audytu, pomija poprawione i
      nieaktualne, działa po restarcie.
- [x] Ekran korekty otwiera się z siatką sieci jako propozycją; zapis
      idzie istniejącą ścieżką i daje te same skutki co ręczna korekta
      (nowe wycinki, unieważnione decyzje symboli wracają do weryfikacji,
      bramka kompletności).
- [x] Plansza zmieniona po audycie nie dostaje starej propozycji.
- [x] Żadnego zapisu do bazy poza zapisem korekty wykonanym przez
      operatora; brak migracji.
- [x] Kontrakt pionem; trasy w Reviewerze tylko lokalnie (albo uzasadnienie).
- [x] Testy przechodzą; dokumentacja.
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

Najpierw prześledź, jak ekran korekty Reviewera ładuje kontekst planszy
(źródło zdjęcia, bieżąca geometria, przestrzeń współrzędnych, podgląd
komórek) i jak zapisuje rewizję — propozycja ma się wpiąć w te same
struktury. Węzły sieci są w przestrzeni `exif-normalized-rgb-pixels-v1`
zdjęcia źródłowego (jak zapisana geometria). Dla siatki 5 × 3 edytor może
pracować na narożnikach; jeżeli korekta przyjmuje tylko narożniki,
propozycja = cztery narożniki siatki sieci.

## Expected files

- Istniejące: moduły API korekty siatki, `apps/reviewer` (ekran korekty,
  kolejka, proxy), `packages/admin-api-client`.
- Nowe (proponowane): `scripts/import_grid_audit_proposals.py`, moduł API
  `grid_audit_proposals`, testy.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests -q -p no:cacheprovider -k "grid_audit or grid_review or grid_correction"
npm run openapi:generate; npm run openapi:check
npm run test --workspace @game-predictor/reviewer; npm run test:geometry --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
```

## Outcome

### Scalenie i wdrożenie (2026-10-04)

Commit zamknięcia wdrożenia: `v1.7.185` /
`fcc53b06df0526504f31b5c5edcc97bda1d2fe10` (wpis hash po commicie).

Operator zakończył przypisywanie symboli i zatwierdził krok 1 handoffu.
Implementacja: `v1.7.183` / `b7d649952980bb8f7b107eebc50a81e082084b78`.
Scalenie do `v1.1-vision-lab-hybrid-geometry`: `v1.7.184` /
`67e02e8b512eb396e6fbf0f790b8746b12dd70de`.

Reviewer i Admin przebudowane, baza na `0140_grid_engine_profiles`, wszystkie
trzy usługi uruchomione i odpowiadają HTTP 200. Kontrolny `--dry-run` importera
z jawnym `--audit` i `--game-id`: `REPEATABLE READ READ ONLY`, 975 aktualnych
propozycji, zero nieaktualnych; 237 plansz z decyzjami symboli (490 pól).
Artefaktu nie nadpisano ani nie importowano ponownie. Żaden rekord planszy
nie został poprawiony przez agenta.

Odbiór API i przeglądarki: kolejka ma 975 otwartych pozycji, 0 poprawionych,
0 nieaktualnych. Pierwsza plansza 171127 (`p00750`) otwiera się z propozycją
sieci i konturem bieżącej siatki, podglądem 15/15 wycinków oraz podpowiedziami
symboli. Przycisk zapisu jest dostępny, lecz nie użyto go na danych operatora.
Kolejka pozostaje otwarta dla operatora.

Kontrole po scaleniu: API 50/50; interakcje Reviewera 16/16 (obejmują zapis,
utraconą odpowiedź i konflikt rewizji w izolowanym UI); Reviewer 207/207;
Admin 624/624; klient 78/78; typecheck, lint (cztery wcześniejsze ostrzeżenia
Admina), oba buildy i OpenAPI Admina poprawne. Pełnego zestawu PostgreSQL
nie ponawiano. Worker general przywrócono do wcześniejszego stanu.

Kolejka „Poprawki z audytu siatek” w lokalnym Reviewerze
(`http://127.0.0.1:3001/?mode=local&gameId=bfc4f949-5c14-4850-b02a-db99610bcfa5&queue=grid-audit`)
podaje 975 plansz z listy audytu TASK-0831 po jednej, na istniejącym ekranie
korekty, z siatką sieci jako propozycją (żółta siatka z narożnikami) i obecną
siatką jako cienkim czerwonym konturem. Zapis to niezmieniony zapis korekty
planszy (`image-reviews/{id}/geometry-revisions`). Bez migracji, tabel i
zapisów do bazy; stan kolejki jest wyliczany z bieżącej `geometry_revision`
planszy.

Import (wykonany 2026-10-04 09:33 UTC, transakcja `REPEATABLE READ READ ONLY`,
`transaction_read_only = on`, baza na `0139`, generacja magazynu 2): 975
pozycji, 975 `proposal`, 0 `stale`, 0 `board_missing`, 0 `no_network_grid`;
237 plansz z decyzjami symboli (490 pól) — wszystkie z propozycją i na
początku listy; 660 werdyktów operatora, 315 z reguły; klasy: 390
`column_shift`, 344 `row_shift`, 240 `scale_rotation`, 1 `diagonal_shift`.
Artefakt:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-audit-proposals\bfc4f949-5c14-4850-b02a-db99610bcfa5\silent-grid-777-20261004\`
(`proposals.json` 1 714 786 B, SHA-256
`90df51daa981b304167d3ddeddc75ff2ae5b242564dc1dc8dc0227456c479f19`, oraz
`manifest.json`). Odczyt tylko do odczytu po imporcie: 975 pozycji `open`.

Współrzędne: węzły sieci i zapisana geometria są w
`exif-normalized-rgb-pixels-v1` zdjęcia źródłowego. Na 4 planszach (odczyt
tylko do odczytu) narożniki, od których startuje edytor (`latticeBoundsQuad`
/ `quad` pozycji `grid-reviews`), są identyczne z narożnikami zapisu w
audycie. Propozycja = węzły 0, 5, 23, 18 (TL, TR, BR, BL) zaokrąglone do
pikseli. 22 propozycje wychodzą poza zdjęcie (plansze przy krawędzi): dla
planszy bez kwalifikacji `pending_partial` edytor przycina narożniki do
krawędzi i informuje o tym operatora.

Decyzje: trasy `grid-audit-proposals` tylko w trybie lokalnym (poza
allowlistą proxy `/review-api`; lista obejmuje całą grę, a sesja zdalna jeden
import). Pochodzenie `audit-network-proposal` jest w odpowiedzi API, ale nie
w bazie: kontrakt zapisu nie ma na nie miejsca, a zmiana aktora zmieniłaby
klasyfikację poziomu etykiety; ścieżka zapisu bez zmian. `Pomiń na razie`
działa w bieżącej sesji (bez zapisu stanu).

### Changed

- API (nowe): `domain/grid_audit_proposals.py` (stany, parser artefaktu),
  `application/grid_audit_proposals.py` (serwis kolejki, magazyn plików z
  weryfikacją SHA-256), `storage/grid_audit_board_reader.py` (rewizje plansz,
  pozycja w kształcie `grid-reviews`), `schemas/grid_audit_proposals.py`,
  `api/grid_audit_proposals.py`; zmienione `api/router.py`, `main.py`
  (zależność tylko do odczytu z rollbackiem, kody 404/409).
- `scripts/import_grid_audit_proposals.py` (import, `--dry-run`, odmowa
  nadpisania).
- `packages/admin-api-client`: OpenAPI, wygenerowany klient, wrapper
  `listGridAuditProposals` / `getGridAuditProposal`, test żądania.
- Reviewer: nowe `grid-audit-correction-workspace.tsx`,
  `grid-audit-correction-state.ts`; `board-geometry-correction-target.ts`
  (`gridAuditBoardGeometryTarget` na bazie celu planszy zgłoszonej, opcjonalne
  `referenceCorners` / `suggestionNotice` widoku),
  `deferred-board-cell-geometry-editor.tsx` (kontur obecnej siatki, notka),
  `page.tsx` i `reviewer-access-gate.tsx` (tryb `queue=grid-audit`, tylko
  host pętli zwrotnej :3001).
- Testy: `services/api/tests/test_grid_audit_proposals.py`,
  `services/api/tests/integration/test_grid_audit_board_reader_postgres.py`,
  `apps/reviewer/test/grid-audit-correction.test.mjs`,
  `apps/reviewer/test-interactions/grid-audit-correction.test.mjs`; rozszerzone
  `reviewer-proxy-policy.test.mjs`, `local-reviewer-workspace-contract.test.mjs`,
  `packages/admin-api-client/test/client.test.mjs`.

### Verification results

- `pytest services/api/tests -k "grid_audit or grid_review or grid_correction or grid_engine_profiles or openapi"`:
  76 passed, 3 skipped, 1 failed —
  `test_openapi_contract.py::test_grid_review_openapi_is_topology_aware_and_checksum_bound`
  (`KeyError: 'minItems'`) pada tak samo na kopii `HEAD` bez zmian tego
  zadania (wcześniejszy błąd, poza zakresem).
- `test_grid_audit_proposals.py` + `test_image_grid_review_api.py`: 39 passed.
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, baza
  `game_predictor_task0840_<hex>_test`, usunięta po teście):
  `test_grid_audit_board_reader_postgres.py` 1 passed.
- `ruff check`, `ruff format --check`, `mypy --strict` nowych i zmienionych
  modułów API, testów i skryptu: czyste.
- `npm run openapi:generate`; `npm run openapi:check`: kod 0.
- Reviewer: `test` 207/207, `test:geometry` 15/15, `typecheck`, `lint`:
  czyste; prettier zmienionych plików czysty. Admin `typecheck` czysty.
  `admin-api-client`: `client.test.mjs` 71/71, `tsc --noEmit` czysty.
- Baza deweloperska: wyłącznie odczyty w transakcjach `READ ONLY` (dry-run,
  import, kontrola stanów i współrzędnych). Brak zapisów i migracji.

### Not completed

- Pierwszy rzeczywisty zapis korekty pozostaje do odbioru podczas pracy
  operatora. Testy interakcji sprawdzają zapis bez zmiany jego danych.
- Nie ponawiano pełnych testów PostgreSQL ani restartu Windows.
- Wdrożenie i odbiór ekranu na żywym API `0140` ukończono.
- Pochodzenie `audit-network-proposal` nie jest zapisywane w bazie (patrz
  decyzje).

### Documentation updates

- `ai_docs/architecture/API_CONTRACT.md` (trasy, artefakt, stany),
  `ai_docs/requirements/ADMIN_APP.md` (kolejka w Reviewerze),
  `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md` (decyzja: tylko lokalnie),
  `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` (import, wdrożenie, praca
  operatora), `ai_docs/quality/SILENT_GRID_AUDIT_777_20261004.md` (wskazanie
  kolejki).

### Recommended next task

- Po przejściu `0140`: przegląd pierwszych plansz na żywo (najpierw 237 z
  decyzjami symboli); ewentualnie link do kolejki w Adminie.
