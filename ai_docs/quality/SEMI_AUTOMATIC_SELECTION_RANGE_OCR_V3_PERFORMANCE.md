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

## Rozszerzony odbiór surowych zdjęć 1000 + 1000

Test wykonano 2026-09-01 na dwóch rozłącznych, naturalnie uporządkowanych
odcinkach pełnego katalogu `E:\blazing zd\blazing 21400`. Nie użyto ręcznie
wybranych plików `seq_*`. Czas inicjalizacji Paddle nie należy do
`elapsedSeconds`; pomiar obejmuje checksumming, thumbnail, deskryptor, pełny
decode zaplanowanych prób i OCR.

| Surowy odcinek | Źródła | Próby OCR | Mocny dowód | Czas | JPEG/s |
|---|---:|---:|---:|---:|---:|
| offset `0` | 1000 | 201 | 137 | 526,801 s | 1,90 |
| offset `9000` | 1000 | 201 | 141 | 475,335 s | 2,10 |
| łącznie | 2000 | 402 | 278 | 1002,136 s | 2,00 |

W obu odcinkach scheduler skierował do OCR około 20% surowych klatek. Mocny
dowód uzyskało 278 z 402 prób, czyli 69,2%. Pierwszy odcinek był droższy:
mediana próby OCR wyniosła `2,122 s` wobec `1,902 s` dla offsetu `9000`.
Brak niezależnego oracle dla każdej surowej klatki nie pozwala wyliczyć
precision/recall końcowego grupowania. Wynik mierzy przepustowość i odsetek
prób z lokalnym dowodem, nie poprawność wszystkich finalnych wyborów.

Fingerprint recognizera obu prób:
`61e35b0653fe0787b352fcf9c4670edae28f020eed3e20f35acdadeae355dd8e`.

Próba 1000 zatwierdzonych plików `seq_*` nie jest korpusem odbiorczym
półautomatu: usuwa redundancję pełnego strumienia i każde kolejne zdjęcie ma
inny zakres. Pozostaje wyłącznie diagnostyką bramki z oracle. Potwierdziła
`138` dokładnych zakresów, `23` odrzucone surowe hipotezy i zero błędnych
automatycznych przypisań, ale jej czasu ani recall nie wolno używać do oceny
produkcyjnego wyboru reprezentantów.

### Diagnostyka orientacji

Pierwotny kandydat łatwej próby z `E:\blazing zd\blazing od 1`, offset `9900`,
okazał się fizycznie obrócony o 180 stopni bez użytecznej informacji EXIF.
Scheduler osiągnął `8,20 JPEG/s`, lecz `0/203` prób dało strong proof. Kontrola
wykonująca OCR na wszystkich 1000 źródłach również dała `0/1000`, więc brak
dowodu nie wynikał z harmonogramu. Obecny `ImageOps.exif_transpose` nie może
naprawić orientacji niezapisanej w metadanych.

### Wnioski wydajnościowe

- łączny wynik `2,00 JPEG/s` jest na granicy celu minimalnego; trudniejszy
  odcinek osiągnął tylko `1,90 JPEG/s`;
- cel `3–6 JPEG/s` dla użytecznego materiału nie został spełniony;
- OCR zajął łącznie `864,248 s` z `1002,136 s`, czyli około 86,2% czasu;
- lekka ścieżka bez OCR kosztowała łącznie około `0,069 s/JPEG`;
- przy udziale prób około 20% osiągnięcie `3 JPEG/s` wymaga zejścia ze średnim
  kosztem próby do około `1,32 s`; `6 JPEG/s` wymagałoby około `0,49 s`;
- projekcja 42 000 zdjęć z dwóch surowych odcinków wynosi około
  `5 h 33 min–6 h 09 min`, bez jednorazowej inicjalizacji Paddle.

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
