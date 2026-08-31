---
title: TASK-0363 Fast symbol verification acceptance
status: done
relevant_docs:
  - ai_docs/requirements/ADMIN_APP.md
  - ai_docs/architecture/API_CONTRACT.md
  - ai_docs/architecture/SYSTEM_ARCHITECTURE.md
  - ai_docs/quality/SYMBOL_REVIEW_FAST_PAGE_ACCEPTANCE.md
---

# TASK-0363 — Odbiór szybkiej Weryfikacji symboli

## Goal

Potwierdzić na rzeczywistych danych wydajność strony 500 cropów, progresywne
atlasy, ponowne użycie cache oraz spójność read-only podglądu v0.10.

## Scope

- bounded pomiar realnej projekcji bez sztucznych danych;
- pełne testy zmienionego API i Admina;
- lint, typecheck, OpenAPI i produkcyjny build;
- aktualizacja wymagań, architektury i bieżącego stanu.

## Outcome

- Metadane 500 rekordów osiągnęły p95 `1,110 s`, poniżej bramki `2 s`.
- Pierwszy atlas był dostępny po `0,488 s`, a pięć atlasów całej strony po
  `2,209 s`; powrót z tymi samymi kluczami zajął `0,085 s`.
- Strona wykonała pięć logicznych requestów obrazów i przeniosła łącznie
  `291 298 B` atlasów WebP.
- Testy potwierdziły limit trzech stron metadanych, viewport z overscanem,
  niezależne liczniki i brak mutacji w trybie v0.10.
- Bieżąca baza nie zawiera komórek `virtual_source`; eksperymentalny wariant
  został odebrany kontraktowo i pokazuje jawny brak proweniencji bez fallbacku.

Pełny raport znajduje się w
`ai_docs/quality/SYMBOL_REVIEW_FAST_PAGE_ACCEPTANCE.md`.

## Verification

- `34 passed` — API symbol review, projection availability i atlasy;
- `354 passed` — pełny zestaw testów Admina;
- Ruff lint i format — zmienione moduły i skrypt pomiarowy;
- mypy — sześć zmienionych modułów/skryptów;
- ESLint i TypeScript Admina;
- OpenAPI oraz generowany klient;
- produkcyjny build Admina;
- Prettier dla wszystkich plików tego zadania.

Globalny `npm run format:check` nadal wskazuje 14 istniejących, niezwiązanych
plików Admina/Reviewera, w tym generowane `next-env.d.ts`. Nie zostały one
zmienione ani włączone do tego commita.
