---
title: Odbiór implementacji jakości i wymiany źródeł 777 A2
status: active
last_updated: 2026-11-03
---

# Odbiór TASK-1124–1132

Implementacja narzędzi jest dostarczona. Empiryczna skuteczność detektora pozostaje niezmierzona: nie wykonano etykietowania, fitu, pilota ani skanu operatora. Dokument nie jest zgodą na migrację, operacje danych, aktywację, wdrożenie ani merge/push.

## Podstawa odbioru

Gałąź `codex/777a2-readability-replacement`, D1 start `07956943`; zintegrowana i testowana baza main `40581449`. Nowszy main `fa38a3cd` wymaga osobnego preflight przed integracją. Nie przepisywano kolidujących numerów wersji. Poniższe wyniki A1–C2 są istniejącymi dowodami z Outcomes, nie nowymi przebiegami D1 ani sumą unikalnych testów.

## Pokrycie planu D1

| Kryterium | Dowód | Granica dowodu |
|---|---|---|
| Ostre nałożenia z pewnym top1, podobne czytelne | A1 testy bramki/liczności, A2 przypięta kalibracja i brak utożsamiania historycznej confidence z dowodem | Nie ma empirycznej estymacji jakości. Brak grup kończy się STOP. |
| Brak leakage base/head/scaler i neutralność wag/BN/aktywacji | [A1 Outcome](../tasks/completed/1124-readability-detector-core.md): 37 testów, frozen extractor, fit/reload, rodziny, TRAIN-only scaler/VAL-only tuning | Końcowy mypy A1 partial: błąd serializacji TypeGuardedType i cisza alternatywnej próby; zaakceptowane przez koordynatora, nie PASS. |
| Stale pixel identity i trwały skan | [A2 Outcome](../tasks/completed/1125-readability-durable-review.md): 19 testów i 4 isolated PG, nowa sesja, dedup/lost response, geometry drift409, źródło decode raz | Bez uruchomienia na danych operatora. |
| Shift poza DOM, locked, limity i kolejka | [A3 Outcome](../tasks/completed/1126-shift-range-selection.md): 37 logiki/keyboard, 30 interakcji, 2 bulk regresje; cap10001, nowy proces, lost response, pause409 | jsdom/Node, bez fizycznego Androida. |
| Deduplikacja całego źródła i boundary<9 | [B1 Outcome](../tasks/completed/1127-source-replacement-manifest.md): 13 unit/HTTP, 4 PG, 17 schema readiness; aliasy, krótki exact range, ledger, RLS | Planned nie oznacza wycofania. |
| Obcy pending, races, późne komendy i późny seq | [B2a Outcome](../tasks/completed/1128-source-replacement-ownership.md): wspólne 8 PG, guards i late seq; [B2b Outcome](../tasks/completed/1129-source-replacement-retirement.md): 2 PG, foreign pending/rollback/replay; [C2 Outcome](../tasks/completed/1131-source-replacement-import.md): restored i late commands | Wyłącznie własne bazy testowe; bez resetu danych operatora. |
| Guarded fallback, liczniki, incremental/rebuild parity | B2a: wspólny predykat current oraz legacy accepted/corrected fallback, bezpośredni stale fastdoc; B2b: current search/supergame; C2: terminalny fence po usunięciu slots | Stare frozen/history pozostają poza current filtrem. |
| Retained modele/kohorty/shared crops obu gier | B2a: inactive-model/prediction retention, cross-game registry, cleanup recovery pod fence; testy guardów/GC i PG | Nie wykonywano rzeczywistego cleanup/GC. |
| Snapshot blocked while gap i po restored | B2b publication/markready race; C2 mobile własny PG1, zwykłe release/layout PG2, worker3: old/NULL lineage refusal, current capture i fence | Wydane stare snapshoty pozostają; brak nowego wydania APK. |
| Journal, lost response i restarty etapów | A2/A3 outbox; B1/B2b receipts/new sessions; [C1 Outcome](../tasks/completed/1130-source-replacement-repair.md): core14 i Admin60, realny dysk/fresh process; C2 durable upload/job/admission/restored | Bez fizycznego Windows Chrome/FSA. |
| Niepełny batch/import/review nie udaje sukcesu | C1 selected A z request A+B i verified committed-only handoff; C2 core PG5, undo43, Node81, HTTP5+2: partial working, rollback, orphan closure, jawna czytelność i restored | Jeden admission/source na entry; brak trybu kolejnej próby/zdjęcia. |
| API/OpenAPI/generated/wrapper/request tests | A2/B1/B2b/C2 Outcomes; aktualne D1 freshness poniżej | Nie utrzymywano ręcznych rozbieżnych typów. |

## Świeża weryfikacja D1

Logi lokalne: `D:/game_predicotr/artifacts/t1132/`. Kontrole mają timeout120s; znany build Admina300s. Root Python uruchamia dokładnie cztery skrypty `docs:check`, ponieważ worktree nie ma własnego `.venv`; jest to równoważne rozwinięciu wrappera npm, nie pominięcie kontroli.

- Admin OpenAPI `--check` PASS14,45s; generated client check PASS7,84s; code-map `--check` PASS6,14s.
- Decision links, current-state window, startup budgets i skill mirrors PASS.
- Rzeczywiste buildy klienta TypeScript PASS4,45s i core PASS1,77s; board-search-ui typecheck PASS3,44s; Selector `node scripts/build.mjs` PASS0,55s.
- Admin `next build` domyślnym Turbopack PASS22,44s: kompilacja, TypeScript i statyczne strony. Ostrzeżenie o dwóch lockfile/root jest jawne. Resolver świeżego procesu wskazywał lokalne pakiety worktree; użyto tymczasowych app-local junctions. `finally` usunął wyłącznie własne linki, bez rekurencji; resolver po cleanup ponownie wskazuje główny checkout. Root junction i zależności main pozostały bez zmian.
- Dokładna grupa APK z Outcome1129, bez deselection: **47 passed in23,81s**, wall26,80s, kod0. Historycznej przyczyny zależności kolejności/środowiska nie ustalono; obecny pełny przebieg jej nie odtworzył. Nie uznajemy jej za potwierdzony stary błąd. Pierwsza próba w ograniczonym środowisku zatrzymana po88,88s bez postępu; oba własne procesy pytest zakończone i sprawdzone przed wznowieniem. Nie jest to wynik testów.

Dokładne polecenie APK (cwd tego worktree, timeout120s):

```powershell
& D:/game_predicotr/.venv/Scripts/python.exe -m pytest services/api/tests/test_source_retirement.py services/api/tests/test_source_replacement.py services/api/tests/test_cleanup_api.py services/api/tests/test_super_game_input_version.py services/worker/tests/test_release_workflow.py -q --tb=short --basetemp=D:/game_predicotr/artifacts/t1132-apk
```

Świeżych zielonych testów A1–C2 nie powtarzano. Pełnego repo quality/backend mypy ani benchmarków nie uruchamiano. Scoped lint/typecheck i regresje są opisane w źródłowych Outcomes. C2 P2-1 sprostowany istniejącym lockiem; P2-2 dostępność LEFT JOIN i P2-3 redundantne self-comparison zaakceptowane, bez zmian w D1.

## Definition of Done

| Obszar | Rozliczenie |
|---|---|
| Funkcjonalność | Wszystkie punkty D1 mają dowód lub jawne ograniczenie powyżej; sequence_number pozostaje domenową kolejnością. |
| Kod | D1 nie zmienia kodu produktu. Poprzednie piony mają domenę oddzieloną od HTTP/UI, trwałe receipts i regresje nowych procesów. Tymczasowe przygotowanie builda posprzątane. |
| Dane | Alembic0172–0176, merge-head0173 i manifestv20/v21 sprawdzone w isolated PG; retencja/RLS i seq guards. Baza operatora niezmieniona. |
| Kontrakt | Backend/OpenAPI/generated/wrapper/request test dostarczone; aktualność sprawdzona D1. |
| Testy/narzędzia | Celowane dowody powyżej, świeże buildy/checks. Mypy A1 partial pozostaje ograniczeniem. |
| UX | Loading/empty/error, confirmation, przyciski i brak double-submit sprawdzone w testach UI. Fizyczne Chrome/FSA i Android czekają na ręczny odbiór. |
| Dokumentacja/raport | Ten raport, task, plan, CURRENT_STATE i audyt; zamknięcie przez task-close i record-hash. Wymagania/architekturę oraz D-578/579/580 aktualizowano w A1–C2; D1 nie wprowadza nowej decyzji ani zachowania wymagającego ich zmiany. |

## Instrukcja odbioru operatora

1. Najpierw zaakceptować wynik implementacji. Osobno uzgodnić integrację do aktualnego main z preflight migracji, konfliktów numeracji i map. Agent nie wykonał merge/push.
2. Wdrożenie, migrację do0176 i restart usług wykonuje operator po osobnej zgodzie. Przed operacjami danych zachować normalny podgląd i potwierdzenie; raport nie upoważnia do wycofania zdjęć.
3. W Chrome/Windows sprawdzić UI jakości, Shift oraz lokalny picker source/output z read-only source. Na fizycznym Androidzie sprawdzić wspierane ekrany webowe i dotyk; lokalny FSA wymaga przeglądarki z natywnym pickerem.
4. Dla detektora: przygotować niezależny pilot zgodnie z limitami planu, zebrać osobne etykiety czytelności/overlap i audit200 przed fitem. Bez wymaganych rodzin/liczności zatrzymać. Fit, TEST i odbiór modelu są odrębnymi krokami. Dopiero PASS i jawny odbiór pozwalają uzgodnić skan. Kandydat nr5 nie jest aktywowany.
5. Dla wymiany: wybrać całe źródła, zapisać planned i eksport, sprawdzić świeży podgląd oraz osobno potwierdzić retirement. Eksport selected gap_open otworzyć w istniejącym narzędziu naprawy; wybrać nowy JPEG exact range, osobny output i autoryzację przez skonfigurowane API. Następnie zwykły staging/import i korekta geometrii, normalne approvals oraz osobne potwierdzenie czytelności/restored. Niepełny zapis/review pozostawia lukę. Po utracie odpowiedzi użyć oryginalnego klucza/recovery, bez nowej komendy w ciemno.

Wynik ręcznego odbioru i decyzję o integracji zapisać w Outcome uzgodnionego taska operatorskiego oraz wskazać w CURRENT_STATE. Dla kroku3 zapisać urządzenie/przeglądarkę i wynik: crop/zoom/całe źródło, Shift pomijający locked, jasny stan błędu oraz brak zapisu do folderu źródłowego; odmowa lub brak uprawnień nie mogą udawać sukcesu. Nie oznacza to uruchomienia nowej automatycznej pracy.

Następny krok to odbiór operatora i decyzja o integracji. Brak zgody na operacyjny pilot, pełny skan, aktywację, usuwanie danych lub automatyczne wydanie.
