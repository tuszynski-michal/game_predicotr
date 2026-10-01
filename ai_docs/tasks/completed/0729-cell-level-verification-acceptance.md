# TASK-0729 — Odbiór weryfikacji per komórka (D-462)

## Status

done

## Goal

Potwierdzić na żywych danych gry `777`, po zatwierdzonym `apply` TASK-0728,
że scenariusze 1–9 planu D-462 działają end-to-end.

## Context

Ostatnie zadanie etapu C planu
`ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`.

## Dependencies / entry conditions

TASK-0728 done oraz `apply` wykonany po osobnej zgodzie operatora. Bez apply
zadanie jest `blocked`.

## Recommended execution

claude-opus-5-5, high — odbiór całości na żywych danych bez zapisu. Audyt:
claude-opus-5-5, high (subagent, poziom warunkowy).

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` D-462
- `ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`

## Scope

- Odczyt po apply: zero akceptacji innych pikseli, dokumenty wyszukiwania
  zgodne z projekcją, ponowny preview TASK-0728 pusty.
- Przegląd scenariuszy 1–9 (testy automatyczne + odczyt żywych danych).
- Aktualizacja `CURRENT_STATE.md` i zamknięcie planu.

## Out of scope

- Nowe zmiany kodu poza poprawkami znalezionych błędów (osobne taski).

## Acceptance criteria

- [x] Ponowny preview TASK-0728 na grze `777` nie ma żadnej pozycji.
- [x] Każdy scenariusz 1–9 ma dowód (test albo odczyt) w `Outcome`.

## Verification

```powershell
.\.venv\Scripts\python.exe scripts/migrate_cell_level_verification.py preview --game-id bfc4f949-5c14-4850-b02a-db99610bcfa5 --output artifacts/cell-level-migration/acceptance-777.json
```

## Risks / open questions

- Aktywność operatora między apply a odbiorem może dodać nowe pozycje
  preview; odbiór je wyjaśnia, zamiast je ukrywać.

## Outcome

### Changed

- Bez zmian kodu. Odbiór na żywych danych gry `777` po apply TASK-0728
  (wszystkie odczyty w transakcjach `REPEATABLE READ READ ONLY`) i na testach
  automatycznych.

### Verification results

- Kontrolny preview po apply
  (`artifacts/cell-level-migration/acceptance-777.json`, 356 s): 37 894
  przeskanowanych plansz, **0 pozycji** (0 recheck, 0 reopen, 0 close, 0
  refresh), brak notatek.

| Scenariusz | Dowód |
|---|---|
| 1 Jedna komórka zweryfikowana | Test PG `test_verified_cells_reach_search_while_the_board_stays_pending`; żywe: plansza 15804 (pola 3, 8) i 250609 (pole 10) są `pending`, a dokument wyszukiwania ma dla zweryfikowanych pól pewny symbol bez alternatyw. |
| 2 Inna komórka ze złym cięciem | Testy domeny `test_grid_issue_must_remain_pending`, `test_approve_requires_a_real_active_symbol_and_clears_grid_issue`; PG `close_and_reopen`: „Zła siatka” cofa weryfikację tylko tej komórki, a otwarcie planszy rozstrzygniętej pokazuje zgłoszenie `unreadable` (ta sama ścieżka ponownego otwarcia). |
| 3 Algorytm odrzuca planszę | Test PG `test_correction_queue_lists_one_reported_board_per_slot` (slot odroczony); żywe: gra `mumie` ma 10 odroczonych slotów bez planszy i wszystkie są w kolejce `correction`. |
| 4 „Zła siatka” z weryfikacji | Ten sam test PG; żywe: kolejka gry `777` = 119 pozycji = 119 plansz `pending` z komórką `grid_issue` (165 komórek). |
| 5 Wiele zgłoszeń jednej planszy | Ten sam test PG (jedna pozycja na slot); żywe: 165 zgłoszeń daje 119 pozycji. |
| 6 Zapis poprawionej geometrii | Testy `test_new_geometry_rechecks_changed_pixels_and_resolves_the_grid_report`, `test_virtual_recrop_*` (4), `test_outside_grid_report_lasts_until_a_new_geometry`; PG `test_fifteen_verified_cells_close_…` (recrop tych samych pikseli zachowuje weryfikację). |
| 7 15/15 zweryfikowanych | Test PG `test_fifteen_verified_cells_close_the_board_without_geometry_approval`; żywe: preview i apply — 0 plansz z kompletem dowodów bez domknięcia. |
| 8 Ekran 3001 | Reviewer: `board-geometry-correction.test.mjs` (5 testów interakcji), kontrakt `local-reviewer-workspace-contract`; `test` 169/169, `test:geometry` 6/6. |
| 9 Migracja | TASK-0728: apply 37 782 plansz bez dryfu; 0 akceptacji innych pikseli; 456 komórek `pending` z etykietą człowieka (0 z pozostawionym `blurry`); zatwierdzonych 73 378 = 73 834 − 456; pusty kontrolny preview. |

- Uruchomione teraz: PG 7 passed (`test_verified_cell_search_projection.py`,
  `test_cell_level_verification_migration.py`, `test_image_batch_store.py`
  `close_and_reopen` i `bulk_operation`); testy domeny/API/bezpieczeństwa
  111 passed; Reviewer 169 + 6 passed.
- Audyt claude-opus-5-5 (subagent, poziom rozumowania dziedziczony): „Brak
  uwag P0–P2”; wszystkie twierdzenia potwierdzone niezależnie (raporty apply
  zgodne z manifestem plansza po planszy, licznik projekcji `all` = stan
  komórek, zdarzenia `reopened` z powodem `approval_pixels_changed`, kolejka
  korekty potwierdzona osobnym SQL). Zastosowane P3: doprecyzowanie
  scenariusza 2 oraz zapis, że gra `777` nie ma teraz żadnej planszy
  domkniętej.

### Not completed

- Nic w zakresie zadania. Znane ryzyka spoza planu pozostają: A4
  (`synchronize_after_board_reopened`), porażki testów obecne na HEAD
  (`cells.minItems`, dryf opt-in suite `test_image_batch_store`).
- Gra `777` ma teraz 0 plansz `accepted`/`corrected` i 0 wierszy
  kanonicznych (trzy ponownie otwarte plansze były jedynymi domkniętymi),
  więc layout, dataset i snapshot mobilny gry są puste do czasu weryfikacji
  kompletów komórek; zgodnie z D-462/P4 snapshot korzysta wyłącznie z plansz
  domkniętych.
- Znaleziony podczas odbioru błąd poza planem: 108 plansz `pending_partial`
  gry `777` nie ma dokumentu wyszukiwania
  (`board_search_projection_repository.py::_qualified_pending_predictions`
  odrzuca 105 plansz rewizji 0 z predykcjami także dla pól niedostępnych i 3
  plansze `legacy_file` po ręcznej rewizji bez manifestu wirtualnego), więc
  „Przybliżona wygrana” liczy je jak brakujące (koszt spinu, wypłata 0).

### Documentation updates

- `CURRENT_STATE.md`, plan (status ukończenia).

### Recommended next task

- Plan D-462 zakończony. Operator weryfikuje 456 komórek i 3 plansze
  (81, 104, 106) w `Weryfikacji symboli`; 119 plansz czeka w „Korekcie
  cięcia siatki”.
- Osobno (decyzja operatora): poprawka 108 plansz niepełnych w projekcji
  wyszukiwania oraz ewentualna zmiana D-462/P4, aby snapshot mobilny liczył
  także plansze niepełne i niezweryfikowane.
