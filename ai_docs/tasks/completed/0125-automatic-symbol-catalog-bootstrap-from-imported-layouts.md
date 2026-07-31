---
title: TASK-0125 Automatic symbol catalog bootstrap from imported layouts
status: done
last_updated: 2026-07-31
---

# TASK-0125 — Automatic symbol catalog bootstrap from imported layouts

## Status

`done`

## Goal

Utworzyć katalog symboli gry z rzeczywistych cropów małego importu 0.2 bez
ręcznego budowania rekordów i bez syntetycznych grafik.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` — D-088, D-109 i D-110
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- operator podaje oczekiwaną liczbę symboli przed bootstrapem,
- backend grupuje rzeczywiste cropy według wersjonowanej predykcji symbolu,
- każda grupa zachowuje liczność, średnie confidence, reprezentatywny crop i
  checksum-bound provenance,
- zgodna liczba grup atomowo tworzy katalog z kolejnymi stabilnymi
  `mobile_code`, proponowanymi nazwami i rzeczywistymi obrazami,
- niezgodna liczba grup zapisuje konflikt bez utworzenia symboli,
- ręczne rozstrzygnięcie może scalać grupy albo wskazać jedną grupę jako źródło
  więcej niż jednego symbolu przy rozdzielaniu,
- ponowienie tego samego źródła i oczekiwania jest idempotentne,
- sekcja `Symbole` prowadzi użytkownika przez bootstrap i stan konfliktu.

## Out of scope

- wybór dziesięciu alternatywnych grafik symbolu i refinement — TASK-0126,
- trening albo automatyczna promocja nowego modelu,
- pełne 500 000 layoutów i nowe gry,
- automatyczne zgadywanie rozwiązania konfliktu liczby grup.

## Acceptance criteria

- [x] bootstrap nie działa bez cropów i nie używa `examples/imgs`,
- [x] wynik ma deterministyczny checksum źródła i reprezentanta każdej grupy,
- [x] zgodna liczba grup tworzy dokładnie oczekiwany katalog,
- [x] niezgodna liczba niczego nie tworzy i wymaga jawnego rozstrzygnięcia,
- [x] merge/split zachowują wszystkie grupy w provenance,
- [x] retry nie dubluje runu ani symboli,
- [x] Admin ma stany loading, empty, conflict, applied i error,
- [x] migracja, OpenAPI, testy backendu i Admina przechodzą.

## Outcome

Dodano checksum-bound bootstrap grupujący rzeczywiste cropy po wersjonowanej
predykcji klasyfikatora. Każda propozycja zachowuje liczność, średnie
confidence, rzeczywisty reprezentatywny crop i checksumę. Zgodna liczba grup
tworzy katalog atomowo; niezgodna zapisuje konflikt, który Admin pozwala jawnie
rozwiązać przez przypisanie, merge lub split. Retry tego samego stanu jest
idempotentne.

Migracja `0023_symbol_bootstrap` została zastosowana. Zweryfikowano 33 testy
backendu, 21 testów klienta Admin API, 99 testów Admina, Ruff, typecheck i lint,
aktualność OpenAPI oraz produkcyjny build Admina.
