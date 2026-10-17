# TASK-1021 — Przegląd ograniczeń i sekcji `CURRENT_STATE.md` do decyzji operatora

## Status

`done`

## Goal

Raport klasyfikuje każdy punkt „Obowiązujących ograniczeń”, każdy plan i każdą
sekcję aktywnego taska w `CURRENT_STATE.md` (zostaje / skrócić / przenieść do
archiwum / do potwierdzenia przez operatora) i dostaje decyzję operatora przed
TASK-1022.

## Context

Plan `ai_docs/delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md`, etap B,
decyzje D3, D6, D7. „Obowiązujące ograniczenia” mają 19 695 B, część punktów
opisuje stany z 2026-10-01..10, które mogły się zmienić (np. stan migracji
bazy operatora, job TASK-0928, nieużywany katalog C, statusy gry Mumie).
Usunięcie ograniczenia operacyjnego bez zgody operatora mogłoby zdjąć
obowiązującą blokadę, dlatego decyzja należy do operatora.

## Dependencies / entry conditions

- TASK-1020 ukończony (etap A).
- Wyłącznie odczyt: bez zmian w `CURRENT_STATE.md`, archiwach, bazie i
  usługach. Odczyty stanu (np. `alembic current`, status jobów przez API) są
  dozwolone tylko jako odczyt i tylko gdy usługa już działa; bez
  uruchamiania usług.

## Recommended execution

claude-opus-5-5 / high. Osąd aktualności ograniczeń operacyjnych (migracje,
zgody, usługi, joby) wymaga ostrożności i weryfikacji źródeł. Bez audytu
modelowego: bramką jest decyzja operatora.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md`
- pliki aktywnych tasków w `ai_docs/tasks/` (tylko w zakresie porównania
  sekcji okna z `Outcome`)
- sekcje-źródła archiwów wskazane w punktach ograniczeń (otwierać punktowo,
  `rg` + `offset`/`limit`)

## Scope

- Raport `ai_docs/quality/CURRENT_STATE_REVIEW_<data>.md` (proponowany):
  - tabela „Obowiązujące ograniczenia”: punkt (pierwsze słowa), bajty,
    źródło, dowód aktualności (co sprawdzono, wynik), proponowana klasa
    (`zostaje` + proponowany skrót ≤ 400 B / `do task` (dotyczy jednego taska,
    przenieść do jego pliku lub sekcji) / `archiwum` (rozwiązane) /
    `operator` (nie da się ustalić z repo));
  - tabela planów z „Plany z niezakończonymi taskami”: status, pozostałe
    taski, propozycja (wiersz tabeli zamiast podsekcji, archiwum dla planów
    zakończonych);
  - tabela sekcji „Aktywne taski”: bajty, czy treść jest już w `Outcome`
    pliku taska, proponowany wskaźnik ≤ 1 200 B (D7), bloki do archiwum
    (np. historia TASK-0290 13,5 KB, iteracje TASK-0472);
  - rozbieżności znalezione przy okazji (task aktywny w oknie a `done` w
    pliku, plan `completed` z aktywnymi taskami) jako pytania, bez napraw;
  - prognoza bajtów po zastosowaniu i ewentualna propozycja zmiany
    budżetów sekcji z D3 (z uzasadnieniem).
- Przedstawienie raportu operatorowi i zapis jego decyzji w raporcie
  (punkt po punkcie albo zbiorczo „zgoda na propozycję z wyjątkami …”).

## Out of scope

- Jakakolwiek edycja `CURRENT_STATE.md`, archiwów, plików tasków.
- Naprawa wykrytych rozbieżności statusów.

## Acceptance criteria

- [ ] Każdy punkt ograniczeń, każdy plan i każda sekcja aktywnego taska ma klasę i uzasadnienie z dowodem.
- [ ] Prognoza rozmiaru po zastosowaniu mieści się w budżetach D3 albo raport proponuje zmianę budżetów z powodem.
- [ ] Decyzja operatora zapisana w raporcie; bez niej TASK-1022 nie startuje.

## Technical notes

- Klasa `archiwum` dla ograniczenia wymaga dowodu (commit, sekcja `done`,
  odczyt stanu); brak dowodu = klasa `operator`.
- Ograniczenia bezpieczeństwa danych i zgód (operacje destrukcyjne, migracje
  tylko za zgodą, cykl życia usług, aplikacja mobilna offline) zostają
  zawsze; najwyżej skrót bez zmiany sensu.

## Expected files

- Nowy (proponowany): `ai_docs/quality/CURRENT_STATE_REVIEW_<data>.md`.

## Verification

```powershell
# katalog worktree (z dowiązaniem .venv), timeout 120 s
.\.venv\Scripts\python.exe scripts/check_startup_read_budget.py --report
git status --short  # tylko nowy raport i plik taska
```

## Risks / open questions

- Odczyt stanu bazy może być niemożliwy (usługi wyłączone); wtedy klasa
  `operator`.

## Outcome

Wykonawca: subagent claude-opus-5-5 (zgodnie z planem), sprawdzenie leada:
struktura raportu i próbka dowodów (D-467 o migracji `0125`, liniowy łańcuch
`0150`–`0154`). Bez audytu Codex (decyzja operatora 2026-10-16). Commit raportu:
v1.7.368 / `a8ed5dcceafefd0a18410e590b5d938d0eb21457`. Decyzja operatora
2026-10-16: propozycja zatwierdzona w całości, pytania z sekcji 5 otwarte
(zapis w sekcji 7 raportu, commit v1.7.369).

### Changed

- Nowy raport `ai_docs/quality/CURRENT_STATE_REVIEW_20261016.md` (38 504 B,
  `proposed`): 40 punktów ograniczeń (13 `zostaje` ze skrótami ≤ 400 B,
  9 `do task`, 13 `archiwum` z dowodem, 5 `operator`), plany, 50 sekcji
  aktywnych zwiniętych do 24 wskaźników, 10 wpisów D6, rozbieżności i
  prognoza: `CURRENT_STATE.md` ok. 22 500 B (ok. 25 800 B po scaleniu
  `codex/v3-grid-fine-tuning`); budżety D3 bez zmian.

### Verification results

- `git status`: jedyny nowy plik to raport; bez zmian w oknie, archiwach i
  plikach tasków.
- Samokontrola: wszystkie trzy kryteria spełnione.

### Not completed

- Pytania z sekcji 5 raportu pozostają otwarte decyzją operatora.

### Recommended next task

- TASK-1022.