# Audyt TASK-0953 — Przyrostowa kopia katalogów danych na D

Werdykt: REVISE
Audytor: gpt-6.1-sol, high
Wykonawca: claude-opus-5-5, reasoning nieodnotowany w Outcome
Zakres: HEAD...f3429d8a50e3f3433f42f72dd62ef2fad919f523 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-10
Runda: 2

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano poprawki po pierwszej rundzie, skrypt synchronizacji, dokumentację i istniejące podsumowania przebiegów. Większość wcześniejszych uwag została usunięta, lecz Mirror nadal może usuwać pliki na podstawie niekompletnego odczytu źródła, a ochrona nazw kluczy pozostaje niepełna. Dodatkowo `-AllowExtras` pozwala zakończyć Final sukcesem przy nierównych manifestach. Otwarte znaleziska P0 i P1 blokują commit.

## Znaleziska

### P0

- [P0-1] `scripts/sync_data_directories_to_d.ps1:640` — Mirror wykonuje usuwanie mimo błędów enumeracji lub wcześniejszego błędu robocopy. Błędy odczytu źródła trafiają do `$errors`, lecz brakujące w niekompletnym odczycie pliki celu zostają uznane za `Extra`. Jeżeli wcześniejsza zatwierdzona lista zawiera taki plik, linia 656 usuwa go, chociaż nadal istnieje w źródle. Poprawka przecięcia list chroni tylko przy kompletnym odczycie. Zablokować usuwanie przy błędach kopiowania, enumeracji lub hashowania oraz przy niedostępnym źródle; zatwierdzenie listy nie może zastępować dowodu, że plik istnieje wyłącznie w celu.

- [P0-3] `scripts/sync_data_directories_to_d.ps1:145` — Redakcja nadal nie zapewnia braku nazw kluczy w logach. Wzorzec kończy dopasowanie na spacji, więc dla fikcyjnej ścieżki `.tooling/test key.jks` pozostawia fragment `key.jks`. Ponadto robocopy zapisuje surowe błędy przez `/LOG` w linii 427, a redakcja następuje dopiero po zakończeniu procesu; przerwanie skryptu pozostawia niezredagowany log. Przy wyborze pojedynczego pliku pod `.tooling` surowy `$rel` trafia również do nagłówka manifestu w linii 341 i nazw plików wynikowych przez `Get-SafeName`. Zapisywać do trwałych logów wyłącznie zredagowane dane, obsłużyć pełne ścieżki ze spacjami i stosować bezpieczne identyfikatory także w nagłówkach oraz nazwach wyników.

- [P0-5] `scripts/sync_data_directories_to_d.ps1:668` — `-Mode Final -AllowExtras` wyłącza błąd dla nadmiarowych plików celu. Skrypt może wtedy zapisać nierówne manifesty, wypisać `extra > 0` i zakończyć się `RESULT: OK`, kodem 0. Task oraz decyzja 3 planu wymagają równości manifestów Final i zatrzymania przy każdej rozbieżności. Ignorowanie nowych plików przewidziano dla `-VerifyOnly -Manifest`. Odrzucić `-AllowExtras` w Final albo usunąć możliwość pomijania jego rozbieżności.

### P1

- [P1-7] `scripts/sync_data_directories_to_d.ps1:498` — `-VerifyOnly -Manifest` enumeruje całe drzewo celu i przenosi wszystkie błędy enumeracji do wyniku. Nowy, nieczytelny podkatalog, którego plików nie ma w zapisanym manifeście, powoduje kod 1 w linii 507 nawet wtedy, gdy wszystkie wymagane pliki mają poprawne hashe. To narusza kontrakt ignorowania plików spoza manifestu. Rozliczać błędy przez brak lub nieczytelność wymaganych plików; błędy dotyczące wyłącznie nowych gałęzi nie powinny odrzucać weryfikacji.

- [P1-8] `scripts/sync_data_directories_to_d.ps1:633` — Limit `-TimeoutMinutes` obejmuje wyłącznie oczekiwanie na robocopy w linii 435. Enumeracja i obliczanie SHA-256 obu stron działają poza tym limitem; `ComputeHash` w linii 165 nie ma ograniczenia czasu. Przebieg Final może więc przekroczyć wymagany limit per katalog bez zakończenia kodem 2. Objąć limitem cały przebieg danego katalogu, w tym enumerację i hashowanie, oraz zapewnić kontrolowane przerwanie pracy.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Inwentarz, nowe wpisy, domyślny zbiór zachowywany i wykluczenie worktree’ów | spełnione | `scripts/sync_data_directories_to_d.ps1:239`, `:535`, `:553`, `:559`; aktualna lista git: 98 zachowywanych, 59 odtwarzalnych, 2 korzenie worktree’ów, brak nowych wpisów według obecnych wzorców |
| Initial: liczniki, kod sukcesu i INCOMPLETE przy błędach | spełnione | `scripts/sync_data_directories_to_d.ps1:613`, `:669`, `:682`; zapisane SUMMARY: pierwszy Initial — INCOMPLETE, drugi — OK |
| VerifyOnly z manifestem ignoruje nowe pliki i wykrywa zmienione | niespełnione | Zwykłe przypadki opisano w `ai_docs/tasks/completed/0953-disk-d-data-directory-sync.md:299`; błędy nowych gałęzi naruszają kontrakt — P1-7 |
| Drugi Initial kopiuje tylko nowe lub zmienione pliki | spełnione | Odczyt `D:\game_predictor_backup\sync-logs\20261010-020051-Initial\SUMMARY.txt`: 98 wpisów, 3 skopiowane pliki, RESULT: OK |
| Mały Final: równe SHA-256; VerifyOnly wykrywa brak pliku | spełnione | SUMMARY `20261010-020051-Final`: trzy wpisy, zero różnic, RESULT: OK; próbę brakującego pliku opisano w Outcome:258 |
| Mirror bez Final i potwierdzenia odmawia | spełnione | `scripts/sync_data_directories_to_d.ps1:450`; nie oznacza to poprawności usuwania po potwierdzeniu |
| `.tooling` skopiowane; kontrola z D nie zgłasza brakujących plików toolchainu | spełnione | SUMMARY Initial: 12 181 plików `.tooling`, brak różnic rozmiaru; wynik kontroli opisano w Outcome:278 |
| Brak nazw i zawartości kluczy podpisu w logach i Outcome | niespełnione | `scripts/sync_data_directories_to_d.ps1:145`, `:341`, `:427`; P0-3 |
| Final odrzuca każdą rozbieżność manifestów | niespełnione | `scripts/sync_data_directories_to_d.ps1:668`; P0-5 |
| Mirror usuwa wyłącznie zatwierdzone pliki istniejące tylko w celu | niespełnione | `scripts/sync_data_directories_to_d.ps1:640`, `:656`; P0-1 |
| Limit czasu per katalog i zakończenie kodem 2 | niespełnione | Limit dotyczy robocopy, lecz nie hashowania w `scripts/sync_data_directories_to_d.ps1:633`; P1-8 |

## Listy zamknięte i otwarte

Zamknięte:

- P0-2 — normalizacja ścieżek i wykluczenie zagnieżdżonych worktree’ów: `scripts/sync_data_directories_to_d.ps1:125`, `:215`, `:275`, `:423`.
- P0-4 — `artifacts/dist` nie podlega już ogólnemu wykluczeniu `dist`: `scripts/sync_data_directories_to_d.ps1:92`; próba opisana w Outcome:285.
- P1-1 — dodano znacznik `New` i raportowanie; aktualna lista źródła nie zawiera nowych zachowywanych wpisów według obecnych wzorców: `scripts/sync_data_directories_to_d.ps1:239`, `:542`.
- P1-2 — dodano liczniki wykluczeń i wpływ błędów enumeracji na INCOMPLETE: `scripts/sync_data_directories_to_d.ps1:280`, `:309`, `:669`.
- P1-3 — zapotrzebowanie na miejsce jest liczone według odpowiadających sobie plików: `scripts/sync_data_directories_to_d.ps1:579`.
- P1-4 — dodano kontrolę położenia LogRoot: `scripts/sync_data_directories_to_d.ps1:463`.
- P1-5 — uzupełniono wyniki prób blokady, różnej treści przy identycznym rozmiarze i czasie oraz kontroli składni i dokumentacji: `ai_docs/tasks/completed/0953-disk-d-data-directory-sync.md:294`, `:296`, `:301`.
- P1-6 — mapa zawiera nowy skrypt i prefiks `data:`: `ai_docs/architecture/CODE_MAP.md:277`, `:279`.
- P2-1 — dodano wykluczenie logów `.runtime`: `scripts/sync_data_directories_to_d.ps1:105`, `:209`.

Otwarte: P0-1 i P0-3 częściowo poprawione, nadal blokujące; nowe P0-5, P1-7, P1-8.

## Proponowane testy

- Dodać izolowany harness `scripts/test_sync_data_directories_to_d.ps1`; uruchamiać przez `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_sync_data_directories_to_d.ps1`.
- Sprawdzić Mirror przy błędzie odczytu źródła i zatwierdzonej liście zawierającej plik obecny po obu stronach. Żaden plik celu nie może zostać usunięty.
- Sprawdzić fikcyjne pliki `.tooling` ze spacjami w nazwie, wybór pojedynczego pliku oraz przerwanie kopiowania. Kontrola powinna obejmować treść logów, nagłówki manifestów i nazwy wyników.
- Sprawdzić dodatkowy plik celu przy `Final -AllowExtras`; rozbieżność musi blokować Final.
- Sprawdzić `VerifyOnly -Manifest` z nowym, nieczytelnym podkatalogiem poza manifestem oraz osobno z nieczytelnym plikiem wymaganym przez manifest.
- Sprawdzić przekroczenie limitu podczas hashowania przez kontrolowane opóźnienie w harnessie; oczekiwany kod 2 i zakończona praca.
- Po poprawkach zapisać wyniki `npm run powershell:check`, `npm run docs:check` i `npm run code-map:check`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, skrypt, task, odpowiednie fragmenty planu, instrukcję utrzymania danych, dokumenty procesu i wcześniejszy raport. Potwierdzono zgodność skryptu na dysku z jego kopią w briefie. Odczytano podsumowania dwóch przebiegów Initial i małego Final oraz aktualną listę ignorowanych wpisów źródła.

Nie uruchamiano synchronizacji, testów, kopiowania, usuwania ani usług. Próby scratchpad oceniono na podstawie zapisów Outcome. Pełny Final pozostaje zakresem TASK-0955. Nie odczytywano zawartości rzeczywistych kluczy podpisu. Znaleziska dotyczące usuwania i ujawniania nazw wynikają z analizy kodu; nie potwierdzają wcześniejszej utraty danych ani wycieku.