---
title: TASK-0122 Active game catalog filters and archiving
status: done
last_updated: 2026-07-31
---

# TASK-0122 — Active game catalog filters and archiving

## Status

`done`

## Goal

Dopracować sekcję `Gry` tak, aby administrator pracował na jednoznacznie
wybranym rekordzie, mógł filtrować katalog według statusu oraz odwracalnie
archiwizować grę bez fizycznego usuwania jej danych.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- filtry `Aktywne`, `Szkice`, `Zarchiwizowane` z licznikami,
- czytelny pusty stan każdego filtra,
- jednoznaczne podświetlenie jedynej wybranej gry,
- usunięcie technicznego opisu o wszystkich rekordach i stabilnym kodzie z
  nagłówka listy,
- archiwizacja z potwierdzeniem, bez usuwania rekordu,
- jawne przywrócenie zarchiwizowanej gry jako szkicu,
- spójne czyszczenie ukrytego kontekstu przy zmianie filtra lub archiwizacji,
- testy czystej logiki filtrów i operacji przywracania.

## Out of scope

- fizyczne usuwanie gry albo należących do niej rekordów i plików,
- zmiany schematu bazy lub kontraktu OpenAPI,
- filtrowanie po nazwie, wyszukiwanie pełnotekstowe i paginacja,
- zmiany zależnych sekcji importu, symboli, reguł i Reviewera.

## Assumptions

- domyślnym filtrem jest `Aktywne`,
- utworzenie lub zapis gry przełącza filtr na jej aktualny status,
- zmiana filtra usuwa aktywny kontekst, jeżeli wybrana gra nie jest w nowym
  widoku,
- zarchiwizowana gra nie może otworzyć zależnego workflow; najpierw trzeba ją
  przywrócić,
- bezpieczne przywrócenie ustawia status `draft`, a administrator może później
  jawnie aktywować grę w edytorze.

## Acceptance criteria

- [x] katalog ma dokładnie trzy filtry statusu z licznikami,
- [x] lista i licznik reagują deterministycznie na filtr,
- [x] pusty filtr nie udaje pustej całej bazy,
- [x] wybrana widoczna gra jest jednoznacznie podświetlona,
- [x] przełączenie na filtr bez wybranej gry czyści zależny kontekst,
- [x] archiwizacja zachowuje rekord i usuwa go z bieżącego aktywnego kontekstu,
- [x] zarchiwizowaną grę można przywrócić jako szkic,
- [x] UI nie zawiera fizycznej akcji `Usuń`,
- [x] testy, lint, typecheck i build Admina przechodzą.

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run build --workspace @game-predictor/admin
```

## Outcome

- Sekcja `Gry` ma trzy filtry `Aktywne`, `Szkice`, `Zarchiwizowane`; każdy
  pokazuje licznik i własny pusty stan odróżniony od pustej bazy.
- Lista renderuje wyłącznie rekordy bieżącego statusu, zachowując kolejność API.
  Zmiana filtra czyści aktywny kontekst tylko wtedy, gdy wybrana gra nie należy
  do nowego widoku.
- Utworzenie albo zapis gry otwiera jej właściwy filtr. Rekord z URL również
  determinuje właściwy widok, bez dodatkowego pobierania katalogu.
- Archiwizacja pozostawia rekord i dane, usuwa zarchiwizowaną grę z aktywnego
  workflow oraz nadal wymaga potwierdzenia.
- Zarchiwizowana gra ma jawną akcję `Przywróć jako szkic`. Operacja używa
  istniejącego typowanego `updateGame`, nie zmienia kodu/tożsamości i nie wymaga
  nowego endpointu ani migracji.
- Zarchiwizowanego rekordu nie można ustawić jako kontekstu zależnych sekcji.
  UI nie zawiera fizycznej akcji `Usuń`.
- Weryfikacja: 96/96 testów Admina, ESLint, TypeScript, Prettier i produkcyjny
  build Next.js przeszły. Testy obejmują dokładny zestaw filtrów, liczniki,
  deterministyczne filtrowanie, zachowanie rekordu po archiwizacji, kontrakt UI
  bez usuwania oraz przywrócenie do `draft`.
- Ręczny test na danych domenowych nie był wykonywany, ponieważ baseline 0.2
  pozostaje celowo pusty; funkcjonalny odbiór pełnego workflow nastąpi po
  utworzeniu małego zestawu testowego w kolejnych zadaniach.
