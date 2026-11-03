# TASK-1156 — Weryfikacja możliwości modelu i kwalifikacji gry

Stan: R1 i focused R2 Opus5.5/high PASS, brak P0/P1; zamknięcie v1.7.560. Bez aktywacji,
treningu, migracji operatora i restartu usług. Wszystkie raporty modelu w testach
są syntetycznymi rekordami serwera; nie stanowią kwalifikacji rzeczywistej gry.

Zmiana: adapter catalogue-v1 zachowuje immutable SHA, jawnie odczytując logiczne
3 wiersze × 5 kolumn i stronę3×3. Preflight-v14 i acceptance-v3 wymagają pinu
operacji, odrębnego od snapshot/proposal v1/v2. V3 nadal używa crop-v2. Exact
per-game report/currentness pochodzi z istniejącego publication readera; brak
dowodu daje propozycje bez automatu. API recheckuje dowody przed zapisem.

Retry nowych operacji odzyskuje zapisany pin po porównaniu pełnego stabilnego
inputu, zanim odczyta kwalifikację. Wyłączone są wyłącznie pochodny pipeline
fingerprint, własny pin/polityka i pochodny hint manifestu bazowego. Tożsamości
źródła/gry/modelu/preflightu/previousJob i parametry operatora pozostają w porównaniu.

Wyniki wykonanych kontroli:

- 65 scoped API/domain/HTTP/reprocess i stable-input cases PASS (9,05 s),
  w tym sześć konfliktów zmienionych parametrów. Cold retry
  managed import ma resolver, którego ponowne wywołanie celowo rzuca błąd.
- 121 regresji snapshot/proposal, v1/v2 acceptance, command/replay, preflight,
  worker reinference i bounded runtime PASS (27,27 s).
- PostgreSQL: 2 przypadki unqualified/forged-worker PASS (24,10 s). Rzeczywista
  bramka API zachowuje źródło i odrzuca automat mimo sfałszowanej deklaracji workera.
- PostgreSQL: 1 dodatni przypadek exact game/report/candidate/publication PASS
  (19,66 s). Faktyczny API pre-write guard dopuszcza automatic/geometry_complete.
- 12 testów wrappera request oraz parsera Admin v13/v14 PASS. Wygenerowany klient
  TypeScript typecheck PASS. Izolowany Admin worktree typecheck PASS z pełnym
  strict config i paths do lokalnego wygenerowanego klienta.
- Ruff i format zmienionych plików PASS. Scoped mypy ma wyłącznie zastany błąd
  Row/tuple w `virtual_grid_geometry_repository.py`; identyczny błąd potwierdzony
  na shadow pliku z HEAD559. Nowe moduły i wywołania bez nowych błędów.
- OpenAPI freshness, generowanie mapy, code-map check i wszystkie kontrole
  docs (decyzje, stan, budżet odczytu, mirrory skills) PASS.

Ograniczenia środowiska: pierwsze uruchomienia zatrzymały TEMP poza workspace i
twarde dowiązania fixture'ów; właściwe uruchomienia używają własnego basetemp i
dozwolonego lokalnego trybu. Standardowy Admin typecheck czyta stary klient z
junction node_modules do main i zgłasza brak v14. Izolowana kontrola zmienia tylko
paths, bez osłabienia strictness; root/main/node_modules nie zmieniano. Jest to
wynik izolowanego worktree, nie standardowy Admin PASS.

Każda komenda ma limit120s. PostgreSQL wykorzystuje istniejący disposable harness,
bez bazy operatora. Odczyt katalogu potwierdził zero pozostałych baz i ról dla obu
nowych przebiegów; receipt w `artifacts/task1156-preflight/postgres-cleanup.json`.
Pełne logi scoped mypy/format/docs i tymczasowy tsconfig są w tym samym katalogu.

PostgreSQL regresja historycznych v1/v2 i cold replay: 6 PASS (44,29 s).

Koordynator przed ukończonym audytem potwierdził P1 wcześniejszego zapisu:
`project_source_geometry` miał osobną transakcję, która ufała workerowemu
`ready` + rollout i mogła nadać `accepted` przed finalizerem. Poprawka opiera
się na zaufanej polityce joba: nowe v3 zawsze zapisuje początkowe `needs_review`,
także przy sfałszowanym `manual_v1`. Finalizer nadal może promować qualified
wynik bez zmiany sealed SHA/payloadu.

Celowane PG po poprawce: dodatni qualified-ready full flow i sześć v1/v2
history/cold replay PASS w przebiegu siedmiu udanych przypadków (65,06 s).
Dwa nowe negatywne forged-ready neural/manual PASS w końcowym przebiegu (21,99 s).
Po pierwszej transakcji test odczytuje wyłącznie trwały stan nową sesją i wymaga
zera zaakceptowanych nowych kandydatów. Starsza ręczna accepted rewizja fixture
pozostaje nietknięta. Pierwszy przebieg ujawnił zbyt szeroką asercję całej historii;
zawężono ją do SHA kandydata, bez osłabiania warunku dotyczącego nowego zapisu.

Scoped mypy nowo dotkniętego `pipeline_store.py` ma pięć wcześniejszych UUID|None
błędów; dokładnie te same komunikaty potwierdza shadow HEAD559. Ruff/format tej
zmiany PASS. Nie powtarzano całych121 testów ani modeli/treningów. Pierwszy Opus R1
zakończył się timeout480s bez werdyktu; nie jest PASS ani rundą poprawek po findingu
audytora. Finding koordynatora i pełny kontekst są w ignored artefaktach audytu.

Snapshot/SHA sprawdził koordynator przed niezależnym audytem Opus5.5/high.
Oryginalne pakiety i logi zachowano; audyt nie uruchamiał testów i ocenił kod statycznie.

## Jedna runda poprawek po R1

Audyt R1: PASS, pięć uwag P2. Koordynator podniósł P2-1 (retry) i P2-5
(modelowy human stamp) do blokujących luk kontraktu P1; obie poprawiono przed R2.
Oryginalny R1, pakiet 279661 B oraz pełny source/context snapshot 49 plików zachowano
w `artifacts/audits/TASK1156-R1-source-snapshot` i pierwotnych manifestach.

- P2-1: exact JSONB lookup w repo, pod istniejącym admission advisory lock przed
  resolverem i do commit. Brak list_jobs i okna 10 000. Dwa trafienia służą wyłącznie
  wykryciu niejednoznaczności i kończą się stabilnym błędem; nie wybiera się pinu.
- P2-5: wspólny helper zaufanej strict policy chroni zarówno wczesny source status,
  jak i automatyczny human stamp. Worker availability metadata nie tworzy approval
  ani GT; prawdziwe ręczne API i wcześniejsze v1/v2 zachowują swoje reguły.
- P2-2: realny qualified reader sprawdza oddzielnie mismatch report ID, report SHA
  i publication evidence SHA. Drugie publish jest prawidłowo blokowane jako
  REVISION_CONFLICT. Zamianę read-modelu zasymulowano jawnie jako korupcję i stary
  pin daje STALE; nie dodano wspieranego ponownego publish.
- P2-3: produkcyjny workflow tworzy suite przez metodę wykonującą rzeczywisty
  recheck. Testy PG dowodzą przekazania `()` albo REQUIRED do faktycznego suite
  i kończą się odpowiednio accepted albo needs_review.
- P2-4: D-585 i VISION_LAB wyjaśniają idempotentny import i przyszłą wskazówkę T5:
  powtórzenie identycznego inputu zachowuje pin; nowe dowody dla istniejących danych
  wykorzystuje nowe jawne prepare grid reinference. Bez request nonce i nowego UI.

Kontrole po tej rundzie:

- 65 unit/domain/cold-replay/mismatch przypadków PASS (8,49 s).
- 88 scoped API neural i production workflow przypadków PASS (8,91 s).
- 1 PG concurrency/publication/ambiguous-identity PASS (18,47 s): dwa prepares,
  rzeczywista publikacja nowego UUID raportu pomiędzy nimi, resolver tylko raz,
  ten sam job i frozen-unqualified, mimo że świeży dowód już kwalifikuje grę.
- 2 PG workflow realrecheck→suite PASS w partii 32,06 s. Dwa pozostałe przypadki
  tej partii zatrzymały się na istniejącym crop/symbol metadata fence. Poprawiono
  tylko forgery fixture do zgodnych metadanych; fence nie osłabiono.
- 2 końcowe PG human-stamp/GT i regresji v2 PASS (25,17 s): v3 pozostaje bez
  approved revision/actor/time i ma poziom U oraz geometry_incomplete; v2 zachowuje
  dotychczasowy import-qualified-manual stamp. Nie zaliczono wcześniejszego błędu
  fence jako dowodu tej regresji.
- Scoped mypy sześciu zmienionych modułów: pięć identycznych wcześniejszych
  UUID|None błędów pipeline_store, nowych: 0. R1 Row/tuple w niezmienionym writerze
  pozostaje znanym baseline. Standardowego Admin tsc nie nazywa się PASS.

Brak pełnego ponowienia wcześniejszych 121 testów, nowych modeli, operator DB
writes, migracji operatora, restartów i własnego Opusa. Focused R2 uruchomił
koordynator; wynik PASS zamknął wszystkie uwagi R1 i obie luki P1 koordynatora.

## Wynik focused R2 i pozostawione ograniczenia

Pełny raport: `TASK-1156_AUDIT_claude-opus-5-5.md`. Brak P0/P1; cztery nowe P2
pozostawiono jawnie bez trzeciej rundy zmian zachowania:

1. Exact lookup uznaje za niejednoznaczne także dwa identyczne piny dla tej samej
   tożsamości, np. po zastąpieniu FAILED/CANCELLED preflightu nową bazą. Kolejne retry
   może trwale zwracać `NEURAL_GRID_OPERATION_IDENTITY_AMBIGUOUS`. To ograniczenie
   żywotności, fail-closed; nie podnosi kwalifikacji i nie umożliwia automatic write.
2. Strict v3 nie nadaje human stamp również z availability metadata wywodzących się
   z ludzkiej decyzji w zaufanym geometry_guard_resolution_manifest. Może być konieczna
   ponowna prawdziwa manual approval; do tego czasu geometry_incomplete. Workflow
   istniejącego ręcznego API pozostaje dostępny. T5 powinno ujawnić to ograniczenie.
3. PG exact lookup sprawdzono dla VALIDATE; brak PG cold retry IMPORT/reprocess.
   Import ma testy unitowe i mock SQL, które nie dowodzą wykonania tej gałęzi JSONB.
4. PG concurrency nie sprawdza przez pg_locks, czy drugi backend faktycznie czekał
   na advisory lock. Skrajny przeplot wątków może ograniczyć siłę regresji; nie jest
   to dowód braku blokady w implementacji.

Standardowy Admin tsc nie jest PASS. Izolowany worktree strict typecheck PASS;
scoped mypy: 0 nowych błędów, pięć identycznych bazowych UUID|None oraz wcześniej
opisany Row/tuple. R2 PG cleanup potwierdzony: DB0/roles0 w
`artifacts/task1156-preflight/postgres-cleanup-r2.json`.

Definition of Done i T2: capabilities/topologia przed inferencją i akceptacją,
nowa gra zachowująca propozycje bez automatu, frozen retry i API exact recheck,
historia v1/v2, pełny pion typed kontraktu oraz dokumentacja/decyzja/mapy zostały
dostarczone. Testy i audyt opisano wyżej z rzeczywistymi ograniczeniami narzędzi.
Zmian schematu nie było. Nie deklaruje się poprawy jakości rzeczywistego modelu.
Punkt A: 197 aktualnych GT / 134 zdjęcia, pełnych9/9=0. T3–T6 czekają na decyzję
kosztową; bez treningu, aktywacji, migracji operatora i usług.
