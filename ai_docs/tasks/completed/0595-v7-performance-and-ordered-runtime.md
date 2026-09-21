---
title: V7 performance measurement and deterministic ordered runtime
status: done
last_updated: 2026-09-21
---

# TASK-0595 — wydajność i uporządkowany runtime V7

## Status

`done`

## Goal

Dostarczyć ograniczony pamięciowo, deterministyczny potok przygotowania zdjęć
V7 oraz powtarzalny benchmark raportujący koszt manifestu, dekodowania, OCR,
analizy, finalizacji i RAM/VRAM bez aktywowania ani zapisywania produkcyjnego
runu.

## Context

T00 potwierdził, że obecny Paddle 3.3.1 działa na CPU mimo RTX 4050. T02/T05
nie dostarczyły jeszcze kalibracji pozwalającej na automatyczny dowód, a T06
blokuje start V7 aż do odbioru T12. T11 może więc mierzyć prawdziwe lokalne
etapy na przypiętym korpusie, ale nie może obejść bramki, podmieniać modelu ani
przedstawiać wyniku benchmarku jako sukcesu OCR.

## Dependencies / entry conditions

- T00–T05 są zakończone; lokalny model i manifest T01 są przekazywane jako
  argumenty CLI, a obecny runtime GPU jest warningiem, nie konfiguracją.
- T07 definiuje kolejność `source_index` i wymaga, aby `V7ScanRunState.consume`
  otrzymywał wyniki dokładnie w kolejności manifestu.
- `game_predictor_worker.benchmarks.performance` już raportuje working set na
  Windows oraz peak alokacji Pythona; nie wolno wprowadzać nowej usługi ani
  zależności telemetrycznej.

## Recommended execution

`gpt-5.6-terra`, reasoning `xhigh`. Zadanie łączy ograniczoną współbieżność,
niezmienność kolejności i rzeczywisty pomiar lokalnego urządzenia. Po
implementacji obowiązuje review `gpt-6-astra`, reasoning `medium`; każde
znalezisko ma zostać naprawione i ponownie zweryfikowane przed commitem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/V7_T02_LABEL_LOCALIZATION_PROBE.md`
- `ai_docs/tasks/0595-v7-performance-and-ordered-runtime.md`

## Scope

- Dodać framework-free potok, który może przygotowywać (np. odczyt/dekodowanie)
  kolejne źródła równolegle, ale przekazuje gotowe wyniki konsumentowi tylko w
  rosnącej kolejności `source_index`.
- Ograniczyć liczbę futures i zatrzymanych gotowych payloadów do jawnego
  `max_in_flight`; nie magazynować wszystkich pełnych obrazów, cropów ani
  wyników OCR w RAM.
- Zachować jedno seryjne użycie mutowalnego recognizera/Paddle. Nie współdzielić
  go przez workery; przygotowanie ma nakładać się na analizę bieżącego źródła.
- Dodać CLI benchmarku dla przypiętego manifestu i inwentarza T01, z
  argumentami liczby próbek, workerów i limitu in-flight. Raport ma zawierać
  CPU/GPU runtime, etapowe czasy, throughput, peak RSS/Python, najwyższy
  obserwowany in-flight oraz identyczność uporządkowanego wyniku `1` vs `N`.
- Uruchomić ograniczony, read-only pomiar na lokalnym korpusie z konfiguracjami
  `1`, `2` i `4` workers, nie więcej niż jedna deterministyczna próbka na case.
  Wybrać wartość domyślną wyłącznie, jeżeli wyniki są identyczne; w przeciwnym
  razie użyć bezpiecznego jednego workera i opisać wynik.

## Out of scope

- Aktywacja V7, zmiana `capabilities.v7.startEnabled`, start API lub zapis JPEG.
- Kalibracja geometrii, strojenie progów, trening, równoległe predyktory Paddle,
  instalacja CUDA/GPU builda, Redis/Celery oraz pełny benchmark całego korpusu.
- Modyfikacja JPEG-ów, katalogów `cut`, manifestu źródłowego lub danych operatora.

## Acceptance criteria

- [ ] Potok zawsze oddaje konsumentowi wyniki w rosnącej kolejności wejściowej,
  nawet gdy późniejszy worker kończy wcześniej.
- [ ] Waliduje unikalne, kolejne `source_index`, ogranicza in-flight i po błędzie
  anuluje wyłącznie własne oczekujące futures; nie przekazuje konsumentowi
  żadnego późniejszego źródła. Wcześniej skonsumowany prefiks jest wyłącznie
  stanem do checkpointu należącym do wywołującego, a nie opublikowanym wynikiem.
- [ ] Jeden mutowalny OCR consumer jest seryjny; każdy wynik 1 vs 2/4 workers
  ma identyczny fingerprint uporządkowanych danych wejściowych i wyjściowych.
- [ ] Benchmark weryfikuje manifest/inventory przed pomiarem OCR; domyślnie
  nie wybiera validation/holdout jako obserwacji, lecz może sprawdzić ich SHA
  wyłącznie w pełnym inwentarzu. Raportuje osobno runtime CPU/GPU, etapowe
  czasy, throughput, RSS/Python oraz VRAM jako `unavailable`, gdy Paddle CPU.
- [ ] Rzeczywisty ograniczony pomiar oraz jego ograniczenia są zapisane w
  raporcie jakości; brak proofu nie jest metryką sukcesu automatu.

## Technical notes

Nowy scheduler przyjmuje pozycjonowane wejścia i funkcje `prepare` oraz
`consume`. Wyłącznie `prepare` działa w `ThreadPoolExecutor`; konsument odbiera
future o najmniejszym nieukończonym indeksie, więc OCR/quality/checkpoint mogą
pozostać deterministyczne. Po każdym consume planuje najwyżej jedno następne
wejście. Zatem najwyżej `max_in_flight` payloadów może istnieć w future/ready
queue, także gdy indeks 0 jest powolny, a późniejsze są gotowe.

Benchmark ładuje `V7CorpusManifest` i zamrożony inventory z T01, wybiera
deterministycznie pierwszy JPEG z każdego dozwolonego case i wykonuje pełne
dekodowanie EXIF do RGB w preparation. Seryjny consumer lokalizuje cropy i
wywołuje jeden recognizer. Nie buduje proofu z konfiguracji zakresów ani nie
zapisuje `V7ScanRunState`; raportuje tylko liczbę etykiet i stabilny digest
obserwacji. Etapy to `manifestValidation`, `decode`, `locator`, `ocr`,
`orderedConsume`, `finalization` (digest/raport) oraz `total`.

Domyślna polityka produktu po pomiarze: jeśli CPU-only i konfiguracje mają
identyczny digest, użyj najmniejszej liczby workerów z najlepszym czasem, przy
remisie mniejszej; `max_in_flight = 2 * workers`, ograniczone do 8. GPU nie
staje się aktywne wyłącznie dlatego, że jest widoczne w systemie — raport musi
potwierdzić GPU build i urządzenie.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_ordered_runtime.py` — bounded ordered scheduler i raport etapów.
- Nowe: `services/worker/tests/test_v7_ordered_runtime.py` — out-of-order,
  limit pamięciowy, błąd prepare/consume i identyczność 1/N.
- Nowe: `scripts/benchmark_v7_selection_runtime.py` — read-only CLI benchmarku.
- Istniejące: `services/worker/src/game_predictor_worker/benchmarks/performance.py` — użyty sampler RSS, bez duplikacji.
- Istniejące: `ai_docs/requirements/IMAGE_SELECTION.md`,
  `ai_docs/architecture/IMAGE_SELECTION.md`, `ai_docs/process/CURRENT_STATE.md`
  — udokumentowany kontrakt i wynik pomiaru.

## Test cases

- `0…5`, gdzie preparation kończy `5…0` → consumer widzi dokładnie `0…5`.
- Powolny pierwszy worker i szybkie późniejsze → liczba zleconych/gotowych
  payloadów nie przekracza `max_in_flight`.
- Duplikat, luka lub ujemny indeks → błąd przed uruchomieniem workera.
- Błąd future albo consume → wyjątek zawiera indeks, żadna późniejsza pozycja
  nie trafia do consumer'a.
- Ten sam fixture 1/2/4 workers → identyczne uporządkowane wyniki i digest.
- Manifest/inventory drift albo niedostępny GPU → raport fail-closed/warning,
  bez otwierania niedozwolonych źródeł i bez zapisu JPEG-a.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr, maks. 120 s na krok
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_v7_ordered_runtime.py services/worker/tests/test_benchmark_performance.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection/v7_ordered_runtime.py services/worker/tests/test_v7_ordered_runtime.py scripts/benchmark_v7_selection_runtime.py
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/semi_automatic_selection/v7_ordered_runtime.py
```

Przed commitem uruchomić ograniczony benchmark z lokalnym manifestem/modelami
T01/T00 i zapisać wynik do `ai_docs/quality/`. Zadanie kończy się po self-audycie,
review Astra Medium, poprawkach, ponownych testach i osobnym commicie.

## Risks / open questions

- Aktualny model Paddle CPU-only może sprawić, że 2/4 workers nie poprawią
  czasu; jest to poprawny wynik, nie powód do instalacji zależności ani zmiany
  progu odbioru.
- T05 nie ma kalibracji, więc benchmark nie jest dowodem jakości ani podstawą
  aktywacji. T12 nadal wymaga niezależnego holdoutu i wszystkich progów planu.

## Outcome

Zrealizowano framework-free `v7_ordered_runtime.py`: przygotowanie kolejnych
źródeł może działać w ograniczonym `ThreadPoolExecutor`, ale mutowalny consumer
zawsze dostaje wynik w rosnącej kolejności `source_index`. Domyślna, zmierzona
polityka to cztery workery i okno ośmiu future/payloadów; własne referencje do
skonsumowanego payloadu są zwalniane przed uzupełnieniem okna, a scheduler nie
akumuluje wyników OCR. Błąd prepare lub consume anuluje oczekujące futures i
nie konsumuje późniejszego indeksu; caller decyduje, czy wcześniej skonsumowany
prefix utrwala jako checkpoint.

Dodano read-only `scripts/benchmark_v7_selection_runtime.py`. Przed pomiarem
porównuje pełny inwentarz T01, a obserwacje OCR wybiera tylko z
development/calibration. Digest obejmuje kolejność, case, ścieżkę, SHA-256
rzeczywiście odczytanego źródła i wszystkie odpowiedzi OCR, bez czasów i
pamięci. Raport nie tworzy runu, katalogu `cut` ani JPEG-a i odmawia nadpisania
istniejącego pliku raportu.

Pomiar z 2026-09-21 obejmuje pięć JPEG-ów (po jednym z `777`, częściowo
przysłoniętego `777`, `blazing`, `gang` i `tresure`). Profile 1/2/4 mają ten
sam digest `26ddad7be83be5065a6ff1409e7c86a09f7c33e1057b8ef021360a4fb1989e29`.
Najlepszy profil 4/8 uzyskał 777,5305 ms dla pięciu źródeł, 6,4306 źródeł/s i
3 668,5503 ms cold end-to-end z kontrolą manifestu oraz inicjalizacją modelu.
Paddle 3.3.1 jest nadal CPU-only; VRAM ma uczciwy status
`unavailable_cpu_runtime`. Pełne dane są w
`ai_docs/quality/V7_T11_RUNTIME_PERFORMANCE.json`.

Weryfikacja: `16 passed` dla scheduler/runtime/benchmark tests, Ruff i mypy
bez błędów oraz `json.tool` dla raportu. Self-audyt i review Astra Medium
wykryły trzy P2 (dodatkowy żywy payload, zbyt słaby digest i rozbieżny default
polityki); wszystkie naprawiono testami regresyjnymi i ponownie zweryfikowano.

T11 nie kalibruje OCR, nie aktywuje V7 ani nie jest odbiorem T12. Parametry
4/8 są wartością początkową zmierzoną na ograniczonym korpusie, a nie obietnicą
wydajności dla pełnych przyszłych katalogów.
