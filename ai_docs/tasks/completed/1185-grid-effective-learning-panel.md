---
title: Panel i porównanie skutecznego uczenia
status: done
last_updated: 2026-11-11
---

# TASK-1185 — Panel i porównanie skutecznego uczenia

## Status

`done`

## Goal

Zrealizować mierzalny wynik T4 zaakceptowanego planu skutecznego uczenia.

## Context

Operator zatwierdził całe T1–T4, koszt6–10h i audyty terminalowe; na końcu pytać o scalenie.

## Dependencies / entry conditions

Plan EFFECTIVE_GRID_LEARNING_PLAN_20261111.md, część T4. Diagnozy T1–T3 potwierdzone; niezależna prezentacja może być przygotowana równolegle. Commit po zamknięciu TASK-1184.

## Recommended execution

claude-opus-5-5/high (dokończenie na polecenie operatora2026-11-11). Ryzyko i warunki według tabeli planu. Audyt zmian Claude: gpt-6.1-sol/high; wcześniejsze części Codex weryfikuje niezależnie Claude przed modyfikacją.

## Relevant docs

- `AGENTS.md`
- `ai_docs/delivery/EFFECTIVE_GRID_LEARNING_PLAN_20261111.md`
- `ai_docs/requirements/VISION_LAB.md`
- `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/CROSS_AUDIT.md`
- `ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md`

## Scope

Wszystkie wymagania części T4 planu; wykorzystać istniejący pion bez równoległego trenera/rejestru.

## Out of scope

Operator GPU/trening, migracje operatora, wdrożenie, merge/push/default i nadpisywanie ręcznych korekt.

## Acceptance criteria

- [x] Wszystkie kryteria T4 planu udowodnione testami i raportem (kod; jakość modelu osobno, niezmierzona).
- [x] Ochrona historycznych wersji, danych i niezależnych kontroli zachowana.
- [ ] Audyt Codex gpt-6.1-sol/high — niewykonany: kontynuacja na polecenie operatora po wyczerpaniu limitu.
- [x] Brak znanych otwartych P0/P1 (przegląd własny wykonawcy, nie audyt), docs/map i właściwe testy.

## Technical notes

Przeczytać część T4 planu przed kodowaniem. Hipoteza nie jest diagnozą. Wyniki kodu, danych i jakości modelu oddzielne.

## Expected files

Istniejące: schemas/application grid_correction_learning, OpenAPI/SDK/wrapper, grid-correction-learning-panel.tsx; scripts/render_grid_correction_comparison.py i templates/grid-correction-comparison.html. Nowy: images/comparison_content_changes.py — content_change i test porównania instancji, oparty wyłącznie na zweryfikowanych assessments istniejącego readera.

## Test cases

Scenariusze i kryteria T4 oraz tabela odbioru planu. Restart i utrata odpowiedzi dla trwałych workflowów.

## Verification

Właściwy scoped pytest przez główną .venv, lint/typecheck, npm run docs:check i npm run code-map:check; dokładne komendy i wyniki w raporcie taska. Komendy mają jawny timeout.

## Risks / open questions

Brak danych operatora może blokować trening lub pomiar, nigdy zastępczy PASS jakości.

## Outcome

Commit: v1.7.605 / `fc149f9bbd859cc20b1b25e27ccf40d2347727e0`.

### Changed

- Pion API: opcjonalne zamknięte `learningMaterial` i `testSample` w preview/ready,
  typowane `roleShortfalls` (naprawa 500 przy niewykonalnym podziale), OpenAPI,
  SDK, wrapper, testy żądań.
- Oznaczenia przed zamrożeniem ról: content-targets `sourceIds` i asset z
  oczekiwanymi checksumami; ochrona kontroli i ślepego pomiaru przez istniejące
  domknięcie grup; zapis istniejącą komendą CAS.
- Panel: materiał/kontrole/wykluczenia/niedobory, próbka testu, „Przygotuj nowy
  podział korekt” (tylko preview), „Oznacz zdjęcia do testu”, opis celu uczenia,
  cztery wyniki zawartości (`contentOutcome`, dodane w tej sesji).
- HTML: naprawione/bez zmian/pogorszone/nierozstrzygnięte z verified assessments
  (`comparison_content_changes.content_change`) i osobny widok odniesienia człowieka.

### Verification results

Szczegóły i granice: `ai_docs/quality/TASK-1185_VERIFICATION.md`. Poprzednia
sesja (po ostatniej zmianie Pythona): API 53, porównanie/HTML 50+16, PG source
annotation 1 (64,5 s), workspace 29. Ta sesja: panel 61/61, wrapper 14/14,
prettier/ESLint, Admin i SDK tsc (Admin z mapowaniem klienta na worktree),
`next build` exit 0, openapi/klient aktualne, Ruff, scoped mypy 11 modułów
(nie pełny), mapa kodu i `docs:check`.

Audyt Codex niewykonany — kontynuacja na polecenie operatora po wyczerpaniu
limitu. Brak PASS audytu i brak niezależnego review; przegląd własny wykonawcy
nie wykazał P0/P1. P2: prywatny import `_content` w `comparison_production_cells`.

### Not completed

- Audyt Codex gpt-6.1-sol/high (patrz wyżej).
- Pełne `npm run quality` i pełny mypy.
- Trening, dowód poprawy nowego modelu, migracja 0184 bazy operatora, restart
  usług, wdrożenie, default, merge/push. Kod nie jest wynikiem jakości.
- Dane operatora: A ma 4 zdjęcia / 4 plansze; po ochronie konfliktu 1121 brakuje
  co najmniej 1 zdjęcia i 11 plansz, więc bezpieczny podział v4 jest niewykonalny.

### Documentation updates

`requirements/VISION_LAB.md`, `architecture/VISION_LAB.md`, `architecture/API_CONTRACT.md`,
`DOC_INDEX.md`, mapa kodu, raport weryfikacji, plan (status), `CURRENT_STATE.md`.

### Recommended next task

Operator: odbiór T1–T4 i decyzja o scaleniu do `main`; potem osobno audyt
Codex (gdy będzie limit), migracja 0184 razem z T3 i uzupełnienie danych A.
