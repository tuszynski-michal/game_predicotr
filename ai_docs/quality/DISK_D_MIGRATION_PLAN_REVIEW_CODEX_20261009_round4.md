---
title: Przegląd planu przeniesienia na dysk D przez Codex (runda 4)
status: active
last_updated: 2026-10-09
---

# Przegląd planu przeniesienia na dysk D — Codex, runda 4

Audytor: Codex CLI 0.162.0, gpt-6.1-sol / high, `codex exec --sandbox read-only`.
Zakres: plan i taski TASK-0952–0957 po poprawkach z rundy 3. Brief: `artifacts/audits/DISK_D_PLAN_REVIEW_PROMPT_ROUND4.md`.

Werdykt: REVISE

## Rozliczenie rundy 3

Oznaczenia R2/R3 rozróżniają numerację nowych uwag z poprzednich raportów.

| punkt | status | gdzie/co brakuje |
|---|---|---|
| P0-2 — zabezpieczenie ignorowanych danych wszystkich worktree’ów | RESOLVED | TASK-0953, Scope i Acceptance criteria; TASK-0954:63–76,124–133 obejmują zachowywane katalogi i luźne pliki, również głównego checkoutu. Osobną sprzeczność zakresu kopii opisano poniżej. |
| R2 nowe P1-1 — równość raportu po wznowieniu zapisów | RESOLVED | TASK-0955:106–115 sprawdza równość przed provisioningiem i startem usług. TASK-0956:100–105 stosuje później niezmienniki i wyjaśnione różnice. |
| R2 nowe P1-2 — bramka manifestu wobec zmiennego stanu | RESOLVED | TASK-0957:102–119 ogranicza wyłączenia i wymaga dowodu dla pozostałych zmian lub usunięć. Nowe pliki D pozostają poza porównaniem. |
| R2 P2-3 — naprawa rejestracji worktree’ów | RESOLVED | TASK-0957:120–125 wskazuje repozytorium właścicielskie `game_predicotr_old\.git`. Worktree’y D powstają niezależnie. |
| R2 P2-4 — operator a agent | RESOLVED | TASK-0955:58–62,106–110 przypisuje operatorowi start kontenera, a agentowi odczyty i raporty. |
| R3 nowe P1-1 — odbiór derive sprzeczny z opróżnieniem kolejki | RESOLVED | Plan, odbiór pkt 6; TASK-0955:70–75; TASK-0956:109–112 akceptują zakończenie na C albo anulowanie i wznowienie na D. |
| R3 nowe P1-2 — provisioning przed porównaniem raportów | RESOLVED | TASK-0955, krok 9 uruchamia sam PostgreSQL. Provisioning przeniesiono do TASK-0956:72–73, za bramkę równości. |
| R3 nowe P1-3 — repair w niewłaściwym repozytorium | RESOLVED | TASK-0957:120–125 wykonuje naprawę z głównego repozytorium `_old`, zamiast z niezależnego klonu D. |
| R3 nowe P1-4 — wykluczenie trwałych danych `.runtime` | RESOLVED | TASK-0953:43–49,79–83; TASK-0956:65–71; TASK-0957:103–119 zachowują profile, sesje i lokalne manifesty oraz rozliczają ścieżki C. |
| R3 P2-1 — kontrakt `-Manifest` | RESOLVED | TASK-0953:92–99,135–137 definiuje porównanie celu z zapisanym manifestem bez odczytu C i bez odrzucania nowych plików D. |
| R3 P2-2 — lista przekazywana przez `powershell -File` | RESOLVED | TASK-0953:88–91 definiuje rozdzielany przecinkami ciąg i parsowanie. Przykład:183 używa tej postaci. |
| R3 P2-3 — nieaktualne skróty dowodów | PARTIAL | Mapa dowodów poprawiona. `CURRENT_STATE.md:144` nadal wymaga raportu „równego TASK-0952”, zamiast raportowi B1 po zatrzymaniu zapisów. |

## Nowe P0

Brak.

## Nowe P1

1. **Domyślny inwentarz obejmuje `worktrees/`, mimo zakazu kopiowania tego katalogu.**
   [TASK-0953:73](ai_docs/tasks/0953-disk-d-data-directory-sync.md:73) klasyfikuje „wszystko inne” jako zachowywane i domyślnie kopiuje cały ten zbiór. Wyłącza `.claude/worktrees`, lecz pomija `worktrees/`. Tymczasem Out of scope:125 oraz plan, Zakres wyłączony, zabraniają kopiowania worktree’ów jako katalogów.

   Odczyt głównego checkoutu potwierdził ignorowany wpis `worktrees/`. Plik `.git` worktree’a `disk-migration` wskazuje bezwzględnie repozytorium C. Domyślna kopia przeniesie więc na D katalogi z powiązaniami do C, zamiast odtworzyć je zgodnie z planem. Może również zająć ścieżki przeznaczone dla `git worktree add`.

   **Poprawka:** jawnie wyłączyć oba korzenie worktree’ów z kopii głównego checkoutu. Oznaczyć je jako obsługiwane osobno przez TASK-0954; nadal inwentaryzować i zabezpieczać dane każdego worktree’a.

2. **Procedura awaryjna tworzy rolę aplikacyjną przed odtworzeniem globals, a następnie odrzuca jej oczekiwany duplikat.**
   [TASK-0955:155](ai_docs/tasks/0955-disk-d-database-cutover.md:155) uruchamia `npm run db:up` na pustym wolumenie. [package.json:50](package.json:50>) dołącza provisioning. Przy domyślnej konfiguracji tworzy on `game_predictor_app`, zgodnie z [config.py:15](services/api/src/game_predictor_api/config.py:15>) i `provision_application_role`.

   Zrzut globals zawiera tę rolę. Jego odtworzenie zgłosi zatem także `role "game_predictor_app" already exists`. TASK-0955:163–165 dopuszcza taki błąd wyłącznie dla `game_predictor`. Procedura zatrzyma się przed odtworzeniem danych mimo poprawnego zrzutu.

   **Poprawka:** również w procedurze awaryjnej uruchomić sam PostgreSQL przez `docker compose … up -d --wait postgres`. Odtworzyć globals, następnie bazę, a provisioning wykonać dopiero po odtworzeniu.

## P2

- Zaktualizować [CURRENT_STATE.md:144](ai_docs/process/CURRENT_STATE.md:144): porównanie dotyczy raportu B1, nie TASK-0952.
- TASK-0957:131–133: podać pełną ścieżkę w `git -C "C:\Users\tuszy\Documents\game_predicotr_old" worktree remove <ścieżka>`. Wskazany katalog wykonania to D; względne `game_predicotr_old` nie wskazuje repozytorium C.

## Potwierdzone

- Zachowano niezależną kopię VHDX po zamknięciu Docker Desktop/WSL, SHA-256 obu plików i pełny odczyt archiwum logicznego.
- Zachowano zakaz synchronizacji C→D po przełączeniu oraz osobne zgody na operacje destrukcyjne.
- Przyjęto fakty briefu: puste `host_actions` i `batches`, sieć `game-predictor_default`, D jako wewnętrzny NVMe/NTFS z 1857 GB wolnego miejsca.
- To przegląd statyczny, bez zmian w plikach. Nie uruchamiałem usług, kopii, operacji bazodanowych ani testów odtworzenia.