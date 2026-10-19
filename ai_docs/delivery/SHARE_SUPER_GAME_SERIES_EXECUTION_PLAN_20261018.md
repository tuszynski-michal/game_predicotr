---
title: Widok serii supergry dla odbiorcy linku udostępniania — plan wykonania
status: accepted
last_updated: 2026-10-19
---

# Widok serii supergry dla odbiorcy linku udostępniania

Autor: Claude Code (`claude-fable-5-1`), 2026-10-18. Status `accepted`
(operator, 2026-10-19): operator zlecił cały plan w kolejności krok 0,
TASK-1056, 1058, 1060, 1057, 1059, z audytami Codex dla TASK-1056, 1057 i
1059, i zgodził się na jego koszt. Akceptacja planu nie jest zgodą na scalenie
do `main`, push ani restart usług.

## 1. Stan obecny

- Odbiorca linku Reviewera (link jednej gry
  `apps/reviewer/src/features/board-search-share/board-search-share-gate.tsx`
  i panel wielu gier
  `apps/reviewer/src/features/board-search-panel/board-search-panel-gate.tsx`)
  widzi znaczniki supergry na kartach wyników i w wierszach „Przybliżonej
  wygranej” (`packages/board-search-ui/src/board-search-super-game-marker.tsx`),
  ale nie może otworzyć serii.
- Publiczny marker celowo nie ma `seriesId`
  (`services/api/src/game_predictor_api/schemas/super_game_markers.py`,
  `SuperGamePublicMarkerResponse`, `PUBLIC_APPROXIMATE_WIN_EXCLUDE`); trasy
  serii istnieją tylko pod `/api/v1/admin/games/{game_id}/super-game-series`
  (`api/super_game_series.py`), aktor zapisu to stała `local-admin`.
- Widok serii (karuzela, super symbol, retriggery, okno linii, „Następna bez
  symbolu”) żyje w Adminie:
  `apps/admin/src/features/super-games/super-game-series-workspace.tsx`
  (`SeriesView`, `SeriesBoardView`), stan w `super-game-series-state.ts`,
  skróty w `super-game-series-keyboard.ts`. Reviewer nie może importować z
  `apps/admin`.
- Proxy Reviewera (`apps/reviewer/src/security/board-search-share-proxy.ts`,
  `boardSearchShareRoute`) ma zamkniętą allowlistę: odczyty, `unlock` i jedna
  mutacja POST (korekta komórki). Test
  `apps/reviewer/test/board-search-share-security-gate.test.mjs` wymaga
  równości allowlisty z trasami `/api/v1/board-search-shares/` w OpenAPI.
- Korekty odbiorcy mają aktora `board-search-share:<sessionId>`
  (`storage/board_search_share_correction_repository.py`).

## 2. Cel i zakres

Kliknięcie dowolnego znacznika supergry (trigger albo spin) w udostępnionej
wyszukiwarce (link jednej gry i panel wielu gier) otwiera modal z tym samym
widokiem serii co w Adminie: karuzela pozycji, wybór i zapis super symbolu z
potwierdzeniem retriggerów i CAS `expectedRevision`, okno „Linie / Popraw
symbole”, „Następna bez symbolu (N)”. Widok serii jest wyniesiony do wspólnego
pakietu `@game-predictor/board-search-ui`, nie kopiowany.

Poza zakresem: lista serii z filtrami i zakresem plansz, „Przelicz serie”
(derive), wpis w dzienniku linku, zmiany panelu zarządzania, migracje.

## 3. Decyzje operatora (czat, 2026-10-18)

1. Odbiorca linku ustawia super symbol: rozszerzenie D-535 („super symbol
   definiuje operator ręcznie”) i D-548. Nowa decyzja D-564 (TASK-1060).
2. Modal = widok jednej serii, bez listy serii.
3. Bez „Przelicz serie”; modal pokazuje `SuperGameStateBanner`.
4. Modal otwiera każdy znacznik (trigger i spin) na karcie wyniku i w wierszu
   zakresu.
5. Zapis odbiorcy nie trafia do dziennika linku; wystarczy audyt serii
   (`defined_by`, `super_game_series_audit_events`).
6. Audyt krzyżowy Codex dla TASK-1056, 1057 i 1059.

## 4. Decyzje projektowe

- **A. `seriesId` w markerach publicznych udostępnienia** zamiast trasy
  `by-sequence`: wyniki `search` i wiersze `approximate-win` udostępnienia
  używają `SuperGameMarkerResponse` (z `seriesId`); trasa publiczna
  `approximate-win` przestaje używać `PUBLIC_APPROXIMATE_WIN_EXCLUDE`. Panel
  zarządzania (`api/management_public_stakes.py`) bez zmian. `seriesId` nie
  jest ścieżką, sekretem ani identyfikatorem przeglądu/importu; jest
  uchwytem zasobu publicznego koniecznym dla `PUT …/super-symbol`.
- **B. Cztery trasy publiczne** pod
  `/api/v1/board-search-shares/super-game-series/`: `state`,
  `next-undefined?afterTrigger=`, `{seriesId}/boards`,
  `PUT {seriesId}/super-symbol`. Bez listy z filtrami, bez `derive`, bez
  osobnego `GET {seriesId}` (`boards` zwraca `series`).
- **C. Aktor zapisu** `board-search-share:<sessionId>`; wspólny helper
  `board_search_share_actor(session_id)` w `domain/board_search_shares.py`.
- **D. Odczyty serii nie tworzą wpisów dziennika zapytań.**
- **E. Wspólny widok w `packages/board-search-ui/src/super-game-series/`.**
- **F. Granica podziału Admina:** workspace Admina zachowuje listę, filtry,
  zakres plansz, derive, odpytywanie `state`, nawigację `?series=`; wspólny
  `SuperGameSeriesPanel` przejmuje cykl otwartej serii. Host przekazuje
  `refreshToken`, symbole i wersję reguł.
- **G. Znacznik jako przycisk:** `SuperGameMarkerBadge` z `onOpenSeries` →
  `<button>`; z `seriesHref` → `<a>` (Admin); bez obu → sam label.
- **H. Esc w modalu** należy do panelu serii; modal blokuje `cancel`
  dialogu, zamyka go przycisk „Zamknij”. Przy otwartym oknie linii skróty
  panelu są wyłączone.

## 5. Taski

Szczegóły w plikach `ai_docs/tasks/1056-…` do `1060-…`.

| Task | Zakres | Zależności |
|---|---|---|
| TASK-1056 | Publiczne trasy serii (API, OpenAPI, klient, `seriesId` i `superGameTriggerCount` w odpowiedziach publicznych, aktor sesji) | — |
| TASK-1058 | Wyniesienie widoku serii do `board-search-ui` (`SuperGameSeriesPanel`, stan, skróty, CSS); Admin konsumuje panel bez zmiany zachowania | — |
| TASK-1060 | D-564, `ADMIN_APP.md`, `API_CONTRACT.md`, `REMOTE_REVIEWER_THREAT_MODEL.md`, `DATA_MODEL.md` | treść decyzji z sekcji 3–4 |
| TASK-1057 | Allowlista proxy Reviewera i proxy panelu (4 trasy, `PUT`), testy bramki | TASK-1056 (OpenAPI) |
| TASK-1059 | Modal serii w udostępnionej wyszukiwarce (znacznik-przycisk, modal, adapter źródła danych, bramki) | TASK-1056, 1057, 1058 |

Kolejność wykonania (polecenie operatora): krok 0, TASK-1056, 1058, 1060,
1057, 1059. Każdy task ma własny commit `vX.Y.N` (skill `task-close`).

## 6. Mapa wymaganie → task → test

| Wymaganie | Task | Test |
|---|---|---|
| Klik dowolnego znacznika otwiera widok serii | 1059 | `board-search-super-game.test.mjs` (przycisk), test modala |
| Karuzela, retriggery, skróty identyczne z Adminem | 1058 | regresja `apps/admin/test-interactions/super-game-series-workspace.test.mjs`, test panelu pakietu |
| Zapis super symbolu z CAS, aktor sesji | 1056 | `test_board_search_share_public_api.py`: 200/409/422/404, `defined_by` |
| Okno linii z poprawkami | 1058, 1059 | regresja Admina, `onBoardEdited` w teście modala |
| „Następna bez symbolu (N)” | 1056, 1058 | API `next-undefined`, zawinięcie w teście panelu |
| Brak listy, zakresu, derive; baner nieaktualności | 1057, 1059 | bramka 403 dla listy/derive, baner w teście modala |
| Odświeżenie po zamknięciu z edycją | 1059 | test modala `onClose(true)` |
| Skróty nie przeciekają do edytora ani okna linii | 1059 | test modala `keydown '1'`, `linesOpen` |
| Allowlista = OpenAPI, `PUT` przez proxy i panel | 1057 | `security-gate`, `proxy`, `panel-proxy` |
| D-564 i dokumenty | 1060 | `npm run docs:check` |

## 7. Odbiór całego przepływu

Operator uruchamia usługi (agent nie restartuje). Link jednej gry i panel
wielu gier dla Mumii: klik znacznika → modal → zapis super symbolu → marker po
ponownym wyszukaniu; w Adminie `definedBy` = sesja linku, seria na liście
„Z super symbolem”; poprawka symbolu z okna linii w modalu → odświeżenie
wyników i baner nieaktualności. Na końcu `npm run quality`. Scalenie do `main`
dopiero po akceptacji wyniku (jedno pytanie na cały plan).

## 8. Ryzyka

- Koszt: 5 tasków, refaktoryzacja ~900 linii, 3 audyty (zgoda operatora
  2026-10-19).
- Test kontraktu Admina `super-game-series-workspace-contract.test.mjs`
  (regexy na tekście pliku) wymaga zmiany źródła asercji; jedyna zmiana
  istniejącego testu Admina.
- `check_decision_links.py` może wymagać aktualizacji nagłówka archiwum
  indeksu decyzji; weryfikacja `docs:check`.
- `exactly({}, {...})` dla `next-undefined` bez parametru w proxy panelu:
  potwierdzić testem `panel-proxy`.
- Zapis odbiorcy widoczny w Adminie tylko przez `definedBy` i audyt serii.
- Rozjazdy dokumentów (`ADMIN_APP.md` „czeka na audyt” dla TASK-0991,
  docstring `domain/board_search_shares.py` „no write capability”) nie są w
  zakresie; TASK-1060 poprawia je tylko tam, gdzie dotyka tych akapitów.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1056 — publiczne trasy serii (API, OpenAPI, klient) | claude-fable-5-1 | high (warunkowo: poziom do potwierdzenia w środowisku) | Nowa publiczna powierzchnia zapisu, atrybucja audytu, modele bez identyfikatorów wewnętrznych. | Tak — `/audit-task` (Codex, read-only) przed commitem |
| TASK-1058 — ekstrakcja widoku serii do pakietu | claude-fable-5-1 | high (warunkowo) | Refaktoryzacja ~900 linii z twardym wymogiem regresji testów interakcji Admina. | Nie, jeśli testy Admina przechodzą bez zmian; inaczej review claude-fable-5-1 high |
| TASK-1060 — D-564 i dokumentacja | claude-fable-5-1 | medium (warunkowo) | Praca dokumentacyjna według ustalonej treści; spójność sprawdza `docs:check`. | Nie |
| TASK-1057 — allowlista proxy i proxy panelu | claude-fable-5-1 | high (warunkowo) | Kod bezpieczeństwa z testem równości allowlisty i OpenAPI; mały zakres, wysoki koszt błędu. | Tak — `/audit-task` (Codex, read-only) |
| TASK-1059 — modal serii w Reviewerze | claude-fable-5-1 | high (warunkowo) | Integracja adaptera, workspace i bramek; blokada skrótów; odświeżanie po edycji. | Tak — `/audit-task` (Codex, read-only) |
