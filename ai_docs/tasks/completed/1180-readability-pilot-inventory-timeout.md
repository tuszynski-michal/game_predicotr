---
title: Wydajny wybór próbki pilota jakości777A2
status: done
last_updated: 2026-11-10
---

# TASK-1180 — Wydajny wybór próbki pilota jakości777A2

## Status

`done`

## Goal

Pilot nie kończy przygotowania błędem timeout i zachowuje dokładnie dotychczasową kolejność oraz niezależność próbek.

## Context

Operator uruchomił4piloty, wszystkie failed/przetworzono0. Trzy czasy wykonania~32s, błąd JOB_EXECUTION_FAILED/OperationalError. Odtworzenie pierwszego query w READONLY na roli aplikacyjnej z timeout5s potwierdziło SQLSTATE57014. Plan czyta~7194350cells i479045boards, sortuje pełneJSONsnapshoty oraz wywołuje guardcurrent dla każdego pola. Dowody: rootartifacts/readability-pilot-20261110/diagnosis.json. Nie uruchamiać kolejnych pilotów w ramach diagnozy.

## Dependencies / entry conditions

Starta9af0032/main; task1180 nie występuje w bieżących gałęziach. OsobnyWT codex/readability-pilot-timeout. Cudze worktree i usługi pozostają. Zgłoszenie błędu upoważnia do naprawy i testów; wdrożenie/restart oraz wznowienie rzeczywistego joba mają osobną bramkę bieżącego zadania.

## Recommended execution

gpt-6-astra/high, wydajność SQL bez zmiany doboru rodzin. claude-opus-5-5/high przez aktualny terminalowy claude-audit/CROSS_AUDIT przed commitem. Bez delegowania implementacji, nowych benchmarków ani zwiększenia timeoutu.

## Relevant docs

- AGENTS.md; ai_docs/process/DEFINITION_OF_DONE.md; ai_docs/process/CROSS_AUDIT.md.
- ai_docs/requirements/ADMIN_APP.md, plan wymiany zdjęć.
- ai_docs/architecture/API_CONTRACT.md, niezależna jakośćsymboli777a2.
- ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md, A1/A2.
- ai_docs/architecture/CODE_MAP.md; CODE_MAP_SYMBOLS.md (wyszukiwanie).
- .codex/skills/claude-audit/SKILL.md; .agents/skills/task-close/SKILL.md.

## Scope

Wspólny fragment FROM/WHERE snapshotów pozostaje zgodny z dotychczasowym kontraktem. Pilot przegląda źródła w kolejności ich hashy, partiami po 128 źródeł (bez rozdzielania remisów), i wybiera kolejne rangi z identycznych warstw source/import/class. Pełne snapshoty pobiera indeksowo, maksymalnie po 250 pól, w tej samej transakcji. Losowy audyt przegląda prefiksy hashy 00–ff w kolejności; tania lista ID jest nadzbiorem, filtrowanym przy hydratacji do dokładnej poprzedniej podsekwencji. Heartbeat co 10 s między partiami i polami odnawia dzierżawę podczas przygotowania. Pusta historia retired/slots/restoredentries sprawdzana raz pod istniejącym EXCLUSIVE sequenceownershipfence pozwala ominąć per-rowcurrent; przy niepustej stosuje identyczny guard. Pilot i losowy audyt zachowują seedy, kwoty, TEST-first, family/base/recording exclusions i pełne cropidentity. Hydration odmawia przy brakującym/stale celu. Brak nowego API, schematu i mutacji danych operatora.

## Expected files

api/storage/symbol_readability.py (fragmentSQL), nowyworker/symbols/readability_inventory.py, readability_workflow.py; unit i ownedPGtesty; task/CURRENT/map/raport.

## Acceptance criteria

- [x] Dokładna zgodność kolejności i snapshotów starego/nowego query dla pilota i audytu, kilka seedów, flagi current zachowane.
- [x] Brak hydratacji całego korpusu, paczki<=250, close po wcześniejszym zakończeniu i brakującecelestale odmawiają.
- [x] Istniejące testy rodzin/izolacji i PGreadability przechodzą; lint/types/docs/map i wymaganyaudyt rozliczone.
- [x] Ograniczony readonly odczyt na istniejących danych potwierdza pierwszą partię bez timeout; nie deklarować ukończonego pilota bez rzeczywistego wykonania przez operatora.

## Verification

RootPython, PYTHONPATH na tenWT. Każdy subprocess timeout120s, readonly query<=30s. OwnedPG z istniejącym test_symbol_readability_postgres.database, bez syntetycznego dużegokorpusu. Audyt1800s/host1860s i idle60s według CROSS_AUDIT. Wykonać jeden pomiar istniejącego query po poprawce, bez nowego joba.

## Risks / open questions

Fences nie mogą być pomijane bez istniejącego gameownershiplocka. Jedna transakcja obejmuje sprawdzenie pustki i wszystkie generatory. Zmiana danych celu między metadata/hydration kończy się typowanym stale, nie cichą utratą pól. Nie zmieniać algorytmu próbkowania dla pozornego przyspieszenia. Nie odnawiać ani nie usuwać failed pilotów poza normalnym retryjob.

## Outcome

Commit: v1.7.601 / `97bb80bf210d31de3dd0a1463596f19b219d1c1e`.

Implementacja gotowa do niezależnego audytu; nie została scalona ani wdrożona.

- Przyczyna potwierdzona na roli aplikacyjnej: stare zapytanie kończy się SQLSTATE 57014 przed pierwszym polem. Cztery istniejące piloty nie przetworzyły żadnego pola.
- Zmieniono wybór metadanych i późniejsze pobieranie snapshotów. Seedy, kwoty, kolejność, TEST-first, wykluczenia rodzin/nagrań i tożsamości wycinków pozostają zgodne. Nie zmieniono limitu 30 s, API ani schematu.
- Ograniczone odczyty READONLY na istniejącej grze: pierwsze 250 pól pilota 1,843 s; osobna próbka kontrolna 18,204 s, oba poniżej limitu 25 s użytego w diagnozie. Pliki dowodowe: D:/game_predicotr/artifacts/readability-pilot-20261110/{diagnosis,first-page,audit-first-page}.json. Wstępna próba samego globalnego sortowania ID nadal przekraczała 25 s; zastąpiono ją podziałem źródeł i uporządkowanych prefiksów. Nie wykonano pełnego pilota ani benchmarku korpusu.
- Testy: 39 PASS (dotychczasowa selekcja i detektor); 8 PASS (3 jednostkowe hydratacji, nowy test PostgreSQL oraz 4 istniejące testy PostgreSQL readability). Mały korpus należący do testu porównuje pełne snapshoty i kolejność starego/nowego zapytania: 3 seedy, pilot/audyt, obie ścieżki guardu current. Test używa 60 pól i partii po 2 źródła. Pierwszy przebieg ujawnił brak odbudowy projekcji w nowym fixture; poprawiono przygotowanie danych, bez zmiany asercji.
- Dwa dodatkowe testy sprawdzają odrzucanie nieaktualnych kandydatów nadzbioru audytu i nierozdzielanie remisów hashy źródeł: końcowy moduł 5 PASS. Łącznie 49 różnych testów PASS.
- Ruff format/check PASS; mypy PASS dla 3 zmienionych plików produkcyjnych. Mapa kodu zregenerowana; cztery skrypty bramki docs:check PASS. Audyt rundy 1: REVISE (P1-1, brak scenariusza historii w teście), raport i receipt zachowane jako quality/TASK-1180_AUDIT_claude-opus-5-5_round1.*.
- Nie zmieniono danych operatora, nie usunięto zdjęć ani failed pilotów, nie aktywowano modelu, nie restartowano usług. Pełne wykonanie pilota po wdrożeniu pozostaje odbiorem operatorskim. Restart i scalenie wymagają bieżącej zgody zgodnie z AGENTS.md.


### Jedna runda poprawek po audycie

- P1-1: rozszerzono rzeczywisty test PostgreSQL. Osobno tylko retired, tylko reserved slot i tylko restored entry wyłączają szybką ścieżkę; każdy wariant faktycznie wyklucza źródło. Dane zawierają też rejected review, niezgodną geometrię i ever_labelled RGB. Pełne listy starego i nowego zapytania są równe dla 3 seedów w każdym wariancie. Zagnieżdżone transakcje cofają wyłącznie własne fixture, nie dane operatora.
- P2-3: has_replacement_fences wymaga rzeczywiście posiadanej blokady EXCLUSIVE; nowy test sprawdza odmowę przed jakimkolwiek query.
- P2-6: wzorzec legacy zawiera zamrożone literały warunków poprzedniego kodu, niezależne od nowej ELIGIBLE_SQL.
- Weryfikacja poprawek: 7 PASS (6 jednostkowych i rozbudowany PG), 60,72 s. Łącznie 50 różnych testów PASS. Ruff format/check PASS. Mypy zmienionego modułu PASS, mapa zregenerowana i aktualna.
- P2-1 pozostaje odnotowanym ryzykiem: READ COMMITTED i istniejący EXCLUSIVE fence serializują główne workflowy, ale nie zweryfikowano wszystkich pisarzy projekcji. Równoległy zapis omijający tę blokadę może przesunąć rangi między partiami; odbiór pilota należy wykonać bez równoległego backfill lub masowych zmian korpusu. Nie deklarujemy pełnej izolacji REPEATABLE READ.
- P2-2: zaakceptowano późne filtrowanie nadzbioru audytu. Brak hydratacji oznacza niekwalifikujące się pole i jest pomijany; pilot nadal odmawia kodem stale. Doprecyzowanie wcześniejszej ogólnej sekcji Risks: ciche pominięcie dotyczy wyłącznie audytu i jego celowego nadzbioru.
- P2-4: 18,204 s pierwszego prefiksu pozostawia ograniczony zapas do 30 s. Wzrost korpusu/obciążenia może wymagać dalszej optymalizacji; pierwszy pełny pilot jest obowiązkowym odbiorem, bez obietnicy czasu ukończenia. Nie uruchamiamy benchmarku bez zgody.
- P2-5: brak osobnego testu zegara heartbeat odnotowany; dopięcie callbacku jest przeglądane statycznie, pełny job pozostaje odbiorem po wdrożeniu.
- Zależność odbioru: w drugim worktree trwa TASK-1181 (Jobs response). Naprawia HTTP500 przy odczycie i odpowiedzi retry readability. Tutaj nie zmieniamy jego kontraktu ani plików. Wznowienie pilota powinno nastąpić po wdrożeniu obu poprawek.

### Wynik końcowy

- Opus 5.5: runda 2 PASS, 0 P0 / 0 P1. Raport quality/TASK-1180_AUDIT_claude-opus-5-5.md i receipt mają SHA pakietu 41d1ebb9d04ac6e3971838f62519b9094f669cc3984b6847cfa9e48cd3b2a6ba oraz potwierdzony model z system.init. Runda 1 zachowana obok. Pozostają jawnie odnotowane P2-1/4/5.
- P2-7: po PASS dodano wyłącznie asercje testowe wykluczenia konkretnego stale ID i oznaczonego RGB. Fixture dostaje jawny niepusty RGB (zwykły backfill bez dekodowania nie zapewnia go). Test PostgreSQL ponownie 1 PASS, 61,17 s; kod produkcyjny nie zmienił się po PASS, bez trzeciego audytu.
- P2-8: licznik we wskaźniku poprawiony; docelowy wiersz done powstaje przez close_task.py.
- npm run docs:check i npm run code-map:check PASS. Początkowa próba npm bez lokalnego .venv nie znalazła Pythona; utworzono junction do istniejącego środowiska root i powtórzono właściwe kontrole. To wyłącznie konfiguracja kopii roboczej, bez instalacji i zmian usług.
- Dodatkowy odczyt READONLY w nowym procesie, pod wymaganą blokadą: pierwsze 250 rzeczywistych pól ma 0 brakujących tożsamości RGB; nie uruchomiono joba. Dowód lokalny check-identities.py.
- W trakcie pracy main przesunął się do fc37f563 (TASK-1181, v1.7.600). Własne zmiany zachowano w odwracalnym stash, roboczą gałąź przesunięto fast-forward do main, przywrócono zmiany i zregenerowano konfliktującą mapę. Kod taska porównany z zapisem sprzed synchronizacji. Numer commita taska wynika z aktualnego brancha: v1.7.601; brak kolizji 599/600. API i usługi nadal nie były sterowane przez ten task.
- Definition of Done: zmieniony pion zweryfikowany, snapshoty/kolejność i gałęzie current pokryte, kontrakt API i schemat bez zmian, kod trwały sprawdzony z nowego procesu, dokumentacja i audyt rozliczone. Pełny pilot oraz scalenie/push/restart są wyraźnie oddzielonym odbiorem po zgodzie operatora.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1180 — Timeout pilota | gpt-6-astra | high | Zachowanie deterministycznej selekcji przy zmianie SQL | Claude Code claude-opus-5-5/high |
