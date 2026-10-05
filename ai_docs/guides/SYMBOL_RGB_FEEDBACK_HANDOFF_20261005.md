---
title: Rozpoznawanie symboli 777 i przekazanie metody RGB do Claude Code
status: active
last_updated: 2026-10-05
---

# Rozpoznawanie symboli 777 i przekazanie metody RGB do Claude Code

Do kolejnego przetwarzania należy przenieść obecną metodę
`symbol-audit-rgb-classifier-v2`. Na 3780 zatwierdzonych polach, które operator
przejrzał z propozycjami tej wersji, zgadza się ona z jego końcowymi wyborami
w 3736 przypadkach, czyli 98,84%. W tej grupie były 44 korekty propozycji,
przy niezmienionym cięciu siatki. Nowy eksperyment z referencjami z tych korekt
pomagał winogronom, ale pogarszał cytryny, więc nie zastępuje obecnej metody.

Przekazanie dotyczy gry 777. Skuteczność w audycie przesuniętych siatek wymaga
osobnej kontroli przy zastosowaniu do pozostałych wybranych komórek.

## Co poprawiono w rozpoznawaniu

Poprzednia biblioteka porównywała kształt, cechy sieci po dodatkowej korekcji
barw `gray_world` i histogram barwy środka cropa. W błędnych śliwkach z audytu
histogram opisywał również tło. Wcześniejsze próby samej barwy nie usuwały
problemu. Dodatkowe `gray_world` zmieniało obraz względem wejścia używanego
w treningu głowicy klasyfikującej.

Obecna metoda podaje istniejącej sieci pełny, oryginalny crop RGB 64 × 64,
z normalizacją `/127.5 - 1`. Nie usuwa tła, nie zamienia kanałów na BGR i nie
stosuje `gray_world` do głównego wyboru. `SpatialSymbolCnn` zachowuje mapę
przestrzenną 4 × 4, więc wybór wykorzystuje rozmieszczenie kształtu, detali
i barwy. Nie jest to reguła „żółty oznacza cytrynę”.

Wybór pochodzi z największego wyniku głowicy CNN. Biblioteka jest drugim
źródłem potwierdzenia: zgodny, jednomyślny wynik obu jej opisów 7/7 usuwa
znacznik `?`. Rozbieżność lub brak jednomyślności pozostawia propozycję CNN
z `?`. Ten znacznik oznacza potrzebę przeglądu, a nie brak rozpoznanego symbolu.

Wagi sieci pozostały bez zmian. W pierwszym, niewielkim porównaniu wzrokowym
obecna metoda poprawnie rozpoznała 120/120 cropów, a poprzednia polityka 115/120.
Ta ocena agenta była regresją techniczną; poniższy pomiar wykorzystuje
zatwierdzenia operatora i ma większy zakres.

## Wyniki nowych zatwierdzeń operatora

Zamrożony zbiór obejmuje 5788 kwalifikujących się pól z 578 zdjęć. Każdy crop
został odtworzony z oryginału i uzyskał SHA zgodny z aktualnymi, zatwierdzonymi
pikselami. Zbiór zawiera wcześniejsze zatwierdzenia oraz nowsze korekty audytu.
Obecny RGB zgadza się z 5688 etykietami, czyli 98,27% całości.

W grupie 3780 pól przeglądanych z propozycjami RGB wyniki są następujące:

| Symbol wybrany przez operatora | Pola | Rozbieżności RGB |
| --- | ---: | ---: |
| Arbuz | 429 | 1 |
| Cytryna | 556 | 0 |
| Śliwka | 584 | 1 |
| Winogron | 500 | 18 |
| Siedem | 309 | 10 |
| Gwiazda | 406 | 6 |
| Wiśnia | 510 | 5 |
| Pomarańcz | 486 | 3 |

Obecnym głównym problemem są śliwki proponowane na winogronach, a następnie
winogrona proponowane na siódemkach. W całym zbiorze porównanie wcześniejszej
propozycji do końcowej etykiety jest nieuprawnione dla 164 pól ze zmienionymi
narożnikami. Ocena RGB zawsze dotyczy końcowych, zatwierdzonych pikseli.

Zatwierdzenie niezmienionej propozycji przez Save jest słabszym dowodem niż
ręczne nadpisanie. Z tego powodu 98,84% oznacza zgodność z decyzjami operatora
w tym przeglądzie, nie niezależną gwarancję jakości całej bazy. Różne zdjęcia
mogą również należeć do tej samej rodziny fotografowania.

Historia wszystkich 5788 pól została sprawdzona: nie zawiera masowego
zatwierdzenia predykcji. Nowy exporter wyklucza takie przypadki zgodnie z D-465.

## Dlaczego nie włączono nowych wzorców z korekt

Zbiór został podzielony po SHA zdjęcia na 3644 pola referencyjne z 341 źródeł,
1188 walidacyjnych ze 134 źródeł i 956 testowych ze 103 źródeł. Identyczne
piksele nie mogą przechodzić między częściami; konflikt etykiet identycznego
cropa wyklucza taki crop. Wszystkie osiem klas występuje w każdej części.

Porównano cztery warianty na przestrzennych cechach oryginalnego RGB: najbliższy
zatwierdzony wzorzec przy podobieństwie ≥ 0,98 oraz zgodność trzech różnych
zdjęć przy progach 0,90, 0,95 i 0,98. Progi podobieństwa nie są pewnością
modelu. Wariant wybrany wyłącznie według łącznej liczby błędów na walidacji
zmniejszył błędy testowe z 21 do 18, lecz cytryny pogorszył z 2 do 5.

Żaden wariant nie spełnia warunku zmniejszenia liczby błędów bez pogorszenia
poszczególnych klas już na walidacji. Końcowa kontrola `safe_improvement`
odrzuca takie warianty przed wyborem do zastosowania. Obecna polityka RGB
pozostaje aktywna; eksperymentalne wzorce nie zostały opublikowane do audytu.

## Implementacja do przeniesienia

- `services/worker/src/game_predictor_worker/symbols/audit_rgb_classifier.py`:
  `rgb_batch`, `AuditRgbClassifier.candidates`, `candidate_is_tentative`.
- `scripts/recognize_grid_audit_symbols.py`: dokładny PNG podglądu,
  `contact_sheet_crops`, zamrożony checkpoint, propozycje i wznawialna publikacja.
- `services/api/src/game_predictor_api/application/grid_audit_symbol_suggestions.py`:
  kontrola SHA i kontekstu artefaktu. API obsługuje wersję RGB v2.
- `scripts/evaluate_grid_audit_feedback.py`: snapshot tylko do odczytu,
  render z kontrolą SHA, podział zdjęć, ocena klas i `safe_improvement`.

Checkpoint jest przypięty w `artifacts/grid-audit-symbols-20261005/library.json`:
SHA `1731869da3d082c43968c55bbc3fee0e2f58066ebcabf50191fb53164fb35f6c`.
Kolejność klas tego checkpointu to `ARBUZ, CYTRYNA, GWIAZDA, POMARANCZ,
SIEDEM, SLIWKA, WINOGRON, WISNIA`. Indeks argmax trzeba mapować przez jego
`classCodes`, a potem przez aktualne ID symbolu. Kolejność palety UI nie
jest katalogiem checkpointu.

Nie używać wyniku `reference_features` jako wejścia do głównego wyboru:
ta gałąź celowo stosuje stare przetwarzanie zgodne z zamrożoną biblioteką.
Nie przypisywać argmaxowi automatycznie „99% pewności”. Obecny writer
`reference_library_writer.py` oznacza wersję biblioteki i ustawia 0,99;
nie wolno podmienić jego wyniku na CNN bez jawnej zmiany kontraktu i pochodzenia.

## Sprawdzenie wyników w Claude Code

Komendy działają z katalogu repozytorium w Windows PowerShell. Odczyt
istniejącego snapshotu nie wymaga nowych zatwierdzeń ani treningu:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_grid_audit_feedback evaluate --output artifacts/grid-audit-feedback-20261005/approved-v2
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_audit_feedback_evaluation.py services/worker/tests/test_audit_rgb_classifier.py -q
```

Raport to `artifacts/grid-audit-feedback-20261005/approved-v2/report.json`.
`exploratory-report.json` zachowuje porównanie 21/18 przed kontrolą regresji
klas. Snapshot, cechy, podział i lista błędnych pól znajdują się obok.
SHA snapshotu: `572722c8f7b9d3a0cbe2e91b9ea93a6ec63326c74a2bde8f5e1191e90c08c3bb`.

Nową analizę po kolejnych korektach należy zamrozić w nowym katalogu:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_grid_audit_feedback snapshot --output artifacts/grid-audit-feedback-next --game-id bfc4f949-5c14-4850-b02a-db99610bcfa5 --model-metadata artifacts/grid-audit-symbols-20261005/library.json
.\.venv\Scripts\python.exe -m scripts.evaluate_grid_audit_feedback render --output artifacts/grid-audit-feedback-next --seconds 100
.\.venv\Scripts\python.exe -m scripts.evaluate_grid_audit_feedback features --output artifacts/grid-audit-feedback-next
.\.venv\Scripts\python.exe -m scripts.evaluate_grid_audit_feedback evaluate --output artifacts/grid-audit-feedback-next
```

Każdy proces należy uruchamiać z limitem do 120 sekund. Render można ponowić
w tym samym katalogu do `remaining=0`. Analiza po zmianie aktywnego checkpointu
wymaga nowego, zgodnego pliku metadanych; istniejący snapshot pozostaje zamrożony.

## Zastosowanie do pozostałych symboli

Rozpoznawanie otwartych pozycji istniejącego audytu jest już dostępne:

```powershell
.\.venv\Scripts\python.exe -m scripts.recognize_grid_audit_symbols --game-id bfc4f949-5c14-4850-b02a-db99610bcfa5 --game-code 7 --output-dir artifacts/grid-audit-rgb-next --library-cache artifacts/grid-audit-symbols-20261005/reference-crops.npz --max-seconds 80
```

Kod gry 777 w tej konfiguracji to `7`.
Kod wyjścia 3 oznacza niedokończoną rundę i ponowienie tej samej komendy.
Nowy audyt po cofnięciu planszy ma nową SHA: wymaga nowego katalogu wyników,
bez kopiowania starego cursora lub metadanych biblioteki. Skrypt zamrozi
bibliotekę dla tego audytu i wykluczy referencje z jego plansz. Wyniki są
propozycjami do przeglądu; odczyt i rozpoznawanie nie zatwierdzają komórek.

Dla wybranych komórek poza audytem Claude Code powinien przenieść ten sam
wybór RGB do istniejącego przepływu nowych rewizji predykcji. Przed większym
zapisem potrzebny jest nowy preview na ograniczonej, rzeczywistej części
wybranego zakresu i osobna ocena każdej klasy. Zapis powinien zachować SHA
aktualnego cropa, rewizje, pochodzenie CNN i regułę pending-only pod blokadą.
Rozwiązane przez człowieka pola oraz geometria pozostają nienaruszone.

Zatrzymane przebiegi Śliwki i Arbuza używały wcześniejszej biblioteki. Nie
wznawiać ich pod dawnymi manifestami po zmianie metody. Ich dalszy przebieg
wymaga nowego preview i zakresu zapisu zaakceptowanego przez operatora.

Dalsze uczenie CNN warto skoncentrować na rzeczywistych nadpisaniach,
zwłaszcza śliwka kontra winogron i winogron kontra siedem, z zachowaniem
niezależnych rodzin zdjęć. Włączenie takiego kandydata wymaga osobnej iteracji,
kalibracji i bramki istniejącego pionu supervised model improvement.
