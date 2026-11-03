# TASK-1149 — Weryfikacja strumieniowego blokowania wejść

Worktree `D:/game_predicotr/worktrees/grid-correction-growth`, baza `5cfe292b`.
Zmiana ogranicza liczbę zapytań sterujących timeoutem; nie zmienia zapytań
wybierających lub blokujących dane, ich kolejności, polityki ani limitów czasu.

## Dowód przyczyny i zakres poprawki

Odbiór TASK-1147 na istniejących danych zakończył pierwszy freeze błędem
`GRID_COHORT_TIMEOUT`. Kontrolowane normalne ponowienie tej samej komendy,
z tą samą rewizją i kluczem, zamroziło kohortę w 53,515 s. Pomiar prowadzącego:
`_lock_inputs` 33,641 s, etykiety 7,990 s, rejestr 7,156 s, populacja 1,344 s,
pliki 0,252 s. Źródło: główny checkout,
`artifacts/grid-growth-deploy-20261103/freeze-profile-result.json`.
Pomiar dotyczy kodu przed TASK-1149; udane ponowienie nie usuwa kosztu zapytań.

Wcześniej `deadline.check(session)` po każdym zablokowanym wierszu wykonywało
osobny SQL, dodatkowo obsługiwany przez istniejący hook timeoutu. Nowy prywatny
`_budgeted_rows` wykonuje tę kontrolę przed każdym `fetchmany(200)`, po pobraniu
sprawdza zegar bez SQL, przekazuje wiersze w niezmienionej kolejności i zwalnia
partię przed kolejnym odczytem. `finally` zamyka wynik. Konsumenci używają
`closing`, więc także błąd podczas pojedynczej blokady sekwencji zamyka kursor.

Wszystkie pięć strumieni korzysta z helpera: sekwencje, źródła, plansze,
review i komórki. Sekwencje pozostają blokowane pojedynczo i rosnąco;
przed ich SQL działa zwykła kontrola zegara oraz istniejący hook wykonania.
Ustawienie timeoutu przed każdym FETCH jest konieczne, ponieważ FETCH kursora
serwerowego omija `before_cursor_execute`. Limity 60/30/5 s pozostają bez zmian.

## Wyniki końcowe

| Kontrola | Wynik | Dowód |
|---|---|---|
| Unit cohort core | 57 PASS, 4,96 s | `artifacts/task1149-unit.log` |
| Ruff check bez fix | 3 pliki PASS | `artifacts/task1149-lint.log` |
| Ruff format --check | 3 pliki PASS | `artifacts/task1149-format.log` |
| Scoped mypy | 1 zmieniony moduł produkcyjny PASS | `artifacts/task1149-types.log` |
| PG selection/locks | 1 PASS, 52,75 s | `artifacts/task1149-selection.log` |
| PG registry i restart | 1 PASS, 61,65 s | `artifacts/task1149-registry.log` |
| Tożsamość SQL | 7 istniejących literałów SELECT identycznych z `5cfe292b` | `artifacts/task1149-sql-preservation.log` |
| Docs:check | PASS, startup 44820/45000 B | `artifacts/task1149-docs.log` |
| Mapa | Regeneracja oraz code-map:check PASS | `artifacts/task1149-map.log`, `artifacts/task1149-map-check.log` |

Testy uruchomiono po ostatnich zmianach kodu, z jawnym PYTHONPATH worktree.
Każdy proces testowy ma timeout 120 s, PG uruchamiano sekwencyjnie wyłącznie
na jednorazowych bazach. Scoped mypy wykorzystuje istniejącą konfigurację
lokalną z pominięciem importów torch, bez osłabiania konfiguracji projektu.
Nie jest to pełny projektowy quality gate.

## Pokrycie regresji

Nowe przypadki jednostkowe sprawdzają 0, 1, 200, 201 i 401 wierszy. Asercje
wiążą pobranie z kontrolą SQL przed i kontrolą zegara po nim, sprawdzają
dokładnie `ceil(N/200)+1` pobrań oraz zachowanie wszystkich wierszy w kolejności.
Wygaśnięcie przed drugim FETCH, po nim oraz błąd samego FETCH kończą strumień
bez przekazania drugiej partii, bez następnego pobrania i z zamkniętym kursorem.
Błąd konsumenta sekwencji również zamyka wynik i zachowuje oryginalny wyjątek.
Wstępne uruchomienie nowych testów przed helperem zakończyło się brakiem symbolu
(`task1149-before.log`); nie przedstawiamy tego jako odtworzenia czasu operatora.

Istniejący test PG rozszerzono z 30 do 270 komórek dwóch dziewięcioplanszowych
zdjęć, bez dużego korpusu. Sprawdza 18 plansz, 18 review, 270 komórek,
deduplikację i rosnące UUID, kolejność sekwencji 110–118 oraz 140–148,
trwałe blokady wszystkich wybranych wierszy, brak blokad nieużytych lub obcych
celów i dostępność w nowym połączeniu po rollbacku. Rzeczywisty hook timeoutu
pozostaje aktywny podczas `_lock_inputs`. Dokładnie 11 kontroli SQL obsługuje
pięć strumieni; źródła/sekwencje/plansze/review wymagają po dwóch pobrań,
komórki trzech (wliczając końcowy pusty FETCH). Test registry zachowuje wcześniejsze
kontrole v1/v2, release, rollback, receipt oraz odczyt w świeżym interpreterze.

## Granice i dalsze kroki

Nie wykonano nowego treningu, benchmarku na dużym zbiorze, operacji na bazie
operatora ani kontroli usług. Nie zmieniono migracji, schematu, kontraktu API,
minimum danych, doboru celów ani treści SQL. Nie powtarzano UI/build.
Nie podajemy nowego czasu freeze na danych operatora bez pomiaru prowadzącego.

Niezależny audyt Opus 5.5/high zakończył się PASS, bez P0/P1. Zapis
commita, wdrożenie oraz task-close prowadzi root. Odbiór uczenia TASK-1147
pozostaje osobnym, trwającym krokiem; ten raport go nie zastępuje.

## Jedna runda po audycie — P2-1

Raport `TASK-1149_AUDIT_claude-opus-5-5.md` zachowano bez zmian. W teście PG
dopisano bezpośrednie asercje blokad `source_images` dla obu wybranych źródeł
oraz źródła z nieużytymi etykietami. To ostatnie jest celowo blokowane przez
politykę korekt, podczas gdy jego nieużyte plansze/review/komórki pozostają wolne.
Obce źródło jest dostępne w sesji obcej gry. Po rollbacku wszystkie trzy źródła
własnej gry są dostępne z nowego połączenia. Bez zmiany fixture, skali lub kodu
produkcyjnego.

Końcowy PG selection: 1 PASS, 44,09 s
(`artifacts/task1149-p2-selection.log`). Ruff check bez fix i format --check
zmienionego testu: PASS (`task1149-p2-lint.log`, `task1149-p2-format.log`).
P2-1 zamknięte. Nie powtarzano pozostałych aktualnych testów. Dodatkowe testy
PG wymienione przez audytora jako opcjonalne odłożono; nie stanowią warunku PASS.
P2-2 dotyczące rozdzielenia stagingu TASK-1149/TASK-1150 oraz samych końców linii
rozlicza prowadzący. Nie wykonano ponownego audytu, stagingu ani commita.

## Pomiar prowadzącego po audycie

Ten sam operatorowy zestaw788 źródeł/124 użytych zdjęć, kohorta8c4d3ab4 w rewizji164. Osobny proces załadował zaudytowany helper1149 z worktree, przy niezmienionych limitach i SQL. `_lock_inputs` zajęło3,968s wobec33,641s w pierwotnym pomiarze. To pomiar fazy blokowania, nie nowego pełnego freeze. Wszystkie blokady zakończono jawnym rollbackiem; stan przed i po `frozen/164` identyczny. Nie utworzono nowego przebiegu ani receipt i nie zmieniono budżetu/modelu. Źródło: głównycheckout `artifacts/grid-growth-deploy-20261103/batched-lock-profile.json` i `.log`.

P2-2: prowadzący stage obejmuje jawnie wyłącznie1149 i metadane task-close; pliki workera1150 pozostają do jego osobnego audytu/commita. Generowane mapy z samą różnicą EOL normalizowane zgodnie z repo, bez zmiany treści.
