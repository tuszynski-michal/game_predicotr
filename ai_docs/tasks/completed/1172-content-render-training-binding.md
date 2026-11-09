---
title: TASK-1172 — Powiązanie renderowania i danych z uczeniem
status: done
last_updated: 2026-11-09
---

# TASK-1172 — Powiązanie renderowania i danych z uczeniem

## Status

`done`

## Goal

Zachowanie rozłącznych danych, przypiętych kontraktów i historycznych raportów.

## Context

Operator zaakceptował cały plan i koszt 6–10 h; audyty tylko terminalowe.
Zatwierdzenie kosztu nie obejmuje operatorowego treningu, wdrożenia ani merge.

## Dependencies / entry conditions

TASK-1171 zamknięty. Przed kodem ponownie odczytać przypisaną sekcję zaakceptowanego planu.

## Recommended execution

gpt-6-astra/high. Uzasadnienie: Zachowanie rozłącznych danych, przypiętych kontraktów i historycznych raportów. Nierozwiązane P0/P1 blokują commit;
nie zmieniać modelu niejawnie. Review Claude Code claude-opus-5-5/high.

## Relevant docs

- `ai_docs/delivery/GRID_SYMBOL_CROP_PREVIEW_PLAN_20261109.md` — T3 i kryteria wspólne.
- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`.
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`.
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-593--izolowane-etykietowanie-i-dowodowy-eksport-html`.
- D-590/D-591/D-592 w tym samym pliku, przez wyszukanie odpowiednich sekcji.
- `ai_docs/process/CROSS_AUDIT.md`, `ai_docs/process/DEFINITION_OF_DONE.md`.

## Scope

Sekcja T3 planu i niezbędne testy regresji. Aktualne liczniki i braki; R0–R3 używają tych samych pinned danych; zmiana kontraktu unieważnia zgodę starego raportu; partial nie tworzy tła; kod/dane/jakość osobno; cold restart/replay.

## Out of scope

Aktywacja modelu/marginesu, operatorowy GPU/trening/import691, mutacje etykiet,
restarty usług, migracja operatora, merge/push oraz klasyfikator nowej architektury.

## Acceptance criteria

- [x] D-597: prawidłowy pomiar u/δ z rzeczywistym oracle render_contract_blocked
  może służyć wyłącznie diagnostyce marginesów; brak/unknown/integrity mismatch
  nadal blokują. Strict content_pin, freeze i bramki publikacji bez poluzowania.

- [x] Istniejący import8 + aktywny zgodny LAB_RGB0 daje nową sesję/oracle/referencev2
  z evaluation0 i nienaruszonym import8; pełny backend/OpenAPI/SDK/wrapper/request.
- [x] Ten sam pin przechodzi freeze, parent/child i ocenę; drift cropu blokuje,
  zmiana samych wag przy identycznym cropie zachowuje reguły v6.
- [x] Legacy/no-policyv1/retry i stare sesje/raporty pozostają byte-identical;
  blank lub aktualnepass1 A blokuje, inna stara pusta sesja nie unieważnia frozenAref.
- [x] Niepoprawne/mieszane/missing piny i oracle/A są blokowane przed kosztami
  optymalizatora; istniejący grid-only/partial semantics bez zmiany.
- [x] Każdy punkt T3 planu ma implementację lub jawny warunek zależny od danych.
- [x] Aktualne liczniki i braki; R0–R3 używają tych samych pinned danych; zmiana kontraktu unieważnia zgodę starego raportu; partial nie tworzy tła; kod/dane/jakość osobno; cold restart/replay.
- [x] Istniejące historyczne kontrakty i ręczne korekty są zachowane.
- [x] Właściwe testy, lint, typy i docs/map; niezależny Opus audit i receipt.

## Technical notes

D-597 domyka wykrytą później lukę diagnostycznego czytnika T2: nie mylić
prawidłowego pomiaru powtarzalności z dopuszczeniem błędnego cropu. Dodatkowe
pliki: storage/production_crop_capture.py, shared pure validator i ich testy.

D-596 rozstrzyga minimalne wpięcie: optional ContentSessionCreate.renderReferencePolicy
active-symbol-render-v2; backend wybiera rzeczywisty aktywny zgodny snapshot,
nie swobodny render klienta. Pin powstaje raz przed oracle/sesją i dziedziczy
się z jednej frozenAref przez split/cohort/R0–R3/eval/freshness. Refv2 oddziela
importProvenance od EvaluationContract; v1 i stare sesje bez zmian. Nie retargetować
dawnych sesji; obecna0/50 nie ma pracy. Nie reimportować zdjęć. Earlyguard przed
bankiem/inferencją/siecią/optimizer; brak B/REG nie blokuje legalnego treningu.
Szczegółowy read-only projekt: artifacts/TASK-1172_READONLY_HANDOFF.md.
T2 jest diagnostyką, nie wyborem aktywnego kontraktu ani raportem kwalifikacji.

Źródłem prawdy są rewizje zapisanych adnotacji, frozen snapshot i pinned render.
Nie zamieniać pudełka podglądu w GT. Nie wyświetlać podpowiedzi w blind; chronić
całe źródła użyte w pomiarze. Brak danych jest jawnym stanem, nie PASS.
Artykuły pomocnicze są w root artifacts/full-symbol-training-20261109; nie nadpisywać
ich ani bazy. Odczyt operatorski tylko read-only; wyniki do artifacts tego worktree.

## Expected files

services/api/src/game_predictor_api/storage/production_cell_reference.py; grid_content_experiment_inputs.py; services/worker/src/game_predictor_worker/images/grid_content_experiment_data.py; istniejąca gotowość/raport i testy. Drobne doprecyzowania listy zapisać po prześledzeniu pionu.

Faktyczny pion obejmuje nowe `domain/grid_render_reference.py`,
`storage/grid_render_selection.py`, `storage/grid_content_training_inventory.py`
i read-only `scripts/export_grid_content_training_inventory.py`; istniejące
session/oracle/split/cohort/evaluation/currentness oraz schema/OpenAPI/SDK/Admin.
D-597 dodaje `storage/grid_content_diagnostic_measurement.py` i diagnostyczny
opt-in w istniejącym capture/content_pin, bez zmiany domyślnej kwalifikacji.

## Test cases

Kryteria planu: ghost quad, wspólne granice/perspektywa, J/10/obramowania/ciemne
symbole, sąsiad, brak pikseli/rzędu, blind isolation, CAS/currentness i restart/replay.
Testy specyficzne dla taska doprecyzować przed implementacją w raporcie weryfikacji.

## Verification

Z katalogu worktree: właściwe testy pytest przez D:/game_predicotr/.venv/Scripts/python.exe
z PYTHONPATH własnego services/api/src i services/worker/src; testy Admin
`npm run test:geometry --workspace @game-predictor/admin`, scoped lint/typecheck,
`npm run docs:check`, `npm run code-map:check`. Każda komenda ma timeout.
Szerszy build dopiero po testach pionu. Audyt według CROSS_AUDIT do 1800 s.

Wykonawca: logi `artifacts/t1172-*`; interpreter
`D:/game_predicotr/.venv/Scripts/python.exe`, `PYTHONIOENCODING=utf-8`,
`PYTHONUTF8=1`, absolutne PYTHONPATH worktree API/worker/integration; timeout120s
na fazę i krótkie basetemp. Potwierdzone:

- API20 PASS (`t1172-existing-api.log`); reference unit5 PASS
  (`t1172-render-unit3.log`), dodatkowy rzeczywisty receipt/pin v2 w nowym procesie
  SQLite PASS (`t1172-cold-v2-final.log`). Replay omija zmieniony aktywny resolver;
  nullable targetSelection i brak/null nowego pola zachowują dawny fingerprint.
- Worker recovery/ledger/earlyguard15 PASS (`t1172-worker-recovery.log`), w tym
  zero wywołań sieci/banku/optymalizatora po błędzie preflight.
- Końcowy D597/preflight/crop50 PASS25.72s (`t1172-d597-final-tests.log`): realny
  oracle30 obrazów, SQL czytnik obu passów i aktualnych rewizji, CPU porównanie
  8→0, brak/unknown/context tamper/stale/missing pair odrzucane; domyślne
  content_pin, ProductionContentRun i preflight nadal blokują kwalifikację.
  D597 używa SQLite, nie poświadcza PostgreSQL RLS ani operatorskiej jakości.
- Disposable PostgreSQL v2: setup94.94s (`t1172-pg-setup3.log`, retained setup
  sam nie jest suite PASS), następnie nowy proces phase2 PASS1/102.77s
  (`t1172-pg-phase2.log`): rzeczywisty LAB registry0, zachowany import8,
  legacy create receipt cold replay, abandoned v1, frozen A, parent/freeze,
  jeden child, pełny worker proof reread i inventory. Oryginalny target.render8
  jest odrębny od execution0. Cleanup w nowym procesie potwierdza
  0DB/0runtimeRoles/0capabilityRoles (`t1172-pg-cleanup.json`), prywatny plik
  usunięty. D597 nie wymagał powtarzania tej kosztownej próby.
- Admin interaction28 PASS (`t1172-admin-interaction.log`), nowe wysłanie v2
  dodatkowo PASS1 (`t1172-admin-interaction-final.log`); SDK wrapper5 PASS
  (`t1172-client-test.log`); eksport OpenAPI/generacja i drift PASS
  (`t1172-generated-drift.log`). Istniejący wrapper przekazuje body bez zmian.
- Ruff/format i mypy19 plików PASS (`t1172-d597-ruff-final.log`,
  `t1172-d597-mypy.log`); końcowy nowy test receipt ma osobny Ruff PASS
  (`t1172-final-ruff2.log`). Admin scoped ESLint exit0, ostrzeżenie o katalogu
  pages przy uruchomieniu z root; TypeScript i Prettier sprawdzone osobno.
  Końcowy TypeScript exit0 (`t1172-admin-types-final.log`) i API domain/pins17
  PASS2.40s (`t1172-api-final.log`); `git diff --check` PASS.

Nie ma pełnego PASS istniejącego testu
`test_grid_content_experiment_workflow.py::test_real_child_dispatch_completes_and_replays_lost_export_response_once`:
próba T3 timeout120s/Windows fatal access violation w Torch Adam
(`t1172-workflow-trace.log`). Root wykonał ten sam nodeid na unchanged main
f8b8a05a: timeout60s, stos w fsync ledger, nie Adam
(`t1172-main-workflow-baseline.log/json`). To nie dowodzi tej samej przyczyny;
przyczyna pozostaje nieustalona. Nie osłabiono testu ani nie naprawiano Torch.
Po testach brak własnych orphan; trzy zastane procesy operatora nietknięte.
Mapy/docs check, niezależny Opus i zamknięcie pozostają po stronie root.

## Risks / open questions

Brak GT i rodowodu może blokować wynik jakości, nie implementację narzędzia.
Nie deklarować poprawy wytrenowanego modelu bez rzeczywistego eksperymentu.

## Outcome

Commit: v1.7.584 (hash dopisuje kolejny commit).

D-596 wdrożona jednym pionem API/OpenAPI/SDK/wrapper/Admin: nowa sesja opt-in
przypina aktywny kompatybilny kontrakt po receipt lookup, oddzielnie od importu.
Pin przechodzi oracle/A/freeze/parent/child/R0–R3/eval/currentness. Historyczne
v1/retry i etykiety poza A zachowano; niedostępny rodowód poza A nie usuwa label.
Nie retargetowano dawnych sesji ani nie zmieniono globalnego marginesu.

D-597 rozdziela poprawne u/δ i dopuszczenie cropu. Rzeczywisty oracle blocked
może służyć tylko diagnozie 8%/0%; report zachowuje blocked oraz diagnosticOnly
true/qualificationAllowed false. Strict caller wymaga wybranego kontraktu;
wyjątek diagnosticNone wiąże aktualny document/report/oracle sesji A. Trening,
kwalifikacja, publikacja/default/apply zachowują bariery; unique ready ma
pierwszeństwo przed blocked, A nadal potrzebuje dokładnej sesji i obu passów.

Weryfikacja: selector/preflight29 PASS10.04s, regresje73 PASS40.09s;
PostgreSQL pełny freeze/one-child/worker proof1 PASS102.77s oraz mały actual
advance/oracle/JSONB1 PASS29.87s. Fresh-process cleanup obu baz:0DB/0runtimeRoles/
0capabilityRoles. Cold v1/v2 receipts odtworzone bez aktywnego resolvera.
API20+17, reference5, worker recovery15, Admin28+1, wrapper5, SDK/OpenAPI drift,
Ruff/format/mypy19/TypeScript/Prettier PASS. Samodzielna kolekcja bez PYTHONPATH:
1 plik i cała Worker3623 PASS; to nie wykonanie3623 testów. Root docs/map PASS.
Szczegóły i nieudane próby w quality/TASK-1172_VERIFICATION.md i FIXES_R1/P1_5.

Opus terminal: R1 REVISE0P0/4P1, focused R2 zamknął je i wykrył P1-5 importu
testu. Operator jawnie zatwierdził dodatkową poprawkę i kontrolę; R2b PASS0P0/0P1,
actual model claude-opus-5-5, high żądane. Canonical i exact R1/R2/R2b report/receipt
zachowane. Payload R2b83937579f3986f516e7e106a4a05de81e0730bd922bae2fa2c186648b8b8af01,
SHA raportu7b455a8716b6595b6b2cd0629cffb56a972b94d5a3365483a66155360997ab22,
sprawdzone z receipt. Dodatkowy focused scope obejmuje poprawkę P1-5 i wcześniejszy
raport; kod produkcyjny pozostał zamrożony od pierwszego R2.

Read-only inventory wybranej kohorty dae22c06…/1b97e3a…: frozen TRAIN98sources/
10used/90boards, A13/5/45, REG13/13/21, B brak; content/render pins0. LiveTRAIN45
dokumentów/383obrysy, humanApproved0, current human class proof0. A/REG content0,
unresolved TRAIN88/A8, brakuje5 pełnych REG. Nie są to globalne liczniki gry,
gotowe etykiety ani wynik wytrenowanego modelu; quality pozostaje not_measured.

Otwarte P2 przyjęte jawnie do T4: P2-1 koszt resolvera per-board bez pomiaru/cache;
P2-4 pełny długi workflow treningowy bez PASS (T3 Windows native Adam/timeout120,
main timeout60 przy fsync, różne objawy i nieustalona przyczyna); P2-5 wyjątek
D597 wymaga pełnej widoczności; P2-7 warunkowe asercje v2 w dużym fixture PG;
P2-8 Admin v2 blokuje tworzenie sesji przy braku rodowodu, także TRAIN — operator
musi zawęzić wybór źródeł. Nie osłabiono testów ani kwalifikacji. P2-9 zbyt szeroki
skrót CURRENT_STATE usunięty przy zamknięciu: zamknięte wszystkie P1, P2 pozostają.

Brak operatorowego treningu/GPU/inference/default/margin/importu691, modyfikacji
etykiet, migracji operatora, usług, wdrożenia i push/merge. Aktywacja LAB wyłącznie
w usuniętej jednorazowej bazie testowej. Kolejny TASK-1173 (T4, cały zakres nadal
zatwierdzony). Gotowość kodu nie jest gotowością danych ani dowodem jakości modelu.
