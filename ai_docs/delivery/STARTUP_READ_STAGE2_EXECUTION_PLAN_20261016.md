---
title: Etap 2 odczytu startowego — skille procedur i odchudzenie AGENTS.md oraz README
status: implemented
last_updated: 2026-10-16
---

# Plan: etap 2 — skille procedur, lżejszy `AGENTS.md` i `README.md`

TASK-1030–1033 (zakres zarezerwowany; TASK-1025–1029 pominięte, bo tor V3 na
`codex/v3-grid-fine-tuning` doszedł do TASK-1024 i nadal numeruje). Baza:
`main` v1.7.376 / `0c0f64de`.

## Stan obecny (`main` v1.7.376)

Po etapie 1 (`delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md`) i
TASK-1024 obowiązkowy odczyt ma ok. 65 000 B:

| Plik | Bajty | Uwagi |
|---|---:|---|
| `AGENTS.md` | ~26 800 | największy plik startowy |
| `ai_docs/README.md` | ~17 300 | z tego „Aktywna dokumentacja” ok. 13 000 B (katalog planów i dokumentów) |
| `ai_docs/process/CURRENT_STATE.md` | ~9 300 | po etapie 1 |
| `ai_docs/process/DECISION_LOG.md` | ~10 800 | po etapie 1 |

**Wynik (2026-10-16):** pomiar `scripts/check_startup_read_budget.py --report`
po TASK-1033 (bajty z końcami linii LF; „przed” to wartości tego planu).

| Plik | Przed | Po | Budżet |
|---|---:|---:|---:|
| `AGENTS.md` | ~26 800 | 13 942 | 14 000 |
| `ai_docs/README.md` | ~17 300 | 4 092 | 5 000 |
| `ai_docs/process/CURRENT_STATE.md` | ~9 300 | 9 537 | 30 000 |
| `ai_docs/process/DECISION_LOG.md` | ~10 800 | 10 842 | 12 000 |
| Suma obowiązkowego odczytu | ~65 000 | 38 413 | 45 000 |

Katalog dokumentów przeniesiono do `ai_docs/DOC_INDEX.md` (otwierany na
żądanie, poza odczytem startowym). Różnice `CURRENT_STATE.md` i `DECISION_LOG.md`
względem „przed” wynikają z zaokrągleń planu i bieżących wpisów, nie z tego planu.

Sekcje `AGENTS.md`, które opisują procedury używane tylko w jednym momencie
pracy (pomiar 2026-10-16):

| Sekcja | Bajty | Kiedy potrzebna |
|---|---:|---|
| „Audyt krzyżowy” | 4 888 | tylko przy audycie |
| „Scalanie do gałęzi integracyjnej” | 2 346 | tylko przy scalaniu |
| „Po kodowaniu” | 2 160 | tylko przy zamykaniu taska |
| „Wersjonowanie commitów” | 1 353 | tylko przy commicie |
| „Brudny worktree i zakres commita” | 616 | przy commicie |
| „Oszczędzanie kontekstu” + akapit mapy kodu | ok. 2 200 | szukanie kodu |

Fakty z sesji 2026-10-16, które uzasadniają skille ze skryptami:

- Zamykanie tasków w nowym formacie okna wymagało jednorazowych skryptów w
  scratchpadzie. Ręczne kroki dały dwa błędy: commit z czerwonym
  `docs:check` (linia `done` bez hasha) i edycję złych plików przy kolizji
  numerów TASK.
- `main` przesunął się w trakcie pracy (równoległa sesja), więc planowany
  fast-forward wymagał scalenia i przenumerowania. Kolizje numerów TASK,
  D-, `vX.Y.N` i migracji trzeba było sprawdzać ręcznie.
- Usuwanie worktree z dowiązaniami (junction) `.venv`/`node_modules` grozi
  usunięciem zawartości głównego checkoutu, jeśli dowiązań nie odepnie się
  najpierw.
- W PowerShell polskie cudzysłowy („ ”) w napisach w podwójnym cudzysłowie
  psują parser.

Istniejące skille: `.claude/skills/audit-task` (Claude) i
`.codex/skills/claude-audit` (Codex).

## Cel

Obowiązkowy odczyt startowy ≤ **45 000 B** (z ok. 65 000 B). Procedury
zamykania taska, scalania do `main` i audytu żyją w skillach ładowanych tylko
przy użyciu, a ich powtarzalne kroki wykonują przetestowane skrypty. Żadna
obowiązująca reguła nie ginie.

## Kluczowe decyzje planu

- **E1. Skill = procedura + skrypt.** Skill opisuje kiedy i jak; kroki
  deterministyczne wykonuje skrypt z testami (`scripts/`), nie model.
- **E2. Jedno źródło treści skilla.** Kanoniczna wersja leży w
  `.claude/skills/<nazwa>/SKILL.md`. Kopia dla Codex leży w katalogu, który
  Codex faktycznie wykrywa w repozytorium. TASK-1030 ustala ten katalog
  (`.agents/skills/` według dokumentacji Codex albo dotychczasowy
  `.codex/skills/`) testem na zainstalowanym CLI. Zgodność kopii sprawdza
  `scripts/check_skill_mirrors.py` w `docs:check`. `claude-audit`/`audit-task`
  pozostają różne (kierunek audytu), sprawdzane są tylko pary oznaczone jako
  lustrzane.
- **E3. W `AGENTS.md` zostaje reguła, w skillu procedura.** Każda przeniesiona
  sekcja zostawia w `AGENTS.md` 1–3 zdania wiążące (co jest obowiązkowe, co
  wymaga zgody) i wskazanie skilla. Skille nie mogą osłabiać reguł z
  `AGENTS.md`.
- **E4. `README.md` jako krótkie wejście.** Katalog dokumentów („Aktywna
  dokumentacja”) przechodzi do nowego `ai_docs/DOC_INDEX.md`, otwieranego na
  żądanie (lub przeszukiwanego `rg`). `README.md` zachowuje: cel, wejście do
  zadania, zasadę pojedynczego źródła prawdy, statusy, regułę aktualizacji i
  link do indeksu.
- **E5. Nowe budżety** w `scripts/check_startup_read_budget.py`:

  | Budżet | Wartość | Włącza |
  |---|---:|---|
  | `AGENTS.md` | 14 000 | TASK-1032 |
  | `ai_docs/README.md` | 5 000 | TASK-1033 |
  | suma obowiązkowego odczytu | 45 000 (z 90 000) | TASK-1033 |

- **E6. Skrypt scalania tylko czyta.** `scripts/integration_preflight.py`
  raportuje stan; scalenie, push i usunięcie worktree wykonuje agent według
  skilla, po zgodzie operatora (`AGENTS.md`, „Akceptacja przed scaleniem”).
- **E7. Bez wpisu `DECISION_LOG.md`.** Zmiana procesu dokumentacji, nie
  domeny ani architektury (precedens etapu 1).

## Taski

| Task | Etap | Zakres |
|---|---|---|
| TASK-1030 | A | `scripts/close_task.py` + skill `task-close` (Claude i Codex) + `check_skill_mirrors.py`; ustalenie katalogu skilli Codex |
| TASK-1031 | A | `scripts/integration_preflight.py` + skill `merge-to-main` (Claude i Codex) |
| TASK-1032 | B | `AGENTS.md` ≤ 14 000 B: procedury do skilli, mapa reguła → miejsce |
| TASK-1033 | B | `README.md` ≤ 5 000 B, `ai_docs/DOC_INDEX.md`, nowe budżety, pomiar końcowy |

Etap A dostarcza skille; etap B przenosi do nich treść z `AGENTS.md`, więc B
zależy od A. Start każdego etapu wymaga jawnego polecenia operatora.

## Mapa wymaganie → task → kryterium

| Wymaganie | Task | Kryterium |
|---|---|---|
| zamykanie taska bez ręcznych kroków i błędów formatu | 1030 | testy `close_task.py` (zamknięcie, zapis hasha, kolizja numeru, brak wskaźnika) |
| skille działają w obu klientach | 1030, 1031 | Codex CLI wymienia skille po nazwie; `check_skill_mirrors.py` PASS |
| bezpieczne scalanie do `main` | 1031 | testy preflight (fast-forward/rozbieżność, kolizje TASK/D/`vX.Y.N`/migracji); skill ma bramki zgody i bezpieczne usuwanie worktree |
| `AGENTS.md` ≤ 14 000 B bez utraty reguł | 1032 | budżet wymuszony; tabela reguła → miejsce w `Outcome` |
| `README.md` ≤ 5 000 B, suma ≤ 45 000 B | 1033 | budżety wymuszone; `docs:check` PASS |

## Ryzyka

- Agent nie załaduje skilla i pominie procedurę. Ograniczenie: zdanie
  wiążące w `AGENTS.md` nazywa skill i warunek użycia (E3); opisy skilli
  mają wyraźne wyzwalacze.
- Codex może nie wykrywać skilli w repozytorium w obecnej wersji; wtedy
  TASK-1030 zostawia kopię w `.codex/skills/` i zapisuje wynik testu.
- Równoległe gałęzie edytują `AGENTS.md`; TASK-1032 wykonać tuż przed
  scaleniem, po synchronizacji z `main`.

## Poza zakresem

- Nowe indeksy kodu, MCP, LSP (Serena, CodeGraph, Graphify) — bez pomiaru
  korzyści na tym repozytorium.
- Skille domenowe (diagnostyka pipeline siatek, migracje) — kandydaci na
  etap 3 po pomiarze etapu 2.
- Zmiana treści reguł (np. polityki audytu) — tylko przeniesienie.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1030 — `close_task.py`, skill `task-close`, lustra skilli | claude-sonnet-5-5 | high | Skrypt modyfikujący dokumenty procesu z testami i ustalenie zachowania Codex CLI; błąd psuje zamykanie każdego taska. Eskalacja do claude-opus-5-5 / high, jeśli Codex nie wykrywa skilli w żadnym katalogu. | nie: samokontrola kryteriów w `Outcome` |
| TASK-1031 — `integration_preflight.py`, skill `merge-to-main` | claude-sonnet-5-5 | high | Skrypt tylko do odczytu, ale skill prowadzi scalenie, push i usuwanie worktree; potrzebne dokładne bramki zgody. | nie: samokontrola kryteriów w `Outcome` |
| TASK-1032 — odchudzenie `AGENTS.md` | claude-opus-5-5 | high | Przenoszenie wiążących reguł procesu; pominięcie reguły zmienia zachowanie wszystkich agentów. | tak: gpt-6.1-sol / medium (Codex, `scripts/audit_task.ps1`); operator może z niego zrezygnować |
| TASK-1033 — `README.md`, `DOC_INDEX.md`, budżety, pomiar | claude-sonnet-5-5 | medium | Mechaniczne przeniesienie katalogu i włączenie budżetów według wzorca etapu 1. | nie: samokontrola kryteriów w `Outcome` |
