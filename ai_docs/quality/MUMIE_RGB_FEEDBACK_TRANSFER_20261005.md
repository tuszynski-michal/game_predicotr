---
title: Mumie — audyt poprawki RGB i 18 korekt operatora
status: complete
last_updated: 2026-10-05
---

# Wynik audytu TASK-0859

Uwzględniono [handoff poprawki 777](C:/Users/tuszy/Documents/game_predicotr/ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md).
Podczas analizy operator zakończył wszystkie 18 korekt. Ich aktualny zapis
ma revision=18, 18 approve od operatora i oryginalne stabilne symbol_id.
Nie trzeba ponownie przypisywać tych klas ani ponownie potwierdzać nagrań.

## Co już działa tak samo

Mumie uczą oraz rozpoznają pełny RGB, bez usuwania tła, zamiany na BGR i
gray_world. `symbol_batch.preprocess` daje RGB64 z normalizacją
`/255, minus 0.5, divide 0.5`, matematycznie równoważną `/127.5 - 1`.
Resize z antialiasingiem jest identyczny z treningiem Mumii. Wszystkie 18
rzeczywistych PNG RGB96 przeszły byte/pixel SHA oraz dokładne porównanie
z `load_image_tensor`; osobna gałąź gray ma własny model i preprocessing.
Nie należy kopiować resize/normalizacji z innego checkpointu bez sprawdzenia
kontraktu jego treningu.

Oba rozwiązania korzystają z `SpatialSymbolCnn` i przestrzennej mapy 4×4.
Kolejność głowicy Mumii pochodzi z zamrożonego słownika, nie z palety UI.
Ten słownik ma dziesięć klas i zachowuje ich UUID. Ośmioklasowy checkpoint,
classCodes i biblioteka referencji 777 nie są modelem ani słownikiem Mumii.

Dokładne cropy i decyzje pozostają source/pixel/revision-bound. Predykcja,
argmax, modelowa pewność i zgodność gałęzi nie tworzą etykiety człowieka.
Historia batch_crop_review nie jest automatyczną kwalifikacją treningową.

## Różnica wymagająca oceny

777 wybiera klasę z głowicy RGB; biblioteka 7/7 wyłącznie potwierdza klasę
lub pozostawia `?`. Mumie dotychczas wybierają skalibrowaną fuzję, której
ograniczone wagi RGB to 0/0.1/0.2/0.3. W V1 i V2 wybrano RGB0.3/gray0.7.
Rozbieżność modeli dodaje review, lecz nie blokuje wyświetlenia propozycji.

Nie zmieniono starego `compare`, calibration, manifestów, galerii ani
propozycji partii. Dzięki temu dokładny replay nadal zachowuje ich znaczenie.
RGB-primary jest sprawdzoną hipotezą, nie nowym ustawieniem domyślnym.

## Identyczna mała walidacja

Raporty obu gałęzi mają zgodne manifest_id, klasy, sample_ids i etykiety.
Wszystkie cztery modele oraz obie fuzje dają 83/84. Rozkład per klasa jest
identyczny: 10=12/12, J=4/4, Q=10/10, K=8/9, A=11/11, Ra=5/5,
Sarkofag=12/12, Mumia=8/8, Faraon=9/9, Sfinks=4/4.
RGB ma niższy logloss niż fuzja, ale nie mniej błędów. Znana etykieta K
wyglądająca jak Q pozostaje bez automatycznej zmiany.

To 84 pola z dwóch zdjęć, już używane do wyboru epoki i kalibracji.
Nie dowodzą jakości całego folderu ani niezależnej dokładności końcowej.

## Rzeczywiste 18 etykiet operatora

Wyniki liczą zgodność z nowymi decyzjami operatora na identycznych pikselach.
Nie zmieniono geometrii ani nie uruchomiono ponownej inferencji całej partii.

| Wersja | RGB | Gray | Dotychczasowa fuzja |
|---|---:|---:|---:|
| V1 | 11/18 | 10/18 | 10/18 |
| V2 | 10/18 | 13/18 | 11/18 |

| Klasa operatora | Liczba | V1 fuzja | V1 RGB | V2 fuzja | V2 RGB | V2 gray |
|---|---:|---:|---:|---:|---:|---:|
| 10 | 3 | 3 | 3 | 3 | 3 | 3 |
| J | 6 | 4 | 4 | 0 | 0 | 2 |
| Q | 3 | 1 | 3 | 3 | 1 | 3 |
| K | 1 | 0 | 0 | 1 | 1 | 1 |
| A | 1 | 1 | 1 | 1 | 1 | 1 |
| Ra | 2 | 0 | 0 | 2 | 2 | 2 |
| Sarkofag | 1 | 0 | 0 | 0 | 1 | 0 |
| Mumia | 1 | 1 | 0 | 1 | 1 | 1 |

RGB V1 poprawia Q, lecz psuje jedyną Mumię. RGB V2 psuje Q względem fuzji.
Gray V2 ma najwięcej trafień, lecz J pogarsza się z 4/6 V1 do 2/6.
Sama podmiana jednej globalnej gałęzi nie rozwiązuje wszystkich błędów.

Te przypadki wybrano celowo po obejrzeniu wyników; zawierają podświetlenia,
linie i białe znaczniki. Nie zawierają Faraona ani Sfinksa jako klas
referencyjnych. 13/18 nie jest accuracy całej gry. Korekty identyfikują
trudne warianty i są dowodem potrzebnym do kolejnej kwalifikacji danych.

## Zasady przeniesione z feedbacku 777

Kolejna ocena powinna wymagać mniejszej liczby błędów ogółem i braku
pogorszenia którejkolwiek klasy na tych samych źródłach, pikselach i
etykietach. Zmiana liczności lub zbioru klas unieważnia porównanie.
Na 18 przypadkach RGB V1 nie przechodzi tej bramki mimo wyniku 11 zamiast
10, ponieważ Mumia spada z 1 do 0. RGB V2 również jej nie przechodzi.
Na walidacji nie ma poprawy liczby błędów, więc żadna gałąź nie uzyskuje
podstaw do promocji wyłącznie z tego porównania.

Odróżniaj ręczne poprawienie klasy od potwierdzenia widocznej propozycji.
Zmieniona geometria unieważnia ocenę starej propozycji. Zachowaj dokładne
PNG, historię decyzji, UUID słownika i CNN provenance; nie używaj starego
kursora lub manifestu po zmianie preprocessingu/checkpointu. Kalibracja
korzysta wyłącznie z dopuszczonej walidacji. Nowe etykiety użyte do uczenia
nie mogą pozostać testem tej nowej iteracji. Rodziny nagrań i ich pochodne
pozostają w jednej części podziału.

Nie kopiujemy liczb 98–99% z 777, reguły jego biblioteki ani umownej pewności
0.99. Mumie nie mają jeszcze kwalifikowanej biblioteki o tym kontrakcie.
Same kolory, nearest-reference i zmiana wagi dobrana na tych 18 polach
nie zastępują niezależnego sprawdzenia pozostałych klas.

## Co dalej po zakończeniu 18 korekt

Najpierw przygotować osobną kwalifikację dokładnych decyzji i PNG do nowej
iteracji symboli. Zachować oryginalne batch_crop_review/trainable=false;
pochodny manifest musi jawnie rozstrzygać wymagane bramki geometrii i splitu.
Nie udawać zatwierdzenia pełnej planszy na podstawie zatwierdzonego wycinka.
Nie trzeba teraz ponownie zbierać po 30 zwykłych przykładów każdej klasy.

Po kwalifikacji wykonać ograniczony trening z trudnymi wariantami i
kontrolą wszystkich dziesięciu klas na dotychczasowej niezależnej walidacji.
Nową iterację sprawdzić na oddzielnej, nieużytej do uczenia partii; dawne
18 przypadków służą wtedy regresji/treningowi, nie niezależnemu testowi.
Następny przegląd operatora powinien dotyczyć nowych konkretnych pomyłek,
szczególnie J i Sarkofagu. Automatyczna aktywacja nadal pozostaje osobna.
Etykiety klasy nie zatwierdzają ramki Super; tego atrybutu tu nie oceniano.

## Weryfikacja i dowody

- 29 istniejących testów batch/training PASS: exact preprocessing,
  disagreement, reference conflict, bindingi, klasy, kalibracja i resume.
- Pierwsza próba pytest w runtime treningowym nie miała pytest. Użyto
  istniejącego głównego runtime testowego, bez instalacji zależności.
- Powtórny odczyt w nowym procesie zwrócił identyczny raport i wszystkie
  sumy wejść bez zmian. Revision=18 i 18 decyzji zachowane. Zero zapisów
  do magazynów operatora, zero treningu, aktywacji, DB i restartów usług.
- Raport jest pod
  `C:/Users/tuszy/Documents/game_predicotr/artifacts/mumie-rgb-feedback-20261005/199f2b585845887455fec2f4e92090e7b733a76fa9c531b649f369e6bff53f84.json`.
  Jego checksum jest nazwą pliku. Zawiera SHA wejść, słownik, wyniki
  per klasa i dokładne powiązania wszystkich 18 decyzji.
- Skrypt odczytowy w tym samym katalogu: `audit_transfer.py`. Uruchomić
  absolutnym `.venv-vision-lab/Scripts/python.exe` z worktree worker/src
  w PYTHONPATH, przez istniejący timeout runner, limit 120 s.
- Własny odrębny review pokrył każde kryterium TASK-0859 i właściwe DoD.
  Nie pozostają P0–P2 w odczytowej analizie; jakość modeli nadal wymaga
  następnej iteracji. Kod API/UI, modele i pierwotne etykiety są bez zmian.
