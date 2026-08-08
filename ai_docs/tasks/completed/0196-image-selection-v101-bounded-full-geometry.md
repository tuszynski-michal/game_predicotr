---
title: TASK-0196 exact full-geometry cost optimization for image selection v10.1
status: done
release: "0.4"
last_updated: 2026-08-08
---

# TASK-0196 — Exact full-geometry cost optimization for image selection v10.1

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/tasks/completed/0194-image-selection-v101-first-200-performance-and-quality-gate.md`
- `ai_docs/tasks/completed/0195-image-selection-independent-range-evidence-55-63.md`

## Goal

Ograniczyć dominujący koszt pełnej geometrii kandydatów v10.1 bez pogorszenia
granic grup, wyboru reprezentanta, lokalnego dowodu OCR ani obsługi skoków
zakresów.

## Problem

Profil TASK-0194 wykonał pełną geometrię dla 99 kandydatów. Po ograniczeniu OCR
to detekcja plansz stała się dominującym kosztem: na problematycznej grupie
55–63 zajęła 19,922492 s z 25,701488 s całego profilu.

## Likely files

- `services/worker/src/game_predictor_worker/images/geometry.py`
- `services/worker/src/game_predictor_worker/images/selection/adapters.py`
- `services/worker/src/game_predictor_worker/images/selection/manifest.py`
- `services/worker/src/game_predictor_worker/images/selection/job.py`
- `services/worker/src/game_predictor_worker/cli.py`
- `services/worker/tests/test_image_selection_adapters.py`
- `services/worker/tests/test_fast_image_selector.py`
- `scripts/profile_image_selection_slice.py`

## Proposed solution

Pomiar rozdzielczości odrzucił skalowanie i crop wejścia: oba warianty zmieniały
wynik detekcji na realnych zdjęciach. Profil funkcji wskazał zamiast tego około
163 tys. wywołań `numpy.mean` i 82 tys. alokacji masek podczas przesuwania okna
refinementu.

- zastąpić powtarzane skanowanie prostokątnych obszarów dokładną sumą
  integralną maski binarnej,
- zachować identyczne liczniki border/interior, krok wyszukiwania, tie-break i
  zaokrąglenie confidence,
- zachować pełną rozdzielczość wejścia, top-12 i wszystkie zdjęcia lekkiego
  scoringu,
- nie zmieniać manifestu ani fingerprintu, jeżeli wynik detektora pozostaje
  bajtowo identyczny,
- potwierdzić parity checksumą kanonicznych wyników przed ponownym profilem.

## Verification

- wynik detektora ma identyczny kanoniczny hash na rzeczywistym wycinku,
- test jednostkowy porównuje sumę integralną z dotychczasowym liczeniem maski,
- historyczny fingerprint v6 pozostaje rozwiązywalny,
- grupa indeksów 159–180 nadal wybiera ten sam checksum i zakres 55–63,
- profil 0–199 zachowuje dziewięć granic oraz dziewięć rozpoznanych zakresów,
- raport porównuje czas i telemetry z 310,859984 s TASK-0194,
- Ruff, mypy oraz skupione testy workera i API przechodzą,
- run 5000/32 000 nie startuje automatycznie.

## Dependencies

- TASK-0194 zakończony decyzją `optimize`.
- TASK-0195 zakończony poprawnym lokalnym dowodem zakresu 55–63.

## Open questions

Brak pytań produktowych. Skalowanie i crop zostały odrzucone; zysk czasu nie
może przesłonić regresji geometrii lub OCR.

## Outcome

Zwykłe skalowanie oraz crop obrazu zostały odrzucone: wariant 1280 px zmienił
wynik semantyczny 14/22 realnych zdjęć. CProfile wskazał rzeczywistą przyczynę
kosztu: 163 194 wywołania `numpy.mean` i 81 769 alokacji masek w przesuwanym
oknie refinementu.

Dodano dokładną sumę integralną binarnej maski. Border i interior zachowują te
same liczności, wzór scoringu, krok, kolejność oraz tie-break. Kanoniczny hash
pełnych wyników 22 zdjęć pozostał równy
`2f7397d516eda85f9ac4f05ff2df2f3e9a971298f6865fec5c3f51c59238806c`,
przy spadku czasu detektora z 8,720996 s do 1,862312 s. Manifest i fingerprint
nie zmieniły się.

Celowany profil 55–63 trwał 9,245810 s zamiast 25,701488 s, zachowując zakres i
checksum reprezentanta. Powtórny cold profile 0–199 trwał 91,714346 s:
70,497% krócej od v10.1 TASK-0194 i 75,707% krócej od baseline v10. Wszystkie
dziewięć granic i zakresów 1–9…73–81 jest poprawne, osiem wcześniej
rozstrzygniętych reprezentantów nie zmieniło się, a liczba błędów skanu wynosi
zero. Geometria 99 kandydatów spadła z 170,748913 s do 35,158739 s.

Weryfikacja: Ruff, mypy oraz 130 skupionych testów workera przeszły. Pełny run
5000/32 000 pozostał wstrzymany do ręcznej bramki właściciela.
