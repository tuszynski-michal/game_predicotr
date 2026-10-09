# Audyt TASK-0938 - Okno kroczące `CURRENT_STATE.md` i indeks `DECISION_LOG.md`

Werdykt: REVISE
Audytor: gpt-6-astra, medium
Wykonawca: claude-sonnet-5-5, medium
Zakres: HEAD...7b7b0a7e4b1b63fbde4518ccdabe336443ef1728 oraz zmiany niezacommitowane, data 2026-10-09
Runda: 1

Przegląd statyczny, bez zmian w plikach.

## Streszczenie

Przeniesienie treści zachowuje wszystkie 597 bloków stanu bez utraty i powielenia, a treść decyzji w pliku rocznym odpowiada dotychczasowej. Oba dokumenty startowe mieszczą się w limicie, a oba checkery zwracają sukces. Przed commitem wymagają poprawy nieaktualny wpis TASK-0937 oraz kontrola błędnych ścieżek linków.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `ai_docs/process/CURRENT_STATE.md:703` — Nowy wpis TASK-0937 podaje `todo`, podczas gdy bieżący plik zadania ma status `blocked` i gotowe narzędzie pilota (`ai_docs/tasks/0937-gold-frame-detection-pilot.md:5`). Okno pomija również konkretne warunki odblokowania: migrację 0152, przeliczenie serii, pięć zdefiniowanych super symboli i etykiety operatora. Dokument startowy przedstawia nieaktualny stan pracy. Zaktualizować wpis na podstawie bieżącego taska i odnotować istniejący commit `v1.7.281` / `7b7b0a7e4b1b63fbde4518ccdabe336443ef1728`.

- [P1-2] `scripts/check_decision_links.py:98` — Gdy wskazany plik nie istnieje, checker zastępuje ścieżkę znalezionym plikiem o tej samej nazwie w katalogu procesu. Przykładowy link `missing/DECISION_LOG.md#d-537--…` może przejść kontrolę, choć pozostaje niedziałającym linkiem Markdown. Kontrola kotwicy nie zastępuje kontroli rzeczywistego celu linku. Dla linków Markdown wymagać istnienia dokładnej ścieżki względnej; ewentualne rozpoznawanie skrótowych odwołań tekstowych obsługiwać osobno.

### P2

- [P2-1] `ai_docs/process/DECISION_LOG.md:27` — Reguła archiwizacji stosuje próg około 90 KB do samej tabeli, choć limit 100 KB dotyczy całego pliku, zawierającego również pięć pełnych decyzji. Checker decyzji nie kontroluje rozmiaru. Przy kolejnych wpisach można przekroczyć limit mimo stosowania instrukcji i zielonego `docs:check`. Zalecane: kontrolować rozmiar całego dokumentu i od niego uzależnić przenoszenie wierszy indeksu.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Oba pliki < 100 KB; przeniesiona treść bez zmian | spełnione | Odczyt rozmiarów: 74 740 B i 69 939 B. Porównanie 597 bloków HEAD: zero brakujących i zero powielonych; treść dawnego dziennika decyzji zachowana w pliku rocznym. |
| Ograniczenia, aktywne taski, plany i otwarte decyzje; checker PASS | niespełnione | Sekcje istnieją; checker: 37 aktywnych tasków, 10 sekcji `done`, PASS. Wpis TASK-0937 jest nieaktualny — P1-1. |
| Wszystkie linki `DECISION_LOG.md#d-` rozwiązują się | spełnione | Odczytowa kontrola bieżących plików: `534 anchor links, 534 entries, 534 index rows`, PASS. P1-2 dotyczy niewiarygodnego wykrywania błędnych ścieżek. |
| `AGENTS.md` i README opisują nowy obowiązkowy odczyt | spełnione | `AGENTS.md:12`, `ai_docs/README.md:19`. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P1-1, P1-2, P2-1.

## Proponowane testy

- Dla `scripts/check_decision_links.py` dodać przypadek istniejącej kotwicy wskazanej przez nieistniejącą ścieżkę. Oczekiwany wynik: exit 1.
- Dla limitu dokumentów dodać przypadek przekroczenia 100 000 B przez cały `DECISION_LOG.md`, przy tabeli mniejszej niż 90 KB.
- Po poprawkach uruchomić `npm run docs:check` oraz porównać wpis TASK-0937 z jego sekcjami `Status` i `Outcome`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, aktywny task, odpowiedni fragment etapu T, dokumenty procesu, zmienione instrukcje i oba checkery. Archiwa sprawdzono przez odczytowe porównanie bloków z HEAD; roczny dziennik decyzji przez porównanie zachowanej treści.

Uruchomiono wyłącznie odczytowe checkery i porównania danych w pamięci. Nie wykonywano pełnej bramki jakości, operacji usług ani zmian plików. Wyniki lintowania i kontroli typów pozostają deklaracjami wykonawcy z `Outcome`. Nie potwierdzono ręcznie aktualności wszystkich historycznych ograniczeń ani wszystkich streszczeń indeksu.

## Nota leada po rundzie 1 (2026-10-09)

P1-1, P1-2 i P2-1 naprawione (wpis TASK-0937 jako `blocked` z warunkami odblokowania, checker linków wymaga dokładnej ścieżki względnej, limit 100 000 B liczony dla całego `DECISION_LOG.md`; 4 nowe testy skryptu). `npm run docs:check` PASS. Commit bez drugiej rundy zgodnie z regułą szybkiego audytu.
