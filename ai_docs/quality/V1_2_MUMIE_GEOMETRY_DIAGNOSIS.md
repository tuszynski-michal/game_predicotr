---
title: V1.2 Mumie geometry diagnosis
status: active
last_updated: 2026-09-22
---

# Diagnoza geometrii V1.2 dla Mumii

## Materiał i metoda

Diagnoza obejmuje cztery pliki źródłowe z lokalnego katalogu
`C:\Users\tuszy\Documents\mumie`: `seq_1-9.jpg`, `seq_10-18.jpg`,
`seq_19-27.jpg` i `seq_28-36.jpg`. Wszystkie mają 1520 × 1054 px.

Sprawdzono trzy niezależne źródła informacji:

1. klasyczny detektor plansz, uruchomiony bez kotwicy;
2. najnowszy manifest preflightu Mumii;
3. kontrakt i dane ręcznej korekty geometrii strony.

Nie zapisano ani nie zmodyfikowano JPEG-ów, importów, rekordów gry lub
manifestów.

## Przypięty dowód i odtworzenie

Raport odwołuje się wyłącznie do manifestu
`artifacts/data/page-geometry-manifests/b5b8b0401ea0134a25b9bb5469f36f789d0031f9524f300fe098fcd3106a4bee.json`.
Nazwa pliku i SHA-256 jego zawartości są równe
`b5b8b0401ea0134a25b9bb5469f36f789d0031f9524f300fe098fcd3106a4bee`.
Manifest należy do gry `cf300bc1-c0c1-4bf9-b607-4c4e1e4f031c`, wyboru źródeł
`fa6772db-70ba-4c1f-b34c-5769730d1231` i manifestu źródeł
`c1b5c380b919cebb0d086e3ab42f9d12a497664e172ea77e5ef14e2b11486435`.
Przypina wariant `selective_board_review_v1_1` o sumie polityki
`94a953809213263fb3893da160195453501e5094398c207477fc947031e14f96`.

| Źródło | SHA-256 źródła | Ręczna decyzja |
| --- | --- | --- |
| `seq_1-9.jpg` | `68f8ba589e9bbca55eedc2431f4fbefd6fe95bb3e192729199e25ee08283e9f9` | rewizja 1, `223a2f20-f876-4518-833a-c7f248bcb3fb`, suma decyzji `2e08b347df32d6882d2e3f18c91371dbdb904de0c2d4abbaf551008b7ac15bfa` |
| `seq_10-18.jpg` | `80759c0f43456ace9a52555d4a64b2b70ce9589f32d7a0425e9ab73f87d18467` | brak |
| `seq_19-27.jpg` | `f2f37f6e9836e0021b6592b66dc96006fd562949ea1251657f88b523887bb4fe` | brak |
| `seq_28-36.jpg` | `e15eca4b489d39da5967408f19d0116acdf09866cdc384eac05f6a638008fde1` | brak |

Wynik klasycznego detektora odtworzono przez
`ClassicalPageBoardDetector()` z domyślnymi progami HSV: nasycenie co najmniej
80 i wartość co najmniej 50. Dla każdego z czterech RGB JPEG-ów wywołano
`detect()` bez odzyskiwania siatki, zasłonięć ani częściowej strony. Wynik
`needs_review` i zero plansz dla każdego pliku jest więc powtarzalny względem
podanych sum i tej konfiguracji.

## Wynik

| Źródło | Klasyczny detektor czerwonej ramki | Wynik preflightu | Pochodzenie geometrii |
| --- | --- | --- | --- |
| `seq_1-9.jpg` | `needs_review`, 0 plansz | 9 plansz | ręczna korekta |
| `seq_10-18.jpg` | `needs_review`, 0 plansz | 9 plansz | rejestracja do kotwicy |
| `seq_19-27.jpg` | `needs_review`, 0 plansz | 9 plansz | rejestracja do kotwicy |
| `seq_28-36.jpg` | `needs_review`, 0 plansz | 9 plansz | rejestracja do kotwicy |

Po ręcznej korekcie `seq_1-9.jpg` preflight zapisał dla pozostałych źródeł
średnie wsparcie czerwonych krawędzi odpowiednio 0,769628; 0,811547; 0,797716.
Wynik dowodzi, że kotwica pomaga rejestracji, ale nie usuwa jej zależności od
konkretnego koloru ani nie jest samodzielnym wykryciem obrysu planszy.

## Przyczyna niedokładności

Aktualna ręczna korekta zapisuje wyłącznie `final_quads`: dokładnie jeden quad
na planszę. Panel przedstawia go jako obrys planszy i na jego podstawie rysuje
równe linie 3 × 5. Kontrakt nie przechowuje oddzielnie:

- zewnętrznej ramki planszy;
- wewnętrznych granic 3 × 5 symboli;
- czterech odstępów ramka → siatka: lewy, górny, prawy i dolny.

Nie można zatem bezpiecznie wywnioskować z obecnych ręcznych korekt, czy ich
quad oznacza ramkę, siatkę symboli, czy kompromis między nimi. Tym bardziej
nie można z niego uczyć asymetrycznych odstępów widocznych w Mumii.

## Kontrakt wymagany przez V1.2

Dla zatwierdzonego przykładu V1.2 musi utrwalić, per gra i per plansza:

1. `boardFrameQuad` — widzialna zewnętrzna granica planszy;
2. `symbolGridQuad` — zewnętrzna granica całej siatki 3 × 5;
3. cztery odstępy wyprowadzone po wyprostowaniu `boardFrameQuad`;
4. dowód lokalnego kontrastu każdej krawędzi ramki oraz wynik kontroli, że
   granice siatki nie przecinają symboli.

Profil gry agreguje wyłącznie kompletne, ręcznie zatwierdzone pary. Na nowym
zdjęciu przewiduje marginesy jako wskazówkę, po czym lokalny estymator symboli
musi je potwierdzić. Brak kontrastu, brak pełnych dziewięciu plansz albo brak
dowodu siatki daje ręczną korektę, nie automatyczny crop.

## Ograniczenia

To jest diagnoza czterech dostępnych zdjęć, nie odbiór jakości V1.2. Nie
wyznacza progów ani nie potwierdza, że konkretna metoda kontrastowa działa na
wszystkich ujęciach. Te bramki należą do T02 i do wizualnego odbioru operatora.
