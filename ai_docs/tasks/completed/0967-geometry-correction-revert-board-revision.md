# TASK-0967 — Cofnięcie korekty istniejącej planszy (rewizja N + 1 = N − 1)

## Status

`done`

## Goal

`GeometryCorrectionRevertService.revert` obsługuje korekty istniejących plansz (przypadek A): zapisuje rewizję `N + 1` z geometrią `N − 1` i przywraca decyzje komórek sprzed korekty.

## Context

Plan `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`, sekcje „Przypadek A”, „Warunki dopuszczenia”, „Założenia” (Z1, Z2).

## Dependencies / entry conditions

- TASK-0966 ukończony (migracja `0154`, status `reverted`, serwis, audyt, warunki wspólne).

## Recommended execution

`claude-opus-5-5`, reasoning `high`: odtwarzanie decyzji komórek z historii i render nowej rewizji; ryzyko utraty zatwierdzeń człowieka. Eskalacja: Z1 nie zachodzi i fallback blokuje typowe korekty → zatrzymaj i zapytaj operatora. Review: Codex `gpt-6-astra`, `high`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md` — D-462, D-467, D-488

## Scope

- Weryfikacja Z1 (wspólne `created_at` zdarzeń komórek jednej transakcji) w kodzie (`image_symbol_review_events.created_at` `server_default now()`, brak jawnego ustawiania) i teście PG. Wynik zapisz w `Outcome`.
- Wyznaczenie geometrii `N − 1` (wiersz rewizji planszy albo wpis slotu poprzedniej rewizji źródła dla `N − 1 = 0`) i poprzedniej rewizji źródła.
- Zapis rewizji `N + 1` wskazującej poprzednią rewizję źródła (bez dopisywania nowej rewizji źródła), manifest renderu `N + 1`, projekcja planszy, zdarzenie `geometry_reverted`.
- Komórki: render `N + 1`, przywrócenie decyzji z najwcześniejszego zdarzenia transakcji korekty, reguła zatwierdzenia po pikselach (D-462), reguła `assignment_source` z planu, zdarzenie komórki `geometry_reverted` z pełnymi `previous_*`.
- Warunek `GEOMETRY_REVERT_REOPENED_RESOLUTION` i pozostałe warunki wspólne dla A.
- Rewizja źródła korekty `reverted`, odwrotne przepięcie sąsiadów, liczniki, wyszukiwarka, wersja supergry, bramka kompletności, audyt (`kind = board_revision`, migawka stanu komórek przed i po).
- Wzorzec przepisania z zachowaniem decyzji: `_convert_current_cells` (`storage/virtual_grid_geometry_repository.py:1107`).

## Out of scope

- Przywracanie roszczenia kanonicznego (odmowa kodem), cofanie dowolnej starszej rewizji, HTTP, UI.

## Acceptance criteria

- [ ] Korekta planszy z komórkami `grid_issue` → cofnięcie → komórki znów `grid_issue`, plansza w widoku `correction`, geometria równa `N − 1`, `approved_geometry_revision` równe wartości sprzed korekty, przy czym zatwierdzenie dokładnie przywracanej rewizji `N − 1` przechodzi na `N + 1` z pierwotnym czasem i aktorem (decyzja leada, do D-542).
- [ ] Korekta z symbolami D-488 → cofnięcie przywraca poprzednie symbole/stany; zatwierdzenia sprzed korekty wracają tylko przy identycznych pikselach.
- [ ] Korekta, która ponownie otworzyła rozstrzygniętą pozycję → 409 `GEOMETRY_REVERT_REOPENED_RESOLUTION` bez zapisu.
- [ ] Drugie cofnięcie → `GEOMETRY_REVERT_NOT_LATEST`; nowa korekta po cofnięciu działa (rewizja `N + 2`).
- [ ] Liczniki, wyszukiwarka i bramka zdjęcia równe stanowi sprzed korekty (porównanie w teście PG).

## Technical notes

- `N + 1` jest nową rewizją append-only; nie obniżaj `geometry_revision`.
- `geometry_approved_at/by`: ze zdarzenia geometrii planszy, którego `approved_geometry_revision` = przywracana wartość; brak → `NULL`.
- Zdarzenia D-488 (`reassign`, `mark_unreadable`) w transakcji korekty mają `previous_*` sprzed symboli, ale po `geometry_invalidated`; bierz najwcześniejsze zdarzenie komórki w transakcji.

## Expected files

- Zmieniane: `application/geometry_correction_reverts.py`, `domain/geometry_correction_reverts.py`, `storage/geometry_correction_revert_repository.py` (z TASK-0966).
- Nowe (proponowane): `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py`; testy jednostkowe w `services/api/tests/test_geometry_correction_reverts.py`.

## Test cases

- Pierwsza korekta planszy (N = 1, N − 1 = 0) z `grid_issue` → pełne przywrócenie.
- Druga korekta (N = 2) → geometria z rewizji 1.
- Korekta z symbolami narzuconymi D-488 → wycofanie symboli.
- Zmiana croppera (symulowana) → zatwierdzenia wracają jako `pending` z podpowiedzią.
- Reguła `assignment_source` dla zdarzeń bez `previous_assignment_source`.
- Odmowy: późniejsza weryfikacja, reopened, nowsza rewizja źródła, CAS.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/test_geometry_correction_reverts.py services/api/tests/integration/test_geometry_correction_revert_board_postgres.py services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py -q
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_correction_cell_symbols_postgres.py services/api/tests/integration/test_cell_render_specs_postgres.py -q
npm run python:lint
npm run python:typecheck
```

## Risks / open questions

- Z1 i Z2 z planu.

## Outcome

Wykonawca: claude-opus-5-5 (high), 2026-10-09. Bez commita (commit, audyt
Codex i `CURRENT_STATE.md` należą do leada).

### Changed

- `domain/geometry_correction_reverts.py`: czyste reguły przypadku A —
  `PreviousCellDecision`, `RestoredCellDecision`, `restore_cell_decision`
  (D-462: zatwierdzenie wraca tylko przy identycznych pikselach, inaczej
  `pending` z dawnym symbolem, bez flagi `blurry`, weryfikacja liczona od
  nowa; decyzja `pending`, w tym `grid_issue`, wraca bez zmian),
  `restored_assignment_source` (zapisane `previous_assignment_source`, inaczej
  reguła planu: `approved` → `human`, `partial_visibility` →
  `geometry_partial`, reszta → `model`), `restored_approved_geometry_revision`,
  `CORRECTION_TRANSACTION_CELL_ACTIONS`; nowy komunikat `NOT_SUPPORTED`.
- `application/geometry_correction_reverts.py`: wynik ma
  `restored_geometry_revision` i `restored_cell_decision_count` (domyślne
  wartości; kontrakt B bez zmian).
- `storage/geometry_correction_revert_repository.py`: `_revert_board_revision`
  (blokady jak zapis: sekwencje pozycji → zdjęcie → plansza → pozycja →
  komórki; idempotencja, CAS i wszystkie warunki pod blokadą), plan
  `_board_revision_plan`, `_restore_cells`, fakty przypadku A w `_evaluate`.
  Kolejność zapisu: migawka planszy i komórek → rewizja `N + 1` + manifest →
  projekcja planszy → zdarzenie planszy `geometry_reverted` → komórki
  (render + decyzje + zdarzenia `geometry_reverted` z pełnymi `previous_*`) →
  liczniki → rewizja źródła `reverted` → odwrotne przepięcie sąsiadów
  (`apply_board_repoint`, kod B) → wyszukiwarka (`sync_review_items`,
  `reconcile_sequence`) → bramka (odmowa przy zmianie dopuszczonego statusu) →
  wersja supergry i `synchronize_after_cell_mutation` → audyt
  (`kind = board_revision`, `restored_geometry_revision = N + 1`, migawka
  planszy i komórek przed/po). Nic nie jest usuwane.
- `storage/virtual_grid_geometry_repository.py`: zdarzenia
  `geometry_invalidated` korekty (i konwersji legacy) zapisują też
  `previous_approved_asset_mode`, `..._source_geometry_revision_id`,
  `..._render_spec_checksum_sha256`, `..._rendered_pixel_checksum_sha256` oraz
  ich bieżące odpowiedniki — przyszłe cofnięcia odtwarzają historię
  zatwierdzenia dokładnie.
- `storage/super_game_input_version.py`: punkt zapisu
  `geometry_correction_revert` dla `_revert_board_revision`.
- Testy: nowy `integration/test_geometry_correction_revert_board_postgres.py`
  (5), nowe testy jednostkowe w `test_geometry_correction_reverts.py` (5),
  zmieniony test 0966 (patrz niżej).

Decyzje wykonawcy (do audytu):

- **Z1 zachodzi.** Kod: wszystkie trzy miejsca tworzenia
  `ImageSymbolReviewEventModel` (`_replace_current_cells`,
  `_convert_current_cells`, `_append_symbol_cell_event`) nie ustawiają
  `created_at` (server default `now()`), brak surowych `INSERT`. Test PG:
  17 zdarzeń korekty (15 `geometry_invalidated` + `reassign` +
  `mark_unreadable`) ma jedno `created_at`, równe `created_at` manifestu
  rewizji `N` i rewizji źródła. Fallback planu niepotrzebny. Konsekwencja:
  znacznik czasu wybiera transakcję, ale nie porządkuje jej zdarzeń —
  „najwcześniejsze zdarzenie” komórki = najniższy `cell_revision` w
  transakcji (każde zdarzenie podbija rewizję komórki). Zdarzenie w transakcji
  z akcją spoza `geometry_invalidated`/`reassign`/`mark_unreadable` →
  `CELLS_CHANGED`.
- **Render bez ponownego renderowania.** Specyfikacja renderu zawiera
  `geometryRevision` w odcisku geometrii, ale czytelnicy
  (`load_cell_render_specs`, materializacja komórek, kohorty) tego nie
  porównują. Rewizja `N + 1` używa dosłownie `virtual_render_spec` rewizji
  `N − 1` (dla `0` dokumentu manifestu importu), zgodnie z planem
  („`virtual_render_spec` z wiersza `N − 1`”); komórki dostają render z tych
  wpisów. Z2 zachodzi z konstrukcji (te same piksele, wersja croppera bez
  znaczenia), serwis nie potrzebuje `artifact_root`. Porównanie D-462 —
  piksele przywracanego renderu vs `previous_approved_rendered_pixel_checksum`
  (dla starszych zdarzeń `previous_approved_crop_checksum`, w `virtual_source`
  równy).
- **Historia `approved_*` komórki niezatwierdzonej:** z pełnego `previous_*`
  zdarzenia; dla starszych zdarzeń bieżące kolumny komórki (korekta ich nie
  rusza, gdy nie przepięła zatwierdzenia), a dla przepiętego zatwierdzenia —
  poprzedni render zdarzenia.
- **`approved_geometry_revision` planszy:** wartość
  `previous_approved_geometry_revision` zdarzenia korekty; zatwierdzenie
  dokładnie przywracanej rewizji `N − 1` przechodzi na `N + 1` (precedens
  konwersji legacy; inaczej plansza z zatwierdzoną geometrią wyglądałaby na
  niezatwierdzoną, a `_manual_neural_lattice_approved` bramki zmieniłoby
  wynik). `geometry_approved_at/by` ze zdarzenia (`approved`/`geometry_saved`/
  `backfilled`), które zapisało tę wartość; brak zdarzenia przy niepustej
  wartości → `NOT_SUPPORTED` (CHECK wymaga obu pól). Zdarzenie
  `geometry_reverted` planszy: `previous_approved_geometry_revision` = stan
  przed cofnięciem (`N`), `approved_geometry_revision` (NOT NULL) = wartość
  przywrócona albo `N + 1`, gdy przywrócono `NULL`; wyszukiwanie metadanych
  zatwierdzenia pomija `geometry_reverted`.
- **Projekcja planszy dla `N − 1 = 0`:** `board_geometry`, silnik i wersja z
  niezmiennego `image_review_items.snapshot` importu; narożniki wiersza
  `N + 1` z wpisu slotu poprzedniej rewizji źródła (`symbolGridQuad`/
  `finalQuad`), w ostateczności z `quad` projekcji. Dla `N − 1 ≥ 1`
  `geometry`/`corners` wiersza `N − 1`, silnik `manual_v1`.
  „`N − 1`” = najwyższa istniejąca rewizja planszy `< N` (plansze slotów mogą
  mieć luki numeracji).
- **`PINNED` dla A** (fakt wstępny z 0966 doprecyzowany): kohorty i biblioteka
  wzorców blokują zawsze; rewizje predykcji i cele operacji zbiorczych tylko,
  gdy powstały w transakcji korekty lub później. Prawie każda plansza ma
  rewizję predykcji importu (odczyt bazy operatora: 893 826 z 904 484 plansz)
  — dawna reguła blokowałaby niemal każde cofnięcie A, a ta predykcja dotyczy
  właśnie przywracanego renderu. Przypadek B bez zmian.
- **`NOT_SUPPORTED` dla A** (fail-closed): kwalifikacja geometrii (plansza
  częściowa) po którejkolwiek stronie, poprzednia rewizja bez renderu
  `virtual_source`/manifestu z kompletem komórek, komórka bez zdarzenia
  transakcji albo z innym renderem sprzed korekty niż przywracany,
  przywracana rewizja źródła `reverted`, brak metadanych zatwierdzenia,
  historyczny `legacy_file`.
- Nieprzywracane: `last_reviewed_by/at` komórek (actor/czas cofnięcia; brak w
  zdarzeniach), `source_images.processed_at`, liczniki monotoniczne. Plansza
  nie jest rozstrzygana po cofnięciu (`synchronize_board_from_cells` nie jest
  wołane — stan sprzed korekty był nierozstrzygnięty).
- Świadoma zmiana kontraktu testu 0966:
  `test_a_board_revision_correction_is_listed_and_refused_as_not_supported`
  (zastępczy kontrakt „A = NOT_SUPPORTED do TASK-0967”) zastąpiony przez
  `test_a_board_revision_correction_of_a_withheld_board_is_reverted`
  (plansza slotu bez komórek: cofnięcie działa, zatwierdzenie przechodzi na
  `N + 1`, slot dalej `NOT_LATEST`). Pozostałe asercje 0966 bez zmian.

### Verification results

Z katalogu worktree, `PYTHONPATH` = `services/api/src;services/worker/src;services/test_support`
worktree, Python `..\..\.venv\Scripts\python.exe`, `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`:

- `pytest services/api/tests/test_geometry_correction_reverts.py services/api/tests/integration/test_geometry_correction_revert_board_postgres.py services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py services/api/tests/integration/test_geometry_correction_revert_refusals_postgres.py -q -p no:logging`
  — 48 passed (27 jednostkowych, 5 A, 6 B, 10 odmów). Testy A: pierwsza korekta
  (`N − 1 = 0`) z `grid_issue`, zatwierdzeniami i symbolami D-488 → pełne
  porównanie stanu gry z migawką sprzed korekty (komórki, plansza, liczniki,
  kolejka, wyszukiwarka, bramka, pozycja), weryfikacja Z1, widok `correction`,
  podgląd bez zapisu, STALE, powtórzenie klucza, drugie cofnięcie →
  `NOT_LATEST`, retry starej korekty → `GEOMETRY_CORRECTION_REVERTED`, nowa
  korekta → rewizja 3; druga korekta (`N = 2`) → geometria i render rewizji 1,
  zatwierdzenie z oryginalnym czasem/aktorem, starsza korekta `NOT_LATEST`;
  symulowana zmiana pikseli → `pending` z podpowiedzią `requires_review`,
  reguła `assignment_source` dla zdarzeń bez `previous_assignment_source`,
  `PINNED` przez predykcję po korekcie (predykcja importu nie blokuje);
  `REOPENED_RESOLUTION` (plansza zaakceptowana 15 komórkami, korekta ją
  otwiera) bez zapisu; `SOURCE_ADVANCED`, `SHARED_SOURCE_REVISION` po cofnięciu
  sąsiedniej korekty, `CELLS_CHANGED` — każde bez zapisu.
- `pytest services/api/tests/integration/test_virtual_deferred_resolution_postgres.py services/api/tests/integration/test_image_geometry_completeness_gate.py services/api/tests/integration/test_grid_correction_cell_symbols_postgres.py services/api/tests/integration/test_cell_render_specs_postgres.py -q -p no:logging`
  — 18 passed, bez zmian asercji.
- `pytest services/api/tests/integration/test_reviewer_operational_geometry_postgres.py services/api/tests/integration/test_convert_legacy_boards_postgres.py services/api/tests/integration/test_board_render_manifests_postgres.py services/api/tests/integration/test_image_geometry_completeness_repository.py -q -p no:logging`
  — 33 passed, 1 skipped (wycofany przez TASK-0940).
- Testy jednostkowe API dotknięte zmianą (`test_board_render_manifests`,
  `test_game_data_v2_schema`, `test_geometry_correction_reverts`,
  `test_geometry_qualification`, `test_lateral_lock_order`,
  `test_schema_readiness`, `test_source_lattice_geometry`,
  `test_super_game_input_version`, `test_virtual_grid_geometry`,
  `test_virtual_grid_geometry_repository`) — 184 passed.
- `python -m ruff check services/api services/worker services/test_support scripts`
  — All checks passed; `ruff format --check` zmienionych plików — czyste;
  `git diff --check` — czyste.
- `python -m mypy services/api/src services/worker/src scripts` — Success
  (862 pliki).
- `python scripts/generate_code_map.py`, potem `--check` — up to date.
- Nie uruchomiono pełnych testów jednostkowych API/workera ani
  `npm run db:baseline:verify` (migracji brak).

### Not completed

- HTTP (TASK-0968), UI (TASK-0969), odrzucanie slotu (TASK-0970), wpisy
  D-542/D-543 (TASK-0972).
- Cofnięcie korekt plansz z kwalifikacją geometrii (częściowa widoczność) —
  świadomie `NOT_SUPPORTED`; przewidywania komórek nie są w zdarzeniach, a
  zestaw komórek może się zmieniać.
- Commit, audyt Codex, `CURRENT_STATE.md` — lead.

### Documentation updates

- `ai_docs/architecture/DATA_MODEL.md` — akapit o przypadku A w podsekcji
  „Cofnięcie korekty cięcia siatki”.
- `ai_docs/architecture/CODE_MAP.md`, `CODE_MAP_SYMBOLS.md` — zregenerowane.

### Recommended next task

TASK-0968 (HTTP nad gotowym serwisem; wynik zawiera teraz
`restoredGeometryRevision`/`restoredCellDecisionCount`), potem TASK-0969.
Do wpisu D-542 w TASK-0972: reguła `PINNED` dla A, przeniesienie
zatwierdzenia na `N + 1` i wartownik `approved_geometry_revision` zdarzenia.

### Runda poprawek audytu

Audyt Codex (`gpt-6-astra`, `high`) runda 1: `REVISE` (P0-1…P0-5, P1-1);
raport zachowany bez zmian w
`ai_docs/quality/TASK-0967_AUDIT_gpt-6-astra_round1.md`. Bez commita.

Decyzje leada (delegowane przez operatora, do D-542; planu nie edytowano):

- **P0-4 — kontrakt zachowany.** Zatwierdzenie dokładnie przywracanej
  rewizji `N − 1` przechodzi na `N + 1` z pierwotnym czasem i aktorem
  (identyczna geometria; bramka wymaga zatwierdzenia bieżącej rewizji).
  Zmieniono tekst kryterium akceptacji w tym pliku.
- **P1-1 — węższa reguła `PINNED` przyjęta z ciaśniejszymi granicami**
  (`_PINNED_BOARD_REVISION_SQL`): kohorty (`verified_training_cohort_cells`,
  `..._items`) i `symbol_reference_images` blokują zawsze;
  `image_symbol_review_bulk_targets` — tożsamość: `expected_geometry_revision
  >= N`; `image_symbol_prediction_revisions` — tożsamość: komórka predykcji z
  `virtualCell.renderSpecChecksumSha256` z manifestu rewizji `>= N` (spec
  zawiera rewizję, więc jest jednoznaczny), a bez niego
  `virtualCell.cropChecksumSha256` równe sumie pikseli renderu `>= N` i
  żadnego renderu `< N`; czas (`created_at >=` transakcji korekty) tylko dla
  rewizji predykcji bez żadnej z tych tożsamości. Odczyt bazy operatora:
  predykcje mają `virtualCell` z obiema sumami.

Poprawki:

- **P0-1.** `_approval_metadata`: czas i aktor zatwierdzenia z najnowszego
  źródła — zdarzenia `approved`/`geometry_saved`/`backfilled` albo migawki
  `board.after` audytu wcześniejszego cofnięcia A, którego przywrócona plansza
  zachowała to zatwierdzenie (oryginalny czas i aktor). Czas/aktor cofnięcia
  nigdy nie są użyte; brak źródła → `HISTORY_INCOMPLETE`.
- **P0-2.** `_approval_history`: pełna proweniencja zatwierdzenia wyłącznie z
  jednego zapisu — najwcześniejszego zdarzenia korekty (gdy ma komplet
  `previous_approved_*`), z komórki, gdy wciąż nosi to samo zatwierdzenie
  (próbka, suma, rewizja), albo z najnowszego wcześniejszego zdarzenia, które
  zapisało to zatwierdzenie z kompletem pól (bieżące lub `previous_*`). Usunięto
  rekonstrukcję z renderu innej rewizji. Brak dowodu → nowy kod
  `GEOMETRY_REVERT_HISTORY_INCOMPLETE` (komunikat po polsku, w kolejności po
  `REOPENED_RESOLUTION`, przed `NOT_SUPPORTED`).
- **P0-3 (wariant preferowany).** Rzeczywiste piksele: nowy port
  `RestoredRenderVerifier` i implementacja `VirtualRestoredRenderVerifier`
  (`application/geometry_correction_reverts.py`, `artifact_root`), która
  renderuje każdą przywracaną specyfikację tym samym renderem co podgląd
  (wydzielone publiczne `render_spec_cell_rgb` w `virtual_cell_previews.py`,
  używane też przez podgląd) i liczy `rgb_pixel_checksum_sha256`. Render pod
  blokadą, po warunkach; manifest i rewizja `N + 1` zapisują dzisiejsze sumy
  pikseli, a D-462 porównuje je z sumą zatwierdzenia z historii. Serwis
  przyjmuje `render_verifier`; bez niego cofnięcie A odmawia
  (`GEOMETRY_REVERT_RENDERER_UNAVAILABLE`), błąd renderu →
  `GEOMETRY_REVERT_RENDER_FAILED`. Zastępuje decyzję „bez ponownego
  renderowania” z pierwszej wersji Outcome.
- **P0-5.** Silnik i wersja rewizji `>= 1`: z migawki `board.after` audytu
  cofnięcia, które ją zapisało; rewizje z zapisu korekty i konwersji legacy —
  `manual_v1` (tak je zapisuje kod). Dla `0` — snapshot importu.

Testy (nowe/zmienione, `integration/test_geometry_correction_revert_board_postgres.py`, 6):

- pierwsza korekta: brak renderera → `RENDERER_UNAVAILABLE` bez zapisu;
  podwójny cykl korekta–cofnięcie od geometrii importu → silnik
  `structured_opencv_v1`, projekcja i zatwierdzenie jak przed pierwszą korektą
  (P0-5). Rewizja 0 fixture'u importu ma syntetyczne specyfikacje bez quada,
  więc ten test używa weryfikatora z zapisanymi pikselami; pozostałe — prawdziwego;
- druga korekta + nowa korekta po cofnięciu + jej cofnięcie → rewizja 5 z
  zatwierdzeniem o pierwotnym czasie/aktorze (P0-1), render rewizji 1 równy
  dzisiejszemu (Z2 na prawdziwych pikselach);
- zmiana renderera dla jednej komórki bez zmiany historii → `pending`,
  `requires_review`, historia zatwierdzenia nietknięta, manifest z nowymi
  pikselami; `PINNED` po obu stronach reguły (predykcja renderu `N`
  datowana wcześniej blokuje, predykcja bez tożsamości po korekcie blokuje,
  cel zbiorczy `expected_geometry_revision = 2` blokuje; predykcja renderu
  przywracanego i cel z rewizją 1 nie blokują);
- scenariusz audytu P0-2 (zatwierdzenie z rewizji 1, nadpisane symbolem D-488
  w korekcie 2, zdarzenia w formacie sprzed 0967) → `HISTORY_INCOMPLETE` bez
  zapisu; po przywróceniu dowodu w zdarzeniu zatwierdzenia — dokładne kolumny
  zatwierdzenia rewizji 1; reguła `assignment_source`;
- `REOPENED_RESOLUTION` i odmowy (bez zmian).

Weryfikacja (worktree, `PYTHONPATH` worktree, `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`):

- `pytest services/api/tests/test_geometry_correction_reverts.py services/api/tests/integration/test_geometry_correction_revert_board_postgres.py services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py services/api/tests/integration/test_geometry_correction_revert_refusals_postgres.py -q -p no:logging`
  — 50 passed.
- `pytest services/api/tests/integration/test_virtual_deferred_resolution_postgres.py services/api/tests/integration/test_image_geometry_completeness_gate.py services/api/tests/integration/test_grid_correction_cell_symbols_postgres.py services/api/tests/integration/test_cell_render_specs_postgres.py services/api/tests/integration/test_reviewer_operational_geometry_postgres.py services/api/tests/integration/test_convert_legacy_boards_postgres.py services/api/tests/integration/test_board_render_manifests_postgres.py services/api/tests/integration/test_image_geometry_completeness_repository.py -q -p no:logging`
  — 51 passed, 1 skipped (wycofany przez TASK-0940).
- Testy jednostkowe `test_virtual_cell_previews.py`,
  `test_image_import_geometry_guard_preview.py`,
  `test_pending_grid_reinference_preview_repository.py`,
  `test_geometry_correction_reverts.py`, `test_super_game_input_version.py`,
  `test_virtual_grid_geometry*.py` — 118 passed.
- `ruff check services/api services/worker services/test_support scripts` —
  All checks passed; `ruff format --check` zmienionych plików — czyste;
  `mypy services/api/src services/worker/src scripts` — Success (862 pliki);
  `generate_code_map.py --check` — up to date; `git diff --check` — czyste.

Pozostaje: HTTP (TASK-0968) musi zbudować serwis z
`VirtualRestoredRenderVerifier(artifact_root)`.

### Zamknięcie (lead)

- Audyt Codex `gpt-6-astra`/`high`: runda 1 REVISE, runda poprawek, runda 2 PASS (`ai_docs/quality/TASK-0967_AUDIT_gpt-6-astra.md`, runda 1 w `_round1.md`).
- P2-2 poprawione przez leada (`DATA_MODEL.md`: kopiowanie specyfikacji komórek i checksumy pikseli z ponownego renderu). P2-1 przyjęte jako ryzyko: test cofnięcia do rewizji 0 używa zapisanych checksum, bo fixture importu nie zawiera renderowalnej specyfikacji; pozostałe cofnięcia używają rzeczywistego renderera.
- Decyzje leada (P0-4, P1-1) wpisane w plan (`Przypadek A` pkt 3, tabela warunków) i do zapisania w D-542.
- Commit: v1.7.292 / 3aa7d04525c9df391a9f82d5839e5ecca4d32e2b.
