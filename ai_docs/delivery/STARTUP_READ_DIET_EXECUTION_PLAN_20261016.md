---
title: Odchudzenie obowiązkowego odczytu startowego
status: proposed
last_updated: 2026-10-16
---

# Plan: odchudzenie obowiązkowego odczytu startowego

TASK-1019–1023. Gałąź robocza `feat/startup-read-diet` (worktree
`worktrees/startup-read-diet`, baza `main` v1.7.363 / `4e171b06`).

## Stan obecny (fakty z repozytorium, `main` v1.7.363)

Każda nowa sesja, wykonawca i audytor czyta przed pracą (`AGENTS.md`, sekcja
„Obowiązkowa kolejność czytania”; `ai_docs/README.md`, sekcja „Wejście do
zadania”):

| Plik | Bajty | Uwagi |
|---|---:|---|
| `AGENTS.md` | 25 943 | reguły nadrzędne |
| `ai_docs/README.md` | 16 296 | indeks dokumentacji |
| `ai_docs/process/CURRENT_STATE.md` | 91 492 | limit skryptu 100 000 B |
| `ai_docs/process/DECISION_LOG.md` | 77 628 | limit skryptu 100 000 B |
| razem (obowiązkowy odczyt) | 211 359 | |
| `CLAUDE.md` (Claude Code ładuje automatycznie) | 8 392 | w dużej części powtarza `AGENTS.md` |

Rozbicie największych plików (pomiar sekcji, 2026-10-16):

- `CURRENT_STATE.md`: „Obowiązujące ograniczenia” 19 695 B; „Plany z
  niezakończonymi taskami” 7 517 B; „Otwarte decyzje i pytania” 995 B;
  „Aktywne taski” 48 560 B, w tym jedna sekcja TASK-0290 13 542 B i kilka
  historycznych sekcji TASK-0472/0517/0603/0654 opisujących dawne iteracje;
  „Ostatnie 10 ukończonych tasków” 12 654 B (pełne sekcje `done`).
- `DECISION_LOG.md`: indeks 58 556 B (187 wierszy, D-359..D-547, średnio ok.
  313 B na wiersz) oraz pięć pełnych kopii najnowszych wpisów ok. 17 KB.
  Kopie są identyczne z wpisami w `decisions/DECISION_LOG_2026.md`.
- Okno kroczące wprowadził TASK-0938 (853 KB → 75 KB). Od tego czasu oba pliki
  wróciły do ok. 90 % limitu, bo limit 100 000 B jest jedynym ograniczeniem,
  a sekcje aktywne i `done` nie mają limitu długości.

Szacunek: tekst polski w Markdown to około 3–3,5 B na token, więc obowiązkowy
odczyt kosztuje około 60–70 tys. tokenów wejścia na każdą sesję i każdego
subagenta, zanim zacznie się praca nad zadaniem. Liczba tokenów jest
szacunkiem; metryką planu są bajty (deterministyczne, mierzalne skryptem).

## Cel

Obowiązkowy odczyt startowy (`AGENTS.md`, `README.md`, `CURRENT_STATE.md`,
`DECISION_LOG.md`) mieści się w **90 000 B** (−57 %), a budżety są pilnowane
przez `npm run docs:check`, bez utraty treści i bez zmiany decyzji
ani stanów.

## Zakres (punkty 1–3)

1. **`DECISION_LOG.md` jako lekki indeks** (TASK-1020): usunięcie pięciu pełnych
   kopii, w indeksie 30 najnowszych wierszy, starsze wiersze w
   `decisions/DECISION_INDEX_ARCHIVE.md`, wyszukiwanie decyzji przez `rg`.
2. **`CURRENT_STATE.md` z budżetami sekcji** (TASK-1021 propozycja i decyzja
   operatora, TASK-1022 zastosowanie): krótkie sekcje aktywne, jednowierszowe
   wpisy `done`, długie historie przeniesione bez zmian do archiwum, przegląd
   „Obowiązujących ograniczeń”.
3. **`CLAUDE.md` bez duplikatu `AGENTS.md`** (TASK-1023) oraz końcowy pomiar.

Pomiar i budżety dostarcza TASK-1019, zanim zmieni się jakikolwiek dokument.

## Kluczowe decyzje planu

- **D1. Metryka = bajty pliku.** Budżety i raport liczy jeden skrypt
  `scripts/check_startup_read_budget.py` (proponowany). Liczenie tokenów API
  nie jest wymagane (brak klucza dla agenta; tokenizer zmienia się z modelem).
- **D2. Jedno źródło budżetów.** Limity rozmiaru żyją wyłącznie w nowym
  skrypcie. Każdy budżet ma flagę `enforced`; TASK-1019 dodaje skrypt do
  `docs:check` z wszystkimi flagami `False` (raport bez porażki). TASK-1020,
  1022 i 1023 włączają swoje budżety i usuwają stare limity 100 000 B ze
  skryptów `check_decision_links.py` i `check_current_state_window.py`.
- **D3. Budżety docelowe** (bajty, UTF-8):

  | Budżet | Wartość | Włącza |
  |---|---:|---|
  | `DECISION_LOG.md` całość | 12 000 | TASK-1020 |
  | wiersze indeksu w `DECISION_LOG.md` | ≤ 30 | TASK-1020 |
  | `CURRENT_STATE.md` całość | 30 000 | TASK-1022 |
  | sekcja „Obowiązujące ograniczenia” | 8 000 | TASK-1022 |
  | sekcja „Plany z niezakończonymi taskami” | 5 000 | TASK-1022 |
  | pojedyncza sekcja aktywnego taska (`###`) | 1 200 | TASK-1022 |
  | pojedynczy wpis `done` | 400 | TASK-1022 |
  | `CLAUDE.md` | 6 000 | TASK-1023 |
  | suma obowiązkowego odczytu (4 pliki) | 90 000 | TASK-1023 |

  `AGENTS.md` i `README.md` dostają tylko pomiar w raporcie (bez budżetu);
  ich odchudzenie jest poza zakresem. TASK-1021 może zaproponować inne
  wartości dla sekcji `CURRENT_STATE.md`; zmiana wymaga zgody operatora i
  aktualizacji tej tabeli.
- **D4. Nic nie ginie.** Treść usuwana z okna trafia bez edycji na początek
  `ai_docs/archive/CURRENT_STATE_2026Q4.md` (sekcje stanu) albo do
  `decisions/DECISION_INDEX_ARCHIVE.md` (wiersze indeksu). Dowód: multizbiór
  bloków (metoda TASK-0938) przed = okno + archiwum po. Pełne kopie decyzji
  są już w pliku rocznym; dowodem jest ich identyczność z wpisami.
- **D5. Decyzje znajduje się wyszukiwaniem, nie lekturą indeksu.** Obowiązkowy
  odczyt `DECISION_LOG.md` = nagłówek z regułami + 30 najnowszych wierszy.
  Starsze decyzje: `rg -n "<słowo|D-NNN>" ai_docs/process/DECISION_LOG.md
  ai_docs/process/decisions/DECISION_INDEX_ARCHIVE.md`, pełny wpis przez
  kotwicę. Planista wpisuje decyzje istotne dla taska do `Relevant docs`
  (link z kotwicą); `TASK_TEMPLATE.md` dostaje to pole wprost. Decyzje
  przekrojowe, które ograniczają każdą pracę, są w „Obowiązujących
  ograniczeniach” (stan bez zmian).
- **D6. Wpis `done` w oknie jest jednowierszowy.** Format:
  `- **TASK-NNNN** — tytuł — vX.Y.N / krótki hash — ścieżka pliku w completed`.
  Pełna sekcja `done` zamykanego taska trafia od razu na początek archiwum Q4
  (później kolejnego kwartału). Okno trzyma 10 takich wierszy.
- **D7. Sekcja aktywnego taska jest wskaźnikiem.** Zawiera status, ścieżkę
  pliku taska, jedno zdanie blokera lub następnego kroku i ewentualnie
  wersję/hash. Szczegóły są w `Outcome` pliku taska albo w archiwum.
- **D8. Bez wpisu `DECISION_LOG.md`.** Zmiana dotyczy procesu dokumentacji,
  nie modelu domenowego ani architektury produktu (precedens TASK-0938 i
  TASK-0939). Jeśli operator uzna to za decyzję, wpis D-NNN dodaje TASK-1023
  (numer według czubka gałęzi integracyjnej; na `codex/v3-grid-fine-tuning`
  zajęte jest D-548..D-555).

## Kolejność i etapy

| Etap | Taski | Bramka na końcu etapu |
|---|---|---|
| A | TASK-1019 → TASK-1020 | raport pomiaru + `docs:check` PASS |
| B | TASK-1021 | **decyzja operatora** o klasyfikacji ograniczeń i sekcji |
| C | TASK-1022 → TASK-1023 | budżety włączone, końcowy pomiar, pytanie o scalenie |

Start każdego etapu wymaga jawnego polecenia operatora (`AGENTS.md`).

## Warunki wejścia i ryzyka współbieżności

- Równoległe gałęzie dopisują sekcje do `CURRENT_STATE.md` i wiersze do
  `DECISION_LOG.md` w starym formacie: `codex/v3-grid-fine-tuning`
  (TASK-0993–1018, D-548–D-555, v1.7.367–384), `codex/photo-crop-p1`
  (TASK-1016). TASK-1020 i TASK-1022 wykonuje się **bezpośrednio przed
  scaleniem**, po zsynchronizowaniu gałęzi z aktualnym czubkiem gałęzi
  docelowej, żeby przenieść także świeżo dopisaną treść.
- Gałąź docelowa scalenia: według `AGENTS.md` domyślnie
  `v1.1-vision-lab-hybrid-geometry` (v1.7.357), ale operator wskazał `main`
  dla TASK-1007 i `main` (v1.7.363) jest przed nią. Wybór gałęzi docelowej
  należy do operatora przy końcowym pytaniu o scalenie.
- Po scaleniu każda inna otwarta gałąź musi przepisać swoje hunki stanu na
  nowy format; TASK-1022 dodaje o tym punkt do „Obowiązujących ograniczeń”.
- Numery TASK-1019–1023 i wersje `vX.Y.N` trzeba potwierdzić z czubkiem
  gałęzi integracyjnej przed każdym commitem (kolizje torów,
  `CURRENT_STATE.md`, punkt „Kolizje numeracji”).

## Mapa wymaganie → task → kryterium

| Wymaganie | Task | Kryterium / test |
|---|---|---|
| pomiar przed i po | 1019, 1023 | raport skryptu w `Outcome` obu tasków |
| budżety pilnowane automatycznie | 1019, 1020, 1022, 1023 | `docs:check` FAIL po przekroczeniu (test negatywny) |
| `DECISION_LOG.md` ≤ 12 000 B, ≤ 30 wierszy | 1020 | skrypt budżetu + `check_decision_links.py` PASS |
| decyzje znajdowalne bez indeksu w kontekście | 1020 | reguła D5 w `AGENTS.md`, `README.md`, `TASK_TEMPLATE.md` |
| klasyfikacja ograniczeń zatwierdzona | 1021 | raport z decyzją operatora |
| `CURRENT_STATE.md` ≤ 30 000 B z budżetami sekcji | 1022 | skrypt budżetu + `check_current_state_window.py` PASS |
| brak utraty treści | 1020, 1022 | dowód multizbioru bloków |
| reguła zamykania taska w nowym formacie | 1022 | `AGENTS.md` „Po kodowaniu” 3, `README.md`, nagłówek okna |
| `CLAUDE.md` ≤ 6 000 B bez duplikatu reguł | 1023 | skrypt budżetu; ręczne porównanie z `AGENTS.md` |
| suma odczytu ≤ 90 000 B | 1023 | skrypt budżetu, flaga włączona |

## Odbiór całego przepływu

Po TASK-1023: nowa sesja Claude Code w worktree czyta wyłącznie pliki z
kolejności czytania; `npm run docs:check` PASS; raport skryptu pokazuje
sumę ≤ 90 000 B; zamknięcie przykładowego taska według nowej reguły
(symulacja w teście skryptu okna) przechodzi kontrolę. Opcjonalnie operator
porównuje `/context` świeżej sesji przed i po (wynik do `Outcome` TASK-1023).

## Poza zakresem

- Odchudzenie `AGENTS.md` (np. wyniesienie „Cyklu wykonania zadania” do
  skilla) i `ai_docs/README.md` (długa lista planów milestone): osobny plan po
  pomiarze tego.
- Pilot TASK-0939 (Serena, Graphify, mapa kodu, hook) i nowe narzędzia z
  notatki o oszczędzaniu tokenów (RTK, CodeGraph, Playwright CLI, skille
  projektowe).
- Zmiana treści decyzji, stanów, statusów tasków i archiwów poza dopisaniem
  przeniesionych bloków.
- Kod produktu, baza, migracje, usługi.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1019 — skrypt pomiaru i budżetów startowych | claude-sonnet-5-5 | medium | Mały skrypt Python z testami, bez logiki domenowej; wzorzec istniejących skryptów kontroli. Eskalacja do claude-opus-5-5 / high, jeśli test negatywny ujawni niejednoznaczny podział sekcji. | tak: gpt-6.1-sol / medium (Codex, `scripts/audit_task.ps1`) |
| TASK-1020 — `DECISION_LOG.md` jako lekki indeks | claude-sonnet-5-5 | medium | Mechaniczne przeniesienie wierszy i usunięcie kopii z dowodem; zmiana reguł w trzech dokumentach. Eskalacja do claude-opus-5-5 / high przy kolizji numerów D z innym torem. | tak: gpt-6.1-sol / medium (Codex) |
| TASK-1021 — przegląd ograniczeń i sekcji `CURRENT_STATE.md` | claude-opus-5-5 | high | Ocena aktualności ograniczeń operacyjnych (migracje, zgody, usługi) wymaga ostrożnego osądu; wynik jest tylko raportem do decyzji. | nie: bramką jest decyzja operatora |
| TASK-1022 — zastosowanie budżetów `CURRENT_STATE.md` | claude-sonnet-5-5 | high | Duże przeniesienie treści z dowodem braku utraty i zmiana reguły zamykania tasków używanej przez wszystkich agentów. Eskalacja do claude-opus-5-5 / high, jeśli dowód multizbioru nie przechodzi. | tak: gpt-6.1-sol / medium (Codex) |
| TASK-1023 — `CLAUDE.md` bez duplikatu i końcowy pomiar | claude-sonnet-5-5 | medium | Krótka zmiana instrukcji i włączenie ostatnich budżetów; ryzyko w pominięciu reguły specyficznej dla Claude. | tak: gpt-6.1-sol / medium (Codex) |
