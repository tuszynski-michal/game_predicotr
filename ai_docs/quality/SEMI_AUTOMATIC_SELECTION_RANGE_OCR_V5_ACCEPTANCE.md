---
title: Row-first range-only OCR v5 acceptance
status: accepted
last_updated: 2026-09-01
---

# Odbiór row-first range-only OCR v5

Wariant: `semi-automatic-range-only-ocr-v5-row-first-v1`
Decyzja: **rollout odrzucony; v5 pozostaje wyłączony.**

## Metoda

Odbiór użył wyłącznie dwóch wcześniej zamrożonych, checksum-bound manifestów
v4.1 z rzeczywistego katalogu `E:\blazing zd\blazing 21400`:

- challenge: 19 źródeł, 16 czytelnych i 3 nieczytelne;
- frozen golden: 100 źródeł, 99 czytelnych i 1 ambiguous.

Harness odczytuje pliki, porównuje ich rozmiar i SHA-256 z manifestem, a wynik
zapisuje w oddzielnym JSON-ie. Nazwa, katalog i source index identyfikują tylko
bajty — nie uczestniczą w dowodzie ani oczekiwanym zakresie. Nie zostały
zmienione źródła, staging, joby, baza, v1–v4.1 ani domyślny recognizer.

## Wyniki

| Zestaw | Exact | False exact | Readable coverage | Group capture | Wybrane | Scan | Źródła/s |
|---|---:|---:|---:|---:|---:|---:|---:|
| Challenge 19 | 0 | 0 | 0% | 0% | 0 | 22,17 s | 0,86 |
| Frozen golden 100 | 0 | 0 | 0% | 0% | 0 | 102,05 s | 0,98 |

Nie było wybranych reprezentantów, więc wymagane kompletne ręczne review nie
może potwierdzić selected range precision ani own proof. Brak false exact jest
poprawnym zachowaniem fail-closed, lecz nie jest wystarczający do rolloutu.

## Diagnostyka

| Zestaw | Dominujące reason codes | OCR calls | OCR crops | OCR inference |
|---|---|---:|---:|---:|
| Challenge 19 | `COMPLETE_ROW_UNVERIFIED=19` | 5 | 225 | 27,22 s |
| Frozen golden 100 | `COMPLETE_ROW_UNVERIFIED=85`, `UNKNOWN_ROWS=11`, `FINAL_PROOF_INSUFFICIENT=4` | 18 | 777 | 90,17 s |

Wynik wskazuje, że rzędy wykryte przez lokalizator nie są następnie
rozpoznawane jako kompletne, zgodne trójki. Nie zmieniano progu ani proof na
podstawie tych wyników: oba zbiory są holdoutem.

## Bramy

| Bramka | Wynik |
|---|---|
| Tylko `exact`/`unknown`, v5 fingerprint i recognition-only OCR | PASS |
| Checksum-bound źródła, bez inferencji z nazwy lub indeksu | PASS |
| Zero false exact | PASS |
| Readable coverage ≥ 50% | **FAIL — 0%** |
| Group capture ≥ 90% | **FAIL — 0%** |
| Wybrane zakresy: kompletne review, 100% own proof i precision | **FAIL — brak wyborów** |
| V5 jako domyślny recognizer | **NIEAKTYWNY** |

## Artefakty

- `row-first-range-ocr-v5-challenge-report.json`
- `row-first-range-ocr-v5-golden-report.json`

Kolejna iteracja może powstać wyłącznie jako nowy wariant i fingerprint,
wytrenowany na rozłącznym zbiorze oraz odebrany na nowym holdoucie. Nie należy
poluzowywać obecnego v5 ani zmieniać aktywnego v3.
