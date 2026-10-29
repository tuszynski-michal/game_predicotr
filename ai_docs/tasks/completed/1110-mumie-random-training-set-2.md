---
title: Drugi losowy zestaw 60 zdjęć Mumii
status: done
last_updated: 2026-10-30
---

# TASK-1110 — Drugi losowy zestaw 60 zdjęć Mumii

## Status

`done`

## Goal

Skopiować dokładnie 60 losowych, różnych zdjęć z `D:\mumie a2` do `D:\trening set 2`, bez zdjęć z `D:\trening set`.

## Context

Operator wskazał katalogi i liczbę 60 zdjęć. Odczyt: źródło ma 50 037 JPEG, pierwszy set 479 JPEG, docelowy katalog jest pusty. Wykluczenia obejmą nazwy i SHA-256 plików; nie zmieniamy nazw zawierających numery sekwencji.

## Dependencies / entry conditions

Katalogi istnieją, brak junctionów i symlinków podczas inwentaryzacji. Operacja obejmuje wyłącznie kopie, bez treningu i rejestracji kohort. Nie deklaruje niezależności nagrań ani kwalifikacji do TRAIN/holdout.

## Recommended execution

Bieżąca sesja Codex, bez delegowania i audytu; ograniczona operacja plikowa, bez planu implementacyjnego.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md` — nazwy plików i zakresy sekwencji.
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Losowanie bez zwracania, z wykluczeniem nazw i zawartości pierwszego setu oraz duplikatów wewnątrz nowego setu.
- Kopiowanie pod oryginalnymi nazwami, bez nadpisywania i zmian źródeł.
- Manifest wybranych ścieżek, rozmiarów i SHA; weryfikacja z nowego procesu.

## Out of scope

Usuwanie, przenoszenie, zmiana obrazów, import do aplikacji, trening, ustalanie splitów, zmiana kodu, usług, API, bazy, merge i push.

## Acceptance criteria

- [x] W `D:\trening set 2` jest dokładnie 60 JPEG.
- [x] Każda kopia ma niezmienioną nazwę i SHA zgodne ze wskazanym źródłem.
- [x] W nowym secie nie ma powtarzających się nazw lub SHA ani wspólnych nazw/SHA z pierwszym setem.
- [x] Nowy proces potwierdza kompletność, zgodność kopii i niezmieniony pierwszy set.
- [x] Manifest i wynik dokumentacji zapisane, task zamknięty przez task-close.

## Technical notes

Próbkowanie z losowej permutacji kandydatów, kryptograficzny generator systemu. Odczyt SHA wszystkich plików pierwszego setu i wybranych kandydatów; bez niepotrzebnego hashowania całego katalogu 50 tys. zdjęć. Przed kopiowaniem ponownie sprawdzić pusty cel; zapis plików w trybie exclusive. Limit każdego przebiegu 120 s.

## Expected files

- Nowe kopie: `D:\trening set 2\seq_*.jpg` — poza repo, zgodnie z poleceniem operatora.
- Nowy: `ai_docs/quality/MUMIE_TRAINING_SET_2_20261030.json`.
- Nowy: ten task; stan i archiwum aktualizowane skillem task-close.

## Test cases / Verification

Nowy proces ponownie czyta pliki źródłowe wybranego setu, 60 kopii i pierwszy set. Porównuje SHA i nazwy, liczbę plików i zbiorczy odcisk pierwszego setu. `npm run docs:check`, limit 120 s. Brak zmian kodu, bez testów implementacji.

## Risks / open questions

Wykluczenia dotyczą identycznych nazw i bajtów. Podobne kadry z jednego nagrania nie są traktowane jako identyczne zdjęcia; operator zlecił losowy set, a nie podział nagrań.

## Outcome

Commit: v1.7.510 (hash dopisuje kolejny commit).

### Changed

- Skopiowano 60 losowych JPEG z podkatalogów `D:\mumie a2` do `D:\trening set 2`, pod oryginalnymi nazwami. Łącznie 12 815 182 B.
- Źródło: 50 037 JPEG. Set 1: 479 JPEG. Nazwy z pierwszego setu wykluczyły 488 ścieżek źródłowych; pozostałych kandydatów przetasowano generatorem SystemRandom i wybrano pierwsze 60 spełniających kontrolę SHA i nazw. Nie wymagano ponownego losowania z powodu SHA.
- Manifest źródeł, kopii, rozmiarów i SHA: `ai_docs/quality/MUMIE_TRAINING_SET_2_20261030.json`. Źródła i pierwszy set nie były zapisywane; zapis kopii w trybie exclusive.

### Verification results

- Nowy proces, 2026-10-30 00:02:56 Europe/Warsaw: dokładnie 60 JPEG i 60 różnych SHA; zero wspólnych nazw i SHA z setem 1. Każda kopia zgodna z odpowiadającym źródłem i manifestem; zbiorczy odcisk pierwszego setu niezmieniony.
- `npm run docs:check`: PASS — decyzje i kotwice, okno stanu, 11/11 budżetów i kopie skillów. Odczyt startowy 43 394 B. Kod nie zmieniał się, więc lint, typecheck i testy implementacji nie dotyczą tej operacji. Audyt nie jest wymagany przez żaden plan.

### Not completed

Nie importowano zdjęć, nie uruchamiano treningu ani usług, nie zmieniano splitów, bazy i modeli. Bez merge i push. Nie badano podobieństwa kadrów; zweryfikowano identyczność nazw i bajtów zgodnie z zakresem.

### Documentation updates

Task, manifest i wpis ukończenia w stanie projektu, zamknięcie przez task-close. Definition of Done dla ograniczonej operacji kopiowania spełniona po kontroli dokumentacji.

### Recommended next task

Użyć `D:\trening set 2` do kolejnego importu i korekt, a kwalifikację danych do rzeczywistego treningu przeprowadzić istniejącym workflowem.
