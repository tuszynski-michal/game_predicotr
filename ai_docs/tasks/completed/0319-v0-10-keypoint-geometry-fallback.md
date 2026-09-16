---
title: TASK-0319 — eksperymentalny fallback geometrii keypoint
status: done
version: 0.10.12
last_updated: 2026-08-29
---

# Cel

Dodać mały, lokalny model heatmap przewidujący cztery narożniki każdego z
dziewięciu slotów strony jako eksperymentalne źródło inicjalizacji geometrii.
Wynik nadal przechodzi przez wspólny lokalny refiner i wszystkie istniejące
hard gates. Integracja pozostaje wyłącznie shadow i nie może zmienić primary
wyniku ani stanu rolloutu gry.

# Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md` — D-254–D-261
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/quality/V0_10_VIRTUAL_GEOMETRY_CUTOVER.md`

# Warunek uruchomienia

Zaakceptowany plan przewidywał implementację dopiero po wyniku `<95%`.
TASK-0318 zakończył się `insufficient_evidence`, więc automatyczna bramka nie
została spełniona. Bezpośrednie polecenie właściciela z 2026-08-29 jest jawną
decyzją o wykonaniu bounded eksperymentu mimo braku raportu. Nie jest to zgoda
na aktywację, trening na danych użytkownika ani zmianę produkcyjnego rolloutu.

# Zakres

- wersjonowany kontrakt ręcznie zatwierdzonego źródła treningowego;
- deterministyczny, source-family-disjoint split;
- mały model PyTorch zwracający `9 × 4` heatmaps i obecność dziewięciu slotów;
- deterministyczne targety heatmap oraz bounded trening CPU;
- eksport ONNX z weryfikacją kontraktu i zgodności PyTorch–ONNX;
- checksum-bound adapter ONNX Runtime używający wyłącznie CPU;
- dekodowanie narożników z jawną active-slot maską wynikającą z `seq_*`;
- `KeypointGeometryEngine` używający wspólnego `SourceGeometryResult`,
  lokalnego line refiner i istniejących walidatorów;
- jawny shadow runner, który nigdy nie zastępuje primary wyniku;
- ograniczony pomiar czasu CPU bez benchmarku dużego zbioru.

# Poza zakresem

- aktywacja per gra, nowe tryby w bazie i migracja;
- podłączenie do produkcyjnego `production_workflow`;
- operacyjny trening na zdjęciach użytkownika;
- segmentacja, Ultralytics, maski i GPU;
- zmiana Structured OpenCV, symbol classifiera, canonical ownership lub review;
- tworzenie trwałych cropów albo nowych binariów domenowych.

# Invarianty

- tylko ręcznie zatwierdzone quady mogą wejść do manifestu treningowego;
- źródło lub source family nie występuje w więcej niż jednym splicie;
- nieaktywne sloty nie są syntetyzowane ani przekazywane do refinerów;
- niepełna obecność lub nieprawidłowy quad kończy się fail-closed;
- ONNX używa wyłącznie CPU i jest związany checksumą;
- finalny wynik przechodzi przez te same hard gates co Structured OpenCV;
- shadow nie zmienia primary result ani stanu gry.

# Testy odbiorcze

- odrzucenie nie-ręcznej próbki i wycieku źródła między splitami;
- deterministyczny manifest i target heatmap;
- active prefix `1..9`, ignorowanie nieaktywnych slotów i brakujący aktywny slot;
- golden dekodowania czterech narożników;
- ONNX contract i parity;
- CPU timing po warm-upie;
- wspólna walidacja finalnego `GeometryResult`;
- shadow nie może wskazać automatycznej promocji primary wyniku.

# Commit

`v0.10.12 - add keypoint geometry fallback`

# Outcome

- Dodano niezależny pakiet `images/keypoint_geometry` z wersjonowanym kontraktem
  ręcznie zatwierdzonych źródeł, deterministycznym source-family-disjoint
  splitem i checksum-bound loaderem zarządzanych JPEG-ów. Dataset wymaga co
  najmniej trzech rodzin, aktywnego prefiksu slotów i kompletnego quada dla
  każdego aktywnego slotu.
- Mały model PyTorch zwraca `9 × 4` heatmaps i dziewięć logitów obecności.
  Bounded trening CPU korzysta wyłącznie ze splitu train, ma stały seed i
  deterministyczne heatmap targets.
- Eksport ONNX opset 18 ma stały kontrakt tensorów. Lokalny adapter ponownie
  sprawdza checksumę, używa wyłącznie `CPUExecutionProvider`, waliduje kształty
  i fail-closed odrzuca brak aktywnego slotu, słaby narożnik lub zły quad.
- Structured OpenCV oraz fallback keypoint korzystają ze wspólnej funkcji
  `refine_initialized_source_geometry`, a więc z tego samego line refiner,
  walidacji cross-slot i hard gates. Regresja istniejącego silnika przechodzi.
- Dodano manifest wydania łączący dataset, konfigurację treningu, ONNX parity i
  bounded CPU timing. Manifest ma niezmienne `shadowOnly=true` oraz
  `activationAllowed=false`.
- `KeypointGeometryShadowRunner` nie ma ścieżki promocji i nie jest podłączony
  do produkcyjnego workflow, API, rolloutu gry ani operacyjnego treningu. Nie
  dodano migracji i nie zapisano nowych binariów domenowych.
- D-262 utrwala, że bezpośrednie polecenie właściciela pozwoliło wykonać
  eksperyment mimo `insufficient_evidence`, ale nie uchyla D-261 ani nie zezwala
  na aktywację.

## Weryfikacja

- testy datasetu, treningu, ONNX, CPU timing i engine shadow: `12 passed`;
- regresja Structured OpenCV i dwóch produkcyjnych ścieżek geometrii:
  `20 passed`;
- Ruff dla zmienionego kodu i testów: pass;
- Ruff format check dla zmienionego kodu i testów: pass;
- celowany mypy dla dziewięciu modułów: pass;
- OpenAPI i wygenerowany klient Admina: pass, bez zmian kontraktu;
- `git diff --check`: pass;
- eksport ONNX emituje jedno ostrzeżenie `FutureWarning` z zależności PyTorch;
  nie wpływa ono na wynik parity ani wykonanie CPU.

Nie uruchomiono benchmarku dużego zbioru, treningu na danych użytkownika,
zmiany rolloutu ani produkcyjnego pipeline'u. Każda z tych operacji wymaga
osobnego, jawnie zaakceptowanego zadania i rzeczywistego raportu jakości.
