---
title: Test strategy
status: accepted
last_updated: 2026-07-24
---

# Strategia testów

## Zasada

Największe ryzyko znajduje się w logice domenowej, integralności kolejności, generowaniu wydania i wydajności offline. Testy algorytmów i danych są ważniejsze niż rozbudowane snapshoty UI.

## Domain unit tests

### Matching

- pusty prefiks,
- prefiks z 0 kandydatów,
- prefiks z 1 kandydatem,
- prefiks z wieloma kandydatami,
- exact unique,
- exact duplicate,
- duplikat nie wybiera najniższego numeru,
- Reset usuwa wynik duplikatu,
- kolejne wyszukiwanie po Reset nie ma starego kontekstu,
- nieprawidłowy symbol,
- nieprawidłowa długość tablicy,
- nieprefiksowy układ z `null`,
- poprawność kodowania stałoszerokiej sygnatury.

### Payouts

- pozioma payline i V,
- ciąg rozpoczynający się w pierwszej kolumnie,
- zgodne symbole rozpoczynające się w kolumnie 2 lub później nie wygrywają,
- długość 2 wygrywa dla symbolu z `minimum_match_length = 2`,
- długość 2 nie wygrywa dla symbolu z domyślnym minimum 3,
- różne symbole w tej samej wersji mogą mieć minimum 2 i 3,
- długości 2/3/4/5 zgodnie z progiem symbolu,
- najdłuższa długość nie sumuje wypłat za krótsze długości,
- luka przerywa dopasowanie,
- joker na początku, w środku i na końcu,
- ciąg samych jokerów nie wygrywa,
- wybór najbardziej korzystnej interpretacji,
- jeden joker interpretowany różnie na różnych paylines,
- kilka symboli i kilka linii,
- wspólna komórka liczona na obu liniach,
- identyczna payline odrzucona,
- brakująca reguła w macierzy precomputingu odrzucona,
- aktywna reguła poniżej minimum symbolu odrzucona,
- brak albo nieprawidłowe `minimum_match_length` odrzucone,
- payout, który nie rośnie wraz z długością, odrzucony,
- plansza szersza niż 5 kolumn nadal ocenia wyłącznie prefiks od pierwszej
  kolumny,
- audyt zawiera komórki i interpretacje.

### Forecast

- spin 0 bez kosztu i payoutu,
- pierwszy oceniany layout jest następnikiem,
- zawinięcie z końca do początku,
- dokładnie `N - 1` ocenionych spinów,
- wszystkie payouty po drodze są kumulowane,
- koszt jest dodawany dla każdego ocenionego spinu,
- `net = cumulative_payout - cumulative_cost`,
- zero nie jest dodatnie,
- brak dodatniego wyniku,
- jeden dodatni lokalny szczyt,
- późniejszy lokalny szczyt niższy od poprzedniego,
- rosnący odcinek zapisuje tylko końcowy szczyt,
- plateau zapisuje pierwszy spin,
- szczyt na granicy końca pełnego cyklu,
- brak numeru pośrodku datasetu powoduje błąd integralności, nie częściowy wynik,
- deterministyczny wynik.

## SQLite snapshot tests

- wymagane metadata istnieją,
- wersja schematu jest obsługiwana,
- liczba gier i layoutów zgadza się z manifestem,
- numery sekwencji są ciągłe,
- duplikaty sygnatur są dozwolone,
- exact lookup zwraca 0/1/wiele,
- prefix lookup korzysta z poprawnej semantyki stałej szerokości,
- cykliczny odczyt zwraca właściwą kolejność,
- każdy layout ma nieujemny payout,
- uszkodzona lub niezgodna baza daje `local_data_error`,
- generator snapshotu jest deterministyczny dla tych samych wejść.

## PostgreSQL repository/integration tests

Od M2, na testowym PostgreSQL:

- unikalność i ciągłość `sequence_number`,
- dozwolone duplikaty `signature`,
- raport sześciu kontrolowanych grup duplikatów bez blokowania publikacji,
- raport luk, numerów poza zakresem, złej liczby komórek, obcego symbolu i
  niespójnej sygnatury,
- dokładne liczniki przy ograniczonych, deterministycznych próbkach
  diagnostycznych,
- deterministyczny mock 1000 layoutów dla tego samego seedu i konfiguracji,
- atomowy zapis stagingowej wersji wraz ze wszystkimi layoutami,
- walidacja długości `row_path`,
- zakaz duplikatu payline,
- zakaz payout rule dla jokera,
- zgodność wymiarów dataset/rules,
- niezmienność opublikowanej wersji,
- raport wszystkich blokad gotowości wersji reguł,
- kompletna i ściśle rosnąca macierz payoutów przed publikacją,
- nieudana publikacja bez częściowej zmiany statusu lub `published_at`,
- publikacja pod blokadą rekordu i archiwizacja zachowująca `published_at`,
- idempotentny import,
- staging nie trafia do wydania,
- transakcja publikacji,
- zmiany schematu wyłącznie przez Alembic.

## Admin API tests

- poprawne statusy HTTP,
- schema zgodna z OpenAPI,
- mapowanie błędów domenowych,
- brak wewnętrznych stack trace,
- walidacja rozmiaru wejścia,
- typowane zlecanie jobs,
- niepełny lub nieudany build nie daje statusu `ready`,
- klient TypeScript generuje się bez ręcznych rozbieżności.

Nie tworzymy testów endpointów matching/forecast dla mobile, ponieważ takie endpointy nie istnieją.

Końcowy odbiór M2 uruchamia jeden scenariusz przez publiczne endpointy HTTP i
prawdziwy PostgreSQL: od pustych list, przez grę 3 × 5, 12 symboli, trzy
paylines i komplet payoutów, do opublikowanych reguł oraz mock datasetu 1000
layoutów. Dane domenowe nie mogą być przygotowane bezpośrednim SQL.

## Mobile tests

### Reducer/unit

- append symbol,
- undo pojedynczego symbolu,
- undo automatycznego uzupełnienia jako jednej operacji,
- reset,
- zmiana gry,
- pełna plansza,
- odrzucona propozycja prefiksu.

### Component/integration

- kolejność komórek,
- disabled states,
- modal accept/close bez ponownego otwierania dla tego samego prefiksu,
- stan inicjalizacji i błędu lokalnych danych,
- komunikat duplicate,
- Target ukryty dla duplicate,
- postęp długiego skanu,
- tabela na dole,
- wirtualizacja i stabilne klucze wierszy.

### Device smoke

M1 wymaga testu na:

- Google Pixel 10 Pro XL,
- Samsung Galaxy S21 Ultra.

Scenariusz działa w trybie samolotowym i po ponownym uruchomieniu aplikacji. E2E automatyzujemy dopiero po ustabilizowaniu UI; manualny protokół urządzenia jest obowiązkowy wcześniej.

Finalne APK M1 przechodzi również statyczną kontrolę manifestu potwierdzającą
brak uprawnienia `INTERNET`.

## Release pipeline tests

- ta sama wersja wejścia tworzy ten sam logiczny snapshot,
- manifest zawiera wszystkie wybrane wersje,
- payouty są obliczone przed zapisem,
- checksum snapshotu i APK jest zapisana,
- błędna walidacja przerywa workflow,
- anulowanie nie publikuje częściowego artefaktu,
- wznowienie nie dubluje wyników,
- poprzednie wydanie nie jest nadpisywane,
- gotowe APK zawiera wskazany snapshot,
- instalacja nowego APK nad starszą wersją aktywuje nowy snapshot,
- aplikacja nie otwiera starej kopii bazy po zmianie release version/checksum,
- signing key pozostaje poza repozytorium i jest używany konsekwentnie dla
  aktualizacji testowych.

## Image pipeline tests

- golden images z oczekiwanymi narożnikami/bounding boxes,
- zdjęcia obrócone,
- perspektywa i krzywizna ekranu,
- moiré, refleksy, słabe światło i rozmycie,
- brak jednego layoutu,
- OCR z błędem lub nieciągłą numeracją,
- błędna klasyfikacja trafia do review,
- podział train/validation według zdjęcia źródłowego,
- lokalne wagi bez pobierania w runtime,
- wznowienie i idempotencja.

## Test data

- stałe seedy,
- jawne przypadki 5–10 duplikatów treści na grę,
- mały fixture do unit tests,
- M1: 3 × 1000 layoutów,
- benchmark: co najmniej 500 000 layoutów w jednej grze,
- test rozmiaru dla estymacji 12–15 gier,
- golden przebiegi payout/forecast wyliczone niezależnie od kodu mobile.

## Robocze budżety wydajności

Do zatwierdzenia po benchmarku na słabszym z urządzeń testowych:

- exact match 500 000 layoutów: p95 poniżej 200 ms,
- typowy prefix match: p95 poniżej 300 ms,
- widoczny postęp pełnego skanu: do 500 ms,
- pełny skan 499 999 gotowych payoutów: cel do 5 s, maksymalnie 10 s przed decyzją o zmianie adaptera,
- płynne przewijanie wirtualizowanej tabeli bez renderowania wszystkich wierszy,
- przetwarzanie snapshotu i importu partiami, bez ładowania całego datasetu do pamięci,
- całe wydanie pozostaje w zaakceptowanej granicy kilku GB.

Budżety są celami roboczymi, nie gwarancją. Wyniki z modelu telefonu, wersją Android, rozmiarem bazy i konfiguracją builda muszą zostać zapisane w Outcome zadania benchmarkowego.
