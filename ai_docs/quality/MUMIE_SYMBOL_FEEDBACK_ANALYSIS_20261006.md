---
title: Mumie — analiza poprawek symboli i dalszego treningu
status: active
last_updated: 2026-10-06
---

# Mumie — poprawki symboli z głównej aplikacji

## Wniosek

Silnik rozpoznawania symboli Mumii używa już sieci CNN. Nowe poprawki są
wartościowym wejściem do kolejnego treningu, szczególnie dla sarkofagu,
faraona i zdjęć z trudnym oświetleniem. Sam zapis etykiety nie aktualizuje
wag modelu. Nie uruchomiono treningu ani aktywacji w tej analizie.

Zalecenie: przygotować osobnego kandydata laboratoryjnego z wcześniejszych
oznaczeń człowieka i nowych, kwalifikowanych poprawek MAIN. Nie trenować
od zera wyłącznie na obecnych 81 próbkach DB: nie obejmują wszystkich klas.
Nie trzeba zaczynać oznaczania od początku; wcześniejsze dane istnieją.
Połączenie obu pul wymaga jawnego eksportu, zgodnego mapowania klas,
tożsamości pikseli, deduplikacji i zachowania ról źródeł kontrolnych.

## Stan sprawdzony 2026-10-06

Gra: `fea55cc1-ebf4-4cee-b3ab-a520017ed1be` w MAIN.
Odczyt21:30–21:33 UTC, wyłącznie bieżący właściciel każdej sekwencji.
Nie wliczano historycznych, zastąpionych propozycji.

- 126 zatwierdzonych komórek z34 zdjęć; poprzedni odbiór TASK-0886 miał40.
- 13 239 bieżących komórek nadal oczekuje na ocenę.
- 122 zatwierdzenia różnią się od zapisanej predykcji;4 ją potwierdzają.
- To celowo oceniona próbka, a nie losowy test. Wynik122/126 nie jest
  częstością błędów w całym folderze ani na całym nagraniu.
- Wszystkie126 zatwierdzeń mają zgodne bieżące/zatwierdzone sample ID,
  checksumę cropa, rewizję geometrii, source geometry, render spec i piksele.
- Nie znaleziono wykluczeń typu zła siatka, nieczytelność, zmieniony crop
  ani brak assetu w istniejącym podglądzie kohorty.

| Symbol człowieka | Zatwierdzenia | Zdjęcia | Próby wybrane przez preview |
| --- | ---: | ---: | ---: |
| 10 | 12 | 3 | 12 |
| J | 2 | 1 | 2 |
| Q | 0 | 0 | 0 |
| K | 13 | 2 | 12 |
| A | 0 | 0 | 0 |
| Sarkofag | 60 | 24 | 24 |
| Ra | 3 | 3 | 3 |
| Faraon | 26 | 15 | 18 |
| Sfinks | 10 | 7 | 10 |
| Mumia | 0 | 0 | 0 |

Podgląd `GET /api/v1/admin/games/{game_id}/model-quality` wybrał81 próbek,
62 plansze i30 zdjęć, manifest schema4 /
`26bd7f8714e92a92d813370375e183001b845b8cdd4c0962941043be98bf4521`.
Redukcja126 do81 wynika z istniejącej selekcji różnorodności/deduplikacji.
`canFreeze=true` oznacza możliwość zamrożenia niepustej kohorty, a nie
zaliczenie wymaganej reprezentacji klas w podziałach treningowych.
Q/A/Mumia są nieobecne; J, K,10 i Ra mają za mało niezależnych zdjęć dla
pełnego pokrycia czterech części podziału. Nie należy uruchamiać tej
samodzielnej kohorty tylko po to, aby uzyskać techniczny start joba.

## Najczęstsze poprawki i obraz

| Predykcja modelu | Decyzja człowieka | Liczba |
| --- | --- | ---: |
| A | Sarkofag | 42 |
| K | Faraon | 22 |
| Mumia | Sarkofag | 15 |
| Ra | Sfinks | 9 |
| Faraon | K | 7 |

Pozostałe poprawki obejmują Ra/Q/Sfinks na10, Ra naK/J i Q naRa.
W zapisanych rozbieżnościach confidence wynosi około0,20–0,61; nie było
błędu z confidence>=0,99. Podnoszenie progu confidence nie poprawi
rozpoznawania tych klas; skieruje większą część do przeglądu.

Obejrzano14 bieżących, checksum-bound miniatur, po dwie na każdą obecną
zatwierdzoną klasę. Widoczne są złote ramki, prześwietlenia i rozmycie;
przy dobrym cięciu bazowa klasa nadal wymaga poprawnego rozpoznania.
To obserwacja diagnostyczna AI, nie nowe zatwierdzenie ani niezależny
audyt wszystkich126 etykiet. Ramka pozostaje osobną cechą supergry.

## Dowód działania sieci i wcześniejsze dane

Aktywna iteracja `fd5b15b6-e335-410d-9720-5f2d3bd6ec43`, origin `lab_import`,
ma jedną aktywację z17:32:39 UTC. Nie ma nowej kohorty ani treningu DB.
Model `lab-rgb-symbol-onnx-v1` ma10 klas, wejście RGB64 i dokładny kontrakt
RGB96/bilinear-antialias64 z zerowym insetem. Sprawdzony ONNX zawiera
3 operacje Conv,2 MaxPool i2 Gemm: to rzeczywista sieć konwolucyjna.
SHA-256 ONNX:
`e4f9b2610407be8724fe0b5f26a5efa595b7b575af8434b73c19a39e04737095`.
Implementacja: `SpatialSymbolCnn` w
`services/worker/src/game_predictor_worker/images/symbol_model_benchmark.py`.

Dotychczasowy zestaw R2 ma283 przykładów człowieka w development
(264 wcześniejsze +19 późniejszych),84 na validation i osobne kontrole.
W development człowiek oznaczył wszystkie10 klas, w tym Q27, A23, Mumia20.
Pochodzenie AI jest osobne; dotychczasowe44 przykłady AI w development
nie stają się zatwierdzeniami człowieka przy nowym połączeniu danych.
Sprawdzono checksumy443 istniejących plików pakietu, łącznie6 637 811 bajtów.
Nie kopiowano folderów zdjęć ani bazy.

Te odczyty potwierdzają dostępność historycznych rastrów i etykiet.
Nie stanowią nowej kwalifikacji połączonej kohorty: trzeba ponownie sprawdzić
powiązania nagrań, pochodne źródeł, role i duplikaty między zbiorami.
Nie należy obiecywać364 nowych próbek przed taką kontrolą.

## Właściwa następna iteracja

1. Eksportować dokładne zatwierdzone cropy i etykiety MAIN z ich rewizjami,
   checksumami i źródłami. Istniejący eksporter
   `scripts/vision_lab_export.py` jest punktem wejścia do przeglądu integracji;
   wycinek w miniaturze120 px nie zastępuje wejściowego rastraRGB96.
2. Połączyć kwalifikowane poprawki z wcześniejszymi ludzkimi przykładami
   przez jawny format/adapter, bez dopisywania fikcyjnych decyzji do DB lub
   laboratoryjnego SymbolLabelStore. Obecny preview DB nie łączy tych magazynów.
3. Przypisać całe zdjęcia/nagrania do ról i usunąć kolizje z kontrolami.
   Zachować stały test poza uczeniem. Obecny DB podział gwarantuje całe zdjęcia,
   ale nie ma trwałego identyfikatora nagrania dla nowych uploadów.
4. Trenować jednego nowego kandydata RGB z większym udziałem rzeczywistych
   trudnych poprawek. Dobór augmentacji jasności/koloru i parametrów opierać
   na validation, bez podglądania końcowego testu.
5. Porównać z aktywnym R2 na identycznych niezależnych kontrolach: wyniki
   per klasa i pomyłki Sarkofag/Mumia/A oraz Faraon/K. Wzrost wyniku na tych
   samych nowych poprawkach po treningu nie jest dowodem generalizacji.
6. Pokazać wynik i ewentualne regresje przed osobną aktywacją. Dopiero potem
   nowe importy użyją nowej wersji; jawne przeliczenie obejmuje tylko pending.

Laboratorium3102 jest miejscem eksperymentów. W głównej aplikacji istnieje
`Mumie → Jakość rozpoznawania → Ulepsz rozpoznawanie` dla kwalifikowanej puli
DB. Przy obecnym niepełnym pokryciu nie zastępuje ono połączenia z historyczną
pulą laboratoryjną. Sieć rozpoznawania i sieć cięcia to osobne modele.

## Dodatkowa rozbieżność prezentacji

GET model-quality zwraca `activeModel:null`, mimo aktywacji w rejestrze.
`build_model_quality_summary` w domain/verified_training_cohorts.py ustawia
oba pola aktywnego modelu naNone. To ograniczenie tego podglądu, nie brak
sieci lub dowód jej wyłączenia. Panel pobiera także osobny rejestr iteracji;
naprawę spójnego opisu jakości należy prowadzić osobnym taskiem.

## Weryfikacja i granice

Dowody: `artifacts/mumie-feedback-analysis-20261006/`:
feedback-readonly.json, model-quality-readonly.json, existing-inputs-proof.json
i correction-visual-sample.png. Komendy0888 w istniejącym bounded runner.
Zapytania są read-only z limitami; HTTP wyłącznie GET. Nie zmieniono aplikacji,
etykiet, modelu, bazy, danych siódemek ani runtime. Nie wykonano treningu,
aktywacji, usunięcia danych ani testu dokładności całej populacji.
