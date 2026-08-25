---
title: TASK-0268 controlled v20 import opt-in
status: done
release: "0.7"
last_updated: 2026-08-23
---

# TASK-0268 — Kontrolowane uruchomienie importu v20 z Admina

## Goal

Udostępnić właścicielowi jawny, audytowalny wybór istniejącego
`board-cell-processing-v20-verified-v19-v1` podczas uruchamiania gotowego
browser stagingu, bez zmiany bezpiecznego domyślnego v18 i bez obchodzenia
niezaliczonej bramki automatycznego rollout.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/DECISION_LOG.md` — D-212 i D-213
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/quality/BOARD_CELL_GEOMETRY_V19_SHADOW_BENCHMARK.md`
- `ai_docs/tasks/completed/0265-board-cell-processing-v20-worker-adapter.md`
- `ai_docs/tasks/completed/0266-manual-deferred-board-cell-resolution.md`
- `ai_docs/tasks/completed/0267-deferred-board-cell-geometry-reviewer-ui.md`

## Confirmed constraint

Cross-staging benchmark osiągnął `93,78%`, a nie wymagane `98%`. TASK 7 nie
może ustawić v20 jako domyślnego ani zmienić bramki. Realizuje wyłącznie jawny
opt-in operatora; bez wyboru pozostaje `historical_v18`.

## Scope

- użyć generowanego typu API dla dwóch dozwolonych trybów,
- pokazać wybór trybu dopiero dla aktywnego, gotowego stagingu z raportem,
- pozostawić `historical_v18` jako domyślny przy każdym nowym stagingu,
- wymagać dodatkowego jawnego potwierdzenia przed uruchomieniem
  `verified_v19`,
- opisać wersję v20, wynik przypiętego benchmarku, fail-closed deferred i brak
  fallbacku do v18,
- wysłać wybrany `boardCellProcessingMode` w checksum-bound komendzie startu,
- potwierdzić, że zwrócony job ma snapshot zgodny z wybranym trybem,
- pokazać w komunikacie po starcie faktycznie przypięty tryb.

## Out of scope

- zmiana domyślnej wartości backendu albo automatyczna aktywacja v20,
- obniżenie progu `98%`, zmiana estymatora/croppera lub benchmarku,
- uruchomienie rzeczywistego importu danych użytkownika,
- trening, auto-akceptacja, backfill i masowe przeliczenie,
- zmiana istniejących jobów i zatwierdzonych plansz,
- zmiana kontraktu HTTP, OpenAPI lub bazy.

## Invariants

- brak interakcji operatora zawsze uruchamia historyczny v18,
- v20 wymaga osobnego świadomego potwierdzenia dla bieżącego stagingu,
- zmiana stagingu albo trybu unieważnia potwierdzenie v20,
- v20 nadal daje 15 cropów v19 albo trwały deferred bez inferencji,
- wysoki confidence modelu nie zastępuje bramki geometrii,
- human-wins, `seq_*`, checksumy i snapshot modelu pozostają niezmienne,
- idempotentny start tego samego stagingu nie może po cichu zwrócić joba w
  innym trybie.

## Acceptance criteria

- [x] Domyślnie wybrany jest `historical_v18`, a przycisk startu działa bez
      dodatkowego potwierdzenia.
- [x] `verified_v19` pokazuje ryzyko i blokuje start do jawnego potwierdzenia.
- [x] Zmiana trybu lub stagingu kasuje potwierdzenie.
- [x] Komenda startu zawsze zawiera dokładnie wybrany
      `boardCellProcessingMode`.
- [x] Odpowiedź z niezgodnym snapshotem nie jest prezentowana jako sukces.
- [x] UI i komunikat końcowy jednoznacznie pokazują v18 albo v20.
- [x] Testy Admina i klienta, lint, typecheck, build oraz OpenAPI przechodzą.

## Outcome

Admin pokazuje selektor dopiero dla aktywnego gotowego stagingu z raportem.
Każdy nowy staging zaczyna w v18; wybór v20 pokazuje wynik benchmarku, brak
fallbacku oraz deferred i wymaga osobnego checkboxa. Wybrany tryb przechodzi
przez typ generowanego klienta do checksum-bound startu, a zwrócony job jest
sprawdzany względem snapshotu przed pokazaniem sukcesu.

Walidacja: Admin `243/243`, klient Admin API `40/40`, typecheck i lint obu
workspace'ów, build Admina, formatowanie zmienionych plików oraz OpenAPI
przeszły. Dwa wcześniejsze ostrzeżenia `<img>` w Adminie pozostają poza
zakresem. Nie uruchamiano rzeczywistego importu ani nie zmieniano domyślnego
v18, bramki `98%`, backendu, bazy i OpenAPI.
