---
title: AI documentation index
status: active
last_updated: 2026-10-16
---

# Dokumentacja AI Driven Development

## Cel

Dokumentacja dzieli produkt na niezależne obszary, dzięki czemu model AI może
realizować małe iteracje bez utraty kontekstu i bez przypadkowego łączenia
niegotowych części systemu.

## Wejście do zadania

Przed rozpoczęciem pracy czytaj w tej kolejności:

1. ten plik (szukając kodu, zacznij od [mapy kodu](architecture/CODE_MAP.md);
   szukając dokumentu lub planu, otwórz [katalog dokumentów](DOC_INDEX.md)
   albo przeszukaj go `rg`),
2. [Current State](process/CURRENT_STATE.md) — plik z oknem kroczącym:
   (≤ 30 000 B): obowiązujące ograniczenia, tabela planów z niezakończonymi
   taskami, otwarte decyzje, wskaźniki tasków aktywnych (≤ 1 200 B każdy) i
   10 jednowierszowych wpisów `done` (pełne sekcje `done` w archiwum),
3. [Decision Log](process/DECISION_LOG.md) — indeks 30 najnowszych decyzji;
   starsze wyszukuj `rg` w nim i w
   [archiwum indeksu](process/decisions/DECISION_INDEX_ARCHIVE.md),
4. aktywne zadanie znajdujące się bezpośrednio w `ai_docs/tasks/`,
5. wyłącznie dokumenty wskazane w sekcji `Relevant docs` tego zadania.

Pełne wpisy decyzji ([DECISION_LOG_2026.md](process/decisions/DECISION_LOG_2026.md))
oraz archiwa stanu ([Q4 2026](archive/CURRENT_STATE_2026Q4.md),
[Q3 2026](archive/CURRENT_STATE_2026Q3.md)) otwieraj na żądanie, gdy `Relevant
docs` aktywnego zadania je wskazuje albo gdy indeks nie wystarcza do oceny
sprzeczności. Pozostałe materiały archiwalne i ukończone zadania nie są
domyślnym kontekstem implementacyjnym.

## Zasada pojedynczego źródła prawdy

| Rodzaj informacji     | Dokument właścicielski  |
| --------------------- | ----------------------- |
| Cel produktu i zakres | `PROJECT_BRIEF.md`      |
| Zachowanie ekranów    | pliki w `requirements/` |
| Model danych          | `DATA_MODEL.md`         |
| Endpointy             | `API_CONTRACT.md`       |
| Stos technologiczny   | `TECH_STACK.md`         |
| Bieżący etap          | `CURRENT_STATE.md`      |
| Historia decyzji      | `DECISION_LOG.md`       |
| Kryteria ukończenia   | `DEFINITION_OF_DONE.md` |

Nie kopiuj pełnej reguły do kilku dokumentów. W dokumentach pomocniczych podaj
krótkie podsumowanie i link do właściciela reguły.

## Statusy

### Dokumenty

- `draft` — materiał roboczy,
- `proposed` — propozycja oczekująca na zatwierdzenie,
- `accepted` — obowiązujące źródło prawdy,
- `active` — dokument procesowy utrzymywany na bieżąco,
- `superseded` — dokument historyczny zastąpiony nowszym źródłem.

### Zadania

- `todo` — gotowe do rozpoczęcia,
- `in_progress` — aktualnie realizowane,
- `blocked` — nie może być kontynuowane bez decyzji lub zmiany stanu,
- `done` — ukończone i przenoszone do `tasks/completed/`.

## Reguła aktualizacji

Nowy plan lub dokument dopisuje się do [DOC_INDEX.md](DOC_INDEX.md) (podsekcja
„Dostarczanie” dla planów), nie do tego pliku. Zmiana zachowania produktu aktualizuje właściwy plik wymagań. Zmiana techniczna
wpływająca na strukturę systemu aktualizuje dokument architektury i, jeżeli
jest istotna, `DECISION_LOG.md` (pełny wpis w `process/decisions/` i wiersz
na górze indeksu; wiersze ponad 30 przechodzą do archiwum indeksu).

Przy zamykaniu taska agent dopisuje jego pełną sekcję `done` na początku
najnowszego archiwum `archive/CURRENT_STATE_*.md` (tekst bez zmian), w
`CURRENT_STATE.md` dodaje jednowierszowy wpis na początku „Ostatnie 10
ukończonych tasków” (format `- **TASK-NNNN** — tytuł — vX.Y.N / hash —
tasks/completed/<plik>.md`) i usuwa najstarszy wiersz ponad 10 (jego sekcja
jest już w archiwum), usuwa wskaźnik taska z „Aktywne taski” (wskaźniki
≤ 1 200 B) oraz aktualizuje „Obowiązujące ograniczenia” i „Plany”. Spójność
oba pliki sprawdza `npm run docs:check`
(`scripts/check_current_state_window.py`, `scripts/check_decision_links.py`),
a budżety bajtów obowiązkowego odczytu `scripts/check_startup_read_budget.py`.
