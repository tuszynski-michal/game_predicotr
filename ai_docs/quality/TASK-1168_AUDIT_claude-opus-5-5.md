# Audyt TASK-1168 — Panel pełnych symboli, porównanie HTML i odbiór

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: a9951e94f8cb7ad1912c1888f3f47eb94cb5efea...HEAD oraz zmiany niezacommitowane (F=`artifacts/audits/TASK-1168-R2-sources`), data 2026-11-09
Runda: 2
SHA pakietu: f385f2cdc45ceb9801fb24132e784a8fc1ec61065262698ae1242b5e1177b8d4
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano poprawki P0-1, P1-1, P1-2, P2-1, P2-3 oraz brakujący w R1 odczyt delty mechanicznej i kontraktu API. Generator używa teraz rzeczywistego adresu `pages/{sha}.json`, nazwy pochodzą z prawdziwego wiersza importu, a stare odpowiedzi mają testy na rzeczywistych komponentach. Pozostaje zaakceptowany P2-2 oraz nowy P2-4: pakiet nie zawiera producenta pinu `detail`, więc jego katalogu bazowego nie dało się potwierdzić.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-2] `F/services/worker/src/game_predictor_worker/images/comparison_production_cells.py:456` — Ścisła równość węzłów z osobnego przebiegu pozostaje bez zmian. Inny backend lub niedeterminizm da uczciwe, być może masowe unavailable; zasięgu nie zmierzono. Akceptacja ryzyka jest jawna (`FULL_SYMBOL_CROPS_ACCEPTANCE_20261109.md:136-141`). Propozycja: sprawdzić przy pierwszym rzeczywistym porównaniu, bez tolerancji ani dopasowania 9/index.
- [P2-4] `F/services/worker/src/game_predictor_worker/images/comparison_production_bundle.py:92-93` — Nowe. Pin `detail` jest brany wprost z raportu, bez budowania ścieżki, więc nie powtarza mechanizmu P0-1. Kształt `{path, sha256}` potwierdza schemat (`schemas/grid_model_evaluations.py:92-94`), ale producenta pliku `detail` nie ma w F, a fixture zapisuje ręczną ścieżkę (`test_comparison_production_cells.py:166`). Skutek, gdyby ścieżka była względna wobec innego katalogu: unavailable, bez fałszywego dowodu. Brak dowodu defektu, stąd P2. Propozycja: potwierdzić przy pierwszym rzeczywistym pakowaniu albo dodać test z rzeczywistym zapisem `detail`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| AC1 ordinary/blind | spełnione | Dowód R1 bez nowych zastrzeżeń. Nowy odczyt: `grid-content-blind.tsx:300-447`; `grid-content-ordinary.tsx:56-93`; rozdzielenie trybów kluczem `grid-content-reference-workspace.tsx:47`. |
| AC2 komendy, współrzędne, izolacja | spełnione | Luka P1-2 zamknięta. Nowe: `grid-content-reference.test.mjs:1225,1351,1386,1449`; token `grid-content-blind.tsx:94`; dokładny pending `grid-content-command-control.tsx:55-63`. CAS, 15 vs 24 i zoom: dowód R1, kod canvasu bez zmian. |
| AC3 targets/asset i liczniki | spełnione | Nowe: `grid_cell_content_targets.py:57-84,101-105,132`; test PG `test_grid_content_targets_postgres.py:121-133,142,190`, nowy proces `:71`. Mechanika: `TASK-1168_R1_MECHANICAL.diff:117-991` w całości; `API_CONTRACT.md:9-22`. Bez rozbieżności z D-593. Asset i liczniki: dowód R1. |
| AC4 panel v6 | spełnione | Nowe: `grid-correction-learning-panel.tsx:142-148,227`; test nieudanego budżetu i ponowienia w `grid-correction-learning-panel.test.mjs` (delta `:1033-1081`). Podział verdict/automat: dowód R1. |
| AC5 HTML/produkcyjne piksele | spełnione dla manifestu, CLI, PNG i T3; katalog bazowy `detail` niezweryfikowany (P2-4) | Nowe: `comparison_production_bundle.py:56-62`; publikator `grid_training_cohort_artifacts.py:110,132`; `grid_training_cohort_commands.py:474,550`; `test_comparison_production_cells.py:88-106,440-510`; hashe PNG/T3 `:317-342`. |
| AC6 handoff T4 | spełnione | Dowód R1. Bez zmian w tych zakresach (manifest różnic i delta). Nowego pełnego odczytu nie wykonano. |
| AC7 odbiór i uczciwość | spełnione | Nowe: `TASK-1168_VERIFICATION.md:239-301` oddziela wcześniejsze niereprezentatywne fixture i pierwotny EPERM; `FULL_SYMBOL_CROPS_ACCEPTANCE_20261109.md:13-18,122-125,136-141`. |

## Rozliczenie uwag R1

- **P0-1, zamknięte.** Adres pochodzi z SHA raportu i odpowiada `publish_json` → `pages/{sha}.json`. Rzeczywisty korzeń ma `manifest_path` i SHA z tego samego wyniku. Dataset nie czyta `captureIndex`, więc jego brak w pakiecie nie szkodzi. Test publikuje strony, indeks i korzeń prawdziwym magazynem, usuwa starą ścieżkę i sprawdza brak `manifest.json`. Dwa nowe procesy istniejącego CLI działają na katalogu bez indeksu, a generator sam go tworzy i daje 30 PNG. Brak dowodu pozostaje unavailable (`:345-437`).
- **P1-1, zamknięte.** Zapytanie ma ten sam JOIN co populacja (`grid_correction_split.py:107-109`), jest ograniczone do jednej strony (≤50), a `limit` ogranicza plansze. Sprawdza obie sumy: `sourceSha256`↔`checksum_sha256` i `sourceRepresentativeSha256`↔`normalized_pixel_checksum_sha256` (`domain/grid_cell_content.py:65-66`). Nie czyta `s.relative_path`. Membership, sekwencja i currentness są nietknięte (`:108-139`), a błąd bazy nie udaje pustej listy. Test PG czyta prawdziwą tabelę przez rolę aplikacyjną, potwierdza brak `logicalName` w stronie i powtarza asercję w nowym procesie.
- **P1-2, zamknięte.** Testy montują rzeczywiste komponenty i mockują tylko API. Obejmują loading, error, empty i retry dla kohort, celów, etykiet oraz sesji (`:913,968,1022,1077`). `hold` i `deferred` są użyte, a asercje następują po `act` z rozwiązaniem starego żądania (`:1147-1449`). Mechanizmy są rozróżnialne: klucz remontu przy grze i trybie, `active` przy źródle, token przy tym samym egzemplarzu (`:1386`). Blind pozostaje bez zwykłego GET i bez hydracji canvasu. Poprawki UI są minimalne.
- **P2-1, zamknięte.** Lokalne unavailable zachodzi tylko po pełnym replayu T3 (`comparison_production_cells.py:313,475-476`) i tylko przy dokładnym świadku 15×`CONTENT_PREDICTION_INVALID` bez zapisanych komórek (`:349-362`). Inaczej wyjątek przechodzi dalej. Test ma 9 plansz, jedną pozaobrazową predykcję i przeciwny model, a sfałszowany świadek jest odrzucany (`:513-545`).
- **P2-2, otwarte** zgodnie z akceptacją.
- **P2-3, zamknięte.** `_write_output` tworzy plik przez `xb`, a przy istniejącym porównuje bajty i niczego nie nadpisuje ani nie usuwa (`:58-70`). PNG jest kodowany do pamięci przed zapisem (`:77-80`). Testy obejmują obce PNG, obcy indeks oraz powtórzenie z tymi samymi bajtami i mtime (`:548-592`). Konflikt indeksu wychodzi z `build_production_package` i przerywa `render` przed zapisem HTML (`render_grid_correction_comparison.py:33-37`), co jest zachowaniem bezpiecznym.

Residual T4P2-1/T3P2-1 pozostaje zaakceptowany i nie jest tu ponownie zgłaszany. Brak treningu, wdrożenia, migracji operatora i merge jest granicą zakresu, nie brakiem implementacji.

## Listy zamknięte i otwarte

Zamknięte: P0-1, P1-1, P1-2, P2-1, P2-3.

Otwarte: P2-2, P2-4.

## Proponowane testy

- `apps/admin/test-interactions/grid-content-reference.test.mjs:968`: tytuł obiecuje czyszczenie starego edytora, ale test go wcześniej nie otwiera. Dodać odświeżenie celów przy otwartym canvasie. Uruchomienie: `node --test` przez istniejący tsx.
- Ten sam plik, `:1171`: warunkowe `if (select)` zastąpić bezwarunkową asercją dla każdego przejścia.
- Ten sam plik: błąd i ponowienie `Sprawdź pokrycie etykietami`.
- `services/worker/tests/test_comparison_production_cells.py`: `detail` zapisany rzeczywistym producentem oceny (P2-4) oraz konflikt indeksu na poziomie CLI. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_comparison_production_cells.py`.

## Zakres przeglądu i ograniczenia

Przegląd wyłącznie statyczny (Read/Glob/Grep). Nie uruchamiano testów, usług, bazy, inferencji ani treningu, a wyniki wykonawców potraktowano jako deklaracje. Sum SHA nie dało się przeliczyć tymi narzędziami.

Przeczytano w całości: indeks R2, `TASK-1168_R2_SOURCE_DELTA.diff`, `TASK-1168_R1_MECHANICAL.diff`, szablon, D-593 (`DECISION_LOG_2026.md:18-113`), `API_CONTRACT.md:1-40`, moduły `comparison_production_bundle.py`, `comparison_production_cells.py`, `grid_cell_content_targets.py`, `grid_training_cohort_artifacts.py`, CLI, test PG, kontrolery workspace i blind oraz `grid-content-command-control.tsx`.

Fragmentami: testy interakcji (fixture i wszystkie nowe przypadki), `test_comparison_production_cells.py` (`:1-290,290-345,436-515`, reszta z delty), `grid-content-ordinary.tsx:1-140`, producent korzenia, dataset, schematy oceny, `domain/production_cell_evaluation.py`.

Nie czytano całego OpenAPI, plików spoza F, zdjęć, wag, sekretów ani bazy. `_save_source` z testu PG nie należy do F; o realności wiersza świadczy asercja nad prawdziwą tabelą. Producent `detail` nie należy do F (P2-4).