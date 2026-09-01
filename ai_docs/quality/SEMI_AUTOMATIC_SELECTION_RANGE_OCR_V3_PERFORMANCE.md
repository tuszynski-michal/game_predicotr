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

## Rozszerzony odbiór 1000 + 1000

Test wykonano 2026-09-01 na dwóch rzeczywistych korpusach. Czas inicjalizacji
Paddle nie należy do `elapsedSeconds`; obejmuje on checksumming, thumbnail,
deskryptor, pełny decode zaplanowanych prób i OCR.

| Próba | Źródła | Próby OCR | Mocny/zaakceptowany dowód | Czas | JPEG/s |
|---|---:|---:|---:|---:|---:|
| trudna: 1000 różnych zatwierdzonych `seq_*` | 1000 | 205 | 138 | 421,802 s | 2,37 |
| łatwa: 1000 kolejnych, poprawnie ustawionych surowych kadrów | 1000 | 201 | 141 | 475,335 s | 2,10 |

Trudna próba miała oracle w nazwach plików. Końcowa bramka zaakceptowała 138
dokładnych zakresów, odrzuciła 23 surowe niekanoniczne hipotezy i nie dopuściła
żadnego błędnego automatycznego przypisania. Jest to celowo skrajny, gęsty
strumień, w którym każde kolejne zdjęcie przedstawia inny zakres; 795
pominiętych źródeł ujawnia ograniczenie recall schedulera dla grup krótszych
niż wymuszony interwał.

Łatwa próba pochodzi z `E:\blazing zd\blazing 21400`, offset `9000`. Numery są
czytelne i obraz jest prawidłowo ustawiony. Mocny dowód uzyskało 141 z 201 prób
OCR. Brak oracle dla pozostałych surowych klatek nie pozwala wyliczyć pełnego
precision/recall grupowania, dlatego wynik opisuje skuteczność prób, nie
końcowych wyborów.

Checksummy manifestów wejściowych:

- trudny: `51f53047ed1a4699a3999c2c9ec6aa72f5b2e2fa0ca829b0ec98f6e84a0a374c`;
- łatwy: `2b19fe63a05d53d7ba704e394f8e5391e192028256b45ec05aa5bf2003f89802`.

Fingerprint recognizera obu prób:
`61e35b0653fe0787b352fcf9c4670edae28f020eed3e20f35acdadeae355dd8e`.

### Diagnostyka orientacji

Pierwotny kandydat łatwej próby z `E:\blazing zd\blazing od 1`, offset `9900`,
okazał się fizycznie obrócony o 180 stopni bez użytecznej informacji EXIF.
Scheduler osiągnął `8,20 JPEG/s`, lecz `0/203` prób dało strong proof. Kontrola
wykonująca OCR na wszystkich 1000 źródłach również dała `0/1000`, więc brak
dowodu nie wynikał z harmonogramu. Obecny `ImageOps.exif_transpose` nie może
naprawić orientacji niezapisanej w metadanych.

### Wnioski wydajnościowe

- cel minimum `2 JPEG/s` został spełniony w obu właściwych próbach;
- cel `3–6 JPEG/s` dla łatwego, użytecznego materiału nie został spełniony;
- w łatwej próbie OCR zajął `407,503 s` z `475,335 s`, czyli około 85,7% czasu;
- mediana jednej próby OCR wyniosła `1,902 s`; lekka ścieżka bez OCR kosztowała
  około `0,068 s/JPEG`;
- przy udziale prób około 20% osiągnięcie `3 JPEG/s` wymaga zejścia ze średnim
  kosztem próby do około `1,32 s`; `6 JPEG/s` wymagałoby około `0,49 s`;
- projekcja 42 000 zdjęć z właściwych prób wynosi około `4 h 55 min–5 h 33 min`.

### Rekomendowane dalsze zmiany

1. Dodać wersjonowaną, lekką detekcję orientacji `0/180` przed OCR. Powinna
   porównać geometrię kandydatów etykiet, nie wykonywać board detection i nie
   stanowić dowodu zakresu.
2. Zmierzyć Paddle z `1/2/4` wątkami CPU na tej samej próbce 200 czytelnych
   źródeł. Zmiana musi otrzymać nowy fingerprint i uwzględnić liczbę
   równoległych workerów, aby nie spowodować oversubscription.
3. Batchować pierwszy poziom kandydatów pomiędzy małą, bounded kohortą prób.
   Obecne 12 cropów na zdjęcie tworzy batch `9+3`; pakowanie cropów kilku
   źródeł może ograniczyć liczbę niepełnych wywołań Paddle bez zmiany proof.
4. Zastąpić sam stały interwał krótkim oknem wybierającym na podstawie taniej
   jakości lattice najlepiej czytelny kadr. Deskryptor może planować próbę, ale
   nadal nie może przypisywać ani dziedziczyć zakresu.
5. Nie zwiększać teraz interwału ponad pięć i nie obniżać progu trzech pozycji.
   Takie zmiany poprawiłyby czas przez pogorszenie recall lub precision, a nie
   przez rzeczywistą optymalizację.
