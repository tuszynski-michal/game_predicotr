---
title: TASK-0121 Admin workspace navigation and collapsible sections
status: done
last_updated: 2026-07-31
---

# TASK-0121 — Admin workspace navigation and collapsible sections

## Status

`done`

## Goal

Zastąpić długą, jednocześnie renderowaną stronę Admina trzema jednoznacznymi
workspace'ami oraz wprowadzić pojedynczy kontekst aktywnej gry i zwijane sekcje
zarządzania grą, bez zmiany zachowania domenowego istniejących funkcji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- naprawa ujawnionych w TASK-0120 rozbieżności bramki integracyjnej PostgreSQL,
- trzy główne workspace'y: `Zarządzanie grami`, `Wersje Android`, `Joby`,
- deterministyczne odtwarzanie workspace'u, aktywnej gry i sekcji z URL,
- jeden aktywny kontekst gry współdzielony przez sekcje zależne,
- accordion: `Import layoutów`, `Symbole`, `Reguły`, `Zatwierdzanie plansz`,
- najwyżej jedna otwarta sekcja i stabilny scroll po przełączeniu,
- zachowanie obecnych ekranów i kontraktów API wewnątrz nowych kontenerów,
- testy stanu nawigacji i kontrole jakości zmienionych części.

## Out of scope

- filtry `Aktywne` / `Szkice` / `Zarchiwizowane` i zmiany archiwizacji
  przewidziane dla TASK-0122,
- nowy workflow importu, katalogu symboli, reguł, wydań lub jobów,
- zmiany schematu bazy i fizyczne usuwanie danych,
- masowy import oraz dane wersji 0.1.

## Likely changed files

- `apps/admin/src/app/page.tsx`
- `apps/admin/src/app/globals.css`
- `apps/admin/src/components/admin-shell.tsx`
- `apps/admin/src/features/catalog/catalog-workspace.tsx`
- `apps/admin/src/features/catalog/admin-navigation-state.ts`
- komponenty katalogu zależne od aktywnej gry,
- testy w `apps/admin/test/`,
- testy integracyjne PostgreSQL i `scripts/verify_postgres_baseline.ps1`,
- bieżąca dokumentacja procesu.

## Assumptions

- URL używa parametrów `workspace`, `game` i `section`; wartości niepoprawne
  wracają do bezpiecznych wartości domyślnych,
- zwinięcie otwartej sekcji jest dozwolone, więc aktywna gra może mieć zero albo
  jedną otwartą sekcję,
- komponenty zależne zachowują tryb samodzielny dla istniejących testów, ale w
  głównym Adminie otrzymują aktywne `gameId` z jednego źródła,
- szczegółowe blokady etapów workflow zostaną dopracowane w zadaniach 0123–0130;
  TASK-0121 nie symuluje jeszcze nieistniejących reguł gotowości.

## Acceptance criteria

- [x] Admin pokazuje dokładnie trzy główne workspace'y,
- [x] odświeżenie i nawigacja historii odtwarzają bieżący workspace,
- [x] bez aktywnej gry widoczna jest wyłącznie sekcja `Gry`,
- [x] wybór gry udostępnia cztery nagłówki sekcji zależnych,
- [x] sekcje zależne nie renderują własnego wyboru gry,
- [x] jednocześnie rozwinięta jest najwyżej jedna sekcja,
- [x] przełączenie sekcji nie powoduje niekontrolowanego skoku scrolla,
- [x] zmiana workspace'u nie kasuje wybranego kontekstu gry i sekcji,
- [x] istniejące funkcje wydań oraz monitor jobów działają w osobnych workspace'ach,
- [x] bramka integracyjna PostgreSQL przechodzi na aktualnym schemacie,
- [x] lint, typecheck, testy i build Admina przechodzą.

## Verification

```powershell
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run build --workspace @game-predictor/admin
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\verify_postgres_baseline.ps1
```

## Outcome

- Długą nawigację boczną zastąpiono trzema kafelkami workspace’ów:
  `Zarządzanie grami`, `Wersje Android` i `Joby`.
- Stan `workspace`, `game` i `section` jest walidowany, zapisywany w URL oraz
  odtwarzany po odświeżeniu i zdarzeniu historii przeglądarki.
- `Gry` jest jedyną sekcją widoczną bez aktywnego kontekstu. Wybrany rekord ma
  jednoznaczne podświetlenie, a cztery sekcje zależne tworzą accordion z
  najwyżej jednym otwartym panelem.
- Symbole, reguły, datasety/import oraz launcher Reviewera przyjmują wspólne
  `gameId`; ich lokalne selectory gry nie są renderowane w głównym Adminie.
- Wydania Android i monitor jobów zachowują istniejące funkcje w osobnych
  workspace’ach. Szczegółowe filtry i archiwizacja pozostają w TASK-0122.
- Naprawiono bramkę PostgreSQL: aktualna rewizja to `0021_reviewer_access`, test
  katalogu sprawdza własny wymagany podzbiór tabel, diagnostyka używa pola
  snapshotu, a Pytest ma kontrolowany `--basetemp` w repozytorium.
- Weryfikacja: 14/14 testów integracyjnych PostgreSQL, 90/90 testów Admina,
  ESLint, TypeScript, Ruff, składnia PowerShell, Prettier i produkcyjny build
  Next.js przeszły. Krótki start builda produkcyjnego na porcie 3010 zwrócił
  HTTP 200 i potwierdził obecność wszystkich trzech workspace’ów; proces został
  następnie zatrzymany.
- Ręczny odbiór pełnego workflow na danych testowych nie należy do TASK-0121;
  czysty baseline celowo nie zawiera gry ani layoutów.
