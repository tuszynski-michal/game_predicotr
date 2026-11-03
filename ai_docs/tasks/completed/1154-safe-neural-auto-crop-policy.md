---
title: Bezpieczna automatyczna akceptacja siatek
status: done
last_updated: 2026-11-03
---

# TASK-1154 — Bezpieczna automatyczna akceptacja siatek

## Status

`done`

## Goal

Nowe operacje blokują automatyczne cropy i akceptację błędnego dopasowania, zachowując interpretację starych przypiętych polityk.

## Context

T0 zaakceptowanego planu pełnych plansz. Opus 5.5/high zakończył focused review R2 wynikiem PASS; P2 dotyczą pełnej inwentaryzacji wersji oraz sprawdzenia zapisanych przyczyn dla 462205.

## Dependencies / entry conditions

- Plan R2 PASS; numery TASK-1154–1160 wolne na wszystkich lokalnych gałęziach i aktywnych worktree, sprawdzone 2026-11-03. Rezerwacja T0–T6 w tej kolejności.
- Praca w `codex/full-board-detection`; bez usług, operator DB writes, migracji, treningu i GPU.
- TASK-1153 nie jest zależnością T0. Został scalony przez roota za zgodą operatora; baza tej gałęzi to `448f75e7`, co spełnia warunek T5.

## Recommended execution

`gpt-6-astra` / `high`; zgodność API/workera i niezmiennej historii. Niezależny audyt `claude-opus-5-5` / `high` przed commitem. Otwarte P0/P1 po jednej rundzie poprawek zatrzymują zadanie.

## Relevant docs

- `AGENTS.md`
- `ai_docs/delivery/FULL_BOARD_DETECTION_PLAN_20261103.md`
- `ai_docs/quality/FULL_BOARD_PLAN_AUDIT_claude-opus-5-5_R2.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md` — D-550 i D-523.
- `ai_docs/requirements/VISION_LAB.md` — ludzka prawda i propozycje V3-D.
- `ai_docs/architecture/VISION_LAB.md` — propozycje i niezmienne operacje.
- `ai_docs/architecture/API_CONTRACT.md` — D-523, wybrana reinferencja D-551.
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-523--operational-neural-crops-and-recoverable-symbol-verification`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-550--akceptacja-silnika-v3-i-statusowy-backfill`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-551--propozycje-dla-błędnej-siatki-v3`

## Scope

- Nowa `neural-auto-crop-v2` i odpowiadająca `v3-engine-acceptance-v2`; wspólna czysta kwalifikacja dla API i workera.
- Blokady FIT_FAILED/FIT_OUTLIERS, niepełne/niejednoznaczne przypisanie, nieprawidłowe 24 węzły/15 pól, brak rzeczywistych pikseli i nieobsługiwany układ.
- Jawna obsługa v1/v2 we wszystkich porównaniach polityk, nowych pinach/fingerprintach, serializacji, projekcji i guardach właścicieli.
- Nowe prepare używa v2; replay/restart zachowuje własną v1 lub v2. Dotychczasowe pole `acceptancePolicy` ujawnia wersję reinferencji; import ma zapisany pin wykonania. Brak automatycznego retrofit.

## Out of scope

Trening, pomiar jakości modelu, backfill, zmiana ręcznych zatwierdzeń, nowe układy/model capabilities T2, kalibracja T4, zmiana edytora, merge/push i wdrożenie.

## Acceptance criteria

- [x] FIT_FAILED z geometrią fallback oraz FIT_OUTLIERS nie daje automatic w v2.
- [x] API ponownie kwalifikuje dowody, ignorując deklarację automatic jako dowód.
- [x] Niepełne przypisanie, nieprawidłowa geometria, brak pikseli i nieobsługiwany układ blokują nowy automat.
- [x] v1 zachowuje decyzję, payload, fingerprint i checkpoint przy wznowieniu; nieznana wersja blokuje wykonanie.
- [x] Nowa polityka zachowuje blokady sekwencji, pochodzenie rewizji i ochronę ręcznych decyzji.
- [x] Zapisany kandydat 462205 ma potwierdzone przyczyny; regresja odtwarza jego blokadę bez nowej inferencji.
- [x] Scoped testy, lint, typecheck, pełny pion zmian kontraktu, docs i mapa są sprawdzone; audyt przed commitem rozliczony.

## Technical notes

Nowe wersje zmieniają kwalifikację, nie reinterpretują istniejących v1. `V3_ENGINE_ACCEPTANCE_POLICY` v2 jednoznacznie wiąże crop v2; v1 wiąże crop v1. Reinferencja już zapisuje acceptancePolicy w immutable operation/job/manifest/scopeSignature, więc używamy tego pinu zamiast dodawać równoległy mechanizm. Import zachowuje oba przypięte pola. Ręczne zatwierdzenia oraz historyczny statusowy backfill nie są aktualizowane.

Wspólna funkcja ocenia istniejącą topologię 3 × 5 oraz dane wiązania i wykrycia. Pełna deklaracja możliwości pakietu i kontrola strony przed inferencją pozostaje T2. Sygnał nieobsługiwanego układu blokuje v2. Nie utożsamiamy `expectedLayoutCount` (maksymalna sekwencja gry) z liczbą plansz na zdjęciu.

W v2 geometria przechowuje mały dowód kwalifikacji (bez bitmap); API porównuje go z przypiętą propozycją i przelicza decyzję. Źródło/crop musi nadal przejść obecny renderer z kontrolą rzeczywistych pikseli. Nowa funkcja nie zastępuje kontroli właściciela, rewizji, checksumu ani zgłoszenia `grid_issue`.

## Expected files

- `services/api/src/game_predictor_api/domain/neural_crop_policy.py`: nowe wersje i wspólna kwalifikacja; `full_neural_prediction_geometry`.
- `domain/v3_engine_acceptance.py`: `qualify_v3_engine_acceptance`, zgodność pinu.
- `storage/v3_engine_acceptance_repository.py`, `grid_engine_acceptance_repository.py`, `lateral_reprocess_protection.py`, `job_repository.py`: jawne wersje i zachowana ochrona.
- `storage/grid_reinference.py`, `application/grid_reinference.py`: nowy pin, zgodne historyczne odczyty.
- `schemas/jobs.py`: zamknięta lista wersji payloadu, generowane OpenAPI/klient jeśli publikowane.
- `services/worker/src/game_predictor_worker/images/neural_pending_geometry.py`, `grid_reinference_handler.py`, `production_workflow.py`, `pipeline_store.py`: kwalifikacja i przenoszenie pinu.
- Testy tych modułów, dokumentacja D-584, mapa kodu, raport audytu i task.

## Test cases

- To samo wykrycie FIT_FAILED/FIT_OUTLIERS: v1 zachowuje dawną decyzję, v2 review; API i worker identyczne.
- Empty/partial visibility, zduplikowane/missing przypisanie, zły układ, niepoprawne węzły i crop bez pikseli: v2 review.
- Sfałszowane automatic lub dowód innego wykrycia: API odmawia.
- Serializacja i nowy proces odtwarzają wersję/checkpoint; utracona odpowiedź prepare/command nie tworzy nowej operacji.
- Stary i nowy pin nie pomijają sequence lock ani ochrony human owner.
- 462205: zapisane węzły i przyczyny, bez twierdzenia o pełnym GT.

## Verification

Planowane, z root worktree; skończone polecenia przez wrapper z timeout 120 s, pojedynczy audyt 480 s:

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_neural_crop_policy.py services/api/tests/test_v3_engine_acceptance.py services/worker/tests/test_grid_reinference_handler.py -q
.venv\Scripts\python.exe -m ruff check <zmienione pliki Python>
.venv\Scripts\python.exe -m mypy <zmienione moduły>
npm run openapi:generate
npm run docs:check
npm run code-map:check
```

Dodatkowe istniejące testy request/replay i izolowane PostgreSQL dobierane do zmienionego pionu. Baza operatora wyłącznie do odczytu; brak migracji i przebiegów modelu. Brak wykonania jest raportowany, nie zastępowany deklaracją PASS.

## Risks / open questions

- T0 nie wykrywa każdego pominiętego rzędu: poprawna krata bez kodu błędu wymaga T4.
- P2 planu poza T0: diagnostyczne poza VALIDATION-B/REGRESSION, jawna definicja błędu GT i baza po T0 w T4/T6.
- Brak blokujących pytań produktowych po focused review PASS.

## Outcome

Commit: v1.7.558 (hash dopisuje kolejny commit).

### Changed

- Wspólna kwalifikacja `neural-auto-crop-v2` i zgodna akceptacja silnika v2; historyczne v1 pozostają odczytywane i wykonywane według dawnego kontraktu.
- API ponownie sprawdza dowody przed automatic write, worker zachowuje niepewne propozycje do ręcznej korekty. Nowe wersje uczestniczą w fingerprintach, źródłach, checkpointach i blokadach właścicieli.
- Dokładny zapis 462205 w regresji; bez nowej inferencji i bez deklaracji GT.

### Verification results

- 87 testów Python PASS po rozliczeniu P2 (pierwotnie 84); 13 izolowanych PostgreSQL PASS; 4 request testy SDK PASS. Po audycie dodano dwa przypadki serializacji FIT i jeden wariant odrzucenia rozbieżnego dowodu.
- OpenAPI/generated client, client typecheck, Ruff, docs:check i code-map:check PASS.
- Mypy 14 zmienionych modułów z zależnościami: sześć błędów zastanych, identycznych na HEAD przez shadow-file; zero nowych. Szczegóły i ograniczenia: `ai_docs/quality/TASK-1154_VERIFICATION.md`.
- Testy head-schema otrzymały bieżący, nadal ograniczony budżet przygotowania partycji zamiast starej liczby tabel v19. Własne bazy testowe używane przez moduły zostały posprzątane przez fixture; baza operatora bez zmian.
- Audyt implementacji `claude-opus-5-5/high`: PASS, runda 1, bez P0/P1; raport `ai_docs/quality/TASK-1154_AUDIT_claude-opus-5-5.md`. Pięć P2 rozliczono w jednej rundzie: dokumentacja projekcji i granicy pikseli, wspólna stała limitu, test serializacji obu FIT oraz test odrzucenia rozbieżnego dowodu przed pierwszym zapisem. Fail-closed przy błędzie integralności pozostaje jawną awarią joba, nie pozornym review; istniejący test PostgreSQL potwierdza rollback i zero zapisów.
- Historyczne odmowy dostępu rozwiązano nową konkretną zgodą operatora. Pierwsza uruchomiona próba audytu przekroczyła 480 s bez stdout/stderr; druga, instrumentowana próba tej samej rundy na scoped pakiecie 100 376 B zakończyła się PASS. Nie było dwóch ukończonych rund review. Historia: `ai_docs/quality/TASK-1154_AUDIT_BLOCKED.md`.

### Not completed

- Nie wykonano treningu, inferencji modelu, wdrożenia, aktywacji, zmian danych operatora, restartów, merge ani push.
- Sześć zastanych błędów mypy pozostaje poza zakresem; pełna globalna bramka jakości repo nie była uruchamiana.

### Definition of Done / plan T0

- Funkcjonalność i zakres: wszystkie siedem kryteriów T0 spełnione; brak treningu ani rozszerzenia T1–T6.
- Kod i trwałość: czysta wspólna kwalifikacja, v1/v2 i piny, restart/utrata odpowiedzi/rollback objęte testami. P2 po audycie zmieniają dokumentację, testy i użycie istniejącej stałej o tej samej wartości.
- Dane: bez zmiany schematu ani migracji operatora; ochrona sekwencji i ręcznych decyzji zachowana.
- Kontrakt: backend/OpenAPI/generowane typy/wrapper/request test spójne. UI niezmienione, kryteria UX nie dotyczą.
- Narzędzia: właściwe testy, Ruff i typy klienta PASS; moduł zmieniony po audycie także mypy PASS. Sześć wcześniejszych błędów mypy innych modułów opisano jako ograniczenie, bez fikcyjnego globalnego PASS.
- Dokumentacja: D-584, wymagania, kontrakt, mapa, raporty, plan i Outcome aktualne; zamknięcie oraz zapis hasha wykonuje task-close.

### Documentation updates

- Plan T0–T6 i focused review R2 PASS, rezerwacja 1154–1160, D-584, wymagania importu, kontrakt API, mapa kodu, raport weryfikacji oraz wskaźnik CURRENT_STATE.

### Recommended next task

TASK-1155 / T1: odtworzenie faktycznego wejścia sieci i raport gotowości danych. Przykłady diagnostyczne pozostają poza VALIDATION-B i REGRESSION.
