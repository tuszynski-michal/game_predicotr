---
title: TASK-0124 Test dataset completeness, gaps and source quality selection
status: done
last_updated: 2026-07-31
---

# TASK-0124 — Test dataset completeness, gaps and source quality selection

## Status

`done`

## Goal

Dodać produkcyjną kontrolę kompletności testowego datasetu obrazowego względem
konfiguracji gry oraz deterministyczny wybór najlepszego źródła dla numeru
sekwencji, z możliwością jawnej korekty numeru i ręcznego override źródła.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` — D-107, D-108 i D-109
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- dodatnie `games.expected_layout_count`, domyślnie `500 000`, edytowalne dla
  testowej gry,
- zamrożone `dataset_versions.expected_layout_count`, kopiowane przy tworzeniu
  stagingu,
- raport kompletności względem zakresu `1..expected_layout_count`, z bounded
  listą brakujących numerów,
- walidacja ręcznego `sequence_number` bez nadpisania surowego wyniku OCR,
- deterministyczny ranking wielu zaakceptowanych źródeł tej samej sekwencji na
  podstawie jawnych metryk jakości,
- ręczny override wybranego źródła z zachowaniem automatycznego rankingu i
  provenance,
- widok Admina pokazujący cel, kompletność, luki i kandydatów źródłowych.

## Out of scope

- syntetyczne uzupełnianie brakujących layoutów,
- bootstrap katalogu symboli i ręczne mapowanie klas — TASK-0125,
- zmiana modelu OCR, croppera lub klasyfikatora,
- masowa publikacja pełnych 500 000 layoutów,
- usuwanie oryginałów albo historycznych decyzji Reviewera.

## Assumptions

- wynik OCR w `recognized_boards.sequence_number` pozostaje niezmienną sugestią;
  numer domenowy pochodzi z najnowszej zaakceptowanej decyzji review,
- kandydatem źródłowym jest plansza zaakceptowana lub poprawiona, zawierająca
  komplet 15 komórek i dodatni numer domenowy,
- ranking jest stabilny: ręczny override, następnie kompletność decyzji,
  `board_confidence`, `sequence_confidence`, rozdzielczość źródła i UUID,
- raport nie materializuje 500 000 pustych rekordów; zwraca dokładne liczniki i
  maksymalnie 100 pierwszych brakujących numerów.

## Acceptance criteria

- [x] gra przechowuje i zwraca dodatni `expected_layout_count`,
- [x] utworzenie stagingu zamraża oczekiwanie gry w wersji datasetu,
- [x] publikacja blokuje dataset, którego `layout_count` nie odpowiada
  zamrożonemu oczekiwaniu,
- [x] raport pokazuje dokładną liczbę unikalnych sekwencji, luk, duplikatów i
  bounded próbkę brakujących numerów,
- [x] ręczna korekta numeru jest walidowana względem celu gry i nie zmienia OCR,
- [x] wiele źródeł jednej sekwencji ma stabilny automatyczny wybór,
- [x] operator może wskazać inne źródło i cofnąć override,
- [x] Admin pokazuje kompletność i provenance wybranego źródła,
- [x] migracja, testy API/domeny, klient OpenAPI i testy Admina przechodzą.

## Outcome

Dodano konfigurowalny cel liczby layoutów gry i jego zamrożenie w wersji
datasetu. Raport kompletności liczy zaakceptowane plansze, unikalne numery,
luki, duplikaty i wartości poza zakresem bez materializowania pustych rekordów;
lista braków jest ograniczona do pierwszych 100 numerów.

Dla wielu zaakceptowanych źródeł tej samej sekwencji backend zwraca stabilny
ranking oparty o confidence planszy i OCR oraz rozdzielczość. Operator może
zapisać albo wycofać append-only ręczny override. Admin udostępnia konfigurację
celu, raport kompletności i inspektor kandydatów wraz z provenance.

Migracja `0022_dataset_quality` została zastosowana. Zmiany zweryfikowano przez
65 testów backendu, 20 testów klienta Admin API, 99 testów Admina, Ruff,
ograniczony typecheck 13 zmienionych modułów Python, typecheck TypeScript, lint,
kontrolę wygenerowanego OpenAPI i produkcyjny build Admina.
