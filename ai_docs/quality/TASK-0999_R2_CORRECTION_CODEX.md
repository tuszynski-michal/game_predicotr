# TASK-0999 — ograniczona odpowiedź na R2-P1-1

Data: 2026-10-15. Wykonawca: gpt-6.1-sol/high.
Baza pozostaje v1.7.378 / `d078938b18abdff5d6e1f99795f9d4aca09716b1`.
Operator zatwierdził dodatkową ograniczoną rundę po R2 oraz kontrolny audyt
Claude Code. Lead wydał release wyłącznie R2-P1-1. Raporty R1/R2 oraz odpowiedź
na R1 zachowano bez zmian. To odpowiedź wykonawcy, nie niezależny audyt.

## Poprawka

`GridReinferenceHandler.cancellation_boundary` nie przekazuje już pustego
payloadu. Gdy bieżący checkpoint nie jest w wersji 1, buduje
`schema_version=1`, `workflow=grid-reinference-v1`, `phase` zgodną z zachowanym
stage oraz `cursor=progress_current`. Ten cursor opisuje bieżącą pozycję
postępu joba; trwały cursor źródeł i receipts nadal należą do operacji.
Istniejący poprawny checkpoint zachowuje całą zawartość. Granica przekazuje
zachowany stage i liczniki do istniejącego checkpointu sklepu. Nie zmieniono
przejść domenowych, kolejki, blokad, schematu ani mechanizmu wznowienia.

Poprawny `checkpoint_job` utrwala payload/postęp, a następnie istniejące
`acknowledge_job_cancellation` potwierdza anulowanie w tej samej transakcji
produkcyjnego store. Runtime otrzymuje `_ExecutionStopped(CANCELLED)`.
Handler zamyka runner w istniejącym finally. Anulowanie nie wymaga już
awaryjnego `store.fail` ani reconciliation gałęzi błędu.

## Regresje i wyniki

- Przed zmianą handlera uruchomiono nową regresję rzeczywistej domeny:
  **1 FAIL / 1 PASS**. Przypadek bez checkpointu odtworzył dokładnie
  `UNSUPPORTED_JOB_CHECKPOINT_VERSION`; istniejący poprawny payload przechodził.
  Log: `artifacts/audits/TASK-0999_R3_RED_REGRESSION.txt`.
- Po zmianie cały istniejący plik testów handlera: **9 PASS**, 2.90s.
  Store testowy deleguje do rzeczywistych `renew_job_lease`, `checkpoint_job`
  i `acknowledge_job_cancellation`. Sprawdza typowane zatrzymanie, CANCELLED,
  stage/cursor/payload i zamknięcie runnera; osobny wariant sprawdza niezmienność
  poprawnego checkpointu z dodatkowymi polami.
  Log: `artifacts/audits/TASK-0999_R3_WORKER_TESTS.txt`.
- Izolowany PG, wyłącznie `cancel_prepare` i `cancel_between_sources`:
  **2 PASS**, 44.55s. Oba używają rzeczywistego checkpointu store, wymagają
  utrwalonego schema_version/stage/phase/cursor, braku error_code oraz zerowych
  wywołań `store.fail` i `_reconcile_board_search`. Pułapki nie pozwalają
  przejść przez fallback błędu. Zachowano asercje receipts, braku dalszych
  zapisów, zamknięcia runnera i wznowienia od trwałego postępu.
  Log: `artifacts/audits/TASK-0999_R3_PG_CANCEL.txt`.
- Ruff/format trzech zmienionych plików Python PASS. Mypy właściwego handlera
  `--follow-imports=silent`: **1 source file PASS**, 43.705s, 2515 modułów
  zależności, 0 errors. Pierwsza próba miała timeout55s; odczyt PID potwierdził
  brak osieroconego procesu. Końcowy przebieg z rzeczywistym logiem postępu
  mieścił się w limicie110s. Reguł typów nie zmieniono.
  Logi: `TASK-0999_R3_TYPES.txt` i `TASK-0999_R3_TYPES_PROGRESS.txt`.
  Docs/map/diff rozlicza `TASK-0999_R3_IMPLEMENTATION_EVIDENCE.json`.
- Własna fixture PG sprawdziła dokładnego owner i brak aktywnych PID, usunęła
  tylko swoją DB/rolę. Receipt ma `phase=cleaned`, `pidsBeforeCleanup=[]`,
  `databaseRemaining=0`, `roleRemaining=0`; dane operatora niezmienione.

Wszystkie komendy miały twardy limit do 120s i jawny PYTHONPATH worktree
api/src, worker/src, test_support; PG dodatkowo katalogi testów API/integration.
Nie uruchamiano TestClient, usług ani rzeczywistego modelu. Nie powtarzano
niezmienionych zestawów całego pionu. Poprzednie manifesty/dowody zachowano;
nowy manifest obejmuje wyłącznie tę korektę.

## Ograniczenia i przekazanie

R2-P2-1 (niespójny kandydat lub niedostępny magazyn może przerwać claim)
i R2-P2-2 (konserwatywna ochrona obcego żywego item może pominąć własny kanon)
pozostają jawnie zaakceptowanymi ryzykami bez dodatkowego kodu. Wcześniejszy
pełny reset pozostaje FAIL, bez xfail i bez rozszerzenia zakresu. Nie zmieniono
operatorDB, usług, backupów, modeli, treningu, GPU, migracji operatora ani
integracji. Brak stage/commita i audytu własnej pracy. Następny krok prowadzi
lead: kontrolny R3 Claude high/do1200s, ograniczony do R2-P1-1. Wykonawca nie
przypisuje własnej poprawce werdyktu audytu PASS.
