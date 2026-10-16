# TASK-1031 — Skill `merge-to-main` z preflightem scalania

## Status

`done`

## Goal

Przed scaleniem gałęzi roboczej do `main` agent uruchamia
`scripts/integration_preflight.py`, który raportuje możliwość fast-forward i
kolizje numerów, a skill `merge-to-main` prowadzi scalenie, push i bezpieczne
usunięcie worktree z bramkami zgody operatora.

## Context

Plan `delivery/STARTUP_READ_STAGE2_EXECUTION_PLAN_20261016.md`, etap A,
decyzje E1, E2, E6. 2026-10-16 `main` przesunął się w trakcie pracy, a
kolizje TASK-1024, D-548 i `v1.7.364–365` wyszły dopiero przy scaleniu.
Usunięcie worktree z junction `.venv`/`node_modules` wymaga najpierw
odpięcia dowiązań.

## Dependencies / entry conditions

- TASK-1030 (mechanizm luster skilli i katalog Codex).

## Recommended execution

claude-sonnet-5-5 / high. Bez dodatkowego review; samokontrola kryteriów w
`Outcome`.

## Relevant docs

- `AGENTS.md` („Scalanie do gałęzi integracyjnej”, „Brudny worktree”)
- `ai_docs/process/CURRENT_STATE.md` (ograniczenia: gałąź `main`,
  akceptacja przed scaleniem, kolizje numeracji, migracje)
- `ai_docs/delivery/STARTUP_READ_STAGE2_EXECUTION_PLAN_20261016.md`

## Scope

- Nowy `scripts/integration_preflight.py` (proponowany), tylko odczyt:
  - gałąź robocza vs `main` i `origin/main`: liczba commitów w obie strony,
    czy fast-forward jest możliwy, czy lokalny `main` wyprzedza `origin`;
  - kolizje numerów między gałęzią a `main` oraz innymi lokalnymi gałęziami
    z niescalonymi commitami: pliki `ai_docs/tasks/**/NNNN-*.md`, nagłówki
    `D-NNN` w pliku wpisów decyzji, prefiksy `vX.Y.N` commitów, numery
    migracji `services/api/alembic/versions/NNNN_*.py`;
  - czy gałąź dodaje migrację (przypomnienie: scalenie dopiero po
    migracji operatora);
  - wynik tekstowy i `--json`; kod 0 zawsze, chyba że błąd git.
- Skill `.claude/skills/merge-to-main/SKILL.md` (+ kopia Codex): kroki
  preflight → zgoda operatora → aktualizacja gałęzi (`git merge main` w
  worktree, rozwiązywanie konfliktów okna w nowym formacie) →
  `docs:check` → `git merge --ff-only` na `main` w `D:\game_predicotr` →
  push (zgoda na scalenie obejmuje push) → odpięcie junction (`cmd /c rmdir`)
  → `git worktree remove` → `git branch -d`; zakazy: bez `--force` na
  worktree z dowiązaniami, bez push gałęzi pomocniczych, bez scalania kodu
  wymagającego niewykonanej migracji.
- Para lustrzana w `check_skill_mirrors.py`.

## Out of scope

- Automatyczne przenumerowanie kolizji (zgłasza preflight, decyduje agent).

## Acceptance criteria

- [ ] Testy preflight na tymczasowym repo git: fast-forward możliwy / niemożliwy, kolizja TASK, D, `vX.Y.N`, migracji, `main` przed `origin/main`.
- [ ] Skill w Claude Code i kopia wykryta przez Codex; lustro w `docs:check`.
- [ ] Skill nazywa wszystkie bramki zgody z `AGENTS.md` bez ich osłabienia.
- [ ] ruff, `mypy --strict`, `docs:check` PASS.

## Expected files

- Nowe (proponowane): `scripts/integration_preflight.py`,
  `.claude/skills/merge-to-main/SKILL.md`, kopia Codex, test w
  `services/worker/tests/`.
- Istniejące: `scripts/check_skill_mirrors.py` (lista par).

## Verification

```powershell
# katalog worktree z dowiązaniem .venv, timeout 120 s
.\.venv\Scripts\python.exe -m pytest services/worker/tests -k integration_preflight -q -p no:cacheprovider --basetemp D:/ptw
.\.venv\Scripts\python.exe scripts/integration_preflight.py
npm run docs:check
```

## Risks / open questions

- Testy na repo git w katalogu tymczasowym na Windows: krótka ścieżka
  `--basetemp` (długie ścieżki psują testy).

## Outcome

Commit: v1.7.379 (hash dopisuje kolejny commit).

Wykonawca: claude-sonnet-5-5 / high. Dodatkowego review nie było (zgodnie z
planem); kryteria sprawdzone samodzielnie poniżej.

### Zmieniono

- `scripts/integration_preflight.py` (nowy, tylko odczyt, bez fetch): gałąź
  (domyślnie bieżąca) vs `main` i `origin/main`: ahead/behind, możliwość
  fast-forward, `main` przed/za `origin/main` (z uwagą, że ref zdalny może być
  nieaktualny), stan brudny worktree gałęzi i checkoutu `main`
  (śledzone/nieśledzone), elementy dodane przez gałąź względem wspólnego
  przodka (pliki `ai_docs/tasks/**/NNNN-*.md`, nagłówki `D-NNN` w
  `decisions/DECISION_LOG_*.md`, prefiksy `vX.Y.N` commitów, migracje
  `services/api/alembic/versions/NNNN_*.py`), kolizje numerów z `main` (drzewo i
  historia) oraz z innymi niescalonymi gałęziami lokalnymi, przypomnienie
  „needs operator migration before merge”. Ten sam plik, nagłówek lub commit po
  obu stronach to jeden element, nie kolizja. Sekcja informacyjna pokazuje
  kolizje innych gałęzi z `main`. Wyjście tekstowe i `--json` (ASCII), kod 0
  zawsze poza błędem git (kod 1). Opcje: `BRANCH`, `--base`, `--remote`,
  `--root`.
- `services/worker/tests/test_integration_preflight_script.py` (28 testów na
  tymczasowych repozytoriach git).
- `.claude/skills/merge-to-main/SKILL.md` i bajtowo identyczna kopia
  `.agents/skills/merge-to-main/SKILL.md`: kroki preflight, zgoda, aktualizacja
  gałęzi, konflikty w nowych formatach okna i indeksu decyzji, `docs:check`,
  zapis hashy (`close_task.py record-hash`), ponowny preflight, `merge --ff-only`
  w `D:\game_predicotr`, push `main`, odpięcie junction i usunięcie worktree i
  gałęzi, raport. Sekcja „Bramki zgody” nazywa bramki z `AGENTS.md` (akceptacja
  i zgoda na scalenie, push, P0/P1, migracje, usługi, cudze zmiany, operacje
  destrukcyjne, koszt) bez ich osłabiania.
- `scripts/check_skill_mirrors.py`: druga para lustrzana.

### Weryfikacja

- Nowe testy: 28 passed; razem z `test_close_task_script.py`,
  `test_check_skill_mirrors_script.py`, `test_check_current_state_window_script.py`,
  `test_check_startup_read_budget_script.py`, `test_check_decision_links_script.py`:
  78 passed (`--basetemp D:/ptw3`).
- Pokryte kryteria: fast-forward możliwy i niemożliwy, kolizja TASK (także z
  inną gałęzią), D, `vX.Y.N` (z `main` i z inną gałęzią, wspólny commit bez
  kolizji), migracji, migracja dodana (przypomnienie), `main` przed i za
  `origin/main`, brak refu `origin`, brudne worktree, kody wyjścia, tryb tylko
  do odczytu.
- `ruff check scripts` PASS, `ruff format --check` PASS, `mypy --strict` na
  trzech zmienionych plikach PASS; `prettier --check` obu kopii skilla PASS;
  `npm run docs:check` PASS (`check_skill_mirrors`: 2 pary); `git diff --check`
  PASS.
- Preflight na `feat/stage2-plan`: ahead 2, behind 0, fast-forward możliwy,
  `main` = `origin/main`; kolizje `v1.7.377` i `v1.7.378` z
  `codex/v3-grid-fine-tuning`; brak kolizji TASK/D i brak migracji. TASK-1024 nie
  jest kolizją tej gałęzi (plik jest ten sam na `main` i na gałęzi V3);
  informacyjnie wychodzą kolizje `v1.7.361–376`, D-548 i migracji `0155` gałęzi
  `codex/photo-crop-p1` i `codex/v3-grid-fine-tuning` z `main`.

### Niewykonane

- Pełne `mypy scripts` (całego katalogu) przekroczyło limit 120 s; sprawdzono
  tylko zmienione pliki.
- Skill nie był ćwiczony na prawdziwym scaleniu, push ani usuwaniu worktree
  (zakaz zmian poza testowymi repozytoriami); fragment wyliczania dowiązań
  sprawdzono odczytem na tym worktree (`.venv`, `node_modules`).
- `AGENTS.md` nadal zawiera zdanie „Nie wykonuj automatycznego push”; skill
  godzi je ze zgodą operatora na scalenie przez wymóg, by pytanie o zgodę
  nazywało push. Treść `AGENTS.md` zmieni dopiero TASK-1032.

### Zalecany następny task

Etap B: TASK-1032 (odchudzenie `AGENTS.md`) po poleceniu operatora.
