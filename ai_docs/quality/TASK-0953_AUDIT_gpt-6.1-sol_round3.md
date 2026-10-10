# Audyt TASK-0953 — Przyrostowa kopia katalogów danych na D

Werdykt: REVISE
Audytor: Codex, etykieta briefu: gpt-6.1-sol, high
Wykonawca: claude-opus-5-5, reasoning nieodnotowany w Outcome
Zakres: HEAD...f3429d8a50e3f3433f42f72dd62ef2fad919f523 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-10
Runda: 3

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano aktualny skrypt, zgodność z taskiem i planem oraz poprawki po rundzie 2. Zamknięto blokady dotyczące błędów kopiowania przed Mirror, dopuszczania nadmiarowych plików w Final i odrzucania nowych gałęzi przez weryfikację manifestu. Nadal pozostają luki w redakcji nazw kluczy i ograniczeniu czasu enumeracji; dodatkowo nazwy manifestów mogą kolidować. Otwarte P0 i P1 blokują commit.

## Znaleziska

### P0

- [P0-3] `scripts/sync_data_directories_to_d.ps1:156` — Redakcja kończy dopasowanie na apostrofie, który może występować w nazwie katalogu Windows. Dla fikcyjnej ścieżki `.tooling/operator's keys/upload.jks` pozostaje fragment `'s keys/upload.jks`, ujawniający pełną nazwę klucza. `Write-ProtectedLog` zapisuje taki wynik w linii 437. Poprawka obsługuje spacje i eliminuje surowy zapis przez `/LOG`, ale nadal nie spełnia zakazu ujawniania nazw kluczy. Redagować cały pozostały fragment ścieżki, także przy apostrofach w nazwach.

- [P0-6] `scripts/sync_data_directories_to_d.ps1:205` — `Get-SafeName` nie zapewnia unikalności: `work/a_b` i `work/a/b` otrzymują tę samą nazwę `work_a_b`. Oba wpisy są dopuszczalne w `-Directories`. Zapis drugiego wpisu nadpisuje manifest pierwszego w linii 717, a także jego log i pozostałe wyniki. Późniejsze `-VerifyOnly -Manifest <katalog>` odczytuje tylko zachowany manifest, więc może zgłosić sukces mimo utraty lub zmiany plików pierwszego wpisu. Dodać do nazw wynikowych skrót pełnej ścieżki względnej albo wykrywać kolizje przed kopiowaniem.

### P1

- [P1-8] `scripts/sync_data_directories_to_d.ps1:253` — Limit czasu nadal nie obejmuje całej enumeracji. `Get-FileCount` materializuje rekurencyjne `EnumerateFiles(AllDirectories)` bez kontroli deadline; wywołuje go liczenie wykluczeń w linii 310. Również pętle enumeracji katalogów i plików w liniach 296 i 315 sprawdzają czas dopiero przy następnym obrocie zewnętrznej pętli. Duży wykluczony podkatalog może zatem blokować wykonanie po upływie limitu. Dodatkowo deadline jest resetowany między preflightem w linii 649 a kopiowaniem w linii 686. Kontrolować czas podczas enumeracji i liczenia wykluczeń oraz rozliczać cały przebieg wpisu jednym budżetem.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Inwentarz, nowe wpisy i domyślny zbiór zachowywany | spełnione | `scripts/sync_data_directories_to_d.ps1:258`, `:613`, `:634`; Outcome opisuje 98 zachowywanych wpisów |
| Worktree’y wykluczone także przy jawnym wyborze i wyborze rodzica | spełnione | `scripts/sync_data_directories_to_d.ps1:243`, `:305`, `:455`, `:624` |
| Initial: liczniki, kod 0 i INCOMPLETE przy błędach | spełnione | `scripts/sync_data_directories_to_d.ps1:697`, `:701`, `:774`; odczytane SUMMARY pierwszego przebiegu: INCOMPLETE |
| Weryfikacja zapisanego manifestu ignoruje nowe pliki i wykrywa zmiany | spełnione | `scripts/sync_data_directories_to_d.ps1:547`, `:568`, `:570`; próby opisane w Outcome |
| Drugi Initial kopiuje tylko nowe lub zmienione pliki | spełnione | Odczyt `20261010-020051-Initial/SUMMARY.txt`: 3 skopiowane pliki `.runtime`, RESULT: OK |
| Mały Final: równe manifesty; VerifyOnly wykrywa brak pliku | spełnione | Odczyt `20261010-020051-Final/SUMMARY.txt`: RESULT: OK; próbę brakującego pliku opisano w Outcome |
| Mirror bez Final i potwierdzenia odmawia | spełnione | `scripts/sync_data_directories_to_d.ps1:487` |
| `.tooling` skopiowane; kontrola toolchainu z D | spełnione | SUMMARY Initial: 12 181 skopiowanych plików; wynik kontroli z D zapisano w Outcome |
| Brak nazw kluczy w logach | niespełnione | `scripts/sync_data_directories_to_d.ps1:156`; P0-3 |
| Final odrzuca rozbieżności i nie dopuszcza AllowExtras | spełnione | `scripts/sync_data_directories_to_d.ps1:491`, `:700`, `:760` |
| Mirror odmawia usuwania przy błędach kopiowania lub odczytu | spełnione | `scripts/sync_data_directories_to_d.ps1:724` |
| Osobne, trwałe manifesty każdego wybranego wpisu | niespełnione | `scripts/sync_data_directories_to_d.ps1:205`, `:717`; P0-6 |
| Limit czasu całego wpisu i zakończenie kodem 2 | niespełnione | `scripts/sync_data_directories_to_d.ps1:253`, `:649`, `:686`; P1-8 |

## Listy zamknięte i otwarte

Zamknięte:

- P0-1 — Mirror sprawdza status kopiowania i błędy odczytu przed usuwaniem: `scripts/sync_data_directories_to_d.ps1:724`.
- P0-5 — Final odrzuca `-AllowExtras`, a nadmiarowe pliki powodują błąd: `scripts/sync_data_directories_to_d.ps1:491`, `:760`.
- P1-7 — zapisany manifest jest weryfikowany przez wymagane pliki; błędy nowych gałęzi nie odrzucają kompletnego zbioru: `scripts/sync_data_directories_to_d.ps1:547`, `:568`.

Otwarte: P0-3 i P1-8 — częściowo poprawione; P0-6 — nowe znalezisko.

## Proponowane testy

Dodać izolowane scenariusze do proponowanego `scripts/test_sync_data_directories_to_d.ps1`, uruchamianego poleceniem `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_sync_data_directories_to_d.ps1`:

- Fikcyjny klucz `.tooling/operator's keys/upload.jks`, również z wymuszonym błędem odczytu. Żaden log nie może zawierać `upload.jks`.
- Dwa wpisy `work/a_b` i `work/a/b`. Oba manifesty muszą przetrwać; zmiana pliku w każdym wpisie osobno musi powodować błąd weryfikacji zapisanego katalogu manifestów.
- Kontrolowane opóźnienie enumeracji wykluczonego katalogu przy krótkim `-TimeoutSeconds`. Oczekiwane przerwanie kodem 2 bez oczekiwania na zakończenie pełnego liczenia.
- Kontrolowane opóźnienia preflightu i kopiowania jednego wpisu. Łączny czas musi respektować jeden limit.

## Zakres przeglądu i ograniczenia

Przeczytano brief, skrypt, task, odpowiednie fragmenty planu, dokumentację procesu, instrukcję utrzymania danych i raport rundy 2. Potwierdzono zgodność skryptu i taska na dysku z kopiami w briefie. Odczytano istniejące podsumowania dwóch przebiegów Initial oraz małego Final.

Nie uruchamiano synchronizacji, testów, kopiowania, usuwania ani usług. Próby scratchpad oceniono na podstawie Outcome. Przykłady redakcji i kolizji wynikają z analizy przekształceń tekstu; nie potwierdzają rzeczywistego wycieku ani utraty danych. Nie odczytywano rzeczywistych kluczy podpisu. Pełny Final pozostaje zakresem TASK-0955.