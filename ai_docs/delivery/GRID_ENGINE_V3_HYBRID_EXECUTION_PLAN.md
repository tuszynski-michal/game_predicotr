---
title: Hybrydowy silnik siatek V3 — plan wykonawczy (kompletne zdjęcia w laboratorium, sieć węzłów, bramka zgodności)
status: proposed
last_updated: 2026-10-02
---

# Hybrydowy silnik siatek V3

Plan do akceptacji operatora. Uzupełnia etap D (`T10`, TASK-0675) i
poprzedza etap E zaakceptowanego
[VISION_LAB_EXECUTION_PLAN.md](VISION_LAB_EXECUTION_PLAN.md) (D-447).
Wersja z 2026-10-02 uwzględnia korektę operatora do pierwszej propozycji:
gra 777 nie jest źródłem danych ani odniesieniem, budżet treningu pozostaje
bez zmian, a symbole wybiera się dopiero z cropów poprawnych siatek.

## Stan obecny

Fakty z repo i raportów:

- **Laboratorium** (`services/worker/src/game_predictor_worker/vision_lab`,
  API `127.0.0.1:8102`, UI `apps/vision-lab` `127.0.0.1:3102`, dane poza
  repo `C:\Users\tuszy\Documents\game_predictor_vision_data`): kontrakty
  `GeometryEngine` / `GeometryResult` (`vision_lab/contracts.py`), silniki
  `baseline` i `hybrid` (`hybrid_*.py`), edytor siatek z przeglądem i
  akceptacją zdjęcia (`photo_review.py`, T03d), trwały protokół runów
  (`runs.py`, `run_worker.py`), izolowane środowisko GPU
  (`.venv-vision-lab`, `scripts/setup_vision_lab.ps1`,
  `scripts/check_vision_lab_gpu.py`). Katalog labu: 1 466 zdjęć z sześciu
  gier; ręcznie zatwierdzone: 63 zdjęcia i 180 pełnych siatek 5 × 3, czyli
  średnio niespełna 3 siatki na zdjęcie przy zwykle 9 planszach na ekranie.
- **Zamrożony pilot D-456** (stan anotacji rev268): development
  777/Blazing/Gang 90 siatek, walidacja Mumie 30, `final_test` Reels 30,
  `unseen_game` Treasure 30. Zdjęcia 777 są w labie wyłącznie jako ręczne
  siatki labu dopuszczone decyzją D-453.
- **Wynik T05** (`ai_docs/quality/VISION_LAB_HYBRID_20260927.md`): hybryda
  `MobileNetV3-Small` poprawiająca propozycje baseline, 20 epok / 200
  kroków, 568 s. Wynik image-macro (mniej = lepiej): DEV 0,1536 vs
  baseline 0,1565; VAL 0,04699 vs 0,04613 — walidacja gorsza o 1,85%,
  najlepsza epoka = 1. Baseline nie znalazł 15/90 i 1/30 plansz; hybryda
  poprawia tylko istniejące propozycje, więc braków nie odzyskuje.
  Raport odnotowuje, że niepełne anotacje zdjęcia nie są etykietami
  nieobecności. Brak promocji, STOP B.
- **Doświadczenie z importu produkcyjnego** (zgłoszenie operatora
  2026-10-01): import przeszedł, plansze z siatką trafiły do cięcia i
  weryfikacji symboli, a dopiero później okazało się, że wiele plansz z
  części zdjęć nie miało siatki. Pipeline traktował każdą planszę osobno i
  nie istniała bramka ani widok na poziomie zdjęcia, więc błąd silnika
  wyszedł na jaw późno i nie dało się go wychwycić ani poprawić silnika na
  świeżych przykładach.
- **Doświadczenie z symboli**: jakość rozpoznania zależy wprost od cięcia;
  błędna siatka daje cropy, które potem poprawia się komórka po komórce.
  Część decyzji o symbolach w starej grze zapadła na podstawie fragmentu
  zdjęcia albo zdjęcia, którego nie ma w systemie, dlatego te decyzje nie
  są wiarygodnym odniesieniem dla nowego silnika.

Wnioski (hipotezy, nie diagnozy): T05 miał za mało danych i dane niepełne
na poziomie zdjęcia, a z konstrukcji nie mógł odzyskać brakujących plansz.

## Cel

Kandydat silnika siatek 5 × 3, który na zamrożonej walidacji labu jest
mierzalnie lepszy od baseline w odsetku zdjęć z kompletem poprawnych
siatek, odzysku brakujących plansz i dokładności węzłów, z bramką, która
całe niepewne zdjęcie kieruje do przeglądu. Na poprawnych, kompletnych
siatkach operator wybiera potem zbiór symboli (etap C planu Vision Lab).

## Zakres i reguły

- **Gra 777 jest poza zakresem.** Plan nie czyta danych produkcyjnych
  `game_data_v2`, nie zmienia pipeline'u ani danych gry 777 i nie używa
  jej zatwierdzonych plansz ani decyzji o symbolach jako danych uczących
  lub odniesienia. Jedyny udział zdjęć 777 to istniejące ręczne siatki
  labu z D-453. Porównanie równoległe z D-461 pozostaje w T11–T13 planu
  Vision Lab i nie jest częścią tego planu.
- **Reguła kompletności zdjęcia (nadrzędna).** Jednostką geometrii jest
  zdjęcie, nie plansza. Zdjęcie ma oczekiwaną liczbę plansz, którą w labie
  potwierdza operator (domyślnie 9). Zdjęcie jest *kompletne*, gdy każda
  oczekiwana plansza ma poprawną, zaakceptowaną siatkę. Dopóki zdjęcie nie
  jest kompletne, żadna jego plansza nie jest cięta na symbole i nie
  wchodzi do zbioru symboli ani do treningu geometrii. Niekompletne
  zdjęcie ma jawny stan i wraca do edytora całym zdjęciem.
- **Kompletność widoczna od razu.** Każdy przebieg silnika i każdy import
  do labu pokazuje liczbę zdjęć kompletnych i niekompletnych oraz listę
  zdjęć z brakującymi albo niepewnymi siatkami, zanim zacznie się praca
  na symbolach.
- **Kompletność jako miara silnika.** Podstawową miarą jest odsetek zdjęć,
  na których silnik oznaczył poprawnie wszystkie oczekiwane plansze.
- **Symbole po siatkach.** Zbiór symboli i ich etykiety powstają z cropów
  kompletnych zdjęć labu po zamknięciu geometrii; plan nie kopiuje
  etykiet ze starej gry.
- **Budżet treningu bez zmian** (plan Vision Lab): smoke do 50 kroków i
  jeden trening do 20 epok lub 30 minut na zadanie modelu; kolejny run
  wymaga osobnej zgody.
- Topologia 5 × 3 (24 węzły); 3 × 3 poza planem. Trening w izolowanym
  środowisku GPU przez istniejący protokół runów. Testy i trening
  sekwencyjnie (VM WSL ma 8 GB). Audyty per zadanie są zawieszone decyzją
  operatora z 2026-10-01; każde zadanie ma własny commit, Outcome i wpis w
  `CURRENT_STATE.md`.

## Decyzje do potwierdzenia przez operatora

Numery nadaje `DECISION_LOG.md` przy akceptacji.

1. **Reguła kompletności zdjęcia** z sekcji wyżej jako wymaganie labu i
   przyszłej integracji silnika V3 dla nowych gier (nie dla 777).
   Doprecyzowuje D-450, gdzie akceptacja zdjęcia nie wymagała kompletu
   plansz: akceptacja pozostaje, a „kompletne” jest osobnym, ostrzejszym
   stanem.
2. **Cel anotacji.** Do treningu sieci widzącej cały ekran potrzebne są
   zdjęcia z kompletem siatek. Propozycja: po 30 kompletnych zdjęć na
   każdą z sześciu gier labu (ok. 1 600 plansz), z czego istniejące 63
   zdjęcia są uzupełniane do kompletu w pierwszej kolejności. Liczba jest
   decyzją operatora (koszt jego czasu); zadanie danych mierzy czas na
   zdjęcie na pierwszych 10 i raportuje go przed resztą.
3. **Kolejność etapów.** Etap D (sieć węzłów) rusza bez ukończenia C
   (symbole): symbole czekają na poprawne siatki, nie odwrotnie.
4. **Metryka nadrzędna** zamrożona przed treningiem: odsetek zdjęć
   kompletnych i poprawnych na walidacji; druga image-macro z T05 z
   kosztem braku = 1; pomocnicze: odzysk plansz, NME mediana i p95.
5. **Podział danych.** Zamrożony podział D-456 jest niezmienny; nowe
   kompletne zdjęcia wymagają nowej wersji podziału z tym samym
   przypisaniem gier (development 777/Blazing/Gang, walidacja Mumie,
   `final_test` Reels, `unseen_game` Treasure). Dotychczasowe wyniki T05
   pozostają przypisane do starej wersji.

## Etapy i zadania

Każdy etap wymaga jawnego uruchomienia; po etapie STOP z raportem.

### Etap V3-0 — kompletność zdjęcia w laboratorium

- **TASK-0800 — stan kompletności zdjęcia w labie.** W magazynie anotacji
  (`vision_lab/annotations.py`, `photo_review.py`, istniejący CAS, historia
  i backup — bez drugiego magazynu): oczekiwana liczba plansz na zdjęcie
  (domyślnie 9, zmiana jawna z autorem), stan `complete` wyliczany z
  zaakceptowanych pełnych siatek i oczekiwanej liczby, cofany przy zmianie
  geometrii. API i UI: filtr i licznik zdjęć kompletnych / niekompletnych
  per gra, w szybkim przeglądzie zdjęcia widoczne „N z M plansz”, lista
  brakujących pozycji; zatwierdzenie zdjęcia jako kompletnego niemożliwe
  przy brakach. Kontrakt pionem (OpenAPI labu, klient, wrapper, test).
  Stare zapisy: zdjęcia zaakceptowane, lecz niepełne, dostają stan
  niekompletny bez utraty akceptacji. Kryteria: testy stanu, cofnięcia i
  restartu; raport: ile z 63 zdjęć jest dziś kompletnych.
  **STOP V3-0:** raport kompletności labu.

### Etap V3-A — dane

- **TASK-0801 — anotacja wspomagana kompletnych zdjęć i nowy zamrożony
  podział (wymaga decyzji 1, 2, 5).** Kolejka zdjęć do uzupełnienia:
  najpierw 63 zaakceptowane, potem losowe z każdej gry do celu z decyzji
  2. Edytor podpowiada brakujące plansze z baseline, a po etapie B z
  kandydata (operator poprawia, nie rysuje od zera); predykcja nigdy nie
  jest zatwierdzeniem. Pomiar czasu anotacji na pierwszych 10 zdjęciach
  każdej gry. Nowa wersja podziału całymi grami (jak T03k, nowa nazwa
  polityki) obejmuje wyłącznie zdjęcia kompletne; kontrola przecieku po
  SHA i powiązaniach na pełnym katalogu bez zmian; backup i próba
  odtworzenia. **STOP V3-A:** liczba kompletnych zdjęć i plansz per gra,
  czas anotacji, zamrożony manifest.

### Etap V3-B — model i bramka

- **TASK-0802 — `neural_grid`: sieć widząca cały ekran (wymaga decyzji 3;
  realizuje T10 / TASK-0675 dla 5 × 3).** Dwa stopnie pod jednym
  `GeometryEngine`:
  1. *Ekran:* zdjęcie zmniejszone (dłuższy bok 768 px), lekki szkielet z
     wagami `MobileNetV3` i głowica map ciepła środków oraz narożników
     plansz (bez założenia 9 plansz; liczba wynika z detekcji), dekodowanie
     do quadów. Uczy się wyłącznie na zdjęciach kompletnych, bo tylko tam
     brak planszy jest prawdziwą etykietą.
  2. *Plansza:* wycinek wokół quada z marginesem, głowica 24 węzłów i
     dopasowanie siatki projekcyjnej z odrzuceniem odstających.
  Augmentacje: perspektywa, rozmycie, odblask, zasłonięcie („ręka”),
  zmiana barwy. Budżet bez zmian: smoke do 50 kroków, jeden trening do 20
  epok lub 30 minut. Preset i fingerprint zapisane przed runem; ONNX z
  parity jak w T05. Kryteria: ten sam kontrakt i odbiorcy co
  `baseline`/`hybrid`; raport z metryką nadrzędną na development i
  walidacji; holdouty nietknięte. Jeśli wynik nie przekracza baseline,
  zadanie kończy się konkretną listą brakujących danych, bez dodatkowych
  runów.
- **TASK-0803 — `hybrid_v3`: bramka zgodności i kompletności.** Silnik
  łączy `baseline` i `neural_grid`. Plansza jest „pewna”, gdy oba silniki
  dają zgodne quady i węzły w tolerancji; plansza tylko z jednego silnika
  albo niezgodna dostaje `needs_review` z powodem. Wynik zdjęcia: gdy
  liczba pewnych plansz jest mniejsza od oczekiwanej, całe zdjęcie ma stan
  niekompletny i trafia do przeglądu — żadna jego plansza nie jest
  oznaczana jako gotowa do cięcia. Progi kalibrowane tylko na walidacji;
  raport krzywej pokrycie–błąd na poziomie zdjęcia. Kryteria: brak cichych
  odrzuceń, test zamiany silnika bez zmiany odbiorcy, ONNX na CPU.

### Etap V3-C — ocena i STOP

- **TASK-0804 — raport porównawczy i rekomendacja.** Trzy silniki
  (`baseline`, `neural_grid`, `hybrid_v3`) na development i walidacji:
  odsetek zdjęć kompletnych i poprawnych, image-macro, odzysk plansz, NME
  mediana i p95, taksonomia błędów (ręka, odblask, skrajna kolumna,
  przeskok o kolumnę lub rząd), czas na zdjęcie na CPU. Po zamrożeniu
  modelu i progów jednorazowy odczyt `final_test` i `unseen_game`.
  **STOP V3-C:** raport w `ai_docs/quality/` i rekomendacja: kandydat do
  etapu symboli i integracji, dalsza anotacja (konkretna lista) albo
  zakończenie kierunku.

### Etap V3-D — integracja dla nowych gier (osobne uruchomienie po STOP V3-C)

- **TASK-0805 — bramka kompletności w aplikacji dla nowych gier.**
  Kontrakt powstaje po STOP V3-C. Założenia: silnik V3 działa tylko dla
  gier, które operator jawnie do niego przypisze; stan zdjęcia
  (kompletne, niekompletne, wyjątek operatora z autorem) wyliczany przy
  zapisie siatek; cięcie na symbole i weryfikacja symboli dopiero dla
  zdjęć kompletnych; licznik i lista zdjęć niekompletnych w panelu
  importu. Gra 777 i jej dane nie są zmieniane. Przed masowym
  przetwarzaniem obowiązuje brama skali z planu Vision Lab. Ten wiersz
  rezerwuje zakres, nie upoważnia do wykonania.

## Błędy i przypadki brzegowe

| Sytuacja | Zasięg | Reakcja |
|---|---|---|
| Zdjęcie ma mniej zaakceptowanych siatek niż oczekiwanych plansz | zdjęcie | stan niekompletny; poza treningiem i symbolami; wraca do edytora |
| Plansza fizycznie poza kadrem | zdjęcie | operator zmniejsza oczekiwaną liczbę plansz (zapis z autorem), dopiero wtedy komplet |
| Zmiana geometrii planszy na zdjęciu kompletnym | zdjęcie | stan cofnięty do ponownej akceptacji; podział oznaczony jako nieaktualny |
| Zdjęcie z błędnym plikiem albo SHA | zdjęcie | wykluczone z powodem; galeria działa dalej |
| Sieć nie zwraca planszy, którą ma baseline, albo odwrotnie | plansza i zdjęcie | `needs_review`; zdjęcie niekompletne |
| Run przerwany | run | wznowienie z checkpointu v2; budżet nie wraca |
| Brak GPU | etap B | stop z komunikatem; bez treningu na CPU |
| Za mało kompletnych zdjęć w grze | etap A/B | raport braków; bez obniżania progu kompletności |

## Mapa wymaganie → zadanie → kryterium

| Wymaganie | Zadania | Kryterium |
|---|---|---|
| Brak cięcia na symbole bez kompletu siatek na zdjęciu | TASK-0800, 0803, 0805 | stan zdjęcia; test: 8 z 9 → zdjęcie niekompletne, zero plansz gotowych |
| Braki siatek widoczne od razu | TASK-0800, 0803 | licznik i lista zdjęć niekompletnych po przebiegu |
| Silnik widzi planszę zamiast wnioskować z sąsiadów | TASK-0802 | odzysk plansz i odsetek zdjęć kompletnych > baseline na walidacji |
| Hybryda zamiast zastąpienia | TASK-0803 | krzywa pokrycie–błąd, powody `needs_review` |
| Dane kontroluje operator, bez starej gry | TASK-0801 | tylko ręcznie zatwierdzone zdjęcia labu; zero odczytów `game_data_v2` |
| Symbole z poprawnych siatek | TASK-0800, 0804 | zbiór symboli tylko z kompletnych zdjęć; rekomendacja do etapu C |
| Budżet i holdouty | TASK-0802, 0804 | jeden trening ≤ 30 min; jeden odczyt holdoutów |

## Odbiór całego przepływu

Po STOP V3-C: raport porównawczy, ONNX kandydata z parity, galeria labu
pokazuje trzy silniki i stan kompletności na tym samym zdjęciu, kontrakt
OpenAPI labu w `quality`, zamrożone manifesty i podział odtwarzalne z
checksum, brak odczytów i zmian w danych gry 777.

## Ryzyka

- Koszt anotacji: komplet 9 siatek na zdjęcie to więcej pracy operatora
  niż dotychczasowe 3; łagodzi to podpowiadanie siatek i pomiar czasu na
  pierwszych zdjęciach przed resztą.
- Mały zbiór i krótki trening mogą nie wystarczyć do przewagi nad
  baseline; wtedy wynikiem jest lista brakujących danych, nie dodatkowe
  godziny GPU.
- Bramka kompletności wstrzymuje symbole dla całego zdjęcia przez jedną
  trudną planszę; to koszt świadomy i mniejszy niż późne wykrycie braków.
- Walidacja na jednej grze (Mumie) i test na dwóch dają szerokie
  przedziały ufności; raport je podaje.

## Zakres wyłączony

Dane i pipeline gry 777, dane produkcyjne `game_data_v2`, etykiety symboli
(etap C, T06b–T09, T12), topologia 3 × 3, aktywacja produkcyjna i masowe
przetwarzanie, porównanie D-461 (T11–T13 planu Vision Lab), dodatkowy
budżet treningu.

## Przypisanie modeli do zadań

Dostępność potwierdzona w bieżącym środowisku (Fable 5.1, Opus 5.5,
Sonnet 5.5, Haiku 4.5). Kolumna review opisuje konfigurację na wypadek
wznowienia audytów; obecnie audyty są zawieszone decyzją operatora.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0800 | claude-opus-5-5 | high | Stan w magazynie anotacji z CAS, historią i zgodnością starych zapisów; kontrakt API i UI. | Zawieszony; przy wznowieniu claude-opus-5-5, medium |
| TASK-0801 | claude-opus-5-5 | high | Nowa wersja podziału, przeciek rodzin i trwałość zamrożenia decydują o wiarygodności wyniku. | Zawieszony; przy wznowieniu claude-opus-5-5, high |
| TASK-0802 | claude-opus-5-5 | high | Architektura dwóch stopni, trening w protokole runów, ONNX i kontrakt silnika. | Zawieszony; przy wznowieniu claude-opus-5-5, high |
| TASK-0803 | claude-opus-5-5 | high | Reguły bramki na poziomie zdjęcia i kalibracja bez przecieku z walidacji. | Zawieszony; przy wznowieniu claude-opus-5-5, medium |
| TASK-0804 | claude-opus-5-5 | high | Ocena dowodów, jednorazowy odczyt holdoutów, rekomendacja. | Zawieszony; przy wznowieniu claude-opus-5-5, high |
| TASK-0805 | claude-opus-5-5 | high | Zmiana przepływu aplikacji dla nowych gier; kontrakt po STOP V3-C. | Zawieszony; przy wznowieniu claude-opus-5-5, high |
