# Audyt TASK-0953 - Przyrostowa kopia katalogów danych na D

Werdykt: REVISE
Audytor: gpt-6.1-sol, high
Wykonawca: claude-opus-5-5, reasoning nieodnotowany w Outcome
Zakres: HEAD...f3429d8a50e3f3433f42f72dd62ef2fad919f523 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-10
Runda: 1

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano skrypt, dokumentację, zakres taska i fragment zaakceptowanego planu. Zapisane podsumowania potwierdzają przyrostowy przebieg Initial oraz poprawne porównanie SHA-256 trzech wybranych wpisów. Implementacja zawiera jednak możliwość usunięcia pliku obecnego w źródle, obejścia wykluczenia worktree’ów i ujawnienia nazw kluczy w logach. Otwarte znaleziska P0 i P1 blokują commit.

## Znaleziska

### P0

- [P0-1] `scripts/sync_data_directories_to_d.ps1:507` — Mirror usuwa każdy plik celu obecny na zatwierdzonej liście, zamiast wyłącznie plików z `comparison.Extra`. Przykład: źródło zawiera `work/a`, cel zawiera `work/a` i `work/b`, a wcześniejsza lista zatwierdza oba klucze. Skrypt usunie oba pliki, lecz usunie z manifestu w pamięci tylko `work/b`, przez co może zakończyć się wynikiem OK mimo utraty `work/a` na D. Ograniczyć usuwanie do przecięcia zatwierdzonej listy i aktualnego zbioru Extra. Po usunięciu ponownie odczytać cel, porównać go i zapisać aktualny manifest docelowy; obecnie zapis następuje przed usuwaniem, w linii 494.

- [P0-2] `scripts/sync_data_directories_to_d.ps1:420` — Zakaz kopiowania worktree’ów działa tylko dla literalnie rozpoznanych wpisów. `-Directories ".claude"` kopiuje również `.claude/worktrees`, ponieważ wykluczenia przekazywane do robocopy nie zawierają tego korzenia. `-Directories ".\worktrees"` także omija kontrolę: normalizacja pozostawia `./worktrees`. To narusza wymaganie „nigdy w kopii” i przenosi pliki `.git` wskazujące C. Kanonizować ścieżki, sprawdzać ich zawieranie w odpowiednich korzeniach oraz wykluczać oba korzenie podczas każdej rekurencji i każdego wywołania robocopy, także przy wyborze katalogu nadrzędnego.

- [P0-3] `scripts/sync_data_directories_to_d.ps1:309` — Redakcja manifestów nie zabezpiecza wszystkich logów. Robocopy zapisuje surowe komunikaty błędów do `/LOG`; `/NFL /NDL` nie redagują ścieżek w błędach. Ponadto linie 211 i 229 dołączają surowe `Exception.Message`, które mogą zawierać nazwę pliku klucza. `Get-Key` w linii 134 używa również rozróżniającego wielkość liter `StartsWith`, więc wybór `.TOOLING` na Windows omija redakcję ścieżek potomnych. Zabezpieczyć również komunikaty błędów, log natywny i aliasy ścieżek; do trwałych logów zapisywać wyłącznie zredagowane identyfikatory.

- [P0-4] `scripts/sync_data_directories_to_d.ps1:86` — Wzorzec `(^|/)dist$` uznaje za odtwarzalny każdy ignorowany katalog `dist`, chociaż task dopuszcza tę klasyfikację dla `packages/*/dist`, a pozostałe wpisy nakazuje zachowywać. Ignorowany `artifacts/dist` zostanie więc pominięty przez domyślną kopię bez ostrzeżenia. Zawęzić wzorzec do zakresu taska i sprawdzić pozostałe dodatkowe wzorce odtwarzalności według tej samej zasady.

### P1

- [P1-1] `scripts/sync_data_directories_to_d.ps1:173` — Inwentarz nie odróżnia znanych wpisów zachowywanych od nowych. Każdy nierozpoznany wpis otrzymuje wyłącznie `preserved`; raport nie ma znacznika „nowy”, a Outcome podaje zbiorcze liczby zamiast wymaganej listy nowych wpisów. Dodać niezależny znacznik nowego wpisu, zachować jego kopiowanie i rozliczyć takie wpisy w Outcome.

- [P1-2] `scripts/sync_data_directories_to_d.ps1:201` — Wykluczone poddrzewa są pomijane bez liczników i raportowania reguły wykluczenia. Pole `skipped` z podsumowania robocopy nie zastępuje wymaganej liczby plików pominiętych przez każde wykluczenie. Dodatkowo w linii 517 błędy enumeracji nie wpływają na wynik Initial, jeśli pozostałe części manifestów są równe, co pozwala raportować OK przy `errors > 0`. Raportować wykluczenia osobno, jawnie oznaczać brak możliwości policzenia nieczytelnego poddrzewa i ustawiać INCOMPLETE również przy błędach enumeracji Initial.

- [P1-3] `scripts/sync_data_directories_to_d.ps1:439` — Szacunek miejsca odejmuje całkowity rozmiar celu od całkowitego rozmiaru źródła. Dodatkowe pliki D zmniejszają przez to oszacowanie, mimo że `/E` ich nie usuwa. Przykładowo 4 GiB nowych plików źródła i 5 GiB niezwiązanych plików celu daje `needed_bytes=0`; przy 6 GiB wolnego skrypt dopuści kopię, która naruszy rezerwę 5 GiB. Liczyć zapotrzebowanie według odpowiadających sobie ścieżek, bez kompensowania nowych danych dodatkowymi plikami celu.

- [P1-4] `scripts/sync_data_directories_to_d.ps1:342` — Nie ma kontroli, czy `-LogRoot` leży poza kopiowanym zbiorem. Ustawienie go wewnątrz wybranego katalogu źródła lub celu powoduje kopiowanie albo porównywanie własnych, nadal zmienianych logów i manifestów. Narusza to kontrakt stabilnej weryfikacji Final. Przed utworzeniem katalogu przebiegu sprawdzić kanoniczne ścieżki i odrzucić takie położenie logów.

- [P1-5] `ai_docs/tasks/completed/0953-disk-d-data-directory-sync.md:233` — Outcome nie dokumentuje wymaganych prób zajętego pliku w Initial i Final ani próby Final z różną treścią przy identycznym rozmiarze i czasie. Zmiana pliku sprawdzona przez `-VerifyOnly -Manifest` nie dowodzi tego ostatniego scenariusza pełnego Final. Nie zapisano również wyników kontroli składni PowerShell i `docs:check`. Uzupełnić brakujące próby na izolowanym zestawie oraz zapisać komendy, kody wyjścia i wyniki wymaganych kontroli.

- [P1-6] `package.json:128` — Dodano nowy skrypt i prefiks npm `data:`, ale mapa kodu nie została zregenerowana: nie zawiera `sync_data_directories_to_d.ps1` ani tego prefiksu. Reguła AGENTS.md wymaga regeneracji przy dodaniu modułu. Wygenerować mapę, dołączyć zmiany należące do taska i odnotować wynik `npm run code-map:check`.

### P2

- [P2-1] `ai_docs/tasks/completed/0953-disk-d-data-directory-sync.md:224` — Outcome jawnie odnotowuje kopiowanie `.runtime/*.log` zamiast ich wymaganej klasyfikacji jako odtwarzalne. Kopiowanie zachowuje dane, lecz deklaracja „wynik jest równoważny” nie rozstrzyga rozbieżności kontraktu. Przywrócić wymaganą klasyfikację albo odnotować akceptację tego odstępstwa przez operatora.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Kompletny inwentarz, rozliczenie nowych wpisów, domyślny zbiór zachowywany i bezwarunkowe wykluczenie worktree’ów | niespełnione | `scripts/sync_data_directories_to_d.ps1:86`, `:173`, `:420`; P0-2, P0-4, P1-1 |
| Initial: kod 0, liczniki i INCOMPLETE przy błędach | niespełnione | Drugi zapisany SUMMARY kończy się OK; luki w raportowaniu: `scripts/sync_data_directories_to_d.ps1:201`, `:517`; P1-2 |
| VerifyOnly z zapisanym manifestem ignoruje nowe pliki i wykrywa zmienione | spełnione | `scripts/sync_data_directories_to_d.ps1:372`, `:375`; deklarowane próby: `ai_docs/tasks/completed/0953-disk-d-data-directory-sync.md:233` |
| Drugi Initial kopiuje tylko nowe lub zmienione pliki | spełnione | Odczyt `D:\game_predictor_backup\sync-logs\20261010-020051-Initial\SUMMARY.txt`: trzy pliki skopiowane w `.runtime`, pozostałe pominięte, RESULT: OK |
| Mały Final: równe SHA-256; VerifyOnly wykrywa brak pliku | spełnione | Odczyt SUMMARY przebiegu `20261010-020051-Final`: trzy wpisy bez różnic; próba brakującego pliku zadeklarowana w Outcome:235 |
| Mirror bez Final i potwierdzenia odmawia z kodem 1 | spełnione | `scripts/sync_data_directories_to_d.ps1:328`; nie oznacza to poprawności usuwania po potwierdzeniu |
| `.tooling` skopiowane, brak brakujących plików toolchainu podczas kontroli z D | spełnione | SUMMARY Initial: 12 181 plików `.tooling`; wynik kontroli opisany w Outcome:255 |
| Brak nazw i zawartości kluczy podpisu w logach i Outcome | niespełnione | Niezabezpieczone ścieżki logowania: `scripts/sync_data_directories_to_d.ps1:134`, `:229`, `:309`; P0-3 |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P0-1, P0-2, P0-3, P0-4, P1-1, P1-2, P1-3, P1-4, P1-5, P1-6, P2-1.

## Proponowane testy

- Dodać izolowany harness `scripts/test_sync_data_directories_to_d.ps1`; uruchamiać przez `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_sync_data_directories_to_d.ps1`. Objąć Mirror z nieaktualną listą zawierającą plik wspólny, ponowną weryfikację po usuwaniu, wybór `.claude` i `.\worktrees`, zachowywany `artifacts/dist`, nowy wpis oraz niedozwolone położenie LogRoot.
- W tym samym harnessie sprawdzić blokadę pliku w Initial i Final, różną treść przy identycznym rozmiarze i czasie oraz redakcję błędów dla fikcyjnego pliku pod `.tooling` i `.TOOLING`. Nie używać rzeczywistych kluczy.
- Przetestować kalkulację miejsca na małych danych z kontrolowaną wartością wolnego miejsca; dodatkowe pliki celu nie mogą zmniejszać potrzebnej rezerwy.
- Uruchomić i zapisać wyniki `npm run powershell:check`, `npm run docs:check` oraz, po regeneracji, `npm run code-map:check`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, skrypt, task, odpowiedni fragment planu, instrukcję utrzymania danych i dokumenty procesu. Sprawdzono wskazany diff, HEAD, mapę kodu oraz istniejące podsumowania przebiegów Initial i małego Final na D. Zmiany TASK-0954 pozostawiono poza zakresem.

Nie uruchamiano skryptu synchronizacji, testów, kopiowania, usuwania ani usług. Prób scratchpad opisanych w Outcome nie odtworzono. Nie odczytywano zawartości rzeczywistych kluczy podpisu. Znalezisko dotyczące ujawniania nazw wynika z analizy ścieżek logowania, a nie z potwierdzenia wcześniejszego wycieku.