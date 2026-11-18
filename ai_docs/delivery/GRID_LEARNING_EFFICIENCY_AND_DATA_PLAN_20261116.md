---
title: Wydajne przygotowanie i wartościowe dane do uczenia detektora oraz siatek
status: accepted
last_updated: 2026-11-16
---

# Plan usprawnienia uczenia Mumie a2

Stan: zakres całego planu zaakceptowany przez operatora 16.11.2026 poleceniem
„możesz wdrożyć cały plan”, z wymaganiem audytu krzyżowego. Zgoda obejmuje
implementację P1–P8 w izolacji; wcześniejsze ograniczenia dotyczące działającej
aplikacji, GPU i integracji obowiązują. Przed kosztowną realizacją pozostaje
potwierdzenie kosztu po ostrzeżeniu zgodnie z AGENTS.md. P1–P8 są lokalnymi
oznaczeniami zadań; numery TASK nadać przy rozpoczęciu po sprawdzeniu numeracji.
Każdy task otrzyma osobny plik zgodny z TASK_TEMPLATE.md.

Uzupełnienie 16.11.2026: implementacja wyłącznie w osobnym worktree i na osobnej
gałęzi, z izolacją zasobów wykonawczych opisaną poniżej. Audyt krzyżowy planu
przez Claude Code jest zablokowany błędem autoryzacji CLI; brak raportu i PASS.
Kontrola dokumentacji nie zastępuje audytu. Ślad wykonania: TASK-1233.

Weryfikacja warunków wejścia po zleceniu wykonania: polecenie `git worktree add`
odmówiło zapisu `.git/refs/heads/codex/grid-learning-efficiency-20261116.lock`
(`Permission denied`). Polityka środowiska odrzuciła eskalację uprawnień;
zarządzane narzędzie aplikacji `create_worktree` także zwróciło błąd. Kodowania
nie rozpoczęto. Wymagany worktree i gałąź nie zostały potwierdzone jako utworzone.
Lokalny `claude auth status --json` zgłasza loggedIn=true, lecz świeże wywołanie
audytu aktualnego planu ponownie zwróciło 401 OAuth access token has expired,
bez raportu i bez zużycia tokenów modelu. `storage/grid_preparation_progress.py`
nie istnieje w HEAD `main`;
zależności od niezatwierdzonych zmian TASK-1230 trzeba rozstrzygnąć przed P1.

## 1. Stan obecny i dowody

Odczyty lokalnego API, kodu i transakcji PostgreSQL READ ONLY z 16.11.2026.
Repo: `D:\game_predicotr`, HEAD `ace8de10`; istotne pliki mają również lokalne,
niezacommitowane zmiany. Analiza uwzględnia te zmiany, nie tylko HEAD.

| Przebieg | Populacja do przygotowania | TRAIN | VALIDATION | REGRESSION | Czas zapisany w budżecie treningu |
|---|---:|---:|---:|---:|---:|
| Detektor i siatki, 8 listopada | 479 zdjęć | 10 zdjęć / 90 plansz | 5 / 45 | 13 / 21 | 1163 s, około 19,4 min |
| Punkty siatki, 13 listopada, najnowszy zakończony | 7039 zdjęć | 379 / 517 | 19 / 60 | 13 / 21 | 2099 s, około 35 min |
| Obecny detektor i siatki | 25 631 zdjęć | 10 / 90 | 5 / 45 | 13 / 21 | trening jeszcze nie powstał w chwili odczytu |

Źródła tożsamości:

- obecny learning/job: `42f30e0e-9707-4cf9-aaf6-10482f6e9d60`;
- obecna kohorta: `19a52a6c-99ea-56ba-b713-c918338db415`;
- gra: `246a1f54-eee8-49d5-b11a-0fde70e5eecd`;
- obecna baza: `01767a49-980e-5ab6-962e-e22d8414a93e`, default revision 5;
- trening z 8 listopada: `42012366-ab65-4668-a5fc-1236951cd905`,
  kohorta `dae22c06-33cf-5f6a-accc-ce3166d13cf3`;
- trening z 13 listopada: `fedc6bcf-05dd-4870-9590-42371884e6ef`,
  kohorta `7e239be4-a04b-57fa-860c-b278cd41379a`.

**Zestaw SHA-256 plików 10 zdjęć obecnego TRAIN jest identyczny z TRAIN detektora
z 8 listopada.** Nie oznacza to identycznych rewizji etykiet ani bezcelowości
treningu: baza modelu jest inna. Zwiększenie populacji ponad 53 razy nie zwiększyło
jednak liczby zdjęć TRAIN detektora. Liczba plansz nie jest liczbą niezależnych
zdjęć; niezależność po filmach nie została tu dowiedziona.

Aktualny raport wymienia m.in. 24 907 przypadków HUMAN_APPROVAL_REQUIRED,
25 616 PHOTO_NOT_FULLY_ANNOTATED i 385 SCREEN_PARTIAL_PHOTO_EXCLUDED.
Liczniki przyczyn nakładają się; nie należy ich sumować ani zakładać,
że wszystkie wykluczone zdjęcia można po korekcie przypisać do TRAIN.

Potwierdzone mechanizmy kosztu:

1. `_materialize` w `application/grid_training_cohort_commands.py` odwiedza
   całą populację, po 5 pozycji, także `used=false`: 5127 stron.
   Obrazy kopiuje tylko dla `used=true`; koszt wykluczonych to przede wszystkim
   metadane, pliki stron, transakcje i ponowne podejmowanie joba.
2. `SqlAlchemyGridTrainingCohortRepository.summary_view` iteruje po wszystkich
   dotychczasowych stronach materializacji. Wywołania widoku podczas kolejnych
   komend i receiptów ponawiają pracę rosnącą z liczbą stron.
3. `GridCorrectionLearningJobHandler.__call__` wykonuje jeden krok na przejęcie
   joba. `GridCorrectionLearningService.advance` odczytuje przygotowany artefakt
   i widok kohorty przed kolejną stroną. Wielkość narzutu wymaga pomiaru P1.
4. `next_materialization` używa `page_index + 5`, a manifest `pageCount=(N+4)//5`.
   Sama zmiana MATERIALIZATION_PAGE_SIZE byłaby niekompatybilna.
5. Etap rodzica `learning` oraz zachowane `data_prepared=100%` nie dowodzą startu
   GPU. Faktyczny start wymaga istniejącego trainingRunId i kroków treningu.

Historyczny czas budżetu nie obejmuje całego przygotowania i wszystkich przerw.
Brak profilu czasowego SQL/pliki/kolejka nie pozwala jeszcze przypisać procentów
kosztu ani zagwarantować czasu po poprawce. Prognoza 14–15 podana wcześniej była
ekstrapolacją krótkiego okna, a nie wiarygodnym terminem całego workflow.

## 2. Cel, zakres i proponowane decyzje

Zalecenie: najpierw usunąć powtarzaną pracę przygotowawczą, następnie zwiększyć
różnorodność prawidłowo oznaczonego TRAIN. Lokalny model wizyjno-językowy jest
opcjonalnym eksperymentem pomocniczym, nie zależnością całego uczenia.

- Rozdzielić trzy zbiory: pełna populacja potrzebna do ochrony podziału;
  kwalifikowane przykłady do treningu/oceny; kolejka zdjęć do oznaczenia.
- Zachować wszystkie dowody ról, aliasów, chronionego sąsiedztwa i sequence_number.
  Ograniczać koszt obsługi metadanych, nie usuwać tych zabezpieczeń.
- Nowe zdjęcia detektora mają kompletne, ludzkie oznaczenia całej strony;
  brakująca adnotacja nie jest negatywnym przykładem obiektu.
- Częściowo oznaczone zdjęcia mogą zasilać model punktów siatki wyłącznie przez
  istniejącą lub jawnie wersjonowaną ścieżkę geometrii, z osobnymi maskami strat.
- VALIDATION i REGRESSION pozostają chronione. Ranking TRAIN, dobór przykładów
  i strojenie nie mogą korzystać z błędów na końcowym REGRESSION.
- D-611, D-612, D-613, D-614 i D-616 pozostają obowiązujące: brak arbitralnego
  limitu populacji, wymagane polepszenie, istniejące progi i budżet GPU.
- Zachować jeden parent, te same dzieci, idempotency i kohortę obecnego joba.
  Nie wstrzykiwać nowych etykiet, receptur lub snapshotu do jego przypiętego wejścia.
  Nowa polityka danych będzie dotyczyć dopiero jawnie zleconej kolejnej iteracji.
- Zachować general i odrębne wykonanie GPU. Jeden punkt uruchomienia/nadzoru;
  image-selection opcjonalny, domyślnie wyłączony w profilu uczenia. To nie jest
  sposób na przyspieszenie pojedynczej sekwencyjnej pętli.

### Obowiązkowa izolacja wykonania

Wymaganie operatora: praca nad tym planem nie zmienia działającej aplikacji ani
bieżących uruchomień. Osobny worktree izoluje kod, lecz nie izoluje bazy, dysku,
rejestru workerów ani GPU. Poniższe warunki dotyczą wszystkich P1–P8.

1. Przed kodowaniem P1 utworzyć osobną gałąź
   `codex/grid-learning-efficiency-20261116` od potwierdzonego commita `main`
   i osobny worktree `D:\game_predicotr\worktrees\grid-learning-efficiency`.
   Operator potwierdził, że cała praca ma pozostać w `D:\game_predicotr`;
   wcześniejsza propozycja worktree pod `D:\workspace` przestaje obowiązywać.
   Najpierw sprawdzić zajętość obu nazw; kolizja wymaga innej jawnie zapisanej
   nazwy, bez przejmowania istniejącej pracy. Zapisać commit bazowy, ścieżkę,
   gałąź oraz wynik kontroli izolacji w tasku P1 i CURRENT_STATE worktree.
2. `D:\game_predicotr` pozostaje checkoutem działających usług. Nie przełączać
   tam gałęzi, nie zmieniać kodu, konfiguracji ani zależności aplikacji; nie
   przenosić, stashować ani commitować zastanych zmian. Analiza tego planu
   uwzględniała niezacommitowane zmiany, których nowy worktree sam nie odziedziczy.
   Przed P1 porównać potrzebne symbole z bazą: jeżeli wymaganej poprawki nie ma
   w `main`, zależny task jest blocked do ustalenia jej przeniesienia. Nie
   kopiować automatycznie całego brudnego checkoutu. Dokument i jego odnośnik
   przygotowano wcześniej w checkoutcie głównym; przy wykonaniu przenieść
   wyłącznie uzgodniony zakres dokumentacji, bez usuwania pozostałych zmian.
3. Własne środowiska Python, zależności Node oraz pliki konfiguracji worktree.
   Bez junction/symlink do zapisywalnych katalogów głównego checkoutu i bez
   instalowania pakietów do jego `.venv` lub `.venv-vision-lab`. Sprawdzić
   rzeczywiste ścieżki importowanych modułów i interpreterów z nowego procesu;
   nie mogą przez editable install wskazywać kodu głównego checkoutu.
4. Testy zapisują wyłącznie do osobnej bazy testowej i osobnych katalogów
   runtime, logów, manifestów, modeli, raportów oraz artefaktów. Wymagane są
   osobne uprawnienia bazy, bez dostępu do zapisu w bazie operatora. Przed każdym
   testem integracyjnym/migracją sprawdzić faktycznie rozwiązaną bazę i katalogi
   zapisu, również po rozwinięciu linków. Domyślna konfiguracja produkcyjna,
   brak dowodu odrębności albo wskazanie zasobu operatora = STOP przed zapisem.
   Kopia danych nie uruchamia automatycznie skopiowanych jobów. Nie wolno
   podłączać workera testowego do kolejki ani rejestru lane działającej aplikacji.
5. Bieżący przebieg odczytywać przez istniejące API tylko do diagnozy. Testy
   restartu, utraty odpowiedzi, przejęcia lease, migracji i wznowienia prowadzić
   na kontrolowanej kopii; nie przejmować rzeczywistego joba ani zmieniać jego
   dzieci, budżetu, snapshotu czy aktywnego modelu. Odczyty mają krótkie timeouty;
   ciężki profil SQL lub skan plików wykonywać na kopii, aby nie obciążać pracy
   operatora. Pomiary CPU/I/O prowadzić z ograniczoną współbieżnością i przerwać,
   jeśli wpływają na działające usługi. Brak dostępu do kopii blokuje taki pomiar.
6. API, Admin i workery operatora pozostają bez restartu. Domyślnie używać
   testów bez uruchamiania serwerów. Osobne usługi testowe dopiero po wyraźnym
   poleceniu operatora, z osobną konfiguracją i uprzednio sprawdzonymi wolnymi
   portami; nie przejmować portu, PID, harmonogramu ani procesu innej pracy.
   Odbiór P7 po restarcie komputera wymaga uzgodnionego okna operatora po
   rozstrzygnięciu bieżących uruchomień; do tego czasu ta kontrola jest pending.
7. GPU pozostaje zasobem wspólnym. Oddzielna testowa baza nie daje globalnej
   blokady GPU wobec bazy operatora. P5/P6 i trening odbiorczy P8 czekają na
   zakończenie bieżącego uczenia oraz jawnie przydzielone, wyłączne okno GPU
   z osobnym limitem czasu. Nie uruchamiać VLM ani eksperymentu obok treningu.
   Nie zmniejszać ani resetować budżetu aktualnego przebiegu.
8. Odbiór izolacji wymaga zapisanej kontroli bazy, ścieżek, interpreterów,
   konfiguracji kolejek i braku konfliktu procesów. Test celowo błędnego
   wskazania zasobu operatora ma odmówić uruchomienia przed połączeniem/zapisem.
   Taski mają osobne commity w gałęzi roboczej. Integracja, migracja bazy
   operatora, zmiana workerów i wdrożenie są osobnym, późniejszym zakresem za
   wyraźną zgodą; nie wynikają z zakończenia tego planu ani audytu PASS.

### Audyt krzyżowy planu

Stan: **BLOCKED — CLI_AUTH**, bez niezależnego werdyktu. `Resolve-AuditorCli`
wykrył lokalną instalację Claude Code 16.11.2026. Próba audytu TASK-1233
potwierdziła w `system.init` wybór `claude-opus-5-5`, lecz zapytanie zostało
odrzucone: `401 OAuth access token has expired. Re-authenticate to continue.`
To nie jest dowód przeprowadzenia analizy ani wyczerpania limitu modelu.
Przed kodowaniem wymagana jedna runda audytu tego dokumentu, tylko do odczytu,
przez Claude Code: `claude-opus-5-5`, effort `high`, według CROSS_AUDIT.md.
To konfiguracja warunkowa do potwierdzenia w rzeczywistym wywołaniu. Brak
audytora lub otwarte P0/P1 blokują rozpoczęcie implementacji.

Zakres audytu: zgodność z decyzjami i kodem, izolacja worktree/danych/GPU,
zachowanie tożsamości i wznowień, dobór materiału bez przecieków, mierzalność
odbioru. Zamrożony pakiet obejmuje ten plan i potrzebne odnośniki, bez cudzych
diffów, sekretów i danych obrazowych. Zachować raport i receipt z SHA pakietu;
nie traktować `--version`, przygotowania briefu ani własnego przeglądu jako PASS.
Audyt planu nie zastępuje późniejszego audytu implementacji wymaganego tabelą.

Dowody próby z 16.11.2026: zamrożony brief
`artifacts/audits/TASK-1233_BRIEF_claude.md`, SHA-256
`3f83005a6628e3f476e84c74b4e6f5653403e17be6158db2f3b8e0f718529278`;
receipt i diagnostyka pod
`artifacts/audits/requests/d770b9c935deafd320375574ec4a1eed1bf64d87da3480a1986b2ed8ecc81390/`.
Pierwszy transport zatrzymała automatyczna kontrola bezpieczeństwa z powodu
dodatkowej transmisji do Datadog. Po potwierdzeniu zakończenia jego procesów
drugi transport tego samego pakietu uruchomiono z wyłączoną telemetrią; zakończył
się powyższym 401, bez raportu i z zerowym zużyciem tokenów w wyniku CLI.
Nie wykonano kolejnego ponowienia. Operator musi odnowić logowanie w lokalnym
CLI; stan sesji aplikacji Desktop nie rozstrzyga autoryzacji tego procesu.

Trwała instrukcja operatorska dla kolejnych wywołań audytu: przed startem CLI
ustawić wyłącznie w środowisku procesu audytora
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, `DISABLE_TELEMETRY=1`,
`DISABLE_ERROR_REPORTING=1`, `DO_NOT_TRACK=1`,
`CLAUDE_CODE_ENABLE_TELEMETRY=0` oraz
`CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL=1`. Nie zmieniać proxy,
ustawień zabezpieczeń ani poświadczeń. Według oficjalnej dokumentacji
[konfiguracji sieci](https://code.claude.com/docs/en/network-config) oraz
[telemetrii](https://code.claude.com/docs/en/data-usage) wyłączenie zbędnego ruchu
obejmuje oba hosty Datadog. Flagi zastosowano do drugiego transportu; nie jest
to jeszcze dowód ukończonego audytu ani trwała zmiana domyślnego runnera.

Po potwierdzeniu przez operatora ścieżki `D:\game_predicotr` wykonano jedno
wywołanie audytu aktualnego dokumentu, z worktree wskazanym wewnątrz repo.
Aktualny brief `artifacts/audits/TASK-1233_BRIEF_claude.md`: 67 954 B,
SHA-256 `7c9fb73ee56391160dbbea542cbc244c8d64d29ac5d15d80c72a99eabadaefa5`.
Historia i diagnostyka nowego pakietu:
`artifacts/audits/requests/03ec912760994ae14eb3174ac4d6fc3048257819e637c13b78671ee1070e505a/`.
Model z init: claude-opus-5-5; effort high żądany. Wynik: CLI_AUTH, 401,
input_tokens=0, output_tokens=0, total_cost_usd=0; brak raportu, PID 37304
zakończony. Nie ponawiano transportu tego pakietu. Wynik podtrzymuje blokadę P1.

### Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/DOC_INDEX.md`;
- `ai_docs/process/CURRENT_STATE.md`, `DECISION_LOG.md`, `PLAN_STANDARD.md`,
  `TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`, `CROSS_AUDIT.md`;
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`;
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`, `API_CONTRACT.md`,
  `CODE_MAP.md`, `CODE_MAP_SYMBOLS.md`;
- `ai_docs/tasks/1230-grid-learning-background-preparation.md`;
- przy implementacji mieszanego treningu: wskazane w DOC_INDEX plany
  `delivery/EFFECTIVE_GRID_LEARNING_PLAN_20261111.md` i
  `delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md`; sprawdzić ich wdrożony zakres,
  aby nie dublować istniejącego rozwiązania.

## 3. Etap A — czas przygotowania, postęp i trwałość

### P1 — Izolacja, pomiar etapów i prawdziwy stan uczenia

**Status:** todo. **Goal:** każda minuta i każdy licznik mają jednoznaczny etap.
**Dependencies:** read-only odczyt tego samego joba; zgoda na implementację etapu A;
audyt planu bez otwartych P0/P1. Pierwszą czynnością wykonawczą jest utworzenie
worktree i gałęzi oraz odbiór izolacji według sekcji 2, przed zmianą kodu.

**Scope / Technical notes:** mierzyć oddzielnie split, capture, materialization,
freeze, oczekiwanie, ładowanie GPU, kroki, eksport i ocenę. Licznik zatwierdzonej
pracy z kursora/commitu jest odrębny od heartbeat. Nie resetować czasu postępu przy
samym przejęciu lease. Po 300 s bez rzeczywistego postępu i bez jawnej zależności
pokazać zastój, nazwę blokera i czas ostatniego ruchu. Brak połączenia oznacza stan
nieznany. ETA dopiero po stabilnym oknie, osobno na etap, z zakresem i licznością.

**Expected files:** istniejące `services/worker/src/game_predictor_worker/images/grid_correction_learning_handler.py`
(`__call__`), `services/api/src/game_predictor_api/storage/grid_preparation_progress.py`,
`application/grid_correction_learning.py`, `schemas/grid_correction_learning.py`,
`api/grid_correction_learning.py`, panel i state w
`apps/admin/src/features/model-quality/`, generowany klient i API_CONTRACT.
Proponowane opcjonalne pola odczytu: `phase`, `completedUnits`, `totalUnits`,
`lastCommittedProgressAt`, `waitingReason`, `estimatedRemainingSecondsRange`.
Kontrakt finalizuje backend; stare pola zachować do migracji konsumentów.
Proponowana kontrola środowiska: `scripts/check_learning_worktree_isolation.py`
i test w `scripts/tests/`; użyć istniejących resolverów konfiguracji i ścieżek,
aby preflight sprawdzał zasoby faktycznie używane przez test/worker. Raport
preflight redaguje poświadczenia; zapisuje tylko tożsamość zasobów i wynik.

**Acceptance / tests:** freeze po materializacji nie pokazuje końca uczenia;
konfiguracja bazy operatora, współdzielonego katalogu zapisu lub importu kodu
z głównego checkoutu blokuje uruchomienie testu przed operacją na tym zasobie;
świeży heartbeat bez pracy wykrywa zastój; zerwane API nie daje zielonego stanu;
restart zachowuje pomiary; kolejka GPU ma jawne oczekiwanie. Rozszerzyć istniejące
`test_grid_preparation_progress.py`, `test_grid_correction_learning_api.py`,
`test_grid_correction_learning_handler.py` i test panelu. Pasywny profil 20
normalnych stron, bez ponownego wykonywania operacji na danych operatora.

**Risks / Outcome:** dokładny udział SQL, serializacji, dysku i kolejki pozostaje
do pomiaru; nie podawać przyspieszenia bez danych. Outcome wypełnia wykonawca.

### P2 — Usunięcie narzutu przy zachowaniu bieżącego snapshotu

**Status:** todo. **Goal:** ograniczona praca na stronę, bez skanowania całej historii
stron w każdej iteracji. **Dependencies:** P1, test zgodności ze starym kursorem.

**Scope / Technical notes:**

1. Oddzielić lekki nagłówek sterowania od pełnego publicznego widoku kohorty.
   `advance` potrzebuje statusu, rewizji, kursora i pinów; nie całego podsumowania.
2. Utrwalić sumy materializacji w nowym polu JSONB `materialization_progress`
   kohorty, poza `document`, historycznym `summary` używanym do checksumy preview
   i manifestem. Migracja Alembic addytywna, nullable dla starych rekordów.
   Sumy i oznaczenie ostatniej strony aktualizować w tej samej transakcji CAS co
   strona i receipt. Replay istniejącego receipt nie dodaje ponownie liczników.
   Brak projekcji: odbudowa z istniejących stron w osobnej kontrolowanej operacji,
   z kontrolą rewizji; przed jej ukończeniem jawny legacy fallback.
3. Zachować format starych stron po 5 i ich tożsamości. Dla bieżącej kohorty
   grupować pracę wykonawcy w maksymalnie 20 kolejnych stron lub 10 s na przejęcie.
   Granicą zapisu nadal pojedyncza strona, kontrola anulowania/lease między stronami,
   a po limicie zwolnienie general. To limit koordynacji, nie timeout całej kohorty.
4. Niezmienny przygotowany artefakt parsować raz na ograniczony cykl, po kontroli
   SHA; aktualność danych nadal sprawdzać w wymaganych granicach zapisu/freeze.
   Wykluczonych źródeł nie dekodować ani nie kopiować — istniejące `used=false`
   zachować. Osobną zmianę liczby pozycji w pliku odłożyć do wersjonowanego formatu.

**Expected files:** `application/grid_correction_learning.py:advance`,
`application/grid_training_cohort_commands.py:_materialize,execute`,
`storage/grid_training_cohort_repository.py:view,summary_view,next_materialization`,
`storage/grid_training_cohort_models.py:GridTrainingCohortModel`, handler rodzica;
nowa migracja w istniejącym katalogu Alembic, numer po odczycie aktualnego head.

**Acceptance / tests:** zgodność członków, etykiet, ról, zakresów i kolejności
z referencją; poprawny ostatni fragment; restart po zapisie pliku/przed DB i po DB
przed odpowiedzią; brak podwójnych liczników, drugi worker odrzucony, anulowanie
między stronami. Testy istniejące: cohort_storage, cohort_requests, background
preparation PostgreSQL, freeze_selection i worker learning_handler.
Cel pomiarowy: co najmniej 5× szybsza materializacja na tej samej skończonej kopii
danych i brak wzrostu kosztu nagłówka z długością prefiksu; to kryterium odbioru,
nie obietnica. Jeśli pomiar nie osiąga celu, raport przyczyny bez maskowania.

**Deployment / risks:** migrację i restart workera uzgodnić w oknie przekazania
lease. API/Admin restartuje operator, jeśli potrzebny. Stary czytnik ignoruje nowe
pole; projekcja jest odtwarzalna. Nie modyfikować starych artefaktów ani zmieniać
page size w już rozpoczętej kohorcie. Usunięcie migracji nie jest automatyczne.

### P3 — Ponowne użycie niezmienionych dowodów w następnych iteracjach

**Status:** todo. **Goal:** nowa korekta nie powoduje ponownego kosztownego capture
wszystkich niezmienionych zdjęć. **Dependencies:** P1–P2; kompletna mapa zależności.

**Technical notes:** pełny spis metadanych populacji i ochrona podziału pozostają.
Reuse dotyczy tylko niezmiennych dowodów capture/plików. Klucz obejmuje grę,
źródło i checksumy pliku/pikseli, rewizje geometrii/akceptacji/własności,
atest kolejności, dowód rejestru ról i aliasów, politykę oraz wersję preprocessingu.
Preferować już istniejące zahashowane strony i zależności zamiast nowego cache
binarnych obrazów. Indeks reuse w nowej tabeli przez Alembic tylko jeśli istniejący
magazyn nie zapewnia wyszukiwania po całym kluczu. Manifest ma wskazać proweniencję
reuse i zachować retencję assetów. Brak kompletnego dowodu unieważnienia = cache miss.
Finalna kontrola bieżących rewizji pod dotychczasowymi blokadami pozostaje obowiązkowa.

**Expected files:** `storage/grid_correction_split.py:prepare_split,validate_population`,
`storage/grid_training_cohort_evidence.py:GridCohortEvidenceReader`,
`storage/grid_training_cohort_currentness.py:check_member`,
`storage/grid_training_cohort_artifacts.py:GridCohortArtifactStore`, freeze i retencja.

**Acceptance / tests:** wynik cold/warm i po restarcie równoważny; zmiana właściciela,
aliasu, etykiety, źródła lub ochrony testowej unieważnia właściwą grupę; brak dostępu
do oryginału nie jest maskowany cache. Testy adaptera splitu, currentness,
cohort_asset_guard, retention_edges. Nie proponować cichego pominięcia walidacji.
**Risk:** brak dowodu pełnej invalidacji blokuje reuse, nie P1–P2.

## 4. Etap B — materiał i efektywność uczenia

### P4 — Kolejka wartościowych zdjęć do korekty i uzupełnienia

**Status:** todo. **Goal:** dostarczyć operatorowi kolejne 50 różnorodnych zdjęć,
z uzasadnieniem wyboru i brakującymi oznaczeniami. 50 to wielkość kolejki pilota,
nie nowy limit zbioru ani obietnica wystarczającej jakości. **Dependencies:** P1,
istniejące ludzkie korekty i ochrona ról; niezależne od opcjonalnego P6.

**Technical notes:** najpierw wyłączyć chronione rodziny testowe i konflikty;
grupować kopie/rodziny/ciągi przed rankingiem. Używać istniejącego modelu geometrii
i zapisanych korekt, bez pełnego ponownego skanu GPU. Proponowana pierwsza kolejka:
20 miejsc dla potwierdzonych trudnych korekt, 20 dla nowych warunków/perspektyw,
10 dla reprezentatywnej próbki kontrolnej wyboru. Niedobór koszyka uzupełniać
reprezentatywnymi źródłami. Najpierw jeden przedstawiciel rodziny, dopiero potem
kolejny; deterministyczne remisy po stabilnym identyfikatorze, nie po zmianie seq.

W koszyku trudności używać błędu względem dostępnej ludzkiej etykiety; w puli
nieoznaczonej niespójności detekcji przy łagodnych transformacjach, braków rzędu,
przecięcia siatki/krawędzi. Niski confidence sam nie wystarcza. Różnorodność:
perspektywa, skala, oświetlenie, rozmycie, odblask, położenie plansz i źródło.
Każda propozycja ma modelVersion, sourceSHA, revision, policyVersion, reasonCodes,
koszt uzupełnienia i docelowy cel `screen` albo `grid`. Nie sumować arbitralnie
nieporównywalnych confidence różnych modeli. Decyzje człowieka są źródłem etykiet.

Panel pozwala dokończyć wszystkie plansze na wybranym zdjęciu i pokazuje przyrost
**niezależnych pełnych zdjęć**, nie tylko liczbę kliknięć. Chronionych pięciu
zdjęć VALIDATION nie powiększać o TRAIN; nowe niezależne kontrole przypinać przed
oglądaniem błędów kandydata. Wyniku na pięciu zdjęciach nie przedstawiać jako
niezawodności całej gry.

**Expected files:** istniejące `domain/grid_learning_material.py:material_report`,
`storage/grid_correction_split.py:prepare_split`, `domain/grid_correction_incremental_split.py`,
panel jakości i obecny edytor korekt; proponowane
`domain/grid_learning_sample_priority.py` (czysty ranking) i jego adapter w
application. Rozszerzenie istniejącego API preview/material, backend → OpenAPI →
klient → wrapper → test żądania, bez równoległego systemu etykiet.

**Acceptance / tests:** brak przecieku po aliasie/importach; 50 podobnych klatek
nie wypiera różnych przypadków; pełna i częściowa etykieta rozróżnione; nowe
zatwierdzenie unieważnia stary ranking. Rozszerzyć test_grid_learning_material,
screen_grid_correction_policy, incremental_split i test panelu. Porównać kolejkę
z losowym wyborem przy tej samej liczbie minut pracy człowieka; mierzyć pełne
kwalifikowane zdjęcia i pokrycie kategorii. Outcome nie deklaruje wzrostu accuracy
bez wyniku P8.

### P5 — Więcej wartości z każdego kroku GPU

**Status:** todo. **Goal:** poprawa modelu przy nie większym uzgodnionym budżecie.
**Dependencies:** P4 i nowe kwalifikowane dane; osobno zatwierdzony eksperyment.

**Technical notes:** repo ma już korekty z wagą 4 i poprawne sprawdzone przykłady
z wagą 1, deterministyczny StepSampler/BalancedSampler, early stopping i ścieżki
ContentTrainingDataset oraz board_only_losses. Nie implementować ich ponownie.
Najpierw sprawdzić faktyczną ekspozycję headów i unikalnych rodzin w domyślnym
screen+grid. W przyszłej wersjonowanej recepturze pełne kadry uczą detektor,
a poprawne częściowe etykiety wyłącznie punkty siatki; maski chronią brakujące
cele. W istniejącym content workflow wykorzystać gotową obsługę po potwierdzeniu
jej zakresu i zgodności. Zapis receptury/samplera w fingerprint i checkpoint.

Pierwsze porównanie ma tylko dwa ramiona: bieżący sampler oraz sampler mieszający
trudne i reprezentatywne rodziny TRAIN, oba na tym samym rozszerzonym zbiorze,
tej samej bazie, rozdziale, augmentacji i budżecie. Nie zmieniać jednocześnie LR,
rozdzielczości i danych. LR 1e-4 pozostaje zgodnie z D-614. Suma kosztu ramion,
eksportu i oceny mieści się we wspólnym jawnie zatwierdzonym limicie; brak środków
kończy eksperyment, nie tworzy automatycznie następnego joba.

Profilować czas dostarczenia batcha i GPU. Jeśli potwierdzi się koszt ponownego
dekodowania, rozszerzyć jednoklatkowy cache `GridCohortSnapshot` do ograniczonego
LRU w RAM (proponowany maks. 512 MiB na proces), po kluczu checksum/preprocessing.
Augmentacje nadal odtwarzać z seed/step; nie cache'ować losowego wyniku jako stałego.
Augmentacje geometrii transformują także cele; fotometryczne zachowują etykiety.

**Expected files:** `training_core/grid_training.py:train,StepSampler,BalancedSampler`,
`grid_training_admission.py`, `grid_rescue_training.py`,
`images/grid_cohort_dataset.py:GridCohortSnapshot,ContentTrainingDataset`,
istniejący workflow content i rejestr wersji receptur.

**Acceptance / tests:** wznowiony sampler daje te same następne indeksy, utrata
odpowiedzi nie zeruje GPU budget, nieoznaczone plansze nie stają się negatywami,
eksport ONNX zachowuje wybrany wynik; obecne quality gates bez zmian.
Rozszerzyć test_grid_cohort_dataset, test_grid_content_mixed_batch,
test_grid_content_partial_selection, test_grid_training_baseline_floor,
test_grid_correction_evaluation_pipeline i test_vision_lab_training_core.
REGRESSION sprawdza raz wybranego na VALIDATION kandydata; nie służy do strojenia.

## 5. Etap C — opcjonalne lokalne AI i odbiór

### P6 — Ograniczony pilot lokalnego modelu wizyjnego

**Status:** todo, opcjonalny. **Goal:** wykazać oszczędność pracy człowieka ponad
ranking P4. **Dependencies:** P4, wolny GPU, zgoda na pobranie i pilot.

Zalecany kandydat do sprawdzenia: `Qwen/Qwen3-VL-2B-Instruct-GGUF`, Q4_K_M
z właściwym vision encoderem. To przykład wspieranego małego VLM, nie twierdzenie,
że jest najlepszy ani że już działa na tym laptopie. Wagi tekstowe to tylko część
pamięci; encoder, tokeny obrazu, KV i bufory wymagają osobnego pomiaru.
Karta modelu potwierdza format i uruchamianie lokalne; nie potwierdza dokładności
współrzędnych siatek Mumie. W tym kroku niczego jeszcze nie instalujemy.

**Scope:** najwyżej 100 zdjęć pilota z puli do oznaczania (rodziny poza końcowym
testem): 20 do ustalenia promptu, 80 do porównania po zamrożeniu promptu.
Jedno zdjęcie na żądanie, ograniczona rozdzielczość, krótki wynik JSON:
`issueCategories`, `needsFullAnnotation`, `explanation`, `abstain`.
Przypiąć model SHA, encoder SHA, runtime, prompt i wejście. Wynik AI to sugestia,
nie human approval ani ground truth. Geometrię proponuje istniejący specjalista,
człowiek ją zatwierdza; VLM pomaga opisać błędy, nietypowe ujęcia i kolejność review.
Osobny lokalny proces/CLI, bez kolizji portu 8000. Limit jednego wywołania 30 s,
łącznie 30 minut pilota; timeout/OOM = zapisany wynik `abstain`, nie poprawna etykieta.

Obecny preset wymaga około 5 GB wolnej VRAM. VLM i trener korzystają kolejno ze
wspólnej dzierżawy GPU; przed treningiem zakończenie VLM i pomiar odzyskanej VRAM.
Kolejka uczenia ma pierwszeństwo. Bez przepuszczania 25 tys. zdjęć przez VLM.

**Expected files:** proponowany adapter
`services/worker/src/game_predictor_worker/images/grid_annotation_adviser.py`,
wersjonowany artefakt sugestii; istniejące `training_core/gpu_lease.py`,
ranking P4 i UI korekt. Nowe zależności wyłącznie w izolowanym runtime.

**Acceptance / tests:** schema JSON, abstain, niepoprawny obraz, stale source,
timeout, brak VRAM i odmowa lease; żadna sugestia nie zmienia etykiet samoczynnie.
Warunek pozostawienia: na tych samych 80 zdjęciach mniej czasu człowieka o co
najmniej 20% bez pogorszenia zweryfikowanej poprawności, po wliczeniu obsługi
błędnych sugestii. To próg decyzji pilota, nie wynik ani gwarancja.
Jeżeli nie pomaga, pozostać przy P4. P6 nie blokuje P7–P8.

### P7 — Jeden trwały nadzór i opcjonalne procesy robocze

**Status:** todo. **Goal:** działanie i alarm przetrwają zamknięcie sesji agenta.
**Dependencies:** P1–P2; dostęp do natywnego środowiska Windows; odbiór procesów
wyłącznie na konfiguracji testowej. Instalacja nadzoru dla działającej aplikacji
oraz próba po restarcie komputera wymagają późniejszego okna operatora.

**Scope / Technical notes:** rozszerzyć istniejący manager, bez nowej kolejki.
Profil uczenia: general i grid-training, selekcja uruchamiana jawnie tylko gdy
potrzebna. Jeden entry point i log nadrzędny. Nadzór czyta istniejący job i dzieci;
nie wysyła nowego startu. Kontrola co 15 s, trwały zapis wyniku, brak postępu przez
300 s = alarm z przyczyną; jawne oczekiwanie na lease/dependency nie jest błędem.
Naprawa techniczna zachowuje job i budżet; brak poprawy po jednej próbie oznacza
blokadę, bez pętli restartów. Brak API nie uruchamia jego zastępczej instancji.

Uruchomienie pod kontem użytkownika poza drzewem procesu agenta, np. natywne
zadanie Windows dopiero po sprawdzeniu dostępności i zapisaniu konkretnej
konfiguracji. Nie uznać sukcesu na podstawie zwróconego PID: sprawdzić po zamknięciu
procesu inicjującego, w nowej sesji, a następnie po ponownym uruchomieniu komputera.
Jeśli środowisko nie pozwala tego dowieść, status blocked, z komendą operatora.
Powiadomienie najpierw lokalne i sprawdzone; dostarczenie do czatu wymaga osobno
działającego połączenia. Nie deklarować stałego nadzoru na podstawie harmonogramu.

**Expected files:** `scripts/manage_worker_lanes.ps1`,
`scripts/Start-GridCorrectionLearning.ps1`, `jobs/lane_runtime.py`, `cli.py`;
proponowana instrukcja profilu uczenia w `ai_docs/guides/`.
**Acceptance / tests:** one-shot nie zastępuje właściciela, jeden general,
restart/wznowienie tej samej pracy, brak połączenia alarmuje, GPU wyłączony nie
blokuje diagnozy. Istniejące test_worker_cli i test_worker_lane_runtime oraz
odbiór w nowym natywnym procesie. API/Admin bez restartu agenta.

### P8 — Odbiór skuteczności całego przepływu

**Status:** todo. **Goal:** raport dowodzący czasu, jakości i trwałości.
**Dependencies:** P1–P5 i P7; P6 tylko jeżeli przeszedł własny pilot.

**Scope:** porównać cold preparation, następne przygotowanie po nowych korektach,
liczbę pełnych TRAIN i niezależnych rodzin, czas oznaczania, czas GPU, poprawność
detektora, punktów i cięcia pól. Oddzielić test optymalizacji na tej samej kohorcie
od eksperymentu nowych danych. Pokazać model bazowy, dokładny manifest, recepturę,
wybrany checkpoint, ONNX i wyniki per gra. Niewykorzystane warianty pozostają jawne.

**Acceptance:** tylko `completed` + `PASS` + candidateVersionId + aktualny raport
i istniejące zgodne artefakty uprawniają do komunikatu „gotowy do użycia”.
FAIL jakości jest prawidłowym wynikiem eksperymentu, nie powodem obniżenia progów.
Aktualny model pozostaje aktywny do osobnej decyzji operatora.

**Expected files / verification:** raport proponowany
`ai_docs/quality/GRID_LEARNING_EFFICIENCY_ACCEPTANCE_20261116.md`, Outcome każdego
taska, CURRENT_STATE. Test e2e na izolowanej bazie i jedna jawnie zlecona kolejna
iteracja GPU, z budżetem określonym przed startem. Nie zastępuje ona istniejącego
joba w trakcie jego działania. Odbiór wskazuje także niewykonane kontrole.

## 6. Weryfikacja, budżety i kolejność wdrożenia

Zadania wykonujemy A: P1 → P2 → P3; B: P4 → P5; C: opcjonalne P6, następnie
P7 → P8. P7 można wykonać po P2 przed B, jeśli priorytetem jest ciągły nadzór.
Akceptacja jednego etapu nie uruchamia automatycznie następnego. Przed etapem
implementacji wymagane ostrzeżenie o koszcie zgodnie z AGENTS; nie ma wiarygodnego
szacunku procentu pakietu. P2/P3 są najbardziej ryzykowne ze względu na wznowienia,
cache i migracje; P4 wymaga także pracy człowieka, a P5/P6 kosztu GPU.
Polecenie operatora z 16.11.2026 obejmuje cały plan i pozwala kontynuować pomiędzy
etapami po kontrolach. Ostrzeżenie przekazane po tym poleceniu: osiem zadań
obejmuje API/UI, migracje, wznowienia, dobór danych, GPU i nadzór, może zużyć
znaczną część pakietu, bez wiarygodnego szacunku procentowego lub terminu.
Potwierdzenie tego kosztu jest nadal pending; nie rozpoczęto kosztownej części.

Komendy poniżej są planowane, nazwy i ścieżki potwierdzone w repo. Uruchamiać
tylko właściwy podzbiór po zmianie; każdy skończony proces z jawnym timeoutem.
Przykład ograniczonej kontroli jednostkowej, cwd `D:\game_predicotr`:

```powershell
$checkJob = Start-Job -ScriptBlock {
    Set-Location -LiteralPath 'D:\game_predicotr'
    & .\.venv\Scripts\python.exe -m pytest `
        services/api/tests/test_grid_training_cohort_core.py `
        services/api/tests/test_grid_training_cohort_storage.py `
        services/api/tests/test_grid_learning_material.py `
        services/worker/tests/test_grid_correction_learning_handler.py -q
    if ($LASTEXITCODE -ne 0) { throw "pytest exit $LASTEXITCODE" }
}
if (-not (Wait-Job $checkJob -Timeout 120)) {
    Stop-Job $checkJob
    Remove-Job $checkJob
    throw 'Timeout kontroli: sprawdź procesy potomne przed ponowieniem.'
}
try { Receive-Job $checkJob -ErrorAction Stop }
finally { Remove-Job $checkJob }
```

Analogiczna osłona dla scoped ruff/mypy, testów interakcji Admina oraz
`npm run docs:check`, `npm run code-map:check`, `npm run openapi:check`.
API: generacja przez `npm run openapi:generate`; zmiany modułów wymagają regeneracji
mapy kodu. Testy PostgreSQL mają istniejącą flagę
`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1` i tworzą izolowane bazy — nie kierować ich
do danych produkcyjnych. Przykłady: test_grid_learning_background_preparation_postgres,
test_grid_cohort_freeze_selection_postgres i test_grid_training_cohort_storage_postgres.
Po timeoutcie skontrolować potomne procesy przed retry; nie zabijać usług operatora.

Wykonanie: audyt planu → izolowany worktree i gałąź → kontrola zasobów → zmiany
i testy na kopii → raport oraz commity robocze → odbiór operatora. Migracje w tym
zakresie dotyczą wyłącznie izolowanej bazy testowej. P1–P2 muszą zachować czytanie
historycznych kohort i wznowienia sprawdzone na kopii, bez podmiany działającego
workera. P3–P6 nie zmieniają wejścia trwającego uczenia. Nie wykonywać hot patcha,
przekazania żywego lease, merge, push ani wdrożenia w ramach samego wykonania
planu. Późniejsza integracja i wdrożenie wymagają oddzielnej zgody oraz sprawdzenia
zgodności z aktualnym `main` i schematem bazy; po zgodzie restartuje operator.

### Pokrycie wymagań

| Wymaganie | Task | Dowód odbioru |
|---|---|---|
| Brak wpływu na działającą aplikację | P1, obowiązuje P1–P8 | osobny worktree/branch, kontrola bazy i ścieżek, test odmowy złej konfiguracji, wyłączne okno GPU |
| Niezależny przegląd planu | warunek wejścia P1 | raport Claude Code i receipt zgodny z SHA, brak otwartych P0/P1 |
| Krótsze przygotowanie bez utraty danych | P1–P3 | czasy etapów, równoważność manifestu, test restartu i invalidacji |
| Wartościowe nowe przykłady | P4 | pełne kwalifikowane kadry, różnorodność, koszt oznaczenia |
| Lepsze wykorzystanie GPU | P5 | ekspozycja headów, wspólny budżet, poprawa na niezmienionej bramce |
| Ocena sensu lokalnego AI | P6 | pilot 20/80, czas człowieka, poprawność, VRAM |
| Jedna obsługa i rzeczywisty nadzór | P7 | nowa sesja/reboot, alarm zastoju i braku dostępu |
| Potwierdzenie gotowego modelu | P8 | completed/PASS, kandydat, raport, artefakty |

### Ryzyka, granice i niewiadome

- Ten sam plik zdjęcia nie dowodzi tej samej rewizji etykiety; porównać piny przed
  wnioskowaniem o braku nowej informacji. Obecnego joba nie anulowano.
- Bez nowych pełnych adnotacji sam ranking nie zwiększy TRAIN detektora.
- Pięć pełnych zdjęć A daje słabą podstawę uogólnienia; wzmocnić niezależny test
  przyszłych wersji bez ponownego użycia ujawnionych rodzin jako nowego testu.
- Nie zmieniamy celu na modele symboli, nie wdrażamy Redis/Celery ani chmury.
- Brak automatycznej aktywacji, push, merge, destrukcyjnego cleanupu i instalacji AI.
- Nie wykonano benchmarków, nowych treningów, testów nowej implementacji ani pilota
  VLM podczas przygotowywania planu. Ustalono kod i stan, porównano trzy kohorty
  oraz sumy plików TRAIN. Skuteczność propozycji musi zostać zmierzona.

### Źródła zewnętrzne — sprawdzone 16.11.2026

- [Core-set active learning, Sener i Savarese](https://arxiv.org/abs/1708.00489)
  — uzasadnienie łączenia wartości informacyjnej i różnorodności; wyniki pracy
  nie są prognozą poprawy na Mumie.
- [Active learning z modelami wizyjnymi, Gupte i in.](https://arxiv.org/abs/2401.14555)
  — badanie reprezentatywności i niepewności; nie wymaga generatora tekstu.
- [Qwen3-VL-2B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct)
  i [oficjalny GGUF](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF)
  — formaty kwantyzacji i osobny vision encoder; brak dowodu jakości siatek Mumie.

## Przypisanie modeli do zadań

Dostępność i poziomy poniżej potwierdza katalog modeli narzędzi tej sesji.
Przypisanie jest propozycją wykonawczą, nie uruchomieniem agentów. Przy rozpoczęciu
każdego taska przenieść jego wiersz do Recommended execution. Eskalacja: sprzeczność
kontraktu lub brak dowodu ochrony danych → ponowna analiza `gpt-6-astra`, `high`,
przed dalszym kodowaniem. Wymagany audyt planu określa sekcja 2. Na polecenie
operatora z 16.11.2026 każdy task P1–P8 otrzymuje niezależny audyt wykonania
przed commitem, po testach. Nie znosi to obowiązków wcześniej zaakceptowanych
planów używanych w P5. Konfiguracja Claude `claude-opus-5-5`,
`high` pozostaje warunkowa do potwierdzenia wykonania. Brak dostępności
wymaganego audytora blokuje objęty tym obowiązkiem zakres.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| P1 — izolacja, pomiary i postęp | gpt-6.1-sol | medium | Kontrola środowiska i wąski pion statusu z istniejącym API. | Tak: claude-opus-5-5 / high; także audyt planu przed kodowaniem. |
| P2 — narzut materializacji | gpt-6.1-terra | high | Transakcje, receipt, zgodność kursora i przejęcie lease. | Tak: claude-opus-5-5 / high; testy awarii i równoważności. |
| P3 — reuse dowodów | gpt-6.1-terra | high | Pełna invalidacja, ochrona ról i retencja. | Tak: claude-opus-5-5 / high; brak dowodu invalidacji blokuje zmianę. |
| P4 — kolejka danych | gpt-6.1-sol | high | Deterministyczny ranking, ochrona podziału i istniejący edytor. | Tak: claude-opus-5-5 / high; testy przecieków i odbiór człowieka. |
| P5 — efektywność GPU | gpt-6.1-terra | high | Receptury, maski strat, sampler i budżet wznowień. | Tak: claude-opus-5-5 / high; zachować wymagania wcześniejszych planów reuse. |
| P6 — pilot lokalnego VLM | gpt-6.1-sol | medium | Ograniczony adapter i pomiar przydatności. | Tak: claude-opus-5-5 / high; również ocena pilota przez człowieka. |
| P7 — trwały nadzór | gpt-6.1-sol | high | Procesy Windows, własność workera i awarie środowiska. | Tak: claude-opus-5-5 / high; odbiór w nowej sesji i po restarcie. |
| P8 — odbiór całości | gpt-6-astra | medium | Synteza niezależnych dowodów jakości i trwałości. | Tak: claude-opus-5-5 / high; audyt dowodów odbioru. |
