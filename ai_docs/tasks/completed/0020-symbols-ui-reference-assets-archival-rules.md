---
title: TASK-0020 Symbols UI, reference assets and archival rules
status: done
last_updated: 2026-07-27
---

# TASK-0020 — Symbols UI, reference assets and archival rules

## Goal

Dostarczyć w lokalnym panelu kompletny katalog symboli dla wybranej gry:
listowanie, tworzenie, edycję pól zmiennych i archiwizację bez fizycznego
usuwania.

## Context

TASK-0018 udostępnił domenę, PostgreSQL i typowane operacje symboli. TASK-0019
dostarczył shell panelu i katalog tożsamości gier. Ostatni pion M2.2 łączy te
elementy i domyka bramkę katalogu gier oraz symboli.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_02_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- aktywna sekcja symboli w shellu panelu,
- wybór gry i odświeżanie selektora po zmianie katalogu gier,
- lista symboli uporządkowana zgodnie z odpowiedzią API,
- stany loading, empty, error i success z jawnym Retry,
- tworzenie symbolu z `mobileCode`, kodem, nazwą, ścieżką obrazu
  referencyjnego, flagą joker, kolejnością i statusem,
- edycja pól zmiennych bez możliwości zmiany stabilnego kodu i `mobileCode`,
- walidacja liczb, wymaganych pól i względnej ścieżki POSIX,
- jawne potwierdzenie archiwizacji i pozostawienie rekordu na liście,
- blokada wielokrotnego submitu oraz tekstowy feedback,
- testy czystej logiki i granicy interakcji z typowanym klientem.

## Out of scope

- przesyłanie binarnej zawartości obrazu przez Admin API,
- kopiowanie plików do magazynu i generowanie miniaturek,
- wymiary gry, koszt spinu, wersje reguł i payout rules,
- dataset, import zdjęć, klasyfikacja i manual review,
- fizyczne usuwanie symbolu.

## Acceptance criteria

- [x] administrator wybiera grę i widzi jej deterministycznie uporządkowane symbole,
- [x] brak gry, brak symboli, ładowanie i błąd API mają osobne stany,
- [x] formularz tworzy symbol ze wszystkimi polami kontraktu M2.2,
- [x] `mobileCode` mieści się w `1..32767`, a `displayOrder` jest nieujemny,
- [x] opcjonalny `imagePath` jest względną ścieżką POSIX bez parent traversal,
- [x] edycja nie pozwala zmienić stabilnego kodu ani `mobileCode`,
- [x] administrator może oznaczyć symbol jako joker i zmienić kolejność/status,
- [x] archiwizacja wymaga potwierdzenia i nie usuwa wiersza,
- [x] podwójny submit jest zablokowany, a błędy mają czytelny tekst,
- [x] typowany klient pokrywa create/update/archive bez ręcznych typów odpowiedzi,
- [x] produkcyjny build i pełna bramka jakości przechodzą.

## Technical notes

- `imagePath` pozostaje względną ścieżką metadanych zgodnie z aktualnym
  kontraktem API; główna tabela nie przechowuje obrazu binarnego,
- UI nie sortuje odpowiedzi symboli ponownie i zachowuje kolejność kanoniczną
  `displayOrder`, `mobileCode`, UUID zwróconą przez backend,
- odświeżenie katalogu gier po create/update/archive jest przekazywane przez
  mały komponent workspace bez globalnego store,
- formularz korzysta wyłącznie z typów generowanego klienta.

## Expected files

- `apps/admin/src/app/page.tsx`
- `apps/admin/src/app/globals.css`
- `apps/admin/src/components/admin-shell.tsx`
- `apps/admin/src/features/catalog/**`
- `apps/admin/src/features/games/game-catalog.tsx`
- `apps/admin/src/features/symbols/**`
- `apps/admin/test/**`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run admin:build
npm run quality
```

## Risks / open questions

- Brak pytania blokującego. Weryfikacja istnienia i kopiowanie pliku obrazu
  należą do przyszłego pionu magazynu/importu; M2.2 zarządza ścieżką metadanych.

## Outcome

### Zmieniono

- dodano aktywną sekcję symboli i workspace odświeżający listę gier po
  mutacjach katalogu,
- dodano wybór gry oraz osobne stany loading, empty, error/success dla gier i
  symboli,
- formularz create/edit obsługuje pełny kontrakt symbolu; w edycji stabilny kod
  i `mobileCode` są zablokowane,
- walidacja UI obejmuje wymagane pola, wzorzec kodu, `mobileCode 1..32767`,
  nieujemny `displayOrder` i względny `imagePath` bez parent traversal,
- aktywny rekord można zarchiwizować wyłącznie osobną akcją z potwierdzeniem;
  wiersz pozostaje na liście, a edycja rekordu zarchiwizowanego pozwala go
  reaktywować,
- lista zachowuje kanoniczny porządek API, a lokalny upsert używa tego samego
  klucza `displayOrder`, `mobileCode`, UUID,
- wydzielono czyste funkcje stanu oraz testowaną granicę typowanego klienta dla
  create/update/archive.

### Zweryfikowano

- `npm run test --workspace @game-predictor/admin` — 19/19 testów,
- `npm run lint --workspace @game-predictor/admin`,
- `npm run typecheck --workspace @game-predictor/admin`,
- `npm run admin:build` — statyczna trasa `/` zbudowana poprawnie,
- fizyczne testy integracyjne PostgreSQL — 2/2,
- lokalny smoke produkcyjnego panelu — HTTP 200 oraz wyrenderowane sekcje gier
  i symboli,
- `npm run quality`.

### Nie wykonano

- panel nie przesyła ani nie kopiuje obrazu binarnego; zapisuje względną ścieżkę
  metadanych zgodnie z kontraktem,
- nie dodano wymiarów, kosztu spinu, wersji reguł ani payout rules.

### Następny krok

`TASK-0021 — Rules version domain and game dimensions`.
