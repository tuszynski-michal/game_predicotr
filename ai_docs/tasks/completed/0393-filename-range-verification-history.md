---
title: TASK-0393 — Historia i trwałe wznawianie weryfikacji zakresów
status: done
last_updated: 2026-09-02
---

# TASK-0393 — Historia i trwałe wznawianie weryfikacji zakresów

## Goal

Utrwalić historię workflowu weryfikacji nazw `seq_*`, odtworzyć wybrany run i
jego postęp po reloadzie oraz umożliwić bezpieczne rozstrzygnięcie każdego
podejrzanego zdjęcia bez wymogu lokalnego katalogu dla samego podglądu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- addytywny `workflowMode` runu i payloadu joba;
- migracja historycznych runów po zamkniętej liście fingerprintów;
- lista runów weryfikacji, checksum-bound asset stagingu i polling jednego runu;
- trwałe, rewizyjne decyzje `keep/reject` dla `runId + sourceIndex`;
- IndexedDB per run dla uchwytu katalogu, kursora i pending confirmation po
  lokalnym journalowanym delete;
- regeneracja OpenAPI, klienta Admina, testy pionu i dokumentacja.

## Out of scope

- nowy job type, nowy lane workera lub restart aktywnego workera;
- automatyczne usuwanie zdjęć;
- migracja binarnych obrazów do tabel domenowych;
- zmiana range-only OCR, wyboru zakresów albo lifecycle istniejącego runu.

## Definition of done

- reload przywraca wybrany aktywny run i jego polling bez drugiego uploadu;
- lista zawiera runy completed, failed i cancelled, lecz review jest możliwe
  wyłącznie po terminalnym sukcesie;
- podgląd działa ze stagingu bez uchwytu lokalnego;
- `keep` i `reject` są idempotentne oraz checksum-bound, a `reject` po utracie
  odpowiedzi nie usuwa pliku ponownie;
- lokalny katalog o innej liczbie lub fingerprintcie źródeł nie autoryzuje delete;
- OpenAPI, klient, testy, lint, typy i build są zielone.

## Outcome

- Dodano addytywny `workflowMode` (`selection` albo
  `filename_verification`) dla runów i payloadów jobów, wraz z migracją
  klasyfikującą historyczne runy po zamkniętej liście fingerprintów.
- Dodano stronicowaną historię runów weryfikacji, trwałe decyzje
  checksum-bound `keep`/`reject` z rewizją oraz endpoint ich zapisu.
- Workspace Admina odtwarza wybrany run i kursor z IndexedDB, używa assetu
  stagingowego dla podglądu, a lokalnego katalogu wymaga wyłącznie przed
  journalowanym usunięciem. Pending confirmation po restarcie nie ponawia
  delete bez potwierdzenia journalu i checksumy.
- Wygenerowano OpenAPI i klienta; testy API i Admina, typy, lint oraz build
  zostały uruchomione bez uruchamiania ani przerywania workera lub joba.
