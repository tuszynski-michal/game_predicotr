---
title: Real range OCR regression corpus v1
status: active
last_updated: 2026-09-02
---

# Rzeczywisty korpus regresyjny OCR zakresów v1

Korpus utrwala cztery redagowane zdjęcia dostarczone przez operatora. Ich
neutralne nazwy oraz usunięcie panelu Admina z tekstem `seq_*` sprawiają, że
żaden wynik nie może pochodzić z nazwy pliku ani tekstu interfejsu.

| Fixture | Ocena człowieka | Kontrakt regresji |
| --- | --- | --- |
| `screen-a.jpg` | czytelny `64–72` | przyszły runtime musi umieć uzyskać wyłącznie ten zakres albo jawne `unknown` |
| `screen-b.jpg` | czytelny `55–63` | analogicznie |
| `screen-c.jpg` | czytelny `28–36` | analogicznie |
| `transition-d.jpg` | przejście `124130–124138` ↔ `124139–124147` | nigdy nie może otrzymać automatycznego `exact` |

Korpus jest bramką regresji i diagnostyki przyczyny, nie reprezentatywnym
benchmarkiem recall. Runner `scripts/run_range_ocr_real_regression_corpus.py`
wywołuje jedynie EXIF canonicalization, lokalizator etykiet i Paddle OCR.
Nie wolno mu uruchamiać detekcji plansz, geometrii, croppera ani inferencji
symboli.

## Baseline historycznych runtime'ów

Wynik realnego przebiegu jest utrzymywany poza repozytorium w
`artifacts/quality/range-ocr-real-regression-v1.json`; zapisuje status oraz
reason codes v2, v3, v4.1 i v5 dla każdego fixture’u. Nie jest automatycznie
interpretowany jako zgoda na aktywację runtime'u.

| Runtime | Trzy czytelne ekrany | Klatka przejściowa | Dominujący reason code |
| --- | --- | --- | --- |
| v2 | 0 / 3 exact | `unknown` | `RANGE_LABEL_LATTICE_INCOMPLETE` |
| v3 | 0 / 3 exact | `unknown` | `RANGE_LABEL_LATTICE_INCOMPLETE` |
| v4.1 | 0 / 3 exact | `unknown` | `UNKNOWN_LATTICE` |
| v5 | 0 / 3 exact | `unknown` | `COMPLETE_ROW_UNVERIFIED` |

Wynik jest diagnostyką punktu wyjścia: historyczne warianty bezpiecznie nie
tworzą false positive dla przejścia, ale nie spełniają wymaganego coverage na
czytelnych ekranach. TASK-0403 może stroić nowy fingerprint wyłącznie na
podstawie jawnie oddzielonego zestawu tuningowego; korpus pozostaje bramką
regresji.
