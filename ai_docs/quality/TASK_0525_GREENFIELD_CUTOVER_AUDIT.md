---
title: TASK-0525 greenfield cutover audit
status: accepted
last_updated: 2026-09-09
---

# Audyt greenfield cutover

## Wynik

Bramka pozytywna. Produkcyjna ścieżka tworzenia gry nie może już zapisać
location `public`. Aktywacja następuje dopiero po walidacji 65 partycji i
inicjalizacji polityki geometrii w partycji V2.

## Dowody

- Izolowany PostgreSQL utworzył grę przez ten sam repository composition co API.
- Location końcowe: `game_data_v2`, generacja 2, `active`.
- Dokładnie 65 fizycznych partycji tabel gry.
- Jeden inicjalny rekord geometrii w V2 i zero w public.
- Brak registry: projekcja katalogu `blocked`, write zwraca
  `GAME_STORAGE_LOCATION_MISSING`.
- Routing i lifecycle po restartach transakcji zachowują checkpoint.
- Admin blokuje mutacje dla `storageWriteAvailable=false`.

## Stan bazy użytkownika

Odczyt po migracjach: `0110_game_partition_lifecycle`, zero gier, 65 rekordów
manifestu game-owned, 65 parentów partycjonowanych, zero partycji konkretnych
gier oraz zero location. Żadnej gry nie utworzono w ramach audytu.

## Niezmienione granice

- `public.games`, `public.jobs`, symbole i reguły pozostają katalogiem zgodnie z
  mapą własności; operacyjne tabele game-owned są kierowane do V2.
- Nie wykonano migracji danych, dual-write, GC ani usuwania legacy schema.
- TASK-0526 pozostaje zależny od osobnej decyzji użytkownika.
