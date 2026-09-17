---
title: TASK-0577 — Ręczna kontrola zarejestrowanego zdjęcia przed importem
status: in_progress
last_updated: 2026-09-17
---

# TASK-0577 — Ręczna kontrola zarejestrowanego zdjęcia przed importem

## Status

`in_progress`

## Goal

Operator może przed rozpoczęciem importu otworzyć i ręcznie poprawić dowolne aktywne, automatycznie zarejestrowane zdjęcie bieżącego browser stagingu.

## Context

Panel korekty był widoczny tylko dla źródeł odroczonych albo świeżo podmienionego JPEG-a. Istniejący endpoint oraz zapis rewizjonowanego override'u już obsługują optional inspection zarejestrowanego źródła, ale interfejs nie pozwalał operatorowi wskazać jego checksumy.

## Dependencies / entry conditions

- Browser staging ma ukończony, checksum-bound preflight geometrii.
- Import dla tego stagingu nie został rozpoczęty.
- Wybrane lokalnie zdjęcie musi odpowiadać SHA-256 aktywnego pliku stagingu.

## Recommended execution

`gpt-5.6-terra`, reasoning `high`. Zmiana obejmuje stan React, istniejący kontrakt API i trwały zapis geometrii, więc wymaga sprawdzenia ścieżki od wyboru pliku do ponownego preflightu. Eskalacja do `gpt-6-astra`, reasoning `high`, jest wymagana wyłącznie przy konieczności zmiany semantyki kanonicznych źródeł albo kontraktu API.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Wyświetlać sekcję ręcznej geometrii po ukończonym preflighcie również przy zerowej liczbie źródeł odroczonych.
- Pozwolić wybrać lokalny JPEG, wyliczyć jego SHA-256 wyłącznie w przeglądarce i otworzyć zarejestrowane źródło o tej samej checksumie.
- Zachować istniejącą checksummed ścieżkę odczytu assetu, zapisu override'u i jawnego ponownego preflightu.
- Czytelnie odrzucić plik, który nie jest aktywnym zarejestrowanym źródłem stagingu.

## Out of scope

- Zmiana geometrii źródeł `skipped_human_resolved`, ponieważ reprezentują już kanoniczne dane gry i preflight celowo ich nie materializuje.
- Edycja geometrii po rozpoczęciu importu, ponowny upload JPEG-a, zmiana manifestów albo uruchamianie joba bez jawnej akcji operatora.

## Acceptance criteria

- [ ] Przy `completed` i `odroczone 0` panel daje możliwość wskazania zarejestrowanego zdjęcia.
- [ ] Zgodny JPEG otwiera istniejącą automatyczną geometrię jako `operator_inspection`.
- [ ] Niezgodny lub nieaktywny plik nie udostępnia edytora i pokazuje zrozumiały komunikat.
- [ ] Zapis korekty pozostaje rewizjonowany; licznik odroczonych nie wzrasta, a nowy preflight wymaga jawnego kliknięcia.
- [ ] Dotychczasowa kolejka źródeł odroczonych i podmiana zdjęcia działają bez zmiany zachowania.

## Technical notes

`PageGeometryCorrectionPanel` ma wykorzystywać istniejące `checksumPageGeometryFile` i opcjonalny parametr `includeSourceChecksumSha256` endpointu listy źródeł. Wewnętrzny wybór zawęża wynik do dokładnie wybranego źródła; zewnętrzny focus podmienionego zdjęcia zachowuje dotychczasową nawigację. Zapis nie uruchamia preflightu — operator wywołuje istniejące `Odśwież preflight geometrii`.

## Expected files

- Istniejące: `apps/admin/src/features/imports/page-geometry-correction-panel.tsx` — wybór checksummed źródła.
- Istniejące: `apps/admin/src/features/imports/image-folder-import-panel.tsx` — widoczność sekcji przed importem.
- Istniejące: `apps/admin/test/page-geometry-correction-panel-contract.test.mjs` — regresje komponentu.
- Istniejące: `apps/admin/test/image-folder-import-panel-contract.test.mjs` — regresja widoczności panelu.
- Istniejące: `ai_docs/requirements/IMAGE_INGESTION.md` — zakres opcjonalnej korekty.

## Test cases

- Ukończony preflight z zerową kolejką → sekcja kontroli jest dostępna.
- JPEG o checksumie zarejestrowanego źródła → pobierany jest tylko zgodny wpis `operator_inspection`.
- JPEG spoza stagingu albo `skipped_human_resolved` → brak edytora i jasny błąd bez zapisu.
- Korekta odroczonego i podmienionego źródła → dotychczasowe ścieżki nadal są dostępne.

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

## Risks / open questions

- Źródło pominięte jako w pełni kanoniczne nie może być pozorowane jako edytowalne w tym stagingu; wymaga osobnego workflowu korekty danych już zaimportowanych.

## Outcome

### Changed

- Po ukończonym preflighcie, przed rozpoczęciem importu, panel zawsze udostępnia opcjonalną korektę geometrii.
- Operator wskazuje lokalny JPEG; przeglądarka używa wyłącznie jego SHA-256, aby otworzyć zgodne zarejestrowane źródło stagingu bez wysyłania pliku.
- Brak zgodności, źródło spoza stagingu i źródło `skipped_human_resolved` nie otwierają edytora ani nie zapisują danych.
- Zaktualizowano wymaganie oraz kontrakty regresji Admina.

### Verification results

- `npm run test --workspace @game-predictor/admin` — zaliczone poza sandboxem systemowym.
- `npm run typecheck --workspace @game-predictor/admin` — zaliczone.
- `npm run lint --workspace @game-predictor/admin` — zaliczone; pozostaje jedno wcześniejsze ostrzeżenie `@next/next/no-img-element` dla istniejącego podglądu podmienionego zdjęcia.
- `git diff --check` — zaliczone.

### Not completed

- Nie dodano edycji `skipped_human_resolved`; jej zapis nie miałby zastosowania do już kanonicznych danych gry.

### Documentation updates

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/process/CURRENT_STATE.md`

### Recommended next task

- Oddzielny workflow korekty geometrii już kanonicznie zaimportowanych źródeł, jeśli operator ma zmieniać także te pozycje.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0577 — Ręczna kontrola zarejestrowanego zdjęcia przed importem | gpt-5.6-terra | high | Istniejące API i zapis override'u ograniczają zmianę do kontrolowanego pionu UI; należy zachować identyfikację checksumą oraz brak automatycznego joba. | Nie jest wymagany; review gpt-6-astra/high tylko przy zmianie zakresu na dane kanoniczne. |
