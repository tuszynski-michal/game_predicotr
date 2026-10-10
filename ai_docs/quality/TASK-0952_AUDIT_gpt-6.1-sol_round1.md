# Audyt TASK-0952 - Kopia zapasowa bazy na D przed przeniesieniem

Werdykt: REVISE
Audytor: gpt-6.1-sol, medium
Wykonawca: claude-opus-5-5, reasoning nieodnotowany
Zakres: HEAD...ef345c6b42bcc079e8097bb51124faed4907c99b oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-10
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Pliki kopii istnieją na D, a zapisany log potwierdza kody wyjścia 0 dla obu zrzutów, spisu archiwum i pełnego odczytu. Raport stanu zawiera wymagane wartości, ale zapisano go poza lokalizacją określoną w zadaniu. Przed commitem należy uzupełnić dokumentację odbioru i wynik wymaganej kontroli dokumentacji.

## Znaleziska

### P0

- [P0-1] `ai_docs/tasks/completed/0952-disk-d-database-backup.md:144` - `Outcome` nie podaje rozmiaru pliku `.toc.txt`, mimo wymagania zapisania rozmiarów w pierwszym kryterium akceptacji (linie 79–82). Plik istnieje i ma 481 073 bajty. Uzupełnić tę wartość; nie trzeba ponawiać zrzutu.

### P1

- [P1-1] `ai_docs/tasks/completed/0952-disk-d-database-backup.md:146` - raport zapisano jako `artifacts/audits/db-state-stage-a.txt`, natomiast zakres i lista oczekiwanych plików wskazują `artifacts/maintenance/disk-d-migration/db-state-stage-a.md`. Wymagany plik nie istnieje. Utrudnia to odnalezienie dowodu przez kolejne zadania. Zapisać istniejący raport w wymaganej lokalizacji i poprawić odwołanie w `Outcome`, bez ponawiania odczytów bazy.

- [P1-2] `ai_docs/tasks/completed/0952-disk-d-database-backup.md:149` - sekcja weryfikacji nie dokumentuje wyniku obowiązkowego `npm run docs:check` po zmianie okna `CURRENT_STATE.md` i archiwum. Brak dowodu wykonania wymaganej kontroli procesu. Uruchomić ją przed commitem i zapisać wynik w `Outcome`.

### P2

- [P2-1] `ai_docs/tasks/completed/0952-disk-d-database-backup.md:153` oraz `ai_docs/process/CURRENT_STATE.md:799` - liczba 264 obejmuje także wpis `ACL game_data_v2 TABLE dataset_versions`, ponieważ wyszukiwanie podciągu `TABLE DATA` dopasowuje początek nazwy tabeli. Faktycznych wpisów typu `TABLE DATA` jest 263: 204 w `game_data_v2` i 59 w `public`. Poprawić liczbę w dokumentacji i stosować wzorzec `^\d+; \d+ \d+ TABLE DATA `. Obecność danych obu schematów jest potwierdzona.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Pliki na D; rozmiary, SHA-256 i kody wyjścia w `Outcome` | niespełnione | Pliki istnieją; rozmiary obu zrzutów i hashe zapisano w tasku:140–143, kody w tasku:151–155. Brakuje rozmiaru spisu — P0-1. |
| `TABLE DATA` obu schematów i zapisana liczba wpisów | spełnione | Odczyt `.toc.txt`: 204 wpisy `game_data_v2`, 59 `public`, 4727 pozycji spisu. Błędny łączny licznik opisano w P2-1. |
| Pełny odczyt archiwum, kod 0 i czas | spełnione | `D:\game_predictor_backup\task0952-20261010-0100.log:5`: kod 0, 943 s; task:155. |
| Zapisany raport stanu; zgodność wartości lub wyjaśnienie odchyleń | spełnione | `artifacts/audits/db-state-stage-a.txt:1`: 88 GB; linie 2–37 zawierają rewizję, tabele, joby, sesje i rozmiary baz. Wzrost wyjaśniono w tasku:162–163. Lokalizacja wymaga poprawki P1-1. |
| Czas zrzutu i wolne miejsce po zrzucie | spełnione | Task:152 i task:156; log:3 i log:8: 1594 s oraz 1802,7 GB. |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P0-1, P1-1, P1-2, P2-1.

## Proponowane testy

- Dla zmian w `ai_docs/process/CURRENT_STATE.md`, archiwum i pliku taska uruchomić `npm run docs:check` z limitem 120 s; zapisać wynik w `Outcome`.
- Dla spisu `D:\game_predictor_backup\game_predictor-20261010-0100.toc.txt` potwierdzić licznik poleceniem `(Select-String -LiteralPath 'D:\game_predictor_backup\game_predictor-20261010-0100.toc.txt' -Pattern '^\d+; \d+ \d+ TABLE DATA ').Count`. Oczekiwany wynik: 263.

## Zakres przeglądu i ograniczenia

Przeczytano brief, zadanie, właściwe fragmenty planu i runbooka, dokumenty procesu oraz diff trzech wskazanych plików. Odczytano raport stanu, log wykonania i pełny spis archiwum. Potwierdzono istnienie i rozmiary plików oraz niezależnie SHA-256 zrzutu ról.

Nie ponawiano hashowania archiwum 33,8 GB, poleceń PostgreSQL, zrzutu ani pełnego odczytu. Ich wyniki oceniono na podstawie zapisanego logu. Nie uruchamiano testów, usług ani odtworzenia próbnego. Audyt odbywa się przed commitem, więc brak jego wersji i hasha w `Outcome` nie stanowi znaleziska na tym etapie.