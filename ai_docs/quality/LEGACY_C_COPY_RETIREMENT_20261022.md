---
title: Przygotowanie usunięcia starej kopii C — TASK-1085
status: active
last_updated: 2026-10-22
---

# Przygotowanie usunięcia starej kopii C

## Werdykt operatorski

Zabezpieczenie plików i przygotowanie techniczne ukończone. Nie usuwać jeszcze
`C:\Users\tuszy\Documents\game_predicotr`: ścieżki w bazie nadal wskazują C.
Nie wykonano migracji danych, scalenia, restartów ani zmiany nazwy starego
katalogu. Claude Code z aplikacji znaleziony w nowym katalogu danych;
wykrywanie poprawione. [Audyt Claude](TASK-1085_AUDIT_claude-opus-5-5.md)
zakończył się PASS, bez P0/P1. Uwagi P2 poniżej ograniczają gotowość do
wykonania migracji i odcięcia C; PASS dotyczy przygotowania.

Świeży końcowy odczyt: **434131 plików, zero błędów**. 311795 zgodnych
plików jest w aktywnym D (76020477970 B), 122336 starszych lub brakujących
wersji zabezpieczono osobno (9822323477 B). Łącznie 85842801447 B.
W podglądzie migracji **179 jobów, 55 źródeł z ponownym SHA, blockers=[]**.

Pełne before/after: `D:\game_predicotr\artifacts\maintenance\legacy-c-20261022\job-paths-preview.json`.
SHA tego podglądu:
`e8b592828aea9e4f33dc701ec85ec95089b84a9a820734b549e3f6835345efe2`.
Zmiana joba po podglądzie wymaga ponownego podglądu; nie osłabiać walidacji.

## Czy stare importy są potrzebne

| Zbiór | Liczba | Ocena |
|---|---:|---|
| Importy waiting_for_review | 53 | Zachować: mają 108835 zdjęć źródłowych i 1792 kanoniczne pozycje. |
| Importy failed | 6 | Brak rekordów source_images; nie usuwać w tej operacji. |
| Preflighty validate completed | 113 | Historia kontroli przed importem; nie są zakończonymi importami. |
| Preflighty validate failed/cancelled | 7 | Historia/ponowienie; zachować i poprawić lokalizację źródła. |
| Sesje selekcji ze ścieżką C | 14 | Wszystkie puste i po expires_at; w czterech pozostał zapisany status active. |

Importy dotyczą „777 a1” (56812 zdjęć i 499 pozycji) oraz „Mumie a1”
(52023 zdjęcia i 1293 pozycje). Status waiting_for_review nie oznacza
porzuconego zadania. Kasowanie tych importów byłoby odrębną operacją na
danych gier i nie jest potrzebne do usunięcia starego checkoutu.

Pięć z sześciu nieudanych importów ma inne podejście z tym samym
source_selection_id w waiting_for_review. Szósty
`5395dc2c-a2db-46bf-b2ed-b45e8682aef8` nie ma takiego drugiego importu w
zbadanym zbiorze. Nie uznano go automatycznie za zbędny. Żaden rekord nie
został skasowany ani ponowiony.

## Zależności i ich rozliczenie

- 179 jobów ma C wyłącznie w input_payload.source_directory. Checkpointy
  nie zawierają zdekodowanych ścieżek zaczynających się od starego korzenia.
- 55 różnych źródłowych katalogów stagingu istnieje na D. Podgląd migracji
  wymaga zgodności ich plików z receiptami SHA; samo istnienie nie wystarcza.
- 59 manifestów importów nadal pamięta C. Wszystkie mają bazę zgodną ze
  starym input joba i wszystkie 112423 wskazane oryginały istnieją na D.
- Skan JSON do 4 MB w artifacts/data znalazł 184 manifesty oryginałów ze
  starym tekstem C: 176 należy do jobów z podglądu (importy i preflighty),
  8 nie ma już joba. Sześć plików protected-control-proofs zawiera również
  historyczne pochodzenie eksperymentów; nie przepisuje się niezmiennych
  dowodów ani ich hashy. To nie jest pełny skan dowolnych formatów binarnych.
- Puste sesje nie mają kolekcji, batchy, plików, operacji, transferów ani
  akcji hosta. Publiczny dostęp sprawdza expires_at; monitor obsługuje brak
  dawnego dysku komunikatem diagnostycznym. Nie przenosi się bindingów,
  nie zmienia base_binding_id i nie usuwa historii sesji.
- PostgreSQL ma wolumen Docker, bez bind mount starego repozytorium C.
- Nie znaleziono konfiguracji środowiska użytkownika ani editable instalacji
  Python wskazującej stary checkout. Bieżące procesy usług wskazują D.
  Stary grid-v3-deployment-services.json z października jest historycznym
  zapisem PID/logów; nie znaleziono jego konsumenta w scripts/services/infra.
- Jedyny taki tekst w bieżącym katalogu modeli jest w eligibility.json
  kandydata symboli: domain/lab_symbol_candidate.py waliduje hash całego
  dowodu, a nie otwiera zapisanych historycznych ścieżek modeli. Plik
  t03k-runtime-readonly.stdout.json jest historycznym wynikiem diagnostyki.

## Przygotowana poprawka

Niezmienny manifest zachowuje dokładne bajty i checksumę. Tylko jawny
source_directory_relocation (contract_version=1, previous/current) w jobie
pozwala loaderowi użyć nowej bazy. Current musi odpowiadać source_directory
joba, a previous musi pasować do zapisanej bazy danego manifestu.
Domyślne zachowanie managed reprocess bez takiego potwierdzenia pozostaje.
Preflight klasyczny i neuronowy akceptują ten opcjonalny receipt.
Rozmiar i SHA-256 odtwarzanych oryginałów nadal są obowiązkowe.

Narzędzie `legacy_job_path_migration.py preview` wykonuje odczyt w
REPEATABLE READ READ ONLY. Tryb apply wymaga SHA dokładnego podglądu,
kompletnego zabezpieczenia plików, aktualnych plików stagingu i nowego
loadera. Wszystkie wiersze są blokowane i porównywane z podglądem przed
pierwszym UPDATE. Zapis dotyczy wyłącznie source_directory, jego jawnego
receiptu oraz updated_at. Statusy, input_key, checkpointy, manifesty i dane
gier pozostają. Błąd wycofuje całą transakcję. Ponowienie po utracie odpowiedzi
odmawia kolejnego zapisu na zmienionych wartościach; stan należy odczytać.

Wartości before w podglądzie są zabezpieczeniem do kontrolowanego
odtworzenia. Odtworzenie też wymaga osobnego podglądu, kontroli stanu jobów
i zgody; stary katalog pozostaje do tego czasu nienaruszony.

## Zabezpieczenie na D

Katalog: `D:\game_predicotr\artifacts\maintenance\legacy-c-20261022`.

- git/all-refs.bundle: 54315680 B, bundle verify PASS; wszystkie referencje C
  są w bundle. Oba zarejestrowane worktree mają HEAD, branch, status oraz
  staged/unstaged patch. Zabezpieczono też config, HEAD i packed-refs.
  Końcowe porównanie: wszystkie aktualne 39 referencji nadal w bundle.
- files.sqlite oraz files-summary.json: SHA i potwierdzenia zachowywanych
  plików. Pliki identyczne pozostają w aktywnym D; starsze/brakujące wersje
  C trafiają wyłącznie do legacy-files. Żaden aktywny plik D nie jest
  nadpisywany. Kopie są publikowane atomowo po pełnym zapisie i kontroli.
- Odtwarzalne środowiska .venv*, node_modules poza .tooling, .next,
  __pycache__, cache i jawne katalogi pytest są wyłączone. .git zabezpiecza
  bundle. Dowiązania są inwentaryzowane bez podążania za nimi.
- Spis ma 10 dowiązań; żadne nie wskazuje D. Obsługa Win32 extended paths
  obejmuje również mkdir i atomową publikację hardlinkiem. Przypadek ponad
  260 znaków odtworzono testem; błędy pierwszej próby zostały poprawione.
  Wznowienie z zapisanego spisu nigdy nie ustawia complete=true; wymagany
  jest osobny świeży odczyt źródła i ponowna kontrola potwierdzeń.
- Sąsiedni game_predictor_vision_data, kopie w game_predictor_backup i obraz
  dysku Docker pozostają poza usuwanym katalogiem.

## Weryfikacja

- Końcowy komplet 78 testów narzędzi, source ingestion, wznowienia z cropami
  i obu preflightów — PASS, 11.97 s. Po usprawnieniu wznawiania i walidacji
  pakietów ponownie 16 testów narzędzi — PASS, 2.27 s.
- Nowy proces odtwarza oryginał po przeniesieniu folderu i zachowuje bajty
  manifestu. Zmieniony obraz, zmieniony podgląd i zmieniony stan joba blokują
  operację. SHA jest sprawdzane również przy zachowanym rozmiarze i mtime.
  Nowy proces odczytał również wszystkie 176 istniejących manifestów jobów
  objętych podglądem, używając nowych katalogów bez zapisu do bazy lub manifestów.
- Ruff zmienionych plików i mypy nowych skryptów — PASS.
- Mypy całego grafu zależności przekroczył 110 s (zakończony proces) oraz
  pokazał wcześniejsze błędy source_lattice_geometry.py:36,38. Zawężony
  mypy workera ma wcześniejszy no-any-return w funkcji weryfikacji cropa:
  ten sam błąd odtworzono na niezmienionym main. Poza zakresem zadania.
- docs:check — PASS; mapa kodu wygenerowana.
- Claude CLI: pierwotnie brief-only przez nieaktualny zestaw lokalizacji.
  W nowym `AppData/Local/Claude-Data/*/claude-code` potwierdzono uruchomienie
  Claude Code (`--version` 2.1.304, kod 0). Wykrywanie poprawione trwale,
  bez utrwalania wersji ani nazwy pakietu. Test wykrywania: 10/10 PASS.
  Skrypt przekazuje również jawne `--effort medium`; istniejący CLI potwierdził
  tę opcję przez `--help` i zakończony audyt. Starszy CLI bez tej flagi zostanie
  odrzucony z diagnostyką (kod 3), bez niejawnej zmiany poziomu rozumowania.
- [Audyt Claude](TASK-1085_AUDIT_claude-opus-5-5.md) — PASS, runda 1,
  `claude-opus-5-5`, medium; brak P0/P1, siedem P2. Przegląd statyczny,
  bez zmian w plikach i bez niezależnej kontroli prywatnych backupów/bazy.

## Ograniczenia po audycie i warunki wykonania

Uwagi pozostają jawnie otwarte jako P2 dla przygotowania. Nie są zgodą na
użycie apply ani usunięcie C. Przed wykonaniem trzeba je ponownie ocenić
w kontekście aktualnego stanu, a warunki poniżej muszą zostać spełnione.

| Uwaga | Rozliczenie i warunek przed wykonaniem |
|---|---|
| P2-1 | `verify_worker` pomija brakujące manifesty pod domyślną ścieżką. W tej kontroli nowy proces odczytał 176 manifestów, ale apply nie wymusza tej liczby. Przed migracją potwierdzić skonfigurowany katalog i kompletny zestaw manifestów; nie uznawać samego przejścia funkcji za dowód. |
| P2-2 | Kontrola loadera dotyczy procesu skryptu. Nie kontroluje kodu już uruchomionych workerów. Scalenie oraz restart wszystkich workerów przez operatora i weryfikacja ich katalogów są obowiązkowe przed apply. |
| P2-3 | SHA zatwierdza cały plik, a apply ufa jego `after_payload`. Nie edytować ręcznie podglądu i nie przeliczać SHA dla zmienionej treści. Przed zatwierdzeniem porównać pełne before/after: wyłącznie source_directory i receipt, bez innych zmian payloadu. |
| P2-4 | Joby managed reprocess nie dziedziczą receiptu. Przy braku zarządzanego oryginału ich fallback może wrócić do C. Przed odcięciem C trzeba obsłużyć propagację relokacji i sprawdzić reprocess z brakującym oryginałem. Obecność 112423 oryginałów dziś nie usuwa tego ryzyka na przyszłość. |
| P2-5 | Ten raport nie potwierdza skanu wszystkich kolumn tekstowych/JSON bazy. Przed odcięciem wykonać odczyt całej bazy pod kątem starego korzenia i rozliczyć konsumentów znalezionych ścieżek, także poza jobs/sessions. |
| P2-6 | Jawny effort udokumentowano; uruchomienie audytu dowodzi obsługi medium w obecnym CLI. Brak osobnego automatycznego testu składania argumentów, starszy CLI jest jawnie odrzucany. To ograniczenie narzędzia audytu, niezależne od relokacji danych. |
| P2-7 | Testy nie wykonują pełnego preview/apply na PostgreSQL. Przed migracją dodać i uruchomić test izolowanej transakcji, konfliktu stanu, rollbacku i odczytu JSONB oraz brakującego manifestu. Nie testować tego przez zapis na danych operatora. |

## Kolejny krok po akceptacji

Najpierw domknąć warunki wykonania z tabeli powyżej; przygotowanie narzędzia
nie jest odbiorem migracji. Po zamknięciu taska i zgodzie na scalenie: wdrożyć poprawkę z gałęzi
codex/retire-c-copy. Operator restartuje workery w swoich terminalach.
Odświeżyć podgląd (stare updated_at mogą się zdezaktualizować), pokazać
operatorowi liczbę wierszy, before/after oraz SHA i uzyskać odrębną zgodę
na migrację danych. Następnie apply z zatwierdzonym SHA i ponowny odczyt.

Dopiero po sprawdzeniu z nowego procesu, kontroli zabezpieczenia i zgodzie
na odcięcie: czasowo zmienić nazwę C, wykonać odbiór bez dawnej nazwy
(zdjęcia, przegląd, odczyt manifestu), zachować możliwość cofnięcia nazwy.
Nie uruchamiać importu na próbę na danych operatora bez osobnej zgody.
Usunięcie starego katalogu pozostaje osobną, końcową decyzją.

Worktree przygotowania ma junction `.venv` do `D:\game_predicotr\.venv`;
przy sprzątaniu najpierw usunąć samo dowiązanie zgodnie z merge-to-main.
