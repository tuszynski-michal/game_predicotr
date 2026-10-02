# TASK-0728 — Migracja danych do reguł D-462: preview i apply

## Status

done

## Goal

Skrypt `preview` pokazuje dokładny, niezmienny manifest zmian danych gry
(ponowna weryfikacja akceptacji innych pikseli, ponowne otwarcie plansz
rozstrzygniętych na takich akceptacjach, domknięcie plansz z komórek, odświeżenie
nieaktualnych dokumentów wyszukiwania), a `apply` wykonuje dokładnie ten
manifest, idempotentnie i bez żadnej nowej weryfikacji komórki.

## Context

D-462 i plan `ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`
(T8, decyzja P2). Etapy A i B zmieniły reguły odczytu i zapisu, ale dane
zapisane wcześniej zostały: akceptacje innych pikseli (R10) nadal mają
`review_state = approved`, dokumenty wyszukiwania plansz z decyzjami człowieka
powstały przed nakładką komórek (T2), a plansze z kompletem dowodów mogły
czekać na zatwierdzenie geometrii (T3). Operator zlecił etap C z zatrzymaniem
po podglądzie (2026-09-29): `apply` na żywych danych wymaga osobnej zgody.

Odczyt tylko do odczytu 2026-09-29 (gra `777`, schemat `game_data_v2`):
500 023 plansze `pending`, 3 `accepted`; komórki inne niż czysta predykcja
modelu na ~37,7 tys. planszach; 456 akceptacji innych pikseli — 419 komórek
na 110 planszach `pending` i 37 komórek na 3 planszach `accepted`; żadna
plansza `pending` nie ma 15/15 zatwierdzonych komórek o bieżących pikselach.

## Dependencies / entry conditions

- TASK-0722–0727 done (reguły odczytu R10, nakładka projekcji, domknięcie z
  komórek, recrop R6, kolejka i ekran korekty).
- Projekcja komórek gry gotowa (`image_symbol_review_state.status = ready`);
  inaczej preview i apply kończą się błędem, bez zapisu.
- Bez DDL: akcja zdarzenia komórki to istniejące `geometry_invalidated`,
  powód ponownego otwarcia jest wartością JSON zdarzenia planszy.

## Recommended execution

claude-opus-5-5, high — operacja na żywych danych z preview i zgodą. Audyt:
claude-opus-5-5, high (subagent, poziom warunkowy). Eskalacja: rozbieżność
preview ≠ apply albo jakakolwiek nowa weryfikacja zatrzymuje apply.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` D-462
- `ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`

## Scope

- Czysta domena planu jednej planszy i manifestu (checksum, walidacja).
- Repozytorium migracji: odczyt kandydatów keysetem, plan planszy bez blokad
  (preview) i pod blokadą (apply), wykonanie planu jednej planszy.
- Publiczna metoda projekcji wyszukiwania: czy zapisany kandydat różni się od
  wyliczonego z bieżących danych (bez zapisu).
- Skrypt `preview` / `apply` z niezmiennym manifestem i raportem apply.
- Testy domeny i opt-in test PostgreSQL.
- Uruchomienie `preview` na żywej grze `777` (tylko odczyt).

## Out of scope

- Uruchomienie `apply` na żywych danych (osobna zgoda operatora po preview).
- Plansze bez żadnej komórki innej niż czysta predykcja modelu (ich dokument
  nie zależy od D-462).
- Ryzyko A4 (`synchronize_after_board_reopened`), zdalny Reviewer, DDL,
  usuwanie historii, trening, kalibracja.

## Acceptance criteria

- [x] `preview` działa w transakcji `REPEATABLE READ READ ONLY`, zapisuje
      niezmienny manifest z `previewSha256` i nie nadpisuje istniejącego pliku.
- [x] Manifest wymienia każdą planszę z co najmniej jedną akcją: `reopen`,
      `recheckCellIndices`, `close`, `refreshProjection`, wraz z odciskiem
      stanu planszy; liczniki są sumą pozycji.
- [x] `apply` wymaga manifestu i jego `previewSha256`, działa planszami (jedna
      transakcja na planszę), ponownie wylicza plan pod blokadą i wykonuje go
      tylko przy zgodności z manifestem; plan pusty = `already_applied`,
      inny = `drift` bez zapisu.
- [x] Żadna komórka nie przechodzi do `approved`; liczba zatwierdzonych
      komórek planszy maleje dokładnie o `recheckCellIndices`.
- [x] Powtórny `apply` tego samego manifestu nie zmienia danych.
- [x] Testy domeny i opt-in PostgreSQL przechodzą; preview na grze `777`
      wykonany, wynik w `Outcome`.

## Technical notes

Kandydaci: plansze `image_review_items.status ∈ {pending, accepted,
corrected}` gry, które mają komórkę inną niż czysta predykcja modelu
(`review_state <> 'pending'` ∨ `assignment_source <> 'model'` ∨
`quality_issue IS NOT NULL` ∨ `source_available IS false`). Keyset
`(sequence_number, id)`, strony po 500.

Plan jednej planszy (czysta funkcja, wejście: status, kompletność, sekwencja,
komórki bieżącej rewizji, wynik porównania projekcji):

| Warunek | Akcja |
|---|---|
| komórka `approved` z tożsamością pikseli różną od bieżącej (R10, `symbol_cell_approval_pixels_changed`) | `recheckCellIndices` += indeks |
| status `accepted`/`corrected` i niepusty recheck | `reopen = true` |
| status `pending` (po recheck), nie `pending_partial`, `derive_symbol_cell_board_resolution` z komórkami po recheck ≠ `None` | `close = accepted/corrected` |
| zapisany kandydat projekcji ≠ wyliczony z bieżących danych | `refreshProjection = true` |

Recheck nie zmienia dokumentu wyszukiwania (R10 jest już regułą odczytu
projekcji, a czyszczona flaga `blurry` nie wpływa na wyszukiwanie), więc
porównanie projekcji w preview odpowiada stanowi po apply; apply i tak
zawsze synchronizuje projekcję planszy, a domknięcie i ponowne otwarcie
robią to także w swojej ścieżce. `closeAction` to akcja wyprowadzona z
komórek przed zamianą ACCEPTED→CORRECTED przy innej sugerowanej sekwencji.

Odcisk planszy: SHA-256 z `status`, `resolution_revision`,
`geometry_revision` i posortowanych `(cell_index, revision, review_state,
crop_checksum_sha256, rendered_pixel_checksum_sha256)`.

Apply jednej planszy (jedna transakcja, blokady sekwencji jak w mutacjach):
1. plan pod blokadą; porównanie z manifestem (akcje i odcisk);
2. `reopen` → `SqlAlchemyOperationalImageReviewRepository.reopen_for_symbol_cell_issue`
   (`reason = approval_pixels_changed`);
3. recheck każdej komórki: `review_state = pending`, etykieta i źródło
   człowieka zostają jako podpowiedź, kolumny `approved_*` zostają jako
   historia, flaga `blurry` (opis zatwierdzonych pikseli) jest czyszczona jak
   w recropie, weryfikacja V2 i liczniki przeliczone, `revision + 1`,
   zdarzenie `geometry_invalidated` aktora `cell-level-migration`;
4. `SymbolCellReviewWriteThroughCoordinator.synchronize_board_from_cells`
   (domknięcie, gdy komplet dowodów);
5. `SqlAlchemyBoardSearchProjectionRepository.sync_review_item`;
6. niezmiennik: liczba `approved` po = przed − recheck; inaczej wyjątek i
   rollback planszy (`CELL_MIGRATION_NEW_VERIFICATION`).

Błędy: brak gry lub niegotowa projekcja komórek — zatrzymanie przed
jakimkolwiek zapisem; dryf jednej planszy — pozycja `drift` w raporcie,
kolejne plansze kontynuowane; błąd programistyczny/infrastruktury — przerwanie
z raportem częściowym (wykonane plansze pozostają, ponowny apply je pomija
jako `already_applied`).

## Expected files

- Nowe (proponowane): `services/api/src/game_predictor_api/domain/cell_level_verification_migration.py`,
  `services/api/src/game_predictor_api/storage/cell_level_verification_migration_repository.py`,
  `scripts/migrate_cell_level_verification.py`,
  `services/api/tests/test_cell_level_verification_migration_domain.py`,
  `services/api/tests/test_cell_level_verification_migration_script.py`,
  `services/api/tests/integration/test_cell_level_verification_migration.py`.
- Istniejące: `storage/board_search_projection_repository.py`
  (`SqlAlchemyBoardSearchProjectionRepository.stale_review_item_ids`, nowa
  metoda tylko do odczytu).

## Test cases

- Domena: akceptacja innych pikseli → recheck; akceptacja bez tożsamości
  pikseli → brak akcji; `accepted` z recheck → reopen; komplet dowodów →
  close; `pending_partial` → nigdy close; checksum manifestu stabilny i
  zmienia się przy zmianie pozycji.
- PostgreSQL: plansza z nieaktualną akceptacją, plansza `accepted` z taką
  akceptacją, plansza z nieaktualnym dokumentem, plansza z 15/15 bez
  zatwierdzenia geometrii, plansza czystego modelu (poza manifestem);
  preview = apply; drugi apply = `already_applied`; zmiana komórki po preview
  = `drift`; zero nowych weryfikacji.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_cell_level_verification_migration_domain.py services/api/tests/test_cell_level_verification_migration_script.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_cell_level_verification_migration.py -q
.\.venv\Scripts\python.exe -m ruff check services/api scripts
.\.venv\Scripts\python.exe scripts/migrate_cell_level_verification.py preview --game-id bfc4f949-5c14-4850-b02a-db99610bcfa5 --output artifacts/cell-level-migration/preview-777.json
```

Każdy krok z timeoutem ≤ 600 s; preview tylko do odczytu.

## Risks / open questions

- Ponowne otwarcie 3 plansz `accepted` usuwa je z layoutu kanonicznego i
  stagingu do czasu ponownej weryfikacji komórek — widoczne w preview.
- Skala preview (~37,7 tys. plansz) — strony po 500, jedna transakcja odczytu.

## Outcome

Stan: preview wykonany 2026-09-29; `apply` na grze `777` wykonany po
osobnej zgodzie operatora (2026-09-29/30), bez dryfu i błędów.

### Changed

- Domena `cell_level_verification_migration.py`: plan planszy
  (`plan_board_migration`), odcisk stanu (`board_fingerprint`), manifest z
  `previewSha256` (bez `generatedAt`) i jego walidacja.
- Repozytorium `cell_level_verification_migration_repository.py`:
  kandydaci (plansze z komórką inną niż czysta predykcja modelu), plan
  bez blokad (preview) i pod blokadą (apply), `apply_board` z niezmiennikiem
  „zero nowych weryfikacji” (`CellLevelMigrationInvariantError` zatrzymuje
  cały przebieg).
- `SymbolCellReviewWriteThroughCoordinator.recheck_changed_pixel_approvals`:
  akceptacja innych pikseli wraca do `pending` z etykietą człowieka jako
  podpowiedzią, kolumny `approved_*` zostają jako historia, liczniki,
  weryfikacja V2, zdarzenie `geometry_invalidated`, rewizja katalogu.
  `assess_cell_level_board` odzwierciedla `synchronize_board_from_cells`
  bez blokad i zapisów.
- `SqlAlchemyBoardSearchProjectionRepository.stale_review_item_ids`: odczyt
  porównujący zapisany kandydat i posiadany dokument sekwencji z wyliczonymi.
- Skrypt `scripts/migrate_cell_level_verification.py` (`preview`, `apply`).

### Verification results

- Testy domeny: 8 passed; testy skryptu na atrapach bazy: 5 passed
  (niezmienny preview, zły checksum, istniejący raport, porcje
  `--after-review-item-id`/`--limit`, kontynuacja po `failed`, zatrzymanie
  na niezmienniku z raportem częściowym).
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`):
  `test_cell_level_verification_migration.py` 1 passed (plansza z
  akceptacją innych pikseli, plansza `virtual_source` z inną sumą renderu
  przy tej samej sumie cropa, plansza `accepted` z taką akceptacją → reopen,
  15/15 bez zatwierdzenia geometrii → close, nieaktualny dokument → refresh,
  plansza czystego modelu poza manifestem; preview bez zapisu, drift po
  decyzji operatora, powtórny apply = `already_applied`, liczba akceptacji
  i licznik projekcji maleją wyłącznie o recheck, rośnie rewizja katalogu,
  weryfikacja V2 `requires_review`, wymuszone naruszenie niezmiennika
  zatrzymuje apply z rollbackiem); razem z
  `test_verified_cell_search_projection.py` 5 passed.
- Testy API `symbol_review`/`board_search`/`cell_level`/`image_review`:
  264 passed, 5 failed — 4 z listy porażek HEAD i 1 z niezacommitowanej
  zmiany limitu spinów operatora.
- Czysty worktree tego commitu (HEAD + wyłącznie hunki zadania): ruff PASS,
  testy domeny i skryptu 13 passed, PostgreSQL 5 passed, testy API
  `symbol_review`/`board_search`/`image_review` 257 passed i 4 porażki z
  listy HEAD.
- Ruff PASS; mypy: nowe pliki bez błędów (29 wcześniejszych błędów w
  plikach poza zadaniem).
- Preview na żywej grze `777` (`REPEATABLE READ READ ONLY`, 504 s):
  `artifacts/cell-level-migration/preview-777.json` (13 MB),
  `previewSha256 = dca87df2433f1772d335515a42d80791604fc985dee21142ecc2eb79626b5e78`.
  Przeskanowano 37 894 plansze; akcje na 37 782: recheck 456 komórek na
  113 planszach (110 `pending`, 3 `accepted` → reopen: sekwencje 81, 104,
  106), 0 domknięć (żadna plansza nie ma kompletu dowodów), odświeżenie
  37 779 dokumentów wyszukiwania. Próbka 400 dokumentów: zapisane kandydaty
  mają alternatywy modelu dla zweryfikowanych komórek (399/400), inny symbol
  główny (207/400), nieaktualną sumę kontrolną planszy (84/400); dokumenty
  sekwencji odpowiadają kandydatom.
- Apply (zgoda operatora w czacie po przejrzeniu preview): 10 porcji
  (`artifacts/cell-level-migration/apply-777-01.json` … `-10.json`, 500 +
  8 × 4500 + 1282 plansz, ~0,09 s na planszę, łącznie ~52 min): 37 782
  `applied`, 0 `drift`, 0 `failed`, 0 `fatal`; 456 komórek wróciło do
  weryfikacji, 3 plansze ponownie otwarte (81, 104, 106 → `pending`), 0
  domknięć. Każda plansza manifestu wystąpiła dokładnie raz.
- Odczyt po apply: 0 akceptacji innych pikseli; zatwierdzonych komórek
  73 378 = 73 834 − 456 (zero nowych weryfikacji); 456 zdarzeń
  `geometry_invalidated` aktora `cell-level-migration` na 456 różnych
  komórkach; plansze: 500 026 `pending`, 0 `accepted`.
- Audyt claude-opus-5-5 (subagent, poziom rozumowania dziedziczony): cykl 1 —
  brak P0–P1, 2× P2 (brak testu ścieżki `virtual_source`, brak testów
  zabezpieczeń: niezmiennika, skryptu, liczników/rewizji katalogu/V2);
  cykl 2 — „Brak uwag P0–P2”; pełny preview obecnym kodem (tylko odczyt) dał
  ten sam `previewSha256`, a 120 losowych plansz przeliczonych osobno — 0
  różnic. Zastosowane P3: czyszczenie `blurry` przy recheck, `reviewItemId`
  i wpis `fatal` przy naruszeniu niezmiennika lub błędzie bazy, wyłączny
  zapis preview, odmowa istniejącego raportu apply, `lock_timeout` 10 s i
  `statement_timeout` 120 s na planszę, kod wyjścia 1 przy `drift`/`failed`,
  odporna walidacja liczników manifestu. Pozostałe P3: `closeAction` to akcja
  przed zamianą ACCEPTED→CORRECTED (0 domknięć), `already_applied` obejmuje
  też plany zdezaktualizowane z zewnątrz, preview trwa ~510–535 s (blisko
  limitu 600 s jednego polecenia).

### Not completed

- Odbiór całości (kontrolny preview po apply, scenariusze 1–9) — TASK-0729.
- Pozostałe uwagi P3 opisane w wynikach audytu.

### Documentation updates

- Plan (T8: wynik preview), `CURRENT_STATE.md`.

### Recommended next task

- TASK-0729.
