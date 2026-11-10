# Audyt TASK-1177 — Wydajny zapis symboli i zamrażanie manifestu

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...f4d1672933487752e51f0e49b4e49513d6779a00 oraz zmiany niezacommitowane, data 2026-11-10
Runda: 2
SHA pakietu: f8ddfd9df89421444bc7e9c81c0d8c7db6c313df9acd206e35a174439476c954
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

To dodatkowy, ukierunkowany przegląd w ramach rundy 2. Operator go zatwierdził. Sprawdziłem poprawkę znaleziska P1-3 (format Prettier dwóch plików Admina) i synchronizację dowodów z P2-5.

Oba pliki wyglądają teraz na sformatowane zgodnie z `.prettierrc.json`, a ostatnia gałąź zagnieżdżonego ternary ma właściwe wcięcie. Outcome taska i raport weryfikacji podają spójne liczby, a sekcja granic ma treść pod właściwym nagłówkiem.

Nie ma otwartych P0 ani P1. Najważniejszym ryzykiem merytorycznym pozostaje jawnie zaakceptowane P2-1 (inwariant pisarzy wejść manifestu). Odnotowuję też jedno istniejące wcześniej uszkodzenie kodowania komunikatu w ścieżce freeze.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/src/game_predictor_api/application/verified_training_cohorts.py:321` — Ryzyko z rund 1 i 2 pozostaje bez zmian.
  - Fence jest poprawny tylko wtedy, gdy każdy pisarz wejść manifestu podbija `catalog_revision` albo unieważnia gotowość projekcji.
  - Architektura D-600 zawiera ten inwariant i listę kontrolną. Testy obejmują bulk i ręczną geometrię.
  - Raport weryfikacji jawnie zachowuje to ryzyko (`ai_docs/quality/TASK-1177_VERIFICATION.md`, sekcja „Audit correction round”).
  - Propozycja: utrzymać akceptację ryzyka w task-close. Testy pozostałych pisarzy można dodać w osobnym tasku.
- [P2-2] `services/api/src/game_predictor_api/storage/image_review_repository.py:713-721` — Zawieszony job CREATED/PROCESSING typu IMPORT lub IMAGE_GRID_REINFERENCE nadal bezterminowo blokuje przygotowanie danych. Panel nie wskazuje, który job blokuje.
  - Według raportu weryfikacji odczyt danych operatora nie znalazł żadnego takiego joba.
  - Odroczenie zapisano jawnie, więc akceptacja ryzyka w task-close jest właściwa.
- [P2-6] `apps/admin/src/features/model-quality/model-quality-actions.ts:681` — Komunikat błędu po udanym zamrożeniu i nieudanym starcie treningu jest zapisany z uszkodzonym kodowaniem: `'Kohorta zostaÅ‚a zamroÅ¼ona, ale nie udaÅ‚o siÄ™ uruchomiÄ‡ treningu.'`.
  - Linia leży poza hunkiem diffu, więc błąd istniał już w HEAD i nie wprowadziła go ta zmiana.
  - Pozostałe komunikaty w tym pliku (np. 618, 651–656) mają poprawne polskie znaki.
  - Skutek: w tej gałęzi ścieżki freeze, objętej zakresem taska, operator zobaczy nieczytelny tekst.
  - Propozycja: poprawić literał na UTF-8 („Kohorta została zamrożona, ale nie udało się uruchomić treningu.”) przy task-close albo w osobnym drobnym tasku. Można też jawnie odnotować to ryzyko.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Zmierzona przyczyna i ograniczone porównanie przed/po | spełnione (według raportu, bez ponownego pomiaru) | `ai_docs/quality/TASK-1177_VERIFICATION.md`, sekcja „Performance limits”: 413→376 SQL, 1.229→1.180 s; inwentarz: stara wersja przekroczyła limit 12 s, nowa 3.292 s |
| Mniej zbędnych SQL, krótsze sekcje blokad, zgodny wynik zapisów | spełnione (ocena z rundy 2, kod backendu bez zmian w tej poprawce) | Raport R2: `image_symbol_review_bulk_operation_repository.py` i `verified_training_cohorts.py:320-331` |
| Aktualne potwierdzenie manifestu, realne stale nadal blokuje | spełnione, z ryzykiem P2-1 | `verified_training_cohorts.py:324-339`; `model-quality-workspace.tsx:239-248`; `model-quality-loading.test.mjs:153-211` |
| Czytelny konflikt/oczekiwanie i bezpieczny retry w Adminie | spełnione | `model-quality-actions.ts:640-662`; `model-quality-workspace.tsx:232-262`; `model-quality-loading.test.mjs:153-337` (nowy klucz idempotencji po STALE: 207; WRITE_BUSY: 213-252; spóźniona odpowiedź po zmianie gry: 290-337) |
| Restart/utrata odpowiedzi/własność/holdouty/human approvals chronione | spełnione statycznie | Ocena z rundy 2. `model-quality-workspace.tsx:225` utrzymuje klucz idempotencji przy retry po utracie odpowiedzi |
| API/OpenAPI/SDK zgodne, właściwe testy PG/UI i kontrole zaliczone | spełnione (według deklaracji wykonawcy) | Format obu plików jest statycznie zgodny z `.prettierrc.json` (`model-quality-actions.ts:647-662`, `model-quality-loading.test.mjs:153-337`). Raport weryfikacji deklaruje Prettier PASS dla trzech plików Admina oraz OpenAPI check PASS. Wyników nie potwierdzałem uruchomieniem |
| Opus i task-close przed commitem, P2 jawnie zapisane | niezweryfikowane | Ten przegląd kończy się PASS. Task-close jeszcze nie nastąpił. P2-1 i P2-2 są zapisane w raporcie weryfikacji, a P2-6 wymaga dopisania przy task-close |

## Listy zamknięte i otwarte

Zamknięte: P1-1, P1-2, P1-3, P2-3, P2-4, P2-5

Dowody zamknięcia z tej rundy:

- **P1-3:** w `apps/admin/test-interactions/model-quality-loading.test.mjs:153-337` bloki `finally` są wielowierszowe (208-210, 249-251, 285-287, 334-336). Strzałki mają nawiasy `(b) =>` (194, 239, 276, 307). Wywołania `mount(client({` są złamane zgodnie z resztą pliku. W `apps/admin/src/features/model-quality/model-quality-actions.ts:657` gałąź `: apiErrorMessage(` ma teraz wcięcie 16 spacji, zgodne z wcięciem zagnieżdżonych ternary w Prettier 3. Raport weryfikacji deklaruje Prettier check PASS dla wszystkich trzech zmienionych plików Admina.
- **P2-5:** Outcome taska (`ai_docs/tasks/1177-symbol-review-performance-freeze.md`, sekcja „Outcome”) podaje 56 Python, 14 PostgreSQL i 12 interakcji, co zgadza się z raportem weryfikacji (8+5+1 PostgreSQL). Opisuje też stan rund R1/R2. Nagłówek „Boundaries and remaining work” w `TASK-1177_VERIFICATION.md` ma teraz treść.
- P1-1, P1-2, P2-3 i P2-4 zamknięto w rundzie 2 z dowodami podanymi w `ai_docs/quality/TASK-1177_AUDIT_R2_claude-opus-5-5.md`. Ta poprawka ich nie narusza.

Otwarte: P2-1, P2-2, P2-6.

## Proponowane testy

- `npm run format:check`, a potem pełne `npm run quality`. Ma to potwierdzić deklarowany wynik Prettier i całą bramkę przed commitem.
- `npm run test:interactions --workspace @game-predictor/admin` (lub odpowiedni skrypt workspace) z dodatkowym przypadkiem w `apps/admin/test-interactions/model-quality-loading.test.mjs`: udany freeze i błąd `createSymbolTraining`. Asercja sprawdza czytelny polski komunikat. Wymusiłoby to poprawkę P2-6.
- `services/api/tests/integration/test_symbol_review_performance_freeze_postgres.py`: zmiana `recognized_boards.geometry_revision` lub właściciela fast document między poświadczeniem a fence'em daje STALE (wzmocnienie P2-1). Uruchomienie z `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`.

## Zakres przeglądu i ograniczenia

Przeczytałem cały zamrożony pakiet:

- task;
- wycinek planu;
- diff zmian śledzonych;
- raport rundy 2 z receiptem;
- raport weryfikacji.

W repozytorium przejrzałem:

- `apps/admin/src/features/model-quality/model-quality-actions.ts` (typy wyniku i `freezeModelQualityCohort`, linie 370-690);
- `apps/admin/test-interactions/model-quality-loading.test.mjs` (linie 1-360 i definicje pomocników `fullQuality`, `quality`, `client`, `flush`, `mount`, `unmount`);
- `apps/admin/src/features/model-quality/model-quality-workspace.tsx` (linie 200-290);
- `.prettierrc.json`.

Wyszukałem też uszkodzone kodowanie w katalogu `model-quality`.

Nie uruchamiałem Prettier, testów, lintu, typechecku, OpenAPI ani pomiarów. Zgodność formatu oceniam statycznie na podstawie konfiguracji i stylu reszty pliku. Wynik PASS Prettier i pozostałe wyniki pochodzą z raportu wykonawcy. Kodu backendu nie analizowałem ponownie, bo ta poprawka go nie zmieniała; oceny backendu pochodzą z rundy 2.