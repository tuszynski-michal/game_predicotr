---
title: Test strategy
status: accepted
last_updated: 2026-07-29
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
- generator snapshotu jest deterministyczny dla tych samych wejść,
- kolejność wyborów gier nie zmienia logicznej treści ani bajtów,
- produkcyjny snapshot nie zawiera pól fixture ani tabel administracyjnych,
- dataset/rules version są zachowane osobno dla każdej gry,
- layouty są pobierane keysetowo w bounded partiach i kontrolowane pod kątem
  ciągłości,
- dokładna bramka payoutów działa przed utworzeniem pliku,
- historyczny payout innego algorytmu nie trafia do snapshotu,
- błąd w połowie strumienia nie publikuje częściowego pliku,
- istniejący cel nie jest nadpisywany,
- fizyczny PostgreSQL zasila SQLite dokładnymi wersjami, symbolami, sygnaturami
  i payoutami,
- manifest schema v1 jest ścisły, kanoniczny i nie zawiera fixture/golden,
- katalog końcowy ma ścieżkę release/checksum i dokładnie dwa dozwolone pliki,
- idempotentny retry waliduje i ponownie wykorzystuje artefakt bez zmiany
  bajtów lub czasu modyfikacji,
- uszkodzony istniejący katalog powoduje kolizję zamiast nadpisania,
- niezależny read-only walidator odtwarza logiczny checksum strumieniowo,
- kontrolowane uszkodzenia manifestu, ścieżki, pliku, schema, indeksu, metadata,
  licznika, sekwencji, FK, symbolu, sygnatury i payoutu są wykrywane,
- błąd stagingu nie publikuje katalogu końcowego.

## PostgreSQL repository/integration tests

Od M2, na testowym PostgreSQL:

- unikalność i ciągłość `sequence_number`,
- dozwolone duplikaty `signature`,
- raport sześciu kontrolowanych grup duplikatów bez blokowania publikacji,
- raport luk, numerów poza zakresem, złej liczby komórek, obcego symbolu i
  niespójnej sygnatury,
- dokładne liczniki przy ograniczonych, deterministycznych próbkach
  diagnostycznych,
- trwałość typowanego payloadu joba, unikalność `input_key`, bounded filtrowanie
  listy i zapis anulowania,
- constraints nieujemnego postępu i pełny rollback migracji jobs,
- atomowy claim najstarszego joba i bazowe ograniczenie jednego `processing`,
- heartbeat, wygaśnięcie lease oraz fencing zapisu starego tokenu,
- atomowy checkpoint z postępem i wznowienie tego samego rekordu bez regresji
  liczników,
- anulowanie przy bezpiecznym checkpointcie oraz zwolnienie slotu po błędzie,
- konkurencyjny claim dwóch procesów na fizycznym PostgreSQL,
- złożony klucz payoutu, FK do layoutu i nieujemny wynik,
- bounded keyset batch layoutów oraz idempotentny upsert bez duplikatów,
- wznowienie payout joba od ostatniego checkpointu bez pominięcia sekwencji,
- awaria po upsercie przed checkpointem i bezpieczne ponowienie tej samej partii,
- deterministyczny JSONL z pełną interpretacją match/joker dla każdej partii,
- strumieniowa weryfikacja nagłówka, kolejności, totalu, rekonstrukcji matches,
  komórek, jokerów i interpretacji JSONL,
- dokładna bramka kompletności dla dataset/rules/algorithm z próbką maksymalnie
  100 brakujących sekwencji i blokadą braku `audit_path`,
- version safety: wyniki innego datasetu, rules lub algorytmu nie maskują braków,
- utrwalone payouty każdej golden case M1 są zgodne z czystym engine,
- odrzucenie stagingu, nieopublikowanych reguł, niezgodnych wymiarów i
  nieobsługiwanej wersji algorytmu,
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
- strumieniowy parser CSV/JSONL zachowujący fizyczne numery linii i offsety,
- bounded obsługa linii większej niż limit bez utraty kolejnego rekordu,
- izolacja parserowo błędnego wiersza bez utraty poprawnych wierszy partii,
- idempotentny upsert surowego stagingu po `(job_id, line_number)`,
- awaria po upsercie przed checkpointem i replay bez duplikatów,
- usunięcie wyłącznie nietrwałego ogona znajdującego się za checkpointem,
- niezgodny łańcuch checksumy prefiksu wymuszający pełny bezpieczny replay,
- zmiana pliku przed lub podczas stagingu blokująca ukończenie joba,
- staging nie trafia do wydania,
- walidacja importu odrzuca nieukończony job, nieopublikowane reguły, obcą grę
  i pusty aktywny alfabet,
- stała szerokość sygnatury wynika z całego aktywnego alfabetu wersji reguł,
- zła liczba komórek i obcy symbol są izolowane ze stabilnym kodem bez utraty
  dobrych wierszy,
- bounded odczyt surowego stagingu oraz idempotentny upsert normalizacji po
  `(validation_job_id, line_number)`,
- awaria po upsercie normalizacji przed checkpointem bezpiecznie powtarza
  partię i daje ten sam staging,
- raport zakończonego importu porównuje oczekiwany i rzeczywisty licznik
  stagingu, liczy luki od `1` wyłącznie na poprawnych wierszach oraz traktuje
  błędny wiersz jako blokadę bez wypełniania jego numeru,
- dokładne agregaty duplikatów numerów i sygnatur zachowują bounded,
  deterministyczne próbki; duplikat numeru blokuje, a duplikat sygnatury
  pozostaje ostrzeżeniem,
- lista znormalizowanych wierszy używa keyset po `line_number` i łączy filtry
  statusu oraz kodu błędu bez materializacji całego stagingu,
- odrzucenie stagingu usuwa znormalizowane wiersze przed surowymi, zachowuje
  joby, jest idempotentne dla pustego stagingu i respektuje FK,
- aktywna walidacja oraz dataset wskazujący import lub walidację blokują
  odrzucenie stabilnym konfliktem,
- publikacja błędnego stagingu zwraca stabilny konflikt i nie pozostawia
  `dataset_versions` ani layoutów,
- poprawny import z dozwolonym duplikatem sygnatury tworzy w jednej transakcji
  opublikowany dataset o ciągu `1..layout_count`, poprawnym codec i
  `source_job_id` walidacji,
- retry publikacji zwraca ten sam dataset, a częściowy unikalny indeks
  `source_job_id` chroni idempotencję także na poziomie PostgreSQL,
- po publikacji odrzucenie stagingu jest blokowane,
- unikalna i bezpieczna wersja mobile release,
- od 1 do 15 unikalnych wyborów gry w jednym atomowym zapisie,
- blokada staging/archived datasetu lub rules, obcej gry, niezgodnych wymiarów
  i pustego datasetu,
- deterministyczna kolejność gier po stabilnym kodzie oraz wydań od najnowszego,
- brak częściowego `mobile_release` po błędzie dowolnego wyboru,
- zmiany schematu wyłącznie przez Alembic.

## Admin API tests

- poprawne statusy HTTP,
- schema zgodna z OpenAPI,
- mapowanie błędów domenowych,
- brak wewnętrznych stack trace,
- walidacja rozmiaru wejścia,
- typowane zlecanie jobs,
- rozdzielenie statusu i etapu, odrzucanie błędnych przejść oraz natychmiastowe
  i odroczone anulowanie zależnie od stanu,
- retry tego samego joba oraz publiczna obserwowalność liczby prób, heartbeat i
  terminu lease bez ujawniania tokenu ani checkpointu,
- typowane create/list/detail mobile release bez możliwości podania algorytmu
  lub wersji schema przez klienta,
- atomowy endpoint build tworzący jeden job i odrzucający drugi start,
- niepełny lub nieudany build nie daje statusu `ready`,
- klient TypeScript generuje się bez ręcznych rozbieżności.

Nie tworzymy testów endpointów matching/forecast dla mobile, ponieważ takie endpointy nie istnieją.

Końcowy odbiór M2 uruchamia jeden scenariusz przez publiczne endpointy HTTP i
prawdziwy PostgreSQL: od pustych list, przez grę 3 × 5, 12 symboli, trzy
paylines i komplet payoutów, do opublikowanych reguł oraz mock datasetu 1000
layoutów. Dane domenowe nie mogą być przygotowane bezpośrednim SQL.

## Admin web tests

- czyste funkcje mapują każdy status i typ joba na tekst,
- lifecycle jawnie określa polling, cancel i retry,
- znany i nieznany total zachowują bieżący postęp oraz liczniki,
- akcje używają wyłącznie generowanego klienta i zachowują stabilne błędy,
- mutacja zastępuje ten sam rekord bez zmiany kolejności listy,
- produkcyjny build sprawdza integrację komponentu z kontraktem TypeScript,
- test przeglądarkowy sprawdza render aktywnego, failed i review joba,
  dwustopniowe anulowanie, retry, brak błędów konsoli oraz brak poziomego
  overflow przy szerokości 390 px.
- panel release filtruje aktywne gry i zgodne opublikowane źródła, waliduje
  1–15 wyborów, nie udostępnia pola komendy, tworzy draft, uruchamia build i
  wznawia dokładnie ten sam job,
- polling nie dubluje żądań jednego release, a zmiana wybranego wpisu nie może
  pokazać joba poprzedniego wydania,
- historia pokazuje status tekstem, dokładne UUID/numery wersji, ścieżki i
  checksumy; produkcyjny build sprawdza cały kontrakt komponentu,
- pobranie APK przechodzi przez wygenerowany klient; test API odrzuca release
  niegotowy i zmianę SHA-256 oraz zwraca zweryfikowane bajty gotowego pliku.
- panel importu tworzy typowany job importu i walidacji, pokazuje tekstowo każdy
  check raportu, dokładne liczniki i informację o obcięciu próbek,
- filtry statusu i kodu błędu resetują kursor, a następna/poprzednia strona
  zachowuje keyset `line_number`,
- podgląd poprawnego wiersza mapuje komórki row-major do siatki wymiarów reguł,
- odrzucenie wymaga otwarcia osobnego dialogu i przepisania dokładnego
  `importJobId`; podwójny submit jest zablokowany,
- test przeglądarkowy sprawdza pusty stan, brak błędów konsoli i brak poziomego
  overflow przy szerokości 390 px.
- workspace manual review zachowuje kolejność `selection_rank`, tekstowo mapuje
  każdy status i confidence, wybiera dokładnie jedną z 15 komórek row-major
  oraz buduje wyłącznie item-scoped URL assetu,
- akcje list/detail używają generowanego klienta, bounded limitu 100 i
  stabilnych błędów,
- accept/correct wymaga zaakceptowanej geometrii i dokładnie 15 etykiet
  powiązanych z `sampleId`; inactive symbol, pusta korekta i etykieta niezgodna
  z komórką są odrzucane,
- exact retry resolution nie dopisuje audytu, reuse klucza z innym payloadem i
  stale revision zwracają stabilny konflikt,
- zmiana accepted/corrected/rejected dopisuje kolejną rewizję bez usunięcia
  historii; rejected nie zawiera etykiet,
- eksport jest blokowany przez pending, wyklucza rejected i daje dokładnie 15
  próbek na accepted/corrected; retry stanu jest idempotentny, a zmiana stanu
  tworzy kolejną niezmienną wersję,
- API assetów odrzuca indeks poza 0–14, unsafe path, brak i niejednoznaczny
  oryginał, weryfikuje source SHA-256 i zwraca prywatny immutable image,
- browser smoke sprawdza kontrolowany error/retry, brak błędów konsoli i brak
  poziomego overflow przy 390 px; produkcyjny build pokrywa pełną kompozycję,
- test na realnym corpusie potwierdza odnalezienie source, board i cell dla
  pierwszej planszy checksum-bound batcha TASK-0063.

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
- zagnieżdżony checkpoint payoutu wznawia ten sam job bez child-jobów,
- wznowienie nie dubluje wyników i ponownie waliduje istniejący artefakt,
- poprzednie wydanie nie jest nadpisywane,
- gotowe APK zawiera wskazany snapshot,
- aplikacja mobilna akceptuje produkcyjny manifest schema v1 bez pól fixture,
- instalacja nowego APK nad starszą wersją aktywuje nowy snapshot,
- aplikacja nie otwiera starej kopii bazy po zmianie release version/checksum,
- signing key pozostaje poza repozytorium i jest używany konsekwentnie dla
  aktualizacji testowych.

## Image pipeline tests

- golden `image-pipeline-manifest-v1` ponownie weryfikuje checksumy wszystkich
  lokalnych modeli i raportów dowodowych,
- canonical JSON daje ten sam `pipelineFingerprint` niezależnie od kolejności
  kluczy, bez ścieżek absolutnych i timestampów,
- zmiana adaptera, modelu, checksumy, kalibracji albo confidence policy zmienia
  `pipelineFingerprint` oraz `fileExecutionKey`,
- ten sam SHA-256 źródła i pipeline daje dokładnie jeden klucz idempotencji,
- niepełna/zdublowana kolejność etapów, niebezpieczna ścieżka, zła checksum lub
  niespójny envelope kończą się stabilnym kodem,
- checkpoint dopuszcza tylko uporządkowany prefiks i przejście idempotentne lub
  o jeden etap; `manual_review_only` wymusza `waiting_for_review` przed
  `manual_review`,
- golden images z oczekiwanymi narożnikami/bounding boxes,
- niezależny golden granic komórek obejmuje obie grupy źródłowe i wszystkie
  dziewięć pozycji planszy,
- plansza 500 × 300 jest dzielona na sloty 100 × 100 przed zastosowaniem
  per-cell insetu; globalny inset nie może zmienić kroku siatki,
- detektorowy wariant v2 pozostaje mierzalnym wynikiem w kwarantannie, a P95
  odchylenia linii skalibrowanego v2 względem zaakceptowanego goldenu mieści się
  w budżecie `5 px`; zaakceptowany wynik TASK-0096 to `1.8337 px`,
- profil kalibracji jest wersjonowany, obejmuje dokładnie grupę i pozycję,
  weryfikuje fingerprinty źródeł oraz nie nadpisuje cropów,
- testy profilu obejmują dokładny anchor, interpolację pomiędzy anchorami,
  clamp przed/za zakresem, pojedynczy anchor, brak/duplikat zakresu oraz drift
  goldenu lub detektora,
- raport i każdy board artifact zapisują identyfikator/wersję profilu,
  sekwencje anchorów i wagę interpolacji; ponowna generacja zachowuje SHA-256,
- zmiana croppera zachowuje logiczne `observationId`, ale tworzy nowy
  `cropSampleId` i checksumę,
- zdjęcia obrócone,
- perspektywa i krzywizna ekranu,
- moiré, refleksy, słabe światło i rozmycie,
- brak jednego layoutu,
- OCR z błędem lub nieciągłą numeracją,
- błędna klasyfikacja trafia do review,
- pełnolayoutowy edytor zachowuje row-major, nie zapisuje etykiety przy
  niezaakceptowanej geometrii i wznawia częściowy layout,
- inwentarz symboli odrzuca v1, detektorowy v2, niezaliczoną bramkę jakości,
  drift profilu, planszy lub cropu oraz niespójne `observationId/cropSampleId`,
- atomowy zapis planszy odrzuca obcy sample bez częściowej zmiany, zachowuje
  idempotencję, konflikty identycznych bajtów i rozdziela postęp plansz od
  postępu komórek,
- loopback HTTP ponownie sprawdza checksumę planszy 500 × 300, token i Origin,
  a endpoint planszy nie przyjmuje ścieżki z klienta,
- trening jest batchowy i wersjonowany; pojedyncza decyzja nie mutuje aktywnego
  modelu,
- indeks sugestii zawiera tylko zaakceptowaną partycję train, a ranking
  wyklucza self-match i wszystkie referencje z tego samego zdjęcia źródłowego,
- ranking top-3 jest deterministyczny także przy remisie, zwraca najwyżej jedną
  referencję na symbol i przechodzi w `no_suggestion` poniżej jawnego progu,
- historyczna etykieta po `observationId` jest odróżniona od wyniku bieżącej
  geometrii; samo wyrenderowanie lub wybór komórki nie zapisuje decyzji,
- testy sugestii obejmują pusty indeks, niski similarity, crop drift,
  same-source leakage oraz smoke obu stanów UI,
- ONNX zachowuje wyłącznie dynamiczny batch; stałe kanały i wymiary obrazu
  oraz stała liczba klas są ponownie walidowane przed utworzeniem sesji,
- parytet PyTorch–ONNX obejmuje wszystkie train/validation/test, wymaga zera
  zmian top-1 i osobnego limitu błędu bezwzględnego dla logits oraz
  prawdopodobieństw,
- adapter ONNX odrzuca drift checksumy, inną liczbę klas, zły typ/kształt,
  pusty batch i wartości niefinitywne oraz wymusza lokalny CPU provider,
- temperatura jest dopasowywana wyłącznie na validation, poprawia albo
  zachowuje NLL i nie może zmienić top-1; test jest tylko pomiarem po fit,
- raport kalibracji obejmuje NLL, Brier, ECE, reliability bins, każdą klasę
  oraz pełne evidence progów, dzięki czemu słaba klasa nie znika w globalnej
  accuracy,
- status bootstrapowy, nieosiągnięty cel próbek lub niespełniony
  precision/support wyłącza auto-accept stabilnym reason code; auto-reject
  pozostaje wyłączony,
- active learning odrzuca niekompletną planszę, weryfikuje checksumę każdego
  pending cropu, wybiera pełne layouty 15/15 i wykorzystuje nowe źródła przed
  ponownym użyciem zdjęcia,
- ponowne uruchomienie dla tych samych raportów, modelu i cropów daje
  identyczną temperaturę, politykę oraz kolejność active-learning,
- import batcha review sprawdza canonical SHA-256, aktywny katalog symboli,
  bezpieczne ścieżki, unikalność źródeł/rankingu i dokładnie 15 komórek
  row-major,
- odbiór pionu ponownie materializuje inventory z zaakceptowanego v16 i wymaga
  byte-for-byte zgodności wszystkich 387 plansz oraz 5805 cropów,
- wszystkie 416 oznaczonych próbek przechodzą ten sam checksum-bound ONNX,
  temperaturę i kolejność klas; raport zapisuje `modelVersion`, confidence,
  top-3 i metryki per symbol dla train/validation/test oraz całości,
- replay manual review używa wyłącznie kompletnych plansz 15/15 i tego samego
  kontraktu accept/correct co Admin API; częściowe plansze pozostają jawnie
  wyłączone zamiast tworzyć niepełny feedback,
- `--check --require-pass` ponownie liczy logiczny raport pionu i wymaga
  identycznych bajtów; obserwacja czasu jest zamrożona i walidowana osobno,
- techniczny pass nie może zmienić `manual-review-only`, auto-accept ani
  zezwolenia na masowy import bez spełnienia progów per symbol,
- ponowienie identycznego importu zwraca ten sam batch bez dodatkowych rekordów,
  a konflikt gry lub payloadu dla tego samego checksumu jest odrzucany,
- testy kontraktu OpenAPI pilnują list/detail, bounded cursor pagination,
  resolution/history oraz create/list/get feedback exports,
- izolowany test PostgreSQL wykonuje migrację do head, zapisuje 30 plansz,
  sprawdza idempotencję oraz deterministyczną stronę elementów; bez lokalnej
  bazy pozostaje jawnym skipem,
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
