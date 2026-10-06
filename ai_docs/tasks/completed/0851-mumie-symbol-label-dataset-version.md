---
title: Mumie — versioned symbol-label dataset and existing editor
status: done
last_updated: 2026-10-05
---

# TASK-0851 — nowa wersja zbioru Mumii do etykietowania symboli

## Status

`done` — edytor gotowy; następna interakcja wymaga przypisania symboli przez operatora.

## Goal

Odblokować istniejący edytor symboli dla obecnych, ręcznie zatwierdzonych
geometrii Mumii przez jawny kontrakt wersji zbioru, z zachowaniem starych
danych, ról testowych i pochodzenia zgód.

## Context / authorization

TASK-0850 doszkolił siatki i przygotował 4185 wycinków. API etykiet zwraca
HOLDOUT_POLICY_UNRESOLVED po korektach, które oznaczyły dawny split jako stale.
Użytkownik zlecił pracę do interakcji; wysłano konkretny draft kontraktu i
pytanie o pochodzenie nagrań. Operator zaakceptował kontrakt i potwierdził,
że dwa wskazane foldery pochodzą z różnych nagrań. Deklaracja dotyczy tych
folderów; nie nadaje wszystkim rodzinom statusu verified.

## Dependencies / Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/guides/VISION_LAB_LOCAL.md`
- `ai_docs/delivery/MUMIE_SYMBOL_DATASET_VERSION_20261005.md` — accepted.
- `ai_docs/quality/MUMIE_CURRENT_APPROVALS_20261005.md`

## Recommended execution

`gpt-6.1-sol`, reasoning `high`, własny audyt bez delegacji.

## Scope

Wszystkie kroki TASK-0851 z zaakceptowanego kontraktu. Odczytowy preview,
create-only wersja z pochodzeniem ręcznych zgód i zachowanymi dawnymi rolami,
istniejący słownik/magazyn/API/edytor, jawne procesy oraz kontrola restartu.
Przed implementacją wskazać pliki pionu i domknąć format wersji. Zmiana API
wymaga pełnego istniejącego pionu z generowanym klientem.

## Implementation files and decisions

Nowy moduł `vision_lab/symbol_dataset_version.py` publikuje niezmienną,
checksumowaną referencję etykietowania z pełnym oryginalnym payloadem geometrii
i symboli. Nie tworzy nowego AnnotationStore ani równoległych etykiet.
Opcjonalna konfiguracja istniejącego `SymbolLabelStore`, rendererów i API
sprawdza referencję pod dotychczasowymi blokadami. Stary frozen split pozostaje
stale. Nowa referencja sprawdza jego integralność i zachowane komponenty
ochronne niezależnie od kwalifikacji geometrii. Wszystkie bramki treningu
pozostają aktywne. Zmiana geometrii blokuje wersję i wymaga nowego preview.
Nie zmienia się schema HTTP; lineage decyzji trafia do istniejącego metadata.
Nowe testy `test_vision_lab_symbol_dataset_version.py` oraz trwały launcher
`scripts/vision_lab_symbol_review.ps1` obejmują ten sam pion. Dokumentacja:
requirements/architecture VISION_LAB, guide, D-496, raport jakości.

## Out of scope

Trening i aktywacja symboli, nadawanie verified lub symboli za operatora,
mechanika/wypłaty Super, produkcyjna DB, materializacja plansz, migracje,
shadow, kasowanie starych danych, push/merge.

## Acceptance criteria / verification

- [x] Stare dane, split i runy bez zmian; nowa wersja ma audytowalne pochodzenie.
- [x] Ręczne geometrie i słownik zachowują tożsamości, SHA i pierwotne zgody.
- [x] Dawne części testowe, całe komponenty i historia użycia zachowane.
- [x] 4185 aktualnych komórek jest dostępnych w istniejącym edytorze bez
  zmiany poprawnej siatki i bez automatycznego przypisania symboli.
- [x] Nowa wersja nie odblokowuje trainability ani starego workflow przez
  usunięcie stale lub pominięcie guardów.
- [x] Restart, utracona odpowiedź, retry, korekta geometrii, holdout i
  uszkodzony manifest pokryte testami; domyślne istniejące zachowanie zachowane.
- [x] Właściwe format/lint/types/build, własny audyt DoD, raport i osobny commit.

## Risks / open questions

Referencja zachowuje zgody bez ich ponownego nadania; istniejący rebase
nie jest używany. Rodziny obecnych 31 zdjęć nadal unresolved.
Przypisanie symboli wymaga człowieka. Super wymaga osobnych obserwacji ramki.

## Outcome

Wykonano wszystkie sześć kroków zaakceptowanego planu oraz kryteria powyżej.
Wersja `dab77630f3518604add168c2baeed124dc9c5010d8ea483201a5be8cb77da1fc`:
31 zdjęć, 279 plansz, 4185 pól. Pełne oryginalne lineage i 523 chronione źródła.
Istniejący magazyn/API/edytor; stare sumy i split stale zachowane. Zero nowych
etykiet. Słownik v1 i klasy bez zmian. Dwa foldery to różne nagrania według
operatora; nie nadano verified pozostałym rodzinom.

63 odrębne testy PASS (47 pionu + 16 snapshot/split), dodatkowe powtórzenie
7 testów po limicie publikacji PASS. Ruff format/lint, scoped strict Mypy
6 modułów, OpenAPI check i Next build/TypeScript PASS. Start/Status/Stop,
restart w nowym PowerShell, HTTP pierwszej/ostatniej strony i pełnej planszy,
browser smoke 15 aktywnych wyborów PASS. Własny audyt DoD/plan bez P0–P2.
Raport `ai_docs/quality/MUMIE_SYMBOL_DATASET_VERSION_20261005.md`.

Nie wykonano DB/migracji/materializacji/shadow/treningu/aktywacji/usuwania/
push/merge. Main Mumie ma zero plansz i zdjęć. Brak restartu całego komputera;
uruchomienie i konfiguracja zapisane trwale. Następny krok: etykiety operatora
w `http://127.0.0.1:3102/symbols`; potem osobna kwalifikacja zbioru symboli.
Osobny commit `v1.7.197` na `feat/grid-engine-v3`; hash dopisany po commicie.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0851 | gpt-6.1-sol | high | Trwały kontrakt wersji danych, lineage zgód i zachowanie części testowych. | Własny audyt integralności, regresji i nowego procesu; bez delegacji. |
