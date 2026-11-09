# Audyt TASK-1173 — HTML i końcowy odbiór pełnych wycinków

Werdykt: REVISE
Audytor: claude-opus-5-5, reasoning high
Wykonawca: gpt-6.1-sol, reasoning high
Zakres: HEAD...aeae60128e954338cdd257c517c48933e0f25846 (pusty diff commitów) oraz zmiany niezacommitowane, data 2026-11-09
Runda: 1
SHA pakietu: bb108399ecdf4439f72293836968e6940bdb8f47fced71429107ce74ac336da4
Otwarte P0: 0
Otwarte P1: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano adapter `--crop-report`, szablon HTML, zmiany w eksporcie ordinary i w Canvas, regułę LF oraz testy, a także kontrakty T2 i capture, z których adapter czyta. Bramka TRAIN i `visualExportAllowed`, weryfikacja pinów, escapowanie danych, rozdział przestrzeni indeksów i niezmienność outputu są poprawne w zakresie sprawdzonym statycznie. Nie znaleziono błędu P0. Dwa braki blokują commit: strona nie oznacza niepoprawnej, lecz dopasowanej geometrii modelu jako porażki, a ścieżka przycięć i sąsiada w HTML nie została wykonana ani przez test, ani na danych pilota.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/worker/src/game_predictor_worker/images/comparison_production_crop_report.py:238` — Projekcja geometrii publikuje `gate` i komórki, ale pomija `geometryMetrics` (`production_crop_comparison.py:331`) oraz informację o poprawności dopasowania (`production_cell_evaluation.py:375`). Szablon nie ma żadnego odniesienia do tych danych (`scripts/templates/production-crop-comparison.html:518`). Jawne są tylko braki i niejednoznaczności. Plansza modelu dopasowana jednoznacznie, lecz błędnie, na przykład przesunięta o rząd, pojawia się jako 15 par „dostępnych” bez komunikatu o porażce, a dodatkowe fałszywe plansze nie są w ogóle zgłaszane. Bez etykiet zawartości gate daje tylko „Brak danych do oceny”, więc jedynym sygnałem pozostaje ręczne porównanie linii na nakładce. Narusza to „Pokazać porażki” z T4, część „porażki jawne” kryterium akceptacji oraz wiersz „Brak rzędu/błędna geometria” raportu odbioru (`ai_docs/quality/GRID_SYMBOL_CROP_PREVIEW_ACCEPTANCE_20261109.md:12`). Nie jest to P0, ponieważ strona nie wystawia pozytywnej oceny, a rozbieżność jest widoczna na nakładce. Poprawka: opublikować ograniczoną projekcję `geometryMetrics` dla każdej geometrii i pokazać widoczny tekst o niepełnej lub błędnej geometrii modelu, z zachowaniem wartości `None` przy niepełnej geometrii jako „brak oceny”. Dodać test DOM dla dopasowania niepoprawnego.

- [P1-2] `scripts/templates/production-crop-comparison.html:493` — Funkcja `assessment()` jest jedyną powierzchnią HTML dla przycięć, obcego pola i sąsiada, które T4 wymienia wprost, a task podaje „sąsiad” w Test cases. Fixture ma komórki wyłącznie z `cellIndex` i `contentState` (`services/worker/tests/test_comparison_production_crop_report.py:95`), więc nawet test `--expect-approved` (`test_comparison_production_crop_report.py:367`, `scripts/tests/verify_production_crop_report.mjs:50`) sprawdza tylko obrysy i klasę. Pilot nie ma zatwierdzonych obrysów, zatem ta gałąź nie została wykonana także na danych rzeczywistych. Mimo to raport odbioru podaje, że HTML pokazuje assessment. Nazwy pól są statycznie zgodne z T2 (`production_cell_evaluation.py:342`, `:380`), więc jest to brak wymaganego dowodu, a nie wykryty błąd działania. Poprawka: w fixture approved dodać dla komórki obserwacje `base` i `candidate` z `finalContentState` oraz `wrongCell`, `tie` i `foreignFullSymbol`, a w weryfikatorze DOM sprawdzić odpowiednie teksty.

### P2

- [P2-1] `scripts/templates/production-crop-comparison.html:527` — Wszystkie obrysy z `quad` mają ten sam ciągły styl `.outline` (`:172`), a legenda nazywa je „zatwierdzoną grafiką” (`:543`). Stany occluded, out_of_frame i unknown różni tylko `<title>` widoczny po najechaniu, podczas gdy eksport ordinary rysuje fragmenty linią przerywaną i to wyjaśnia. Skutek: fragment wygląda jak pełny symbol. Propozycja: dodać `data-state`, przerywany styl i zdanie w legendzie.
- [P2-2] `scripts/templates/production-crop-comparison.html:472` — Stan `unavailable` klasyfikacji powstaje także przy dostępnej klasie człowieka i niedostępnym klasyfikatorze (`production_crop_comparison.py:293-294`, `:316-319`). Strona mówi wtedy „Brak aktualnej klasy człowieka”, czyli podaje błędną przyczynę. Propozycja: rozróżnić komunikat na podstawie `classReference.state` i `reason`.
- [P2-3] `scripts/templates/production-crop-comparison.html:495` — Ocena powstaje tylko dla komórek `visible` z quadem (`production_cell_evaluation.py:268-274`), więc zatwierdzona komórka occluded lub out_of_frame dostaje napis „Brak zatwierdzonego odniesienia”. Publikowany `contentState` nie jest renderowany. Propozycja: pokazać zatwierdzony stan komórki i informację, że pełności się dla niej nie ocenia.
- [P2-4] `services/worker/src/game_predictor_worker/images/comparison_production_crop_report.py:391` — TRAIN ze stanem `unavailable` znika ze strony bez licznika, a statystyki (`production-crop-comparison.html:334`) obejmują tylko pokazane zdjęcia. Filtr jest wymagany przez kontrakt publicznego JSON, ale agregat bez identyfikatorów niczego by nie ujawnił. Propozycja: dodać liczbę pominiętych źródeł TRAIN albo przyjąć ryzyko w raporcie odbioru.
- [P2-5] `services/worker/src/game_predictor_worker/images/comparison_production_crop_report.py:391` — Render jest wyłącznie plikowy, więc ochrona blind obowiązuje na moment capture (`services/api/src/game_predictor_api/storage/production_crop_capture.py:316-319`). Sesja blind zapisana po capture nie zablokuje późniejszego renderu tego samego raportu. Raport odbioru (`GRID_SYMBOL_CROP_PREVIEW_ACCEPTANCE_20261109.md:13`) nie wskazuje tej granicy dla nowego HTML. Propozycja: dopisać ograniczenie obok T1 P2-4 lub zalecić świeży capture przed publikacją.
- [P2-6] `apps/admin/src/features/model-quality/grid-content-canvas.tsx:307` — Przy wyłączonej warstwie obrysów kliknięcia na obrazie są zablokowane, zgodnie z literą T1 P2-7. Przycisk „Usuń obwiednię” i pola współrzędnych (`:638-664`) nadal zmieniają quad bez widocznego obrysu. Są to jawne kontrolki, więc skutek jest mały. Propozycja: wyłączyć je przy ukrytej warstwie albo przyjąć ryzyko.
- [P2-7] `services/worker/src/game_predictor_worker/images/comparison_production_crop_report.py:327` — Adapter porównuje konfigurację rastra z konfiguracją pary, ale nie sprawdza, że `paddingFraction` wynosi 0,08 i 0,0, choć etykiety 8% i 0% są stałe (`production-crop-comparison.html:547`). T2 ustawia te wartości poprawnie (`production_crop_comparison.py:222-225`), więc ryzyko dotyczy przyszłej zmiany kontraktu. Propozycja: dodać jawną asercję z lokalnym `unavailable`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Każdy punkt T4 planu ma implementację lub jawny warunek zależny od danych | niespełnione | Oryginał, siatka, obrysy, wejścia NN i 15 par: `comparison_production_crop_report.py:398-446`; brak dla błędnej geometrii: P1-1; przycięcia i sąsiad bez dowodu wykonania: P1-2 |
| Oryginał, siatka, content, input NN i 15 rastrów obecnych i porównywanych | spełnione | `comparison_production_crop_report.py:229`, `:343-352`; `production-crop-comparison.html:547`; test: `test_comparison_production_crop_report.py:190-205` |
| Porażki jawne; brak GT nie udaje jakości | niespełnione | Braki i ambiguous jawne: `test_comparison_production_crop_report.py:257-286`; brak GT bez oceny: `production-crop-comparison.html:495`; luka: P1-1 |
| PostgreSQL, Admin, lint, typy, build, docs/map i cold read | niezweryfikowane | Wyniki deklarowane w `ai_docs/quality/TASK-1173_VERIFICATION.md`; logi i receipt poza odczytem, polecenia nieuruchamiane |
| Historyczne kontrakty i ręczne korekty zachowane | spełnione | Rozdział trybów CLI: `scripts/render_grid_correction_comparison.py:224-257`; instrukcja blind bez zmian: `grid-content-canvas.tsx:160-162`; brak zapisów w adapterze |
| Właściwe testy, lint, typy i docs/map; niezależny audyt i receipt | niezweryfikowane | Ten raport jest audytem rundy 1 z werdyktem blokującym; receipt jeszcze nie istnieje |
| TRAIN i `visualExportAllowed` przed pikselem oraz public JSON | spełnione | `comparison_production_crop_report.py:391`, ochrona: `production_crop_capture.py:316-319`, test: `test_comparison_production_crop_report.py:208-241` |
| Follow-up T1 P2-7 | spełnione | `grid-content-canvas.tsx:101-104`, `:401-407`; test: `grid-content-reference.test.mjs:1688-1714`; ryzyko resztkowe: P2-6 |
| Follow-up T1 P2-8 | spełnione | `scripts/export_grid_content_preview.py:96-97`, `:191-203`; test: `services/api/tests/test_grid_content_preview_export.py:178-206` |
| Reguła LF dla raportów audytu | spełnione | `.gitattributes:12`; test `scripts/tests/test_audit_report_checkout.py:9-38`, odczytany bez uruchamiania |
| Ograniczenia T1–T3 wskazane w odbiorze | spełnione | Sekcja „Przyjęte ograniczenia” w `GRID_SYMBOL_CROP_PREVIEW_ACCEPTANCE_20261109.md` |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P1-1, P1-2, P2-1, P2-2, P2-3, P2-4, P2-5, P2-6, P2-7.

## Proponowane testy

- Dopasowanie niepoprawne geometrii modelu: w `services/worker/tests/test_comparison_production_crop_report.py` ustawić metryki pary na błąd i sprawdzić komunikat DOM. Polecenie: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_comparison_production_crop_report.py -k geometry`.
- Ocena przycięć i sąsiada: rozszerzyć fixture approved o obserwacje wariantów i dodać w `scripts/tests/verify_production_crop_report.mjs` asercje dla tekstów „Grafika przycięta”, „obce pole” i „obcy pełny symbol”. Polecenie: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_comparison_production_crop_report.py -k approved`.
- Rozróżnienie stylu obrysów fragmentów oraz komunikatu o niedostępnym klasyfikatorze, w tym samym teście DOM.
- Test interakcji dla usuwania i edycji numerycznej przy ukrytych obrysach, jeżeli P2-6 zostanie naprawione: `npm run test:geometry --workspace @game-predictor/admin`.

## Zakres przeglądu i ograniczenia

Przeczytano pakiet audytu, `AGENTS.md`, fragmenty planu, pełny eksport ordinary i Canvas, `production_crop_artifacts.py`, `production_crop_comparison.py`, `production_crop_capture.py`, `grid_content_preview.py` oraz potrzebne fragmenty `production_cell_evaluation.py` i `grid_correction_metrics.py`.

Nie uruchamiano testów, lintu, typecheck, builda, `docs:check`, `code-map:check` ani CLI, a wyniki z dokumentów weryfikacji są deklaracjami wykonawcy. Nie czytano zdjęć, operatorskiego HTML, publicznego JSON, bazy, logów w `artifacts/` ani `.tmp`.

Nie policzono SHA raportów. Na dysku starsze raporty z zakresu 1150–1169 mają CRLF, a raporty 1170–1172 go nie mają, co jest spójne z checkoutem przy autocrlf, lecz nie stanowi dowodu zgodności hashy poza scenariuszem testu. Wygląd strony w przeglądarce nie został oceniony.