---
title: Powiększenie drugiego setu Mumii do 1000 zdjęć
status: done
last_updated: 2026-10-30
---

# TASK-1111 — Powiększenie drugiego setu Mumii do 1000 zdjęć

## Status

`done`

## Goal

Dodać 940 losowych JPEG z `D:\mumie a2` do `D:\trening set 2`, zachowując wcześniejsze 60 i wykluczając pierwszy set.

## Context / entry conditions

Operator zwiększył zamówiony set z 60 do 1000 zdjęć w tym samym katalogu. Zachowujemy całość wcześniejszego setu; wykluczenia obejmują nazwy i SHA z `D:\trening set` oraz bieżącego setu 2. Manifest 60 zdjęć jest wskazany jawnie jako dowód zachowania poprzedniego wyniku.

## Recommended execution

Bieżąca sesja Codex; ograniczone kopiowanie przez istniejące narzędzia, bez delegowania, planu implementacyjnego i audytu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md` — zakresy sekwencji w nazwach.
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/quality/MUMIE_TRAINING_SET_2_20261030.json` — poprzednie 60 zdjęć.

## Scope

Losowanie 940 nowych, różnych zdjęć, kopie z oryginalnymi nazwami, bez nadpisywania; manifest i weryfikacja nowym procesem. Nie kwalifikuje danych do TRAIN/holdout ani nie deklaruje niezależności nagrań.

## Out of scope

Usuwanie lub zmiana obecnych plików, import, trening, usługi, baza, modele, zmiana kodu, merge i push.

## Acceptance criteria

- [x] Dokładnie 1000 JPEG w docelowym katalogu, w tym poprzednie 60 bez zmian.
- [x] Dokładnie 940 nowych plików zgodnych bajtowo ze źródłami.
- [x] Brak duplikatów nazw i SHA w secie 2 oraz brak wspólnych nazw/SHA z setem 1.
- [x] Nowy proces potwierdza stan i niezmieniony pierwszy set.
- [x] Manifest, docs:check i zamknięcie task-close zakończone.

## Technical notes

SystemRandom tasuje kandydatów po wykluczeniu nazw; SHA kandydatów sprawdzamy przed dopuszczeniem. Przed kopiowaniem ponownie porównujemy katalog celu z manifestem 60 zdjęć; pliki zapisujemy exclusive. Każdy przebieg ma limit 120 s i postęp. Po przerwaniu nie ponawiać ślepo kopii; sprawdzić dziennik i faktyczne pliki.

## Expected files

- Nowe kopie: `D:\trening set 2\seq_*.jpg` — 940 JPEG poza repo.
- Nowy: `ai_docs/quality/MUMIE_TRAINING_SET_2_EXPANSION_20261030.json`.
- Nowy: niniejszy task; `CURRENT_STATE.md` i archiwum aktualizuje task-close.

## Verification

Nowy proces liczy 1000 plików, porównuje SHA i nazwy z setem 1 oraz manifestami obu partii, weryfikuje źródła 940 kopii i zachowanie 60. `npm run docs:check`, limit 120 s. Bez testów kodu, którego nie zmieniamy.

## Risks / open questions

Badamy identyczność nazw i zawartości plików, nie podobieństwo różnych kadrów. Brak otwartych pytań blokujących.

## Outcome

Commit: v1.7.512 / `a872732336309711e629682bf31b3254bd267f87`.

### Changed

- Dodano 940 losowych JPEG z `D:\mumie a2` do `D:\trening set 2`; razem 1000 zdjęć i 212 627 551 B. Zachowano wszystkie wcześniejsze 60 zdjęć i ich oryginalny manifest.
- Wykluczono nazwy i SHA pierwszego setu (479 zdjęć) oraz dotychczasowego setu 2. Z 50 037 ścieżek źródła wykluczono 549 po nazwach; losowa permutacja SystemRandom dostarczyła 940 różnych nowych zdjęć, bez odrzuceń po SHA podczas próbkowania.
- Kompaktowy manifest nowych 940 i zachowanych 60: `ai_docs/quality/MUMIE_TRAINING_SET_2_EXPANSION_20261030.json`. Kopie zapisano exclusive, bez nadpisywania.

### Verification results

- Nowy proces, 2026-10-30 00:06:39 Europe/Warsaw: 1000 JPEG, 1000 różnych nazw i SHA, zero wspólnych nazw i SHA z setem 1. Wszystkie kopie zgodne ze źródłami; set 1, poprzednie 60 i oryginalny manifest bez zmian.
- `npm run docs:check`: PASS — decyzje, kotwice, okno stanu, 11/11 budżetów i kopie skillów. Odczyt startowy 43 380 B. Brak zmian kodu; lint, typecheck, migracje i testy implementacji nie dotyczą tej operacji. Żaden plan nie wymaga dodatkowego audytu.

### Not completed

Bez importu, treningu, zmian źródeł, modeli, bazy, usług, merge i push. Nie badano podobieństwa różnych kadrów, tylko identyczność plików i nazw.

### Documentation updates

Task, manifest i wpis ukończenia w stanie projektu przez task-close. Kryteria operacyjne i dokumentacyjne Definition of Done spełnione.

### Recommended next task

Użyć całego katalogu `D:\trening set 2` zawierającego 1000 zdjęć do kolejnego importu i korekt.
