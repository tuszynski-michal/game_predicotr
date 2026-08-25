---
title: TASK-0282 - Strumieniowy transfer wybranych zdjęć
status: done
owner: Codex
version: 0.7
---

## Cel

Zaimplementować TASK 10 z planu zdalnej ręcznej selekcji: po potwierdzonym
`SELECT` przesyłać wyłącznie bieżącą generację wybranego JPEG-a do bezpiecznego
pliku tymczasowego hosta, zweryfikować rozmiar, checksumę i dekodowalność JPEG
oraz zakończyć transfer w stanie `verified`.

## Zakres

- status i idempotentny endpoint strumieniowego `PUT` dla jednego pliku,
- ograniczenia rozmiaru, sesji, współbieżności i czasu transferu,
- zapis `.part`, checksumowanie w locie, walidacja JPEG i publikacja host-internal
  artefaktu `verified`,
- status-before-retry i exact retry bez ponownego zapisu treści,
- bezpieczny binarny proxy Reviewera bez buforowania całego requestu,
- ograniczony scheduler klienta z priorytetem, backoffem, anulowaniem i trwałym
  checkpointem metadanych,
- testy jednostkowe, integracyjne, bezpieczeństwa i regresyjne.

## Poza zakresem

- materializacja końcowego `seq_<start>-<end>.jpg`,
- usuwanie po `DESELECT`, finalizacja partii i reconciliacja,
- transfer kawałkowy/resumable na poziomie bajtów,
- pełny ekran zdalnej selekcji (TASK 13).

## Invarianty

- upload dotyczy tylko potwierdzonego `SELECT` i bieżącej generacji,
- `.part` nigdy nie jest wynikiem ukończonym,
- przerwanie lub nieprawidłowy JPEG nie tworzy artefaktu `verified`,
- retry tego samego requestu nie tworzy drugiej treści,
- proxy i backend nie przechowują całego JPEG-a w pamięci,
- baza przechowuje wyłącznie metadane i ścieżkę host-internal,
- stan końcowy TASK 10 to najwyżej `verified`, nigdy `materialized`.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Kryteria odbioru

- przerwany stream nie pozostawia gotowego pliku,
- utracona odpowiedź po weryfikacji jest odzyskiwana przez status bez resend,
- zły MIME/magic/decode, rozmiar, quota i konflikt generacji mają stabilne błędy,
- aktywna liczba transferów i pamięć klienta są ograniczone,
- nawigacja klienta nie oczekuje na zakończenie transferu,
- testy API, repozytorium i Reviewera oraz lint/typecheck/OpenAPI przechodzą.

## Outcome

- Backend przyjmuje wyłącznie potwierdzoną bieżącą generację `SELECT`, zapisuje
  strumień porcjami do `.part`, sprawdza zadeklarowane metadane, SHA-256 oraz
  pełną dekodowalność JPEG i publikuje atomowo host-internal artefakt
  `verified`. Nie dodano materializacji `seq_*`.
- Limity per plik i sesję, liczba transferów per sesję i globalnie oraz timeout
  są konfigurowalne. Przerwany, przekroczony albo błędny transfer usuwa `.part`
  i kończy stabilnym błędem domenowym.
- Status-before-retry, stabilny `transferId` w IndexedDB i adopcja zgodnego
  artefaktu po restarcie zapewniają idempotentne odzyskanie utraconej odpowiedzi
  bez ponownego przesłania treści.
- Reviewer udostępnia tylko dokładne route statusu i binarnego `PUT`; proxy
  streamuje body bez pełnego buforowania. Scheduler ma ograniczoną
  współbieżność i pamięć, priorytet, anulowanie oraz retry wyłącznie błędów
  przejściowych.
- Bramka końcowa: 54 celowane testy API, 14 testów repozytorium PostgreSQL i 91
  testów Reviewera; Ruff, ESLint, typecheck, build Reviewera oraz kontrola
  OpenAPI i wygenerowanego klienta są zielone. Pełna regresja API została
  wcześniej wykonana w rozłącznych grupach: 534 testy przeszły, 2 pominięto;
  późniejsze zmiany były ponownie objęte celowaną bramką 54 testów.
- TASK 10 kończy się na stanie `verified`. Finalizacja, `DESELECT`, reconciliacja
  i końcowe pliki wynikowe pozostają świadomie poza zakresem TASK 11.
