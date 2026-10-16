# TASK-1032 — `AGENTS.md` ≤ 14 000 B: procedury do skilli

## Status

`done`

## Goal

`AGENTS.md` ma najwyżej 14 000 B, zawiera wszystkie reguły wiążące w krótkiej
formie, a procedury zamykania taska, scalania i audytu są w skillach; budżet
jest wymuszany.

## Context

Plan `delivery/STARTUP_READ_STAGE2_EXECUTION_PLAN_20261016.md`, etap B,
decyzja E3. `AGENTS.md` ma ok. 26 800 B i jest czytany przez każdą sesję,
wykonawcę i audytora; ok. 13 500 B to procedury potrzebne tylko w jednym
momencie pracy (tabela sekcji w planie).

## Dependencies / entry conditions

- TASK-1030 i TASK-1031 ukończone (skille `task-close`, `merge-to-main`).
- Gałąź zsynchronizowana z `main` tuż przed wykonaniem.

## Recommended execution

claude-opus-5-5 / high. Review: gpt-6.1-sol / medium przez
`scripts/audit_task.ps1` (operator może zrezygnować).

## Relevant docs

- `AGENTS.md`, `CLAUDE.md`
- `.claude/skills/audit-task/SKILL.md`, `.codex/skills/claude-audit/SKILL.md`
  (lub nowy katalog Codex z TASK-1030)
- `.claude/skills/task-close/SKILL.md`, `.claude/skills/merge-to-main/SKILL.md`
- `ai_docs/delivery/STARTUP_READ_STAGE2_EXECUTION_PLAN_20261016.md`

## Scope

- Przenieść szczegóły do skilli, zostawiając w `AGENTS.md` 1–3 zdania
  wiążące i nazwę skilla:
  - „Audyt krzyżowy” → skille audytu (wykrywanie CLI, parametry skryptu,
    format raportu, limity czasu); w `AGENTS.md`: audytor z innej rodziny,
    tylko gdy wskazuje go plan, P0/P1 blokują commit, jedna runda;
  - „Scalanie do gałęzi integracyjnej” → `merge-to-main`; w `AGENTS.md`:
    `main`, scalenie i push tylko po akceptacji wyniku całego zleconego
    zakresu, migracje przed scaleniem;
  - „Wersjonowanie commitów”, „Brudny worktree”, „Po kodowaniu” →
    `task-close`; w `AGENTS.md`: osobny commit `vX.Y.N` na task, tylko hunki
    taska, zamknięcie przez skill;
  - „Oszczędzanie kontekstu” i akapit mapy kodu: skrócić do jednego akapitu.
- Pozostałe sekcje (zasady nadrzędne, budżet tokenów i zgody, usługi,
  trwałość, limity czasu, testy, operacje danych, hierarchia źródeł) zostają;
  dozwolone tylko skróty bez zmiany sensu.
- `scripts/check_startup_read_budget.py`: budżet `AGENTS.md` 14 000 B
  wymuszony; test negatywny.
- Odwołania do przeniesionych sekcji w innych dokumentach (`rg` po nazwach
  sekcji w `ai_docs/`, `CLAUDE.md`, skillach) przepiąć na skill.

## Out of scope

- Zmiana treści reguł lub polityk (np. modelu audytora).

## Acceptance criteria

- [ ] `AGENTS.md` ≤ 14 000 B; budżet wymuszony; `docs:check` PASS.
- [ ] Tabela w `Outcome`: każda reguła (zdanie z „musi”, „nie”, „wymaga”, „tylko”) z poprzedniej wersji → miejsce po zmianie (`AGENTS.md` sekcja albo skill); brak reguł bez miejsca.
- [ ] Brak martwych odwołań do usuniętych nagłówków.
- [ ] Review Codex PASS albo jawna rezygnacja operatora.

## Expected files

- Istniejące: `AGENTS.md`, `CLAUDE.md` (odwołania), skille z TASK-1030/1031,
  skille audytu, `scripts/check_startup_read_budget.py`, test budżetu.

## Verification

```powershell
# katalog worktree z dowiązaniem .venv, timeout 120 s
.\.venv\Scripts\python.exe scripts/check_startup_read_budget.py --report
npx prettier --check AGENTS.md
npm run docs:check
```

## Risks / open questions

- Agent bez załadowanego skilla może pominąć procedurę; zdanie wiążące w
  `AGENTS.md` musi nazywać skill i moment użycia.

## Outcome

Commit: v1.7.381 / `676f22f42b7e28ba82476471247aea828e4ed604`.

Wykonawca: claude-opus-5-5 / high (subagent). Audyt Codex gpt-6.1-sol / medium
(`scripts/audit_task.ps1`): PASS, bez otwartych P0/P1
(`ai_docs/quality/TASK-1032_AUDIT_gpt-6.1-sol.md`). Task zamknął lead skryptem
`close_task.py`.

### Wynik

- `AGENTS.md`: 26 404 B → 13 942 B (pomiar z LF, `file_size` w
  `scripts/check_startup_read_budget.py`; na dysku z CRLF przed zmianą
  26 822 B). Wszystkie dotychczasowe nagłówki zostają, więc odwołania w
  `CURRENT_STATE.md`, `close_task.py`, skillach i `guides/TOKEN_TOOLING.md`
  nie są martwe. Usunięty jest tylko komentarz `<!-- [mapa kodu] -->`
  (wariant `rules` protokołu pilota nakłada `AGENTS.md` z commita pilota, nie
  bieżący plik).
- Przeniesienia:
  - „Audyt krzyżowy” → nowa sekcja „Zasady (z `AGENTS.md`, „Audyt krzyżowy”)”
    w `.claude/skills/audit-task/SKILL.md` i `.codex/skills/claude-audit/SKILL.md`
    (wspólne: wymóg z kolumny `Dodatkowy review` i rezygnacja operatora, inna
    rodzina, audytor zastępczy, skład briefu, przegląd statyczny, szybki audyt,
    limit 600/480 s, format raportu, zapis hasha, poświadczenia; kierunkowe:
    parametry Codex CLI w `audit-task`, wykrywanie Claude Code CLI w
    `claude-audit`). W `AGENTS.md` zostaje akapit wiążący.
  - „Scalanie do gałęzi integracyjnej” → `merge-to-main` (dodane: dawna gałąź
    `v1.1-…`, praca na gałęzi roboczej, niezależne blokery w bramce 1, push
    objęty zgodą na scalenie w bramce 2 i kroku 9, potwierdzenie
    `merge-base --is-ancestor` w kroku 11). Kopia `.agents/skills/merge-to-main`.
  - „Wersjonowanie commitów”, „Brudny worktree i zakres commita”, „Po
    kodowaniu” → `task-close` (nowe sekcje „Kolejność zamykania”,
    „Wersjonowanie commitów”, „Brudny worktree i zakres commita”; regeneracja
    mapy kodu). W `AGENTS.md` zostają krótkie reguły, lista 1–8 i pełny punkt 8
    (zatrzymanie etapu). Kopia `.agents/skills/task-close`.
  - „Oszczędzanie kontekstu” i akapit mapy kodu → jeden akapit w
    „Oszczędzanie kontekstu”.
- Budżet `AGENTS.md` 14 000 B wymuszony (`Budget("AGENTS.md", 14_000, True, …)`
  z podpowiedzią), dziewięć dotychczasowych budżetów bez zmian; testy negatywne
  `test_default_flags_fail_on_agents_over_14000_bytes` i
  `test_agents_budget_measures_lf_line_endings`.
- Odwołania: `scripts/audit_task.ps1` (opis `-Effort` wskazuje skill
  `audit-task`), `ai_docs/process/PLAN_STANDARD.md` („osobny audyt (gdy wymaga
  go plan)”), `ai_docs/process/CURRENT_STATE.md` (ograniczenie „Akceptacja
  przed scaleniem”: zgoda na scalenie obejmuje push). `CLAUDE.md` bez zmian
  (5 911 B; odwołania aktualne).

### Reguły zmienione decyzjami operatora

- Push: dawne „Nie wykonuj automatycznego push” (sekcje „Scalanie…” i „Po
  kodowaniu” 8) → `AGENTS.md` „Scalanie…”: zgoda na scalenie obejmuje push
  `main` do origin, bez niej push nie następuje; „Po kodowaniu” 8: push nigdy
  nie jest automatyczny; `merge-to-main` bramka 2 i krok 9.
- Scalanie tylko po akceptacji wyniku całego zleconego zakresu; kod z
  niewykonaną migracją nie jest scalany (treść bez zmian, skrócona).
- Audyt: dawne „wymagany po każdym tasku, który wskazuje go w kolumnie
  `Dodatkowy review`” → „wymagany tylko, gdy wskazuje go kolumna; operator może
  zrezygnować dla planu lub taska (zapis w `Outcome`)”; „Po kodowaniu” 8: „po
  audycie (jeśli wymagany)”. Ta sama treść w obu skillach audytu.

### Mapa reguła → miejsce

Skróty: AG = `AGENTS.md`; TC = `.claude/skills/task-close/SKILL.md` (+ kopia
`.agents/`); MM = `.claude/skills/merge-to-main/SKILL.md` (+ kopia `.agents/`);
AU = `.claude/skills/audit-task/SKILL.md` i `.codex/skills/claude-audit/SKILL.md`.
Stara sekcja w nawiasie kwadratowym.

| # | Reguła (stara wersja, skrót) | Miejsce po zmianie |
|---|---|---|
| 1 | [Cel] `ai_docs/` jest źródłem prawdy produktu, architektury i etapu | AG „Cel dokumentu” |
| 2 | [Kolejność] Przed każdym zadaniem przeczytaj pliki 1–6 | AG „Obowiązkowa kolejność czytania” 1–6 |
| 3 | [Kolejność] `CURRENT_STATE.md` to okno ≤ 30 000 B (ograniczenia, plany, wskaźniki ≤ 1 200 B, 10 wpisów `done`) | AG „Obowiązkowa kolejność czytania” 2 (format w nagłówku `CURRENT_STATE.md`, limity w `check_startup_read_budget.py`) |
| 4 | [Kolejność] `DECISION_LOG.md`: indeks 30; starsze przez `rg` w nim i w archiwum indeksu; pełny wpis przez kotwicę | AG „Obowiązkowa kolejność czytania” 3 |
| 5 | [Mapa kodu] Szukając kodu, zacznij od `CODE_MAP.md`, potem `rg` na `CODE_MAP_SYMBOLS.md`, potem plik z `offset`/`limit` (pilot) | AG „Oszczędzanie kontekstu” |
| 6 | [Mapa kodu] Aktualność mapy sprawdza `npm run code-map:check` poza `docs:check` i `quality` | TC „Kolejność zamykania” 2 |
| 7 | [Mapa kodu] Task zmieniający moduł lub publiczny symbol regeneruje mapę i dołącza ją do commita | AG „Oszczędzanie kontekstu”; TC „Kolejność zamykania” 2 |
| 8 | [Kolejność] Nie czytaj całej dokumentacji bez potrzeby; otwieraj `Relevant docs` | AG „Obowiązkowa kolejność czytania”, akapit pod listą |
| 9 | [Kolejność] Nie wczytuj `tasks/completed/` ani `archive/` bez jawnego odwołania zadania | jw. |
| 10 | [Kolejność] Pełne wpisy decyzji i archiwa stanu tylko na żądanie (`Relevant docs` albo ocena sprzeczności) | jw. |
| 11 | [Kolejność] Archiwów nie czytaj w całości; szukaj skryptem lub `grep` | jw. |
| 12 | [Nadrzędne] Przed planem przeczytaj w całości `PLAN_STANDARD.md`, zastosuj kontrolę i `TASK_TEMPLATE.md`; link nie zastępuje odczytu | AG „Zasady nadrzędne” |
| 13 | [Nadrzędne] Komunikacja i plany po polsku, chyba że użytkownik poprosi inaczej | AG „Zasady nadrzędne” |
| 14 | [Nadrzędne] Instrukcje w języku dokumentu; nie tłumacz identyfikatorów, kodu, dokumentacji | AG „Zasady nadrzędne” |
| 15 | [Nadrzędne] Czat w stylu `caveman lite` (bez wstępów, grzeczności, powtórzeń, asekuracji, narracji przed narzędziami; zwięzłe pełne zdania) | AG „Zasady nadrzędne” |
| 16 | [Nadrzędne] Styl tylko w rozmowie; kod, komendy, błędy, dokumentacja, commity, taski, `Outcome`, `DECISION_LOG.md` normalnie | AG „Zasady nadrzędne” |
| 17 | [Nadrzędne] Wyjście ze stylu: bezpieczeństwo, operacje nieodwracalne, wieloetapowe instrukcje, „stop caveman”/„normal mode” | AG „Zasady nadrzędne” |
| 18 | [Nadrzędne] Agent ze skillem `caveman` uruchamia go z poziomem `lite` | AG „Zasady nadrzędne” |
| 19 | [Nadrzędne] Ostatnia sekcja planu musi być `Przypisanie modeli do zadań` z pełną tabelą | AG „Zasady nadrzędne” |
| 20 | [Nadrzędne] Każdy task ma własny wiersz z dokładnym modelem i reasoning; nie wolno „ten sam model” | AG „Zasady nadrzędne” |
| 21 | [Nadrzędne] Reguły doboru określa `PLAN_STANDARD.md` | AG „Zasady nadrzędne” |
| 22 | [Nadrzędne] Nie rozszerzaj zakresu bez wyraźnej potrzeby | AG „Zasady nadrzędne” |
| 23 | [Nadrzędne] Domyślnie implementuj wyłącznie wskazany task | AG „Zasady nadrzędne” |
| 24 | [Nadrzędne] Polecenie etapu obejmuje jego taski i delegowanie według tabeli | AG „Zasady nadrzędne” |
| 25 | [Nadrzędne] Sama tabela nie jest zgodą na delegowanie | AG „Zasady nadrzędne” |
| 26 | [Nadrzędne] Plan bez etapów: zatrzymanie po tasku, chyba że polecono cały plan | AG „Zasady nadrzędne” |
| 27 | [Nadrzędne] Przed kodowaniem ponownie przeczytaj task i fragment planu | AG „Zasady nadrzędne” |
| 28 | [Nadrzędne] Sprzeczność taska z planem zgłoś przed implementacją | AG „Zasady nadrzędne” |
| 29 | [Nadrzędne] Nie podejmuj ukrytych decyzji produktowych; zapisz je | AG „Zasady nadrzędne” |
| 30 | [Nadrzędne] Deterministyczna kolejność; `sequence_number` jest domeną | AG „Zasady nadrzędne” |
| 31 | [Nadrzędne] Nie uruchamiaj kalkulacji targetu przed jednoznaczną pozycją | AG „Zasady nadrzędne” |
| 32 | [Nadrzędne] Obrazy jako ścieżka i metadane, nie bloby | AG „Zasady nadrzędne” |
| 33 | [Nadrzędne] Schemat bazy wyłącznie przez Alembic | AG „Zasady nadrzędne” |
| 34 | [Nadrzędne] Kontrakt API z backendu i OpenAPI; frontend nie może ręcznie rozbieżnych typów | AG „Zasady nadrzędne” |
| 35 | [Nadrzędne] Komendy działają na Windows PowerShell | AG „Zasady nadrzędne” |
| 36 | [Nadrzędne] Nie wykonuj destrukcyjnych operacji bez zgody | AG „Zasady nadrzędne” |
| 37 | [Nadrzędne] Nie dodawaj Redis/Celery, mikroserwisów, chmury bez pomiaru | AG „Zasady nadrzędne” |
| 38 | [Budżet] Zasada obowiązuje wszystkich agentów, subagentów, wykonawców, audytorów | AG „Budżet tokenów…”, zdanie wstępne |
| 39 | [Budżet] Przed zmianą ~10% pakietu agent musi ostrzec i uzyskać wyraźną zgodę | AG „Budżet tokenów…” 1 |
| 40 | [Budżet] Do odpowiedzi nie zaczyna kosztownej implementacji, delegowania, audytów, szerokich testów | AG „Budżet tokenów…” 1 |
| 41 | [Budżet] Ostrzeżenie musi zawierać zakres, powód, czas, szacunek | AG „Budżet tokenów…” 1 |
| 42 | [Budżet] Nie podawaj zmyślonych procentów | AG „Budżet tokenów…” 1 |
| 43 | [Budżet] Bez wiarygodnego szacunku także ostrzeżenie i zgoda | AG „Budżet tokenów…” 1 |
| 44 | [Budżet] Koszt obejmuje agenta, subagentów, audyty, odczyty, kontrole | AG „Budżet tokenów…” 2 |
| 45 | [Budżet] Nie dziel zadania, by obejść zgodę | AG „Budżet tokenów…” 2 |
| 46 | [Budżet] „Kontynuuj”/„dokończ”/„pracuj samodzielnie” nie zastępują zgody bez ostrzeżenia | AG „Budżet tokenów…” 2 |
| 47 | [Budżet] Zatwierdzony zakres nie upoważnia do nieograniczonego zużycia | AG „Budżet tokenów…” 2 |
| 48 | [Budżet] Przy wzroście kosztu zatrzymaj kosztowną część, podaj wynik, uzyskaj zgodę | AG „Budżet tokenów…” 3 |
| 49 | [Budżet] Przestrzegaj limitów czasu i budżetu użytkownika | AG „Budżet tokenów…” 3 |
| 50 | [Budżet] Wykorzystuj aktualne wyniki zamiast powtarzać audyty i testy | AG „Budżet tokenów…” 3 |
| 51 | [Kontekst] Pilot TASK-0939 obowiązuje do czasu pomiaru | AG „Oszczędzanie kontekstu” |
| 52 | [Kontekst] Szeroką eksplorację deleguj subagentowi na tańszym modelu | AG „Oszczędzanie kontekstu” |
| 53 | [Kontekst] Subagent zwraca ścieżkę, symbol, linie, 1–3 zdania, nie zrzuty | AG „Oszczędzanie kontekstu” |
| 54 | [Kontekst] Brief audytu zawiera wyłącznie plik taska, fragment planu i diff (`audit_task.ps1`) | AU „Zasady” (brief) i „Ograniczenia” |
| 55 | [Kontekst] Nie wklejaj całych dokumentów procesu do promptów; podaj ścieżkę i zakres | AG „Oszczędzanie kontekstu”; AU „Ograniczenia” |
| 56 | [Kontekst] Plik > 200 KB tylko z `offset`/`limit`; hook odrzuca inny odczyt | AG „Oszczędzanie kontekstu” |
| 57 | [Kontekst] Wyłączenie hooka i narzędzia pilotowe: `guides/TOKEN_TOOLING.md` | AG „Oszczędzanie kontekstu” (odnośnik) |
| 58 | [Kontekst] Z MCP Serena preferuj `find_symbol` i `find_referencing_symbols` | AG „Oszczędzanie kontekstu” |
| 59 | [Kontekst] Stały wpis o Serena/Graphify dopiero po werdykcie „zostaje” | AG „Oszczędzanie kontekstu” |
| 60 | [Usługi] API i Admin uruchamia użytkownik; agent nie bez osobnego polecenia | AG „Kontrola lokalnych usług API i Admin” 1 |
| 61 | [Usługi] Polecenie naprawy, diagnozy, testów nie jest zgodą na uruchomienie, porty, ukrytą instancję | AG „Kontrola lokalnych usług…” 1 |
| 62 | [Usługi] Wcześniejsza zgoda na restart nie przechodzi na kolejne zadania | AG „Kontrola lokalnych usług…” 1 |
| 63 | [Usługi] Restart potrzebny: przekaż komendę użytkownikowi | AG „Kontrola lokalnych usług…” 2 |
| 64 | [Usługi] Status i port sprawdzaj bez zmiany stanu; nie kończ cudzych procesów | AG „Kontrola lokalnych usług…” 2; MM bramka 5 |
| 65 | [Trwałość] Usuwaj przyczynę globalnie i trwale (nowy proces, terminal, restart) | AG „Trwałość rozwiązań” 1 |
| 66 | [Trwałość] Zmiana `PATH`, zabicie procesu, jednorazowa komenda to obejście, nie naprawa | AG „Trwałość rozwiązań” 1 |
| 67 | [Trwałość] Obejście oznacz jawnie i dodaj trwałą poprawkę | AG „Trwałość rozwiązań” 2 |
| 68 | [Trwałość] Weryfikuj z nowego procesu lub odczytem konfiguracji | AG „Trwałość rozwiązań” 3 |
| 69 | [Trwałość] Bez potwierdzenia nie raportuj jako naprawionego; zapisz ryzyko | AG „Trwałość rozwiązań” 3 |
| 70 | [Wersjonowanie] Każdy task osobny commit | AG „Wersjonowanie commitów”; TC „Wersjonowanie commitów” |
| 71 | [Wersjonowanie] Niezależna poprawka przed taskiem też osobny commit | AG „Wersjonowanie commitów”; TC |
| 72 | [Wersjonowanie] Pierwszy commit toru: wersja z najnowszego wersjonowanego commita na branchu (`git log`) | AG „Wersjonowanie commitów”; TC |
| 73 | [Wersjonowanie] Nie zakładaj wersji z nazwy brancha ani przykładowej/zapamiętanej (`v1.1`) | AG „Wersjonowanie commitów”; TC |
| 74 | [Wersjonowanie] Następny commit zwiększa patch o jeden | AG „Wersjonowanie commitów” („`N` następny”); TC |
| 75 | [Wersjonowanie] Po commicie zapisz wersję i hash w `Outcome` i `CURRENT_STATE.md` | TC „Wersjonowanie commitów” i „Kroki skryptu” 8 (`record-hash`) |
| 76 | [Wersjonowanie] Przy kontynuacji potwierdź zapis z historią; obowiązuje rzeczywisty commit | TC „Wersjonowanie commitów” |
| 77 | [Wersjonowanie] Patch według kolejności commitów, nie liczby zadań | TC „Wersjonowanie commitów” |
| 78 | [Wersjonowanie] Nie wolno ponownie użyć ani pominąć numeru bez decyzji użytkownika | AG „Wersjonowanie commitów”; TC |
| 79 | [Wersjonowanie] Format `vX.Y.N - {opis}` | AG „Wersjonowanie commitów”; TC |
| 80 | [Wersjonowanie] Przed commitem `git diff --cached --check`, statystyka, lista staged | TC „Wersjonowanie commitów”; „Kroki skryptu” 7 |
| 81 | [Wersjonowanie] Po commicie `git show --stat` i `git status` | TC „Wersjonowanie commitów” |
| 82 | [Brudny] Zmiany sprzed taska należą do użytkownika, chyba że pochodzenie jest znane | AG „Brudny worktree i zakres commita”; TC |
| 83 | [Brudny] Nie usuwaj ich, nie formatuj masowo, nie dołączaj do commita | AG „Brudny worktree…”; TC |
| 84 | [Brudny] W pliku z mieszanymi zmianami do indeksu tylko hunki taska | AG „Brudny worktree…”; TC (sposób w „Uwagach”) |
| 85 | [Brudny] Nie commituj całego pliku tylko dlatego, że task zmienił fragment | TC „Brudny worktree…” |
| 86 | [Brudny] Zmiana API wymaga pionu: backend, OpenAPI, klient, wrapper, test żądania | AG „Zasady nadrzędne” (kontrakt API); TC „Brudny worktree…” |
| 87 | [Brudny] Nie utrzymuj ręcznie rozbieżnych typów | AG „Zasady nadrzędne”; TC „Brudny worktree…” |
| 88 | [Scalanie] Gałąź integracyjna `main` (operator 2026-10-16), chyba że użytkownik wskaże inną | AG „Scalanie do gałęzi integracyjnej”; MM „Fakty” |
| 89 | [Scalanie] `v1.1-vision-lab-hybrid-geometry` jest w `main`; nie scalaj do niej, nie zakładaj od niej gałęzi | MM „Fakty”; `CURRENT_STATE.md` „Obowiązujące ograniczenia” |
| 90 | [Scalanie] Najpierw cały zlecony zakres z weryfikacją, audytami, dokumentacją, commitami | AG „Scalanie…”; MM „Kiedy użyć” |
| 91 | [Scalanie] Potem przedstaw wynik i zapytaj o akceptację i zgodę na scalenie | AG „Scalanie…”; MM krok 2 |
| 92 | [Scalanie] Przy planie/etapie nie pytaj o scalenie po każdym tasku; jedno pytanie | AG „Scalanie…”; MM bramka 1 |
| 93 | [Scalanie] Niezależne blokery i zgody na koszt/dane zgłaszaj nadal | MM bramka 1 |
| 94 | [Scalanie] Scalaj dopiero po akceptacji wyniku i potwierdzeniu | AG „Scalanie…”; MM bramka 1 |
| 95 | [Scalanie] Akceptacja planu ani polecenie implementacji nie zastępują zgody | AG „Scalanie…”; MM bramka 1 |
| 96 | [Scalanie] Brak odpowiedzi nie oznacza zgody | AG „Scalanie…” („milczenie”); MM bramka 1 |
| 97 | [Scalanie] Nowe prace na gałęzi roboczej, nie bezpośrednio na integracyjnej | AG „Scalanie…”; MM „Fakty” |
| 98 | [Scalanie] Przed scaleniem sprawdź historię, zakres commitów, stan obu worktree | MM kroki 1, 2, 7 |
| 99 | [Scalanie] Preferuj fast-forward | MM krok 8 (`--ff-only`) |
| 100 | [Scalanie] Nie nadpisuj ani nie commituj cudzych zmian; zabezpiecz; inaczej zatrzymaj i zgłoś blocker | MM bramka 6 |
| 101 | [Scalanie] Scalenie nie znosi P0/P1, migracji, zgód na dane i koszt | AG „Scalanie…” (P0/P1, migracja); MM bramka 3 |
| 102 | [Scalanie] Nie scalaj kodu wymagającego niewykonanej migracji | AG „Scalanie…”; MM bramka 4 |
| 103 | [Scalanie] Nie wykonuj automatycznego push, restartu usług ani wdrożenia | ZMIENIONE (decyzja operatora): AG „Scalanie…” (push objęty zgodą na scalenie, bez niej brak push) i „Po kodowaniu” 8; MM bramki 2 i 5, krok 9 |
| 104 | [Scalanie] Po scaleniu potwierdź commit taska w gałęzi, sprawdź worktree, zapisz hash w `Outcome` i `CURRENT_STATE.md` | MM kroki 6 i 11 |
| 105 | [Scalanie] Raport rozróżnia wynik do akceptacji od scalonego i podaje gałąź | MM krok 11 |
| 106 | [Scalanie] Oczekującego scalenia nie przedstawiaj jako wykonanego | MM krok 2 |
| 107 | [Przed kodowaniem] 1–4: zakres, pliki, pytania blokujące, założenia w tasku i `CURRENT_STATE.md` | AG „Przed kodowaniem” 1–4 |
| 108 | [Przed kodowaniem] 5: decyzja domeny/architektury do `DECISION_LOG.md` (pełny wpis, wiersz indeksu, przeniesienie ponad 30 ze zmianą tylko linku) | AG „Przed kodowaniem” 5 (+ reguły w nagłówku `DECISION_LOG.md`) |
| 109 | [W czasie] Jeden spójny pion naraz | AG „W czasie kodowania” |
| 110 | [W czasie] Testy razem z kodem | AG „W czasie kodowania” |
| 111 | [W czasie] Małe moduły, jawne nazwy domenowe | AG „W czasie kodowania” |
| 112 | [W czasie] Logika domenowa oddzielona od HTTP, UI, ORM | AG „W czasie kodowania” |
| 113 | [W czasie] Algorytmy jako czyste, deterministyczne funkcje | AG „W czasie kodowania” |
| 114 | [W czasie] Rozszerzenie API dla UI: zgłoś przed zmianą, rozszerz zgodnie zamiast równoległego endpointu | AG „W czasie kodowania” |
| 115 | [W czasie] Wspólny komponent zachowuje zachowanie konsumentów; opcje opcjonalne; test regresyjny | AG „W czasie kodowania” |
| 116 | [Testy] Kolejność: testy pionu, lint, typecheck, szersze testy, build | AG „Testy, benchmarki i regresje” |
| 117 | [Testy] Bez benchmarków, testów obciążeniowych, wielkich fixture'ów bez polecenia | AG „Testy, benchmarki i regresje” |
| 118 | [Testy] Najpierw analiza teoretyczna albo ograniczony test | AG „Testy, benchmarki i regresje” |
| 119 | [Testy] Nie osłabiaj ani nie usuwaj testu dla zielonego wyniku | AG „Testy, benchmarki i regresje” |
| 120 | [Testy] Test zmieniaj tylko przy świadomej zmianie kontraktu | AG „Testy, benchmarki i regresje” |
| 121 | [Testy] Naprawa regresji z testem odtwarzającym (restart, utracona odpowiedź, konflikt, wznowienie) | AG „Testy, benchmarki i regresje” |
| 122 | [Testy] Niezwiązany błąd nie rozszerza zakresu; potwierdź moduły, opisz blocker, poza commitem | AG „Testy, benchmarki i regresje” |
| 123 | [Workflowy] Weryfikuj po restarcie procesu i utracie odpowiedzi API | AG „Trwałe workflowy i operacje danych” |
| 124 | [Workflowy] Sukces w bieżącej sesji nie dowodzi trwałości | AG „Trwałe workflowy…” |
| 125 | [Workflowy] Implementacja mechanizmu destrukcyjnego nie jest zgodą na wykonanie | AG „Trwałe workflowy…” |
| 126 | [Workflowy] Migracje destrukcyjne, GC, cleanupy, usuwanie danych wymagają preview i potwierdzenia | AG „Trwałe workflowy…” |
| 127 | [Limity] Każda komenda musi mieć jawny timeout; nie bez limitu | AG „Limity czasu i procesy długotrwałe” 1 |
| 128 | [Limity] Domyślnie ≤ 120 s; dłużej tylko build/benchmark po uprzedzeniu | AG „Limity czasu…” 1 |
| 129 | [Limity] Serwery i watchery nie jako foreground; osobny proces, PID, polling ≤ 10 s | AG „Limity czasu…” 2 |
| 130 | [Limity] 60 s bez wyniku: przerwij, sprawdź, zgłoś przed ponowieniem | AG „Limity czasu…” 3 |
| 131 | [Limity] Bez nieograniczonego oczekiwania; polling z limitem prób i krótkimi timeoutami | AG „Limity czasu…” 3 |
| 132 | [Limity] Po przerwaniu sprawdź osierocone procesy; bez drugiej kopii usługi | AG „Limity czasu…” 4 |
| 133 | [Po kodowaniu] 1: formatowanie, lint, testy, typy | AG „Po kodowaniu” 1; TC „Kolejność zamykania” 1 |
| 134 | [Po kodowaniu] 2: dokumentacja zmienionego zachowania | AG „Po kodowaniu” 2; TC 2 |
| 135 | [Po kodowaniu] 3: okno `CURRENT_STATE.md` (sekcja do archiwum, wiersz ≤ 400 B, usunięcie najstarszego i wskaźnika, ograniczenia, plany) i `docs:check` | AG „Po kodowaniu” 3 (skrót); TC „Kroki skryptu” 2–6 (`close_task.py`); nagłówek `CURRENT_STATE.md` |
| 136 | [Po kodowaniu] 4: `Outcome` | AG „Po kodowaniu” 4; TC „Kolejność zamykania” 4 |
| 137 | [Po kodowaniu] 5: plik `done` do `tasks/completed/` | AG „Po kodowaniu” 5; TC „Kroki skryptu” 5 |
| 138 | [Po kodowaniu] 6: raport (zmiany, testy, czego nie wykonano, następne kroki/ryzyka) | AG „Po kodowaniu” 6; TC „Kolejność zamykania” 7 |
| 139 | [Po kodowaniu] 7: porównanie z DoD i planem | AG „Po kodowaniu” 7; TC 7 |
| 140 | [Po kodowaniu] 8: po raporcie stop, chyba że etap/plan bez etapów | AG „Po kodowaniu” 8 |
| 141 | [Po kodowaniu] 8: kontynuacja po audycie, commicie, `Outcome`, `CURRENT_STATE.md` każdego taska | AG „Po kodowaniu” 8 (ZMIENIONE: „po audycie (jeśli wymagany)”) |
| 142 | [Po kodowaniu] 8: stop na końcu etapu, sprzeczności, decyzji, braku modelu, P0/P1 po rundzie, operacji/koszcie poza zakresem | AG „Po kodowaniu” 8 |
| 143 | [Po kodowaniu] 8: P2 odnotowane w `Outcome` nie zatrzymują | AG „Po kodowaniu” 8 |
| 144 | [Po kodowaniu] 8: scalenie według sekcji „Scalanie…” | AG „Scalanie do gałęzi integracyjnej” |
| 145 | [Po kodowaniu] 8: bez automatycznego push, aktywacji modelu, wdrożenia | AG „Po kodowaniu” 8 (ZMIENIONE: „nigdy nie są automatyczne”; push objęty zgodą na scalenie) |
| 146 | [Audyt] Brak `claude` w `PATH` nie oznacza braku instalacji; skrypt wykrywa `.local/bin`, `Claude/claude-code/…`, pakiet Windows | `.codex/skills/claude-audit/SKILL.md` „Zasady” (ostatni punkt) i krok 3 |
| 147 | [Audyt] Korzystaj z wykrywania przed zgłoszeniem niedostępności audytora | jw. |
| 148 | [Audyt] Ścieżka `AppData/Roaming` może być wirtualna; nie utrwalaj wersji, builda, PID | jw. |
| 149 | [Audyt] `--version` potwierdza start CLI, nie logowanie ani audyt | jw. |
| 150 | [Audyt] Nie proponuj reinstalacji na podstawie samego `Get-Command` | jw. |
| 151 | [Audyt] Audytuje model z innej rodziny (Claude ↔ Codex) | AG „Audyt krzyżowy”; AU „Zasady” |
| 152 | [Audyt] Wykonawca nie audytuje własnej pracy | AG „Audyt krzyżowy”; AU „Zasady” |
| 153 | [Audyt] Audyt wymagany po tasku wskazanym w `Dodatkowy review`, przed commitem | ZMIENIONE (decyzja operatora): AG „Audyt krzyżowy” („tylko, gdy”; rezygnacja operatora); AU „Zasady”, „Kiedy użyć” |
| 154 | [Audyt] Zastępca: niezależny subagent Claude z innym modelem, świeży kontekst, tylko odczyt | AU „Zasady”; AG „Audyt krzyżowy” (odnośnik) |
| 155 | [Audyt] Zastępstwo jawnie w `Outcome`, zgodne z kolumną planu | AU „Zasady” |
| 156 | [Audyt] Brak modelu zatrzymuje task według `PLAN_STANDARD.md` | AU „Zasady”; AG „Po kodowaniu” 8 |
| 157 | [Audyt] Brief buduje `audit_task.ps1` (skład, `-Base HEAD`, `-Paths`, `artifacts/audits/`, CLI tylko do odczytu z limitem, bez CLI tylko brief) | AU „Zasady” (brief) i „Kroki” 2–3 |
| 158 | [Audyt] Timeout audytu do 600 s, `-TimeoutSec` niższy (480 s, ~25 s sprzątania) albo proces w tle | AG „Limity czasu…” 1 (wyjątek ≤ 600 s); AU „Zasady” i krok 2 |
| 159 | [Audyt] Audytor nie zmienia plików | AG „Audyt krzyżowy” („tylko do odczytu”); AU „Zasady”, „Ograniczenia” |
| 160 | [Audyt] Przegląd statyczny: zakres, kryteria, plan, reguły; nie rozszerza zakresu | AU „Zasady” |
| 161 | [Audyt] Raport: ścieżka, polska proza, szablon, `PASS`/`REVISE`, P0–P2 z `plik:linia`, listy uwag, testy, oświadczenie | AU „Zasady” (raport) |
| 162 | [Audyt] Raport wchodzi do commita taska | AU „Zasady”, „Ograniczenia” |
| 163 | [Audyt] Otwarte P0/P1 blokują commit | AG „Audyt krzyżowy”; AU krok 4 |
| 164 | [Audyt] P2 napraw albo odnotuj w `Outcome` z uzasadnieniem | AU „Jedna runda poprawek”; AG „Po kodowaniu” 8 |
| 165 | [Audyt] Jedna runda audytu i jedna runda poprawek | AG „Audyt krzyżowy”; AU „Jedna runda poprawek” |
| 166 | [Audyt] Ponowny audyt tylko na żądanie operatora lub po zmianie zachowania P0/P1; bez pętli | AG „Audyt krzyżowy” („bez pętli”); AU „Jedna runda poprawek” |
| 167 | [Audyt] Otwarte P0/P1 po poprawkach: zatrzymaj task i zgłoś | AG „Po kodowaniu” 8; AU „Jedna runda poprawek” |
| 168 | [Audyt] Szybki audyt domyślny (`gpt-6-astra` `medium`, `high` dla schematu/migracji/wypłat/danych dowodowych, `-Paths`, P0/P1, ≤ 5 P2; zastępca `medium`; brak odpowiedzi w limicie nie zatrzymuje, zapis w `Outcome`) | AU „Zasady” (bez zmiany treści) |
| 169 | [Audyt] Po commicie lead dopisuje wersję i hash; audytor sprawdza zapis | TC „Wersjonowanie commitów”; AU „Zasady” |
| 170 | [Audyt] Codex CLI przez `node.exe` + `codex.js`, `windows.sandbox="unelevated"`, `model_reasoning_effort` | `.claude/skills/audit-task/SKILL.md` „Zasady” (ostatni punkt) i krok 2 |
| 171 | [Audyt] Poświadczeń CLI nie wpisuje agent; instalacja i logowanie: operator | AG „Audyt krzyżowy”; AU „Zasady” |
| 172 | [Hierarchia] Kolejność źródeł prawdy 1–6 | AG „Hierarchia źródeł prawdy” |
| 173 | [Hierarchia] Przy sprzeczności kodu z dokumentacją nie zakładaj, że kod ma rację; zgłoś | AG „Hierarchia źródeł prawdy” |
| 174 | [Jakość] Uruchomienie aplikacji nie kończy zadania; obowiązuje `DEFINITION_OF_DONE.md` | AG „Standard jakości” |

Reguł w tabeli: 174; bez miejsca: 0.

### Verification results

- `.\.venv\Scripts\python.exe scripts/check_startup_read_budget.py --report`:
  OK, `AGENTS.md: max 13942 / 14000 B, enforced`, 10/10 budżetów wymuszonych.
- `npx prettier --check` dla `AGENTS.md`, czterech skilli, dwóch kopii
  `.agents/`, `CURRENT_STATE.md` i `PLAN_STANDARD.md`: PASS.
- `pytest services/worker/tests/test_check_startup_read_budget_script.py`
  (`-p no:cacheprovider --basetemp D:/ptw6`): 14 passed.
- `ruff check`, `ruff format --check`, `mypy --strict` na
  `scripts/check_startup_read_budget.py` (ruff także na teście): PASS.
- `scripts/check_skill_mirrors.py`: OK (2 pary).
- `npm run docs:check`: PASS. `git diff --check`: PASS.

### Odstępstwa i ryzyka

- Nagłówki przeniesionych sekcji zostały w `AGENTS.md` (krótkie reguły), więc
  zewnętrzne odwołania nie wymagały przepinania poza `audit_task.ps1`.
- Dodatkowe zmiany spójności poza listą plików taska: ograniczenie „Akceptacja
  przed scaleniem” w `CURRENT_STATE.md` (push objęty zgodą na scalenie) i
  `PLAN_STANDARD.md` (audyt tylko, gdy wymaga go plan).
- Zapas budżetu `AGENTS.md` to 58 B; każda kolejna reguła wymaga skrócenia
  innej treści albo przeniesienia procedury do skilla.
- Review Codex: nie uruchomiony przez wykonawcę; decyzja należy do leada
  (operator może zrezygnować).
