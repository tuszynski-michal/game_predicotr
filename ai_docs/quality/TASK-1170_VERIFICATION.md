---
title: TASK-1170 — Weryfikacja zwykłego podglądu i szkiców
status: active
last_updated: 2026-11-09
---

# TASK-1170 — Weryfikacja

Wykonanie T1 w `worktrees/grid-symbol-crop-preview`, gałąź
`codex/grid-symbol-crop-preview`. Poniższy wynik dotyczy implementacji narzędzia,
nie poprawy wytrenowanego modelu ani gotowości obecnych etykiet operatora.
Terminalowy audyt Opus5.5/high R2 zakończony PASS (P0=0/P1=0); raport i receipt są w sąsiednich plikach. Zamknięcie prowadzi task-close.

Audyt Opus R1 dał REVISE (2P0/1P1 oraz6P2). Wykonano jedną rundę poprawek;
mapa uwag i dowodów jest w `TASK-1170_FIXES_R1.md`. Poniższe wyniki testów
dotyczą poprawionego kodu. Nie oznaczają audytorskiego PASS przed focused R2.

## Zakres i dowody

| Kryterium T1 | Implementacja / dowód |
|---|---|
| Dokładne24zapisane punkty, wspólne granice/perspektywa | `grid_content_preview.preview_document` przenosi zapisane współrzędne bez fitu; pure test z nierówną siatką i ułamkami; UI porównuje rzeczywiste SVG points. Niepełne/NaN/inf/out-of-bounds są unavailable. |
| Trzy niezależne warstwy i otoczenie | Ordinary canvas ma Siatka pól / Obrysy grafik / Rzeczywiste wycinki, legendę i osobny zoom z rzeczywistym footprintem na większym tle. Test interakcji przełącza każdą warstwę bez zmian cells/nodes. |
| Brak14ghost quadów | HTML rysuje1obrys dla15komórek z14quad=null mimo14boxInPreview. Nie ładuje overlay PNG. Unknown z faktycznym fragmentem pozostaje pokazany z tekstem/stylingiem fragmentu. |
| Aktualne adnotacje i provenance | Legacy reference jest czytany na nowo. Source/sequence/frame mismatch nie wypełnia edytora ani HTML. UI/HTML pokazują rewizję, origin, actor, approvedBy/humanApproved oraz licznik quadów. |
| Produkcyjny footprint zamiast insetu/pełnego pola | Wyłącznie zapisany paddedSourceQuad aktualnego board_render_manifest. Manifest/cellSHA, source byte/pixelSHA, revision/slot i nominalny quad względem zapisanych nodes są sprawdzane. Brak/drift/błąd dowodu daje unavailable z zachowanymi nodes i poprawnymi komórkami, bez blokady adnotacji. Legalny pozakadrowy footprint pozostaje nieprzycięty, z informacją o wsparciu poza źródłem; SOURCE_SUPPORT_EPSILON jest tolerowany. Konfiguracja renderowania ma zamknięty DTO. |
| Pełny pion kontraktu | Istniejący GET content-references z opcjonalną parą cohortId/manifestSha256; no-store; OpenAPI, wygenerowany SDK, wrapper i request test. Bez pinów historyczne trzy pola; zapisy/CAS bez zmiany. |
| Read-only i trwałość | Disposable PostgreSQL wykonuje rzeczywisty JSONB contains dla aliasu obrazu o innymUUID/byteSHA i innym slocie. Frozen sesja chroni całe normalized pixelSHA; preview nie emituje SQL mutation; legacy read zachowany. Zimny proces odczytuje tę samą ochronę. |
| Blind isolation | Chronione źródło nie powoduje odczytu geometrii i zwraca nullnodes/emptycells bez geometryprovenance. B/REG chronione po roli. Galeria eksportuje tylko niechronione TRAIN. Istniejące26regresji Admin obejmują puste przebiegi, CAS/retry/lostresponse i zmianę gry/źródła/trybu; brak nowych ordinary requestów w blind. |
| Wycofanie generatora koloru | Nowy wersjonowany `scripts/export_grid_content_preview.py` czyta bieżące adnotacje przez GET; nie generuje ani nie importuje propozycji. Untracked root helpers i istniejące szkice pozostają nietknięte. |

## Wykonane kontrole

Każda komenda testu/kontroli miała zewnętrzny timeout subprocess ≤120s.
Worktree i jego `services/api/src;services/worker/src` były jawnie przypięte
przez cwd/PYTHONPATH. Użyto współdzielonego `.venv/Scripts/python.exe`.

| Kontrola | Wynik | Dowód w artifacts tego worktree |
|---|---|---|
| pytest `test_grid_content_preview.py`, `test_grid_content_preview_export.py`, `test_grid_cell_content_targets.py`, `test_grid_cell_content.py` |52PASS | `t1170-r1-api-tests.log` |
| Pełne `npm run test:geometry --workspace @game-predictor/admin` |428PASS/10FAIL, 438testów /20,34s; zmieniony content pion PASS | `t1170-r1-admin-geometry.log` |
| Ograniczony baseline niezwiązanych testów picker/supergames na main |24PASS/10FAIL; identyczne10porażek supergames | `t1170-r1-baseline-unrelated.log` |
| SDK `grid-cell-content-request.test.mjs` przez tsx |4PASS /0,44s | `t1170-r1-sdk-request.log` |
| Po doprecyzowaniu polskich objaśnień powodów: przypadek UI unavailable + helper HTML/export |1UI PASS +6pytest PASS | `t1170-r1-readable-ui.log`, `t1170-r1-readable-html.log` |
| Scoped Ruff9zmienionych plików Python | PASS | `t1170-r1-ruff.log` |
| Scoped mypy `--follow-imports=silent`6plików wykonawczych | PASS | `t1170-r1-mypy.log` |
| Scoped ESLint canvas/ordinary/testinteractions | PASS | `t1170-r1-admin-eslint.log` |
| Standardowe `npm run typecheck --workspace @game-predictor/admin` (next typegen + tsc) | PASS | `t1170-r1-admin-typecheck.log` |
| OpenAPI --check + SDK check:generated po usunięciu ordinaryPreview z write DTO | PASS | `t1170-r1-contract.log` |
| `integration/test_grid_content_targets_postgres.py` z RUN_POSTGRES_TESTS=1 |1PASS /30,43s;15zgodnych produkcyjnych footprintów, cold read i cleanup0/0 | `t1170-r1-pg.log`, `TASK-1168_R2_API-pg-receipt.json` (historyczna nazwa receipt istniejącego rozszerzonego testu) |

Root po pierwszym freeze, przed poprawkami R1, wykonał dodatkowe kontrole.
Regenerację i kontrole docs/map trzeba odświeżyć po obecnym freeze:

| Kontrola | Wynik | Dowód |
|---|---|---|
| Regeneracja mapy kodu | PASS | `artifacts/t1170-code-map.log` |
| `npm run docs:check` | PASS | `artifacts/t1170-docs-check.log` |
| `npm run code-map:check` | PASS | `artifacts/t1170-code-map-check.log` |

Formatowanie wykonano wyłącznie na zmienionych plikach przez Ruff/Prettier.
OpenAPI/SDK rzeczywiście zregenerowano; schema/configuration/optional query mają
test żądania. Root po freeze i poprawkach odświeżył mapę oraz zaliczył docs:check/code-map:check. Niezależny audyt R2 PASS.
Pełny build Admina pozostaje jawną końcową bramką T4 zaakceptowanego planu;
nie był uruchamiany w T1 i nie ma wyniku PASS w tym raporcie.

Pierwsza próba pełnego test:geometry w rundzie R1 miała425PASS/12FAIL.
Nowy test warstw ujawnił zbyt wczesną rejestrację testów przed inicjalizacją
stałych fixture; poprawiono kolejność. Przejściowa porażka pickera nie powtórzyła
się w końcowym pełnym biegu ani w ograniczonym baseline na main. Końcowe10FAIL
to identyczne błędy istniejącego supergames (`undefinedSeriesCountLabel`),
niezmienionego w T1. Nie osłabiono testów i nie naprawiano ich poza zakresem.

## Ograniczenia środowiska i wcześniejsze próby

Pierwsza próba pytest miała7PASS/9fixtureERROR wskutek niedostępnego domyślnego
TMP. Długi worktree temp przekraczał Windows MAX_PATH; testy użyły nowych,
dedykowanych krótkich katalogów root `artifacts/t1170-20261109-*`, za zgodą
agenta głównego. Żaden istniejący katalog danych nie został usunięty.

Windows ograniczał komunikację TestClient: profil ograniczony kończył się
timeout60s bez wyniku. Po timeout sprawdzono brak własnych osieroconych Pythonów;
ten sam pojedynczy test w zatwierdzonym szerszym profilu przeszedł w2s, a następnie
pełny ograniczony zestaw38testów w2,60s. Nie uruchamiano API ani Admina.

Pierwsza próba PostgreSQL ujawniła wymóg non-null report dla testowej frozen
sesji. Poprawiono wyłącznie fixture (report ready), druga próba zakończyła pełny
scenariusz i utworzyła końcowy receipt po cleanup. Nie osłabiono constraintu.

Pierwotne npm junctiony wskazywały main SDK. Agent główny przygotował lokalny
root node_modules z własnymi workspace junctionami i zależnościami z istniejącej
instalacji. Nowy proces rozwiązuje admin-api-client do tego worktree. Końcowy
typecheck i requesttest używają worktree SDK; tymczasowy alias config nie jest
końcową bramką. Bezpieczne przyszłe sprzątanie musi odpiąć wszystkie junctiony
bez podążania za ich celami (`artifacts/worktree-dependency-layout.json`).

## Domyślny pomocniczy workflow

Po wdrożeniu kodu/restartach wykonanych przez operatora nowy eksport zastępuje
uruchamianie archiwalnych generatorów jasności/koloru:

```powershell
.venv/Scripts/python.exe scripts/export_grid_content_preview.py `
  --game <UUID-gry> --cohort <UUID-zamrożonej-kohorty> `
  --manifest <SHA256-manifestu> --limit 50 --offset 0 `
  --output artifacts/current-grid-content-preview-01
```

Katalog musi być nowy; eksport ma limit110s, request≤20s, odpowiedź≤32MiB i
stronę≤50targetów. `preview.json` zawiera pominięcia/nextOffset. Kolejną stronę
eksportuje się do nowego katalogu z jawnym offsetem. Nie ma POST, regeneracji
detektora, zapisu etykiet ani automatycznej akceptacji istniejących szkiców.

## Granice wyniku

Nie wykonano operatorowego treningu/GPU, inferencji, importu691, zmiany bazy,
adnotacji, domyślnego modelu/marginesu, usług, merge ani push. Stara root galeria
nie została nadpisana. Działające usługi nadal mają wdrożony kod; nowego endpointu
nie uruchamiano w tle. Brak live odbioru nowego helpera pozostaje jawny.

T1 pokazuje rzeczywiste zakresy cropów. Odbiór15produkcyjnych rastrów i wejścia NN,
J/10/ciemnych symboli/ramek, przycięć/sąsiada/brakującego rzędu oraz mierzona
jakość należą do T2–T4, z istniejącymi etykietami i pinami; ten raport nie
zastępuje takiego dowodu. Brak danych nie oznacza PASS modelu.

Zaakceptowane ryzyko P2-4: obecny kontrakt chroni role wybranej kohorty i już
zapisane ślepe sesje, nie wszystkie przyszłe wybory obrazu ani globalną historię
ekspozycji we wszystkich kohortach. Nie rozszerzono tej polityki w T1.

Root po rundzie poprawek ponownie zaliczył regenerację mapy, docs:check i
code-map:check. Skupiony audyt R2 sprawdza zamknięcie uwag R1 i regresje zmian.

## Odbiór audytu

R1 REVISE zamknięto jedną rundą poprawek. R2 terminal Opus5.5/high PASS,
P0=0/P1=0; payload f047b00198836ba8e41f41725f1585d084ca669b6b8f91a99f6638f6f2255135,
report SHA856c8cae285ff1f32941b1e24033cab1a6590b774ee859f88733debc1530532c.
P2-4 pozostaje jawnym ryzykiem D594. P2-7/P2-8 są ograniczeniami T1 z zaplanowaną
poprawą w T4; P2-9 usunięto aktualizacją metadanych zamknięcia, bez zmiany kodu.
