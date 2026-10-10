# Audyt TASK-0953 - Przyrostowa kopia katalogów danych na D

Werdykt: REVISE
Audytor: Codex, etykieta briefu: gpt-6.1-sol, high
Wykonawca: claude-opus-5-5, reasoning nieodnotowany w Outcome
Zakres: HEAD...f3429d8a50e3f3433f42f72dd62ef2fad919f523 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-10
Runda: 4

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano zgodność zmian z taskiem i planem oraz poprawki po rundzie 3. Zamknięto znaleziska dotyczące redakcji nazw kluczy i kolizji nazw manifestów. Wspólny budżet czasu wdrożono, ale nadal istnieje ścieżka zakończenia sukcesem po jego przekroczeniu. Otwarte P1 blokuje commit.

## Znaleziska

### P0

Brak.

### P1

- [P1-8] `scripts/sync_data_directories_to_d.ps1:393` - Limit czasu pozostaje niepełny. `Build-Manifest` nie sprawdza deadline między plikami, a `Get-FileSha256` sprawdza go wyłącznie po odczytaniu niepustego bloku (`scripts/sync_data_directories_to_d.ps1:186`). Dla pustych plików kontrola czasu nie zachodzi. Jeżeli budżet wyczerpie się podczas końcowego hashowania zbioru pustych plików, oba manifesty mogą zostać zbudowane i porównane, po czym `Stop-EntryBudget` resetuje deadline bez sprawdzenia przekroczenia (`scripts/sync_data_directories_to_d.ps1:286`). Wynikiem może być kod 0 zamiast wymaganego kodu 2. Dodatkowo pętla podkatalogów w `Get-FileCount` nadal nie kontroluje czasu podczas enumeracji dzieci (`scripts/sync_data_directories_to_d.ps1:263`). Dodać kontrolę czasu na wejściu i wyjściu hashowania, podczas iteracji manifestu i podkatalogów oraz przed zamknięciem budżetu wpisu.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Klasyfikacja inwentarza, oznaczanie nowych wpisów i domyślny zbiór zachowywany | spełnione | `scripts/sync_data_directories_to_d.ps1:291`, `:651`, `:672`; wyniki inwentaryzacji opisano w Outcome |
| Worktree’y wykluczone przy jawnym wyborze i wyborze rodzica | spełnione | `scripts/sync_data_directories_to_d.ps1:246`, `:339`, `:493`, `:662`; scenariusze zapisano w Outcome |
| Initial: liczniki, kod 0 i INCOMPLETE przy błędach | spełnione | `scripts/sync_data_directories_to_d.ps1:737`, `:741`, `:815`; odczyt SUMMARY pierwszego przebiegu: `RESULT: INCOMPLETE` |
| Zapisany manifest ignoruje nowe pliki i wykrywa zmiany | spełnione | `scripts/sync_data_directories_to_d.ps1:585`, `:598`, `:608`; próby opisano w Outcome |
| Drugi Initial kopiuje tylko nowe lub zmienione pliki | spełnione | Odczyt `20261010-020051-Initial/SUMMARY.txt`: 3 skopiowane pliki `.runtime`, pozostałe pominięte, `RESULT: OK` |
| Mały Final daje równe manifesty; VerifyOnly wykrywa brak | spełnione | Odczyt `20261010-020051-Final/SUMMARY.txt`: trzy wpisy bez różnic, `RESULT: OK`; próbę brakującego pliku opisano w Outcome |
| Mirror bez Final i potwierdzenia odmawia | spełnione | `scripts/sync_data_directories_to_d.ps1:525` |
| `.tooling` skopiowane; kontrola plików toolchainu z D | spełnione | SUMMARY pierwszego Initial: 12 181 skopiowanych plików; wynik kontroli środowiska zapisano w Outcome |
| Brak nazw i zawartości kluczy podpisu w logach i Outcome | spełnione | `scripts/sync_data_directories_to_d.ps1:156`, `:197`, `:470`, `:663`; regresję z apostrofem opisano w Outcome |
| Final odrzuca błędy i rozbieżności; Mirror sprawdza kompletność odczytu | spełnione | `scripts/sync_data_directories_to_d.ps1:529`, `:740`, `:764`, `:801` |
| Osobne manifesty wpisów o wcześniej kolidujących nazwach | spełnione | `scripts/sync_data_directories_to_d.ps1:204`; różne nazwy wynikowe potwierdzono w Outcome |
| Limit czasu całego wpisu i zakończenie kodem 2 | niespełnione | `scripts/sync_data_directories_to_d.ps1:186`, `:263`, `:286`, `:393`; P1-8 |

## Listy zamknięte i otwarte

Zamknięte:

- P0-3 - redakcja obejmuje cały fragment po `.tooling\`, również apostrofy i spacje; surowy stdout robocopy nie jest zapisywany: `scripts/sync_data_directories_to_d.ps1:156`, `:470`.
- P0-6 - nazwy wyników zawierają skrót pełnej ścieżki względnej, rozdzielający `work/a_b` i `work/a/b`: `scripts/sync_data_directories_to_d.ps1:204`.

Otwarte: P1-8 - częściowo poprawione. Budżet jest współdzielony między fazami, lecz nie wszystkie końcowe operacje sprawdzają jego wyczerpanie.

## Proponowane testy

Dodać deterministyczne scenariusze do proponowanego `scripts/test_sync_data_directories_to_d.ps1`, uruchamianego poleceniem `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_sync_data_directories_to_d.ps1`:

- Zbudowanie manifestu istniejącego pustego pliku przy już przekroczonym deadline musi rzucić `TimeoutException`.
- Wyczerpanie budżetu podczas ostatniej fazy wpisu musi zakończyć przebieg kodem 2, również gdy manifesty są równe.
- Kontrolowana enumeracja podkatalogów w `Get-FileCount` musi zostać przerwana podczas iteracji dzieci, bez oczekiwania na jej zakończenie.

## Zakres przeglądu i ograniczenia

Przeczytano brief, skrypt, task, odpowiednie fragmenty planu, dokumentację procesu, instrukcję utrzymania danych, zmiany dokumentacyjne oraz raport rundy 3. Potwierdzono zgodność skryptu i taska na dysku z kopiami zawartymi w briefie. Odczytano istniejące podsumowania dwóch przebiegów Initial i małego Final.

Nie uruchamiano synchronizacji, testów, kopiowania, usuwania ani usług. Próby scratchpad oraz kontrole formatowania, składni, dokumentacji i środowiska oceniono na podstawie Outcome. Znalezisko P1-8 wynika z analizy przepływu sterowania; nie wykonywano reprodukcji. Nie odczytywano rzeczywistych kluczy podpisu. Pełny Final pozostaje zakresem TASK-0955.