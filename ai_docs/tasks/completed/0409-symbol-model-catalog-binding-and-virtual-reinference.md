---
title: TASK-0409 Symbol model catalog binding and virtual reinference
status: done
last_updated: 2026-09-04
---

# TASK-0409 — Symbol model catalog binding and virtual reinference

## Problem

Import gry `777` został utworzony po zakończeniu treningu, ale przed jawną
aktywacją kandydata. Resolver przypiął globalny model bootstrapowy z klasami
`cherries`, `lemon`, `orange` itd., podczas gdy aktywny katalog gry używa kodów
`WISNIA`, `CYTRYNA`, `POMARANCZ` itd. Predykcje istniały, lecz projekcja
Weryfikacji symboli nie znalazła identycznych kodów i zapisała 297 000
oczekujących komórek jako nierozpoznane.

## Scope

- zachować jawną, audytowalną aktywację modelu,
- blokować tworzenie nowych jobów z bootstrapem, jeżeli gra ma już gotowego,
  lecz nieaktywowanego kandydata,
- sprawdzać zgodność klas aktywnego modelu z aktywnym katalogiem symboli gry,
- kończyć fail-closed, jeśli predykcja modelu gry zawiera kod spoza katalogu,
- rozszerzyć `image_symbol_reinference` o checksum-bound renderowanie bieżących
  cropów `virtual_source` bez tworzenia plików PNG,
- zachować decyzje człowieka i przeliczać wyłącznie elementy `pending`,
- aktywować zatwierdzonego kandydata gry `777`, uruchomić celowaną reinferencję
  i odświeżyć projekcję bez ponownego uploadu źródeł.

## Out of scope

- brak automatycznej aktywacji po treningu,
- brak semantycznego mapowania angielskich kodów bootstrapu na kody katalogu,
- brak ponownego cięcia geometrii i ponownego importu 19 000 plansz,
- brak zmiany schematu bazy i OpenAPI,
- brak modyfikacji zatwierdzonych komórek, kohort oraz historii decyzji.

## Relevant docs

- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/CURRENT_STATE.md`

## Definition of Done

- gotowy kandydat bez aktywacji nie może zostać cicho zastąpiony bootstrapem w
  nowym imporcie ani reinferencji,
- aktywny snapshot o klasach innych niż aktywny katalog gry jest odrzucany
  stabilnym błędem,
- predykcja aktywnego modelu spoza katalogu nie staje się `?`,
- pending-only reinferencja renderuje `virtual_source` bez trwałych bitmap i
  ponownie sprawdza źródło, render spec oraz checksumę pikseli,
- testy obejmują brak aktywacji, drift katalogu, wirtualny render i ochronę
  decyzji człowieka,
- gra `777` używa aktywnej iteracji 5, a jej bieżące pending cropy mają
  przypisania z kodami własnego katalogu.

## Outcome

- Implementację dostarczył commit `v0.10.112`: nowe joby nie mogą ominąć
  gotowego kandydata ani użyć aktywnego modelu o klasach niezgodnych z
  katalogiem gry, a reinferencja odtwarza bieżące cropy `virtual_source`
  checksum-bound bez trwałych bitmap.
- Dla gry `777` jawnie aktywowano iterację 5
  `ab9780d1-0082-40de-9c8e-cdc1be736b77`. Job naprawczy
  `c2611039-5aca-4360-922e-c6bb9e01142f` zakończył się statusem `completed`:
  przetworzył 19 914 z 19 914 plansz, z 19 914 sukcesami i bez błędów.
- Późniejsza, niezależna aktywacja numer 2 przełączyła grę na iterację 6
  `b739e552-ab55-41e4-861a-7ea4f448ab39`.
- Historyczne rozstrzygnięcia człowieka pozostały chronione; zadanie nie
  wymaga ponownego uploadu ani recropu.
