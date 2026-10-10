# Audyt TASK-0953 — Przyrostowa kopia katalogów danych na D

Werdykt: REVISE
Audytor: gpt-6.1-sol, high
Wykonawca: claude-opus-5-5, high; odstępstwo od tabeli odnotowane w Outcome
Zakres: HEAD...f3429d8a50e3f3433f42f72dd62ef2fad919f523 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-10
Runda: 5

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Poprawka zamyka znalezisko P1-8 dotyczące przekroczenia budżetu czasu podczas obsługi pustych plików i kończenia fazy. Zachowano zabezpieczenia Mirror, redakcję ścieżek `.tooling` oraz rozdzielenie nazw manifestów. Pozostaje naruszenie zakresu: jawny wybór przez `-Directories` pozwala kopiować `node_modules` i `.venv`.

## Znaleziska

### P0

Brak.

### P1

- [P1-9] `scripts/sync_data_directories_to_d.ps1:674` — Jawnie wybrane wpisy trafiają do kopii bez sprawdzenia klasy odtwarzalności. Wywołanie z `-Directories "node_modules"` albo `-Directories ".venv"` wybiera taki katalog, mimo zakazu jego kopiowania w `ai_docs/tasks/completed/0953-disk-d-data-directory-sync.md:130`. Wykluczenia w `Get-EntryFiles` dotyczą dzieci wybranego korzenia (`scripts/sync_data_directories_to_d.ps1:335`); analogicznie robocopy otrzymuje ten korzeń jako źródło (`scripts/sync_data_directories_to_d.ps1:503`). Skrypt może więc skopiować zakazane dane i zakończyć się sukcesem. Przed dodaniem wpisu zastosować wspólną kontrolę wykluczeń obejmującą również wybrany korzeń i ścieżki wewnątrz wykluczonych katalogów. Odrzucać takie wybory albo pomijać je z ostrzeżeniem.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Inwentarz, oznaczanie nowych wpisów i domyślny zbiór zachowywany | spełnione | `scripts/sync_data_directories_to_d.ps1:296`, `:643`, `:678`; wyniki inwentarza opisano w Outcome |
| Worktree’y wykluczone przy jawnym wyborze i wyborze rodzica | spełnione | `scripts/sync_data_directories_to_d.ps1:214`, `:249`, `:499`, `:668` |
| Initial: kod 0, liczniki i INCOMPLETE przy błędach | spełnione | `scripts/sync_data_directories_to_d.ps1:743`, `:747`, `:808`, `:821`; pierwszy zapisany SUMMARY kończy się INCOMPLETE |
| VerifyOnly z manifestem ignoruje nowe pliki i wykrywa zmiany | spełnione | `scripts/sync_data_directories_to_d.ps1:591`, `:611`, `:614`; próby opisano w Outcome |
| Drugi Initial kopiuje tylko nowe lub zmienione pliki | spełnione | Odczyt `D:\game_predictor_backup\sync-logs\20261010-020051-Initial\SUMMARY.txt`: trzy skopiowane pliki `.runtime`, RESULT: OK |
| Mały Final: równe SHA-256; VerifyOnly wykrywa brak | spełnione | Odczyt SUMMARY przebiegu `20261010-020051-Final`: zero różnic, RESULT: OK; próbę brakującego pliku opisano w Outcome |
| Mirror bez Final i potwierdzenia odmawia | spełnione | `scripts/sync_data_directories_to_d.ps1:531` |
| `.tooling` skopiowane; kontrola z D nie zgłasza brakujących plików toolchainu | spełnione | SUMMARY Initial: 12 181 plików `.tooling`; wynik kontroli środowiska opisano w Outcome |
| Brak ujawniania nazw i zawartości kluczy podpisu | spełnione | `scripts/sync_data_directories_to_d.ps1:151`, `:200`, `:476`, `:669`; opisane próby błędów ze spacjami i apostrofami |
| Zakres wyłączony: brak kopiowania `node_modules` i `.venv` | niespełnione | P1-9; `scripts/sync_data_directories_to_d.ps1:674` |

## Listy zamknięte i otwarte

Zamknięte:

- P1-8 — kontrola deadline obejmuje wejście i wyjście hashowania, każdy element manifestu, podkatalogi licznika wykluczeń oraz zamknięcie budżetu: `scripts/sync_data_directories_to_d.ps1:182`, `:194`, `:267`, `:291`, `:399`.
- P0-3 — zachowano redakcję całego fragmentu po `.tooling\` oraz zapis wyłącznie zredagowanego stdout: `scripts/sync_data_directories_to_d.ps1:156`, `:476`.
- P0-6 — zachowano skrót pełnej ścieżki w nazwie pliku wynikowego: `scripts/sync_data_directories_to_d.ps1:207`.

Otwarte: P1-9.

## Proponowane testy

Dodać scenariusze do proponowanego `scripts/test_sync_data_directories_to_d.ps1`, uruchamianego poleceniem:

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_sync_data_directories_to_d.ps1`

- Jawny wybór `node_modules`, `.venv` i podkatalogów tych korzeni nie kopiuje żadnego pliku.
- Zachowywany katalog `work` nadal kopiuje się poprawnie, a jego zagnieżdżony `node_modules` pozostaje wykluczony.
- Zachować próby przekroczonego deadline dla pustego pliku, manifestu i zamknięcia budżetu opisane po rundzie 4.

## Zakres przeglądu i ograniczenia

Przeczytano brief, skrypt, task, odpowiednie fragmenty planu i dokumentacji procesu, zmiany dokumentacyjne oraz wcześniejsze raporty audytu. Odczytano podsumowania dwóch przebiegów Initial i małego Final. Zmiany dotyczące TASK-0954 pozostawiono poza oceną.

Nie uruchamiano testów, synchronizacji, kopiowania, usuwania ani usług. Wyniki prób scratchpad i kontroli środowiska oceniono na podstawie Outcome. Nie odczytywano kluczy podpisu. Pełny Final pozostaje zakresem TASK-0955. Znalezisko P1-9 wynika z analizy przepływu sterowania; nie wykonywano reprodukcji.