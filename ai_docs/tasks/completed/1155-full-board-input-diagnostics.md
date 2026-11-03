# TASK-1155 — Odtwarzalne wejście sieci i dowody gotowości

## Status

`done` — TASK-1154 ukończony w `0a7ef2d3`; koordynator zlecił T1.

## Goal

Dostarczyć wersjonowany, odtwarzalny zapis rzeczywistego wejścia sieci oraz
ograniczony raport gotowości z istniejących dowodów, bez nowych inferencji i
bez przypisywania ludzkiej poprawności niezatwierdzonym geometriom.

## Context

Plan `ai_docs/delivery/FULL_BOARD_DETECTION_PLAN_20261103.md`, T1 i mapa
wymagań, focused review R2 PASS. Dla 462205 obie zapisane wersje mają identyczny
obszar detektora. Kandydat ma FIT_OUTLIERS. CPU preprocessing odtworzył wejście
320×192; górna krawędź przecina widoczne symbole. Brak kwalifikowanego GT
tej planszy wyklucza dokładną miarę ucięcia względem pełnej planszy człowieka.
Surowych punktów, peak, visibility i miar fit nie zachowano w historycznym JSON.

LIVE: istniejący reader potwierdził 197 etykiet na 134 zdjęciach, zero zdjęć
z kompletem 9 etykiet. Historyczny snapshot: TRAIN 98 zdjęć/146 etykiet,
VALIDATION 13/17, REGRESSION 13/21, screenEligible=0. To różne odczyty.
Źródło: lokalne `artifacts/task1155-preflight/readiness-report.json` i manifest.

## Dependencies / entry conditions

- TASK-1154 zakończony z wersjonowanym commitem; spójny import API/workera.
- Korzystać z istniejącego normalizatora, preprocessingu i readera dowodów.
- Nie zmieniać polityki T0 ani jej konsumentów w T1.
- Przed kodowaniem przeczytać ponownie zaakceptowany T1 i ostateczny task.
- Dane operatora pozostają poza tracked tree. Brak zgody na inferencję CPU/GPU,
  trening, migracje, aktywację modelu, usługi i zapisy operacyjnej bazy.

## Recommended execution

`gpt-6-astra`, `high`. Ochrona dowodów, dokładne transformacje i rozróżnienie
braku danych od poprawności. Niezależny audyt `claude-opus-5-5/high` uruchamia
koordynator wyłącznie na zatwierdzonym pakiecie scoped code/context, bez historii
rozmowy. Eskalacja przy konieczności nowej inferencji lub zmiany ledger.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/FULL_BOARD_DETECTION_PLAN_20261103.md`, T1 i T4
- `ai_docs/requirements/VISION_LAB.md`, sekcje bieżących human labels,
  descriptive measurements, correction cohorts i source protection
- `ai_docs/architecture/VISION_LAB.md`, `GridCohortEvidenceReader`, snapshot
  boundary, bounded read-only qualification i istniejące role
- `ai_docs/quality/FULL_BOARD_PLAN_AUDIT_claude-opus-5-5_R2.md`
- `ai_docs/quality/TASK-1155_AUDIT_ROUND1.md`

## Scope

1. Ścisły wersjonowany kontrakt diagnostyki i odtwarzania wejścia.
2. CLI dla jawnie wskazanych źródeł i zapisanych wyników; bez wywoływania sieci.
3. Ograniczona komenda gotowości reuse istniejącego readera. Same liczniki,
   powody, identyfikatory i hashe dowodów; bez nowego źródła GT.
4. Raport przypadku 462205, dostępności materiału i braków; referencje do
   lokalnych artefaktów operatora, bez kopiowania zdjęć/targetów do repozytorium.
5. Rozróżnienie `readiness_metadata_only` i `diagnostic_comparison`. Tylko
   faktyczne diagnostyczne przykłady wpisuje się do listy użycia, którą T4
   konsumuje przy wykluczaniu nowych B/REGRESSION, z domknięciem kopii/grup.

## Out of scope

Nowa sieć, trening, zmiana marginesu/rozdzielczości runtime, progi kompletności,
nowy ledger, API/UI, migracje i uruchomienie inferencji. Używanie REGRESSION
lub przyszłej VALIDATION-B do wybierania przykładów, progów albo modelu.

## Acceptance criteria

- [x] Oryginalne piksele i zapisane metadane odtwarzają identyczny crop w nowym
  procesie; PNG po odczycie ma dokładnie ten sam SHA surowych pikseli.
- [x] Zapis identyfikuje źródło, model/preset, transformację, canvas, margines,
  interpolację, padding, wersję preprocessingu i dostępność obserwacji.
- [x] Surowe punkty historyczne są `unavailable`, nie zastąpione fitted nodes.
- [x] Brak GT daje stan `unavailable` i null miary ucięcia, nigdy zero błędów.
- [x] Stan historycznej akceptacji i bieżąca kwalifikacja T0 są oddzielone.
- [x] LIVE i frozen mają osobne zakresy, czasy, liczniki i ograniczenia.
- [x] Lista diagnostycznego użycia zawiera 462205 i tylko rzeczywiście użyte
  przykłady; odczyt readiness 134 źródeł nie staje się wyborem projektowym.
- [x] Bez materiału TRAIN z zapisanymi predykcjami dostępne dobre/złe przykłady
  są jawnie niedostępne; nie zastępować ich przykładami kontrolnymi.
- [x] Aktualne role, historia, kopie i bufory bez zmian.
- [x] Testy, lint/typecheck zmienionych części, docs/map check; audyt root PASS;
  task-close, osobny commit i hash zgodnie z procedurą repozytorium.

## Technical notes

Nowy `geometry_core/input_diagnostics.py` ma definiować ścisłe typy rekordu,
`input_stages` i `reconstruct_input`, używając bez zmian
`preprocessing.board_rectifier`, `preprocessing.crop_board`,
`preprocessing.screen_input` i istniejących presetów. Zapis source→crop i
odwrotnej macierzy, wymiarów i interpolacji ma obejmować również wejście
screen stage (768, zaokrąglone wymiary i pad do32), aby nazwa „wejście sieci”
nie ukrywała pierwszego etapu. Znormalizowane źródło ładuje istniejący
`CanonicalSourceLoader`; hash źródła i pikseli musi się zgadzać przed cropem.

Kontrakt `full-board-input-diagnostic-v1`: source identity/checksums,
modelVersionId/bundle/preset SHA, preprocessing version/OpenCV version,
detector screenQuad, transform/size/interpolation/fill, tensor layout/dtype,
crop RGB SHA, obserwacje raw/fitted, GT availability i powody, historical
acceptance oraz oddzielna policy evaluation. Eksport nie dopisuje blobs do DB.
Odtworzenie waliduje wersję, finiteness, invertibility, preset/hash i zgodność
odtworzonej macierzy. Błędna wersja/źródło/transformacja kończy się jawnym
błędem przed publikacją częściowego wyniku.

CLI `scripts/diagnose_full_board_input.py` przyjmuje katalog artefaktów,
jawny sourceId/sequenceNumber/positionIndex oraz przypięte base/candidate
manifesty. Nie wyprowadza pozycji sekwencji z ordinalu detekcji. Musi sprawdzić
istniejący binding `inputs.json` i dokładny zestaw source/model SHA, zanim
połączy obserwacje. Dla 462205 binding istnieje: positionIndex=0 i atest
462205–462213. Opcja replay-inference nie powstaje w T1 bez osobnej zgody.

Nowy adapter `storage/grid_diagnostic_readiness.py` ma wyłącznie orkiestrację
ograniczonego wyboru źródeł i istniejącego `GridCohortEvidenceReader.capture`.
Nie kopiuje logiki approval/currentness/target binding. Readiness nie fabrykuje
roli eligible. Raportuje `fullHumanAnnotatedCount`, a niezbadane dopuszczenie
rolami ma null. Wymusza transakcje read-only i jawny budżet `max_sources` (domyślnie250),
konfigurowalny przez operatora. Stronicowanie źródeł, krótkie limity SQL
i limit całkowitego czasu chronią odczyt. Przekroczenie budżetu daje jawny
raport `partial`, z policzonym zakresem i `nextSourceId`; nie jest pełną
gotowością. Większy jawny budżet pozwala odczytać większą populację, bez
nowego workflow/jobów ani trwałego limitu aplikacji. W dokumentacji count access nie oznacza
użycia do projektowania modelu.

Lista `diagnosticUse` w raporcie jest wersjonowanym dowodem wejściowym T4,
nie drugim rejestrem ról. Zawiera sourceId, byte/pixel SHA, cel i powiązanie
z raportem. T4 odczyta ją przed podziałem A/B i kwalifikacją kontroli oraz
zastosuje istniejące domknięcie kopii/grup. T1 nie zmienia historycznych
TRAIN/VALIDATION/REGRESSION i nie uznaje metadanych readiness za ekspozycję
model selection. Raport ma wprost podać, że samo zapisanie listy nie jest
jeszcze aktywną blokadą kwalifikacji T4.

## Expected files

Istniejące, używane bez zmiany algorytmu:
- `services/worker/src/game_predictor_worker/geometry_core/preprocessing.py`
- `services/worker/src/game_predictor_worker/images/normalization.py`
- `services/api/src/game_predictor_api/storage/grid_training_cohort_evidence.py`
- `services/api/src/game_predictor_api/domain/neural_crop_policy.py` po T0

Nowe pliki:
- `services/worker/src/game_predictor_worker/geometry_core/input_diagnostics.py`
- `services/api/src/game_predictor_api/storage/grid_diagnostic_readiness.py`
- `scripts/diagnose_full_board_input.py`
- `services/worker/tests/test_full_board_input_diagnostics.py`
- `services/worker/tests/test_full_board_diagnostic_cli.py`
- `services/api/tests/test_grid_diagnostic_readiness.py`
- `ai_docs/quality/FULL_BOARD_INPUT_DIAGNOSIS_20261103.md`
- `ai_docs/tasks/1155-full-board-input-diagnostics.md`

Aktualizowane: właściwe fragmenty obu `VISION_LAB.md`, wygenerowana mapa,
CURRENT_STATE i task po uzyskaniu własności dokumentów od koordynatora.

## Test cases

- Niesymetryczne oznakowane piksele i nieosiowy quad: exact parity z runtime,
  zapis/odczyt JSON oraz nowy proces dają identyczne bytes i transformację.
- Fragment poza oryginałem: poprawne stałe wypełnienie114, bez udawania pikseli.
- EXIF/canonical hash lub preset/model SHA różny: jawne odrzucenie rekordu.
- Nieznana wersja, NaN/Inf, singular matrix, inny crop SHA: fail closed.
- Brak raw albo GT pozostaje unavailable po roundtrip; fitted nodes osobno.
- Historyczny kandydat FIT_OUTLIERS: historyczny status nie nadpisuje wyniku T0.
- Osiem etykiet i dowolna liczba nominalnych approve nie daje pełnego zdjęcia.
- Reader wywołany raz na wybrane źródło; limit/SQL error nie daje sukcesu
  częściowego. Bez zapisów i bez zmiany roli eligible.
- Readiness sourceIds nie trafiają do diagnosticUse. Faktyczny przykład trafia
  z byte/pixel SHA; duplikat identycznego wpisu nie mnoży użycia.

## Verification

Przed wykonaniem potwierdzić interpreter i konfigurację z bieżącego taska T0.
Scoped pytest na trzech nowych plikach, scoped ruff/mypy, następnie
`npm run docs:check` i `npm run code-map:check`; każde uruchomienie z timeout
≤120s. Przypadek operatora: odtwarzanie z zapisanych artefaktów, bez inferencji.
Poniższe wyniki preflight nie są testami przyszłej implementacji.

## Risks / open questions

- 462205 nie ma GT: diagnoza ilościowa ma pozostać niedostępna.
- Zapisane porównanie pending nie zawiera TRAIN; żadna z150 plansz w jego
  inputs.json nie ma aktualnego zatwierdzenia. Brak potwierdzonego bezpiecznego
  zestawu GT+predykcja good/bad do diagnostycznego doboru poza kontrolami.
- Raw outputs można uzyskać dopiero nowym replay; byłby to nowy wynik modelu,
  nie odzyskana historyczna obserwacja. W tym projekcie T1 nie jest wymagany.
- Wersja OpenCV jest częścią dowodu; zgodność bitowa między różnymi wersjami
  runtime nie jest obiecana. Niezgodność ma być jawna.
- Zadanie nie udowadnia niezależności sesji i nie kwalifikuje automatu T4.

## Outcome

Commit: v1.7.559 (hash dopisuje kolejny commit).

### Changed

- Ścisły rekord `full-board-input-diagnostic-v1`; produkcyjne transformacje obu
  etapów, PNG uint8 i NPY float32, osobne hashe, jawny CHW sample przed batch.
- CLI `capture`, `replay`, `readiness`, `frozen`; brak ONNX/torch inference.
- `GridCohortEvidenceReader` i `GridCohortSnapshot` pozostają źródłami dowodów.
  Budżet i kursor są jawne; partial nigdy nie jest pełnym readiness.
- Faktyczna diagnostyka 462205 oddzielona od metadata-only dostępu do 134 źródeł.
- Założenia: brak GT 462205 i raw pozostaje unavailable; brak bezpiecznej pary
  GT+predykcja poza kontrolami nie upoważnia do użycia REGRESSION w projektowaniu.

### Verification results

- Nowe testy: 21 PASS w 7.51 s; po dodaniu komendy frozen końcowe 5/5 testów CLI
  PASS w 1.69 s. Łącznie 22 różne przypadki (10 core, 7 API, 5 CLI).
- Scoped ruff format i check: PASS dla 3 modułów i 3 plików testowych.
- `mypy --follow-imports=silent` dla 3 modułów: PASS, także po dodaniu komendy frozen.
- `npm run docs:check` i `npm run code-map:check`:PASS; mapa odświeżona po końcowej zmianie symbolu frozen,
  bez zmiany publicznego API aplikacji.
- Rzeczywiste capture i dwa osobne procesy replay dla 462205: PASS obu etapów,
  RGB/tensor SHA zgodne. Bez nowej inferencji.
- LIVE smoke nowego readera: 1 źródło, 2 etykiety, prawidłowe partial i kursor;
  transakcja read-only, limit 20 s. Bez powtórzenia całych 197 kwalifikacji.
- Frozen CLI: 788 źródeł; role/counts zgodne z wcześniejszym zweryfikowanym
  snapshotem; nie czyta pikseli.
- Wcześniejsze 20 testów: 12 PASS / 8 błędów środowiska tworzenia pytest temp;
  poprawne powtórzenie używa jawnego nowego basetemp w artifacts. Bez zmian testów
  dla obejścia wyników. Mypy z follow-imports=skip dawał Any i został zastąpiony
  właściwym silent, bez osłabienia pyproject.
- Logi i polecenia: `D:/game_predicotr/artifacts/task1155-verification/`.
  Każda skończona komenda miała timeout ≤120 s; testy subprocess mają własny 25 s.

### Corrections after R1

- Pełny `archived_preset` i niezależna walidacja jego kanonicznego SHA, zgodności
  screen/board oraz obsługiwanej wersji przetwarzania. SHA całego bundle pozostaje
  odrębnym przypięciem capture. Pięć negatywnych przypadków przelicza checksum
  envelope; zmiana samego SHA ani zgodnie zmieniona nieobsługiwana wersja nie przechodzą.
- Wyłącznie dwa domenowe błędy wycofanego/usuniętego źródła trafiają do
  `rejectedSources`. Kursor obejmuje także odrzucone źródła. Liczniki selected,
  nominal, qualified i successful są rozdzielone; SQL/timeout/integrity abortują.
  Limitations jawnie ogranicza populację do nominal current human.
- Listener rzeczywiście ustawia malejący timeout i odrzuca przekroczony deadline;
  przekroczenie po capture nie daje raportu. Disposable PostgreSQL potwierdził
  `SHOW transaction_read_only=on`, odrzucenie INSERT (SQLSTATE25006) i rzeczywiste
  anulowanie `pg_sleep` przez statement_timeout (57014), bez zmian danych operatora.
- `diagnosticUse` deduplikuje źródło/purpose i zachowuje unikalne SHA rekordów
  z sequence/position. Stabilny klucz i obowiązek union między raportami w T4 są
  opisane w architekturze. Nie powstał drugi ledger.
- JSON: temp+flush/fsync+publikacja bez nadpisania; Windows rename, POSIX exclusive
  hard link. Capture: wszystkie pliki fsync przed no-replace rename katalogu na
  Windows. Testy wyścigu dwóch zapisów i istniejącego pustego katalogu, awarii flush
  oraz kolejności fsync/rename. Bez obietnicy directory-fsync ani physical power-cut.
- Frozen liczy targets/screenEligible tylko dla used; pełny raport porównuje liczby
  z root manifestem. Test obejmuje unused bez targets, unused z pozornymi targetami,
  zgodność oraz rozbieżność manifestu. Historyczne automatic + bieżący blocker
  sprawdzono w jednym rekordzie.
- Końcowe wyniki: 38 różnych testów jednostkowych PASS (17 core, 11 API, 10 CLI)
  i 2 disposable PG PASS (12.79 s). Po ograniczonym błędzie uprawnień hard-link
  ponowiono tylko 10 CLI; po kontroli manifestu tylko jej 1 test (PASS 0.89 s).
  Pierwsza próba PG nie połączyła się przez ograniczenie sieci; właściwa próba
  zatwierdzona wykonała oba testy. Nie powtórzono 197 LIVE.
- Ruff 7 plików PASS; mypy `--follow-imports=silent` 3 modułów PASS bez zmian
  pyproject. Końcowe docs/map checks zapisane w `task1155-verification/*r2*.log`.
- Nowy capture z pełnym presetem i dwa nowe procesy replay PASS:
  `D:/game_predicotr/artifacts/task1155-input-replay-r2/`. Piksele/tensory identyczne
  jak R1; wcześniejszy capture zachowano jako przedwydaniowy dowód R1, bez nadpisania.
  Frozen ponownie potwierdził 788 źródeł i zgodność counts z manifestem.
- Snapshot R1 ma zweryfikowane fullFileSha256; focused brief używa rzeczywistej
  delty do niego. R1 raport pozostaje niezmieniony, bez trzeciej rundy audytu.

### Not completed

- Brak wdrożenia, merge/push, treningu, migracji operatora i zmian usług.
- Brak ilościowej diagnozy GT 462205 i historycznych raw; ograniczenie danych,
  nie implementacji. T4 dopiero egzekwuje wykluczenie diagnosticUse z kontroli.

### Audit acceptance and retained limitations

- [R1](../../quality/TASK-1155_AUDIT_ROUND1.md): PASS, 0 P0/P1 i 5 P2.
  [Focused R2](../../quality/TASK-1155_AUDIT_claude-opus-5-5.md): PASS, 0 P0/P1;
  P1 kontraktu odbioru koordynatora oraz wszystkie 5 P2 R1 zamknięte.
- **P2-R2-1 zaakceptowane przez koordynatora jako ograniczenie przedwydania:**
  R1 i R2 mają ten sam identyfikator schematu v1 mimo dodania wymaganego
  `archived_preset`. R1 nie był wydany operatorowi/aplikacji; zachowano go wraz
  ze snapshotem i manifestem audytu. Bieżący strict decoder odrzuca brak presetu
  przez ogólny `ValidationError`. To luka rozróżnienia wersji, a nie jawna migracja
  lub osobny kod zgodności. T4 ma przyjmować wyłącznie kompletny rekord zgodny
  ze ścisłym kontraktem i checksumami; nie może domyślać presetu R1. Bez trzeciej
  rundy audytu ani dalszej zmiany zachowania zgodnie z poleceniem koordynatora.
- P3: nominalHumanBoards obejmuje również odrzucone źródła; różnica wobec
  qualified nie oznacza wyłącznie błędnych geometrii. Są osobne rejectedSources
  i selected/sourceCount, lecz nie ma rejectedNominalHumanBoards.
- P3 testów: negatywne przypadki dryfu nie przypinają `match=` konkretnego kodu;
  drugi obsługiwany kod GRID_COHORT_SOURCE_REMOVED nie ma osobnego testu.
  Testy PG zastępują router/selection/capture entry; nie są integracją całego GT readera.
- P3 frozen: porównanie counts obejmuje role obecne w manifeście, bez dodatkowej
  kontroli użytej roli spoza jego katalogu. Capture i testy katalogów wymagają
  Windows; nie dodano skipif dla innych systemów.
- Pozostałe P3 R1: kod używa fullyHumanAnnotatedPhotos, task opisowo
  fullHumanAnnotatedCount; fitted_nodes przy FIT_FAILED mogą być zapasowym
  grid_from_quad (powód pozostaje jawny); readiness używa konta właściciela
  z wymuszoną i sprawdzoną transakcją READ ONLY. Bez refaktorów poza zakresem.

### Definition of Done and plan T1

- Odtworzenie obu etapów z produkcyjnych transformacji, osobne RGB/tensor SHA
  i nowy proces replay: spełnione; bez inferencji ani zmiany runtime.
- Źródło/model/preset/transform/version oraz raw/fitted/GT i historyczna polityka:
  spełnione, przy jawnym braku raw i GT462205 oraz przedwydaniowym P2 powyżej.
- Bounded LIVE/frozen i dostępność materiału: spełnione; role, niezależność
  i kwalifikacja T4 nie są dopowiadane. Brak bezpiecznych TRAIN GT+prediction
  poza kontrolami opisany zamiast użycia testowych przykładów do projektowania.
- Faktyczne diagnosticUse, deduplikacja i powiązanie dowodu: spełnione; T4
  otrzymuje obowiązek wykluczenia źródeł/kopii/grup, historia ról bez zmian.
- Testy/lint/mypy, docs/map, raporty R1/R2 i Outcome: spełnione. Zamknięcie
  skryptem, osobny commit v1.7.559 i record-hash do kolejnego commita T2.

### Documentation updates

- Wymagania i architektura VISION_LAB, raport
  `quality/FULL_BOARD_INPUT_DIAGNOSIS_20261103.md`, mapa kodu i wskaźnik stanu.
- Zachowano 3 zastane zmiany record-hash TASK-1154, do dołączenia do commita 1155
  zgodnie z poleceniem koordynatora; nie przepisano jego historii.

### Recommended next task

TASK-1156/T2 według zaakceptowanego planu; shared docs wracają do koordynatora.


## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1155 / T1 — Odtworzenie wejścia sieci i dane | gpt-6-astra | high | Dokładna geometria i ochrona pochodzenia dowodów | Claude Code claude-opus-5-5/high, uruchamia root |
