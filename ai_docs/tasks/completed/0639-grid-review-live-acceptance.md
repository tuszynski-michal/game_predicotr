---
title: TASK-0639 — odbiór na żywych danych (bez zmian kodu i danych)
status: done
last_updated: 2026-09-24
---

# TASK-0639 — odbiór na żywych danych (bez zmian kodu i danych)

## Status

`done`

## Goal

Potwierdzić na żywym API/DB/Reviewerze (gra 777, `game_data_v2`), że
naprawa z TASK-0637/TASK-0638 rzeczywiście przywraca podglądy oryginałów i
cropów, bez wykonywania jakiegokolwiek zapisu.

## Context

Ostatni task planu D-442. Read-only odbiór na dokładnie tych danych, które
posłużyły do pierwotnej diagnozy (dowody F1–F7 w przekazanym planie).

## Dependencies / entry conditions

- TASK-0637 (v0.10.409) i TASK-0638 (v0.10.410) ukończone.
- API `python -m game_predictor_api --reload` już działało (port 8000,
  PID 10828) — zmiana z T1/T2 backendu weszła bez restartu.
- Reviewer (port 3001) **nie działał** na początku tej sesji — uruchomiony
  jako `npm run reviewer:start` (kontrolowany proces w tle, PID 12848) na
  buildzie z T2 (`npm run reviewer:build` uruchomiony w TASK-0638).
- Admin (port 3000) działał (PID 4636) — nie dotknięty.

## Recommended execution

claude-sonnet-5, reasoning: high. Weryfikacja read-only w przeglądarce i
sieci; wymaga dyscypliny, by nie kliknąć zapisu. Dodatkowy review: nie.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-442)

## Scope

- Otworzyć `http://127.0.0.1:3001/?mode=local&gameId=bfc4f949-5c14-4850-b02a-db99610bcfa5&importJobId=6a47766c-61e9-40e4-a382-fadb8dc374dc`
  we wbudowanej przeglądarce.
- Sprawdzić zakładki „Do walidacji”, „Do poprawy”, „Wszystkie”: oryginał
  się renderuje, `source-asset` → 200.
- Sprawdzić dokładnie „Plansza 1 · sekwencja 379306” (przypadek z F1/F5
  diagnozy) i deferred slot (board bez automatycznej geometrii,
  `pendingGeometryId`).
- Wygenerować podgląd cropów przyciskiem porównania A/B (nie zapisywać).
- Sprawdzić konsolę przeglądarki pod kątem błędów JS.

## Out of scope

- Jakikolwiek zapis: zatwierdzenie planszy/zdjęcia, zapis geometrii,
  odrzucenie.
- Reimport, regeneracja cropów, zmiany danych.
- Pełny scenariusz z sekcji T3 planu (szybkie przełączanie + F5 + dokładna
  weryfikacja pikseli canvas vs. tło) — częściowo wykonany (patrz Outcome),
  część pominięta świadomie ze względu na ograniczenia narzędzia
  zrzutów ekranu w tej sesji (patrz Not completed).

## Acceptance criteria

- [x] „Do walidacji”: oryginał renderuje się z nałożoną siatką.
- [x] „Do poprawy”: „Plansza 1 · sekwencja 379306” (dokładny przypadek z
      diagnozy) renderuje się; `source-asset` → 200 dla dokładnie
      `reviewItemId=0b9166a1-b860-4859-b28f-eacee097ef2c`,
      `expectedSourceChecksumSha256=befcf58d…f32f4` (identyczne parametry
      co w kryterium zakończenia TASK-0637).
- [x] Deferred slot (`#4 · 379309 · obowiązkowa ręczna geometria`,
      `pendingGeometryId`) pokazuje panel „Podgląd 15 cropów wybranej
      planszy” bez błędu.
- [x] „Wszystkie” działa; wygenerowanie porównania A/B → `geometry-preview`
      → 200.
- [x] Brak błędów w konsoli JS.
- [x] Brak zapisów: `Zatwierdzone` pozostało `0` przez cały odbiór; żadne
      żądanie `PUT`/`geometry-revisions`/`geometry-approval`/`source-geometry-approval`
      nie zostało wykonane.

## Technical notes

Zaobserwowane w Network (wbudowana przeglądarka):

```
GET .../image-reviews/19a7bdb9-3a3e-406f-a1da-f4a8ae374185/source-asset?...gameId=bfc4f949-... → 200 OK   (Do walidacji, plansza 1 · 379252)
GET .../image-reviews/0b9166a1-b860-4859-b28f-eacee097ef2c/source-asset?...gameId=bfc4f949-... → 200 OK   (Do poprawy, plansza 1 · 379306 — dokładny przypadek z diagnozy)
POST .../image-reviews/19a7bdb9-.../geometry-preview?gameId=...&importJobId=6a47766c-... → 200 OK          (Wszystkie, porównanie A/B)
```

Przed naprawą (TASK-0637) te same żądania zwracały 409
`IMAGE_GRID_REVIEW_PROJECTION_INCOMPLETE`.

## Expected files

Brak — task wyłącznie weryfikacyjny, bez zmian kodu/danych.

## Test cases

Manualne, opisane w Scope/Acceptance criteria powyżej.

## Verification

Wykonane ręcznie we wbudowanej przeglądarce (patrz Outcome). Brak
automatycznych komend do uruchomienia poza już uruchomionym Reviewerem.

## Risks / open questions

- Zrzuty ekranu (`computer.screenshot`) w tej sesji wielokrotnie kończyły
  się timeoutem/pustym kadrem mimo poprawnie działającej strony
  (potwierdzone przez `get_page_text`/Network); dwa wcześniejsze zrzuty w
  tej samej sesji renderowały obraz planszy poprawnie (z nałożoną siatką),
  więc traktuję to jako ograniczenie narzędzia przechwytywania, nie wadę
  aplikacji. Pełna weryfikacja pikselowa (`canvas.width === naturalWidth`,
  piksele ≠ tło) z sekcji T3 planu nie została wykonana — patrz Not
  completed.
- Nie wykonano szybkiego przełączania plansz/zakładek + F5 (regresja
  „obraz poprzedniego źródła”) — deferred do następnej weryfikacji
  manualnej użytkownika, jeśli potrzebna.
- Reviewer pozostał uruchomiony (`npm run reviewer:start`, PID 12848) po
  zakończeniu tego taska — użyteczne dla dalszej pracy użytkownika w
  Revieverze; można zatrzymać na życzenie.

## Outcome

### Changed

- Brak zmian kodu/danych — task wyłącznie weryfikacyjny.
- `ai_docs/process/CURRENT_STATE.md`: nowa notatka.

### Verification results

- Otwarto Reviewer (`http://127.0.0.1:3001/?mode=local&gameId=bfc4f949-…&importJobId=6a47766c-…`)
  we wbudowanej przeglądarce.
- **Do walidacji**: „Plansza 1 · sekwencja 379252” — `source-asset` → 200,
  obraz z nałożoną siatką widoczny na zrzucie ekranu.
- **Do poprawy**: „Plansza 1 · sekwencja 379306” (identyczny przypadek jak
  w F1/F5 pierwotnej diagnozy) — `source-asset` → 200, obraz z nałożoną
  siatką widoczny na zrzucie ekranu.
- **Do poprawy, board #4** (`379309`, deferred slot,
  `IMAGE_GRID_REVIEW_DEFERRED_SLOT`, brak automatycznej geometrii): panel
  „Podgląd 15 cropów wybranej planszy” obecny, brak komunikatu błędu.
- **Wszystkie**: lista ładuje się; tryb edycji + „Generuj porównanie A/B”
  → `POST geometry-preview` → 200 OK (`image/png`); panel porównania
  „A · Automat / B · Edycja” pojawił się po wygenerowaniu.
- Konsola JS: 0 błędów (`read_console_messages`, `onlyErrors=true`).
- Brak zapisów: `Zatwierdzone` = `0` przez cały czas; jedyne żądania
  sieciowe do `/image-reviews/…` to `GET source-asset`,
  `OPTIONS`/`POST geometry-preview` — brak `geometry-revisions`,
  `geometry-approval`, `source-geometry-approval`.

### Not completed

- Pikselowa weryfikacja canvas (`naturalWidth`, piksele ≠ tło `#555`) nie
  wykonana — narzędzie zrzutów ekranu w tej sesji było niestabilne po
  interakcjach z panelem edycji (timeout/pusty kadr), mimo że dane
  sieciowe i tekst strony potwierdzają poprawne działanie. Dwa wcześniejsze
  zrzuty w tej samej sesji (przed wejściem w tryb edycji) pokazały obraz
  planszy z nałożoną siatką poprawnie.
- Scenariusz „szybkie przełączanie + F5 + brak obrazu poprzedniej planszy”
  nie wykonany.
- Regresja Admin „Weryfikacja symbolu na planszy” (F6) nie zweryfikowana
  ponownie na żywo w tej sesji — endpoint niedotknięty przez TASK-0637/0638
  (inny router, `symbol-cell-reviews`), wcześniej potwierdzona działająca
  w pierwotnej diagnozie.
- Skrypt read-only sprawdzający istnienie wszystkich `originals/` (F3)
  przed/po nie uruchomiony ponownie — dane nie były modyfikowane w żadnym
  z tasków T1–T3, więc powtórka nie wnosi nowej informacji.

### Documentation updates

- `ai_docs/process/CURRENT_STATE.md` — nowa notatka, na górze.
- Ten plik przeniesiony do `ai_docs/tasks/completed/`.

### Recommended next task

- T4 / TASK-0640 (zalecane w planie, wymaga osobnej zgody użytkownika):
  bezpiecznik skryptu legacy GC (`scripts/preview_legacy_game_managed_asset_gc.py`),
  żeby nie mógł zakwalifikować oryginałów gier V2 do usunięcia.
