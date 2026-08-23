---
title: Board cell geometry v19 cross-staging shadow benchmark
status: accepted
last_updated: 2026-08-23
---

# Board cell geometry v19 cross-staging shadow benchmark

## Cel i zakres

TASK 2 mierzy niezmieniony produkcyjny estymator v19 oraz source-direct cropper
w trybie wyłącznie do odczytu. Benchmark nie zapisuje decyzji, nie zmienia
jobów, nie aktywuje modelu i nie uruchamia treningu.

Kohorta główna zawiera dokładnie 300 stron: po 50 deterministycznie wybranych
stron z sześciu przypiętych manifestów geometrii. Daje to 2700 plansz, a każda
pozycja strony 0–8 występuje dokładnie 300 razy. Challenge jest przypięty do
niezmiennego raportu TASK 1 i zawiera 81 bieżących ręcznie poprawionych plansz;
trzy historyczne rewizje zostały jawnie wykluczone.

Źródłem konfiguracji jest
`ai_docs/quality/board-cell-geometry-v19-shadow-benchmark.json`. Benchmark
waliduje checksumy manifestów, źródeł, raportu TASK 1 i aktywnego modelu przed
wykonaniem obliczeń. OpenCV działa w pojedynczym deterministycznym lane, a
diagnostyczne współrzędne i residuale są kwantyzowane wyłącznie w raporcie na
poziomie znacznie dokładniejszym od progów odbiorczych. Produkcyjna geometria
nie jest modyfikowana.

## Niezmienne artefakty

- manifest: `8640084933f74586e2a429120ac29835c7e7fa20d9ac52d91c9c2f271c22473f`,
- indeks galerii: `ac6b106c8755d9b274d4d136571fbcc1a783e162c0c02314d6436de9ab940c01`,
- galeria: 300 overlayów stron, 75 arkuszy kontaktowych i 81 overlayów
  challenge,
- przykładowy raport czasu: `45bee6d437680d54ddadde18568892583595a416a0fa1a64e9b20d4dd8b2c8dd`.

Raport czasu jest osobnym artefaktem, ponieważ obciążenie komputera nie może
zmieniać checksumy manifestu jakościowego. Dwa niezależne zapisy oraz osobny
przebieg `--check` odtworzyły tę samą checksumę manifestu.

## Wynik

| Miara | Wynik | Bramka | Status |
| --- | ---: | ---: | --- |
| Automatyczne pokrycie 2700 plansz | 93,78% (2532/2700) | ≥98% | FAIL |
| Kontrolowane odroczenia | 168 | — | informacja |
| Katastrofalne przesunięcia w auto-success challenge | 0/76 | 0 | PASS |
| Symbol accuracy challenge | 95,61% | ≥95% | PASS |
| Whole-board accuracy challenge | 73,68% | ≥70% | PASS |
| Średni błąd narożników komórek | 1,95 px | diagnostyczna | PASS |

Pokrycie per staging:

| Staging | Auto-success | Pokrycie |
| --- | ---: | ---: |
| `1-19809` | 443/450 | 98,44% |
| `19810 - 45162` | 424/450 | 94,22% |
| `45163 - 70371` | 406/450 | 90,22% |
| `70363 - 93861` | 415/450 | 92,22% |
| `93853 -117828` | 422/450 | 93,78% |
| `117829 - 128268` | 422/450 | 93,78% |

Najsłabsze pozycje to lewa górna (`86,67%`) oraz prawa górna i prawa dolna
(`90,33%`). Najczęstsze kontrolowane przyczyny odroczeń to niewystarczające
pokrycie inlierów (`71`) i nieudane przypisanie osi (`65`). Żadna odroczona
plansza nie przekazała częściowych cropów do inferencji.

Przekrojowy audyt arkuszy ze wszystkich stagingów potwierdził, że zielone
wyniki automatyczne obejmują symbole, a czerwone przypadki są odraczane bez
fałszywego sukcesu. Porównanie challenge pokazało zgodność automatycznej
geometrii z ręczną i zero przesunięć o cały wiersz lub kolumnę. Pełna galeria
pozostaje dostępna do niezależnego review właściciela.

## Decyzja checkpointu

**Odrzucono aktywację i przejście do następnego etapu.** Jakość trafień
automatycznych spełnia bramki, lecz pokrycie 93,78% nie spełnia wymaganego 98%.
TASK 2 dostarcza powtarzalny benchmark i dowód wyniku, ale nie upoważnia do
zmiany produkcyjnego pipeline'u ani rozpoczęcia TASK 3.

Późniejsze jawne polecenie właściciela dopuściło implementację pełnego adaptera
v20 wyłącznie jako staging-local opt-in z trwałym deferred. Nie zmieniło
wyniku tego checkpointu: v18 pozostaje domyślny, bramka `98%` nie została
obniżona, a automatyczny rollout nadal jest odrzucony.

## Odtworzenie

```powershell
.venv\Scripts\python.exe scripts\run_board_cell_geometry_shadow_benchmark.py `
  --source-root "C:\Users\user\Documents\777"

.venv\Scripts\python.exe scripts\run_board_cell_geometry_shadow_benchmark.py `
  --source-root "C:\Users\user\Documents\777" `
  --check
```

`--check` nie zapisuje nowych artefaktów. Odczytuje źródła i bazę tylko po to,
aby potwierdzić, że przypięta kohorta TASK 1 oraz jej wynik nadal są odtwarzalne.
