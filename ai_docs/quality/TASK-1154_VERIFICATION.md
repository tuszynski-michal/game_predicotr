# TASK-1154 — Weryfikacja T0

Data: 2026-11-03. Worktree: `codex/full-board-detection`, baza testów `c6f9597a0cbaf8c3a2d27966a586693ab2498fde`.

Przed audytem gałąź zaktualizowano fast-forward do `448f75e769c0f35fe23956813faecc29109fd3df`
(TASK-1153, scalony i wypchnięty przez roota za osobną zgodą operatora). Żaden
zmieniany moduł Python, schema ani SDK nie zmienił się w tej aktualizacji. Jedyny
konflikt DOC_INDEX rozwiązano z zachowaniem obu planów, mapę zregenerowano.
Powtórzone docs:check, code-map:check, Admin OpenAPI check i generated client check: PASS.

## Wyniki wykonane

| Kontrola | Wynik |
|---|---|
| `pytest` — test_neural_crop_policy, test_neural_auto_crop_v2, test_v3_engine_acceptance, test_grid_reinference_handler, test_grid_reinference_backend | 87 PASS po P2, 12,53 s (pierwotnie 84 PASS, 15,40 s) |
| PostgreSQL — `test_complete_acceptance_and_legacy_or_deferred_cold_replay`, v1/v2 | 6 PASS, 55,25 s |
| PostgreSQL — `test_fit_errors_never_materialize_v2_automatic_cells`, FIT_FAILED/FIT_OUTLIERS, v1/v2 | 4 PASS, 38,62 s |
| PostgreSQL — reinference `accepted`, `prepare_restart`, `rollback_retry` | 3 PASS, 64,50 s |
| SDK wrapper `grid-reinference-request.test.mjs` | 4 PASS |
| `tsc --noEmit`, admin-api-client | PASS |
| Admin OpenAPI export/check i generated client check | PASS; enum v1/v2, bez nowych pól/tras |
| Ruff format/check zmienionego Pythona | PASS |
| docs:check — decyzje, okno, budżet startowy, mirrors | PASS; 44 616 B odczytu startowego, 11/11 budżetów |
| generate_code_map.py / --check | PASS |

Skończone polecenia miały timeout 120 s. Testy korzystały z krótkiego, unikalnego
`artifacts/p…`, `artifacts/g…` lub `artifacts/r…`; początkowo zbyt długi lokalny
basetemp przekraczał MAX_PATH Windows. Nie zmieniano produkcyjnego zapisu plików,
aby ukryć ten problem. Testy wymagające zapisu plików i nowych procesów wykonano
poza ograniczonym dostępem do katalogu tymczasowego. Test restartu uruchamia nowy
proces Python i czyta ten sam niezmienny checkpoint.

Testy PostgreSQL tworzyły wyłącznie własne jednorazowe bazy. Nie wykonano migracji
ani zapisów w bazie operatora. Receipt reinferencji potwierdza `phase=cleaned`,
`databaseRemaining=0`, `roleRemaining=0`, bez pozostałych sesji. Fixture head-schema
miały historyczny limit liczby tabel v19; w tych dwóch modułach testowych limit
przygotowania jest ograniczony aktualną liczbą tabel lifecycle. Asercje danych,
RLS, zapisu i replay pozostają aktywne.

## Kontrola typów Python i zastany stan

`mypy --follow-imports=silent` wszystkich 14 zmienionych modułów aplikacji,
z rzeczywistymi zależnościami, zakończył się sześcioma błędami. Identyczne
komunikaty potwierdzono przez `--shadow-file` dla oryginalnych plików z HEAD:

- `pipeline_store.py`: pięć błędów `UUID | None` przekazywanego jako UUID do
  `require_active_sha`, `acquire_sequence_ownership_lock`, `materialize_admission`
  i `require_active_source` (baseline linie 169, 209, 221, 248, 1481).
- `virtual_grid_geometry_repository.py`: przypisanie tuple do zmiennej typu
  SQLAlchemy Row (baseline linia 2786).

Brak nowych błędów typów. Te sześć zastanych błędów pozostawiono poza zmianą.
Pierwsza próba z ograniczonym dostępem do plików osiągnęła timeout 120 s; sprawdzono
brak osieroconych procesów. Wynik końcowy i baseline pochodzą z pełnego sprawdzenia
zależności, nie z pomocniczej próby `--follow-imports=skip`.

## Dowód 462205

Fixture `services/api/tests/fixtures/neural_462205_fit_outliers.json` zawiera
dokładne zapisane węzły pozycji 0, score, przyczynę i identyfikatory pochodzenia
kandydata. Źródło: lokalny zapis porównania z 2026-11-03, source
`e1423fff-6d95-4e8c-ba73-9c8ea6b52f70`, checksum
`8e713b2036210c3bf7a6e66043bf973876e18fce648af6beb4aecfa794bacdb7`, rozmiar
1498 × 1246. Zapisany kod to `NEURAL_GRID_FIT_OUTLIERS`: v1 dopuszcza dawną
decyzję, v2 blokuje. Nie uruchamiano nowej inferencji. Fixture nie jest niezależnym
GT ani pomiarem skuteczności modelu.

## Ograniczenia i zakres

- Brak treningu, model runs, GPU, aktywacji, restartów usług, wdrożenia i merge/push.
- T0 nie wykrywa każdej niekompletnej, lecz strukturalnie poprawnej kraty bez
  sygnału błędu. Kompletność i kalibracja należą do T4.
- Capabilities pakietu i kontrola strony przed inferencją należą do T2; T0 zachowuje
  obecną topologię 3 × 5 i blokuje jawny sygnał braku obsługi.
- Historyczny statusowy backfill pozostaje v1 i nie jest uruchamiany.
- Ręczne korekty i etykiety nie są automatycznie zatwierdzane. Propozycja dla
  zgłoszonej złej siatki zachowuje zgłoszenie i dotychczasowe cropy.

## Niezależny audyt i jedna runda rozliczenia P2

Audyt `claude-opus-5-5/high`: **PASS**, bez P0/P1, pięć P2. Raport:
[TASK-1154_AUDIT_claude-opus-5-5.md](TASK-1154_AUDIT_claude-opus-5-5.md).
Audytor wykonał przegląd statyczny; nie uruchamiał testów.

| Uwaga | Rozliczenie wykonawcy |
|---|---|
| P2-1 | Docstring rozróżnia projekcję spójności od dowodu z przypiętej propozycji. Test pokazuje true dla samej spójności sfałszowanej geometrii, ale odrzucenie przez kwalifikację akceptacji. |
| P2-2 | Użyto istniejącej `MAX_PAGE_BOARD_SLOTS` (9) z kontraktu zakresu. Bez zmiany semantyki. |
| P2-3 | Docstring wyjaśnia opcjonalność valid_pixel_box; w produkcji retained crop ograniczają require_inside_valid_box i renderer. Guard API sprawdza granice obrazu. |
| P2-4 | Oba FIT przechodzą przez rzeczywiste raw_inference, publikację/odczyt JSON w świeżym handlerze, build_neural_source_proposal i blockers v1/v2. FIT_FAILED używa fallbacku grid_from_quad. Runner tylko zwraca obiekt fixture; brak inferencji modelu. |
| P2-5 | Dodatkowy test rozbieżnego dowodu potwierdza NEURAL_GRID_AUTOMATIC_WRITE_BLOCKED przed pierwszym wywołaniem sesji DB. Istniejący wykonany PostgreSQL rollback_retry potwierdza FAILED, brak target results, geometry_revision=0 i automaticWrittenBoardCount=0 po błędzie zapisu oraz późniejsze wznowienie. Błąd integralności pozostaje jawną awarią, bez zamiany na needs_manual_review. Nie wykonano osobnego PG scenariusza korupcji dowodu; to jawne ograniczenie pokrycia. |

Po rozliczeniu P2: 87 scoped testów Python PASS (12,53 s), Ruff format/check PASS,
mypy zmienionego `neural_crop_policy.py` z rzeczywistymi zależnościami PASS.
API i zachowanie runtime nie zmieniły się po audycie poza użyciem istniejącej
stałej o tej samej wartości; wcześniejsze 13 testów PostgreSQL i 4 SDK pozostają
aktualne. Nie powtarzano ich bez potrzeby.

Historia dostępu i transportu:
[TASK-1154_AUDIT_BLOCKED.md](TASK-1154_AUDIT_BLOCKED.md). Dwie odmowy dostępu
wystąpiły przed startem audytora; nowa konkretna zgoda operatora rozwiązała
blokadę. Pierwsza uruchomiona próba: timeout 480 s, stdout=0 B, stderr=0 B,
bez werdyktu i bez pozostawionego procesu Claude. Druga instrumentowana próba
tej samej rundy R1 użyła scoped pakietu 100 376 B, stream-json/verbose i zakończyła
się powyższym PASS. Nie było dwóch ukończonych rund audytu.
