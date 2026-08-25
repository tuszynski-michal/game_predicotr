---
title: Verified v19 symbol residual cohort
status: accepted
last_updated: 2026-08-23
---

# Kohorta pozostałych błędów modelu symboli v19

## Cel i granica eksperymentu

TASK 8 oddziela błędy aktywnego modelu symboli od błędów etykiet i geometrii
na niezmiennej kohorcie poprawnych cropów v19. Operacja jest read-only wobec
bazy, decyzji review i aktywacji modelu. Nie uruchamia treningu, eksportu ani
promocji kandydata.

Źródłem konfiguracji jest
`ai_docs/quality/v19-symbol-residual-cohort.json`. Descriptor przypina grę,
sześć stagingów, aktywny model, jego dataset treningowy, seed splitu oraz
checksumy wynikowych artefaktów.

## Niezmienna kohorta

- checksum manifestu:
  `eaa368b5fd6671103c1e2e65ff06ada082a08da0d47a09ea48f629791523ab88`,
- 321 plansz `accepted/corrected`, 4815 cropów i 41 rodzin źródeł,
- dokładnie sześć stagingów: `1-19809`, `test`, `19810 - 45162`,
  `45163 - 70371`, `70363 - 93861` i `93853 -117828`,
- 251 plansz korzysta z checksum-verified zapisanych cropów v19, a 70 zostało
  odtworzonych read-only przez ten sam fail-closed estymator i cropper v19,
- każda plansza zawiera dokładnie 15 komórek row-major,
- split `source-family-balanced-split-v2` ma 38 rodzin train oraz po jednej
  validation, test i regression, bez przecieku źródła,
- 12 plansz z jednoznacznym wizualnym konfliktem etykiety lub pozycji zostało
  wykluczonych jako całe plansze; 10 plansz spoza sześciu przypiętych stagingów
  również nie weszło do kohorty.

Audytowane konflikty obejmują sekwencje `15`, `54`, `118`, `19814`, `19816`,
`19817`, `19835`, `70369`, `70377`, `70384`, `70388` i `93859`. Descriptor
przechowuje checksumy cropów stanowiących dowód. Builder sprawdza, że każdy
dowód nadal należy do cropów wskazanej planszy; drift albo brak planszy blokuje
odtworzenie. Konflikty mają klasyfikację `OPEN` i nie są traktowane jako błąd
modelu ani przykład przyszłego treningu.

## Wynik aktywnego modelu

Raport:
`c617fdf461fa4e9a56d5bebc96a01f01ab3e3b3348c46670a731613c5d07d3cc`.

| Miara | Wynik |
| --- | ---: |
| Accuracy symboli | 99,3354% (4783/4815) |
| Błędy symboli | 32 |
| Accuracy całych plansz | 94,3925% |
| Accuracy na rodzinach widzianych w treningu | 99,6721% |
| Accuracy na nowych rodzinach | 99,2564% |
| Parity preprocessingu trening/ONNX | 4815/4815 |

Recall każdej klasy przekracza 98,46%. Najniższy wynik ma `plum`:
`98,4642%` przy wsparciu 586 próbek. Macierz pomyłek, metryki per staging,
source exposure i wszystkie błędy confidence co najmniej 0,99 znajdują się w
niezmiennym raporcie JSON.

## Klasyfikacja residuali i decyzja

- `M2`: `plum -> grapes`, 9 błędów z dwóch nowych rodzin źródeł, w tym 6 z
  confidence co najmniej 0,99. Audyt cropów potwierdził rzeczywiste warianty
  śliwki, a nie przesunięcie komórki. Błąd przekracza wersjonowaną bramkę 1%
  wsparcia klasy.
- `OPEN`: 12 plansz z konfliktami ręcznej etykiety lub slotu, 27 cropów
  dowodowych. Są wykluczone z metryk modelu i wymagają osobnej korekty danych.
- `P1`: brak; preprocessing produkcyjny i treningowy jest bitowo zgodny dla
  wszystkich 4815 próbek.
- `M1`: brak istotnego residualu spełniającego bramkę na źródłach widzianych
  w treningu.

Decyzja raportu to **`retrain`**, ponieważ powtarzalny residual M2 przekracza
bramkę. TASK 8 nie uruchamia treningu. Nowa iteracja może powstać dopiero w
osobnym zadaniu, z zachowaniem dotychczasowej jawnej bramki i aktywacji.

## Odtworzenie

```powershell
.venv\Scripts\python.exe scripts\build_v19_symbol_residual_cohort.py --check
.venv\Scripts\python.exe scripts\evaluate_v19_symbol_residuals.py --check
```

Obie komendy ponownie weryfikują bazę, aktywny snapshot modelu, dataset
treningowy, źródła, cropy i content-addressed wyniki. Zmiana któregokolwiek
przypiętego wejścia kończy się stabilnym błędem driftu.
