# Audyt TASK-0946 - Cofnięcie korekty istniejącej planszy

Werdykt: REVISE
Audytor: Codex, etykieta briefu `gpt-6-astra`, reasoning `high`
Wykonawca: `claude-opus-5-5`, reasoning `high`
Zakres: HEAD...25a7c099c10a11da7dec6be86aa56c2505e8d362 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-09
Runda: 1

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono odtwarzanie geometrii, decyzji i zatwierdzeń komórek, warunki odmowy oraz testy PostgreSQL. Implementacja obejmuje podstawowe scenariusze, ale zawiera błędy kolejnych cykli cofania i odtwarzania historycznej proweniencji zatwierdzeń. Kopiowanie historycznych sum kontrolnych nie realizuje wymaganego scenariusza zmiany croppera. Wprowadzono również odstępstwa od zaakceptowanego kontraktu.

## Znaleziska

### P0

- [P0-1] `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:331` — **Nie można cofnąć nowej korekty po wcześniejszym przywróceniu zatwierdzonej geometrii.** Cofnięcie rewizji 2 zapisuje rewizję 3 z `approved_geometry_revision = 3`, ale jedynym zdarzeniem zapisującym tę wartość jest `geometry_reverted`. Po kolejnej korekcie do rewizji 4 odczyt metadanych zatwierdzenia wyklucza właśnie tę akcję. `_board_revision_plan` zwraca wtedy `None` przy linii 1762, a cofnięcie odmawia kodem `NOT_SUPPORTED`. Należy odtwarzać pierwotny czas i autora zatwierdzenia również przez historię wcześniejszego cofnięcia, np. jego migawkę audytową. Samo dopuszczenie akcji do zapytania zwróciłoby czas i autora cofnięcia zamiast zatwierdzenia.

- [P0-2] `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:2051` — **Fallback dla starszych zdarzeń może zapisać nieprawdziwą proweniencję zatwierdzenia.** Przykład: komórka zatwierdzona na rewizji 0 po korekcie do rewizji 1 jest `pending`, zachowując zatwierdzenie rewizji 0. Korekta do rewizji 2 z symbolem D-488 nadpisuje jej bieżące pola zatwierdzenia. Przy cofnięciu starszego zapisu, którego `geometry_invalidated` nie zawiera pełnych `previous_approved_*`, fallback łączy checksumę zatwierdzenia rewizji 0 z `previous_source_geometry_revision_id` i specyfikacją renderu rewizji 1. Powstaje niespójna historia zatwierdzenia. Należy odnaleźć rzeczywistą proweniencję wcześniejszego zatwierdzenia w zdarzeniach; przy braku dowodu odmówić zamiast ją rekonstruować z innego renderu.

- [P0-3] `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:1282` — **Porównanie zatwierdzeń nie wykrywa zmiany pikseli spowodowanej zmianą croppera.** `restored_pixels` pochodzi ze starego manifestu, a następnie jest porównywane ze starą checksumą zatwierdzenia. Cofnięcie nie renderuje ani nie sprawdza aktualnych pikseli. Jeżeli renderer odtworzy inne piksele, komórka może zostać oznaczona jako `approved`, a późniejszy podgląd odmówi z `SYMBOL_CELL_REVIEW_PREVIEW_PIXEL_CHECKSUM_MISMATCH` (`application/virtual_cell_previews.py:610`). Test przy `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:626` zmienia historię zatwierdzenia, więc nie odtwarza tego scenariusza. Należy zweryfikować rzeczywisty render i zastosować regułę D-462 do jego checksumy; test powinien zmieniać wynik renderera bez modyfikacji historii.

- [P0-4] `services/api/src/game_predictor_api/domain/geometry_correction_reverts.py:324` — **Wartość zatwierdzenia planszy nie wraca do stanu sprzed korekty.** Funkcja zamienia wcześniejsze `approved_geometry_revision = N − 1` na `N + 1`. Kryterium przy `ai_docs/tasks/0946-geometry-correction-revert-board-revision.md:46` i punkt A.3 planu wymagają przywrócenia wcześniejszej wartości. Test drugiej korekty oczekuje już zmienionego kontraktu (`services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:566`). Uzasadnienie dotyczące bramki kompletności wskazuje konflikt wymagający rozstrzygnięcia, ale zapis w `Outcome` nie zastępuje akceptacji zmiany. Należy przywrócić uzgodniony kontrakt albo uzyskać decyzję operatora i odpowiednio uzgodnić plan, kryteria oraz testy.

- [P0-5] `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:1648` — **Kolejny cykl cofania zmienia silnik przywracanej geometrii.** Każda wcześniejsza rewizja większa od zera jest traktowana jako `manual_v1`. Tymczasem rewizja 2 utworzona przez cofnięcie pierwszej korekty może zawierać geometrię importu i pierwotny silnik automatyczny. Po korekcie do rewizji 3 i jej cofnięciu geometria wróci, lecz silnik zostanie ustawiony na `manual_v1`/`manual-source-geometry-v1`. Należy odtwarzać silnik i wersję z proweniencji przywracanej rewizji, uwzględniając rewizje utworzone przez cofnięcie.

### P1

- [P1-1] `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:364` — **Warunek `PINNED` został osłabiony względem zaakceptowanego planu.** Zapytanie pomija cele operacji zbiorczych i rewizje predykcji utworzone przed transakcją korekty. Plan wymaga odmowy przy wskazaniu planszy lub komórek przez te tabele, bez wyjątku czasowego. Argument dotyczący powszechności predykcji importu uzasadnia propozycję zmiany, ale sam czas utworzenia nie dowodzi, że każdy starszy rekord odnosi się do przywracanego renderu. Należy zachować warunek planu albo uzgodnić wyjątek, opisać jego dokładne granice i sprawdzać właściwą tożsamość renderu zamiast wyłącznie daty.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Przywrócenie `grid_issue`, widoku `correction`, geometrii i wcześniejszego `approved_geometry_revision` | niespełnione | Podstawowy scenariusz: `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:409`; odstępstwo wartości zatwierdzenia: P0-4. |
| Wycofanie symboli D-488 i przywrócenie zatwierdzeń wyłącznie dla identycznych pikseli | niespełnione | Podstawowy scenariusz ma test; historia starszych zatwierdzeń i zmiana renderera pozostają błędne: P0-2, P0-3. |
| Odmowa `GEOMETRY_REVERT_REOPENED_RESOLUTION` bez zapisu | spełnione | `services/api/src/game_predictor_api/domain/geometry_correction_reverts.py:194`; test: `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:676`. |
| Drugie cofnięcie odmawia; nowa korekta zapisuje `N + 2` | spełnione | `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:458`. Dalsze cofnięcie nowej korekty ma odrębne błędy P0-1 i P0-5. |
| Liczniki, wyszukiwarka i bramka odpowiadają stanowi sprzed korekty w teście PG | niezweryfikowane | Porównanie jest zaimplementowane w `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py:223`; wykonania PG nie powtarzano. |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P0-1, P0-2, P0-3, P0-4, P0-5, P1-1.

## Proponowane testy

W `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py`:

- Dwie korekty, cofnięcie drugiej, nowa korekta i jej cofnięcie; sprawdzenie pierwotnego autora i czasu zatwierdzenia.
- Dwa pełne cykle korekta–cofnięcie od geometrii importu; porównanie silnika, wersji i projekcji planszy.
- Starsze zdarzenie bez pełnych `previous_approved_*`, wcześniejsze zatwierdzenie innej rewizji i nadpisanie D-488; porównanie wszystkich pól proweniencji.
- Zmieniony wynik renderera przy niezmienionej historii zatwierdzeń; oczekiwane `pending` i poprawny podgląd.
- Zatwierdzona geometria z `grid_issue`; sprawdzenie wartości zatwierdzenia według rozstrzygniętego kontraktu.
- Starsze predykcje i cele operacji zbiorczych dotyczące różnych renderów; weryfikacja uzgodnionej reguły `PINNED`.

Po poprawkach, na dedykowanej bazie testowej:

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/test_geometry_correction_reverts.py services/api/tests/integration/test_geometry_correction_revert_board_postgres.py services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py services/api/tests/integration/test_geometry_correction_revert_refusals_postgres.py -q
```

## Zakres przeglądu i ograniczenia

Przeczytano brief, task i jego `Outcome`, odpowiednie fragmenty planu, decyzje D-462/D-467/D-488, zmienione moduły i testy oraz zależności zapisu zdarzeń, renderowania i bramki kompletności. Oceny „spełnione” oznaczają zgodność ustaloną statycznie, nie niezależne potwierdzenie wykonania testów.

Nie uruchamiano testów, migracji, usług ani operacji na bazie. Wyniki PG, lint i mypy podane w `Outcome` pozostają deklaracjami wykonawcy. Odczyt `git rev-parse HEAD` potwierdził hash briefu. `git diff --check` zakończył się kodem 1 z powodu końcowego białego znaku w pliku taska przy linii 142. Raportu nie zapisano na dysku zgodnie z zakazem zmian plików.