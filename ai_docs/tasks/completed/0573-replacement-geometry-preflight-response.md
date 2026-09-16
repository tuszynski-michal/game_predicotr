---
title: TASK-0573 — Odpowiedź preflightu geometrii po podmianie źródła
status: done
last_updated: 2026-09-16
---

# TASK-0573 — Odpowiedź preflightu geometrii po podmianie źródła

## Goal

Umożliwić jawne utworzenie preflightu v1.1 dla stagingu po podmianie zdjęcia,
z zachowaniem przypiętego manifestu geometrii rodzica.

## Context

Staging `abf32736-cc62-515d-a28b-d7686ea7fa84` powstał z podmiany zdjęcia.
Po wyborze v1.1 raport słusznie wymagał nowego preflightu, lecz jego utworzenie
kończyło się HTTP 500. Serializacja utrwalonego inputu do odpowiedzi API
odrzucała pola pochodzenia i tryb zgodności z manifestem rodzica; transakcja
była wycofywana, więc job nie powstawał.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- Uzgodnić ścisły schemat odpowiedzi joba z polami pochodzenia podmiany i
  przypiętej bazy używanymi przez usługę i workera.
- Wygenerować OpenAPI oraz klienta i dodać regresję żądania API.
- Sprawdzić rzeczywiste utworzenie joba dla wskazanego stagingu bez duplikatu.

## Out of scope

- Zmiana algorytmu geometrii i istniejących manifestów.
- Automatyczne uruchamianie preflightu po samym otwarciu raportu.

## Acceptance criteria

- [x] Schemat przyjmuje pełny utrwalony input preflightu po podmianie.
- [x] Żądanie API w teście tworzy job i zwraca jego pochodzenie.
- [x] OpenAPI i klient są zgodne z backendem.
- [x] Wskazany staging tworzy rzeczywisty preflight v1.1 bez drugiego joba.

## Outcome

### Changed

- Dodano pola pochodzenia podmiany oraz tryb zgodności przypiętej bazy do
  schematu odpowiedzi joba, OpenAPI i klienta.
- Dodano regresję żądania API oraz walidacji pełnego descriptoru bazy.

### Verification results

- Testy API: 73 zaliczone; Ruff lint, kontrola OpenAPI, generowanego klienta
  i kontrola typów klienta: zaliczone.
- Działające API: pierwsze żądanie zwróciło `201` i utworzyło job
  `9c7f87c4-deb7-4315-8030-fa1a00d8c19a`; ponowienie zwróciło `created=false`
  dla tego samego joba. Input przypiął manifest v1.1 joba rodzica
  `23aec586-7bda-4345-9636-7bc23b648586` w trybie
  `replacement_lineage_exact_policy`.
- Job oczekuje w kolejce na worker; w chwili kontroli inny job pozostawał
  w toku. Ukończenie przetwarzania nie jest częścią tej poprawki API.

### Not completed

- Nie czekano na zakończenie kolejki workera ani na końcowy manifest geometrii.

### Documentation updates

- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md` i
  `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- Brak.
