---
title: V7 T02 label localization probe
status: measured_not_accepted_for_activation
last_updated: 2026-09-21
---

# V7 T02 — pomiar lokalizacji etykiet

## Metoda

Read-only probe użył przypiętego modelu `en_PP-OCRv5_mobile_rec`, lokalizatora
dziewięciu source-local cropów oraz manifestu i inwentarza T01. Przed
otworzeniem obrazu porównuje bieżący manifest i fingerprint każdego katalogu z
zamrożonym inwentarzem `604185fbe5d8bbfe071788dd38a9bf6cf764d16561415afcf4e29b70d54ffda9`.
Domyślnie wybiera wyłącznie development i calibration; validation oraz holdout
wymagają jawnego parametru.

Próg jest wyłącznie proponowanym kontraktem T02: co najmniej pięć etykiet ma
confidence rozpoznania i niezależnie zmierzoną pewność pozycji co najmniej
`0.90` oraz ten sam source-local start. T02 nie mierzy jeszcze geometrii, więc
bez kalibracji T05 lokalizator emituje pewność pozycji `0.00` i blokuje proof.
Nie użyto nazwy pliku, oczekiwanego kolejnego zakresu, sąsiedniego kadru ani
jakości reprezentanta.

## Wynik ograniczonej próby

| Katalog | Próbka względna | Etykiety liczbowe | Wiarygodne pozycje | Konsensus 5+ |
|---|---|---:|---:|---|
| `777` | `777/302200 777_000645.jpg` | 9 | 0 | nie, fail-closed |
| `777 - przysłoniete częściowo plansze` | pierwsze źródło | 4 | 0 | nie |
| `blazing` | pierwsze źródło | 0 | 0 | nie |
| `gang` | pierwsze źródło | 1 | 0 | nie |
| `tresure` | pierwsze źródło | 2 | 0 | nie |

Cała bezpieczna próba pięciu plików wykonała się w 863 ms po inicjalizacji OCR.
W osobnym pomiarze kadru `777/302200 777_000645.jpg` OCR odczytał siedem
zgodnych liczb z wysoką pewnością rozpoznania w 3 874 ms. Dowód zakresu pozostał
jednak `none`, ponieważ T02 nie może zastąpić pomiaru geometrii stałą `0.95`.

Wczesny, wycofany probe przed audytem otworzył po jednym pliku z validation i
z holdoutu `rells_big`; jego wyniki nie są metryką T02 i nie mogą zostać
przedstawione jako niezależny odbiór. T05 wykluczy ten konkretny plik holdoutu
z końcowego zbioru albo utworzy nowy, wcześniej nieoglądany holdout przed
raportem T12.

## Wniosek i granica aktywacji

Kontrakt dowodu i OCR działają source-local, lecz T02 świadomie nie uznaje
stałych cropów za dowód jednoznacznej geometrii. Obecny, wstępny układ cropów
nie osiąga jeszcze wymaganego poziomu dla innych gier ani dla zasłoniętej
próbki. Nie jest to zgoda na automatyczny zapis ani aktywację V7.

T05 musi skalibrować lokalizację i progi na przypisanych danych development i
calibration, następnie ocenić je tylko raz na walidacji i zamrożonym holdoucie.
Brak dowodu w tej próbie jest raportowany jako brak dowodu, nigdy jako numer
wyprowadzony z kolejności katalogu.
