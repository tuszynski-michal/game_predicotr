# Audyt TASK-0953 - Przyrostowa kopia katalogów danych na D

Werdykt: REVISE
Audytor: gpt-6.1-sol, high
Wykonawca: claude-opus-5-5; reasoning niepodany w Outcome
Zakres: HEAD...f3429d8a50e3f3433f42f72dd62ef2fad919f523 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-10
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano skrypt synchronizacji, konfigurację npm, dokumentację oraz zgodność z taskiem i planem. Mechanizmy porównywania manifestów, obsługi błędów i ochrony nazw kluczy są zaimplementowane. Pozostaje luka w zakresie domyślnej kopii: `v7-output/` został skopiowany osobno, ale domyślny przebieg `Final` nie obejmie jego późniejszych zmian.

## Znaleziska

### P0

- [P0-1] `scripts/sync_data_directories_to_d.ps1:708` — Domyślna lista kopiowanych wpisów pochodzi wyłącznie z inwentarza `git ls-files --others --ignored` tworzonego w linii 321. Katalog `v7-output/` jest nieśledzony, lecz nieignorowany, więc nie trafia do tej listy. Potwierdzają to odczyty git na C oraz `ai_docs/tasks/completed/0953-disk-d-data-directory-sync.md:302`, gdzie zapisano jego osobne kopiowanie. Tymczasem Goal wymienia go w domyślnym zakresie, a TASK-0955 przewiduje zwykłe `-Mode Final`. Zmiany tego katalogu po pierwszej kopii pozostaną na C, bez aktualizacji kopii i bez manifestu B1, mimo możliwego wyniku `OK`. Należy uzupełnić domyślny inwentarz o istniejący `v7-output/` jako zachowywany wpis, zachowując zgodność inwentarza, wyboru katalogów i manifestów. Dodać regresję dla nieśledzonego, nieignorowanego `v7-output/`.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Klasyfikacja wpisów ignorowanych, domyślny wybór zachowywanych i wykluczenie worktree’ów | spełnione | `scripts/sync_data_directories_to_d.ps1:320`, `:273`, `:696`, `:708`; istniejący inwentarz na D nie zawiera wpisów oznaczonych `new`. |
| Domyślny zakres Goal obejmuje `v7-output/` | niespełnione | `scripts/sync_data_directories_to_d.ps1:708`; P0-1. Odczyt git zwraca `v7-output/` wyłącznie wśród wpisów nieśledzonych i nieignorowanych. |
| Kontrakt `Initial`, liczniki i znacznik `INCOMPLETE` | spełnione | `scripts/sync_data_directories_to_d.ps1:494`, `:773`, `:775`, `:851`; ocena statyczna. |
| `-VerifyOnly -Manifest` ignoruje nowe pliki celu i wykrywa zmienione | spełnione | `scripts/sync_data_directories_to_d.ps1:618`, `:641`, `:650`; sprawdzane są zapisane klucze. |
| Drugi przebieg `Initial` kopiuje tylko nowe lub zmienione pliki | niezweryfikowane | Outcome deklaruje trzy skopiowane pliki i kod 0: `ai_docs/tasks/completed/0953-disk-d-data-directory-sync.md:323`. Nie powtarzano przebiegu. |
| Test `Final` daje równe manifesty; `-VerifyOnly` wykrywa brak pliku | niezweryfikowane | Mechanizmy: `scripts/sync_data_directories_to_d.ps1:466`, `:791`; wyniki prób deklarowane w Outcome, bez ponownego wykonania. |
| Odmowa `-Mirror` bez wymaganego trybu i potwierdzenia | spełnione | `scripts/sync_data_directories_to_d.ps1:557`. |
| Kopia `.tooling/` i kontrola plików toolchainu z D | niezweryfikowane | Deklaracje wykonawcy: `ai_docs/tasks/completed/0953-disk-d-data-directory-sync.md:320`, `:329`. |
| Ochrona nazw i zawartości kluczy podpisu | spełnione | Redakcja i zapis wyłącznie chronionego tekstu: `scripts/sync_data_directories_to_d.ps1:151`, `:200`, `:502`; ocena statyczna. |
| Limit czasu per wpis i kod 2 po przekroczeniu | spełnione | `scripts/sync_data_directories_to_d.ps1:308`, `:605`, `:642`, `:829`; ocena statyczna. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P0-1.

## Proponowane testy

- Dla `scripts/sync_data_directories_to_d.ps1` przygotować małe repozytorium testowe z ignorowanym `work/` oraz nieśledzonym, nieignorowanym `v7-output/`. Uruchomić `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_data_directories_to_d.ps1 -Source $src -Destination $dst -LogRoot $logs -Mode Initial`, bez `-Directories`. Oba katalogi muszą zostać skopiowane.
- Dopisać plik w testowym `v7-output/`, następnie uruchomić tę samą komendę z `-Mode Final`. Nowy plik musi znaleźć się w celu i manifeście SHA-256. Po zmianie tego pliku w celu `-VerifyOnly -Manifest $finalRun` musi zwrócić kod 1 i wskazać plik.

## Zakres przeglądu i ograniczenia

Przeczytano brief, pełny skrypt, task z Outcome, zmiany konfiguracji i dokumentacji oraz właściwe fragmenty planu i zasad procesu. Potwierdzono, że aktualny skrypt odpowiada kopii w briefie. Pomocniczo odczytano istniejący inwentarz na D, status git, historię i klasyfikację `v7-output/` na C.

Nie uruchamiano synchronizacji, usuwania, testów, usług ani kontroli środowiska. Wyniki wykonania opisane w Outcome pozostają deklaracjami wykonawcy. Pełny przebieg `Final` na danych operatora należy do TASK-0955.