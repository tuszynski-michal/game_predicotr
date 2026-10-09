---
title: Przegląd planu przeniesienia na dysk D przez Codex (runda 1)
status: active
last_updated: 2026-10-09
---

# Przegląd planu przeniesienia na dysk D — Codex, runda 1

Audytor: Codex CLI 0.162.0, gpt-6.1-sol / high, `codex exec --sandbox read-only`.
Zakres: `ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md` i taski TASK-0952–0957 w wersji sprzed poprawek. Brief: `artifacts/audits/DISK_D_PLAN_REVIEW_PROMPT.md`.

Werdykt: REVISE

## P0

- **[Plan](ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md:106), decyzja 2; [TASK-0952](ai_docs/tasks/0952-disk-d-database-backup.md:77), Technical notes — kopia nie zabezpiecza stanu przełączenia.** Zrzut powstaje podczas importu. Odtworzenie po awarii utraci późniejsze wyniki i zmiany operatora. Nie obejmuje pozostałych baz ani globalnych ról. Nie ma też niezależnej kopii VHDX; pozostawienie oryginału przez Docker Desktop jest założeniem.
  **Poprawka:** przed przeniesieniem zamrozić zapisy i zabezpieczyć aktualny stan. Zalecana osobna kopia całego VHDX przy całkowicie zamkniętym Docker Desktop, z weryfikacją SHA-256 i opisaną procedurą przywrócenia. Zrzut A1 pozostawić jako dodatkowe zabezpieczenie. Jeżeli zabezpieczeniem mają być wyłącznie zrzuty, objąć nimi wszystkie zachowywane bazy i role oraz ponowić je po zatrzymaniu zapisów.

- **[TASK-0954](ai_docs/tasks/0954-disk-d-repository-handover.md:54), Scope i Technical notes; TASK-0957, Scope 4 — niepełne zabezpieczenie pracy przed usunięciem C.** `git diff > plik.patch` pomija zmiany staged i pliki nieśledzone oraz nie zapewnia odtwarzalności zmian binarnych. PowerShell 5.1 zapisze przekierowany tekst w nieodpowiednim kodowaniu. Sam `git worktree list` nie potwierdza czystości worktree’ów. Push czterech gałęzi nie zabezpiecza niezacommitowanej pracy w tych katalogach.
  **Poprawka:** zinwentaryzować każdy worktree, także detached HEAD, staged, unstaged i pliki nieśledzone. Zabezpieczyć referencje lokalnym bundle’em, zmiany śledzone przez patch `--binary` z jawnym kodowaniem, pozostałe pliki przez kopię. Zweryfikować odtwarzalność na D. Usunięcie C uzależnić od zabezpieczenia wszystkich worktree’ów, również zmian powstałych po A3.

## P1

- **TASK-0952, Acceptance criteria i Verification, linie 69, 87–98 — sprawdzenie spisu nie weryfikuje danych kopii.** Uszkodzony lub ucięty CUSTOM dump może mieć czytelny spis. SHA-256 identyfikuje plik, ale nie dowodzi jego kompletności. Pokazanie pierwszych 12 linii dodatkowo nie zastępuje sprawdzenia zakończenia komendy.
  **Poprawka:** wymagać kodu 0 z `pg_dump`, zachować pełny wynik kontroli i zweryfikować odczyt wszystkich danych archiwum. Dla kopii będącej podstawą odzyskania wykonać kontrolowane odtworzenie do osobnej bazy i porównać dane. Runbook sam rozróżnia spis od odtworzenia w sekcji 4.

- **[TASK-0955](ai_docs/tasks/0955-disk-d-database-cutover.md:110), procedura awaryjna 2 — podana komenda odtworzenia nie działa.** `pg_restore -j 4` wymaga zwykłego pliku lub katalogu; nie obsługuje stdin podawanego przez `docker exec -i`. Brakuje też obowiązkowego zakończenia przy błędzie. [Dokumentacja PostgreSQL](https://www.postgresql.org/docs/18/app-pgrestore.html).
  **Poprawka:** udostępnić archiwum jako plik wewnątrz kontenera albo wykonać odtworzenie ze stdin bez `-j`. Dodać `--exit-on-error`, sprawdzenie kodu zakończenia, kolejność odtworzenia ról i pełną kontrolę danych. Nie usuwać jedynej zachowanej kopii podczas przygotowania nowego obrazu.

- **[TASK-0953](ai_docs/tasks/0953-disk-d-data-directory-sync.md:75), Acceptance criteria, Technical notes i Test cases — sprzeczny kontrakt błędów kopiowania.** Kryteria wymagają błędu dla ≥8, a test wymaga sukcesu dla kodu 8 bez niezdefiniowanego w Scope `-Strict`. Kody 4–7 oznaczają rozbieżności, nie pliki zajęte. Błąd kopiowania ma bit 8. [Dokumentacja Microsoft](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/robocopy).
  **Poprawka:** zdefiniować tryb kopii wstępnej i tryb końcowy. Wstępny może kontynuować z jawnie oznaczonym niekompletnym wynikiem. Końcowy musi blokować przełączenie przy każdym błędzie, rozbieżności lub nieudanej weryfikacji.

- **TASK-0953, Scope i Acceptance criteria, linie 57–78 — liczby plików i bajtów nie dowodzą kompletności.** Różne zestawy plików mogą mieć identyczne sumy. Robocopy może pominąć zmienioną zawartość o zachowanym rozmiarze i czasie. Log wewnątrz synchronizowanego `.runtime\sync-logs` sam tworzy różnicę. Wykluczenia również nie mają określonego wpływu na weryfikację.
  **Poprawka:** po zatrzymaniu zapisów porównać manifesty względnych ścieżek, rozmiarów i sum kontrolnych zachowywanych danych. Logi umieścić poza kopiowanym zbiorem. Jawnie określić wykluczenia i wykazać, że nie pomijają trwałych danych. Przed `/MIR` zatwierdzić listę plików istniejących wyłącznie na D.

- **Plan, Etapy i odbiór; TASK-0955, Dependencies i Scope 1–3 — brakuje stabilnej granicy przełączenia.** Sprawdzenie jobów przed zatrzymaniem producentów pozostawia wyścig: worker może pobrać kolejny job przed `workers:stop`. Ten skrypt kończy procesy przez `Kill()`. Po zatrzymaniu nie ma ponownej kontroli jobów i dzierżaw. Porównanie z raportem A1 jest niewłaściwe, ponieważ import i operator nadal zmieniają bazę.
  **Poprawka:** zatrzymać producentów zapisów, opróżnić uzgodnione kolejki, zatrzymać workery i ponownie sprawdzić joby, dzierżawy oraz kolejki host actions zdalnej selekcji. Utworzyć raport odniesienia bezpośrednio przed przeniesieniem. Po nim porównać dane z tym raportem, również w pozostałych zachowywanych bazach. Rozstrzygnąć sprzeczność między opróżnieniem `created` a wymaganiem zakończenia istniejącego joba derive dopiero w B2.

- **[TASK-0957](ai_docs/tasks/0957-disk-d-cleanup-and-job-paths.md:53), Scope 1 i 4 — usunięcie C nie zależy od usunięcia zależności jobów od C.** Przepisanie ścieżek jest opcjonalne, a usunięcie katalogu ma osobną, niezależną zgodę. Pominięte `cancelled` można ponawiać: `requeue_job` dopuszcza ten status. Przepisywany jest tylko prefiks `imports`, bez bramki dla pozostałych ścieżek. Kontrola `input_payload::text` dodatkowo operuje na JSON z escapowanymi backslashami.
  **Poprawka:** usunięcie C zablokować do czasu rozliczenia wszystkich operacyjnych odwołań. Sprawdzać zdekodowane wartości JSON i checkpointy. Objąć mapowaniem ponawialne `cancelled`; dla historycznych rekordów wykazać, że żaden obsługiwany workflow nie używa ich starego źródła. Przy zapisie ponownie sprawdzić status pod blokadą wiersza. Wybranie archiwum na C wyklucza usunięcie tego archiwum.

- **[TASK-0956](ai_docs/tasks/0956-disk-d-application-startup.md:69), Scope 6; TASK-0957, Scope 4 — revoke nie przenosi danych zdalnej selekcji.** Unieważnienie sesji pozostawia `host_base_path`. Operacje hosta nadal otwierają bazę przez ten binding. Nowa sesja nie przejmuje automatycznie starych batchy ani ich markerów własności. Opróżnienie `public.jobs` nie obejmuje wszystkich kolejek tego workflow.
  **Poprawka:** zinwentaryzować dane i pending actions wszystkich 13 bindingów. Przed usunięciem C zakończyć operacje i zweryfikować zachowane wyniki albo zaplanować kontrolowane przeniesienie bindingów z zachowaniem tożsamości i markerów. Dodać odbiór istniejącej selekcji, nie tylko utworzenie nowej sesji.

- **TASK-0954, Scope; TASK-0955, Dependencies — D nie musi zawierać kodu potrzebnego do wykonania planu.** `git fetch` aktualizuje referencje, lecz nie checkout. Plan i nowe skrypty powstają na osobnej gałęzi; lista czterech wypychanych gałęzi nie obejmuje tej gałęzi. B1 nie wymaga nawet ukończenia TASK-0954.
  **Poprawka:** wskazać sposób dostarczenia zaakceptowanego planu i commitów narzędzi na D. Przed B1 wymagać TASK-0954 `done`, oczekiwanego HEAD oraz obecności właściwej wersji skryptu synchronizacji i wpisu npm.

- **TASK-0957, Scope 4, linie 71–77 — końcowa synchronizacja z C jest niewłaściwa po dniu pracy z D.** D zawiera już nowe artefakty i stan runtime. Różnica 0 nie powinna wtedy występować. Uruchomienie kopiowania może nadpisać nowszy plik na D; użycie `/MIR` usunie nowe pliki D.
  **Poprawka:** po przełączeniu zakazać synchronizacji C→D do aktywnych katalogów. Zachować manifest z B1 i przed usunięciem sprawdzić obecność oraz integralność zachowywanych danych z tego manifestu. Nowe pliki D pozostawić poza porównaniem.

- **Plan, Odbiór całego przepływu; TASK-0956, Acceptance criteria — odbiór nie potwierdza „100% danych” ani niezależności od C po restarcie.** Dwie gry i kilka podglądów to próbka. Brakuje sprawdzenia wszystkich odwołań do plików, trzeciej gry, ignorowanego `examples/imgs` używanego przez konfigurację oraz trwałych manifestów zawierających ścieżki. B2 może zaliczyć odbiór, nadal korzystając ze źródeł na C.
  **Poprawka:** dodać mapę wymaganie→task→dowód. Zweryfikować wszystkie zachowywane odwołania do plików i jawnie rozliczyć pozostałe ignorowane katalogi oraz ustawienia ścieżek. Wymagać odbioru po restarcie Windows i kontrolowanym odcięciu dostępu do starego katalogu, przed jego usunięciem. Dla każdej granicy etapu zapisać stan trwały i procedurę wznowienia.

## P2

- **Plan, linia 148; taski, warunki wolnego miejsca — progi są niespójne.** Podana suma 25+138+77 wynosi około 240 GB przed zapasem, nie 200 GB.
  **Poprawka:** wyliczać pozostałe potrzebne miejsce przed każdym krokiem, uwzględniając dodatkowe kopie i odtworzenie awaryjne.

- **TASK-0956, Scope 1 — skrypt środowiska nie usuwa starych wpisów PATH.** Dodaje ścieżki D przed istniejącymi wpisami. Ponadto zachowuje `C:\gpg`, jeśli ten katalog istnieje.
  **Poprawka:** opisać rzeczywiste zachowanie. Po odbiorze usunąć wyłącznie nieużywane wpisy starego repozytorium i sprawdzić środowisko po restarcie.

- **Plan, Przypisanie modeli — wywołanie audytu nie zapewnia konfiguracji z tabeli.** Samo `-Auditor codex` pozostawia model domyślny i reasoning `medium`, również dla tasków wymagających `high`.
  **Poprawka:** podać `-Model gpt-6.1-sol`, właściwy `-Effort`, `-Plan` i ograniczone `-Paths`. Dodać wymaganą zgodę na koszt długich kopii oraz jawne timeouty; opis „w tle” nie jest mechanizmem ich egzekwowania.

- **Plan, linie 87 i 184; TASK-0956, Technical notes — dwie instrukcje diagnostyczne są zbyt ogólne.** Trwałe sesje zdalnej selekcji nie znikają po restarcie API; wygasają capability procesu. Operacyjne obrazy resolver otwiera pod `artifact_root/data`, nie zawsze bezpośrednio pod `artifact_root`.
  **Poprawka:** rozróżnić typy sesji i wskazać resolver właściwy dla danego pola ścieżki.

## Potwierdzone

- `compose.yaml` definiuje `name: game-predictor` i nazwany wolumen. Zmiana checkoutu nie wymaga nowego projektu ani bind mountu. Przy podanych identycznych hashach konfiguracji ponowne użycie kontenera jest uzasadnione.
- `ApiSettings.from_environment` czyta `os.environ`; domyślne korzenie danych rozwiązuje względem katalogu procesu.
- `recover_expired_job` zachowuje checkpoint i przy braku żądania anulowania przywraca `created`. Żądanie anulowania prowadzi do `cancelled`.
- Skrypt środowiska wylicza toolchain względem repozytorium i zapisuje zmienne trwale dla użytkownika. `CheckOnly` sprawdza również zgodność zapisanych wartości.
- Stan lifecycle znajduje się w `.runtime/worker-lanes.json` i `.runtime/remote-reviewer.json`. Produkcyjny Reviewer wymaga lokalnego builda.
- Przeniesienie danych WSL2 przez ustawienia Docker Desktop jest wspierane. [Dokumentacja Docker](https://docs.docker.com/desktop/features/wsl/).
- Taski mają zasadnicze sekcje szablonu. Końcowa tabela obejmuje wszystkie sześć tasków; modele i reasoning odpowiadają ich `Recommended execution`. Podział A/B1/B2/C pozwala na przerwy, ale wymaga opisanych wyżej bramek wznowienia i odbioru po restarcie.
- Przegląd statyczny, bez zmian w plikach. Nie uruchamiałem usług, operacji bazodanowych, kopii ani testów odtworzenia.