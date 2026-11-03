---
title: Zakres zaznaczenia Shift i trwały zapis grup jakości
status: done
last_updated: 2026-11-03
---

# TASK-1126 — Zakres zaznaczenia Shift i trwały zapis grup jakości

## Status

`done`

## Goal

Dodać inclusive Shift w obu przeglądach oraz bezpieczny zapis do 10 000 zaznaczonych pól jakości.

## Dependencies / entry conditions

A2 zamknięty v1.7.519 / 8c096263, hash zapisany w v1.7.520. Cały plan i koszt oraz kontynuacja A3 zatwierdzone przez operatora. Bez usług i operacji danych operatora.

## Recommended execution

gpt-6.1-sol / medium; audyt claude-opus-5-5 / medium przed commitem. Niedostępność konfiguracji blokuje task.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md` — A3
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md`

## Scope / technical notes

Zwykły klik toggle+anchor; Shift dodaje inclusive range obu kierunków po pełnej bieżącej stronie, pomija locked i zachowuje już zaznaczone. Gry/filtry/sort/strona/refetch resetują anchor. Bez anchor zwykły klik. Cap 10 000 odrzuca cały nowy range atomowo. All_matching usuwa tylko wyłączenia zakresu. Zachować istniejące klawiaturowe akcje i bulk preview/jobs.

Uściślenie zaakceptowanego limitu: 10 000 dotyczy zaznaczenia, 250 dotyczy jednego żądania label API. Większy zapis używa sekwencyjnych porcji do 250. Przed pierwszym żądaniem localStorage utrwala cały snapshot targetów/identity/revisions i klucze wszystkich porcji. Checkpoint dopiero po potwierdzeniu. Błąd/konflikt pauzuje ogon i pokazuje wykonane/pozostałe. Jawne retry zachowuje snapshot i klucz; bez rebase. Mniejsze komendy zachowują dotychczasowy workflow. Limit walidowany przed zapisem kolejki.

## Expected files

Istniejące: oba workspace i state w `apps/admin/src/features/{symbol-reviews,readability}`, testy stanu/interakcji, wymagania/architektura, plan i mapy. Nowe: współdzielony helper zakresu, trwała kolejka jakości i jej regresje.

## Acceptance criteria

- [x] Inclusive Shift obu kierunków, pomijanie locked, pełne dane poza DOM i reset anchor.
- [x] Atomowy cap 10 000 i all_matching bez utraty innych wyłączeń.
- [x] Kolejka >250 utrwala snapshot i klucze; retry po restarcie/utracie odpowiedzi bez powtórnej mutacji.
- [x] Błąd/409 zatrzymuje ogon; widoczny postęp i ręczne retry.
- [x] Dotychczasowe bulk/klawiatura i małe komendy zachowane.
- [x] Testy, lint/typecheck, code-map/docs, audyt i commit rozliczone.

## Verification

Celowane testy Node i tsx interakcji w apps/admin, lint zmienionych modułów i typecheck Admina. Python głównego checkoutu do regeneracji mapy i docs:check. Komendy testów z timeoutem 120 s; audyt 480 s. Testy planowane nie są wynikami.

## Outcome

Commit: v1.7.521 / `2720e7aab26c6c0f29add4fe7dd376fd996903ea`.

### Audit corrections (runda 1)

Audyt Opus5.5/medium potwierdzony przez JSON modelUsage: `claude-opus-5-5`. P1-1: trwały konflikt wymaga wyjścia z kolejki. Dodano wyłącznie jawną akcję operatora z potwierdzeniem, bez cofania zapisów; przy utraconej odpowiedzi UI ostrzega, że niepotwierdzona porcja mogła już zostać zapisana. Akcja jest zablokowana podczas requestu i dostępna również przy uszkodzonej kolejce, bez zgadywania liczników. Bez automatycznego czyszczenia/rebase. P2-1: przywrócono poprawny UTF-8 kolejki i początkowej części tego taska, potwierdzone odczytem bajtów. P2-2: trwały409 pozostaje błędem przy retry; osobny test lost response odpowiada za udane wznowienie. P2-3: limit porcji pochodzi z ilorazu stałych. Reaudyt zmian P1: PASS, [raport Opus 5.5](../quality/TASK-1126_AUDIT_claude-opus-5-5.md). JSON modelUsage obu merytorycznych rund potwierdza `claude-opus-5-5`. Pierwsze uruchomienie bez dostępu do sieci dało ENOTFOUND i0tokenów; nie było audytem. Obie właściwe rundy wykonano z dostępem do API, tylko Read/Glob/Grep.

### Changed

Inclusive Shift w obu przeglądach; zwykły review działa po pełnej stronie2500, pomija pending/settled/hidden, all_matching usuwa tylko wyłączenia zakresu. Readability zachowuje snapshoty zaznaczeń między stronami250 i zapisuje większe grupy w trwałej kolejce porcji250. Brak zmian API i danych operatora.

### Verification results

- Finalnie 37/37 testów logiki, keyboard i workspace contracts PASS: `node --experimental-strip-types --test test/symbol-review-selection-state.test.mjs test/readability-state.test.mjs test/readability-label-queue.test.mjs test/symbol-review-workspace-contract.test.mjs test/symbol-review-keyboard.test.mjs` (cwd apps/admin, timeout120s).
- Finalnie 30/30 interakcji PASS: `node ../../node_modules/tsx/dist/cli.mjs --tsconfig tsconfig.json --test test-interactions/readability-workspace.test.mjs test-interactions/symbol-review-partial.test.mjs` (cwd apps/admin, timeout120s). Po dodaniu asercji Shift pomijającego locked: obie regresje independent bulk jobs ponownie2/2PASS.
- Zapis kolejki przed pierwszym requestem, atomic cap10001, checkpoint storage failure, pause409, lost response i replay z nowego procesu Node PASS. UI cold mount zachowuje rewizję3 mimo pobrania99.
- ESLint zmienionych modułów/testów PASS; prettier zastosowany. Scoped TypeScript PASS: `node node_modules/typescript/bin/tsc --noEmit -p artifacts/task1126-tsconfig.json` (cwd root, timeout120s). Config extends ABS apps/admin/tsconfig.json, include obu zmienionych features oraz tymczasowy next-env, paths @/* do lokalnego apps/admin/src/* i @game-predictor/admin-api-client do lokalnego packages/admin-api-client/src/index.ts; incremental=false. Nie osłabia strict ani typów. Zwykły tsc przez junction node_modules czytał klienta main bez typów Readability; niezwiązane baseline grid-model-comparison również poza zakresem.
- Po poprawkach audytu: 9/9 pure queue+state, 12/12 UI readability, scoped ESLint i strict TypeScript PASS. Trwały409, anulowanie/potwierdzenie porzucenia, corrupted queue i disabled podczas requestu objęte regresjami.
- Mapa kodu zregenerowana. Cztery kontrole docs:check i `generate_code_map.py --check` PASS przez Python głównego checkoutu. Sam npm docs:check w worktree nie znalazł lokalnej .venv; uruchomiono identyczne skrypty z timeout120s. Audyt runda2 PASS; wszystkie P0/P1 zamknięte.

### Non-blocking review notes

N-1 (P2): SyntaxError uszkodzonego JSON może być po angielsku. Ścieżka potwierdzonego porzucenia jest po polsku i działa bez zgadywania liczników; brak wpływu na integralność/recovery. Odnotowano bez rozszerzania jedynej rundy poprawek.

N-2 (P2): test sprawdza liczby postępu oraz ostrzeżenie o niepotwierdzonej porcji, lecz nie dosłowny tekst liczników w dialogu. Audytor zweryfikował zgodność tych samych obliczeń w dialogu; brak wpływu na wynik.

### Definition of Done / plan comparison

Wszystkie sześć kryteriów taska spełnione: zakres i resety obu workspace, atomowy cap/all_matching, pełne snapshoty/restart/replay, błąd pauzujący i jawne porzucenie, regresje keyboard/bulk/small commands, kontrole i niezależny audyt. Brak zmian API/schematu wymagających pionu kontraktu lub migracji. DoD: funkcjonalność/kod/testy/docs spełnione w izolowanych fixture'ach; empiryczny smoke operatora i Android pozostają jawnie niewykonane. Bez merge/push.

### Not completed

Bez operatorowego smoke w działającym Adminie/Androidzie, usług, migracji, merge/push i operacji na danych. Testy UI wykonane na izolowanych fixture'ach.

### Documentation updates

Plan A3 i wymagania/architektura opisują limit10000/250, snapshoty między stronami i trwałe recovery.

### Recommended next task

TASK-1127 / B1 po zamknięciu A3 przez koordynatora.
