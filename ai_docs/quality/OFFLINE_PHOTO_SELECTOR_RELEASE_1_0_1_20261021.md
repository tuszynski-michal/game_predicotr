---
title: Selektor Windows 1.0.1 — kontrola wydania
status: active
last_updated: 2026-10-21
---

# Selektor Windows 1.0.1 — TASK-1078

## Zakres

Jedno rozpoznawanie folderu źródła/projektu/manifestu, kompaktowy interfejs bez checkboxa i opisów lokalności, wspólne style przycisków Admina i desktopu (32 px w desktopie, domyślnie 42 px), limit 500000, edycja kierunku oraz kolejny folder z zachowaną grą.

Źródła kontraktu: [wymagania](../requirements/MANUAL_IMAGE_SELECTION.md), [architektura](../architecture/MANUAL_IMAGE_SELECTION.md), D-567.

## Weryfikacja

- Test interfejsu Electron na osobnych danych: poprawne kolory i wysokość przycisków, zachowany domyślny styl współdzielony, jeden rząd przycisków i kontrolek, duży podgląd, fullscreen, zapis `seq_499996-500000.jpg`, pięć plansz w manifeście, zmiana kierunku po terminalnej decyzji, anulowanie nowego folderu/formularza oraz wznowienie w nowym procesie.
- Testy lokalnego projektu obejmują przerwanie procesu po prepared i idempotentne ponowienie zmiany kierunku wraz z ograniczeniem starego projektu bez granicy.
- Import zachowuje sumy kontrolne i oryginały, a stary v1 z niejednoznacznym zakończeniem nadal jest odrzucany. Błędne JSON-y nie są przepisywane.
- Lint i typecheck desktopu; bundlowanie CSS Admina wraz z nowymi importami wspólnych stylów.
- Pokrycie wszystkich 269 testów w grupach; monolityczny przebieg zakończony limitem 120 s, bez utraty wyników już zaliczonych przypadków. Dwa końcowe compact-persistence: 2/2. Pozostałe pliki: 171/172 przed poprawką sprzątania workera w nowym teście; po niej cały legacy-contract 27/27. Pierwsza regresja terminalnego v1 także usunięta. Brak otwartych porażek.
- ZIP: sprawdzenie SHA-256, dokładnej zawartości app.asar i uruchomienie świeżo rozpakowanego EXE. `smoke:release:workflow`, `smoke:release:legacy`, `smoke:release:start`: PASS.
- Formatowanie, lint, typecheck, build, docs:check i code-map:check: PASS. Nie wykonywano audytu krzyżowego (brak wymagania planu).

## Artefakty

Końcowa paczka: `artifacts/selector-releases/1.0.1/Selektor zdjec-win32-x64-1.0.1.zip`. Obok znajdują się `.sha256` i `.release.json`; podgląd to `selection.png`. Kopię paczki ponownie sprawdzono SHA-256.

- Wersja aplikacji: **1.0.1**.
- Rozmiar ZIP: **149412820 B**.
- SHA-256 ZIP: `cf59acc740a80265965024803ebe4e61a5b6a9f9322885372f6d5bda0b5b6ba4`.
- SHA-256 app.asar: `056a715d6b19bcc69aced14a915c1c2410991fbc396c69ccf7cf7ddc5be2404c`.
- Commit źródeł: `206e1755b3caf37d711a8cbcc4ad77b8024d0554` (v1.7.451).
- `applicationSourceDirty=false`; `dirty=true` wynika z zastanych zmian poza aplikacją, niewłączonych do commita. Metadane zachowują rzeczywisty stan, bez czyszczenia plików operatora.
- Końcowy ZIP z commita ponownie przeszedł wszystkie trzy scenariusze release: workflow, legacy i start.

## Ograniczenia

Testy działają na wygenerowanych fixture'ach. Nie zmieniano sesji, źródeł, JPEG-ów ani manifestów operatora. Nie uruchamiano ani nie restartowano jego usług i aplikacji. Nie wykonywano pomiarów wydajności ani fizycznego odbioru na drugim komputerze. Błędne historyczne nazwy z końcem 500004 wymagają cofnięcia wyboru i ponownego zapisu, a nie automatycznej podmiany plików. Scalenie i push wymagają osobnej zgody.
