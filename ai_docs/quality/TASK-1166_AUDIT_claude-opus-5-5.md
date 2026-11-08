Analiza jest zakończona, poniżej pełny raport R2.

# Audyt TASK-1166 — ocena zawartości produkcyjnych wycinków

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: 450f9ef11bc08aae5b9e9e5fbba89d1408a020ed oraz zamrożone zmiany niezacommitowane, data 2026-11-08
Runda: 2
SHA pakietu: 799b40d4dbedf78b007fcc339fe9cd9e7d2e3909c212bc69fbcb0b4f8de55204
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano poprawki P1-1 i P2-2…P2-5, zaakceptowane ryzyko P2-1 oraz statyczną lukę AC8. P1-1 jest usunięte, a świeżość REG nadal działa fail-closed. Poprawki P2-2…P2-5 są zgodne z kodem i granicami integracji. Nowe P2-6 dotyczy późnego wykrycia nadmiernego rozmiaru oraz kosztu pamięci i nie tworzy ścieżki fałszywego PASS.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/production_cell_reference.py:166` — pełny replay nadal działa przy każdej kontroli świeżości, także przy statusie i każdym właściwym źródle importu. Koszt rośnie z liczbą odczytów, a profilowania nie ma. Akceptacja ryzyka jest zasadna: cache kluczowany samym SHA raportu i detali pominąłby bieżące kontrole źródeł, assetów modelu i wsparcia. Ryzyko zapisano jawnie w `ai_docs/tasks/1166-production-cell-evaluation.md:259-262` oraz `ai_docs/quality/TASK-1166_VERIFICATION.md:204`.
- [P2-6] `services/worker/src/game_predictor_worker/images/grid_model_evaluation_handler.py:367-384` — ścieżka workera przekazuje już `verified_details`, więc limit 96 MiB z `production_cell_run.py:177` przestał w niej działać, a `_verify_details` czyta plik bez limitu. Wyzwalacz: detal roli powyżej 96 MiB. Skutek: job kończy się sukcesem, a raport jest później trwale nieświeży przez `production_cell_reference.py:153`. Dodatkowo `grid_model_evaluation_handler.py:493` parsuje i przetrzymuje dokumenty wszystkich gier, a wynik odrzuca, także dla zadań bez oceny zawartości. Poprawka: sprawdzać `st_size` przed odczytem w `_verify_details`, a końcową kontrolę wykonywać tylko na hashach.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| 1. Wspólny mianownik, renderer, float32→float64, u, ε | spełnione | Bez zmian od R1; `images/production_cell_evaluation.py:95-117` |
| 2. Stany, missing, valid_box, odrębne NNinput | spełnione | Bez zmian od R1; `images/production_cell_evaluation.py:272-292` |
| 3. Macierz, wiązanie, brak kompensacji; stabilne remisy | spełnione | `images/production_cell_evaluation.py:137-157`; `test_production_cell_matching.py:18-59` |
| 4. Bramka per gra, świeży REG | spełnione | `images/production_cell_run.py:191-212`; `domain/production_cell_evaluation.py:177-178,185`; producent pinów `storage/grid_correction_split.py:415-425,517-522` |
| 5. Niezależne przeliczenie A przed B | spełnione | `images/full_board_calibration_observations.py:180-204`; kolejność `training_core/grid_correction_metrics.py:213-218`; `images/production_cell_input.py:186-230` |
| 6. v6, para gate/rule, dyspozycja | spełnione | `domain/production_cell_evaluation.py:17-19,265-275` |
| 7. Świeżość cropu, replay, READ ONLY | spełnione | `storage/production_cell_reference.py:156-175`; ryzyko P2-1 |
| 8. Pion API/SDK | spełnione statycznie | DTO `schemas/grid_model_evaluations.py:360-413,468`; OpenAPI `openapi.json:7559,17061,17993`; SDK `types.gen.ts:4102,9372,9858`; wrapper i test żądania z pakietu |
| Limit 1800/1860 s, idle 60 s | spełnione | Bez zmian od R1 |

Domknięcie AC8: porównano pole po polu `ModelContentCounts` (9), `ContentRoleEvidence` (17), `ContentGameEvidence` (10), politykę (9), grę oraz raport (22 wymagane i 2 opcjonalne). Schemat v6, `ruleVersion`, `policyVersion`, dyskryminowane `rawQuality` v3/v4/v5 i typowane `contentEvaluation` są spójne na każdej warstwie. `attach_content` emituje ten sam kształt. Wrapper tylko reeksportuje sześć wygenerowanych typów, bez ręcznych definicji. Zawężenie kluczy `roles` do `string` w SDK jest mechaniczne i nie tworzy rozbieżnego typu.

## Listy zamknięte i otwarte

Zamknięte: P1-1, P2-2, P2-3, P2-4, P2-5.

Otwarte: P2-1, P2-6.

Dowody zamknięcia:

- **P1-1:** `expected_reg` obejmuje wyłącznie wybrane piny z `representative=true` i `eligibleBoards>0` (`production_cell_run.py:195-201`). Brak pinu, pusty zbiór, nadmiarowe użyte źródło albo brak kwalifikowanego źródła dają `freshRegression=false`. Kopia ma `representative=false`, a zdjęcie bez plansz `eligibleBoards=0`. Minima REG pozostały bez zmian.
- **P2-2:** ścieżka kanoniczna jest wymuszona (`production_cell_reference.py:162-164`), a `finish` przyjmuje te same dokumenty, które sprawdzono po SHA i odtworzono w replayu (`:169-173`). Worker parsuje dokładnie zweryfikowane bajty.
- **P2-3:** świadectwo A pochodzi wyłącznie z obserwatora zawartości, tylko przy `bound` i `matchAmbiguous=false`. Obserwator jest ustawiany dla tego samego zdjęcia przed kalibracją. Brak świadectwa pozostawia `geometry_proxy`.
- **P2-4:** minimum jest ograniczone do REG, a pierwszeństwo `and` nad `or` jest poprawne.
- **P2-5:** liczniki wartowników i `fsum` kosztów skończonych usuwają utratę precyzji przy porównaniu sum.

## Proponowane testy

- `services/api/tests/test_production_cell_evaluation.py`: REG z pięcioma pełnymi zdjęciami i 14 planszami. Obecny przypadek REG ma `fullPhotos=0`, więc nie izoluje minimum 15 plansz. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_production_cell_evaluation.py -k five_photo`.
- `services/worker/tests/test_production_cell_audit_regressions.py`: detal powyżej limitu rozmiaru przerywa job przed `finish`. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_production_cell_audit_regressions.py -k verified`.

## Zakres przeglądu i ograniczenia

Przeczytano różnice korekty i AC8 z pakietu, manifest, zmienione funkcje, testy P1-1 oraz P2-3…P2-5, a także producenta pinów, `hungarian` i importy modułów dołączanych przez nowy import `detail_path`. Nie czytano ponownie niezmienionych dużych klas ani całego SDK.

Audytor nie uruchamiał testów, generatora, kontroli OpenAPI, builda SDK ani usług. Wyniki testów pochodzą wyłącznie z deklaracji pakietu i nie zostały tu potwierdzone. Audytor nie przeliczał też hashy SHA manifestu, a kwalifikacja rzeczywistego modelu pozostaje poza dowodami.

Domknięcie AC8 dotyczy delty dostarczonej w pakiecie. Migawka statusu git wymienia też jako zmienione pliki `generated/client/*` i `generated/core/*`, których nie ma w delcie ani w manifeście. Pliki te mają w drzewie roboczym końce linii LF, ale bez dostępu do gita nie da się potwierdzić, czy zmiana dotyczy tylko końców linii.