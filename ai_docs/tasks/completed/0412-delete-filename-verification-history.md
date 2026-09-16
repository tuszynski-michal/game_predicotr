---
title: TASK-0412 Delete completed filename verification history
status: done
last_updated: 2026-09-03
---

# TASK-0412 — Usuwanie historii zakończonej Weryfikacji zakresów

## Problem

Weryfikacja zakresów po bezpiecznym cleanupie zachowuje lekki rekord runu i
job jako historię operacyjną. Operator potrzebuje usunąć taki wpis z ekranu
oraz z bazy, gdy podsumowanie nie jest już potrzebne.

## Scope

- dodać lokalny endpoint `DELETE` dla historii pojedynczego runu
  `filename_verification`;
- usuwać tylko run ze statusem `completed`, którego checkpoint potwierdza
  wykonany cleanup;
- atomowo usuwać rekord runu, jego job oraz ewentualne już-osierocone rekordy
  review/ranges;
- fail-closed blokować run aktywny, oczekujący na decyzje, zablokowany cleanup,
  pozostały staging, diagnozy lub wynikowy output;
- dodać do prawej strony kafla historii przycisk `Usuń`, z potwierdzeniem;
- po sukcesie usunąć wpis z UI, wyczyścić lokalny kontekst tego runu i wybrać
  kolejny wpis historii.

## Out of scope

- usuwanie runów zwykłej półautomatycznej selekcji;
- usuwanie lokalnego katalogu operatora `seq_*`;
- usuwanie aktywnych procesów, retry lub cleanupu zablokowanego;
- zmiany modeli OCR, stagingu lub migracji schematu.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`

## Definition of Done

- ukończony wpis filename verification można świadomie i trwale usunąć;
- żadne dane robocze, staging, output ani aktywny job nie są usuwane przez tę
  akcję — ich obecność blokuje operację;
- run i jego job znikają w jednej transakcji z bazy;
- przycisk jest po prawej stronie wpisu historii, wymaga potwierdzenia i po
  sukcesie nie pozostawia starego wyboru w UI ani IndexedDB;
- OpenAPI, klient API oraz testy backendu i Admina są zgodne.

## Assumption

Usunięcie historii jest trwałe. Ponieważ automatyczny cleanup usunął już
szczegółowe dane robocze, operacja usuwa wyłącznie końcowe metadane historii i
job. Nie uruchamia GC ani nie dotyka katalogu wybranego przez operatora.

## Outcome

Dodano potwierdzony lokalny endpoint usuwający wyłącznie zakończoną i już
wyczyszczoną historię `filename_verification`. Repozytorium blokuje chroniony
staging, diagnostykę, output i obce referencje, a następnie w jednej transakcji
usuwa run, job oraz ewentualne osierocone rows range/review. Admin pokazuje
dwustopniową akcję po prawej stronie właściwego kafla i po sukcesie czyści jego
lokalny kontekst IndexedDB.

Zweryfikowano: testy API i lokalnego bezpieczeństwa (25), testy klienta API
(51), testy Admina (376), Ruff, OpenAPI/generated-client, TypeScript, ESLint,
Prettier i produkcyjny build Admina. Pełny mypy nadal zatrzymuje się na 44
wcześniejszych błędach nieoznaczonych modułów workera oraz dwóch istniejących
błędach poza tym pionem; zmienione moduły nie dodały własnej diagnostyki.
