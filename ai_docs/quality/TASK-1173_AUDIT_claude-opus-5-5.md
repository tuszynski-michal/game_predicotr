# Audyt TASK-1173 — HTML i końcowy odbiór pełnych wycinków

Werdykt: PASS
Audytor: claude-opus-5-5, reasoning high
Wykonawca: gpt-6.1-sol, reasoning high
Zakres: HEAD...aeae60128e954338cdd257c517c48933e0f25846 (pusty diff commitów) oraz zmiany niezacommitowane, data 2026-11-09
Runda: 2
SHA pakietu: 293ed2a525aa0176ef022b1890705afd7e4c352736518203abccb1c68b93f45a
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono poprawki po rundzie 1 i prześledzono ich zgodność z producentem T2, w tym przestrzeń indeksów detekcji i etykiet. Oba znaleziska P1 z rundy 1 zostały usunięte: strona pokazuje dopasowaną, lecz błędną geometrię oraz fałszywe detekcje, a ścieżka przycięć i sąsiada jest objęta testem wykonującym rzeczywisty szablon. Nie znaleziono nowych błędów P0 ani P1. Pozostają dwa drobne znaleziska P2 dotyczące opisu oceny zawartości, widoczne dopiero przy zatwierdzonych obrysach, których pilot nie ma. Główne ryzyko resztkowe to brak ręcznego odbioru strony w przeglądarce oraz brak operatorowego dowodu jakości, co dokumenty odbioru podają jawnie.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-8] `scripts/templates/production-crop-comparison.html:517` — Gdy raster wariantu jest niedostępny, adapter zastępuje całą komórkę wariantu wartością `_missing` (`services/worker/src/game_predictor_worker/images/comparison_production_crop_report.py:384`), więc ocena T2 przypięta w linii 377 przepada. T2 zapisuje dla widocznej zatwierdzonej komórki stan `missing` również wtedy, gdy plansza nie ma dopasowania albo jest niejednoznaczna (`production_cell_evaluation.py:338-342`). Strona podaje wtedy „Brak zatwierdzonego odniesienia — bez oceny jakości”, choć odniesienie istnieje, a etykieta „Brak wycinka” (`production-crop-comparison.html:425`) pozostaje nieosiągalna dla tego przypadku. Porażka jest nadal jawna przez „Niedostępne: …” i brak pozytywnej oceny, dlatego nie blokuje to commita. Propozycja: zachować `assessment` także w gałęzi `_missing` albo rozróżnić komunikat przy `c[v].state === 'unavailable'`, i dodać asercję DOM dla zatwierdzonej komórki bez dopasowania.
- [P2-9] `scripts/templates/production-crop-comparison.html:435` — Słownik `states` nie zawiera stanu `borderline`, który `assess_content` zwraca dla grafiki na granicy niepewności (`services/api/src/game_predictor_api/domain/production_cell_geometry.py:207`, `:212`). Przy zatwierdzonych obrysach operator zobaczy surowy angielski identyfikator zamiast opisu. Stan nie jest przedstawiany jako zachowany, więc nie ma fałszywej oceny pozytywnej. Propozycja: dodać polską etykietę, na przykład „Na granicy niepewności”, i asercję w teście approved.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Każdy punkt T4 planu ma implementację lub jawny warunek zależny od danych | spełnione | Oryginał, siatka, obrysy, wejścia NN i 15 par: `comparison_production_crop_report.py:398-446` oraz rendering szablonu; porażki geometrii: `production-crop-comparison.html:525-552`; przycięcia i sąsiad: `:511-523`; rozdział modelu i wycinania: wstęp szablonu i `ai_docs/quality/GRID_SYMBOL_CROP_PREVIEW_ACCEPTANCE_20261109.md` |
| Oryginał, siatka, content, input NN i 15 rastrów obecnych i porównywanych | spełnione | `comparison_production_crop_report.py:229-241`, `:343-380`; test: `services/worker/tests/test_comparison_production_crop_report.py:190-205` |
| Porażki jawne; brak GT nie udaje jakości | spełnione | Projekcja: `comparison_production_crop_report.py:242-280`; tekst DOM: `production-crop-comparison.html:525-552`; test rzeczywistego `evaluate_photo`: `test_comparison_production_crop_report.py:460`, `scripts/tests/verify_production_crop_report.mjs:33-56`; niepełny opis przyczyny bez fałszywej oceny: P2-8 |
| PostgreSQL, Admin, lint, typy, build, docs/map i cold read | niezweryfikowane | Wyniki deklarowane w `ai_docs/quality/TASK-1173_VERIFICATION.md` i `ai_docs/quality/TASK-1173_FIXES_R1.md`; polecenia nieuruchamiane, logi poza odczytem |
| Historyczne kontrakty i ręczne korekty zachowane | spełnione | Rozdział trybów CLI: `scripts/render_grid_correction_comparison.py:224-257`; instrukcja i kontrolki blind niezależne od `contentHidden`: `apps/admin/src/features/model-quality/grid-content-canvas.tsx:53`, `:161-163`; brak zapisów w adapterze |
| Właściwe testy, lint, typy i docs/map; niezależny audyt i receipt | niezweryfikowane | Ten raport jest audytem rundy 2; wyniki kontroli są deklaracjami wykonawcy, a receipt tej rundy powstaje poza audytem |
| TRAIN i `visualExportAllowed` przed pikselem oraz public JSON | spełnione | `comparison_production_crop_report.py:423-429`; ochrona w capture: `services/api/src/game_predictor_api/storage/production_crop_capture.py:316-319`; test: `test_comparison_production_crop_report.py:208-248` |
| Zgodność indeksów geometrii z producentem T2 | spełnione | Etykiety są ordinalem listy capture sortowanej po pozycji: `production_crop_capture.py:371`, `production_crop_comparison.py:197`, `comparison_production_crop_report.py:468`; `prediction` i `matchedPrediction` używają tej samej przestrzeni detekcji z węzłami: `grid_evaluation.py:44-52`, `production_cell_evaluation.py:277`, `:373` |
| Follow-up T1 P2-7 | spełnione | `grid-content-canvas.tsx:102-105`, `:311-314`, `:402-409`, `:630`, `:649-652`; test: `apps/admin/test-interactions/grid-content-reference.test.mjs:1688-1737` |
| Follow-up T1 P2-8 | spełnione | `scripts/export_grid_content_preview.py:96-97`, `:191-210`; kod przyczyny z API: `services/api/src/game_predictor_api/storage/grid_content_preview.py:100`; testy: `services/api/tests/test_grid_content_preview_export.py:178-206` |
| Reguła LF dla raportów audytu | spełnione | `.gitattributes:12`; test odczytany bez uruchamiania: `scripts/tests/test_audit_report_checkout.py:9-38` |
| Ograniczenia T1–T3 wskazane w odbiorze | spełnione | Sekcja „Przyjęte ograniczenia” w `GRID_SYMBOL_CROP_PREVIEW_ACCEPTANCE_20261109.md` |

## Listy zamknięte i otwarte

Zamknięte: P1-1, P1-2, P2-1, P2-2, P2-3, P2-4, P2-5, P2-6, P2-7.

Dowody zamknięcia:

- P1-1: `geometryMetrics` i `boardMatches` są publikowane (`comparison_production_crop_report.py:242-280`), a tekst porażki i liczniki renderuje `production-crop-comparison.html:525-552`. Wartości `None` pozostają „brak oceny”. Przypadki pełny i częściowy, w tym pozycja 7 z etykietą 0, ma test `test_comparison_production_crop_report.py:460-549`.
- P1-2: fixture approved zawiera obserwacje wariantów (`test_comparison_production_crop_report.py:388`), a weryfikator DOM sprawdza teksty (`verify_production_crop_report.mjs:75-95`). Nazwy pól są zgodne z T2 (`production_cell_evaluation.py:342-345`, `:380`).
- P2-1: `production-crop-comparison.html:176-178`, `:341`, `:575`; test `verify_production_crop_report.mjs:103-111`.
- P2-2: `production-crop-comparison.html:483`; test `verify_production_crop_report.mjs:100`.
- P2-3: `production-crop-comparison.html:512-515`.
- P2-4: `comparison_production_crop_report.py:425-428`, `production-crop-comparison.html:608`; test `test_comparison_production_crop_report.py:248`.
- P2-5: granica opisana w `production-crop-comparison.html:342` i w dokumentach odbioru; zgodnie z propozycją rundy 1 bez zmiany renderera.
- P2-6: `grid-content-canvas.tsx:311-314`, `:630`, `:649-652`; test `grid-content-reference.test.mjs:1688-1737`.
- P2-7: `comparison_production_crop_report.py:358-359`; test `test_comparison_production_crop_report.py:552`.

Otwarte: P2-8, P2-9.

## Proponowane testy

- Zatwierdzona komórka bez dopasowania planszy: rozszerzyć `services/worker/tests/test_comparison_production_crop_report.py` o `matchedPrediction=None` przy obserwacji `finalContentState="missing"` i sprawdzić tekst DOM w `scripts/tests/verify_production_crop_report.mjs`. Polecenie: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_comparison_production_crop_report.py -k approved`.
- Stan `borderline`: dodać do fixture approved komórkę z tym stanem i asercję polskiej etykiety, tym samym poleceniem.
- Pełny `npm run test:geometry --workspace @game-predictor/admin` przy najbliższej okazji, ponieważ po zmianach Canvas z rundy poprawek wykonano tylko zawężony zestaw.

## Zakres przeglądu i ograniczenia

Przeczytano pakiet audytu, `AGENTS.md`, potrzebne fragmenty `production_crop_comparison.py`, `production_cell_evaluation.py`, `production_cell_geometry.py`, `production_crop_capture.py`, `grid_content_preview.py`, `grid_correction_metrics.py`, `grid_evaluation.py` i `geometry_core/metrics.py`, eksport ordinary oraz fragmenty Canvas i `.gitattributes`. Audyt skupiono na poprawkach po rundzie 1 oraz na ich zgodności z kontraktem T2.

Nie uruchamiano testów, lintu, typecheck, builda, `docs:check`, `code-map:check` ani CLI, a wyniki z dokumentów weryfikacji są deklaracjami wykonawcy. Nie czytano zdjęć, operatorskiego HTML, publicznego JSON, bazy, logów w `artifacts/` ani `.tmp`. Nie policzono SHA raportów ani receiptów. Wygląd strony w przeglądarce nie został oceniony, a PostgreSQL i pełna suita geometrii nie były powtarzane po rundzie poprawek, co dokumenty podają jawnie.