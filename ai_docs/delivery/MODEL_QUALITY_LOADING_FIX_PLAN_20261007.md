---
title: Naprawa długiego ładowania jakości modelu
status: done
last_updated: 2026-10-07
---

# Stan i cel

TASK-0898 realizuje zgłoszenie operatora: jakość Mumii pozostaje w ładowaniu
ponad dwie minuty. Read-only SQL wybiera 28 320 kandydatów z 1117 źródeł;
odczyt liczników trwał 0,469 s, pula 2,156 s. Obecny renderer dla każdej
komórki ponownie dekoduje JPEG, koduje PNG i dekoduje PNG do deskryptora.
UI dodatkowo czeka na niezależne preview reinferencji bez limitu czasu.

Celem jest szybki, odtwarzalny odczyt identycznej kohorty oraz zakończenie
loading komunikatem i retry przy utracie odpowiedzi. Nie zmieniamy API,
reguł kwalifikacji, danych, selekcji, modeli ani aktywacji.

# TASK-0898

1. W istniejącym rendererze udostępnić wykonaniowy renderer obrazów RGB.
   Domyślny renderer PNG nadal zapisuje identyczne piksele i sprawdza pełny
   kontrakt. Jedna grupa kandydatów jednego źródła używa jednego loadera;
   maksymalnie siedem grup działa równolegle. Po grupie zwalniamy klatkę.
2. Repozytorium liczy deskryptory bez PNG. Wyniki wracają w oryginalnej
   kolejności SQL. Protected-source attestation korzysta z tej samej klatki,
   której loader hashuje i dekoduje dokładnie te same bajty. Bramka chronionego
   źródła działa przed renderowaniem komórek; lekki odczyt manifestów renderu
   odbywa się wcześniej. Checksumy, aktualna geometria, zatwierdzona tożsamość
   i obsługa missing asset pozostają niezmienione.
   Cold process/freeze również korzysta z grupowania; optymalizacja nie
   zależy od rozgrzanego cache. Nie zapisujemy nowych bitmap/cache na dysku.
3. Odczyty Admina mają anulowanie i limit 45 sekund, z błędem i ponowieniem.
   Preview reinferencji nie blokuje jakości. Zmiana gry, ponowienie i unmount
   anulują wcześniejsze odczyty oraz chronią przed spóźnioną odpowiedzią.
4. Testy odtwarzają jednokrotny decode, identyczne deskryptory/manifesty,
   świeży proces, drift/missing, timeout i niezależne preview. Ograniczony
   odczyt rzeczywistych danych mierzy efekt bez mutacji. Lint, typy i build.

# Odbiór i granice

Kryteria: identyczny manifest na tym samym wejściu, brak PNG i powtórnych
decode per komórka, kontrolowane loading/error/retry, brak zmian danych.
Jeżeli ograniczony pomiar wykaże dodatkową przyczynę, dokumentujemy ją przed
rozszerzeniem rozwiązania. Wdrożenie i restart usług pozostają osobnym krokiem.

Pomiar kontrolny nowego procesu: 32,610 s, 6303 próbki, 3074 plansze i
813 źródeł po selekcji; checksum taki sam jak wcześniejsze odczyty tej poprawki:
138a43d3290d0fcc983d57cccfeb1aabcd41647edb08b6d1182bdd18cd11c7c8.
To wynik rzeczywistego, ograniczonego istniejącymi capami odczytu, bez treningu
lub zapisów DB; nie jest obietnicą czasu przy każdej przyszłej wielkości gry.
Pełny handler FastAPI odtworzony w nowym procesie zwrócił HTTP 200 w 39,843 s
z identyczną checksumą. Regresje Python 104/104 plus końcowe 28/28, Admin
14/14 i interakcje 4/4 przeszły. Format/lint, typy oraz build Admina przeszły.
Wdrożenia i restartu usług nie wykonano.

# Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0898 | gpt-6.1-sol | high | Optymalizacja odczytu z zachowaniem integralności treningu i kontrolą cyklu UI; konfiguracja dostępna w sesji. | Samodzielny przegląd diff i testy parity; eskalacja przy zmianie kontraktu lub kwalifikacji. |
