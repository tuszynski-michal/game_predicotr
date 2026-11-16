---
title: Winning chart points and compact board preview
status: done
last_updated: 2026-11-16
---

# TASK-1232 — Wygrane na wykresie i miniatura planszy

## Status

`done`

## Goal

Kliknięcie wybiera rzeczywistą wygraną, a jej planszę można obejrzeć bez zasłaniania ekranu w Adminie i udostępnianej wyszukiwarce.

## Context

Operator zlecił oba usprawnienia globalnie. Dotychczasowe maksimum z wszystkich spinów ±50 mogło wypaść na pustym lewym brzegu okna. Kliknięcie znacznika ponownie wykonywało przyciąganie zamiast otworzyć jego planszę.

## Dependencies / entry conditions

Wspólny pakiet `board-search-ui`; istniejące porty szczegółów i zdjęcia planszy działają także przez adapter publiczny. Zastane zmiany TASK-1230/1231 pozostają poza zakresem. Git odmówił utworzenia gałęzi roboczej z powodu braku zapisu `.git`; implementacja pozostaje w bieżącym checkout do przeglądu, bez merge/push.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — wyszukiwanie plansz, przybliżona wygrana.
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` — współdzielony UI i publiczny adapter.
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md`

## Scope

- Maksimum bilansu tylko wśród dodatnich, nieprowizorycznych wypłat w ±50 spinach; remisy: bliskość, potem wcześniejszy spin.
- Bezpieczne założenie: brak wygranej w oknie oznacza komunikat i brak nowego przypięcia, bez skoku do dalekiej planszy.
- Miniatura pod wykresem po wyborze wygranej, po kliknięciu jej znacznika lub akcji przy etykiecie/przypięciu. Jedna plansza naraz; zamknięcie i retry.
- Identyfikator planszy pochodzi z `row.sequenceNumber`, nigdy z dodawania spinu do startu (zawijanie sekwencji).
- Zachować strzałki, hover, odpinanie, filtr tabeli, kontrolowane piny i pełne okno linii wypłat.

## Out of scope

API, migracje, dane i kalkulator wypłat, niezmienne wyniki historyczne, restart usług, merge, push, wdrożenie.

## Acceptance criteria

- [x] Maksimum nie wybiera pustego spinu ani prowizorycznej wypłaty; brak kandydata jest jawny.
- [x] Wskazany znacznik otwiera własną planszę bez ponownego przyciągania do innego maksimum.
- [x] Podgląd jest ograniczony szerokością i wysokością, nie jest modalem; działa z publicznym adapterem.
- [x] Loading/error/brak zdjęcia i spóźnione odpowiedzi nie pokazują innej planszy.
- [x] Testy logiki i interakcji, lint, typecheck i dokumentacja sprawdzone.

## Expected files

- `packages/board-search-ui/src/board-search-approximate-win-state.ts` — `approximateWinBestPointNearSpin`.
- `packages/board-search-ui/src/board-search-approximate-win.tsx` — `ApproximateWinBalanceChart`, przekazanie klienta.
- Nowy `packages/board-search-ui/src/board-search-chart-preview.tsx` — `BoardSearchChartPreview`.
- `packages/board-search-ui/src/board-search.css`.
- `packages/board-search-ui/test/board-search-approximate-win-state.test.mjs`.
- `packages/board-search-ui/test-interactions/board-search-approximate-win.test.mjs`.
- `apps/admin/src/features/board-search/board-search-share-query-log.tsx` — klient miniatury w dzienniku.
- Wymagania, mapa kodu i bieżący stan.

## Test cases

- Opadający pusty odcinek przed rzeczywistą wygraną; pusty zakres; końce; remisy i supergra.
- Zaznaczenie i odpinanie w trybie lokalnym i kontrolowanym; marker i przycisk bez zmiany pinów.
- Sekwencja zawijająca się: spin 200, plansza 7; użycie checksum i rewizji assetu.
- Zmiana planszy podczas pobierania, zamknięcie, błąd API/obrazu i ponowienie.

## Verification

Komendy z katalogu repo, każda z timeoutem 120 s: testy Node/tsx pakietu, ESLint zmienionych plików, `tsc --noEmit` pakietu i konsumentów, `npm run docs:check`, `npm run code-map:check`. Build konsumentów po uprzedzeniu, jeśli pozwoli stan działających usług.

## Outcome

Commit: v1.7.647 (hash dopisuje kolejny commit).

### Changed

- Wybór maksimum pomija puste spiny i wypłaty prowizoryczne; zachowuje ±50, rozstrzyganie remisów i bilans po wypłacie, także ujemny.
- Wspólny wykres otwiera nieblokujący podgląd po wyborze wygranej; marker, akcja SVG i przycisk HTML otwierają własną planszę bez zmiany przypięć. Pusty klik pokazuje komunikat i zamyka poprzedni podgląd.
- Karta korzysta z klienta Admin/publicznego; wiersz wyznacza `sequenceNumber`, obraz wiąże checksum i rewizję. Brak/stare zdjęcie, obca tożsamość, spóźniona odpowiedź i retry są obsłużone.
- Niezmieniony kontrakt API, pełny modal, hover/strzałki i ręczne piny paneli. Zmiana dostępna we wspólnym UI Admina, linku online i panelu wielu gier oraz dzienniku Admina; historyczne snapshoty bez zmian.
- Niezależny audyt nie jest wymagany przez żaden plan tego zadania.

### Verification results

- Testy unit całego `board-search-ui`: PASS; zmieniony plik logiki 32/32 PASS.
- Zmieniony plik interakcji: 32/32 PASS, następnie dodatkowe 4/4 przypadki braku/starego/obcego zdjęcia PASS.
- Pełne interakcje pakietu: 120/121 PASS. Jedyny FAIL to `Admin opens the editable series modal in StrictMode...` w `super-game-series-modal.test.mjs`: dwie kopie Reacta (`apps/admin/node_modules/react` i `packages/board-search-ui/node_modules/react-dom`), wyjątek `useMemo` w niezmienionym wrapperze Admina (brak diff względem HEAD). Poza zakresem; nie zmieniano testu ani zależności.
- Publiczny adapter i proxy Reviewer/panel: 38/38 PASS.
- Typecheck pakietu, Admina i Reviewera: PASS. ESLint zmienionych modułów i pliku Admina: PASS. Prettier zmienionych plików kodu/testów/CSS: PASS.
- Chrome headless: szerokości 1100/390 px PASS; karta 380/344 px, zdjęcie 214,8/193,2 px; brak poziomego overflow i modala, marker otwiera właściwą planszę. Zrzuty i skrypt w `artifacts/task-1232/` (ignorowane).
- Mapa kodu zregenerowana; `code-map:check` PASS. Łatka tylko tego taska w `artifacts/task-1232/code-map-task-only.patch` chroni zastane zmiany mapy innych tasków.
- `docs:check` po zamknięciu przez skrypt: PASS (okno 16 667 B, odczyt startowy 44 995 B, wszystkie 11 budżetów i kopie procedur zgodne). Wcześniejsze przekroczenie po dodaniu wskaźnika usunięte prawidłowym zamknięciem taska.
- `git apply --cached --check artifacts/task-1232/commit-scope.patch`: PASS; to kontrola łatki bez zapisu indeksu.

### Not completed

- Commit nie został wykonany przez Codex: zwykły `git switch -c codex/chart-win-preview` dostał `Permission denied` przy zapisie `.git`. Nie stosowano obejścia uprawnień.
- Na polecenie użytkownika podjęto przekazanie informacji do Claude Code przez CLI odkryte procedurą `Resolve-AuditorCli`. Stan uwierzytelnienia wskazuje aktywne logowanie. Dwie próby informacyjne (stdin, następnie argument pozycyjny z niskim effort) zakończono po 60 s bez potwierdzenia; pośredni błąd parsowania argumentu poprawiono. Nie ma potwierdzenia odbioru ani commita. Zakres, wyniki i kontrolowana łatka są w `ai_docs/quality/TASK_1232_COMMIT_HANDOFF.md` i `artifacts/task-1232/commit-scope.patch`. Nie podnoszono uprawnień ani nie włączano narzędzi zapisu w sesji przekazania.
- Bez merge, push, restartu usług i wdrożenia. Brak pełnych buildów Next i testu faktycznego linku operatora; weryfikacja UI odbyła się na izolowanym bundlu komponentu i publicznym adapterze z kontrolowanymi odpowiedziami.

### Documentation updates

- Wymagania `ADMIN_APP.md`, wspólna architektura, mapy kodu i stan projektu.

### Recommended next task

- Commit wyłącznie tego zakresu przez uprawnioną sesję, odbiór użytkownika i osobna zgoda na integrację/wdrożenie; problem środowiska React osobno.
