---
title: Semi-automatic range OCR v3 performance acceptance
status: accepted
last_updated: 2026-09-01
---

# Odbiór wydajności `range-only OCR v3`

## Bezpieczeństwo i jakość

V3 zachowuje recognizer v2 dla każdej próby i dodaje wyłącznie scheduler.
Checksummowany golden dał:

| Próba | Exact | Fałszywe przypisania | Czas pełnego OCR |
|---|---:|---:|---:|
| 10 | 7 | 0 | 13,451 s |
| 100 | 68 | 0 | 180,607 s |

Różnica czasu pełnego OCR względem poprzedniego odbioru wynika z bieżącego
obciążenia komputera; ścieżka produkcyjna v3 nie OCR-uje całego wejścia.
Geometria, cropper i symbol inference miały po zero wywołań.

## Kalibracja schedulera

Na pierwszych 500 rzeczywistych JPEG-ach sam checksumming, draft thumbnail i
deskryptor wykonały się w `14,551 s` (`34,36 JPEG/s`). Próg historyczny
`0.004` kierował do OCR 68,8% zdjęć. Próg `0.08` wraz z obowiązkowym interwałem
pięciu źródeł ograniczył udział do 24,2%; nie osłabia to proof, ponieważ
deskryptor nie przypisuje numeru.

## Pełne pomiary

| Korpus | Źródła | Próby OCR | Czas | Przepustowość |
|---|---:|---:|---:|---:|
| 10 rzeczywistych goldenów × 10 kolejnych ujęć | 100 | 20 | 30,325 s | 3,30 JPEG/s |
| rzeczywisty fragment surowego katalogu od indeksu 9900 | 200 | 40 | 27,403 s | 7,30 JPEG/s |

Pierwszy pomiar zawiera kosztowne, czytelne etykiety i potwierdził 14 exact
prób odpowiadających 7/10 rozpoznawalnych goldenów. Drugi jest pomiarem
przepustowości rzeczywistych klatek; badany fragment nie dał strong proof i
pozostał luką, zgodnie z fail-closed.

Dla 42 000 zdjęć daje to około `1 h 36 min` przy 7,30 JPEG/s albo około
`3 h 32 min` przy 3,30 JPEG/s. Nie jest to obietnica dla każdego katalogu:
udział mocnych zmian i koszt dysku pozostają zależne od źródła.

## Recovery

Scheduler zapisuje fingerprint i source index razem z groupingiem. Test
pause/restart potwierdził próby `0,5`, wznowienie od `10`, brak powtórzenia OCR
zatwierdzonego prefiksu oraz końcowe liczniki `3 probed / 8 skipped`.
