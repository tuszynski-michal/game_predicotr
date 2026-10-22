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
zakończył się PASS, bez P0/P1. TASK-1086 rozlicza zabezpieczenia P2 poniżej;
wdrożenie, restart usług przez operatora i zgoda na migrację/odcięcie
pozostają warunkami wykonania. PASS dotyczy przygotowania.

Świeży końcowy odczyt: **434131 plików, zero błędów**. 311795 zgodnych
plików jest w aktywnym D (76020477970 B), 122336 starszych lub brakujących
wersji zabezpieczono osobno (9822323477 B). Łącznie 85842801447 B.
W podglądzie migracji **179 jobów, 55 źródeł z ponownym SHA, blockers=[]**.

Pełne before/after: `D:\game_predicotr\artifacts\maintenance\legacy-c-20261022\job-paths-preview.json`.
SHA pierwotnego podglądu v1 (nie uruchamiać po TASK-1086):
`e8b592828aea9e4f33dc701ec85ec95089b84a9a820734b549e3f6835345efe2`.
Zmiana joba po podglądzie wymaga ponownego podglądu; nie osłabiać walidacji.

Aktualizacja TASK-1086: przygotowano preview **v2**, wymagający jawnego katalogu
artefaktów, dokładnego zestawu manifestów z SHA oraz kontroli odpowiedzi API.
Plik `job-paths-preview-v2.json` w tym samym katalogu zabezpieczenia: 179 jobów,
176 manifestów, 55 źródeł z ponownym SHA, blockers=[]. SHA:
`b6089b4c5cff7b42b11673f11f1b973c6439fd20fb69b47ccbecdd147ec96ca0`.
Nie uruchomiono apply. Operator zastąpił pełny skan historii analizą
rzeczywistych zależności od plików; wynik i ograniczenia opisano niżej.

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

Poniższa tabela podaje końcowe rozliczenie jednej rundy poprawek TASK-1086.
Nie stanowi zgody na apply ani usunięcie C. Warunki operatorskie trzeba
spełnić dla aktualnego stanu usług i danych.

| Uwaga | Rozliczenie i warunek przed wykonaniem |
|---|---|
| P2-1 | Rozwiązane w v2: jawny artifact_root, kompletny zestaw ID/SHA manifestów zapisany w preview; brak albo zmiana manifestu blokuje apply. Zweryfikowano 176 manifestów. |
| P2-2 | Kontrola loadera dotyczy procesu skryptu. Nie kontroluje kodu już uruchomionych workerów. Scalenie oraz restart wszystkich workerów przez operatora i weryfikacja ich katalogów są obowiązkowe przed apply. |
| P2-3 | Rozwiązane: apply wylicza dozwolony after_payload z before i korzeni; dodatkowa zmiana jest odrzucana także po przeliczeniu SHA. |
| P2-4 | Rozwiązane: obie ścieżki managed reprocess dziedziczą receipt. Test nowego procesu usuwa stare źródło i zarządzany oryginał; odtworzenie z D zachowuje bajty manifestu. |
| P2-5 | Rozliczone w zakresie jawnie zmienionym przez operatora: wszystkie 133 kolumny ścieżkowe/108 tabel oraz analiza konsumentów JSON i odpowiadających danych. Pełny skan dowolnej historii poza zakresem; szczegóły poniżej. |
| P2-6 | Rozwiązane: sześć asercji rzeczywistego budowania argumentów Claude, łącznie 16 asercji CLI PASS, bez ponownego audytu. |
| P2-7 | Rozwiązane: izolowany PostgreSQL z Alembic head; konflikt stanu, NOWAIT, rollback po pierwszym UPDATE, zapis JSONB i retry po utracie odpowiedzi — PASS. Brak/zmiana manifestu dodatkowo testowane bez danych operatora. |

## Kolejny krok po akceptacji

Aktualizacja zabezpieczeń TASK-1086 rozlicza P2-1, P2-3, P2-4, P2-6 i P2-7:
apply przypina katalog i zestaw/SHA manifestów, wylicza dozwolony payload,
kontroluje jego serializację API; obie ścieżki reprocessu dziedziczą receipt.
Nowy proces odtwarza oryginał także ze sklonowanego manifestu po relokacji.
P2-2 pozostaje jawną bramką wdrożenia i restartu usług przez operatora.
Potwierdzenie testami: 76 testów Python, pełna transakcja PostgreSQL na
własnej bazie UUID (konflikt, NOWAIT, częściowy zapis/rollback, retry, JSONB),
test wrappera i GET API, typy/generowanie klienta oraz 16 asercji CLI — PASS.

## Analiza rzeczywistych zależności od plików — TASK-1086

Operator zatwierdził zastąpienie pełnego skanu historycznych tekstów i JSON
analizą konsumentów plików i odczytem odpowiadających danych. Końcowy odczyt
READ ONLY objął wszystkie **133 kolumny ścieżkowe w 108 tabelach**:
complete=true, errors=[]. Jedyne trafienie: 14 historycznych
remote_manual_selection_sessions.host_base_path, rozliczonych powyżej.
Inwentaryzacja uwzględnia teksty, domeny i tablice; kolumny dobierane po
nazwach path/directory/root/filename/uri/url/location. To nie zastępuje
analizy ścieżek zapisanych w dowolnym JSON, którą przeprowadzono osobno.

| Źródło operacyjne | Konsument i wynik |
|---|---|
| jobs.input_payload.source_directory / receipt | Loader managed originals i jobów; 179 rekordów objętych preview v2, 55 źródeł D z SHA, 176 niezmiennych manifestów z SHA. Wymagana zatwierdzona relokacja. |
| V7 context_payload.outputRoot i feedbackSnapshot.sourceRoot | Worker semi_automatic_selection/v7_delivery.py:_operation_output_root i storage/v7_selection_feedback.py:verify_feedback_source; odczyt całej tabeli operacji V7: 0 rekordów. |
| jobs.input_payload.source_manifest_relative_path | Worker job.py i storage/local_source_manifest.py:load_local_source_manifest, absolutny sourceRoot plus względne files[].relativePath; 0 odwołań w jobach, 0 lokalnych plików source-manifest.json w katalogu eksportów. |
| artifacts/v7-draft-folders/*.json.directory | Worker v7_draft_catalog.py:draft_folder/read_draft; 0 plików przypiętych draftów. |
| Ścieżki zdjęć, modeli, cohortów, wydań | image_review_assets.py:_safe_candidate, symbol_model_snapshot_resolver.py:_managed_path, grid_training_cohort_artifacts.py, grid_quality_manifest.py oraz release_artifacts.py:resolve_mobile_release_apk kontrolują względne lokalizacje i granice skonfigurowanych korzeni. Skan kolumn nie znalazł C. |
| Niezmienne dowody / eligibility | Historyczne pochodzenie, sprawdzany hash dowodu; brak otwierania historycznych ścieżek przez runtime. Nie przepisywać. |
| ApiSettings w nowym procesie | artifact_root, import_root, runtime V7, model OCR, review_crop_root i review_source_root wskazują D. Korpusy CLI/testów nie są utrwalonymi źródłami API/workera. |

Prywatne wyniki w katalogu zabezpieczenia:
`database-operational-paths.json` i `operational-json-sources.json`.
Ten drugi potwierdza read_only=on, complete=true, errors=[], brak dalszych
legacy_dependencies. Analiza nie znalazła dodatkowego operacyjnego źródła
plików z absolutnym korzeniem C poza jobami i pustymi wygasłymi sesjami.

Pełny wcześniejszy skan historii pozostaje celowo nieukończony: 825/2092
kolumn, 169/392 tabel, baza 147370317503 B (~137.3 GiB). Nie dowodzi braku
tekstu C w pozostałej historii. Checkpointy: database-scan-partial-summary.json
oraz database-paths-part0.json–database-paths-part2.json. Odcinki odczytu
REPEATABLE READ pochodzą z różnych chwil; nie są jedną globalną migawką.
Wszystkie własne procesy skanu zakończone. Własne bazy testowe TASK-1086
usunięte; baza operatora pozostała bez zmian.

Mypy API z zachowaniem typów Pydantic i domeny, pomijając importowany graf
storage/workera, daje identyczne 23 wcześniejsze błędy w 13 plikach jak na
niezmienionym main. Brak nowych błędów w zmienionych modułach; pełny typecheck
API nie jest zielony. Mypy dwóch skryptów i typy klienta — PASS.

## Wykonanie po odrębnych zgodach

Przygotowanie narzędzia nie jest odbiorem migracji. Po zamknięciu taska i
zgodzie na scalenie: wdrożyć poprawkę z gałęzi codex/retire-c-copy.
Operator restartuje API i wszystkie workery w swoich terminalach.
Odświeżyć podgląd (stare updated_at mogą się zdezaktualizować), pokazać
operatorowi liczbę wierszy, before/after oraz SHA i uzyskać odrębną zgodę
na migrację danych. Następnie apply z zatwierdzonym SHA i ponowny odczyt.

Dopiero po sprawdzeniu z nowego procesu, kontroli zabezpieczenia i zgodzie
na odcięcie: czasowo zmienić nazwę C, wykonać odbiór bez dawnej nazwy
(zdjęcia, przegląd, odczyt manifestu), zachować możliwość cofnięcia nazwy.
Nie uruchamiać importu na próbę na danych operatora bez osobnej zgody.
Usunięcie starego katalogu pozostaje osobną, końcową decyzją.

Worktree przygotowania ma junction `.venv` i `node_modules` do głównego D;
przy sprzątaniu najpierw usunąć same dowiązania zgodnie z merge-to-main.
