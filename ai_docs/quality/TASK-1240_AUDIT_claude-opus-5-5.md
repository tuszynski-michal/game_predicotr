# Audyt TASK-1240: wykorzystanie częściowych korekt siatki i uczciwe porównanie modeli historycznych

Werdykt: PASS
Audytor: claude-opus-5-5, przegląd statyczny
Wykonawca: brief nie podaje modelu wykonawcy; wiadomo tylko, że należy do innej rodziny modeli niż audytor
Zakres: 68ac66e7de54565c20144ba9b049d5621c620abb...68ac66e7de54565c20144ba9b049d5621c620abb oraz zmiany niezacommitowane z pathspec briefu, data 2026-11-17
Runda: 2
SHA pakietu: b1b8342f334bdb4c6bb41225688383f8a144779be09c76a9dfcc952284387116
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

W rundzie 2 sprawdziłem poprawki czterech znalezisk z rundy 1, którą przeprowadzono jeszcze pod numerem TASK-1239. Zrobiłem to na przejętym starterze, w funkcji lejka, w nowym receipcie lejka v3 i w testach. Jedyne P1 jest zamknięte. Lejek TRAIN rozkłada się teraz dokładnie: 428 = 49 + 367 + 2 + 10. Liczba 10 zgadza się z liczbą zdjęć TRAIN zużytych przez trening screen+grid. Brak szczegółowych powodów odrzucenia w manifeście jest zapisany jawnie. Powiązanie polecenia z grą przez plik `.game.json` działa fail-closed i ma testy. Receipt v3 wiąże wynik z SHA manifestu i z kopią źródła, a jego funkcje są identyczne z bieżącym skryptem. Zostały dwa drobne ryzyka P2 w starterze: rozwiązywanie względnej ścieżki `-CommandFile` i odzyskiwanie po przerwaniu między zapisem polecenia a zapisem metadanych.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-4] `scripts/Start-GridCorrectionLearning.ps1:20`. `[IO.Path]::GetFullPath($CommandFile)` rozwiązuje ścieżkę względną według katalogu bieżącego procesu .NET (`[Environment]::CurrentDirectory`), a nie bieżącej lokalizacji PowerShell (`$PWD`). Po `Set-Location` w tej samej sesji te katalogi mogą być różne. Względny `-CommandFile` może wtedy wskazać inny katalog niż zamierzony. Przy kolejnym uruchomieniu w innej sesji ta sama nazwa może wskazać nieistniejący plik. Skrypt utworzy wtedy nowy klucz idempotencji i wyśle nowy POST. To słabsza wersja ryzyka, które zamyka komentarz w linii 22 („an upgrade must never silently start another run”). Dotyczy tylko ścieżek względnych i nie ma wpływu na ścieżkę domyślną. Poprawka: użyć `$PSCmdlet.GetUnresolvedProviderPathFromPSPath($CommandFile)` albo odrzucać ścieżki nieabsolutne. Można też jawnie zaakceptować to ryzyko w dokumentacji operatora.
- [P2-5] `scripts/Start-GridCorrectionLearning.ps1:56` i `:83-86`. Nowy plik niestandardowy powstaje w linii 56, a jego metadane dopiero w linii 86, po sprawdzeniu trybu, klucza i SHA. Jeśli proces zostanie przerwany między tymi zapisami, następne uruchomienie trafi na `createdCommand = false` bez metadanych. Skończy się wtedy błędem „Existing custom command has no game binding” (linia 84). Zachowanie jest bezpieczne, bo POST nie zostaje wysłany. Operator traci jednak automatyczny dostęp do klucza i musi ręcznie odtworzyć metadane albo użyć nowego pliku. Poprawka: zapisywać metadane zaraz po utworzeniu polecenia, w tej samej gałęzi co linia 56 i przed parsowaniem. Można też zaakceptować ryzyko, bo okno jest krótkie i działa fail-closed.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Dokładne zamrożone liczniki wyjaśniają wynik 10 zdjęć i niewykorzystane poprawne korekty | spełnione | `scripts/compare_grid_historical_models.py:92-128` liczy pełne (`==9`), częściowe (`1..8`) i puste (`0`) reprezentanty, aliasy oraz uzgodnienia. `artifacts/TASK-1240-comparison/data-funnel-v3.json:1` podaje: `fullTrainRepresentatives=10`, `partialTrainPhotos=367`, `emptyTrainRepresentatives=2`, `nonRepresentativeAliases=49`, `trainAssignmentsReconciled=true` oraz `screenTrainCountReconciled=true` przy `usedCounts.TRAIN.photos=10`. `reasonProvenance` jawnie stwierdza brak szczegółowych powodów w manifeście. Test: `scripts/tests/test_grid_historical_comparison.py:49`. |
| Nowe polecenia domyślnie wybierają grid-only, a jawny tryb detektora nadal działa | spełnione | `scripts/Start-GridCorrectionLearning.ps1:5`, `:49`; test `scripts/tests/test_partial_grid_learning_starter.py:81-95` |
| Stare polecenia nie są przepisywane, a niezgodne opcje kończą się błędem bez POST | spełnione | Sprawdzenia trybu, klucza i powiązania z grą są w `scripts/Start-GridCorrectionLearning.ps1:61-88`, przed pobraniem OpenAPI (`:91`) i POST (`:99`). Testy w `scripts/tests/test_partial_grid_learning_starter.py`: `:97`, `:119`, `:127`, `:134`, `:147`, `:157`. Oryginał (`artifacts/TASK-1240-original-starter.ps1.txt:28`) nadal ma na sztywno `screen+grid`, a nowa ścieżka domyślna jest z nim zgodna (`:17` wobec `:23` w nowym skrypcie). |
| Częściowe cele są używalne w grid-only, a nieoznaczone plansze nie są negatywami ani wyciekiem | niezweryfikowane statycznie | Kod konsumenta danych się nie zmienił. Wykonawca powołuje się na istniejące testy datasetu (7 PASS) oraz podglądu i rekomendacji (5 PASS), których nie uruchamiałem. |
| Kandydat i modele historyczne mają porównywalne dowody związane sumami kontrolnymi na tych samych zdjęciach, a reguła wyboru i ograniczenia są ujawnione | spełnione | `scripts/compare_grid_historical_models.py` sprawdza rodzinę, SHA deskryptora i `input_sha256`, a `historical-selection.json` zapisuje przed REGRESSION. `ai_docs/quality/TASK-1240_COMPARISON_EVIDENCE.json` przypina artefakty i receipt lejka v3. Liczby w raporcie zgadzają się z JSON: 45/45, 43 i 42, 17 i 18, suma 60/60, spadek błędu REG o około 2,7%. |
| Testy, lint, typy, dokumentacja, mapy i audyt Claude przechodzą | niezweryfikowane | Kryterium jest jawnie otwarte w pliku taska. Testów nie uruchamiałem. Mapy kodu leżą poza pathspec pakietu. |

## Listy zamknięte i otwarte

Zamknięte: P1-1 (dokładny bilans TRAIN i jawne pochodzenie powodów w `compare_grid_historical_models.py:92-128` oraz `data-funnel-v3.json`), P2-1 (powiązanie `.game.json` z grą, kluczem i SHA w `Start-GridCorrectionLearning.ps1:75-88`, testy `:147` i `:157`), P2-2 (receipt v3 z `sourceSha256` i kopią źródła, której funkcje lejka i receiptu są identyczne z `compare_grid_historical_models.py:92-153`), P2-3 (ryzyko jawnie zaakceptowane, komenda zapisana w Outcome taska).

Otwarte: P2-4, P2-5.

## Proponowane testy

- `scripts/tests/test_partial_grid_learning_starter.py`: dodać przypadek, w którym zapisane polecenie zmieniono po powstaniu `.game.json`. Niezgodność `commandSha256` powinna dać błąd bez żadnego wywołania. Komenda: `.\.venv\Scripts\python.exe -m pytest scripts/tests/test_partial_grid_learning_starter.py`.
- Ten sam plik: dodać przypadek, w którym istnieje `.game.json`, ale brakuje polecenia. Oczekiwany jest błąd z linii 39, brak nowego klucza i brak wywołań.
- Ten sam plik: dodać przypadek z kontraktem OpenAPI bez ścieżki `/api/v1/admin/games/{game_id}/grid-correction-learning`, żeby potwierdzić fail-closed przy braku `$ref`.
- Jeśli P2-4 zostanie naprawione: test z względnym `-CommandFile` po `Set-Location` w harnessie. Oczekiwane jest rozwiązanie ścieżki względem `$PWD`.

## Zakres przeglądu i ograniczenia

Przeczytałem cały pakiet: plik taska, raport jakości, JSON dowodów, raport i receipt z rundy 1 (wtedy jako TASK-1239), różnice w dokumentacji wymagań i architektury, starter, oba skrypty Python i oba pliki testów. Poza pakietem przeczytałem tylko to, co było potrzebne do oceny poprawek: `artifacts/TASK-1240-original-starter.ps1.txt`, `artifacts/TASK-1240-comparison/data-funnel-v3.json` i fragment `data-funnel-v3.source.txt` (linie 88–157). Porównałem ten fragment tekstowo z bieżącym `frozen_funnel` i `write_funnel_evidence`.

Nie uruchamiałem testów, lintu ani mypy. Nie liczyłem sum SHA i nie otwierałem zamrożonego manifestu kohorty. Wartości lejka przyjmuję więc z artefaktu v3 i jego spójności z kodem. Zachowanie PowerShell ocenałem wyłącznie statycznie. Map kodu i `CURRENT_STATE.md` nie oceniałem, bo leżą poza pathspec pakietu.