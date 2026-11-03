---
title: Learning refresh feedback and independent reads
status: done
last_updated: 2026-11-03
---

# TASK-1138 — Widoczne odświeżanie stanu uczenia

## Status

`done`

## Goal

Kliknięcie odświeżania natychmiast pokazuje ładowanie i aktualizuje przebiegi bez czekania na wolniejszą gotowość korekt.

## Context

`Learning.refresh` łączy sześć GET przez Promise.all i dopiero po wszystkich wynikach ustawia historię/wybrany przebieg. Przycisk używa wyłącznie busy komend POST, a nie stanu odczytu. Brak potwierdzenia udanego odczytu sprawia, że identyczny wynik wygląda jak brak reakcji. Nie wymaga zmiany backendu.

## Recommended execution

gpt-6.1-sol / high, bez delegowania; Claude Code claude-opus-5-5 / high przed commitem zgodnie z poleceniem operatora.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md` — uczenie z korekt i GET-only wejście/odczyt.
- `ai_docs/architecture/VISION_LAB.md` — correction learning pipeline / jawne apply.
- `ai_docs/architecture/CODE_MAP.md`, `CODE_MAP_SYMBOLS.md`.
- `ai_docs/process/PLAN_STANDARD.md`, `TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`.

## Scope / technical notes

- Osobne refreshing + synchroniczny ref, blokada ponownego kliknięcia i aria-busy, etykieta „Odświeżanie stanu uczenia…”. Stan komend i zapisane polecenia pozostają osobne.
- Niezależne przyjęcie wyników GET. Historia i wybrany przebieg aktualizują się od razu; błąd gotowości/modeli nie usuwa poprawnie odczytanej historii. allSettled zbiera błędy, finally zwalnia loading dla najnowszego odczytu.
- Sekwencja odczytów i generation unieważniają stare odpowiedzi po nowym odczycie, zmianie gry i unmount. Nowszy refresh po komendzie może zastąpić starszy; przycisk nie duplikuje trwającego żądania.
- Ostatni poprawny odczyt ma widoczne potwierdzenie czasu także przy niezmienionym stanie. Nie czyścić istniejących danych podczas odczytu.
- Wyłącznie GET. Bez nowych endpointów, typów klienta, publikacji, treningu, przypisań i restartów usług.

## Expected files

- `apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx`: Learning.refresh/open i przycisk.
- `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs`: regresje odroczonych odpowiedzi.
- ADMIN_APP, VISION_LAB, mapa, task/Outcome i raport audytu.

## Acceptance criteria

- [x] Przycisk natychmiast zmienia etykietę, disabled i aria-busy; podwójne kliknięcie nie tworzy drugiego zestawu odczytów.
- [x] Wolna/błędna gotowość nie blokuje historii i świeżego stanu wybranego przebiegu.
- [x] Po sukcesie widoczne potwierdzenie; po błędzie przycisk ponownie dostępny i dane zachowane.
- [x] Stare odpowiedzi/unmount nie nadpisują nowych odczytów i wyboru; istniejące komendy bez automatycznego replay.
- [x] Testy interakcji, lint/typecheck, build, docs/map i Opus; task-close i osobny commit.

## Test cases / verification

Odroczone Promise: gotowość wolna, lista szybka; ręczne odświeżenie ze zmianą statusu; błąd gotowości i ponowienie; starsza odpowiedź po zmianie wyboru/unmount. Istniejące testy komend/response loss zachowane. Bez nowego testowania sieci neuronowej i bez mutacji API. Komendy ≤120 s, audyt ≤600 s.

## Risks / open questions

Brak pytań blokujących. Zachowanie spinnera obejmuje wszystkie odczyty metadanych; stan przebiegu pojawia się wcześniej. Nie dodajemy równoległego cache ani automatycznego treningu.

## Outcome

Commit: v1.7.535 / `961b6b47bff01fee8dab84284225d886faefb148`.

### Changed

- Refresh ma własny loading, aria-busy i synchroniczną blokadę kliknięcia, niezależne od busy komend. Po sukcesie widoczny czas odczytu.
- Sześć GET przyjmuje wyniki niezależnie; lista, status i raport nie czekają na gotowość korekt. allSettled zbiera błędy bez usuwania poprawnie pobranej historii.
- Read sequence/generation odrzucają spóźnione odpowiedzi po nowym odczycie, zmianie wyboru i unmount. Refresh po komendzie może zastąpić starszy odczyt. Raport tej samej selekcji pozostaje widoczny podczas odczytu.

### Verification results

- Finalne 48 interakcji PASS (22 w panelu uczenia + istniejące kohorty/workspace), 4,03 s: `artifacts/task1138-interactions-final.log`. Dziewięć nowych regresji obejmuje loading/deduplikację, wolną gotowość, błąd i retry, unmount/inną grę i nowszy refresh po jawnej komendzie, opóźniony default, wybór przy błędzie listy i tożsamość raportu oceny.
- Scoped ESLint i Prettier PASS dla dwóch plików. Pełny typecheck Admina `tsc --noEmit -p apps/admin/tsconfig.json` PASS.
- Pełny build Admina PASS: `artifacts/task1138-admin-build-final.log`. Pierwsza próba miała EPERM podczas mkdir w .next; nie zaliczona. Po potwierdzeniu braku pozostawionego builda powtórzenie z właściwymi uprawnieniami Windows exit 0. Nie restartowano serwera.
- docs:check i code-map:check PASS, mapa zregenerowana bez zmiany publicznych symboli/liczby plików. Startup 44532/45000 B przed zamknięciem.
- Rzeczywisty Admin/Mumie A2 w ukrytej własnej karcie: historia PASS i dwa stare błędy widoczne przed końcem gotowości. Po kliknięciu widoczne `Odświeżanie stanu uczenia…`, disabled=true, aria-busy=true. Po zakończeniu disabled=false, aria-busy=false i czas odczytu zmieniony z 08:05:28 na 08:07:36 (Europe/Warsaw). Tylko kliknięcie GET refresh, bez treningu/aktywacji. Weryfikacja DOM, bez zrzutu ekranu.

### Not completed

- Audyt [Opus 5.5/high R1](../../quality/TASK-1138_AUDIT_claude-opus-5-5.md) PASS, brak P0/P1. Wszystkie P2 poprawiono w jednej rundzie: P2-1 loading modelu do odpowiedzi default; P2-2 niezależny odczyt wybranego przebiegu przy błędzie listy; P2-3 czyszczenie raportu przy zmianie evaluationId; P2-4 dwa kliknięcia w jednym act z potwierdzeniem, że DOM nie został jeszcze wyłączony; P2-5 nowy kod stanu przy nieudanej gotowości. Dodatkowe testy i końcowy build rozliczone po poprawkach. Task-close przed commitem.
- Nie scalono ani nie wykonano push bieżącej poprawki; zgoda na wcześniejsze wdrożenie dotyczyła 1136/1137. Nie restartowano usług, nie zmieniono API/defaultu/modelu i nie wykonano treningu.
- Backendowy koszt sprawdzania gotowości pozostaje; ten task usuwa blokowanie widoczności innych odczytów i brak informacji o loading, nie zmienia solvera.

### Definition of Done

- Kryteria loading/feedback, niezależnych odczytów, błędów i spóźnionych odpowiedzi mają regresje. Istniejące response-loss/apply/kohorty zachowane (48 PASS), sprawdzono też działający Admin przez GET.
- Pełny typecheck/build Admina, scoped lint/format i docs/map wykonane. Brak zmian kontraktu API, schematu, modeli i wspólnego komponentu przycisków; SDK/migracje/trening niewymagane. Fizyczny Android nie był częścią odbioru.
- Dokumentacja, audyt, task-close i osobny wersjonowany commit zamykają naprawę kodu; merge/push wymaga akceptacji tego wyniku.

### Documentation updates

ADMIN_APP i VISION_LAB: niezależne odczyty, częściowe błędy, status odświeżania i ochrona spóźnionych odpowiedzi.

### Recommended next task

Akceptacja wyniku i scalenie/push poprawki UI, bez migracji lub wymaganego restartu usług.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1138 — odświeżanie uczenia | gpt-6.1-sol | high | Ograniczona naprawa stanów UI i wyścigów odpowiedzi | Claude Code claude-opus-5-5 / high, przed commitem |
