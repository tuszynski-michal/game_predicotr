---
title: Audyt routingu i write fence magazynu gry
status: accepted
last_updated: 2026-09-08
---

# Audyt TASK-0519

## Zakres

Audyt objął adapter `public` / `game_data_v2`, cykl życia sesji SQLAlchemy,
worker runtime, zabezpieczenia PostgreSQL, kontrakt katalogu gier oraz Admin.
Nie wykonywał migracji ani cutoveru na bazie użytkownika.

## Wynik

- Każdy zapis rozwiązuje aktualny status i generację oraz utrzymuje
  współdzieloną blokadę advisory gry i `FOR SHARE` do końca transakcji.
  Konkurencyjny cutover jest blokowany także dla legacy bez registry.
- Commit i rollback czyszczą binding; ponowne użycie tej samej sesji rozwiązuje
  registry od nowa i nie zachowuje starego transaction-local `search_path`.
- ORM/Core SELECT pozostaje odczytem. Flush, DML i nierozpoznany raw SQL są
  traktowane jako zapis, więc tekstowy DML nie omija maintenance.
- Scope requestu wynika z `/games/{gameId}` lub jawnego `game_id` operacji;
  worker przypina `claimed.game_id` tylko na czas handlera. Zapisy globalnego
  rekordu `jobs` po handlerze pozostają w `public`.
- 65 parentów v2 ma domyślny transaction-scoped `game_id`, wymuszone RLS i
  politykę `USING/WITH CHECK`. Siedem triggerów kolejki/review ma wersje
  schema-aware.
- Skan kwalifikowanych odwołań `public.<game-table>` wykazał wyłącznie celowe
  ścieżki utrzymaniowe starej gry: deletion repository i zamrożony eksport
  archiwum. Nie są one ogólnym routingiem aplikacji ani ścieżką v2.
- Admin pokazuje wersję/generację/status i blokuje edycję, archiwizację oraz
  przywracanie, gdy backend raportuje brak dostępności zapisu.

## Granice

Brak partycji i cutoveru oznacza, że dane użytkownika nadal pozostają w
`public`. TASK-0519 nie kopiuje danych i nie aktywuje v2 dla żadnej gry. Kolejne
zadania muszą używać tego adaptera podczas migracji danych; nie wolno zastępować
go ręczną zmianą `search_path`.
