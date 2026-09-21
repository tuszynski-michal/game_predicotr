---
title: TASK-0604 Shared deterministic shape geometry v2 core
status: done
last_updated: 2026-09-21
---

# TASK-0604 — Wspólny deterministyczny rdzeń geometrii shape v2

## Status

`in_progress`

## Goal

Dostarczyć czysty, deterministyczny rdzeń v2, który na kanonicznym obrazie RGB
proponuje geometrię pełnej strony z ramką, perspektywę, dziewięć plansz 3 × 5
i ustrukturyzowany powód review bez używania profilu ani algorytmu per gra.

## Context

G01 potwierdził kontrakt przyszłych gier z rodziną `framed_full_page_v2`.
G02 buduje wspólny mechanizm niezależnie od brakujących corpusów
produkcyjnych. Istniejący `VerifiedPageRegistrar` i
`structured_geometry` zachowują zachowanie v1.0/v1.1; nie wolno zmieniać ich
masek czerwieni, progów ani fingerprintów. Kolor ramki jest tylko opcjonalnym,
wielokolorowym dowodem wzmacniającym kandydat znaleziony przez kształt i
kontrast.

## Dependencies / entry conditions

- G00 i G01 są ukończone w `c1e063d3` i `4b914f5e`.
- Plan `ai_docs/delivery/SHAPE_GEOMETRY_V2_EXECUTION_PLAN.md` jest
  zaakceptowany.
- Brak corpusów executor nie blokuje modułu i jego syntetycznych regresji; nie
  pozwala jednak ustalić progów produkcyjnych ani aktywować automatu.

## Recommended execution

`gpt-5.6-terra`, reasoning `xhigh`: zadanie łączy geometrię projekcyjną,
deterministyczne rozstrzyganie hipotez i ochronę przed błędnym automatem.
Przed commitem obowiązuje `gpt-6-astra`, reasoning `medium`, dla
niezależnego sprawdzenia false-accept, kompletności i izolacji v1.1.
P0/P1: dowód koloru sam akceptuje stronę, wynik ignoruje brak slotu/ucięcie,
niedeterministyczna kolejność kandydatów albo zmiana zachowania v1.1 — zatrzymać
serię.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SHAPE_GEOMETRY_V2_EXECUTION_PLAN.md`
- `ai_docs/quality/SHAPE_GEOMETRY_V2_MEASUREMENT_PROTOCOL.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/delivery/GLOBAL_GEOMETRY_LIBRARY_EXECUTION_PLAN.md`

## Scope

- Dodać niezależny od ORM, HTTP i profili gry moduł `shape_geometry_v2` z
  wejściem `RGB uint8 ndarray`, jawną konfiguracją, znormalizowanym quadem
  strony, homografią i deterministycznym porządkiem kandydatów.
- Wykrywać neutralne kolorystycznie hipotezy ramki przez kształt i kontrast;
  obliczać opcjonalny wielokolorowy dowód ramki dopiero dla hipotezy
  strukturalnej.
- Rektyfikować stronę, wyprowadzić pełną siatkę 3 × 3 plansz i 3 × 5 komórek,
  sprawdzić jej regularność oraz kompletność obrazu.
- Zwracać `needs_manual_review` z kodami dowodów, gdy kształt, siatka albo
  kompletność są niepewne. Moduł nie może zwrócić akceptacji importu.
- Pokryć syntetyczne strony o co najmniej dwóch kolorach ramek, perspektywie,
  słabej siatce, ucięciu i stabilnym replayu.

## Out of scope

- Profil wspólny, migracja, API, UI, import, aktywacja lub zapis korekty.
- Sieć neuronowa, trening, ORB jako obowiązkowy etap oraz powielanie silnika
  dla poszczególnych gier.
- Zmiana v1.0/v1.1 lub użycie danych acceptance.

## Acceptance criteria

- [x] Wynik zawiera jeden kanoniczny quad, homografię, siatkę 9 × 15 i
      diagnostykę albo stabilny kod review.
- [x] Kolor nie może sam utworzyć propozycji ani poprawić wyniku bez
      niezależnego dowodu kształtu/kontrastu.
- [x] Wynik nie udaje kompletności przy ucięciu pionowym albo brakującym
      dowodzie siatki.
- [x] Ta sama tablica wejściowa i konfiguracja dają identyczny wynik.
- [x] Historyczne moduły rejestracji nie są modyfikowane.
- [x] Testy obejmują perspektywę, dwa kolory, słabą siatkę, niepełność oraz
      deterministyczny replay.

## Technical notes

Wynik rdzenia jest propozycją do późniejszej weryfikacji G03, nigdy
automatycznym importem. Kolejność: walidacja wejścia → neutralne kandydaty
czterech narożników → deterministyczna deduplikacja i ranking → homografia do
stałego płótna → dowód regularnej siatki → kontrola kompletności → opcjonalna
miara wielokolorowa. Brak dowodu kończy się dokładnym reason code; nie ma
fallbacku do koloru ani cichego obcięcia slotów.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/images/shape_geometry_v2/core.py`.
- Nowe: `services/worker/tests/test_shape_geometry_v2_core.py`.
- Istniejące: `services/worker/src/game_predictor_worker/images/shape_geometry_v2/__init__.py`.
- Istniejące: `ai_docs/quality/SHAPE_GEOMETRY_V2_MEASUREMENT_PROTOCOL.md`,
  `CURRENT_STATE.md`, `DECISION_LOG.md` i ta karta.

## Test cases

- Pełna syntetyczna strona o czerwonej i złotej ramce → ta sama neutralna
  geometria oraz dowód koloru tylko jako metryka.
- Transformacja perspektywiczna pełnej strony → dziewięć plansz i 135 komórek
  w kanonicznym porządku row-major.
- Brak wewnętrznej siatki albo pionowe ucięcie → `needs_manual_review`, bez
  propozycji kompletnego importu.
- Dwukrotny replay identycznej tablicy → identyczny payload bajt po bajcie.

## Verification

```powershell
# C:\Users\tuszy\.codex\worktrees\shape-geometry-v2\game_predicotr
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m pytest services\worker\tests\test_shape_geometry_v2_core.py services\worker\tests\test_shape_geometry_v2_corpus.py services\worker\tests\test_shape_geometry_v2_experiment.py -q --basetemp .runtime\pytest-shape-v2-g02
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m ruff check services\worker\src\game_predictor_worker\images\shape_geometry_v2 services\worker\tests\test_shape_geometry_v2_core.py
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m mypy --no-incremental --follow-imports=skip services\worker\src\game_predictor_worker\images\shape_geometry_v2\core.py
```

## Risks / open questions

- Syntetyczne regresje sprawdzają kontrakt i bezpieczeństwo, nie skuteczność
  na realnych grach. Parametry jakościowe wymagają później atestowanego corpusów.
- G02 nie może obiecać automatycznych importów; G03 doda lokalną weryfikację i
  snapshot, a G07 kwalifikację aktywacji.

## Outcome

### Changed

- Dodano wspólny, czysty rdzeń `shape_geometry_v2.core`: neutralne wykrycie
  ramki, homografia do kanonicznego płótna, siatka 3 × 3 / 3 × 5, kontrola
  kompletności i ustrukturyzowany wynik `proposal` albo
  `needs_manual_review`.
- Dowód koloru jest obliczany dopiero po wykryciu strukturalnej ramki i nie
  uczestniczy w jej wyborze. Rdzeń nie ma ścieżki automatycznego importu.
- Siatka wymaga dowodu w każdym z dziewięciu slotów; brak planszy, słaba
  siatka lub ucięcie kończy się review bez plansz i komórek.
- Skorygowano kanoniczną orientację narożników, wspólny zakres W−1/H−1 dla
  homografii i siatki oraz odrzucanie niejednoznacznego, małego konturu bez
  przerywania detekcji strony.

### Verification results

- 28 testów shape-v2 przeszło, w tym regresje perspektywy, dwóch kolorów,
  braku slotu, odbicia lustrzanego, ucięcia i konturu poza stroną.
- Ruff zmienionego pakietu i ograniczony mypy rdzenia przeszły; mypy ostrzegł
  jedynie o zastanej, nieużywanej sekcji konfiguracji ONNX.
- Pierwszy audyt Astra Medium wykrył P1 braku slotu i trzy P2. Poprawiono je
  wraz z reprodukcjami. Re-audyt wykrył dodatkowe P2 niejednoznacznego
  konturu, również poprawione. Końcowy re-audyt nie ma P0–P2 ani P3.

### Not completed

- Parametry jakościowe nie są progami produkcyjnymi; wymagają później
  atestowanego corpusów. G02 nie łączy jeszcze rdzenia z preflightem, API,
  biblioteką ani importem.

### Documentation updates

- Uzupełniono protokół pomiaru i Decision Log o deterministyczną propozycję
  rdzenia oraz wymóg dowodu w każdym slocie.

### Recommended next task

- G06 — trwała, neutralna biblioteka wersji profili geometrii.
