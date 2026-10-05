---
title: Mumie — versioned symbol-label dataset and existing editor
status: planned
last_updated: 2026-10-05
---

# TASK-0851 — nowa wersja zbioru Mumii do etykietowania symboli

## Status

`planned` — kontrakt draft oczekuje na decyzję operatora; nie rozpoczęto kodowania.

## Goal

Odblokować istniejący edytor symboli dla obecnych, ręcznie zatwierdzonych
geometrii Mumii przez jawny kontrakt wersji zbioru, z zachowaniem starych
danych, ról testowych i pochodzenia zgód.

## Context / authorization

TASK-0850 doszkolił siatki i przygotował 4185 wycinków. API etykiet zwraca
HOLDOUT_POLICY_UNRESOLVED po korektach, które oznaczyły dawny split jako stale.
Użytkownik zlecił pracę do interakcji; wysłano konkretny draft kontraktu i
pytanie o pochodzenie nagrań. Akceptacja draftu nie jest jeszcze odebrana.

## Dependencies / Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/guides/VISION_LAB_LOCAL.md`
- `ai_docs/delivery/MUMIE_SYMBOL_DATASET_VERSION_20261005.md` — zaakceptować przed kodem.
- `ai_docs/quality/MUMIE_CURRENT_APPROVALS_20261005.md`

## Recommended execution

`gpt-6.1-sol`, reasoning `high`, własny audyt bez delegacji.

## Scope

Wszystkie kroki TASK-0851 z zaakceptowanego kontraktu. Odczytowy preview,
create-only wersja z pochodzeniem ręcznych zgód i zachowanymi dawnymi rolami,
istniejący słownik/magazyn/API/edytor, jawne procesy oraz kontrola restartu.
Przed implementacją wskazać pliki pionu i domknąć format wersji. Zmiana API
wymaga pełnego istniejącego pionu z generowanym klientem.

## Out of scope

Trening i aktywacja symboli, nadawanie verified lub symboli za operatora,
mechanika/wypłaty Super, produkcyjna DB, materializacja plansz, migracje,
shadow, kasowanie starych danych, push/merge.

## Acceptance criteria / verification

- [ ] Stare dane, split i runy bez zmian; nowa wersja ma audytowalne pochodzenie.
- [ ] Ręczne geometrie i słownik zachowują tożsamości, SHA i pierwotne zgody.
- [ ] Dawne części testowe, całe komponenty i historia użycia zachowane.
- [ ] 4185 aktualnych komórek jest dostępnych w istniejącym edytorze bez
  zmiany poprawnej siatki i bez automatycznego przypisania symboli.
- [ ] Nowa wersja nie odblokowuje trainability ani starego workflow przez
  usunięcie stale lub pominięcie guardów.
- [ ] Restart, utracona odpowiedź, retry, korekta geometrii, holdout i
  uszkodzony manifest pokryte testami; domyślne istniejące zachowanie zachowane.
- [ ] Właściwe format/lint/types/build, własny audyt DoD, raport i osobny commit.

## Risks / open questions

Nowa wersja wymaga jawnego kontraktu przeniesienia zgód; istniejący rebase
nie obsługuje obecnego payloadu. Pochodzenie filmów nadal unresolved.
Przypisanie symboli wymaga człowieka. Super wymaga osobnych obserwacji ramki.

## Outcome

Nie wykonano. Oczekuje na akceptację kontraktu.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0851 | gpt-6.1-sol | high | Trwały kontrakt wersji danych, lineage zgód i zachowanie części testowych. | Własny audyt integralności, regresji i nowego procesu; bez delegacji. |
