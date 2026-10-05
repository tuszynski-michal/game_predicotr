---
title: Mumie — odbiór pierwszego rzeczywistego folderu
status: completed
last_updated: 2026-10-05
---

# Mumie — odbiór pierwszego rzeczywistego folderu

## Wynik i znaczenie

Test istniejących eksportów ONNX iteracji 2 i 3 na 200 zdjęciach z rzeczywistego
folderu zakończył się bez brakujących wyników. Każdy model znalazł 9 plansz na
każdym zdjęciu. Nie wykryto nieprawidłowych struktur siatek ani wycinków poza
obrazem. Nieoznaczone zdjęcia nie pozwalają obliczyć accuracy geometrii.
Zgodność liczby plansz z zakresem nazwy pliku jest wyłącznie diagnostyką.

Osobny pomiar 11 nowych zatwierdzonych zdjęć spełnia D-483 dla obu modeli:
11/11 kompletnych zdjęć, 99/99 plansz, zero fałszywych plansz i duplikatów.
Wszystkie 99 referencji są jednak niezmienionymi propozycjami iteracji 3
zatwierdzonymi przez operatora. Niemal zerowy błąd iteracji 3 oznacza zgodność
z tymi zatwierdzeniami; nie dowodzi jej niezależnej przewagi nad iteracją 2.
Zatwierdzenia są ważne. Nie były cofane, zmieniane ani użyte do nowego treningu.

## Źródła i dobór

- Folder: `C:\Users\tuszy\Documents\mumie wybrane\1 - 23175 cut`.
- 2580 JPEG-ów; 6 dokładnych kopii SHA; 5 SHA znanych kompletnych źródeł.
  Pozostało 2569 kwalifikujących się zdjęć; wybrano 200.
- Dobór deterministyczny po liczbowym zakresie nazwy `seq_start-end`,
  równomiernie od pierwszego do ostatniego dostępnego zdjęcia.
  Zakres próby: `seq_55-63.jpg` do `seq_23167-23175.jpg`.
- Sufiks Windows ` — kopia` zachowuje zakres; deduplikacja wyłącznie po bajtach,
  z preferencją oryginalnej nazwy. Bez zmiany nazw albo usuwania plików.
- Nowe 11 pochodzi z zatwierdzeń dodanych do kompletu 20 zdjęć; obecnie 31
  kompletnych, rewizja anotacji 591. Zakres nowych 11: 156610–156708.
  Nie są niezależnymi nagraniami ani testem nowej rodziny gry.
- Katalog: `0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2`.
  Istniejący ledger: `C:\Users\tuszy\Documents\game_predictor_vision_data\neural-grid-runs\finetune-D\ledger.json`.

Manifest, wyniki per zdjęcie, nakładki, arkusze wycinków, podsumowanie i audyt
pochodzenia są w ignorowanym katalogu
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-folder-test-20261005`.
Każdy wynik jest związany z manifestem i SHA swoich obrazów. Źródła, stan
anotacji i modele są przypięte do SHA. Publikacja wyników jest create-only;
niepełna próba nie jest odzyskiwana jako ukończony wynik.

| Element | SHA-256 |
|---|---|
| Manifest payload | `93558cd0e842aeca9b68570d591f6c8223e29c62426741fbf08a407b375c27a1` |
| Inwentarz folderu | `3f068f83c9039320bccfe9d41eeb385ec3803566e3437445bb31edf9c1a9976b` |
| Stan anotacji | `06870eb890ad41947d05d0e0a4da1f0c6d7cac31a797ba196971a72ec1ee9f43` |
| Bundle iteracji 2 | `d1b0beec1f905bf4564ef856ea13de061a9b725e24e780e8247e9176bd77f157` |
| Bundle iteracji 3 | `024dc1f0d5bc46515cb4173e04c474ea864d730b4d48abd6f418bacfa9b43566` |
| Summary payload | `6d29a8ef288a187d9be4828de3f5dec3dc3243f7bf352a09e2a09c01ee788f9f` |

## Modele, metryki i pochodzenie referencji

Użyto istniejącego `neural_grid_inference.onnx_engine` na CPU, cztery wątki;
bez zmiany dekodowania, progów lub checkpointów. Adapter nie tworzy nowego
silnika. Nie przypisuje końcowych `sequence_number` wykrytym planszom.

Eksporty: `iteration02-3ce52571e70d460f` i `iteration03-f896da7196431be2`,
run `5bc981568c3f42bd96f6f9238e57aedc`. Pełne ścieżki i SHA obu grafów ONNX
są zapisane w manifeście. Łącznie 422 wyniki: 211 zdjęć na każdy model.

| Pomiar | Iteracja 2 | Iteracja 3 |
|---|---:|---:|
| Zdjęcia folderu z liczbą 9 plansz | 200/200 | 200/200 |
| Nieprawidłowe struktury / pola poza obrazem | 0 / 0 | 0 / 0 |
| Nowe zdjęcia zgodne z zatwierdzeniami według D-483 | 11/11 | 11/11 |
| Nowe plansze zgodne z zatwierdzeniami według D-483 | 99/99 | 99/99 |
| Image-macro względem tych zatwierdzeń | 0,001239334759 | 0,000001539849 |
| Mediana NME | 0,001161594422 | 0,000001528490 |
| P95 NME | 0,001893221144 | 0,000001786300 |
| P95 największego błędu węzła | 0,003988551764 | 0,000002915959 |

D-483: dopasowanie Hungarian po IoU czworokątów, minimum 0,5; poprawna plansza
ma NME ≤ 0,02 i największy błąd węzła ≤ 0,05. Odległości normalizowane przekątną
referencyjnej siatki. Poprawne całe zdjęcie wymaga wszystkich poprawnych plansz
i braku fałszywych. Definicja metryk znajduje się także w `summary.json`.

Audyt `reference-provenance.json`: 99/99 `origin=proposal_unchanged`,
`actor=operator`, zestaw propozycji
`415c793103cd421db5090740e6edff36f072a6479e197c3d6965a43ea23aee85`.
Ledger wiąże zestaw z iteracją 3. Nieuczestniczenie nowych 11 w treningu nie
usuwa tego powiązania referencji z ocenianym modelem. Rozstrzygnięcie jakości
wymaga oceny pikseli i niezależnych granic, nie samego porównania z propozycją.

## Odbiór wizualny i podgląd

Obejrzano cztery arkusze z 20 równomiernie dobranymi parami nakładek
(`visual-qa-1.jpg`–`visual-qa-4.jpg`). Nie widać oczywistego przesunięcia plansz
ani zamiany wierszy/kolumn. Obejrzano dodatkowo arkusze 135 wycinków dla
iteracji 3 na `seq_11548-11556` i iteracji 2 na `seq_23167-23175`.
Symbole pozostają w odpowiednich polach; źródła zawierają odblaski, rozmycie
i nakładki interfejsu gry. To ograniczony przegląd wizualny, bez niezależnej
referencji wszystkich węzłów ani ręcznej oceny wszystkich wycinków z 200 zdjęć.

Podgląd operatora: `review.html`, z jawną informacją o pochodzeniu referencji.
Pokazuje modele obok siebie, pełne nakładki i rozwijane arkusze pól. Filtry
rozdzielają 200 zdjęć folderu i 11 zatwierdzonych. Pusty filtr anomalii ukrywa
poprzednie zdjęcie. W przeglądarce potwierdzono nawigację, oba filtry, pusty
filtr oraz rozwinięcie wycinków. Obejrzano także render pierwszego zdjęcia.
Nie korzystać z pierwotnego `index.html` jako raportu niezależnej dokładności.

Lokalny serwer podglądu: `http://127.0.0.1:8108/review.html`, PID 41152.
Wyłącznie localhost, katalog artefaktu, bez autostartu i bez nowych uprawnień.
PID i logi zapisane obok galerii. Same pliki pozostają po zamknięciu serwera;
`review.html` można otworzyć lokalnie wraz z katalogiem `assets`.
Podgląd nie zapisuje ani nie zatwierdza danych w aplikacji.

## Weryfikacja i trwałość

- 7 testów adaptera PASS: liczbowy i równomierny dobór, wykluczenia SHA,
  dokładne kopie, zmiana obrazu, odzyskanie i drift artefaktów, create-only
  manifest oraz ujawnienie pochodzenia referencji bez zmiany zatwierdzeń.
- Ruff check i format --check PASS; Mypy strict PASS dla jednego modułu CLI,
  z pominięciem kontroli importowanych zależności.
- Wszystkie kroki miały limit czasu przez zapisany runner. Inferencja etapami
  po maksymalnie 40 zdjęć; kroki kończyły się w limicie 120 s.
- Nowe procesy `run` obu modeli: pending=0, recovered=211; bez powtórnej
  inferencji, nowych wyników i duplikatów. `verify`: 211+211 wyników, SHA modeli,
  źródeł i wszystkich obrazów wyjściowych poprawne.
- Powtórne `finish` i `audit` odzyskały identyczne podsumowanie, pochodzenie
  i podgląd. To weryfikacja restartu procesu; nie wykonano restartu komputera.
- Test obejmuje wyłącznie adapter offline; nie wymaga zmiany OpenAPI ani
  builda uruchamianych aplikacji. Nie uruchamiano szerszego benchmarku.

## Następny zakres i wyłączenia

Nie ma teraz uzasadnienia do ręcznego oznaczania wszystkich 2580 podobnych
zdjęć. Najpierw przejrzeć porównanie i wskazać konkretne błędne granice.
Do niezależnego pomiaru wybrać małą reprezentatywną próbę, w tym trudne ujęcia
i inne warunki, z referencją sprawdzoną względem pikseli. Nowy trening ma sens
po dodaniu informacji o błędach, a nie samych kolejnych podobnych akceptacji.
Nie aktywowano ani nie przywrócono żadnego modelu na podstawie tego testu.

Nie wykonano zapisu do DB, migracji, importu tego folderu do produkcji,
V3-D/TASK-0805, nowego treningu, rozpoznawania symboli ani złotej ramki Super.
Zadanie 0845 realizuje wszystkie punkty zaakceptowanego planu pierwszego
testu. Zmiana numeru 0844→0845 chroni równoległy task symboli w głównym checkoutcie.
Kod pozostaje w `feat/grid-engine-v3`; bez scalenia do checkoutu z tym taskiem.

Commit zadania: `v1.7.189`; pełny hash zapisany po commicie w Outcome i CURRENT_STATE.
