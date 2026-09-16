---
title: TASK-0572 — Preflight CORS podmiany zdjęcia źródłowego
status: done
last_updated: 2026-09-16
---

# TASK-0572 — Preflight CORS podmiany zdjęcia źródłowego

## Goal

Umożliwić przeglądarce wysłanie JPEG-a przy podmianie niezatwierdzonego źródła
w korekcie geometrii strony.

## Context

Po wskazaniu katalogu `cut` i wybraniu zdjęcia panel zgłaszał błąd przygotowania
rewizji. Żądanie OPTIONS do działającego API zwracało `400 Disallowed CORS headers`;
upload nie docierał do endpointu, a staging pozostawał bez rewizji.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- Dopuścić cztery nagłówki identyfikujące źródło i manifest w lokalnym CORS API.
- Dodać test OPTIONS dla dokładnego zestawu nagłówków klienta.

## Out of scope

- Zmiana danych stagingu, pliku `cut`, joba lub kontraktu OpenAPI.

## Acceptance criteria

- [x] Preflight CORS z origin Admina i nagłówkami podmiany zwraca `200`.
- [x] Przepływ podmiany nadal przechodzi dotychczasowe testy API.
- [x] Nie uruchomiono nowego joba ani nie podmieniono rzeczywistego zdjęcia.

## Outcome

### Changed

- Lista nagłówków CORS API obejmuje `X-Game-Id`, `X-Source-Checksum-Sha256`,
  `X-Source-Relative-Path` i `X-Geometry-Manifest-Checksum-Sha256`.
- Dodano regresję w testach API i opisano kontrakt w architekturze.

### Verification results

- Przed zmianą działające API: `OPTIONS` → `400 Disallowed CORS headers`.
- Po zmianie i automatycznym przeładowaniu API: `OPTIONS` → `200 OK`.
- Testy podmiany i CORS: 6 zaliczonych; Ruff lint: zaliczony.

### Not completed

- Nie wysłano ponownie prywatnego zdjęcia operatora; ostateczny zapis wymaga
  jego ponownej próby w panelu.

### Documentation updates

- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md` i
  `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- Brak.
