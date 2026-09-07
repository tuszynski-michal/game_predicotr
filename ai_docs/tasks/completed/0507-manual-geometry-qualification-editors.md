---
title: Spójna korekta i nawigacja w edytorach
status: done
last_updated: 2026-09-07
---

# TASK-0507 — Spójna korekta i nawigacja w edytorach

## Status

`done`

## Goal

Spójna korekta i nawigacja w edytorach, według zaakceptowanego planu „Niepełne plansze i wykluczanie niepewnej geometrii z uczenia”.

## Context

Operator zlecił całą serię 0505–0509 wraz z audytami; bez zatrzymywania po każdym tasku.

## Dependencies / entry conditions

TASK-0506; jego implementacja oraz wymagany audyt muszą być odebrane. Obce zmiany i pozostałości TASK-0504 pozostają poza commitem. Bez restartów usług i operacji na danych operatora.

## Recommended execution

`gpt-5.6-sol high`, zgodnie z końcową tabelą zaakceptowanego planu. Wymagany niezależny audyt `gpt-6-astra high` przed zamknięciem: geometria, trwałość lub integracja właściwa dla zakresu. Eskalacja przy konflikcie kontraktu lub bezpieczeństwa danych.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md` — ręczna kompletność i kwalifikacja
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/DECISION_LOG.md` — D-371

## Scope

- Zwarte kontrolki pod zdjęciem: Niepełna plansza oraz Nie używaj do uczenia geometrii; partial wymusza wykluczenie.
- Szary hatch niedostępnych pól i licznik dostępnych. Edycja wszystkich aktywnych slotów, wspólny jawny zapis.
- Następna/Poprzednia tylko nawigują, nie wywołują zapisu API ani preflightu.
- Trwały lokalny szkic: gra, import/preflight, SHA źródła, bazowa rewizja, quady i oznaczenia, bez obrazów. Restore po refresh; nowsza rewizja zgłasza konflikt.
- Reset odtwarza bazę wraz z oznaczeniami, nie kasuje zapisanej decyzji. Istniejący workflow innych konsumentów wspólnych komponentów pozostaje bez zmian.

## Out of scope

Detektor produkcyjny v0.10, OCR, lokalny auto-crop, aktywne joby, dane operatora, cleanup. Warunkowa prośba o eksperymentalny v0.10.4 wymaga osobnej analizy po odbiorze tej serii.

## Acceptance criteria

- [x] Zwarte kontrolki pod zdjęciem: Niepełna plansza oraz Nie używaj do uczenia geometrii; partial wymusza wykluczenie.
- [x] Szary hatch niedostępnych pól i licznik dostępnych. Edycja wszystkich aktywnych slotów, wspólny jawny zapis.
- [x] Następna/Poprzednia tylko nawigują, nie wywołują zapisu API ani preflightu.
- [x] Trwały lokalny szkic: gra, import/preflight, SHA źródła, bazowa rewizja, quady i oznaczenia, bez obrazów. Restore po refresh; nowsza rewizja zgłasza konflikt.
- [x] Reset odtwarza bazę wraz z oznaczeniami, nie kasuje zapisanej decyzji. Istniejący workflow innych konsumentów wspólnych komponentów pozostaje bez zmian.
- [x] Testy i niezależny audyt zakresu oraz zgodność historyczna.

## Technical notes

Kanoniczny właściciel kwalifikacji to snapshot rewizji źródła; nullable projekcje nie są alternatywną prawdą. Nowe oznaczenia nie mogą zniknąć przez historyczny zapis. Żaden szablon nie tworzy fikcyjnego cropa ani zatwierdzenia.

## Expected files

- Istniejący: `apps/admin/src/features/imports/page-geometry-correction-panel.tsx`.
- Istniejący: `apps/admin/src/features/imports/geometry-guard-resolution-panel.tsx`.
- Istniejący: `apps/reviewer/src/features/grid-reviews`.

## Test cases

Każde kryterium zakresu otrzymuje test zachowania, w tym przypadki negatywne i zgodność historyczna. Nie osłabiać testów dla zielonego wyniku.

## Verification

Komendy ustalić ze skryptów repo po identyfikacji zmienionych modułów; każdy skończony krok z timeoutem do 120 s. Znane buildy wymagają jawnego dłuższego limitu. Najpierw testy pionu, potem typy/lint i szersza kontrola. Poniższe wyniki nie są jeszcze zaliczone.

## Risks / open questions

Samo zapisanie wykluczenia nie odtrenowuje aktywnego profilu. Bezpieczne read-only fixture’y nie dowodzą odbioru UI na urządzeniu operatora.

## Outcome

Wdrożono trzy edytory, wspólną projekcyjną maskę komórek i lokalne szkice
bez obrazów. Zapis page/guard ma opcjonalne CAS i idempotentny retry; starsze
formularze pełnych plansz zachowują dotychczasowy kontrakt. Nowe kwalifikacje
nadal są chronione bramkami konsumentów do TASK-0508 — nie deklarujemy
działającego końcowego importu partial ani aktywacji v0.10.4.

Odbiór: 6 testów interakcji React/JSDOM, 16 testów helperów/draftów, 18 API,
53 wygenerowanego klienta; typecheck Admina, Reviewera i core, scoped ESLint,
Ruff oraz OpenAPI passed. Formatowano wyłącznie zmienione pliki. Mypy
uruchomiony na 6 zmienionych modułach wskazuje dwa wcześniej obecne błędy
(redundant cast guard, nullable board preview) i importy workera bez py.typed;
nie raportujemy pełnego green ani nie rozszerzamy poprawki o te zależności.

Niezależny audyt `gpt-6-astra high` wykrył i zweryfikował poprawki: izolacja
scope, reset przed załadowaniem kolejnego obrazu, dirty samych flag, reset
legacy, CAS i cleanup innej karty/nowszej rewizji. Po audycie udostępniono
również zwykły reset dirty guard, z testem zachowania. Brak otwartych
blockerów integralności tego pionu. Odbiór wizualny na urządzeniu pozostaje
niepotwierdzony; pełne buildy i przepływy konsumentów należą do 0508–0509.

Doprecyzowanie użytkownika utrwalono w wymaganiach i D-372: brak boków może
być niepełnością źródła; ucięta góra/dół wymaga poprawy upstream cropa.
Bez migracji, restartów, cleanupu lub zmian danych operatora. Następny task:
0508 — konsumenci kwalifikacji, trening/kotwice i atomowe rewizje partial.
