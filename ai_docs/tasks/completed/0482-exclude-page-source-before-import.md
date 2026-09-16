---
title: TASK-0482 — Wykluczenie błędnie przyciętego źródła przed importem
status: done
last_updated: 2026-09-06
---

# TASK-0482 — Wykluczenie błędnie przyciętego źródła przed importem

## Goal

Pozwolić operatorowi w `Korekta geometrii strony` trwale wykluczyć pojedynczy
JPEG z bieżącego browser stagingu, raportu preflightu i nowego importu, bez
mutowania niezmiennego manifestu stagingu ani historycznych jobów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`

## Scope

- staging-scoped, checksum-bound i append-only decyzja wykluczenia źródła;
- przycisk `Usuń z importu` z jawnym potwierdzeniem w korekcie geometrii;
- natychmiastowe usunięcie źródła z bieżącej kolejki korekty;
- przypięcie snapshotu wykluczeń do nowego joba importu i jego fingerprintu;
- pominięcie wykluczonego JPEG-a przy tworzeniu managed originals, geometrii,
  cropów oraz inferencji symboli;
- zgodne rozszerzenie backendu, OpenAPI, klienta i testów UI/API/workera.

## Out of scope

- fizyczne kasowanie pliku z niezmiennego browser stagingu;
- usuwanie danych istniejącego lub historycznego importu;
- zastępowanie już kanonicznej planszy innym źródłem (TASK-0305);
- automatyczne poprawianie lokalnego katalogu `cut`.

## Invariants

- decyzja jest związana z grą, stagingiem, checksumą i ścieżką źródła;
- źródło musi należeć do dokładnego manifestu oraz preflightu;
- identyczne ponowienie jest idempotentne, a inny cel nie współdzieli klucza;
- historyczny preflight i browser manifest pozostają bitowo niezmienne;
- retry joba zawsze zachowuje przypięty snapshot wykluczeń;
- wykluczenie nie usuwa źródła ani decyzji z innych stagingów i jobów;
- poprawiony plik o innej checksummie nie dziedziczy wykluczenia.

## Acceptance criteria

- źródło znika z kolejki po poprawnym zapisie decyzji;
- import utworzony po decyzji nie kopiuje i nie przetwarza źródła;
- wykluczenie zmienia input key nowego importu;
- restart API/workera zachowuje decyzję i wynik;
- obcy staging, checksum, gra lub manifest są odrzucane fail-closed;
- kontrakt OpenAPI i klient TypeScript pozostają zgodne;
- testy API, domeny, workera i Admina przechodzą.

## Outcome

Zaimplementowano checksum-bound wykluczenie źródła z browser importu. Nowa
tabela `image_page_source_exclusions` utrwala decyzję operatora dla gry i
stagingu, a endpoint weryfikuje dokładny manifest preflightu, ścieżkę i SHA-256
oraz blokuje wykluczenie ostatniego źródła. Kolejka korekty od razu ukrywa
pozycję po potwierdzonej akcji `Usuń z importu`.

Snapshot wykluczeń wchodzi do joba preflightu/importu i jego fingerprintu.
Worker weryfikuje snapshot względem niezmiennego browser manifestu, po czym
pomija JPEG jeszcze przed utworzeniem managed originals. Tym samym dalsza
geometria, cropy i inferencja nie widzą wykluczonego źródła. Staging i jego
historyczne manifesty nie są mutowane.

Migracja `0097_page_source_exclusions` została zastosowana. Odbiór: 86
skoncentrowanych testów API/workera, 6 testów kontraktu UI, Ruff, typecheck i
lint Admina, aktualność OpenAPI oraz produkcyjny build Admina — zielone. Pełny
`format:check` pozostaje czerwony na 55 wcześniejszych plikach spoza taska;
pełny mypy nadal raportuje wcześniejsze błędy w 13 niezwiązanych modułach.
