---
title: Mumie — odporność modeli symboli i porównanie 600 zdjęć
status: complete
last_updated: 2026-10-05
---

# Wynik eksperymentu V2

Modele V2 zakończyły trening i kwalifikację, ale większa partia nie potwierdziła
ich przewagi. Nie zastępują V1. Użyto wyłącznie istniejących 339 etykiet
człowieka: 255 development i 84 validation z D-498. Zdjęcia partii 600 nie
weszły do treningu, wyboru epoki ani kalibracji. Przejrzana wcześniej partia
służy eksploracji; nie jest ślepym testem końcowym.

## Trening i eksport

| Wariant | Run ID | Epoki | Najlepsza epoka | Walidacja | Czas treningu |
|---|---|---:|---:|---:|---:|
| RGB V2 | e1f1770f06f44d3687e8985f8f9313b4 | 20 | 7 | 83/84 | 70,63 s |
| Gray V2 | 67b60e8b82d847cfb23cc8e320b05b38 | 20 | 10 | 83/84 | 78,93 s |

Oba modele uczone od zera, po 160 kroków, z limitem 1800 s i 10000 kroków.
`symbol-light-payline-v1` jest deterministyczne dla próbki/seed/epoki;
walidacja pozostaje nietknięta. Próby 40 epok odrzucono przed admission;
zachowano wspólny limit 20. Oba warianty mają 255/255 development.

Eksporty CPU Torch/ONNX Runtime: parity wszystkich 84 cropów, maksymalny
błąd bezwzględny 2,86102294921875e-6. Temperatury RGB/gray 0,8/1,1;
waga RGB fuzji 0,3. Kalibracja wyłącznie na pierwotnej walidacji. Znany
konflikt etykiety K z wyglądem Q pozostaje bez automatycznej korekty.
83/84 oraz Mumia 8/8 na małej walidacji nie dowodzą jakości całego folderu
ani rozpoznania złotej ramki Super.

Root:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-symbol-robustness-20261005\runs`.
Kalibracja: `comparison.json` w katalogu nadrzędnym.

## Rzeczywista partia i identyczność porównania

600 tych samych zdjęć, 5396 plansz i 80940 pól. V2 ponownie wyrenderował
każdy wcześniejszy quad i sprawdził SHA dokładnych pikseli RGB96. Geometria,
atlasy, overlaye, zakresy, kolejność i brak zatwierdzeń człowieka są identyczne.
1357 propozycji klasy zmieniło się między wersjami.

| Miara bez referencji człowieka | V1 | V2 |
|---|---:|---:|
| Modelowa niepewność | 15626 (19,31%) | 16024 (19,80%) |
| Rozbieżności RGB/gray | 3494 (4,32%) | 4047 (5,00%) |
| Wszystkie pola wymagające review | 15695 | 16084 |
| Niedostępne piksele | 0 | 0 |

To miary pokrycia i zgodności, nie accuracy. Niepewność wzrosła o 398 pól,
a disagreement o 553. Wizualny przegląd ujawnił poprawny K pod linią wygranej,
ale też regresje zwykłych J do Ra/K oraz nadal błędne J/Q pod białym znacznikiem.
Podświetlenie zmienia również symbole obrazkowe. Nie ma podstaw do wyboru
V2 jako lepszego modelu. Ocenę siatki obejrzanych przypadków oddzielono od
etykiety symbolu; żaden odbiór wizualny agenta nie staje się zgodą człowieka.

Manifest V2:
`916130086b1c7ed8b72869a3bca8ca3e0607bd4d6ec7af3ba8cd12cc15c6f27e`.
Root:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-folder-test-20261005\symbol-batch-v2-600`.
Przegląd: `http://127.0.0.1:8108/symbol-batch-v2-600/review.html`.

Ostatni plik nadal ma 5 pokazanych plansz i 75 pól, mimo 6 kandydatów sieci
i nazwy do 500004. Granica folderu 500000 i jawne powody konfliktu pozostają.
Nie przypisano finalnego sequence_number ani brakujących pikseli.

## Trwałość i kontrola jakości

- 36 testów augmentation/batch/training PASS. Dokładne wznowienie V1 i V2
  zachowuje optimizer/RNG/best weights/licznik kroków. Augmentacja identyczna
  w nowym procesie. Nieprawidłowe i NaN wyniki kwalifikacji są odrzucane.
- Ruff format/lint PASS. Mypy pięciu zmienionych modułów z
  `--follow-imports=silent` PASS. Pierwsza szersza kontrola wykazała wcześniejsze
  błędy typów w `board_search_share_queries.py` i osiągnęła limit 120 s;
  procesy zakończono. Próba `skip` traciła typy importów i nie jest dowodem
  jakości; końcowe `silent` zachowuje ich analizę.
- Świeży proces: wznowienie przetwarza 0 zdjęć; wszystkie 2404 pliki V2
  (737389437 bajtów) i 2404 pliki V1 zachowują identyczne SHA po replay.
- Ścisłe porównanie 80940 pól: zmieniły się tylko propozycje klasyfikatora,
  ich pewność i powody review. Geometria i piksele identyczne.
- Oryginalna geometria rev591 SHA:
  `06870eb890ad41947d05d0e0a4da1f0c6d7cac31a797ba196971a72ec1ee9f43`.
  Symbole rev63 SHA:
  `fa518e34b5547eec3b09e7158126a3c01b976bc989b472fa0c21ac54cb046e02`.
  Kontrola PASS, bez zmian historii, D-496 i V1.
- Driver ukończył 23 porcje po początkowych 25 zdjęciach, z budżetem 1800 s
  i timeoutem 115 s na porcję. Trening i inferencja mają trwałe raporty.
- Browser smoke obu galerii i strony 18 przypadków PASS. Sprawdzono kadry
  zmian, regresji, niepewności, kontroli klas oraz pełne zdjęcie z siatką.

Dowody: `comparison-600`, `replay-verification.json` i `independent-operation`
w `artifacts\mumie-symbol-robustness-20261005` głównego checkoutu.
Odrębny samodzielny przegląd braku przecieku, zgodności V1, deterministyczności,
kwalifikacji i publikacji nie wykazał nierozwiązanych P0–P2 w implementacji.
Jakość modeli pozostaje ograniczeniem danych, nie ukończonym wdrożeniem.

## Rzeczywista następna interakcja

Wybrano 18 pól z dokładnym zdjęciem, numerem planszy/pola, quadem i SHA.
Propozycje modeli są domyślnie ukryte. Strona
`http://127.0.0.1:8108/symbol-review-priority/review.html` i checksumowany
`cases.json` są tylko do odczytu; nie zapisują etykiet. Potrzebne są prawdziwe
etykiety trudnych wariantów i potwierdzenie geometrii przez istniejący workflow
po dopuszczeniu źródeł. Nie wymagamy kolejnych 30 przykładów każdej klasy ani
ponownego potwierdzenia już ustalonego pochodzenia nagrań.

Nie wykonano DB, aktywacji, wdrożenia, nowych zgód ani treningu Super.
Brak etykiet ramki Super uniemożliwia raport jakości tego atrybutu.
Kryteria TASK-0857 i planu pokryto kodem, testem lub artefaktem.
Osobny commit v1.7.203; pełny hash po commicie w Outcome/CURRENT_STATE.
