# TASK-1147 — Weryfikacja integracji kodu

Worktree `D:/game_predicotr/worktrees/grid-correction-growth`; HEAD `7881711b`,
dołączany stabilny ref `60f50c64`. Merge bez commita. Dziewięć konfliktów
rozwiązanych w dokumentacji oraz readiness; indeks nie zawiera konfliktów.

## Ochrona połączonych funkcji

0178 ma rodzica `0177_source_replacement_purge`. Nie zmieniono historycznych
migracji 0172–0177. Samo przepięcie rodzica usuwałoby SQL strażników 0175,
ponieważ 0178 ponownie tworzy photo capability i wrapper. Zatwierdzona poprawka
integracyjna stosuje mały `source_recording_replacement_sql.py`: dokładny guard
0175, ten sam lock i filtr aktualnej populacji, zarówno przy instalacji v6,
jak i odtworzeniu legacy v4/v5 na downgrade do 0177. AST upgrade/downgrade
pozostał identyczny z `7881711b`; zmieniły się importowane, złożone definicje SQL.
Nie zmieniono algorytmu splitu, reguł zwolnienia rezerw ani kontraktu API.

## Wyniki

| Kontrola | Wynik |
|---|---|
| PG guarded migration i replacement fence | 1 PASS, 21,03 s; 0178 → 0177 → 0178; runtime wrapper i private photo odrzucają retired/reserved; current i retencja zachowane |
| PG core correction registry | 1 PASS, 54,91 s; v1/v2, ochrony, rollback, release, nowy interpreter |
| PG replacement guards | 1 PASS, 35,57 s; bootstrap, atomowość, restart, replay i retencja |
| API learning, worker dataset/admission | 104 PASS |
| Evaluator v1/v2, częściowe kontrole i restart | 5 PASS |
| Readiness, domena, adapter, replacement guards i retencja jednostkowa | 74 PASS; dwie zastane porażki retencji opisane poniżej |
| UI interakcje korekt i powiązanych paneli | 74 PASS |
| Requesty klienta: korekty/apply/readability/replacement | 9 PASS |
| Scoped ruff/format | 11 plików PASS |
| Scoped mypy | 8 modułów PASS |
| Admin i klient TypeScript; scoped ESLint | PASS |
| Admin production build | PASS; TypeScript 17,0 s, trzy strony statyczne |
| OpenAPI i SDK | Wygenerowane z połączonego backendu |
| Docs:check | PASS, 44765/45000 B; 30 decyzji, 10 zakończonych tasków |
| Mapa kodu | Zregenerowana |

Logi: `artifacts/task1147-*.log`. Polecenia mają timeout120s i jawny PYTHONPATH
worktree. Build i testy korzystają z lokalnych aliasów dla obu klientów oraz
manual-image-selection-core i podścieżki admin-api-client/types. Pierwsze próby
typecheck/build ujawniły wskazanie współdzielonych node_modules na starszy root;
aliasy rozwiązują to wyłącznie w tymczasowym configu. Oryginalne bajty tsconfig
przywrócono w finally. Nie zmieniono konfiguracji działających usług.

## Końcowa kontrola po audycie — P2-1 i P2-3

Audyt Opus zakończył się PASS bez P0/P1. W jednej rundzie uwag dodano
`services/api/tests/test_source_recording_replacement_sql.py`, bez zmian kodu
produkcyjnego. Test porównuje literal strażnika z migracją 0175 oraz przechwytuje
SQL emitowany przez jej rzeczywiste `upgrade()` bez połączenia z bazą. Wrapper
i odcinek photo przywracane na downgrade muszą być identyczne z tym SQL.
Pozostałe przypadki pilnują pojedynczego strażnika, blokady sequence-ownership
i filtra aktualnej populacji w v6. Ochrona wrappera sprawdza currentness członków;
osobny filtr populacji występuje wyłącznie w funkcji photo.

Po ostatniej edycji testu wykonano wyłącznie kontrole bez autofix, zakończone
2026-11-03 o 11:30 CET. Żadnych późniejszych zmian kodu ani formatowania:

| Kontrola końcowych plików | Wynik i log |
|---|---|
| Nowy test SQL oraz readiness | 29 PASS, 4,78 s; `artifacts/task1147-final-unit.log` |
| PG migracja 0178 → 0177 → 0178 i strażniki | 1 PASS, 23,03 s; `artifacts/task1147-final-migration.log` |
| PG replacement guards | 1 PASS, 19,88 s; `artifacts/task1147-final-replacement-guards.log` |
| PG correction registry z nowym procesem | 1 PASS, 50,33 s; `artifacts/task1147-final-registry.log` |
| Ruff format --check oraz check bez fix | 12 plików PASS; `artifacts/task1147-final-lint.log` |
| Scoped mypy | 8 modułów PASS; `artifacts/task1147-final-types.log` |

Testy PG wykonano sekwencyjnie na jednorazowych bazach, każde polecenie z limitem
120 s i jawnym PYTHONPATH worktree. Mapa została ponownie wygenerowana bez zmiany
jej rozmiarów. Nie powtarzano 104 testów API/worker, testów UI ani buildu.
Opcjonalnego dodatkowego wariantu v2 dla fixture replacement fence nie dodano;
istniejący test registry nadal sprawdza polityki v1/v2 i trwałość po restarcie.
P2-1 oraz P2-3 są zamknięte tymi dowodami. Uwagi dotyczące odbioru bez aliasów,
znanych błędów retencji i rewizji bazy przed wdrożeniem pozostają rozliczane
przez prowadzącego w tasku i planie.

## Zastane porażki

`test_grid_cohort_asset_retention.py` ma dwie porażki także na stabilnym `60f50c64`:

- `test_actual_publisher_hard_crash_residue_enters_guarded_gc_after_retention`:
  mock nie ma nowego `source_replacement_gc_guard`; produkt chroni plik fail-closed.
- `test_completed_game_deletion_requires_catalog_route_and_partition_absence`:
  sztuczna sekwencja wyników nie daje oczekiwanego dowodu usunięcia; stan pozostaje unresolved.

Pierwsza próba zakończyła się 68 PASS/1 FAIL; druga z jawnie pominiętą pierwszą
porażką dała 74 PASS/1 FAIL/1 deselected. Obie odtworzono w świeżym procesie,
ładując `storage_gc` z `git show 60f50c64` i potwierdzając identyczność modułu
retencji, publishera oraz testów z tym refem. Dowód:
`artifacts/task1147-retention-baseline.log` (2 FAIL, jawnie baseline).
Nie zmieniono niezwiązanych testów ani mechanizmu GC. Nie powtarzano znanych
legacy reset_game/stats dla uzyskania zielonego wyniku.

## Zachowanie historii

`artifacts/task1147-preservation.json` potwierdza zachowanie pełnych sekcji
archiwum stanu i decyzji obu rodziców; żadna sekcja nie różni się tekstowo.
Indeksy zawierają obie nowe decyzje D-582/D-583, a nadmiar wierszy pozostaje
w archiwum indeksu. Historyczne audyty TASK-1139/1140/1145 nie były zmieniane.

## Odbiór operacyjny — koordynacja po usunięciu blokady

Koordynator zgłosił `GAME_STORAGE_LIFECYCLE_IN_PROGRESS` przy próbie 0172:
stary running delete gry z 2026-10-20. Przywrócił działającą aplikację na 0171.
Operator następnie osobno zatwierdził dokończenie usuwania pustej 777v2,
konfiguracji i przypisania oraz dalszą migrację i wdrożenie. Koordynator
realizuje ten zakres przed przekazaniem okna dla 0178.
Drugie okno zachowuje kontrolę root/main, usług i bazy; ten wykonawca nie
zmieniał ich. Nie wykonano commita, push, migracji operatora, restartu ani uczenia.
Gotowość kodu do focused audytu nie oznacza zakończenia TASK-1147 ani wdrożenia.

## Synchronizacja po wdrożeniu koordynatora do 0177

Powyższa blokada opisuje wcześniejszy etap. Koordynator następnie, za odrębną
zgodą operatora, dokończył lifecycle pustej gry i wdrożył 0177. Źródłem odbioru
jest `quality/777A2_DEPLOYMENT_BLOCKER_20261103.md`; ten wykonawca nie wykonywał
tych operacji. Migracja i odbiór 0178 nadal pozostają przed nami.

Kod pierwszej integracji zapisano w checkpoincie v1.7.543 / `08a9ffcf`.
Po przekazaniu stabilnego refu koordynatora przygotowano w tym samym worktree
merge bez commita `be10f90e8d6d8121f70577be7243946ab5ee8979`. Wystąpiły tylko
dwa konflikty dokumentacji: CURRENT_STATE i jego archiwum Q4. Zachowano obie
historie i 10 wpisów zakończonych tasków. Pełne sekcje archiwów stanu i decyzji
obu rodziców pozostają identyczne; dowód `artifacts/task1147-sync-preservation.json`.
Poprawka React z TASK-1148, wszystkie trzy manifesty/lock oraz cały Selector
1.0.5 są zgodne z przychodzącym refem (porównanie normalizuje końce linii).

Preflight prowadzącego wykazał wyłącznie historyczne kolizje numerów wersji
v1.7.537–543, bez kolizji własnych TASK, decyzji lub migracji. Historii commitów
ani wersji nie przepisano. Źródło: `artifacts/task1147-preflight-before-handover.json`.

Mapa zregenerowana. Docs:check PASS: 2 aktywne taski, 10 zakończonych wpisów,
startup 44970/45000 B. Po pierwszym przekroczeniu budżetu skrócono wyłącznie
aktualne wskaźniki wdrożenia, pozostawiając pełny raport i archiwa. Logi:
`artifacts/task1147-sync-map.log`, `artifacts/task1147-sync-docs.log`.
Code-map:check i diff --check (również indeksu) PASS; oba konflikty oznaczono
jako rozwiązane. Log kontroli: `artifacts/task1147-sync-check.log`.
Brak nowej logiki produktu; nie ponawiano PG, UI ani buildów. Koordynator nadal
zachowuje kontrolę root/main/usług/bazy. Synchronizacja nie zamyka TASK-1147.

Audyt: `TASK-1147_AUDIT_claude-opus-5-5.md`, R1 PASS bez P0/P1.
P2-1/P2-3 zamknięte kontrolami powyżej; P2-2 zamknięte późniejszym standardowym
typecheckiem i buildem w głównym checkout, opisanymi poniżej. P2-4 (dwie zastane porażki retencji)
zaakceptowane jako odłożone przez prowadzącego i zapisane w CURRENT_STATE.
P2-5: ponowny odczyt tożsamości/rewizji bazy przed migracją zapisany w planie.
Nie jest to raport pełnego quality PASS ani zakończonego wdrożenia.

## Checkpoint odbioru operatora na 0178

Prowadzący wdrożył root/main `5cfe292b` i przeprowadził rzeczywistą migrację
0177 → 0178 oraz kontrolę ról aplikacyjnych: PASS. Snapshoty przed i po
potwierdzają niezmienione 166971 źródeł, 1500019 plansz, 22248975 komórek
oraz hashe aktywacji; `purged_sources=0`. P2-5 zamknięte: odczytano tożsamość
bazy i rewizję 0177 przed migracją, bez pominięcia niespodziewanego 0178.

P2-2 zamknięte: standardowy root Admin typecheck i production build bez
aliasów PASS. Dowody `D:/game_predicotr/artifacts/grid-growth-deploy-20261103/`
zawierają `root-typecheck.log`, `root-build.log`, `database-before.json`,
`database-after.json` oraz `migrate-0.log`–`migrate-2.log`.

API/Admin i lane general 7 / grid-training 1 działają. Rzeczywisty panel
potwierdził loading i zmianę czasu po odświeżeniu, verified przy aktualności
oraz odblokowanie Apply po potwierdzeniu, bez kliknięcia Apply. Liczniki
przed nowym startem: 196 zatwierdzonych plansz, TRAIN 146 (77 zapisanych,
69 nowych), VALIDATION 17, REGRESSION 21, wyłączenia 12. Z UI utworzono
jeden przebieg `cc7e739e-027c-4f44-87d8-8088c0d86bb1`; odpowiedź i późniejszy
odczyt historii potwierdzają ten sam trwały identyfikator. Odczyt z 11:17:19 UTC
ma `processing`, kohortę `8c4d3ab4-4d01-59fe-a826-46883b72ddfe`
i `trainingRunId=null`. Nie zgłoszono sukcesu treningu ani zastosowania modelu.

Pełny checkpoint wraz z liczbą zdjęć, PID, instrukcją przy przejściowym
`KillAccessDenied` i granicami dowodów:
`quality/GRID_CORRECTION_GROWTH_DEPLOYMENT_20261103.md`.
Prowadzący dopisze wynik uczenia; TASK-1147 nadal pozostaje `in_progress`.

## Checkpoint rzeczywistego odbioru — blokady1149/1150

Pierwszy freeze parenta `cc7e739e-027c-4f44-87d8-8088c0d86bb1` przekroczył60s. Normalny replay tego samego polecenia `freeze:163` i oryginalnego klucza zamroził kohortę `8c4d3ab4-4d01-59fe-a826-46883b72ddfe` do rewizji164 w53,515s; blokady wejść33,641s. To dowód poprawnego zapisu, ale nie trwała naprawa kosztu; TASK-1149 ogranicza per-row SQL do partii200 bez zmiany blokad/limitów.

Oficjalne resume tego samego parenta zachowało historię i utworzyło tylko run `7a1b3835-639c-4439-8f49-3dfaea5e650a`. Dziecko zakończyło się na kroku488: `PermissionError [WinError5]` w atomowym `os.replace` pliku postępu. Budget pozostał488/8000 kroków i161,969/7200 sekund, attempt1; brak kandydata i zmiany defaultu. TASK-1150 dodaje krótki ograniczony retry tej samej podmiany. Nie wznowiono ponownie przed poprawką.

Bramka odbioru pozostaje otwarta: sam PASS statycznego audytu1147 i poprawne liczniki nie stanowią sukcesu uczenia. Źródła: root `artifacts/grid-growth-deploy-20261103/freeze-profile-result.json`, `failed-training-job.json`, `latest-training.json` oraz diagnostyka runa. Zakres naszego178 nie został jeszcze wypchnięty.


## Odbiór końcowy — 0179 i rzeczywiste uczenie PASS

Po skoordynowanym wdrożeniu root/main i origin/main `d01a0f07cc72d44f54711cd1a1a60a27df4823df` baza ma jedyny head `0179_empty_replacement_search`. Kontrola ról compliant, API/Admin działają, worker general7 i grid-training1 uruchomione z nowego procesu. Dane przed/po179 identyczne:166971źródeł,1500019plansz,22248975pól, purged0, te same hashe aktywacji. TASK-1151 zamknięto osobno po rzeczywistym wyszukiwaniu; naprawa nie zmienia danych ani zakresu modeli.

Oficjalne resume12:53:41UTC wznowiło ten sam parent `cc7e739e-027c-4f44-87d8-8088c0d86bb1` i dziecko `7a1b3835-639c-4439-8f49-3dfaea5e650a`. Nie powstał drugi run ani nowy budżet. Attempt2 poprawnie zapisał checkpointy i eksport; wykonał2400kroków, zakończył przez early_stopping i wybrał checkpoint1200 na VALIDATION. Progress3600/3600 oznacza zamknięcie planu, nie wykonanie3600kroków. Łączne zużycie2888/8000kroków zawiera wcześniejsze488; czas865,313/7200s, bez resetu/odnowienia. `result-1.json` zachowuje wcześniejszy błąd, `result-2.json` potwierdza exported/early_stopping.

Automatyczna ocena `eeb70311-2ab7-4e2e-9961-4ff9aac6821a` zakończyła się13:07:04UTC wynikiem PASS, raport `0cd1539a-412f-561c-a022-838577c09f62`, kandydat `3ed60010-7c3e-5c3b-91aa-4e03eb9bfa5e`. Porównano te same oryginalne zdjęcia:

| Rola | Zdjęcia / opisane plansze | Poprawne baza / kandydat | Średni znormalizowany błąd baza / kandydat | Spadek błędu |
|---|---:|---:|---:|---:|
| VALIDATION |13/17|12/14|0,01734436/0,01316342|24,11%|
| REGRESSION |13/21|15/17|0,01442749/0,01180831|18,15%|

Wykryte odpowiednio17/17 i21/21 dla obu modeli. Gate v2 PASS i ONNX parity PASS. Wszystkie zdjęcia kontrolne są częściowo opisane: ocena dotyczy opisanych plansz, bez miary fałszywych detekcji poza nimi. Dowód photo-only nie potwierdza niezależności sesji ani nieznanego wykorzystania danych przez przodków; zweryfikowany zakres obejmuje wyłącznie MumieA2. Nie deklarujemy jakości innych gier ani istotności statystycznej.

Po freeze liczniki:196zatwierdzonych/133zdjęcia, TRAIN146/98; zapisane TRAIN146/98 i nowe0/0, VALIDATION17/13, REGRESSION21/13. Nowe69plansz z poprzedniego podglądu weszły do zamrożonego TRAIN; dlatego licznik nowych spadł do0. Bufor12opisanychplansz/53źródła, wyłączone12/9 bez zmian. Zachowano niezależną od TRAIN pulę testową i ochrony.

Rzeczywisty Admin po restarcie pokazał PASS i powyższe liczniki. Przycisk sprawdzenia aktualności przeszedł w loading, zakończył się potwierdzeniem i nowym preview. Zaznaczenie potwierdzenia odblokowało Apply; checkbox następnie odznaczono, Apply nie kliknięto. Default oraz przypisanie MumieA2 pozostały Mumie v1, revision1. Kandydat oczekuje na osobne zastosowanie operatora. Starsze importy i ręczna geometria nie zostały przeliczone.

Dowody w root `artifacts/grid-growth-deploy-20261103`: `before-resume-afterfix.json`, `learning-resume-afterfix-intent.json`, `learning-resume-afterfix-response.json`, `afterfix-history.jsonl`, `latest-afterfix.json`, `final-evaluation.json`, `latest-ready.json`, `database-before179.json`, `database-after179.json`, `final-panel-pass.png`. Rzeczywisty obraz panelu pokazuje tabelę15→17poprawnych w kontroli końcowej. Historyczne checkpointy raportu powyżej pozostają zapisem kolejnych etapów, nie aktualnym blockerem.

DoD: kod i kontrakt, migracje/restart, liczniki, aktualność i rzeczywisty trening/ocena potwierdzone. Audyty1139/1140/1145/1147/1149/1150 i1151 rzeczywiste, bez otwartych P0/P1; P2 oraz zastane niepowiązane FAIL opisane w raportach. Nie zgłaszamy pełnego globalnego quality/mypy PASS. Końcowy commit dokumentuje odbiór, a późniejszy metadata commit zapisze jego hash oraz finalny push.
