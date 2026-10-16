# TASK-1022 — Zastosowanie budżetów `CURRENT_STATE.md`

## Status

`done`

## Goal

`CURRENT_STATE.md` ma najwyżej 30 000 B i mieści się w budżetach sekcji z planu,
treść usunięta z okna jest bez zmian w archiwum, a reguła zamykania taska
utrzymuje nowy format.

## Context

Plan `ai_docs/delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md`, etap C,
decyzje D2–D4, D6, D7. Klasyfikację punktów i sekcji zatwierdził operator w
raporcie TASK-1021.

## Dependencies / entry conditions

- TASK-1021 z zapisaną decyzją operatora. Rozbieżność między raportem a
  bieżącym oknem (nowe sekcje dopisane po raporcie) klasyfikować tą samą
  regułą i wymienić w `Outcome`; nowe ograniczenia operacyjne bez decyzji
  operatora zostają w pełnej treści.
- Gałąź zsynchronizowana z aktualnym czubkiem gałęzi docelowej tuż przed
  wykonaniem.

## Recommended execution

claude-sonnet-5-5 / high. Duże przeniesienie treści z dowodem i zmiana reguły
zamykania tasków używanej przez wszystkich agentów. Eskalacja do
claude-opus-5-5 / high, jeśli dowód multizbioru nie przechodzi. Bez audytu Codex (decyzja operatora
2026-10-16); wykonawca robi samokontrolę kryteriów akceptacji i zapisuje ją w
`Outcome`.

## Relevant docs

- `AGENTS.md` (sekcje „Obowiązkowa kolejność czytania”, „Po kodowaniu” 3)
- `ai_docs/README.md` (sekcje „Wejście do zadania”, „Reguła aktualizacji”)
- `ai_docs/process/CURRENT_STATE.md`, `ai_docs/archive/CURRENT_STATE_2026Q4.md`
  (tylko początek pliku, `offset`/`limit`)
- `ai_docs/quality/CURRENT_STATE_REVIEW_<data>.md` (raport TASK-1021)
- `ai_docs/delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md`
- `ai_docs/tasks/completed/0938-process-docs-rolling-window.md` (metoda dowodu)

## Scope

- `CURRENT_STATE.md` według zatwierdzonego raportu:
  - „Obowiązujące ograniczenia”: punkty `zostaje` skrócone do zatwierdzonej
    treści; `archiwum` i pełne wersje skracanych punktów przeniesione bez
    zmian do archiwum; `do task` przeniesione do pliku taska (sekcja
    „Ograniczenia z CURRENT_STATE”) z odnośnikiem;
  - „Plany z niezakończonymi taskami”: tabela (plan, status, pozostałe taski,
    gałąź); podsekcje planów w pełnej treści do archiwum;
  - „Aktywne taski”: każda sekcja ≤ 1 200 B według D7; usunięte bloki
    (np. historia TASK-0290, iteracje TASK-0472) do archiwum bez zmian;
    nagłówek każdej sekcji zachowuje `TASK-NNNN` (kontrola okna);
  - „Ostatnie 10 ukończonych tasków”: 10 wpisów jednowierszowych (D6); pełne
    sekcje `done` do archiwum bez zmian;
  - nagłówek okna: nowa reguła utrzymania; punkt w „Obowiązujących
    ograniczeniach” o nowym formacie dla innych otwartych gałęzi.
- Archiwum: bloki dopisane na początku `ai_docs/archive/CURRENT_STATE_2026Q4.md`
  (lub nowego pliku kwartału, jeśli data wykonania to 2027Q1 lub później;
  wtedy aktualizacja `ai_docs/archive/README.md`).
- Reguły:
  - `AGENTS.md` „Po kodowaniu” 3: przy zamknięciu pełna sekcja `done` idzie
    na początek najnowszego archiwum, do okna trafia wiersz D6 (najstarszy
    ponad 10 usunięty z okna, jego pełna sekcja już jest w archiwum); sekcja
    aktywna ≤ 1 200 B; `npm run docs:check`;
  - `AGENTS.md` „Obowiązkowa kolejność czytania” pkt 2: opis okna;
  - `ai_docs/README.md`: te same zmiany;
  - wzmianki w `ai_docs/process/AI_DRIVEN_DEVELOPMENT.md`,
    `ai_docs/process/DEFINITION_OF_DONE.md` i skillach audytu
    (`.claude/skills/audit-task/SKILL.md`, `.codex/skills/claude-audit/SKILL.md`),
    jeśli opisują stary format.
- Skrypty:
  - `scripts/check_current_state_window.py`: limit `done` liczony z wierszy
    D6 w sekcji „Ostatnie 10 ukończonych tasków” (≤ 10, format sprawdzany),
    usunięty limit 100 000 B; kontrola sekcji aktywnych tasków bez zmian;
  - `scripts/check_startup_read_budget.py`: włączone budżety
    `CURRENT_STATE.md` z D3 (wartości po ewentualnej zmianie zatwierdzonej w
    TASK-1021);
  - testy: pozytywny dla nowego formatu, negatywne dla 11 wierszy `done`,
    sekcji aktywnej > 1 200 B i pliku > 30 000 B.

## Out of scope

- Zmiana sensu ograniczeń, statusów tasków i planów poza zatwierdzonym raportem.
- Naprawa rozbieżności statusów wykrytych w TASK-1021.

## Acceptance criteria

- [ ] `CURRENT_STATE.md` ≤ 30 000 B; wszystkie budżety sekcji D3 spełnione.
- [ ] Dowód multizbioru bloków: (okno przed) = (bloki okna po, które istniały przed) + (bloki dopisane do archiwum i plików tasków); nowe bloki okna (skróty, wiersze D6, tabela planów) wymienione z liczbą.
- [ ] Każdy plik aktywnego taska ma sekcję w oknie; `npm run docs:check` PASS z włączonymi budżetami.
- [ ] Reguła zamykania w `AGENTS.md` i `README.md` opisuje nowy format; brak sprzecznych wzmianek w dokumentach procesu i skillach audytu.
- [ ] Raport `--report` przed i po w `Outcome`.

## Technical notes

- Skrót punktu ograniczenia zachowuje: co jest zabronione lub wymagane, kogo
  dotyczy, źródło (link do archiwum lub taska).
- Przykład wpisu D6:
  `- **TASK-1007** — Trwałe wykrywanie Claude Code CLI — v1.7.361 / baf67dbd — tasks/completed/1007-claude-cli-discovery.md`.
- Wiersze D6 dla dziesięciu obecnych sekcji `done` budować z ich treści
  (wersja i hash commita implementacji lub zamknięcia).

## Expected files

- Istniejące: `ai_docs/process/CURRENT_STATE.md`,
  `ai_docs/archive/CURRENT_STATE_2026Q4.md`, `AGENTS.md`, `ai_docs/README.md`,
  `scripts/check_current_state_window.py`, `scripts/check_startup_read_budget.py`,
  testy skryptów w `services/worker/tests/`, wybrane pliki aktywnych tasków,
  wzmianki w dokumentach procesu i skillach audytu.

## Verification

```powershell
# katalog worktree (z dowiązaniem .venv), timeout 120 s
.\.venv\Scripts\python.exe scripts/check_startup_read_budget.py --report
.\.venv\Scripts\python.exe -m pytest services/worker/tests -k "check_current_state or startup_read" -q
.\.venv\Scripts\python.exe -m ruff check scripts/check_current_state_window.py scripts/check_startup_read_budget.py
.\.venv\Scripts\python.exe -m mypy --strict scripts/check_current_state_window.py scripts/check_startup_read_budget.py
npx prettier --check AGENTS.md
npm run docs:check
```

## Risks / open questions

- Równoległe gałęzie dopisują sekcje w starym formacie; po scaleniu wymagają
  przepisania hunków (punkt w ograniczeniach).
- Pliki tasków rosną o przeniesione ograniczenia; to akceptowane, bo czyta
  się je tylko przy pracy nad tym taskiem.

## Outcome

Wykonawca: claude-sonnet-5-5 (subagent). Bez audytu Codex (decyzja operatora
2026-10-16). Kontrola leada (claude-opus-5-5): ponowne `npm run docs:check`,
20 testów skryptów PASS, ponowny dowód (402/406 bloków dosłownie; 4 brakujące
to celowo zmienione front matter, dwa akapity starej reguły i nagłówek
TASK-1022 `(todo)`). Commit: v1.7.370 / `138005341bfde8b4ae7ccf8e89265542dd2bf882`.

### Changed

- `ai_docs/process/CURRENT_STATE.md` 90 029 B → 23 204 B według raportu
  TASK-1021 (sekcje 1–4): 17 punktów ograniczeń (11 skróconych `zostaje`, 5
  skrótów `operator` O1–O5, punkt o nowym formacie dla innych gałęzi), tabela
  10 planów, 23 wskaźniki aktywnych tasków (największy 653 B), 10 wierszy
  `done` w formacie D6, nowy nagłówek z regułą utrzymania, pytania R1–R15 z
  sekcji 5 raportu jako jedna pozycja w „Otwartych decyzjach i pytaniach”
  (bez napraw).
- `ai_docs/archive/CURRENT_STATE_2026Q4.md`: na początku sekcja „Przeniesione
  z okna 2026-10-16 (TASK-1022)” z niezmienionymi punktami ograniczeń
  (oprócz „do task”), podsekcjami planów, 43 pełnymi sekcjami aktywnych
  tasków i 10 pełnymi sekcjami `done`.
- Sekcja „Ograniczenia z CURRENT_STATE” (punkty `do task` bez zmian) w plikach:
  `completed/0975-symbol-training-rejected-split-recovery.md` (pkt 6), `0947`
  (11), `0972` (16), `0928` (18, 19), `0937` (31), `0645`/`0646`/`0647` (33),
  `0668`/`0671` (35), `0603`/`0654`/`0290` (36).
- `AGENTS.md` („Obowiązkowa kolejność czytania” 2, „Po kodowaniu” 3),
  `ai_docs/README.md` (Wejście do zadania, Proces i jakość, Reguła
  aktualizacji): nowa reguła zamykania.
- `scripts/check_current_state_window.py`: wpisy `done` to wiersze D6
  (≤ 10, format regex), usunięty limit 100 000 B. `scripts/check_startup_read_budget.py`:
  `enforced=True` dla pięciu budżetów `CURRENT_STATE.md`. Testy: nowy
  `services/worker/tests/test_check_current_state_window_script.py` (7),
  4 nowe w `test_check_startup_read_budget_script.py`.

### Verification results

- Dowód multizbioru (skrypt poza repo, `scratchpad/prove.py`): podział na
  bloki od każdego nagłówka `#`/`##`/`###` i każdego punktu `- ` poza blokami
  kodu. Stare okno (HEAD): 406 bloków; 36 zostało w oknie bez zmian, 357
  znaleziono bez zmian w dopiskach archiwum, 9 w dopiskach plików tasków:
  402/406 dosłownie. Cztery wymienione celowo: front matter (data), dwa
  akapity nagłówka (stara reguła utrzymania) i nagłówek „TASK-1022 (todo)” →
  `(in_progress)`. Nowe bloki okna: 66 (skróty ograniczeń i O1–O5, punkt o
  formacie, tabela planów, notka o planie Reviewera, pozycja R1–R15, 17
  nagłówków/wskaźników, wiersze D6 i nowy nagłówek). Dopiski spoza starego
  okna: nagłówek i akapity sekcji w archiwum oraz akapity w plikach tasków;
  kopie punktów `do task` w wielu plikach (33, 35, 36) to celowe duplikaty.
- Raport przed → po (`check_startup_read_budget.py --report`): `CURRENT_STATE.md`
  90 029 → 23 204 B (budżet 30 000); ograniczenia 20 327 → 5 446 (8 000);
  plany 8 180 → 1 732 (5 000); otwarte decyzje 1 015 → 2 843; aktywne taski
  48 866 → 9 807, najdłuższa sekcja 653 B (1 200); done 11 286 → 1 651,
  najdłuższy wpis 189 B (400); suma odczytu startowego 143 897 → 78 047 B
  (cel 90 000 w TASK-1023). Zapisy: `report_before.txt`/`report_after.txt` w scratchpadzie.
- `npm run docs:check` PASS (44 plików aktywnych tasków, 10 wpisów done, 7 z 9
  budżetów wymuszone); pytest obu plików testów 17 passed; `ruff check`,
  `ruff format --check`, `mypy --strict` skrypty i testy PASS;
  `prettier --check AGENTS.md` PASS; `git diff --check` bez błędów
  (tylko ostrzeżenia LF/CRLF środowiska).

### Not completed

- Pytania R1–R15 z raportu pozostają otwarte (bez napraw). Statusy: TASK-0939
  zapisano jako `blocked` zgodnie z propozycją raportu (R3 otwarte).
- Nie zsynchronizowano z `codex/v3-grid-fine-tuning` ani `main` (to warunek
  wejścia przed scaleniem, wykonuje lead).
- Wzmianki w `AI_DRIVEN_DEVELOPMENT.md`, `DEFINITION_OF_DONE.md` i skillach
  audytu nie opisują starego formatu okna, więc ich nie zmieniano.

### Documentation updates

- `AGENTS.md`, `ai_docs/README.md`, nagłówek `CURRENT_STATE.md`.

### Deviations from the report

- TASK-0305 i TASK-0802 zostały bez zmian (już ≤ 1 200 B, nic nie ginie).
- Punkty `do task` leżą tylko w plikach tasków (nie w archiwum), żeby dowód
  multizbioru był jednoznaczny; punkt 36 w trzech plikach, 33 w trzech, 35 w dwóch.
- Tabela planów ma 10 wierszy: dodano plan V3 (stan z tej gałęzi) i cztery
  plany bez podsekcji; plan Reviewera tylko jako notka (archiwum, R7).

### Self-check of acceptance criteria

- [x] `CURRENT_STATE.md` ≤ 30 000 B (23 204), budżety D3 spełnione.
- [x] Dowód multizbioru: 402/406 dosłownie, 4 wymienione, nowe bloki (66) wymienione.
- [x] Każdy aktywny task ma sekcję; `docs:check` PASS z włączonymi budżetami.
- [x] Reguła zamykania w `AGENTS.md` i `README.md` opisuje nowy format; brak
      sprzecznych wzmianek w dokumentach procesu i skillach.
- [x] Raport `--report` przed i po zapisany powyżej.

### Recommended next task

TASK-1023 (`CLAUDE.md` bez duplikatu i końcowy pomiar).
