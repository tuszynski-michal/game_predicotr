# TASK-0938 — Okno kroczące `CURRENT_STATE.md` i indeks `DECISION_LOG.md`

## Status

`done`

## Goal

Obowiązkowe dokumenty startowe mieszczą się w limicie czytelnym dla agenta:
`CURRENT_STATE.md` zawiera tylko zadania `in_progress` i ostatnie 10 `done`,
`DECISION_LOG.md` jest indeksem decyzji z pełnymi wpisami w plikach rocznych;
żadna treść nie ginie.

## Context

`CURRENT_STATE.md` ma 11 774 linie (853 KB), `DECISION_LOG.md` 11 300 linii
(791 KB). Pełny odczyt na start każdej sesji jest niewykonalny i kosztowny.
Plan: etap T.

## Dependencies / entry conditions

- Decyzja operatora D-1 planu (teraz czy później).
- Fakt: `AGENTS.md` i `ai_docs/README.md` nakazują czytać oba pliki; wiele
  dokumentów linkuje do `DECISION_LOG.md#d-xxx`.

## Recommended execution

claude-sonnet-5-5 / medium. Przeniesienie treści bez zmian merytorycznych,
kontrola linków. Eskalacja niepotrzebna. Audyt: gpt-6.1-sol / medium; do czasu CLI zamiennik claude-opus-5-5 / medium.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- `CURRENT_STATE.md`: obowiązkowy spis elementów zachowanych w oknie:
  (1) sekcja każdego taska ze statusem `in_progress`, `blocked` lub `todo`
  mającego plik w `ai_docs/tasks/`; (2) każdy plan o statusie `proposed`
  lub `accepted` z niezakończonymi taskami, z listą tasków pozostałych;
  (3) nierozstrzygnięte decyzje i pytania (wskaźniki do
  `OPEN_QUESTIONS.md`/`DECISION_LOG.md`); (4) aktywne ograniczenia
  operacyjne ze starszych wpisów (np. stan migracji bazy operatora,
  uruchomione usługi i joby, zgody wymagane przed wdrożeniem, znane
  blokady), wyniesione do osobnej sekcji „Obowiązujące ograniczenia”;
  (5) ostatnie 10 sekcji `done`. Reszta przeniesiona bez edycji do
  `ai_docs/archive/CURRENT_STATE_2026Q3.md` (i kolejnych). Przed
  przeniesieniem każdy starszy wpis jest przejrzany pod kątem (3) i (4);
  wyniesione ograniczenia dostają odnośnik do archiwum.
- Reguła utrzymania (do `AGENTS.md`): przy zamykaniu taska agent dopisuje
  jego sekcję `done`, przenosi do archiwum sekcje `done` ponad limit 10 i
  aktualizuje „Obowiązujące ograniczenia”. Skrypt
  `scripts/check_current_state_window.py` (proponowany) sprawdza, że każdy
  aktywny plik taska ma sekcję, że limit `done` jest zachowany i że rozmiar
  pliku nie przekracza progu; uruchamiany w `npm run quality`.
- `DECISION_LOG.md`: na górze indeks (numer, tytuł, status, data, jedno
  zdanie, link do pełnego wpisu); pełne wpisy w
  `ai_docs/process/decisions/DECISION_LOG_2026.md` (lub podział kwartalny),
  kotwice `#d-xxx` zachowane; skrypt `scripts/check_decision_links.py`
  (proponowany) sprawdza linki w `ai_docs/`.
- `AGENTS.md` i `README.md`: obowiązkowy odczyt = indeks; pełny wpis na
  żądanie, gdy zadanie go wskazuje.

## Out of scope

- Zmiana treści decyzji lub stanów; skracanie wpisów.

## Acceptance criteria

- [x] Oba pliki < 100 KB; archiwa zawierają przeniesioną treść bez zmian
      (diff treści = przeniesienie).
- [x] Sekcja „Obowiązujące ograniczenia” istnieje i każdy aktywny task,
      plan i otwarta decyzja ma wpis; `check_current_state_window.py` PASS.
- [x] Wszystkie linki `DECISION_LOG.md#d-` w `ai_docs/` rozwiązują się.
- [x] `AGENTS.md`/`README.md` opisują nowy obowiązkowy odczyt.

## Verification

```powershell
# katalog worktree, timeout 120 s
.\.venv\Scripts\python.exe scripts/check_decision_links.py
```

## Risks / open questions

- Równoległe sesje edytują oba pliki; wykonać w oknie bez innych aktywnych
  zadań i zmergować jako pierwsze.

## Outcome

Wykonał: claude-sonnet-5-5 (executor), worktree `worktrees/mumie-super-game`,
HEAD wejściowy `v1.7.280` / `8629be40`. Zmiany nie są zacommitowane (commit i
hash dopisuje lead).

### Changed

- `ai_docs/process/CURRENT_STATE.md`: 868 364 B / 13 375 linii → 74 740 B / 976
  linii. Okno: „Obowiązujące ograniczenia” (25 punktów, każdy ze wskazaniem
  sekcji-źródła), „Plany z niezakończonymi taskami” (tabela 11 planów + zachowana
  sekcja planu Mumie), „Otwarte decyzje i pytania”, „Aktywne taski” (12 sekcji
  zachowanych bez zmian + 30 krótkich wpisów dla tasków z plikiem w
  `ai_docs/tasks/`, które nie miały własnej sekcji), „Ostatnie 10 ukończonych
  tasków” (TASK-0936, 0935, 0934, 0933, 0940, 0932, 0931, 0929, 0930, 0927) i
  „Archiwum”.
- `ai_docs/archive/CURRENT_STATE_2026Q4.md` (147 761 B, 91 sekcji) i
  `ai_docs/archive/CURRENT_STATE_2026Q3.md` (677 547 B, 483 sekcje): sekcje
  przeniesione bez zmian. Reguła podziału (zapisana w nagłówkach archiwów):
  sekcja zaczynająca się w źródle powyżej „D-470 / D-471” (wiersz 2455, pierwsza
  sekcja datowana 2026-09-30) trafia do Q4 (wpisy 2026-10-01..09), reszta do Q3;
  sekcje późniejsze zostają w Q3 nawet z dopisanymi wpisami z października.
  Dolna część źródła (od „Phase”, lipiec–sierpień, bez dat w treści) jest w Q3.
- `ai_docs/process/DECISION_LOG.md`: 787 675 B / 12 566 linii → 69 939 B / 408
  linii. Nagłówek z regułami, indeks (nr z linkiem do kotwicy, tytuł, status,
  data, jedno zdanie) 177 najnowszych wierszy (D-359..D-537) i pięć najnowszych
  pełnych wpisów D-533..D-537 (identycznych z wpisami w pliku rocznym).
- `ai_docs/process/decisions/DECISION_LOG_2026.md` (788 213 B): pełne wpisy,
  nagłówki `## D-NNN — …` i kolejność bez zmian (do pliku dodano tylko nagłówek
  z front matter; od wiersza 17 tekst jest identyczny z dawnymi wierszami 9..
  koniec). `ai_docs/process/decisions/DECISION_INDEX_ARCHIVE.md` (103 998 B):
  indeks pozostałych 357 wierszy (D-1..D-358). Wszystkie daty wpisów to 2026, więc
  jeden plik roczny.
- `scripts/check_decision_links.py` (nowy): sprawdza linki `DECISION_LOG*.md#d-…`
  w `ai_docs/**/*.md`, `AGENTS.md`, `CLAUDE.md` (kotwice w stylu GitHub z
  przyrostkami `-1`, pomija bloki kodu), poprawność kotwic wierszy indeksów oraz
  zgodność zbioru (numer, kotwica) indeksów ze zbiorem nagłówków wpisów w obie
  strony; exit 1 przy problemach.
- `scripts/check_current_state_window.py` (nowy): każdy `ai_docs/tasks/NNNN-*.md`
  ma nagłówek z `TASK-NNNN`, ≤ 10 sekcji `### TASK-… (done`, istnieje sekcja
  „Obowiązujące ograniczenia” z punktami, rozmiar < 100 000 B.
- `package.json`: skrypt `docs:check` (oba skrypty) dopisany na końcu `quality`.
- `AGENTS.md` (kolejność czytania, krok „Przed kodowaniem” 5, „Po kodowaniu” 3,
  hierarchia źródeł), `ai_docs/README.md` (wejście do zadania, spis procesu,
  reguła aktualizacji), `ai_docs/archive/README.md` (spis archiwów stanu).
- Ten plik zadania (sekcja `Outcome`); linia `Status` bez zmian.

### Verification results

- `npm run docs:check` (2,3 s łącznie): `check_decision_links: OK (534 anchor
  links, 534 entries, 534 index rows)`, `check_current_state_window: OK (37 active
  tasks, 10 done sections, 74740 bytes)`. Próby negatywne: zły link do kotwicy i
  usunięta sekcja taska/sekcja ograniczeń dają exit 1.
- Dowód przeniesienia bez zmian (skrypt poza repo, `scratchpad/task0938/prove.py`):
  `CURRENT_STATE.md` z HEAD (`git show HEAD:…`) dzielony na bloki od każdego
  nagłówka `##`/`###` poza blokami kodu (597 bloków; wstęp z front matter i
  `# Current State` wymieniony). Okno (59 bloków: 23 z HEAD + 36 wygenerowanych)
  i oba archiwa (91 + 483) dzielone tą samą regułą. Multizbiór (bloki okna
  obecne w HEAD + bloki archiwów) jest równy multizbiorowi bloków HEAD
  (PASS, 868 269 B = 868 269 B, brak nakładania okno/archiwum, jedyny blok spoza
  HEAD w archiwach to stopka „Koniec archiwum 2026Q4” dodana, by plik nie
  kończył się pustym wierszem). Wygenerowane bloki okna: 6 sekcji `##` + 30
  krótkich wpisów tasków. `DECISION_LOG`: plik roczny kończy się dokładnie
  wierszami 9..koniec z HEAD (PASS); multizbiór 534 wpisów (`##`/`###` D-NNN,
  bez bloków kodu) HEAD = plik roczny (PASS); pięć pełnych kopii w
  `DECISION_LOG.md` równe wpisom HEAD z dokładnością do końcowego znaku nowej
  linii.
- Rozmiary: oba obowiązkowe pliki < 100 KB (74 740 B i 69 939 B).
- `ruff check`, `ruff format --check`, `mypy --strict` dla obu skryptów, `prettier
  --check AGENTS.md package.json`: PASS. `git diff --check` dla zmienionych
  plików śledzonych: czysto (tylko ostrzeżenia LF/CRLF środowiska); nowe pliki
  bez białych znaków na końcu wierszy.

### Not completed

- Indeks w `DECISION_LOG.md` nie obejmuje wszystkich 534 wpisów: przy pełnych
  polach (tytuł, status, data, zdanie, link z kotwicą) sam indeks ma ok. 174 KB,
  co łamie kryterium < 100 KB. Dlatego `DECISION_LOG.md` zawiera 175 najnowszych
  wierszy, a 359 starszych jest w `decisions/DECISION_INDEX_ARCHIVE.md`
  (linkowanym z nagłówka, sprawdzanym tym samym skryptem). Alternatywa
  (wstawianie ukrytych kotwic `<a id>` do pliku wpisów) naruszyłaby przeniesienie
  bez zmian.
- Brak linków `DECISION_LOG.md#d-…` do przepisania: w `ai_docs/`, `AGENTS.md`,
  `CLAUDE.md` nie było ani jednego (jedyne trafienia to opis w tym pliku zadania),
  więc żaden istniejący dokument poza wymienionymi nie został zmieniony.
  `CLAUDE.md` nie był w zakresie edycji; jego punkty „read `CURRENT_STATE.md`”
  i „add a `DECISION_LOG.md` entry” pozostają prawdziwe, ale lead może dopisać
  tam krótką wzmiankę o indeksie i oknie.
- Zdania w indeksie są wyciągane automatycznie (pierwsze zdanie pola Decision
  albo pierwszego akapitu, ≤ 110 znaków); część jest obcięta wielokropkiem.
  Nie sprawdzano ich ręcznie dla wszystkich 534 wpisów.
- Do klasyfikacji wymagającej decyzji: (a) `LEGACY_PUBLIC_STORE_REMOVAL_EXECUTION_PLAN.md`
  ma w nagłówku `completed`, mimo że TASK-0687..0691 są aktywne; (b)
  `IMPORT_REPORT_PERFORMANCE_PLAN_20261007.md` (`proposed`) ma wykonany tylko
  TASK-0910, TASK-0911..0918 nie mają plików; (c) `MILESTONE_06_EXECUTION_PLAN.md`
  ma `in_progress` z 2026-07-29; (d) TASK-0472, 0517, 0603, 0654, 0290 mają stare,
  zachowane sekcje, których aktualności nie weryfikowano; (e) stan migracji bazy
  operatora (0151 potwierdzone 2026-10-08, 0152 wymagana przez kod) trzeba
  sprawdzić `alembic current`. Wszystko to jest zapisane w „Obowiązujących
  ograniczeniach” albo w tabeli planów.
- Numery D-416..D-429 występują w pliku wpisów w dwóch torach (kolizja
  numeracji istniejąca w HEAD); indeks rozróżnia je kotwicą, nie zmieniono tego.

### Documentation updates

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/archive/README.md`: nowy obowiązkowy
  odczyt (okno stanu + indeks decyzji z pięcioma najnowszymi wpisami), pełne wpisy
  i archiwa na żądanie, reguła utrzymania okna przy zamykaniu taska.
- `CURRENT_STATE.md` i `DECISION_LOG.md`: opisane wyżej; ten task nie zmienia
  treści decyzji ani stanów, więc nie dopisano wpisu do `DECISION_LOG.md`.
  Lead dopisuje sekcję `done` TASK-0938, hash commitu i przenosi plik taska do
  `ai_docs/tasks/completed/` (przy tym wpis „TASK-0938 (todo)” z „Aktywne taski”
  należy zastąpić sekcją `done`, a najstarszą sekcję `done` (TASK-0927) przenieść
  na początek archiwum Q4).

### Recommended next task

- TASK-0939 (narzędzia oszczędzania tokenów z pomiarem); równolegle review
  tego taska (audyt `claude-opus-5-5 / medium` do czasu CLI Codex). Po scaleniu
  zalecane jednorazowe sprawdzenie ręczne „Obowiązujących ograniczeń” z
  operatorem (szczególnie stanu migracji bazy i usług).

### Audyt i runda poprawek

Audyt Codex gpt-6-astra / medium: REVISE (`ai_docs/quality/TASK-0938_AUDIT_gpt-6-astra.md`),
jedna runda poprawek:

- P1-1: wpis TASK-0937 w `CURRENT_STATE.md` przepisany na stan `blocked`
  (narzędzie gotowe, v1.7.281 / 7b7b0a7e, warunki odblokowania); wpis TASK-0938
  zastąpiony sekcją `done` (z miejscem na hash commita v1.7.282); najstarsza
  sekcja `done` (TASK-0927) przeniesiona bez zmian na początek archiwum Q4,
  więc okno ma nadal 10 sekcji `done`; zaktualizowano wskaźniki i tabelę planów.
- P1-2: `scripts/check_decision_links.py` wymaga istnienia dokładnej ścieżki
  względnej linku (bez zastępowania plikiem o tej samej nazwie gdzie indziej);
  odwołania tekstowe `D-NNN` bez ścieżki nie są sprawdzane (opisane w nagłówku
  skryptu). Test negatywny (istniejąca kotwica, nieistniejąca ścieżka -> błąd) w
  `services/worker/tests/test_check_decision_links_script.py`.
- P2-1: skrypt zgłasza błąd, gdy cały `DECISION_LOG.md` ma co najmniej 100 000 B;
  reguła archiwizowania wierszy indeksu opisana w nagłówku `DECISION_LOG.md` i
  skryptu; test negatywny w tym samym pliku testów (4 testy PASS).
