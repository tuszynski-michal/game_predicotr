---
title: TASK-1162 — Weryfikacja routingu CLI rejestracji diagnostyk
status: active
last_updated: 2026-11-06
---

# TASK-1162 — Weryfikacja

## Problem i zmiana

Root odtworzył `GAME_STORAGE_SCOPE_REQUIRED` w zatwierdzonym wdrożeniu T6:
`register_grid_diagnostics.py execute` otwiera zwykły SQLAlchemy Session, któremu
sam kontekst `game_storage_scope` nie ustawia transakcyjnego routingu SQL.
Transakcja operatora wycofana, zero zapisów według odbioru root.

Naprawa dodaje wyłącznie importy GameStorageRouter/Intent i jawny bind WRITE
wewnątrz istniejącego begin po ustawieniu lokalnych timeoutów, przed pierwszym
SQL domenowym/capability. Router ustawia SQL scope,
sprawdza status i pobiera wspólną blokadę zapisu. Format manifestu, klucze
idempotencji, funkcja SQL, timeouty writer i atomowa transakcja pozostają zgodne.
Brak raw set_config, obejścia właścicielem, zmian schematu/API/UI i usług.

## Wykonane kontrole

Wszystkie komendy z WT `D:/game_predicotr/worktrees/full-board-detection`, HEAD
`119f4716` v1.7.568. Helper `artifacts/task1162/run_check.py` uruchamia komendę
przez subprocess z timeout120s i zapisuje UTF-8. PG tylko przez jawny opt-in
`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, własny resource root
`artifacts/task1162/pg-resources`. Subprocess CLI ma timeout15s i usuwa odziedziczone
PGOPTIONS. Test blokady polega na własnym lock_timeout3s CLI, ustawionym przed
routerem, obok statement_timeout10s. Brak wstrzykiwania limitu połączenia.

| Kontrola | Wynik | Log w artifacts/task1162 |
|---|---|---|
| pytest test_diagnostic_registration_cli_postgres.py -q | 1 PASS / 29.75s, wrapper32.39s | green-budget-final.txt |
| ruff check, oba pliki Python | PASS | lint-budget.txt |
| ruff format --check, oba pliki | PASS | format-budget.txt |
| mypy scripts/register_grid_diagnostics.py --follow-imports skip | PASS, 1 source file | types.txt |
| generate_code_map.py + aktualny --check | PASS | map-generate.txt, map-budget.txt |
| npm.cmd run docs:check | PASS, startup44110/45000B, window16039B,11/11budżetów | docs.txt |
| git diff --check | PASS | diff-check.txt |
| READ ONLY cleanup po dokładnych nazwach/OID własnych zasobów | 5journali, DB0/roles0/sessions0 | cleanup.txt, cleanup.json |

Ruff/mypy używają `.venv/Scripts/python.exe -m <narzędzie>`. Polecenie testu:

```powershell
.venv/Scripts/python.exe artifacts/task1162/run_check.py green-budget-final.txt --postgres .venv/Scripts/python.exe -m pytest services/api/tests/integration/test_diagnostic_registration_cli_postgres.py -q
```

## Dowód regresyjny

Test tworzy rzeczywistą disposable PG0181 i LOGIN applicationRole przez istniejący
application_role_database, provisionowanie capability i migracje. Gra ma wymagane
neural_grid_v3. Synthetic strict record korzysta z istniejącego fixture T1;
brak danych/zdjęć operatora. CLI uruchamiane bezpośrednio z worktree w czterech
świeżych subprocessach, z przypiętym PYTHONPATH worktree, przez rzeczywiste
get_settings i create_database_engine. Nie mockuje SQL, ustawień ani silnika.

1. Maintenance status=migrating: execute odmawia, prywatny ledger pusty.
2. Status active, owner trzyma exclusive advisory game-write fence: CLI kończy
   się lock timeout, ledger pusty. WRITE routera musi konkurować o tę samą blokadę.
3. Po zwolnieniu fence: execute kończy się sukcesem, dokładnie jeden wpis ledger.
4. Nowy proces ponawia dokładnie ten sam manifest (utrata odpowiedzi pierwszego
   execute): sukces, identyczne id/payload/digest/actor, bez duplikatu. Nowa sesja
   appRole odczytuje diagnosticExposed=true przez publiczny context v3.

Wyłącznie odczyt prywatnego ledger jest kontrolą właściciela; wszystkie cztery
execute korzystają z URL applicationRole. Wcześniejsze trzy nieudane próby były
błędami setupu fixture: nieuprawniony bezpośredni odczyt ledger (dwie próby) i
brak neural_grid_v3 (jedna). Nie traktuje się ich jako odtworzenia błędu produktu.
Pierwszy pełny PASS27.59s używał PGOPTIONS750ms, co maskowało oczekiwanie bind
przed lokalnymi timeoutami. Root wykrył tę lukę przed audytem. Istniejące SET LOCAL
przeniesiono przed bind, a PGOPTIONS usunięto z testu. Końcowy PASS29.75s dowodzi
budżetu samego CLI; brak mocka routera lub oczekiwania poza subprocess15s.
Wszystkie pięć disposable baz/ról/capability posprzątane i zweryfikowane
niezależnym odczytem po nazwach/OID z journal.

## DoD i ograniczenia

AC1–3 pokrywa test rzeczywistego CLI w zakresie opisanym wyżej. AC4: celowane
kontrole PASS; rzeczywisty niezależny [audyt Opus5.5/high R1](TASK-1162_AUDIT_claude-opus-5-5.md)
PASS, brak P0/P1. Audyt był statyczny: nie uruchamiał testów i nie weryfikował
operacji operatora. Root przeczytał raport i zaakceptował task-close oraz pięć P2
bez rozszerzenia minimalnej naprawy i bez kolejnej rundy audytu:

1. Dowód replay obejmuje identyczny ledger, bez porównania zwracanego receipt.
   AC2 nie oznacza dowodu równości receipt; nowe wyjście CLI poza naprawą.
2. Test jednego requestu nie odtwarza rollbacku w środku partii. Odmowy maintenance
   i fence mają zero zapisów; istniejącej pojedynczej transakcji nie zmieniano.
3. Stare timeouty per statement nie są limitem całej partii do250 requestów.
   Root podał outer110s i32 bindings w4s dla własnej operacji; to nie gwarancja
   najgorszego czasu250. Limit całej transakcji nie jest częścią naprawy routingu.
4. Pozostaje wcześniejszy raw traceback; stabilne kody błędów CLI poza zakresem.
5. Scoped mypy follow-imports=skip nie sprawdza pełnego grafu zależności;
   raportujemy wyłącznie wynik skryptu, bez deklarowania pełnego typecheck.

Bez decyzji domenowych, migracji, zmiany kontraktu API i generowania SDK.
Instrukcja operatora wyjaśnia jawny WRITE binding; mapa odświeżona.

Nie otwierano prywatnego manifestu rollout, nie rejestrowano niczego na bazie
operatora, nie uruchamiano usług, treningu ani inference. Nie powtarzano buildów
ani suites T0–T6. Test potwierdza działanie retry na fixture; wynik właściwych
requestów operatora weryfikuje osobno root; zgłosił rejestrację32 rekordów przez
jawne routed-capability workaround z timeoutami. Nie jest to wykonanie naprawionego
CLI ani dowód jakości modelu. Pakiet audytu zawiera wyłącznie jawne pliki
kodu/testów/dokumentacji; bez manifestów operatora, zdjęć, DB, .env i payloadów.
