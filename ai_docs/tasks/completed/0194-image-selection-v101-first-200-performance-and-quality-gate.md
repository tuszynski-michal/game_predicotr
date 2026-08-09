---
title: TASK-0194 v10.1 first 200 performance and quality gate
status: done
release: "0.4"
last_updated: 2026-08-08
---

# TASK-0194 — V10.1 first-200 performance and quality gate

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/tasks/completed/0193-image-selection-deterministic-parallel-verification.md`

## Goal

Powtórzyć izolowany profil indeksów 0–199 i zdecydować, czy można przejść do
ręcznego runu około 5000/32 000.

## Baseline

- 377,530649 s,
- 9 grup,
- 99 pełnych weryfikacji,
- 792 batche i 7128 cropów OCR,
- brak błędów skanu.

## Likely files

- `scripts/profile_image_selection_slice.py`
- `artifacts/image-selection-v10-first-200-timing.json`
- dokumentacja quality/current state

## Proposed solution

- uruchomić ten sam staging, kolejność, limit 200 i cold-cache policy,
- porównać granice, zakresy, checksumy reprezentantów i telemetry,
- obejrzeć każdy zmieniony reprezentant,
- zapisać decyzję `accepted | optimize | rejected`.

## Verification

- pierwszy cel: 113–151 s, czyli 60–70% krócej,
- brak regresji zakresów i jakości reprezentantów,
- raport pokazuje poziomy adaptacyjne oraz anchored/fallback,
- pełny run nie startuje automatycznie.

## Dependencies

- TASK-0188–0193.

## Open questions

Brak. Właściciel wybrał `optimize` 2026-08-08.

## Outcome

Profil wykonano 2026-08-08 na indeksach 0–199 stagingu 32 079 zdjęć, bez cache,
publikacji i zapisu domenowego. Harness został najpierw zaktualizowany do
aktualnego fingerprintu v10.1, batchowego `verify_many`, pomiaru peak RSS oraz
diagnostyki reprezentantów.

| Wariant | Czas | Zmiana vs v10 | Peak RSS | Zakresy |
|---|---:|---:|---:|---|
| v10 baseline | 377,530649 s | — | brak pomiaru | 9/9 |
| v10.1, 2 verifiery | 366,322600 s | -2,97% | 457 359 360 B | 8/9 |
| v10.1, 1 verifier | 310,859984 s | -17,66% | 457 039 872 B | 8/9 |

Oba warianty zachowały dziewięć identycznych granic grup i zero błędów skanu.
V10.1 ograniczył koszt do 35 weryfikacji dowodu zakresu, 249 wywołań OCR i 2211
cropów wobec baseline 99, 792 i 7128. Koszt pełnej oceny reprezentanta pozostał
jednak na 99 kandydatach. Dwa równoległe verifiery spowodowały konkurencję
Paddle/OpenCV i były wolniejsze od jednego; produkcyjny lane wrócił dlatego do
jednego verifiera i trzech scan workers przy budżecie czterech.

Grupa indeksów 159–180 nie uzyskała dowodu OCR dla zakresu 55–63 i poprawnie
trafiła do `manual_required`. Historyczny v10 raportował 55–63 przez
odziedziczony cursor ciągłości. V10.1 nie może przywrócić tego zgadywania,
ponieważ poprawny skok zakresu musi pozostać dozwolony. Pozostałe osiem zakresów
jest zgodne z baseline.

Pierwszy cel 113–151 s nie został osiągnięty. Właściciel jawnie wybrał
`optimize` 2026-08-08. Bramka TASK-0194 jest zamknięta tym wynikiem, run
5000/32 000 pozostaje wstrzymany, a kolejny pion ma poprawić niezależny dowód
OCR dla grupy 55–63 oraz ograniczyć koszt pełnej geometrii bez przywracania
zgadywanej ciągłości zakresów.

Raporty robocze:

- `artifacts/image-selection-v101-first-200-timing-v2.json` — dwa verifiery,
- `artifacts/image-selection-v101-first-200-timing-v3-single-verifier.json` —
  jeden verifier.

## Powtórka po TASK-0195 i TASK-0196 — 2026-08-08

Na polecenie właściciela TASK-0194 powtórzono na bieżącym kodzie z adapterem
zakresu v6 i dokładną optymalizacją geometrii opartą na sumie integralnej.
Profil użył tego samego stagingu, indeksów `0–199`, cold-cache, trzech scan
workers, jednego verifiera oraz trybu read-only bez publikacji i zapisu
domenowego.

| Pomiar | Czas | Zmiana vs v10 | Grupy | Peak RSS |
|---|---:|---:|---:|---:|
| v10 baseline | 377,530649 s | — | 9 | brak pomiaru |
| pierwszy profil po TASK-0196 | 91,714346 s | -75,71% | 9 | brak porównywalnego odczytu |
| powtórka TASK-0194 | 109,111404 s | -71,10% | 9 | 449 204 224 B |

Powtórka zachowała dokładnie te same granice dziewięciu grup, zakresy `1–9`
do `73–81` oraz checksumy wszystkich dziewięciu reprezentantów co pierwszy
profil po TASK-0196. Grupa indeksów `159–180` nadal zwraca `55–63` i reprezentant
`1/1_010522.jpg`. Liczba błędów skanu wyniosła zero.

Telemetria powtórki: 99 pełnych ocen geometrii, 19 weryfikacji dowodu zakresu,
118 wywołań OCR i 1050 cropów OCR. Różnica czasu względem pierwszego profilu po
TASK-0196 wynosi +18,97%, ale wynik nadal spełnia pierwotny cel 113–151 s i
potwierdza deterministyczną jakość. Raport:
`artifacts/image-selection-v101-first-200-task0194-repeat.json`.
