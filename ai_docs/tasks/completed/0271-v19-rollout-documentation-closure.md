---
title: TASK-0271 v19 rollout documentation closure
status: done
release: "0.7"
last_updated: 2026-08-23
---

# TASK-0271 — Dokumentacja, decyzje i zamknięcie rollout'u v19/v20

## Goal

Zsynchronizować wymagania, architekturę, stan projektu, decyzje i instrukcje
operatorskie z faktycznie wdrożonym oraz zweryfikowanym zachowaniem TASK 1–9.

## Context

- Automatyczna geometria v19 spełniła bramki jakości trafień, ale osiągnęła
  `93,78%` pokrycia przy wymaganym minimum `98%`.
- Pełny adapter v20 został wdrożony na jawne polecenie właściciela wyłącznie
  jako staging-local opt-in. Historyczny v18 pozostał domyślny.
- Niewiarygodna geometria v20 tworzy trwały deferred bez cropów i inferencji;
  Reviewer pozwala rozwiązać go ręcznie na końcu.
- Kandydat modelu symboli wytrenowany na cropach v19 poprawił metryki, ale
  został kontrolowanie odrzucony po jednym błędzie z confidence co najmniej
  `0,99`. Aktywny model nie został zmieniony.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/quality/GRID_CROPPING_VS_SYMBOL_MODEL_DIAGNOSIS.md`
- `ai_docs/quality/BOARD_CELL_GEOMETRY_V19_SHADOW_BENCHMARK.md`
- `ai_docs/quality/V19_SYMBOL_RESIDUAL_COHORT.md`
- `ai_docs/quality/V19_SYMBOL_MODEL_CANDIDATE.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/0256-deferred-self-improving-page-geometry.md`

## Scope

- uzupełnienie diagnozy końcowymi wynikami TASK 1–9,
- zapisanie zaakceptowanej architektury aktywnego v18, opt-in v20 i deferred,
- opisanie procedury operatora oraz rollbacku,
- zapisanie formalnej decyzji o wyniku rollout'u i odrzuconym kandydacie,
- aktualizacja `CURRENT_STATE.md`, outcome tasków i końcowego raportu,
- zamknięcie zrealizowanych tasków dopiero po przejściu kontroli dokumentacji.

## Out of scope

- kod algorytmiczny, API, UI, baza i migracje,
- kolejny trening, zmiana progów lub ponowna ocena modelu,
- aktywacja odrzuconego kandydata,
- zmiana domyślnego pipeline'u z v18 na v20,
- uruchomienie importu lub masowego przeliczenia danych użytkownika.

## Acceptance criteria

- [x] Dokumentacja jednoznacznie opisuje v18 jako tryb domyślny i v20 jako
      jawny, staging-local opt-in.
- [x] Dokumentacja opisuje 15 cropów albo trwały deferred bez inferencji oraz
      ręczne rozwiązanie deferred w istniejącej kolejce Reviewera.
- [x] Finalny raport odwołuje się do niezmiennych raportów i checksum TASK 1,
      TASK 2, TASK 8 i TASK 9.
- [x] Wynik `93,78% < 98%`, jawny wyjątek właściciela i zakaz automatycznego
      rollout'u są zapisane bez sprzeczności.
- [x] Odrzucony kandydat i niezmieniony aktywny fingerprint modelu są zapisane
      w wymaganiach, architekturze, Decision Log i stanie projektu.
- [x] Instrukcja operatorska opisuje wybór v18/v20, obsługę deferred i rollback.
- [x] Wcześniejsze decyzje pozostają widoczne; żadna nie jest usunięta.
- [x] Kontrola linków, wersji, formatowania i diffu przechodzi dla zmienionych
      dokumentów.

## Outcome

- Dodano końcowy raport rollout'u z checksumami TASK 1, 2, 8 i 9, aktywnym
  fingerprintem, opisem v18/v20, deferred, rollbackiem oraz ograniczeniami.
- Wymagania importu i ulepszania modelu oraz obie architektury opisują
  faktycznie aktywny stan: v18 domyślny, v20 opt-in, kandydat `rejected`.
- D-214 i D-215 zachowują wcześniejsze decyzje i formalizują końcowy wynik bez
  obniżenia bramek.
- Instrukcja operatorska opisuje wybór trybu, końcową korektę deferred oraz
  rollback przez utworzenie nowego joba v18.
- Targetowany Prettier zmienionych dokumentów przeszedł. Kontrola linków,
  checksum/fingerprintów i `git diff --check` przeszła.
- `npm run quality` został uruchomiony i zatrzymał się na znanym driftcie
  Prettiera w 32 plikach spoza TASK 10. `openapi:check` oraz kontrola kandydata
  nie zwróciły wyniku przez 90 sekund i zostały przerwane; TASK 10 nie zmienia
  API ani artefaktów modelu. Niezwiązany `apps/admin/next-env.d.ts` pozostaje
  poza commitem.
