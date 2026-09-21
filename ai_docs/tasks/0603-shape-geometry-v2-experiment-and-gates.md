---
title: TASK-0603 Shape geometry v2 experiment and gates
status: blocked
last_updated: 2026-09-21
---

# TASK-0603 — Eksperyment i bramki geometrii shape v2

## Status

`blocked`

## Goal

Na rzeczywistym corpusie executor wyznaczyć algorytm, dowody decyzji i liczbowe
bramki jakości dla pięciu gier, a następnie uzyskać ich jawne zatwierdzenie
przed rozpoczęciem G02.

## Context

G00 dostarczył checksum-bound kontrakt corpusów, protokół metryk i baseline
v1.1. Nie dostarczył obrazów ani anotacji, ponieważ pozostają operator-owned.
Plan nie pozwala zastąpić ich danymi syntetycznymi ani użyć acceptance do
projektowania algorytmu.

## Dependencies / entry conditions

- G00 jest ukończone w commicie `c1e063d3`.
- 2026-09-21 sprawdzono lokalny worktree: `examples/imgs` zawiera tylko
  `README.md`; w repo nie ma JPEG-ów shape v2 ani wypełnionego manifestu
  executor. Poza repo istnieją niezarządzane katalogi JPEG-ów, lecz bez
  manifestu, podziału, przypisania gry, anotacji i profilu v1.1. Pojedyncza
  obejrzana próbka wskazuje pełną stronę 3 × 3 Blazing, co nie stanowi jeszcze
  atestacji całego zbioru.
- `shape-geometry-v2-executor-corpus.local.example.json` ma zastępczy
  `corpusRoot`, pustą listę `sources` i `v11Profile: null` dla każdej gry.
- Przed odblokowaniem operator udostępnia lokalny manifest `executor`, jego
  corpus root, checksum-bound manual annotations oraz przypięte profile v1.1
  dla dostępnych gier. Materiał acceptance pozostaje niedostępny.
- Przed G02 właściciel jawnie zatwierdza liczby bramek ustalone na development
  i calibration. Polecenie realizacji całego planu nie może zatwierdzić
  nieistniejących jeszcze wartości pomiarowych.

## Recommended execution

`gpt-5.6-terra`, reasoning `xhigh`: porównanie wariantów, wartości dowodów i
bramek wymaga ścisłego rozdzielenia danych oraz mianowników. Przed commitem
wyniku obowiązuje niezależny review `gpt-6-astra`, reasoning `medium`, dla
metodologii i ochrony acceptance. P0/P1: jakikolwiek odczyt acceptance podczas
strojenia, wynik liczony na nieprzypiętym corpusie albo automatyczne przyjęcie
bramek zatrzymuje plan.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `TEMP PLAN V2 GEOMETRY.md`
- `ai_docs/tasks/completed/0602-shape-geometry-v2-corpus-baseline.md`
- `ai_docs/quality/SHAPE_GEOMETRY_V2_MEASUREMENT_PROTOCOL.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ALGORITHMS.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`

## Scope

- Porównać per gra na development/calibration: kształt i kontrast bez/z
  pomocniczym kolorem, bez/z jedną przypiętą kotwicą oraz bez/z transferowym
  profilem, który wyklucza badaną grę.
- Zapisać algorytm, pseudokod decyzji, format dowodów, konflikty hipotez,
  tolerancje, limity zasobów i bramki per gra.
- Raportować osobno automaty plansz, automaty źródeł, błędne automaty,
  review/korekty, tylko-potwierdzenie, czas operatora i koszt konfiguracji.
- Zatrzymać G01 z `not_evaluable`, gdy dowód dla gry lub porównania transferu
  nie ma mianownika albo nie spełnia minimum liczności.

## Out of scope

- Implementacja silnika v2.0, API, UI, migracje, import i trwała biblioteka.
- Użycie lub ujawnienie acceptance, zastąpienie danych realnych danymi
  syntetycznymi, wyprowadzenie liczb z wyników v1.1 innych gier albo aktywacja
  automatu.

## Acceptance criteria

- [ ] Każdy wynik wskazuje fingerprint manifestu, inwentarza, anotacji,
  profilu v1.1 i algorytmu; żaden nie używa acceptance.
- [ ] Każda z pięciu gier ma mierzalny raport albo jawny `not_evaluable` z
  przyczyną oraz osobnymi mianownikami.
- [ ] Transfer dla gry nie używa jej własnych źródeł, kotwic ani wkładów;
  brak wykazanej korzyści jest przekazany właścicielowi jako decyzja zakresu.
- [ ] Dokument bramek zawiera liczby, tolerancje, minima prób, budżety czasu i
  pamięci oraz wymaga jawnej akceptacji właściciela przed G02.
- [ ] v1.1 pozostaje niezmieniony, a dane i wyniki eksperymentu nie tworzą
  joba, importu ani zapisu do bazy.

## Technical notes

Początek G01: odczytaj manifest executor, zamroź inwentarz i uruchom jego
baseline v1.1 w trybie `--check`. Następnie dla każdego wariantu przechodź po
źródłach w stabilnym porządku `captureFamilyId`, `sourceOrdinal`, SHA,
`sourceId`; wynikowi przypisz ten sam zestaw mianowników i statusów. Rozdziel
pomiar konfiguracji od automatu oraz korekty. Kandydat transferowy jest
budowany wyłącznie z innych gier, a jego brak jest wynikiem, nie fallbackiem do
ukrytej kotwicy badanej gry. Dopiero po pełnym raporcie można zaproponować
wartości bramek do decyzji właściciela.

## Expected files

- Nowe: `ai_docs/quality/SHAPE_GEOMETRY_V2_GATES.md` — wersjonowana decyzja
  liczbowa po pomiarze i akceptacji właściciela.
- Nowe, lokalne i ignorowane: zamrożone manifesty executor, anotacje, baseline
  i raport eksperymentu; bez JPEG-ów, ścieżek hosta i danych acceptance.
- Istniejące: `ai_docs/quality/SHAPE_GEOMETRY_V2_MEASUREMENT_PROTOCOL.md`,
  `TEMP PLAN V2 GEOMETRY.md`, `CURRENT_STATE.md` i ta karta.

## Test cases

- Wariant z manifestem acceptance jest odrzucany przed odczytem obrazu.
- Zmiana corpus, anotacji, profilu albo algorytmu po zamrożeniu zatrzymuje
  replay wyniku.
- Przypisanie obrazu, kotwicy lub wkładu badanej gry do jej profilu transferu
  jest wykrywane jako błąd.
- Pusty mianownik, brak kotwicy i brak wymaganej liczności dają
  `not_evaluable`, a nie 0% albo wynik zaliczony.

## Verification

```powershell
# C:\Users\tuszy\.codex\worktrees\shape-geometry-v2\game_predicotr
# Wykonać po dostarczeniu lokalnych artefaktów executor:
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe scripts\freeze_shape_geometry_v2_corpus.py --manifest <executor-manifest.json> --output <executor-inventory.json> --check
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe scripts\run_shape_geometry_v2_v11_baseline.py --manifest <executor-manifest.json> --inventory <executor-inventory.json> --output <v11-baseline.json> --check
```

G01 pozostaje zablokowane, dopóki powyższe artefakty nie są dostępne i spójne.

## Risks / open questions

- Brak rzeczywistych danych dla 777, Blazing, Gang, Reels i Mumie uniemożliwia
  wyznaczenie uczciwych progów między grami.
- Dostępny historyczny manifest M5 opisuje tylko jedną grę i nie ma obecnie
  obrazów w `examples/imgs`; nie może zastąpić corpusów G01. Niezarządzane
  JPEG-y poza repo wymagają najpierw jawnej klasyfikacji przez operatora; ich
  lokalizacja nie jest zapisywana w repozytorium.
- Wartości bramek nie są jeszcze decyzją produktu i nie mogą zostać wymyślone
  w celu odblokowania G02.

## Outcome

### Changed

- Utworzono kartę G01 i zapisano zweryfikowaną przeszkodę wejściową.

### Verification results

- Potwierdzono brak zarejestrowanego executor corpus shape v2 w worktree oraz
  pusty stan przykładowego manifestu. Znaleziono niezarządzane JPEG-y poza
  repo, lecz bez wymaganej atestacji; nie wykonano pomiaru na danych
  zastępczych ani nie przypisano ich samodzielnie do gry.

### Not completed

- Pełny eksperyment, raport i liczby bramek czekają na corpus executor,
  anotacje i profile v1.1.

### Documentation updates

- `CURRENT_STATE.md` wskazuje stan blokady i potrzebne artefakty.

### Recommended next task

- Odblokować ten sam TASK-0603 po udostępnieniu lokalnych artefaktów executor;
  nie rozpoczynać G02 przed jego ukończeniem i decyzją właściciela o bramkach.
