---
title: Przybliżona wygrana — podgląd linii, wykres, złotówki i udostępnianie online
status: accepted
last_updated: 2026-09-30
---

# Plan: rozszerzenie „Przybliżonej wygranej” i udostępnianie wyszukiwarki online

Plan zaakceptowany przez operatora 2026-09-30 wraz z poleceniem wykonania
etapu A. Operator potwierdził liniowość wypłat względem stawki (R1) i
wymaganie, by linia wypłaty liczyła się wyłącznie od lewej krawędzi (R2).

## 1. Stan obecny (fakty z kodu)

| Obszar | Sprawdzona ścieżka + symbol | Stan |
|---|---|---|
| Ekran wyszukiwania | `apps/admin/src/features/board-search/board-search-workspace.tsx` · `BoardSearchWorkspace` | Komponent przyjmuje wstrzykiwany `client` (`BoardSearchClient`), więc źródło danych da się podmienić bez zmiany logiki. |
| Karuzela wyników | `.../board-search-results.tsx` · `BoardSearchResults`, `BoardCrop` | Dla `operational_review` pobierane jest **całe zdjęcie źródłowe**, a kadrowanie robi CSS w przeglądarce (`computeBoardCropTransform`, margines 20%). |
| Przybliżona wygrana | `.../board-search-approximate-win.tsx` · `ApproximateWinResultView`, `ApproximateWinBalanceChart` | Tabela ma 4 kolumny. Wykres SVG 800 × 240 ma tylko osie i linię zera, bez siatki. Tooltip istnieje tylko przy najechaniu i leży na punkcie. |
| Logika stanu | `.../board-search-approximate-win-state.ts` · `approximateWinChartPoints`, `formatApproximateWinCredits` | Czyste funkcje, testy w `apps/admin/test/board-search-approximate-win-state.test.mjs`. |
| Kalkulator | `services/api/src/game_predictor_api/domain/board_search_approximate_win.py` · `calculate_approximate_win` | Callback `evaluate` zwraca tylko sumę wypłaty. Informacja o liniach jest odrzucana. |
| Ewaluator wypłat | `services/worker/src/game_predictor_worker/domain/payout.py` · `PreparedPayoutEvaluator.evaluate` | Zwraca `PayoutEvaluation.matches` z `payline_id`, `matched_cells`, `joker_cells`, `matched_length`, `payout_credits`. Dane o liniach już istnieją, nie trzeba nowego algorytmu. |
| Endpoint | `services/api/src/game_predictor_api/api/board_search.py` · `getBoardSearchApproximateWin` | Tylko odczyt, limit 100 000 spinów, bez cache. |
| Siatka pól na zdjęciu | `apps/admin/src/features/symbol-reviews/symbol-review-source-context.ts` · `symbolReviewSourceCells` | Czyta 15 wielokątów pól z `geometry` pozycji review. |
| Wzorzec modala | `apps/admin/src/features/symbol-reviews/symbol-review-source-modal.tsx` | `<dialog>` + `showModal()`, SVG ze zdjęciem i wielokątami. |
| Sesje zdalne (wzorzec) | `services/api/.../application/remote_manual_selection_access.py`, `application/access_credentials.py` | Kod `XXXX-XXXX` (8 znaków + myślnik), PBKDF2, 5 prób, token w cookie `HttpOnly`, TTL 5 min–24 h. |
| Wybór czasu (wzorzec) | `apps/admin/src/features/manual-image-selection/remote-manual-selection-host-panel.tsx` | Select 1 h / 4 h / 8 h / 24 h, domyślnie 8 h; kod trzymany lokalnie w `localStorage` Admina. |
| Tunel | `services/api/.../application/reviewer_ingress.py` · `ensure_online_reviewer_ingress` | Cloudflare Quick Tunnel kieruje wyłącznie na Reviewer `127.0.0.1:3001`. |
| Proxy publiczne | `apps/reviewer/src/security/remote-selection-proxy.ts`, `reviewer-proxy-policy.ts` | Zamknięta allowlista, osobne cookie i CSP per powierzchnia. |
| Przetwarzanie obrazów w API | `services/api/.../application/virtual_cell_previews.py` · `VirtualCellPreviewService` | Pillow jest zależnością API; istnieje wzorzec cache plikowego z przycinaniem. |

Otwarty element poprzedniej serii: `ai_docs/tasks/0654-approximate-win-docs-and-acceptance.md`
ma status `in_progress` (odbiór na żywych danych czeka na zgodę). Ten plan go
nie zamyka i nie zależy od niego.

## 2. Cel i zakres

1. Podgląd planszy z narysowanymi wygrywającymi liniami, w modalu, z legendą
   wyłączającą każdą linię osobno; wejście z nowej kolumny akcji w tabeli.
2. Siatka na wykresie bilansu.
3. Przypinanie punktów wykresu kliknięciem; etykiety u góry wykresu,
   połączone z punktem kropkowaną pionową linią.
4. Przeliczanie na złotówki i wybór stawki.
5. Link online do kopii sekcji „Wyszukaj plansze” z „Przybliżoną wygraną”,
   z kodem 8-znakowym i czasem dostępu, z przyciętymi zdjęciami i cache.

## 3. Kluczowe reguły i decyzje

### R1. Złotówki i stawka (punkt 4) — proponowana decyzja D-470

- `1 zł = 10 kredytów`. Stawka bazowa = `rules.spinCost / 10` zł (dziś
  100 kredytów = 10 zł).
- Dozwolone stawki: 1,20 zł, 2 zł, 4 zł, 6 zł, 10 zł, 20 zł.
- Mnożnik = `stawka / stawka bazowa`. Mnożnik skaluje **wypłaty i koszt
  spinu**, więc także bilans. Liniowość wypłat względem stawki potwierdził
  operator 2026-09-30 na przykładzie: 4 winogrona dają 1 000 kredytów
  (100 zł) przy stawce 100 kredytów (10 zł), a przy stawce 6 zł dają
  600 kredytów (60 zł). Ten przykład wchodzi do testów T3.
- Przeliczenie jest wyłącznie prezentacją po stronie klienta. API i kalkulator
  pozostają w kredytach przy stawce bazowej.
- Arytmetyka na liczbach całkowitych w groszach: licznik
  `kredyty × stawka_gr` jest liczbą całkowitą, a zaokrąglenie wykonuje się
  z ilorazu i reszty z dzielenia przez `spinCost`, bez `float`:

```text
grosze = kredyty_bazowe * stawka_gr / stawka_bazowa_gr * 10
       = kredyty_bazowe * stawka_gr * 10 / (spinCost * 10)
       = kredyty_bazowe * stawka_gr / spinCost
```

| Wejście (kredyty bazowe) | Stawka | Wynik w zł | Wynik w kredytach |
|---|---|---|---|
| 10 000 | 10 zł | 1 000,00 zł | 10 000 |
| 10 000 | 6 zł | 600,00 zł | 6 000 |
| 1 000 (4 winogrona) | 6 zł | 60,00 zł | 600 |
| 10 000 | 20 zł | 2 000,00 zł | 20 000 |
| 5 | 1,20 zł | 0,06 zł | 0,6 |
| 100 (koszt spinu) | 1,20 zł | 1,20 zł | 12 |

- Dzielenie `kredyty * stawka_gr / spinCost` może dać ułamek grosza.
  Zaokrąglenie: do pełnego grosza, połówki od zera (symetrycznie dla
  wartości ujemnych), wykonywane **raz na wartości końcowej** (nie
  sumujemy zaokrąglonych wierszy). Bilans
  narastający liczy się z kredytów bazowych i dopiero potem przelicza.
- Domyślnie: stawka bazowa, jednostka „kredyty”. Bez zmiany ustawień ekran
  wygląda jak dziś.
- Suwak „Pokaż wypłaty od” działa w wybranej jednostce i stawce.

### R2. Dane o liniach (punkt 1)

- Źródłem prawdy o liniach jest `PayoutEvaluation.matches` z tego samego
  ewaluatora i tej samej opublikowanej wersji reguł co suma w tabeli.
- Szczegóły planszy pobiera się leniwie, osobnym żądaniem dla jednej planszy.
  Odpowiedź zakresu (`rows[]`) nie rośnie.
- Wypłata liczy się wyłącznie od lewej krawędzi: każda linia jest
  sprawdzana od kolumny 1 i przerywana na pierwszej nieznanej komórce
  (`_compatible_prefix_length`, `payout-v3-unknown-prefix-stop`). Plansza
  przycięta z lewej strony (kolumna 1 nieznana) nie daje żadnej linii,
  nawet gdy kolumny 2–5 tworzą ciąg. Przycięcie z prawej po pełnym
  widocznym prefiksie daje `confirmed_minimum`. Szczegóły planszy używają
  tego samego ewaluatora, więc modal nie może pokazać linii, której tabela
  nie naliczyła.
- Suma `matches[].payoutCredits` musi równać się `payoutCredits` wiersza.
  Różnica oznacza, że dane zmieniły się między żądaniami: modal pokazuje
  komunikat i przycisk ponownego przeliczenia, nie rysuje niespójnych linii.

### R3. Obraz planszy

- Serwer renderuje przycięty widok planszy (margines 20%, dłuższy bok
  maks. 1280 px, WebP jakość 80) i zwraca 15 wielokątów pól w układzie
  znormalizowanym 0–1 względem tego widoku.
- Identyfikacja planszy: `gameId + sequenceNumber + boardChecksumSha256`.
  Bez `reviewItemId` i `importJobId` w kontrakcie widoku — ten sam kontrakt
  obsłuży Admina i aplikację online.
- Brak geometrii albo obrazu nie blokuje modala: pokazuje się schemat 3 × 5
  z ikon symboli z tymi samymi liniami i jawną informacją o braku zdjęcia.

### R4. Udostępnianie online (punkt 5) — proponowana decyzja D-471

- Nowy cel sesji `board-search-share`, osobna tabela, osobne cookie, osobny
  prefiks proxy. Nie rozszerza uprawnień istniejących sesji Reviewera ani
  zdalnej selekcji.
- Sesja jest przypięta do jednej gry. Powierzchnia jest **tylko do odczytu**.
- Link nie zawiera kodu. Kod ma 8 znaków (format `XXXX-XXXX`, istniejący
  generator), przekazywany osobnym kanałem.
- Czas dostępu: 1 h / 4 h / 8 h / 24 h, domyślnie 8 h.
- Jedno odblokowanie naraz: nowe odblokowanie rotuje token. Dla drugiej osoby
  tworzy się drugi link.
- API, baza i Admin pozostają na loopbacku. Publiczny jest wyłącznie Reviewer
  za Quick Tunnelem.

## 4. Kontrakty

### 4.1 Szczegóły planszy (nowy endpoint, proponowany)

```text
GET /api/v1/admin/games/{gameId}/board-search/boards/{sequenceNumber}
operationId: getBoardSearchBoardDetail
```

Odpowiedź (proponowana):

```text
gameId, sequenceNumber
boardStatus              # pending | accepted | corrected
boardChecksumSha256
dataSource               # operational_review | legacy_archive
rules: { rulesVersionId, rulesVersion, spinCost, algorithmVersion }
symbolCodes[15]          # kod symbolu albo null dla „?”
payoutCredits            # suma, przy stawce bazowej
payoutKind               # exact | confirmed_minimum | none
matches[]:
  paylineId, paylineCode, paylineName, paylineDisplayOrder
  rowPath[5]
  symbolCode
  matchedLength
  matchedCells[]         # indeksy 0..14
  jokerCells[]
  payoutCredits
view:                    # null, gdy brak obrazu
  width, height
  cellPolygons[15]       # 4 punkty {x,y} w 0..1; null, gdy brak geometrii
```

Błędy: `404 GAME_NOT_FOUND`, `404 BOARD_SEARCH_BOARD_NOT_FOUND` (brak
dokumentu dla pozycji), `409 BOARD_SEARCH_BOARD_REVISION_CONFLICT`
(geometria planszy o innej checksumie niż dokument), `409` jak w kalkulatorze zakresu
(`APPROXIMATE_WIN_RULES_NOT_PUBLISHED`, `APPROXIMATE_WIN_RULES_INVALID`,
`APPROXIMATE_WIN_BOARD_SYMBOL_OUTSIDE_RULES`, projekcja/archiwum niegotowe).

### 4.2 Widok planszy (nowy endpoint, proponowany)

```text
GET /api/v1/admin/games/{gameId}/board-search/boards/{sequenceNumber}/view
  ?expectedBoardChecksumSha256={sha256}
operationId: getBoardSearchBoardView
Content-Type: image/webp
Cache-Control: private, immutable, max-age=31536000
```

Niezgodna checksuma: `409 BOARD_SEARCH_BOARD_REVISION_CONFLICT`. Brak pliku
źródłowego: `404 BOARD_SEARCH_BOARD_VIEW_UNAVAILABLE`. Ścieżka pliku
rozwiązywana fail-closed jak w `resolve_board_search_archive_asset`.

Cache plikowy: `artifact_root/cache/board-search-views/` (proponowane), klucz
= SHA-256 z wersji renderera, checksumy źródła, checksumy geometrii i
parametrów. Zapis atomowy. Przycinanie do limitu rozmiaru według wzorca
`VirtualCellPreviewService._prune`; dotyczy wyłącznie plików pochodnych.

### 4.3 Powierzchnia publiczna (proponowana)

Administracja (loopback, Admin):

```text
POST /api/v1/admin/board-search-shares/sessions        # gameId, label, lifetimeMinutes
GET  /api/v1/admin/board-search-shares/sessions
POST /api/v1/admin/board-search-shares/sessions/{id}/revoke
```

Publiczne (tylko przez proxy Reviewera, nagłówek intencji + cookie):

```text
POST /api/v1/board-search-shares/sessions/{id}/unlock
GET  /api/v1/board-search-shares/context               # nazwa gry, expiresAt, stawki
GET  /api/v1/board-search-shares/symbols
GET  /api/v1/board-search-shares/symbols/{symbolId}/image
GET  /api/v1/board-search-shares/search
GET  /api/v1/board-search-shares/approximate-win
GET  /api/v1/board-search-shares/boards/{sequenceNumber}
GET  /api/v1/board-search-shares/boards/{sequenceNumber}/view
```

`gameId` nigdy nie pochodzi z żądania publicznego — zawsze z sesji.
Odpowiedzi publiczne nie zawierają `reviewItemId`, `recognizedBoardId`,
`importJobId`, ścieżek ani identyfikatorów jobów.

Limity na sesję (proponowane): 120 żądań JSON/min, 600 obrazów/min,
10 kalkulacji zakresu/min i jedna kalkulacja naraz; przekroczenie daje
`429 BOARD_SEARCH_SHARE_RATE_LIMITED`. Maks. 5 aktywnych sesji.

### 4.4 Model danych (proponowany, migracja Alembic)

`board_search_share_sessions`: `id`, `game_id` (FK `games`, `RESTRICT`),
`label`, `code_salt`, `code_hash`, `failed_attempts` (0–5), `locked_at`,
`revoked_at`, `token_hash` (unikalny indeks), `token_expires_at`,
`last_unlocked_at`, `created_at`, `expires_at` (`> created_at`).

`board_search_share_audit_events`: `id`, `session_id` (FK), `event_type`
(`created|unlock_failed|unlocked|locked|revoked`), `created_at`.

Migracja jest wyłącznie addytywna. Numer rewizji ustalić przy wykonaniu
(ostatnia na gałęzi: `0128_partial_board_reconciliation_receipts.py`; inne
worktree mogą dodać kolejne).

### 4.5 Cache po stronie odbiorcy

| Dane | Mechanizm | Czas życia |
|---|---|---|
| Widoki plansz, ikony symboli | Cache HTTP przeglądarki; URL zawiera checksumę, `immutable` | do 24 h (proxy ogranicza `max-age` do 86 400 s) |
| Kontekst i symbole | Jedno pobranie po odblokowaniu, stan w pamięci | sesja karty |
| Wyniki wyszukiwania | Mapa w pamięci, klucz = wzór + zakres + limit | 5 min, maks. 50 wpisów |
| Przybliżona wygrana | Tylko ostatni wynik otwartej sekcji dla bieżącego wyboru, jak w Adminie (D-446) | do zwinięcia sekcji albo zmiany wyboru; ponowne rozwinięcie liczy od nowa (D-462) |
| Szczegóły planszy | Mapa w pamięci, klucz = numer planszy + `dataFingerprintSha256` wyniku zakresu | do zmiany wyniku zakresu |
| Sąsiednie plansze | Istniejący prefetch `new Image()` | — |

Stawka i jednostka to przeliczenie lokalne: zmiana nie wysyła żądania.

## 5. Zadania

Praca w dedykowanym worktree `worktrees/board-search-share`, gałąź
`feat/board-search-share` z `v1.1-vision-lab-hybrid-geometry` (`v1.7.81`,
`f3340b3b`). Numery `TASK-0760…0770` oraz decyzje D-470 i D-471 zostawiają
zapas względem równoległego toru biblioteki symboli, który w chwili zapisu
używa TASK-0740–0750 i D-466. Pierwszy commit toru: `v1.7.82`.

Wspólne polecenia weryfikacji (katalog główny repo, timeout 120 s każde):

```powershell
.\.venv\Scripts\python.exe -m pytest <plik testu>
npm run python:lint
npm run python:typecheck
npm run openapi:generate
npm run openapi:check
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
```

### Etap A — Admin lokalny (punkty 1–4)

#### T1 / TASK-0760 — Decyzje, wymagania i zapis planu

- **Goal:** plan, D-470, D-471 i zaktualizowane wymagania są zapisane w `ai_docs/`.
- **Scope:** zapis planu; pliki zadań 0761–0770; `DECISION_LOG.md` (D-470,
  D-471); `requirements/ADMIN_APP.md` (sekcja „Przybliżona wygrana”: modal,
  siatka, przypinanie, stawki; nowa sekcja udostępniania); `CURRENT_STATE.md`.
- **Out of scope:** kod.
- **Acceptance:** dokumenty opisują R1–R4 bez sprzeczności z D-446 i D-462;
  numery decyzji i zadań potwierdzone z repo.
- **Verification:** przegląd dokumentów; `git diff --cached --check`.

#### T2 / TASK-0761 — Siatka wykresu i przypinane punkty (punkty 2 i 3)

- **Goal:** wykres ma siatkę z opisanymi podziałkami, a kliknięcie przypina
  punkt z etykietą u góry wykresu.
- **Expected files:** istniejące
  `apps/admin/src/features/board-search/board-search-approximate-win.tsx`
  (`ApproximateWinBalanceChart`), `...-approximate-win-state.ts`,
  `apps/admin/src/app/globals.css` (`.boardSearchApproximateWinChart*`),
  `apps/admin/test/board-search-approximate-win-state.test.mjs`.
- **Technical notes:**
  - Nowe czyste funkcje (proponowane): `approximateWinAxisTicks(min, max,
    targetCount)` zwraca „okrągłe” podziałki (kroki 1/2/5 × 10ⁿ);
    `toggleApproximateWinPinnedPoint(pins, point)`;
    `layoutApproximateWinPinLabels(pins, width)` przydziela etykietom
    wiersze, żeby się nie nakładały.
  - Siatka: 4–6 linii poziomych i 5–8 pionowych, cienkie, o niskim
    kontraście; każda z opisem wartości na osi. Linia zera pozostaje
    wyróżniona.
  - Oś Y: dziedzina rozszerzona do skrajnych „okrągłych” podziałek
    obejmujących minimum i maksimum bilansu; opisy podziałek zastępują
    dotychczasowe etykiety minimum i maksimum (minimum, maksimum i bilans
    końcowy pozostają w opisie `<desc>`). Oś X analogicznie od 0 do
    podziałki ≥ liczby spinów zakresu.
  - Zwiększyć `padding.top`, aby zmieścić pas etykiet nad obszarem danych
    (do 3 wierszy).
  - Etykieta najechania i etykiety przypięte leżą w pasie u góry. Od etykiety
    do punktu biegnie pionowa linia `stroke-dasharray`, punkt ma znacznik.
  - Kliknięcie przypina najbliższy punkt (ta sama reguła co najechanie,
    bez punktów `before_payout`). Kliknięcie przypiętego punktu albo „×” na
    etykiecie odpina. Przycisk „Wyczyść punkty”. Limit 8 punktów; dziewiąte
    kliknięcie pokazuje komunikat, nie usuwa po cichu starszego.
  - Przypięcia kasują się przy zmianie wyniku (inny klucz żądania).
  - Dostępność: etykiety przypięte są przyciskami z `aria-label`; lista
    przypiętych punktów dostępna także jako tekst pod wykresem.
  - Układ etykiet: etykieta trafia do pierwszego z 3 wierszy pasa, w którym
    nie nachodzi na inne; gdy żaden wiersz nie jest wolny przy docelowym
    `x`, etykieta jest przesuwana poziomo do najbliższego wolnego miejsca w
    wierszu o najmniejszym przesunięciu, a linia prowadząca łamie się
    (odcinek skośny od etykiety do górnej krawędzi obszaru danych, dalej
    kropkowany pion do punktu). Szerokość etykiety ≤ 1/6 szerokości
    wykresu (etykieta dwuwierszowa). Wiersz blokuje nową etykietę tylko
    wtedy, gdy każda wolna przerwa jest węższa niż etykieta, a to wymaga co
    najmniej 3 etykiet, więc 3 wiersze blokują dopiero przy 9 już
    umieszczonych — dziewiąta etykieta (8 przypiętych + najechanie) zawsze
    się mieści bez nakładania.
  - Klawiatura: wykres jest fokusowalny; strzałki przesuwają podświetlony
    punkt, Enter albo spacja przypina lub odpina, Escape czyści
    podświetlenie.
- **Test cases:** podziałki dla zakresów `[-2500, 0]`, `[-120, 9800]`,
  `[0, 0]`; przypięcie, odpięcie, limit 8; układ etykiet dla dwóch punktów
  o tym samym `x`, dla punktu przy prawej krawędzi i dla 9 etykiet o tym
  samym `x`; nawigacja klawiaturą pomija `before_payout`.
- **Acceptance:** istniejące testy stanu przechodzą bez zmian asercji; wykres
  bez wypłat zachowuje obecny komunikat.

#### T3 / TASK-0762 — Złotówki i stawka (punkt 4)

- **Goal:** operator wybiera stawkę i jednostkę, a wszystkie kwoty sekcji
  przeliczają się zgodnie z R1.
- **Dependencies:** T2 (etykiety wykresu używają formatowania kwot).
- **Expected files:** istniejące pliki jak w T2; nowy (proponowany)
  `apps/admin/src/features/board-search/board-search-stake.ts` z
  `APPROXIMATE_WIN_STAKES_GROSZE = [120, 200, 400, 600, 1000, 2000]`,
  `scaleApproximateWinAmount`, `formatApproximateWinAmount`; nowy test
  `apps/admin/test/board-search-stake.test.mjs`.
- **Technical notes:**
  - Kontrolki „Stawka” i „Jednostka” w nagłówku wyniku, poza `<summary>`
    (kliknięcie nie może zwijać sekcji). Wybór zapisany w
    `localStorage` (preferencja widoku, nie dane domenowe); błąd magazynu
    jest ignorowany.
  - Przeliczane: trzy kafelki podsumowania, koszt spinu w nagłówku, kolumny
    „Wypłata” i „Bilans narastająco”, suwak progu, opisy osi, etykiety
    punktów, opis `<desc>` wykresu. Legenda modala (T5) użyje tych samych
    funkcji.
  - Suwak progu przechowuje wartość w kredytach bazowych (krok 1 kredyt
    bazowy), a wyświetla ją przeliczoną; zmiana stawki lub jednostki nie
    resetuje progu.
  - Jeżeli stawka bazowa nie należy do listy dozwolonych, pojawia się jako
    dodatkowa opcja „bazowa” (D-470).
  - `spinCost = 0` wyłącza wybór stawki z komunikatem (brak podstawy
    przeliczenia); jednostka „złote” pozostaje dostępna w kursie
    `kredyty / 10`.
  - Nagłówek pokazuje mnożnik, np. „Stawka 6 zł · mnożnik 0,6”.
- **Test cases:** tabela z R1; zaokrąglenie połówki grosza; wartości ujemne
  bilansu; `BigInt` nie jest potrzebny (maks. 100 000 spinów × wypłata mieści
  się w bezpiecznym zakresie liczb całkowitych — potwierdzić asercją).
- **Acceptance:** przy stawce bazowej i jednostce „kredyty” wynik jest
  identyczny z obecnym.

#### T4 / TASK-0763 — API: szczegóły planszy i widok planszy

- **Goal:** endpointy 4.1 i 4.2 działają dla obu źródeł danych i są w
  kliencie TypeScript.
- **Expected files:** istniejące `api/board_search.py`,
  `application/board_search_approximate_win.py`,
  `storage/board_search_projection_repository.py`,
  `storage/board_search_approximate_win_repository.py`,
  `schemas/board_search_approximate_win.py`, `main.py`,
  `packages/admin-api-client` (generowane + wrapper),
  `ai_docs/architecture/API_CONTRACT.md`; nowe (proponowane)
  `domain/board_search_board_detail.py`,
  `application/board_search_board_view.py`,
  `services/api/tests/test_board_search_board_detail_api.py`,
  `services/api/tests/test_board_search_board_view.py`.
- **Technical notes:**
  - Wydzielić z `BoardSearchApproximateWinService.calculate` budowę
    ewaluatora do wspólnej metody; zakres i szczegóły muszą używać tej samej
    ścieżki. Zachowanie `calculate` bez zmian.
  - Mapowanie `payline_id` → kod, nazwa, kolejność i `mobile_code` → kod
    symbolu z tej samej opublikowanej wersji reguł.
  - `view.cellPolygons` dla `operational_review`: z geometrii, której
    checksuma równa się `boardChecksumSha256` dokumentu wyszukiwania,
    przeliczone do układu przyciętego widoku. Gdy bieżąca geometria planszy
    ma inną checksumę (projekcja nie nadążyła albo korekta siatki zmieniła
    geometrię), szczegóły i widok zwracają `409
    BOARD_SEARCH_BOARD_REVISION_CONFLICT` zamiast łączyć obraz z innymi
    wielokątami. Dla `legacy_archive` archiwum już przechowuje obraz jednej
    planszy, więc widok go tylko zmniejsza (bez obrysu + 20%); geometria
    pól archiwum to **niewiadoma** — jeżeli jej nie ma, `cellPolygons =
    null`; nie wymyślać równomiernej siatki bez dowodu, że obraz archiwalny
    jest wyprostowany.
  - Renderowanie: otwarcie pliku przez Pillow z limitem pikseli, korekta
    orientacji EXIF zgodna z tym, jak liczona jest geometria (potwierdzić w
    kodzie workera), przycięcie do obrysu + 20%, ograniczone do granic
    zdjęcia.
  - Równoległe żądania tego samego widoku: jeden render (wzorzec
    `_acquire_flight`).
- **Test cases:** plansza kompletna z dwiema liniami; plansza częściowa z
  `confirmed_minimum` (przycięta z prawej, prefiks 4 symboli widoczny);
  plansza przycięta z lewej (kolumna 1 = `?`, kolumny 2–5 tworzą ciąg
  4 symboli) → `matches = []`, `payoutCredits = 0`, `payoutKind = none`;
  plansza bez wypłaty (`matches = []`); linia z jokerem; brak dokumentu →
  404; symbol spoza reguł → 409; niezgodna checksuma widoku → 409;
  geometria planszy z inną checksumą niż dokument → 409; ścieżka z `..` →
  odmowa; drugi odczyt widoku z cache daje identyczne bajty.
- **Acceptance:** `sum(matches.payoutCredits) == payoutCredits`; `openapi:check`
  przechodzi; istniejące testy `test_board_search_approximate_win_*` bez zmian.

#### T5 / TASK-0764 — Modal planszy z liniami i kolumna akcji (punkt 1)

- **Goal:** z każdego wiersza tabeli otwiera się modal z planszą, liniami i
  legendą.
- **Dependencies:** T3, T4.
- **Expected files:** istniejące `board-search-approximate-win.tsx`,
  `board-search-workspace.tsx` (typ `BoardSearchClient`), `globals.css`;
  nowe (proponowane) `board-search-board-lines-modal.tsx`,
  `board-search-board-lines-state.ts`,
  `apps/admin/test/board-search-board-lines-state.test.mjs`.
- **Technical notes:**
  - Piąta kolumna tabeli bez nagłówka widocznego (nagłówek tylko dla
    czytników ekranu), przycisk „Pokaż planszę” z `aria-label` zawierającym
    numer planszy.
  - Modal według wzorca `SymbolReviewSourceModal` (`<dialog>`, Esc,
    kliknięcie tła, fokus wraca na przycisk).
  - Rysunek: SVG z `<image>` widoku i nakładką. Dla każdego dopasowania
    łamana przez środki `matchedCells` oraz obrys tych pól w kolorze linii.
    Pola z jokerem mają dodatkowy znacznik. Pola nieznane (`?`) mają
    przygaszoną nakładkę ze znakiem `?`, aby było widać, gdzie linia została
    przerwana. `vector-effect: non-scaling-stroke`.
  - Kolor przypisany do linii wypłat stabilnie według `paylineDisplayOrder`
    z palety o wysokim kontraście; przy większej liczbie linii niż kolorów
    dochodzi wzór kreskowania. Kolor nie jest jedynym nośnikiem informacji:
    legenda zawiera nazwę linii.
  - Legenda: jeden wpis na dopasowanie — przełącznik widoczności, kolor,
    nazwa linii, symbol, długość, wypłata w wybranej jednostce i stawce.
    Przyciski „Pokaż wszystkie” i „Ukryj wszystkie”.
  - Nagłówek modala: numer planszy, spin, status, wypłata, rodzaj wypłaty.
  - Spójność (R2): suma linii różna od wypłaty wiersza albo
    `rules.rulesVersionId` różny od wyniku zakresu → komunikat i „Przelicz
    ponownie”. Przycisk zamyka modal i ponownie uruchamia kalkulację zakresu
    dla bieżącego klucza (istniejące `runCalculation`); po nowym wyniku
    operator otwiera modal jeszcze raz.
  - Ładowanie i błędy: stan „Wczytywanie planszy…”; 404/409/błąd sieci →
    komunikat z przyciskiem „Spróbuj ponownie” (ponowne pobranie
    szczegółów); odpowiedź dla wcześniej otwartej planszy jest odrzucana
    (licznik żądań, jak w `BoardSearchApproximateWin`). Błąd wczytania
    obrazu (`<image>`/`onError`) przełącza na schemat 3 × 5.
  - `view = null` albo `cellPolygons = null` → schemat 3 × 5 z ikon symboli.
- **Test cases:** środki pól z wielokątów; stabilność kolorów; przełączanie
  widoczności jednej linii nie zmienia pozostałych; stan po ponownym
  otwarciu modala dla innej planszy zaczyna od wszystkich linii widocznych.
- **Acceptance:** filtr progu wypłat i przewijanie tabeli działają jak
  dotąd; modal nie wysyła żadnej mutacji.

**Odbiór etapu A (cały przepływ):** operator w Adminie wyszukuje planszę,
rozwija „Przybliżoną wygraną”, widzi siatkę wykresu, przypina kilka punktów
myszą i klawiaturą, zmienia stawkę i jednostkę (kwoty w tabeli, kafelkach,
suwaku, osiach i etykietach zgodne z R1), otwiera modal z wiersza tabeli,
wyłącza i włącza linie w legendzie. Plansza całkowicie przycięta z lewej
(cała kolumna 1 nieznana) nie daje wypłaty ani wiersza w tabeli, a
`getBoardSearchBoardDetail` zwraca dla niej `matches = []` (test T4). W
modalu planszy, na której tylko część pól kolumny 1 jest `?`, żadna linia
nie zaczyna się od tych pól, a pola mają nakładkę `?`. Zwinięcie i rozwinięcie sekcji liczy wynik od nowa
(D-462).

**Granica etapu A — STOP.** Odbiór operatora w Adminie.

### Etap B — Udostępnianie online (punkt 5)

#### T6 / TASK-0765 — Wspólny pakiet UI wyszukiwarki

- **Goal:** komponenty i stan wyszukiwarki żyją w pakiecie współdzielonym, a
  Admin działa identycznie.
- **Expected files:** nowy (proponowany) `packages/board-search-ui/`
  (`package.json` z eksportem źródeł `.ts/.tsx` jak
  `manual-image-selection-core`, `src/`, `test/`, `board-search.css`);
  przeniesione pliki z `apps/admin/src/features/board-search/`; istniejące
  `apps/admin/src/app/globals.css` (reguły `.boardSearch*`, wiersze
  ok. 9657–10270, przeniesione do pakietu), `catalog-workspace.tsx` (import).
- **Technical notes:**
  - Pakiet definiuje interfejs `BoardSearchDataSource` (proponowany): metody
    `listSymbols`, `symbolImageUrl`, `search`, `approximateWin`,
    `boardDetail`, `boardViewUrl` i mapowanie błędów. Admin dostarcza adapter
    na `createConfiguredAdminApiClient`.
  - Karuzela w pakiecie używa `boardViewUrl` (widok z T4) zamiast całego
    zdjęcia i kadrowania CSS. To zmiana zachowania Admina: mniejszy transfer,
    ten sam kadr. `computeBoardCropTransform` zostaje tylko, jeżeli ma innych
    konsumentów; sprawdzić przed usunięciem.
  - Pakiet nie importuje niczego z `apps/admin` (m.in. `apiErrorMessage`,
    `keyboard-shortcuts` wchodzą przez adapter albo są przenoszone).
  - Jeżeli Next nie kompiluje TSX z pakietu, dodać `transpilePackages` w obu
    `next.config.ts`.
- **Test cases:** wszystkie testy `apps/admin/test/board-search-*.test.mjs`
  przeniesione i zielone bez zmiany asercji; test kontraktu adaptera Admina.
- **Acceptance:** build i typecheck Admina; brak różnic funkcjonalnych poza
  źródłem obrazu karuzeli.

#### T7 / TASK-0766 — Sesje udostępniania: model, serwis, API administracyjne

- **Goal:** Admin API tworzy, listuje i unieważnia sesje `board-search-share`.
- **Expected files:** nowa migracja Alembic; istniejące `storage/models.py`,
  `main.py`, `api/router.py`; nowe (proponowane)
  `domain/board_search_shares.py`, `application/board_search_share_access.py`,
  `storage/board_search_share_repository.py`, `api/board_search_shares.py`,
  `schemas/board_search_shares.py`,
  `services/api/tests/test_board_search_share_access.py`,
  `services/api/tests/test_board_search_share_access_api.py`; OpenAPI i klient.
- **Technical notes:**
  - Użyć `access_credentials.py` bez zmian (kod, sól, PBKDF2, token).
  - `create` wywołuje `ensure_online_reviewer_ingress`; `revoke` nie zależy
    od tunelu.
  - Kod zwracany tylko w odpowiedzi `create`. Lista nie zawiera sekretów.
  - Walidacja: gra istnieje, projekcja albo archiwum gotowe, opublikowane
    reguły istnieją — inaczej `409` z kodem przyczyny (nie tworzymy linku do
    pustej aplikacji).
  - Limit 5 aktywnych sesji pod blokadą transakcyjną.
  - Flaga `GAME_PREDICTOR_BOARD_SEARCH_SHARE_ENABLED`; wartość
    nieprawidłowa = wyłączone.
- **Test cases:** czas życia poza 5 min–24 h; 5 błędnych kodów → blokada;
  odblokowanie po wygaśnięciu; rotacja tokenu; unieważnienie czyści token;
  szósta aktywna sesja → konflikt; audyt bez sekretów.
- **Acceptance:** migracja w górę na czystej bazie testowej; testy
  integracyjne tylko z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`.

#### T8 / TASK-0767 — Publiczne endpointy odczytu

- **Goal:** endpointy 4.3 zwracają dane wyłącznie gry z sesji.
- **Dependencies:** T4, T7.
- **Expected files:** istniejące `api/board_search_shares.py` (z T7),
  `main.py`; nowe testy `test_board_search_share_public_api.py`.
- **Technical notes:**
  - Router wymaga nagłówka intencji proxy i cookie tokenu, jak
    `_require_remote_selection_proxy`.
  - Middleware `bind_game_storage_request` rozpoznaje grę po ścieżce
    `/admin/games/{id}`; trasy publiczne jej nie mają. Zależność routera musi
    jawnie otworzyć `game_storage_scope(session.game_id)`. Bez tego
    wyszukiwanie czytałoby złe źródło danych.
  - Serwisy wyszukiwania, zakresu i szczegółów są te same co w Adminie; różni
    się tylko autoryzacja i schemat odpowiedzi bez identyfikatorów
    wewnętrznych.
  - Limity żądań według wzorca `remote_manual_selection_control.py`.
  - `Cache-Control` obrazów: `private, immutable, max-age=86400`.
- **Test cases:** brak cookie → 401; token innej sesji nie czyta gry A;
  parametr `gameId` w zapytaniu jest odrzucany; odpowiedź nie zawiera
  zakazanych kluczy (test rekurencyjny); 429 po przekroczeniu limitu;
  sesja unieważniona w trakcie → 401 przy następnym żądaniu.

#### T9 / TASK-0768 — Aplikacja online w Reviewerze

- **Goal:** pod linkiem działa bramka kodu i pełna kopia sekcji.
- **Dependencies:** T6, T8.
- **Expected files:** istniejące `apps/reviewer/next.config.ts`,
  `apps/reviewer/src/security/reviewer-proxy-policy.ts`,
  `apps/reviewer/package.json`; nowe (proponowane)
  `apps/reviewer/src/app/board-search/page.tsx`,
  `apps/reviewer/src/app/board-search-api/[...path]/route.ts`,
  `apps/reviewer/src/security/board-search-share-proxy.ts`,
  `apps/reviewer/src/features/board-search-share/` (bramka, adapter, cache),
  testy `apps/reviewer/test/board-search-share-*.test.mjs`.
- **Technical notes:**
  - Proxy: tylko `GET` i `POST unlock`; dokładna allowlista ścieżek i
    parametrów zapytania; cookie `gp_board_search_token`, `HttpOnly`,
    `Secure`, `SameSite=Strict`, `Path=/board-search-api`.
  - Odpowiedzi JSON przechodzą przez filtr wrażliwych kluczy; obrazy są
    przekazywane strumieniowo z limitem rozmiaru i sprawdzeniem
    `Content-Type`.
  - Osobny CSP bez `127.0.0.1:8000`; matcher pierwszej reguły w
    `next.config.ts` musi wykluczyć nowe ścieżki.
  - Adapter `BoardSearchDataSource` z cache według 4.5.
  - Widok pokazuje czas do wygaśnięcia i czytelny ekran po wygaśnięciu albo
    unieważnieniu.
- **Test cases:** allowlista (każda trasa spoza listy → 403); cookie selekcji
  i Reviewera nie autoryzują nowej powierzchni i odwrotnie; nagłówki CSP;
  trafienie i wygaśnięcie cache; zmiana stawki nie wysyła żądania.

#### T10 / TASK-0769 — Panel udostępniania w Adminie

- **Goal:** przycisk w „Wyszukaj plansze” tworzy link i kod oraz zarządza
  sesjami.
- **Dependencies:** T7.
- **Expected files:** istniejące `board-search-workspace.tsx` (albo jego
  opakowanie w Adminie po T6), `globals.css`; nowe (proponowane)
  `apps/admin/src/features/board-search/board-search-share-panel.tsx`,
  `board-search-share-state.ts`, `board-search-share-code-cache.ts`, testy.
- **Technical notes:**
  - Przycisk „Udostępnij online” w nagłówku sekcji otwiera panel: etykieta,
    czas dostępu (1 h / 4 h / 8 h / 24 h, domyślnie 8 h), „Utwórz link”.
  - Po utworzeniu: link, kod, „Kopiuj link”, „Kopiuj kod”, data wygaśnięcia,
    „Zatrzymaj” z potwierdzeniem w dwóch krokach.
  - Kod przechowywany lokalnie według wzorca
    `remote-manual-selection-access-code-cache.ts`, pod osobnym kluczem.
  - Panel jest elementem Admina, nie pakietu współdzielonego — odbiorca
    online nie widzi przycisku udostępniania.
- **Test cases:** cache kodów (wygaśnięcie, usunięcie po unieważnieniu);
  brak tunelu → czytelny błąd; lista filtruje aktywne i zakończone.

#### T11 / TASK-0770 — Bramka bezpieczeństwa, dokumentacja, odbiór

- **Goal:** powierzchnia jest opisana w modelu zagrożeń i odebrana.
- **Scope:** `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md` (nowa
  powierzchnia, zagrożenia, reakcja na incydent), `API_CONTRACT.md`,
  `ADMIN_APP.md`, `guides/LOCAL_OPERATION_GUIDE.md`, `CURRENT_STATE.md`;
  odbiór na lokalnym buildzie produkcyjnym Reviewera.
- **Out of scope:** uruchomienie publicznego tunelu i test z drugiego
  urządzenia — wymaga osobnej zgody operatora.
- **Acceptance:** lista kontrolna: allowlista zgodna z OpenAPI, izolacja
  celu sesji, cookie i pochodzenie żądań, limity, redakcja odpowiedzi,
  stabilne błędy HTTP; brak otwartych uwag P0–P2.

**Granica etapu B — STOP.**

## 6. Mapa wymaganie → zadanie → test

| Wymaganie | Zadanie | Kryterium |
|---|---|---|
| 1. Modal z liniami, legenda, kolumna akcji | T4, T5 | suma dopasowań = wypłata wiersza; przełączniki per linia |
| 1. Linia tylko od lewej krawędzi (R2) | T4, T5 | plansza przycięta z lewej → brak wiersza i `matches = []` (test T4); częściowo nieznana kolumna 1 → brak linii od tych pól i nakładka `?` w modalu |
| 2. Siatka wykresu | T2 | testy `approximateWinAxisTicks` |
| 3. Przypinane punkty, etykiety u góry | T2 | testy przypinania i układu etykiet |
| 4. Złotówki i stawki | T1, T3 | tabela przykładów z R1 |
| 5. Link online, kod 8 znaków, 8/24 h | T7, T10 | testy sesji i panelu |
| 5. Kopia sekcji ze wszystkimi funkcjami | T6, T9 | te same komponenty z pakietu |
| 5. Przycięte zdjęcia | T4, T6 | widok WebP ≤ 1280 px |
| 5. Szybkość i cache | T4, T8, T9 | cache HTTP, cache w pamięci, cache plikowy |
| 5. Bezpieczeństwo | T8, T9, T11 | allowlista, izolacja, limity |

## 7. Ryzyka i niewiadome

- **Liniowość wypłat względem stawki** — potwierdzona przez operatora
  (R1); ryzyko zamknięte.
- **Geometria pól w archiwum `legacy_archive`** — nieustalona; T4 rozstrzyga,
  modal ma zabezpieczenie schematem.
- **Orientacja EXIF** — widok musi stosować tę samą konwencję co geometria.
- **Obciążenie** — kalkulacja 100 000 spinów jest synchroniczna w procesie
  API. Limit jednej kalkulacji naraz na sesję chroni Admina; czasu
  odpowiedzi nie mierzono (bez benchmarku, zgodnie z zasadami repo).
- **Quick Tunnel** — bez SLA, adres zmienia się po restarcie; link traci
  ważność po restarcie tunelu.
- **Obrazy w cache przeglądarki odbiorcy** zostają do 24 h po wygaśnięciu
  sesji. Odbiorca mógłby je też zapisać ręcznie; to cecha udostępniania, nie
  błąd.
- **Ujawnienie danych** — odbiorca widzi zdjęcia plansz, pełną sekwencję
  przez wyszukiwanie i wypłaty. To świadomy zakres punktu 5.
- **Równoległe worktree** mogą zająć numery migracji, zadań i decyzji.

## 8. Zakres wyłączony

- Aplikacja mobilna, snapshot i APK.
- Zmiana algorytmu wypłat i rankingu.
- Stały adres publiczny (named tunnel), konta użytkowników, wielu odbiorców
  na jednym linku.
- Cache serwerowy wyników kalkulacji zakresu.
- Uruchomienie tunelu, migracji na bazie deweloperskiej i odbioru na żywych
  danych bez osobnej zgody operatora.
- Zamknięcie TASK-0654.

## 9. Notatka decyzyjna — wybory i odrzucone możliwości

| # | Decyzja | Inne możliwości | Dlaczego ten wybór |
|---|---|---|---|
| 1 | Szczegóły planszy osobnym, leniwym endpointem | (a) dodać `matches` do każdego wiersza zakresu; (b) liczyć linie w przeglądarce | (a) powiększa odpowiedź o dane, z których operator użyje kilku plansz, i nie daje obrazu ani geometrii; (b) duplikuje algorytm wypłat w TypeScripcie i grozi rozjazdem z wydaniami. |
| 2 | Linie rysowane w SVG w przeglądarce | Serwer wypala linie w obrazie | Legenda ma wyłączać linie osobno; obraz z wypalonymi liniami wymagałby nowego renderu przy każdym kliknięciu i psułby cache. |
| 3 | Serwer przycina i zmniejsza zdjęcie (WebP, 1280 px) | (a) obecne kadrowanie CSS pełnego zdjęcia; (b) JPEG; (c) kafelki / wiele rozdzielczości | (a) wysyła całe zdjęcie — sprzeczne z wymaganiem ograniczenia transferu; (b) większe pliki przy tej samej jakości; (c) złożoność nieuzasadniona dla jednej planszy na ekran. |
| 4 | Jeden kontrakt widoku dla Admina i online | Osobne ścieżki obrazów | Jedna implementacja renderowania, jeden cache, identyczny wygląd po obu stronach. |
| 5 | Schemat 3 × 5 z ikon, gdy brak zdjęcia albo geometrii | Blokada modala z błędem | Linie są informacją logiczną; brak zdjęcia nie powinien jej ukrywać. |
| 6 | Siatka z „okrągłymi” podziałkami i opisami | (a) stała liczba równych odcinków; (b) biblioteka wykresów | (a) daje wartości typu 1 237,5; (b) nowa zależność dla jednego wykresu, a obecny SVG jest pod pełną kontrolą. |
| 7 | Etykiety w pasie u góry + kropkowana linia; także dla najechania | Etykieta przy punkcie z automatycznym odsuwaniem | Operator jawnie prosił o górę wykresu; pas nigdy nie zasłania linii bilansu. |
| 8 | Limit 8 przypiętych punktów, bez cichego usuwania | (a) bez limitu; (b) usuwanie najstarszego | (a) etykiety przestają się mieścić; (b) punkt znika bez wiedzy operatora. |
| 9 | Stawka skaluje wypłaty **i** koszt spinu | Skalować tylko wypłaty | Stawka jest kosztem spinu; skalowanie samych wypłat fałszowałoby bilans. |
| 10 | Przeliczenie po stronie klienta, API bez zmian | Parametr `stake` w API | Przeliczenie jest liniowe; zmiana stawki działa natychmiast i bez żądania, a kontrakt API pozostaje stabilny. |
| 11 | Osobne kontrolki „Stawka” i „Jednostka” | Jedna kontrolka, złotówki wymuszają stawkę | Operator chce osobno przeliczać stawkę i osobno walutę. |
| 12 | Arytmetyka całkowita w groszach, zaokrąglenie raz na końcu | `float` z `toFixed(2)` | Sumowanie zaokrąglonych wierszy daje rozjazd groszowy w bilansie narastającym. |
| 13 | Aplikacja online w Reviewerze za istniejącym tunelem | (a) wystawić Admina; (b) nowa aplikacja i nowy tunel; (c) hosting w chmurze | (a) łamie regułę, że Admin zostaje na loopbacku; (b) drugi proces i tunel do utrzymania; (c) sprzeczne z zasadą „bez chmury bez zmierzonej potrzeby”. |
| 14 | Nowa tabela sesji dla nowego celu | Kolumna `purpose` w `reviewer_access_sessions` | Tamta tabela wymaga `import_job_id` i autoryzuje zapis decyzji; model zagrożeń wymaga izolacji celów. |
| 15 | Link bez kodu, kod osobno | Kod w adresie (jedno kliknięcie) | Linki trafiają do historii, podglądów komunikatorów i logów; istniejący model zagrożeń zakłada link bez sekretu. Wygodę można dodać później jako świadomą opcję. |
| 16 | Kod `XXXX-XXXX` z istniejącego generatora | Nowy format 8 znaków bez myślnika | To już 8 znaków z alfabetu bez mylących liter; jeden sprawdzony generator dla trzech rodzajów sesji. |
| 17 | Czas 1/4/8/24 h, domyślnie 8 h | Tylko 8 h i 24 h | Zgodność z panelem zdalnej selekcji; krótsze czasy nic nie kosztują, a ograniczają ekspozycję. |
| 18 | Jeden odbiorca na link | Wiele tokenów na sesję | Prostszy model i audyt; drugi link tworzy się jednym kliknięciem. |
| 19 | Wspólny pakiet `packages/board-search-ui` | (a) kopia komponentów w Reviewerze z testem zgodności; (b) import z `apps/admin` | (a) każda przyszła zmiana wymaga dwóch edycji — a wymaganie mówi o funkcjach „starych i nowych”; (b) aplikacja nie może zależeć od drugiej aplikacji. |
| 20 | Cache: HTTP dla obrazów + pamięć karty dla JSON | (a) service worker; (b) IndexedDB; (c) cache serwerowy wyników | (a)(b) trwałe dane po wygaśnięciu sesji i trudne unieważnianie; (c) sprzeczne z D-462 (świeże przeliczenie po weryfikacji symboli). |
| 21 | Limity żądań na sesję, jedna kalkulacja naraz | Bez limitów | Kalkulacja obciąża ten sam proces, z którego korzysta operator lokalnie. |
| 22 | Dwa etapy z punktem STOP | Jeden etap | Punkty 1–4 dają wartość od razu i są warunkiem punktu 5; etap B niesie ryzyko bezpieczeństwa i zasługuje na osobne polecenie. |

## Przypisanie modeli do zadań

Modele dostępne w bieżącym środowisku: `claude-fable-5-1`, `claude-opus-5-5`,
`claude-sonnet-5-5`, `claude-haiku-4-5-20251001`. Wykonawcą jest model sesji
wybrany przez operatora przy poleceniu etapu A (`claude-opus-5-5`). Audyt
każdego taska wykonuje niezależny agent; poziomu rozumowania agenta nie da
się ustawić jawnie z sesji, dlatego wpis `high` jest rekomendacją warunkową.
Eskalacja: dwa nieudane cykle poprawek P0–P2 zatrzymują etap.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T1 / TASK-0760 | claude-opus-5-5 | high | Zapis gotowych ustaleń w dokumentacji; model sesji wybrany przez operatora. | Tak: claude-opus-5-5, high, osobny agent |
| T2 / TASK-0761 | claude-opus-5-5 | high | Jeden komponent i czyste funkcje; ryzyko w układzie etykiet i dostępności. | Tak: claude-opus-5-5, high, osobny agent |
| T3 / TASK-0762 | claude-opus-5-5 | high | Arytmetyka pieniężna z zaokrągleniami, wiele miejsc prezentacji. | Tak: claude-opus-5-5, high, osobny agent |
| T4 / TASK-0763 | claude-opus-5-5 | high | Pion API, dwa źródła danych, geometria, pliki i cache. | Tak: claude-opus-5-5, high, osobny agent |
| T5 / TASK-0764 | claude-opus-5-5 | high | UI na gotowym kontrakcie; geometria nakładki i stan legendy. | Tak: claude-opus-5-5, high, osobny agent |
| T6 / TASK-0765 | claude-opus-5-5 | high | Przeniesienie między pakietami z zachowaniem zachowania i buildów dwóch aplikacji. | Tak: claude-opus-5-5, high, osobny agent |
| T7 / TASK-0766 | claude-opus-5-5 | high | Migracja, poświadczenia, blokady i audyt. | Tak: claude-fable-5-1, high, osobny agent |
| T8 / TASK-0767 | claude-opus-5-5 | high | Publiczna powierzchnia danych: izolacja gry, redakcja, limity. | Tak: claude-fable-5-1, high, osobny agent |
| T9 / TASK-0768 | claude-opus-5-5 | high | Proxy, cookie, CSP i cache klienta na publicznym hoście. | Tak: claude-fable-5-1, high, osobny agent |
| T10 / TASK-0769 | claude-opus-5-5 | high | Panel według istniejącego wzorca zdalnej selekcji. | Tak: claude-opus-5-5, high, osobny agent |
| T11 / TASK-0770 | claude-opus-5-5 | high | Bramka bezpieczeństwa i spójność dokumentacji z kodem. | Tak: claude-fable-5-1, high, osobny agent |
