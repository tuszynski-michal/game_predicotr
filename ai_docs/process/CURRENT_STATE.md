---
title: Current project state
status: active
last_updated: 2026-09-02
---

# Current State

Tor `0.5` został zamknięty. Ostatni commit implementacyjny to `v0.5.15`, a
commit dokumentacyjny zamknięcia otrzymuje `v0.5.16`. Następny tor rozpoczyna
się od `v0.6.0`; jego pierwszy pion dotyczy workspace’ów `Gry` i
`Import layoutów`.

## Phase

`Version 0.10 active: virtual geometry and structured-CV rollout`

### Niepuste zbiory oceny treningu symboli — TASK-0397

- Nowe iteracje modelu zbierają rodziny źródeł zarówno z kohort pełnych plansz,
  jak i z pojedynczo zatwierdzonych cropów. Dataset z co najmniej czterema
  rodzinami nie może rozpocząć treningu z pustym train, validation, test ani
  regression.
- Wadliwe historyczne przypisanie jest naprawiane deterministycznie wyłącznie,
  gdy nie da się go uzupełnić do pełnego podziału bez przesunięcia źródeł.

### Widoczność wykluczenia zatwierdzonego cropa z uczenia — TASK-0396

- W widoku `Zatwierdzone` Weryfikacji symboli crop, który zachowuje decyzję
  człowieka, lecz nie spełnia kryteriów bieżącej kohorty, otrzymuje badge
  `Poza uczeniem` z przyczyną jakościową lub informacją o nieaktualnym cropie.
- Oznaczenie jedynie wyjaśnia istniejącą politykę kohort; nie zmienia statusu,
  przypisania symbolu, checksumy ani decyzji review.

### Historia i trwałe wznawianie weryfikacji zakresów — TASK-0393

- Weryfikacja plików `seq_*` ma trwały `workflowMode=filename_verification`,
  ale nie tworzy nowego `JobType` ani lane. Historyczne runy są przy migracji
  rozpoznawane po fingerprintcie v2; aktywnego joba nie wolno przerywać ani
  ponownie tworzyć.
- Admin przechowuje listę runów oraz ich wybrany kontekst po reloadzie.
  Podgląd podejrzanych źródeł jest checksum-bound do stagingu, a decyzje
  `keep/reject` są serwerowe i rewizyjne. Lokalny uchwyt katalogu jest potrzebny
  wyłącznie dla journalowanego delete.

### Finalizacja OCR weryfikacji nazw — TASK-0394

- Po OCR workflow `filename_verification` nie wybiera reprezentantów, nie
  tworzy `seq_*` i nie wywołuje zwykłej ścieżki selekcji. Utrwala tylko wynik
  `verified`, `unreadable`, `mismatch` albo `invalid_filename`.
- Licznik review joba jest publikowany wyłącznie w terminalnym checkpointcie,
  więc nie może zmaleć po rozpoczęciu wyborów. Failed run można wznowić z
  zapisanych obserwacji bez drugiego OCR; Admin pokazuje do tego jawną akcję.

### Domknięcie i cleanup weryfikacji nazw — TASK-0395

- Automatycznie zgodny `filename_verification` albo run po ostatniej ręcznej
  decyzji przechodzi przez wznawialny `cleanup_pending` do `completed`.
  Historia zachowuje tylko podsumowanie; staging, OCR, raporty, ranges i
  decyzje tego runu są usuwane.
- Przed cleanupem worker blokuje retencję i sprawdza obce joby, runy, outputy
  oraz referencje. W razie konfliktu zapisuje `cleanup_blocked`, nie usuwa
  wspólnych danych i pozwala wznowić sam cleanup bez drugiego OCR.

### Bezpieczne usuwanie pustej historii browser stagingu — TASK-0391

- Usuwanie stagingu bez plansz i review kasuje również automatyczne rewizje
  źródłowej geometrii `0` oraz nierozwiązane rekordy odroczeń, zanim usunie
  źródła i wykonania pipeline'u.
- Ręczne lub rozwiązane rewizje geometrii, canonical, rollout i kohorty są
  nadal fail-closed chronione. Operacja wycofuje się w całości, zamiast usuwać
  część grafu danych.

### Wspólna blokada lokalnego pickera katalogów — TASK-0392

- Jeden współdzielony koordynator serializuje jedynie czas systemowego dialogu
  File System Access dla lokalnych workflowów Admina. Nie obejmuje jobów OCR,
  uploadu, skanu ani zapisu plików, więc aktywna `Weryfikacja zakresów` nie
  blokuje `Uzupełnij luki` ani `Usuń sekwencje`.
- Drugi dialog jest fail-fast z czytelną instrukcją zamknięcia pierwszego;
  lock zwalnia się po anulowaniu, sukcesie i rozpoznanym konflikcie natywnego
  pickera. Wywołanie zachowuje binding `window`, co eliminuje `Illegal
  invocation`.

### Produkcyjny import structured z przypiętym preflightem — TASK-0390

- Nowe joby `structured_default` przypinają silnik
  `structured-opencv-independent-board-refinement-v2-pinned-preflight-v1` i
  nie mogą ponownie użyć wadliwych wyników etapów v1.
- Wpis `registered` checksum-bound manifestu strony jest finalnym dowodem
  zewnętrznego obrysu. Topologia wyprowadza komórki także dla gier bez
  widocznych linii 5×3; row-major, brak nakładania i padded source support
  pozostają twardymi bramkami.
- Structured cropy walidują osobno pozycje `verified` i `deferred`, nie
  duplikują zapisu odroczeń, a nowy job odtwarza własne projekcje z
  niezmiennych wyników współdzielonych etapów.
- Liczniki sukcesów fazy pipeline'u nie obejmują już samego skopiowania
  źródeł. Awaria wszystkich 2200 źródeł pokazuje `0` poprawnych i `2200`
  błędów oraz kończy job jako failed, zamiast sugerować gotowość do review.
- Ograniczona próba na rzeczywistych `seq_1-9.jpg` oraz `seq_10-18.jpg`
  zwróciła po dziewięć zweryfikowanych obrysów, dziewięć virtual crops i zero
  odroczeń. Historyczny v1 pozostaje bez zmian.

### Trwałe grafiki z pojedynczo zatwierdzonych cropów — TASK-0389

- Picker `Wybierz grafikę` używa teraz tej samej bieżącej, checksum-bound
  decyzji pojedynczej komórki co kohorta treningowa; nie wymaga już
  rozstrzygnięcia całej planszy.
- Zatwierdzony crop legacy jest kopiowany bez zmiany bajtów. Crop
  `virtual_source` v0.10 jest przy wyborze jednokrotnie renderowany w pełnym
  rozmiarze do content-addressed PNG w `data/symbol-references`; aplikacja
  mobilna odczytuje następnie wyłącznie ten trwały plik.
- Migracja `0090_symbol_reference_individual_cell_provenance` dopuszcza
  `resolution_revision = 0` tylko dla referencji utworzonej z pojedynczo
  zatwierdzonej komórki.

### Produkcyjny silnik v0.10 per gra — TASK-0384

- Admin przywraca jednoznaczny wybór pomiędzy stabilnym v19 i produkcyjnym
  v0.10 dla nowych importów. Historyczny shadow pozostaje odtwarzalny, ale nie
  jest opcją operatorską.
- Weryfikacja symboli renderuje bieżący asset zapisany na komórce; dane legacy
  pozostają legacy do czasu jawnego ponownego przetworzenia, a nowe wyniki
  `virtual_default` są bezpośrednio mutowalne.

### Bezpośredni wybór filtrów Weryfikacji symboli — TASK-0385

- Gra i zakres symbolu startują jako niewybrane, więc samo wejście do zakładki
  nie pobiera strony cropów.
- Po wskazaniu obu pól pierwsza strona ładuje się automatycznie. Usunięto
  dodatkowe akcje `Zatwierdź wybór` i `Zmień wybór`; zmiana gry zeruje symbol,
  strony oraz viewport, a istniejące zaznaczenie nadal wymaga jawnego
  potwierdzenia wyczyszczenia.

### Filtr stanu Weryfikacji symboli — TASK-0387

- Radio `Wszystkie / Oczekujące / Zatwierdzone` wykorzystuje istniejący,
  cursor-bound filtr `state`; zmiana resetuje strony, viewport i zaznaczenie
  tak samo jak zmiana gry lub zakresu symbolu.
- `Zła siatka` i `Nieczytelny symbol` nie są sztucznie prezentowane jako
  status `odrzucone`: pozostają osobnymi problemami jakościowymi.

### Niewyraźne cropy symboli — TASK-0388

- Akcja `Niewyraźny` zachowuje rozpoznany symbol jako zatwierdzony, zapisuje
  osobny `quality_issue = blurry` i wyklucza crop z kohort treningowych.
- Toolbar grupuje w jednej linii akcje `Niewyraźny / Nieczytelny / Zła siatka`;
  `blurry` nie trafia do kolejki nieczytelnych ani korekty geometrii.

### Miniatury symboli od krawędzi do krawędzi — TASK-0386

- Bieżący renderer cropów legacy nie dopisuje już czarnego płótna do atlasu;
  pełny crop wypełnia tile 100 × 100 tak samo jak źródło wirtualne.
- Obramowanie karty jest nakładką na krawędzi grafiki. Nie zabiera miejsca
  miniaturze i nie zmienia wirtualizacji, batchingu ani liczby requestów.

### Zakres cropów gry w Weryfikacji symboli — TASK-0371/TASK-0383

- `Weryfikacja symboli` wybiera grę oraz jawny zakres: wszystkie bieżące cropy,
  jeden aktywny symbol albo nierozpoznane `?`. Stan i confidence nie zawężają
  listy.
- Admin API obsługuje odrębny zakres `symbolId=all`; `unknown` zachowuje swoje
  dotychczasowe znaczenie, cursor game-wide jest związany z własnym scope, a
  kolejność pełnego katalogu ma dedykowany indeks seek.
- W mieszanym widoku dostępne jest jawne zaznaczanie kart lub strony. Masowe
  zaznaczenie całego filtra pozostaje wyłączone, aby nie łączyć niezgodnych
  mutacji cropów zwykłych i nierozpoznanych.

### Odbiór range-only OCR v4.1 — TASK-0370

- V4.1 przeszedł bramki bezpieczeństwa i wydajności, ale nie przeszedł bramek
  coverage. Na challenge: `0` false exact, `62,5%` readable coverage i `100%`
  group capture. Na frozen golden: `0` false exact, lecz tylko `26,3%`
  readable coverage i `35,3%` group capture.
- Próby 1000 surowych JPEG-ów osiągnęły `4,83` oraz `5,05` źródła/s. Ręczna
  kontrola wszystkich 120 wybranych reprezentantów potwierdziła `100%` zakresu
  i własnego exact proof; koszt skaluje się liniowo.
- Rollout został odrzucony. Nowe runy nadal używają v3, a v4.1 pozostaje za
  flagą. Następna iteracja musi poprawić lokalizację środkowego rzędu pod nowym
  fingerprintem i przejść nowy holdout bez osłabiania proof.

### Batch, orientacja i recovery range-only OCR v4.1 — TASK-0369

- V4.1 ma osobną, fingerprintowaną ścieżkę runtime'u: recognition-only Paddle,
  stałą orientację runu, bounded lattice prior, batchowanie i checkpoint po
  pełnym prefiksie. Historyczne v1–v3 nadal wybierają własne adaptery.
- Rzeczywisty bounded pomiar `1/3/6/12` wybrał `sourceBatchSize=6`: medianowo
  około `6,23 źródła/s` dla OCR wobec `5,25` dla batcha 3. Jeden wewnętrzny
  batch Paddle nadal obejmuje najwyżej dziewięć cropów.
- Unknown nie jest kandydatem i nie przesuwa granic evidence span. Po restarcie
  audit odcina tylko niezatwierdzony suffix, a observation key oraz checkpoint
  zapobiegają duplikatom. V4.1 nie jest jeszcze domyślne; próby jakościowe i
  rollout pozostają zakresem TASK-0370.

### Exact proof środkowego rzędu v4.1 — TASK-0368

- Powstał niezależny komponent przyszłego
  `semi-automatic-range-only-ocr-v4-middle-row-triple-v2`: jednokrotna
  kanonizacja EXIF, bounded locator afinicznej siatki 3×3, dokładnie trzy cropy
  środkowego rzędu i fail-closed bramki kompletności oraz czytelności.
- `ExpectedRangeTable` i resolver dopuszczają `exact` tylko dla trzech kolejnych
  odczytów pasujących do dokładnie jednego oczekiwanego zakresu. Brak fuzzy,
  inferencji z nazwy, indeksu albo sąsiadów; częściowa strona bez pełnego
  środkowego rzędu pozostaje `unknown`.
- Dostępny rzeczywisty `seq_21169-21177.jpg` po EXIF wymagał ograniczonego
  rozszerzenia ROI i został zlokalizowany jako trzy kompletne, czytelne cropy.
  Produkcyjny Paddle, grouping, checkpoint i przełączenie runów pozostają
  zakresem TASK-0369; v1–v3 nie zmieniły zachowania.

### Numery końcowej częściowej strony `seq_*` — TASK-0366

- Produkcyjny adapter przypisuje teraz numery z poświadczonej nazwy również
  kompletnej stronie krótszej niż dziewięć plansz. `seq_499996-500000.jpg`
  daje deterministycznie numery `499996–500000` dla pozycji `0–4`.
- Niekompletna geometria nadal pozostaje do korekty i nie przesuwa numerów.
  Istniejące pięć rekordów gry `777` skorygowano atomowo na podstawie nazwy
  źródłowej; odbudowa projekcji zostanie wznowiona po zwolnieniu blokady
  trwających importów.
- `expectedBoardCount` zawsze wynika z `end - start + 1`, gdy istnieje
  poświadczony zakres. Fallback dziewięciu dotyczy tylko źródła bez zakresu;
  niepoprawny zakres kończy się fail-closed.

### Atomowy start browser stagingu — TASK-0365

- Nowy preflight geometrii albo import i przypięcie rekordu retencji stagingu
  są zapisywane w jednej transakcji. Usuwa to wzajemne oczekiwanie dwóch sesji
  na FK do jeszcze niezatwierdzonego joba.
- Idempotentne odzyskanie istniejącego joba nadal odświeża ochronę stagingu.
  Zakres `seq_*` pozostaje automatycznym źródłem sekwencji i liczby plansz;
  nie powstaje dodatkowy przycisk ani drugi workflow.

### Szybkie stronicowanie Weryfikacji symboli — TASK-0359

- Lista 500 cropów używa teraz wymuszonego `seek → owner check → hydrate`,
  dzięki czemu szerokie rekordy i JSONB nie są materializowane przed limitem.
- Cursor v3 zachowuje natywny UUID; istniejące scoped cursory v2 pozostają
  czytelne. Na bieżącej bazie pięć odczytów 500 rekordów zajęło
  `0.066–0.357 s` wobec wcześniejszych około `4.6–5.7 s` bez liczników.

### Liczniki poza krytyczną ścieżką — TASK-0360

- Odpowiedź listy cropów nie wykonuje już globalnych agregacji i nie zawiera
  liczników. Osobny endpoint zwraca snapshot liczników związany z dokładnym
  filtrem i `catalogRevision`.
- Admin renderuje metadane strony od razu, pobiera liczniki niezależnie bez
  nakładania requestów i ignoruje wyniki starego filtra. Błąd agregacji nie
  blokuje listy ani mutacji; skuteczna decyzja odświeża licznik z nowej rewizji.

### Stabilne atlasy Weryfikacji symboli — TASK-0361

- Zarówno plikowe cropy legacy, jak i wirtualne cropy źródłowe korzystają z
  jednego checksum-bound kontraktu atlasu WebP. Strona 500 rekordów tworzy
  najwyżej pięć deterministycznych grup po 100.
- Admin pobiera najpierw grupę widocznych kart, następnie sekwencyjnie pozostałe
  grupy. Klucz cache obejmuje pełną tożsamość cropa, więc powrót na stronę trafia
  w ten sam atlas, a zmiana rewizji wymusza nowy.
- Cache ma TTL 24 godziny i nie wykonuje pełnego skanu po każdym renderze;
  bounded pruning uruchamia się dopiero po przekroczeniu limitu 2 GiB.

### Podgląd A/B cropów — TASK-0362

- Weryfikacja symboli ma jawny wybór bieżących cropów v20/v19 albo
  eksperymentalnego renderera strukturalnego v0.10. Przełączenie nie zmienia
  projekcji ani danych gry.
- Tryb v0.10 jest tylko do odczytu i blokuje zaznaczenia oraz wszystkie mutacje.
  Komórki bez kompletnej proweniencji source-direct pokazują `Brak v0.10`, bez
  fallbacku do cropa legacy.
- API zwraca wersję i fingerprint renderera oraz dostępność per komórka. Tryb i
  wersja należą do klucza atlasu, dlatego oba warianty cache nie kolidują.

### Odbiór szybkiej Weryfikacji symboli — TASK-0363

- Na rzeczywistej stronie 500 oczekujących cropów metadane osiągnęły p95
  `1,110 s`, pierwszy atlas `0,488 s`, a komplet pięciu atlasów `2,209 s`.
- Powrót na stronę wykorzystał te same pięć content-addressed kluczy i zajął
  `0,085 s`; łączny rozmiar atlasów wyniósł `291 298 B`.
- Admin pozostaje ograniczony do trzech stron metadanych i wirtualnego okna
  kart. Liczniki są poza ścieżką krytyczną, a v0.10 pozostaje read-only.
- Szczegóły odbioru są w
  `ai_docs/quality/SYMBOL_REVIEW_FAST_PAGE_ACCEPTANCE.md`.

### Odebrany szeroki OCR zakresów v2 — TASK-0357/TASK-0358

- Nowe runy używają dedykowanego filtra małych etykiet i progresji
  `12/24/36`, zachowując niezmienioną bramkę minimum trzech zgodnych pozycji
  oraz pary sąsiadującej.
- Worker rozwiązuje v1 albo v2 z fingerprintu utrwalonego runu; historyczny v1
  pozostaje odtwarzalny, a nieznany kontrakt jest blokowany przed OCR.
- Próby 10/100 osiągnęły odpowiednio `7/10` i `68/100` dokładnych zakresów,
  zawsze z `0` fałszywych przypisań, `0` overlap i bez wywołań geometrii,
  croppera oraz symbol inference. Koszt próby 100 wyniósł `131.883438 s`,
  mediana `1.421131 s/JPEG`, a peak RSS `541708288 B`.
- Pełny raport jest w
  `ai_docs/quality/SEMI_AUTOMATIC_SELECTION_RANGE_OCR_V2_ACCEPTANCE.md`.
  Feature flag pozostaje domyślnie wyłączona do osobnej decyzji operatora.

### Adaptacyjne próby OCR zakresów v3 — TASK-0364

- Nowe runy przypinają `semi-automatic-range-only-ocr-v3`. Sam recognizer jest
  zgodny jakościowo z v2 (`12/24/36`, minimum trzy pozycje, para sąsiednia,
  confidence `0.90`); zmienia się wyłącznie harmonogram wywołań.
- Thumbnailowy deskryptor wybiera mocne granice, a próba co piąte źródło
  ogranicza ryzyko pominięcia subtelnej zmiany. Pominięty JPEG jest jawnie
  `unproven` i nie może utworzyć zakresu.
- Scheduler i grouping mają wspólny trwały prefiks. Checkpoint v3 jest bounded
  do 10 źródeł, więc restart nie zmienia kontraktu ani nie powtarza już
  zatwierdzonych prób.
- Golden 10/100 zachował `7/10` i `68/100` exact oraz zero fałszywych
  przypisań. Modelowa seria 10 rzeczywistych ekranów po 10 ujęć osiągnęła
  `3,30 JPEG/s`; rzeczywisty fragment 200 zdjęć osiągnął `7,30 JPEG/s`.
  Projekcja dla 42 000 zdjęć wynosi około `1 h 36 min–3 h 32 min`, zależnie od
  udziału wymagających prób. Flaga rolloutowa nadal pozostaje wyłączona.

### Kontrakty półautomatycznej selekcji zakresów — TASK-0350

- TASK-0350 tworzy czysty, niezależny od gry kontrakt `seq-inclusive-v1` dla
  przyszłego półautomatu. Zakresy są dodatnie i inkluzywne, pełny zakres ma
  obecnie dziewięć plansz, a ostatnia strona może być krótsza.
- `RangeEvidenceGate` ocenia wyłącznie lokalny dowód OCR dokładnego zakresu
  względem expected ranges. Nie uruchamia ani nie ocenia geometrii, plansz,
  cropów, symboli, ostrości, ekspozycji czy refleksów.
- Sam kontrakt TASK-0350 nie zależy od adaptera OCR, stagingu, migracji, joba,
  API ani UI. Późniejsze taski dokładają te warstwy bez rozszerzania domeny.

### Range-only OCR półautomatycznej selekcji — TASK-0351

- Adapter `semi-automatic-range-only-ocr-v1` wykorzystuje istniejący
  Paddle/proof-first OCR przez port przyjmujący wyłącznie RGB. Bridge przekazuje
  pusty zestaw plansz, więc workflow nie uruchamia geometrii, croppera ani
  symbol inference i nie ma bramki jakości obrazu.
- Tylko mocny pozycyjny proof może dać `exact_range`; końcowy krótszy zakres
  wymaga trzech zgodnych obserwacji mieszczących się w jego granicach.
- Checksumowany rzeczywisty korpus wyznacza wersjonowany maksymalny odstęp `160`
  źródeł bez proof. Silnik TASK-0353 konsumuje tę politykę bez dodawania oceny
  wyglądu plansz.

### Globalny run półautomatycznej selekcji — TASK-0352

- Migracja `0087` utrwala globalny run i jego oczekiwane zakresy bez
  przypisania do gry. Idempotencja obejmuje cały kontrakt stagingu, granic,
  kierunku i wersji algorytmów.
- Purpose `semi_automatic_selection` przechowuje naturalnie uporządkowane
  JPEG-i, checksumę manifestu i fingerprint źródła. Restart API nie traci
  stagingu ani runu; zmieniony manifest lub asset jest blokowany fail-closed.
- Lokalne API udostępnia capabilities, lifecycle runu, listę zakresów,
  diagnostykę, assety i checksum-bound acknowledgement outputu. Run używa
  istniejącego selection lane.
- Rollout jest domyślnie wyłączony flagą
  `GAME_PREDICTOR_ENABLE_SEMI_AUTOMATIC_IMAGE_SELECTION=false`.

### Deterministyczny silnik półautomatycznej selekcji — TASK-0353

- Istniejący lane selekcji obsługuje teraz także globalny job
  `semi_automatic_image_selection`; general worker nadal go nie przejmuje.
- Scanner wykonuje range-only OCR raz na JPEG, grupuje wyłącznie dokładne
  lokalne dowody i zapisuje strumieniowe JSONL oraz atomowy checkpoint.
- Wybór środka nie ocenia geometrii ani jakości plansz. Brak proof pozostaje
  luką, a duplikat lub zakres poza kolejnością jest diagnostyką bez podmiany
  pierwszego trwałego właściciela.
- Pauza i restart wznawiają ostatni zatwierdzony prefiks bez ponownego OCR.
  Zakończona analiza przechodzi do `waiting_for_review`; zapis lokalnego outputu
  pozostaje zakresem TASK-0354.

### Lokalny output i recovery półautomatycznej selekcji — TASK-0354

- Admin zapisuje wybrane źródła jako niezmienione `seq_<start>-<end>.jpg` i
  potwierdza zakres do API dopiero po lokalnym read-backu SHA-256.
- Manifest outputu v1 jest związany z runem, źródłem, pełnym snapshotem
  zakresów i fingerprintami. Inny run lub zmieniony plik docelowy blokuje
  zapis bez silent overwrite.
- Jedna trwała pending operation pozwala wznowić awarię przed albo po zapisie
  JPEG-a. Ponowienie nie pobiera ponownie zgodnego pliku i może bezpiecznie
  dokończyć samo acknowledgement.
- IndexedDB przechowuje tylko uchwyty katalogów i mały stan UI; obrazy nie są
  utrwalane w przeglądarce. Konfigurator i ekran progresu pozostają zakresem
  TASK-0355.

### Konfiguracja i postęp półautomatycznej selekcji — TASK-0355

- Admin ma niezależny od gry workspace `Półautomatyczny wybór zdjęć`. Odczytuje
  capabilities API przed odblokowaniem konfiguracji; jedna flaga serwerowa
  steruje dostępnością i UI nie wysyła mutacji, gdy funkcja jest wyłączona.
- Operator wybiera źródłowy katalog JPEG oraz lokalny katalog docelowy, podaje
  dodatnie granice i kierunek. Skan źródła jest naturalnie uporządkowany, upload
  używa purpose `semi_automatic_selection`, a postęp pokazuje potwierdzone pliki
  i bajty oraz umożliwia bounded retry albo anulowanie.
- Po finalizacji Admin tworzy lub odzyskuje idempotentny globalny run. Lokalny
  klucz i operator-local IndexedDB przywracają run oraz uchwyty po reloadzie.
  Sekwencyjny polling pokazuje etap i liczniki oraz udostępnia trwałe
  pause/resume/cancel bez nakładających się requestów.
- Końcowy review i ręczna edycja nie są jeszcze eksponowane; pozostają zakresem
  TASK-0356.

### Review i ręczna edycja półautomatycznej selekcji — TASK-0356

- Ukończony run otwiera pełny, keysetowo pobrany przegląd expected ranges po
  lokalnej synchronizacji automatycznych wyborów. Postęp zapisu jest widoczny,
  a nieciągły snapshot blokuje mutację.
- `REVIEW MODE` nawiguje po zakresach, natomiast `EDIT SOURCE MODE` blokuje
  zakres i nawiguje po źródłowych JPEG-ach we wspólnym viewerze. Luka zaczyna
  po poprzednim wyborze, a zastąpienie od dokładnego zapisanego indeksu.
- Ręczne dodanie i zastąpienie zachowują oryginalne bajty, journal recovery i
  ochronę przed silent overwrite. Acknowledgement wiąże rewizję z ponownie
  zweryfikowanym źródłem stagingu przez opcjonalny `sourceIndex`.
- TASK-0357 pozostaje odpowiedzialny za rollout flagi i odbiór na rzeczywistych
  katalogach 10/100 zdjęć.

### Częściowa geometria ostatniej strony — TASK-0349

- Lista ręcznej korekty zwraca `expectedBoardCount` wyliczony z poświadczonej
  nazwy `seq_<start>-<end>`. Dla `seq_499996-500000.jpg` Admin prowadzi przez
  dokładnie pięć plansz zamiast wymuszać dziewięć.
- API, append-only override, preflight i produkcyjny adapter obsługują aktywny
  prefiks 1–9 quadów w kolejności row-major. Backend ponownie sprawdza liczbę
  względem manifestu stagingu; częściowa strona nie może zostać globalną
  kotwicą dla innych zdjęć.
- Migracja `0086_partial_page_geometry_overrides` luzuje wyłącznie constraint
  długości JSONB z dokładnie 9 do zakresu 1–9. Istniejące rewizje pozostają
  niezmienione, a pełne strony nadal używają dziewięciu quadów i 36 uchwytów.

### Wznowienie malejącej zdalnej selekcji ręcznej

- Manifest operator-local zapisuje teraz jawną semantykę naturalnego porządku
  źródła. Ponowne wskazanie folderów albo wznowienie pod nowym linkiem nie może
  odwrócić działania `→`/Enter dla kierunku `malejąco`.
- Historyczny manifest bez znacznika jest naprawiany od następnego naturalnego
  zdjęcia po ostatniej zaakceptowanej decyzji; `skipped` zmienia wyłącznie
  zakres i nie przesuwa punktu wznowienia zdjęć.

### Widoczny postęp browser uploadu — TASK-0348

- Admin pokazuje postęp przesyłania na podstawie liczników potwierdzonych przez
  API, a nie wyłącznie lokalnego indeksu pętli.
- Po pierwszym pliku i następnie co 25 plików klient jawnie oddaje sterowanie
  przeglądarce, aby duża seria szybkich requestów nie blokowała odmalowania
  licznika na wartości `0/N`.

### Czytelne liczniki ręcznej geometrii — TASK-0347

- Preflight i panel korekty opisują liczniki jako zdjęcia źródłowe. Plansze
  powstają po dziewięć na zdjęcie dopiero w późniejszym imporcie.
- Panel rozróżnia odroczone zdjęcie od ponownej korekty geometrii, która była
  już zarejestrowana. Ta druga zmienia quady, ale zgodnie z domeną nie zwiększa
  licznika zarejestrowanych źródeł.
- Regresja workera potwierdza, że jeden snapshot partii stosuje wszystkie
  zapisane override'y, a nie wyłącznie ostatni.

### Edycja wszystkich narożników po wyznaczeniu plansz — TASK-0346

- Zakończenie trybu osobnego wyznaczania dziewięciu plansz automatycznie
  przełącza korektę na `Wszystkie plansze — 36 narożników`, zamiast pozostawiać
  aktywne uchwyty tylko planszy 1.
- Dziewięć niezależnych quadów jest bezstratnie mapowanych na istniejącą siatkę
  6 × 6. Ponowne wybranie tego zakresu zachowuje bieżące obrysy, odstępy i
  krzywiznę; nie odtwarza ich z czterech narożników całej strony.

### Osobne wyznaczanie dziewięciu plansz — TASK-0345

- Korekta geometrii strony ma dodatkowy prowadzony tryb, w którym operator
  wskazuje LT → PT → PD → LD osobno dla każdej z dziewięciu plansz.
- Plansze są zbierane w domenowej kolejności row-major: 1–3, 4–6, 7–9. Każdy
  poprawny obrys jest od razu widoczny, a niepoprawny lub przestawiony quad
  blokuje przejście dalej i można go cofnąć jednym punktem.
- Wynik korzysta z istniejącego zapisu dziewięciu finalnych quadów. Nie zmienia
  API, numeracji `seq_*`, preflightu ani source-direct croppera; wcześniejsze
  tryby obrysu strony, krzywizny i pojedynczej planszy nadal działają.

### Selekcja cropów między stronami — TASK-0344

- Weryfikacja symboli zachowuje jawne, checksum-bound zaznaczenie przy
  przejściu między stronami keysetowymi. Operator może połączyć do 10 000
  cropów z wielu stron po 500 w jeden job masowy.
- Zmiana filtra, jawne wyczyszczenie albo przekazanie operacji nadal czyści
  selection. Pomyślna operacja ukrywa wszystkie jej jawne targety również po
  powrocie do wcześniej odwiedzonej strony.

### Zoom korekty geometrii — TASK-0343

- Viewport korekty strony używa wspólnego modelu `fit to viewport` ręcznej
  selekcji i pozwala powiększyć obraz od 100% do 3000% co 25%.
- Powiększony obraz jest przewijany w obu osiach, a kliknięcia i przeciąganie
  nadal zapisują współrzędne źródłowego JPEG-a. Przycisk procentu wraca do
  dopasowania 100%; zoom nie zmienia resetu ani zapisanej geometrii.

### Elastyczna korekta pełnej strony — TASK-0342

- Edytor ręcznej geometrii strony prowadzi przez narożniki LT → PT → PD → LD,
  blokuje skrzyżowany obrys i generuje dziewięć rozdzielonych ramek z 36
  niezależnych punktów krawędzi. Pozwala to odwzorować perspektywę, odstępy i
  łuk ekranu bez wymuszania prostokątnej, stykającej się siatki.
- `Reset` przywraca geometrię widoczną przy otwarciu zdjęcia. Kolejne poprawki
  można zapisywać bez uruchamiania preflightu, a następnie wysłać całą partię
  jedną akcją. Istniejące ręczne override'y pozostają edytowalne i audytowalne.
- Lokalny Reviewer rozpoznaje importy z odroczoną, niepełną geometrią i pozwala
  przełączyć się do istniejącego edytora operacyjnego; zdalny scope nie został
  rozszerzony.

### Stabilizacja korekty ręcznej selekcji — TASK-0341

- Wspólny viewer zachowuje pozycję obrazu pomiędzy przejściami także wtedy,
  gdy loading chwilowo redukuje zawartość viewportu. Techniczne zdarzenie
  scrolla dla nieaktualnego Object URL nie może już nadpisać pozycji zerem.
- Fill, delete, undo i restore aktualizują lokalny snapshot jednego pliku bez
  ponownego hashowania całego katalogu po każdej operacji. Pełny audyt nadal
  odbywa się przy otwarciu/reloadzie, a usuwany plik nadal wymaga SHA-256.
- Drift istniejącego output manifestu pozostaje fail-closed i otrzymuje
  czytelny komunikat; aktualna check­suma nie jest przyjmowana automatycznie.

### Korekta ręcznej selekcji — TASK-0336

- `v0.10.29` wydziela wspólny viewer lokalnych zdjęć: bounded cache bieżącego
  okna, zoom 100–3000%, fullscreen oraz pamięć pionowego scrolla.
- Dotychczasowy lokalny selector korzysta z nowego komponentu bez zmiany
  manifestów, skrótów ani operacji plikowych. Jest to fundament niezależnej
  sekcji `Popraw selekcję`; manifest i mutacje korekty powstaną w TASK-0337.

### Domena korekty ręcznej selekcji — TASK-0337

- `v0.10.30` dodaje lokalny repair manifest v1, walidację top-level plików
  `seq_*`, trwałe granice kolekcji oraz deterministyczne luki do dziewięciu
  plansz. Błędna nazwa JPEG-a, duplikat, overlap lub drift checksummy blokują
  mutację fail-closed.
- Osobna IndexedDB v1 zapisuje wyłącznie uchwyty, tryb, kursory, zoom, scroll i
  skok. JPEG-i nie są utrwalane w bazie przeglądarki. Operacja oczekująca jest
  finalizowana po restarcie na podstawie obecności pliku i SHA-256.

### Uzupełnianie luk ręcznej selekcji — TASK-0338

- `v0.10.31` dodaje lokalny workspace uzupełniania wykrytych luk z katalogu
  bazowego tylko do odczytu. Nawigacja zdjęć ma skoki 1/2/5/10/20/50/100, a
  targety przechodzą po rzeczywistych lukach zamiast mechanicznego `start+9`.
- Enter/F zapisuje oryginalne bajty pod dokładnym `seq_<start>-<end>.jpg`,
  weryfikuje SHA-256 i aktualizuje repair/output manifest oraz trace. Akceptacja
  jest dostępna po 300 ms rzeczywistej widoczności; ostatni fill można cofnąć
  bez usuwania obcego albo zmienionego pliku.

### Usuwanie ręcznie wybranych sekwencji — TASK-0339

- `v0.10.32` dodaje tryb przeglądania `seq_*` ze stałym skokiem 1. F i jawny
  przycisk usuwają dokładny, checksummowany JPEG oraz aktualizują trwałą listę
  luk i oba manifesty.
- Wyłącznie ostatni usunięty Blob pozostaje w pamięci otwartej karty. A/Ctrl+A
  przywraca go pod pierwotną nazwą po kontroli kolizji i SHA-256; reload albo
  następne usunięcie bezpowrotnie usuwa wcześniejszą możliwość restore.

### Finalizacja korekty ręcznej selekcji — TASK-0340

- `v0.10.33` montuje kartę `Popraw selekcję` bezpośrednio pod lokalnym
  selektorem i chroni naprawiany katalog przed ponownym przejęciem przez zwykły
  start albo resume.
- Output manifest jest jedynym źródłem aktywnych wyborów. Ranker opcjonalnie
  scala widoczne repair fill z pierwotnym trace, lecz ignoruje delete/restore i
  nie może uznać za pozytyw pliku usuniętego z outputu.
- Workflow pozostaje operator-local: bez API, migracji bazy i Blobów w
  IndexedDB. Wymagania, architektura oraz D-276 opisują recovery, checksumy i
  jednopoziomowe przywracanie delete.

### Fundament 0.10 — TASK-0307

- `v0.10.0` definiuje wyłącznie czysty kontrakt przyszłej wirtualnej geometrii.
  Parser `seq_*` używany przez API i worker waliduje jeden ciągły zakres
  `1..9`; jego aktywne sloty są zawsze prefiksem row-major strony 3 × 3, więc
  częściowa ostatnia strona nie może zawierać dziury między planszami.
- Nowe typy opisują współrzędne RGB po pojedynczej normalizacji EXIF,
  wypukły source quad bez wymagania prostokąta, geometrię aktywnej planszy oraz
  geometry-bound render spec komórki. Nie ma jeszcze migracji, endpointu,
  flagi runtime, pipeline'u OpenCV ani zapisu nowych cropów.
- Logical identity komórki jest niezależne od rewizji geometrii; render identity
  wiąże źródło, topologię, quad, rewizję i konfigurację bezpośredniego
  renderowania. Następny task wykorzysta te kontrakty do addytywnego schematu
  i bezpiecznej ścieżki kompatybilności.

### Trwałość wirtualnej geometrii — TASK-0308

- `v0.10.1` dodaje migrację `0082_virtual_geometry_foundation`, lecz nie
  aktywuje nowego pipeline'u. Istniejące plansze, cropy, review i kohorty
  pozostają w trybie `legacy_file`; stan każdej gry domyślnie wynosi
  `legacy` / `legacy_files`.
- `source_images` może zapisać kompletny, all-or-none opis współrzędnych RGB po
  EXIF. Append-only `image_source_geometry_revisions` wiąże źródło, attested
  zakres i sloty, topologię, silnik, quady oraz checksumy bez binariów.
- Dual-schema pozwala przyszłemu rekordowi `virtual_source` nie mieć ścieżki
  pliku, ale wymaga source geometry, logical cell key, render spec, extractor
  version i rendered-pixel SHA-256. Dotychczasowe repozytoria legacy odrzucają
  taki rekord fail-closed do czasu ich jawnego przełączenia w kolejnych
  taskach.
- Backfill rolloutów jest idempotentny i ograniczony do 200 gier na partię
  (maksymalnie 500); nie skanuje obrazów ani wielomilionowych tabel cropów.
  Lokalna baza użytkownika została zaktualizowana przez
  `0082_virtual_geometry_foundation` i
  `0083_image_geometry_rollout_backfill_job_type` 2026-08-29. Stan gier
  pozostał domyślnie `legacy` / `legacy_files`; druga migracja jedynie dodaje
  wartość enum wymaganą przez ogólny worker i nie zmienia danych obrazów.

### Source-direct renderer wirtualnych komórek — TASK-0309

- `v0.10.2` dodaje `CanonicalSourceLoader`, który weryfikuje SHA-256 managed
  original, dekoduje JPEG raz na bieżące wykonanie, stosuje EXIF Orientation
  1–8 dokładnie raz i zwraca niemodyfikowalne RGB `uint8` wraz z checksumą
  pikseli. Loader nie zapisuje pełnowymiarowego PNG.
- `VirtualCellRenderer` konsumuje kontrakty TASK-0307 i wykonuje jeden
  source-direct `warpPerspective` na każdą komórkę. Zwraca piksele wyłącznie w
  pamięci, logiczny klucz, niezmienny render spec, jego checksumę oraz checksumę
  wynikowych pikseli. Przed pierwszym warpem waliduje komplet całej partii i
  pełne pokrycie źródła.
- Produkcyjnym kontraktem przyszłego rolloutu jest wariant B — bezpośrednia
  perspektywa źródło→komórka. Warianty A (native bounding box) i C (pośrednio
  wyprostowana plansza) istnieją wyłącznie jako diagnostyka A/B/C w pamięci.
- Historyczny `board-cell-crops-v19-multi-point-source-direct-fixed-padding-v1`
  nie został zmieniony. Test regresyjny potwierdza dokładną zgodność pikseli B
  z v19 dla 15 pól. TASK-0309 nie podłącza nowego renderera do pipeline'u, bazy,
  API ani rolloutu gry.

### Globalna inicjalizacja Structured OpenCV — TASK-0310

- `v0.10.3` dodaje wyłącznie globalny etap
  `structured-opencv-global-initialization-v1`. Wejście jest związane z
  kanonicznym RGB, topologią i attested prefiksem slotów; wynik nie zawiera
  finalnej geometrii plansz i nie uruchamia croppera.
- Profil zatwierdzonych stron używa ORB/RANSAC na obrazie 50% i wybiera anchor
  deterministycznie po inlierach, ratio, błędzie oraz checksumie. Dotychczasowy
  `VerifiedPageRegistrar.register()` zachowuje pełną walidację czerwonych ramek
  i kontrakt produkcyjny.
- Cold start bez profilu łączy czerwone ramki, gradienty grayscale oraz LSD,
  dopasowuje wyłącznie oczekiwane aktywne sloty i zwraca początkowe ROI.
  Niewystarczający dowód kończy się `needs_manual_review` bez syntetycznych
  pozycji i bez częściowego rezultatu.
- Golden testy obejmują pełne i częściowe strony, różne perspektywy, obie
  strategie, deterministyczność oraz fail-closed bez dowodu. Integracja
  pipeline'u, finalny local line refinement, UI i rollout pozostają poza
  TASK-0310.

### Niezależne dopracowanie plansz — TASK-0311

- `v0.10.4` dodaje lokalny refiner LSD dla każdej aktywnej planszy osobno.
  Tymczasowa rektyfikacja służy wyłącznie analizie sześciu pionowych i czterech
  poziomych linii; finalny quad wraca do współrzędnych źródła i nie jest
  wymuszany do prostokąta w zdjęciu.
- Hard gates wymagają granic zewnętrznych, co najmniej 5/6 pionów, 3/4
  poziomów, 18/24 przecięć, p95 reprojekcji do 2,5 px na skali 50%, pełnego
  source support, zachowania row-major i braku nakładania. Niepełny dowód daje
  stabilny reason code i korektę ręczną zamiast false-success.
- Osiem składników confidence jest całkowicie niezależnych od modelu symboli.
  Wynik źródła jest checksumowany i agreguje najgorszy status niezależnych
  slotów. Testy obejmują glare, mocną okluzję/rękę, brak linii, overlap,
  kolejność oraz historyczny obraz false-success.
- TASK-0311 nie zmienia pipeline'u v20, bazy, API, UI, croppera ani rolloutu.
  Produkcyjna integracja pozostaje odroczona.

### Integracja wirtualnej geometrii z pipeline'em — TASK-0312

- `v0.10.5` przypina do każdego nowego joba niezmienny snapshot rolloutu gry:
  tryb geometrii, tryb assetów komórek, rewizję oraz wersje silnika,
  renderera i preprocessingu. Brak stanu gry pozostaje dokładnie historycznym
  `legacy` / `legacy_files`; fingerprint starego joba nie zmienia się.
- `structured_shadow` zachowuje legacy jako wynik domenowy i dual-write'uje
  źródłową geometrię oraz odrębną prediction revision z pełną proweniencją
  virtual. `structured_review` zapisuje geometrię do ręcznej walidacji bez
  inferencji, a `structured_default` używa wyłącznie zweryfikowanych slotów
  Structured OpenCV i wirtualnych komórek.
- Wariant virtual dekoduje managed original raz w ramach wykonania, renderuje
  maksymalnie 9 × 15 komórek w pamięci, tworzy jeden tensor NCHW i wykonuje
  jedno wywołanie ONNX dla całego źródła. Nie zapisuje board ani cell PNG;
  rekordy `recognized_boards` i `cell_observations` korzystają z
  `virtual_source`, source geometry revision, render specu i checksummy
  dokładnych pikseli.
- Restart odtwarza piksele z managed original i porównuje render spec oraz
  pixel checksum ze stage checkpointem. Rozbieżność kończy się fail-closed;
  identyczny replay nie tworzy drugiej geometrii ani prediction revision.
- Rozstrzygnięte przez człowieka numery pozostają chronione przez canonical
  ownership przed projekcją automatu. Legacy Reviewer nadal nie serwuje
  wirtualnych assetów; lokalny Admin korzysta z bounded rendering podglądów
  wdrożonego przez TASK-0313.

### Bounded podglądy komórek wirtualnych — TASK-0313

- `v0.10.6` udostępnia lokalnemu Admin API batch maksymalnie 100 aktualnych
  komórek `virtual_source`. Żądanie zawiera oczekiwaną rewizję i checksumę
  render specu; wynik jest checksumowanym atlasem WebP z deterministycznym
  deskryptorem tile'ów oraz czasem wygaśnięcia.
- `VirtualCellPreviewService` dekoduje managed original najwyżej raz na źródło
  w batchu, waliduje current geometry/source geometry/spec/pixel provenance i
  renderuje direct-perspective preview bez trwałych cropów. Legacy PNG/JPEG
  pozostaje obsługiwany niezmienionym endpointem assetu.
- Atlas pozostaje wyłącznie odtwarzalnym cache'em
  `data/working/virtual-preview-cache-v1`: 15 minut TTL, 2 GiB LRU,
  process-local single-flight i brak rekordów domenowych lub binariów w bazie.

### Weryfikacja geometrii całego źródła — TASK-0314

- `v0.10.7` rozszerza wyłącznie lokalny Reviewer o source-scoped workspace
  geometrii. Anchor kolejki nadal ma bounded keyset po jednej pozycji, a po
  odczycie jego `sourceImageId` klient pobiera maksymalnie dziewięć aktywnych,
  row-major slotów tego samego zdjęcia. Cursor jest związany także z opcjonalnym
  filtrem źródła; zdalny proxy Reviewera nadal nie udostępnia tej powierzchni.
- Canvas pokazuje pełny EXIF-oriented asset, quady wszystkich aktywnych plansz,
  linie topologii, numery slotów, confidence i reason codes. Operator wybiera
  jeden quad, korzysta z drag narożników lub całej siatki, undo/resetu do
  automatu oraz nietrwałego porównania A/B source-direct cropów. Overlay ani
  preview nie są zapisywane jako JPEG.
- Akceptacja i odrzucenie wykonują checksum-bound, revision-bound mutacje dla
  kompletu aktywnych plansz źródła z blokadą podwójnego submitu. Workspace
  pokazuje oddzielne liczniki globalnej kolejki i bieżącego źródła. Legacy
  zapis ręcznej korekty zachowuje istniejący workflow oraz przechodzi do
  następnego źródła; ręczny zapis `virtual_source` jest celowo fail-closed,
  aby nie zastąpić proweniencji wirtualnej fizycznymi cropami przed backfillem
  i walidacją TASK-0317.

### Wirtualizowana Weryfikacja Symboli — TASK-0315

- `v0.10.8` zachowuje keysetową nawigację po stałych stronach 500 cropów, ale
  Admin renderuje wyłącznie viewport i mały overscan przez
  `@tanstack/react-virtual`. Metadane są ograniczone do bieżącej strony oraz
  maksymalnie dwóch sąsiednich; jedyny prefetch pobiera kolejną stronę bez
  assetów.
- Wirtualny renderer żąda checksum-bound atlasu wyłącznie dla aktualnie
  widocznych kart `virtual_source`, maksymalnie 100 komórek. Legacy assety
  zachowują dotychczasowy lazy thumbnail. W DOM ani w pamięci nie powstaje
  zestaw 500 obrazów, a tym bardziej lista 10 000 obrazów.
- Filtr confidence (`niska`, `średnia`, `wysoka`) jest częścią zapytania,
  cursorów i snapshotu masowej operacji. Operator może wybrać bieżącą stronę
  jawnie albo wszystkie wyniki filtra przez snapshot rewizji katalogu i
  ograniczone `excludedIds`; pojedyncza jawna decyzja nadal nie tworzy joba.
- D-241 została zastąpiona przez D-259. Zdalny Reviewer pozostaje poza nową
  powierzchnią lokalnego Admin API.

### Bezpieczny rollout wirtualnej geometrii — TASK-0317

- `v0.10.9` dodaje trwały job `image_geometry_rollout_backfill` w general lane.
  Waliduje najwyżej 100 źródeł na transakcję, zapisuje source cursor i stany
  `not_started/processing/ready/failed`; drugi start aktywnego joba jest
  idempotentny. Nie konwertuje legacy ani nie zmienia trybu rolloutu gry.

### Finalny cutover wirtualnej geometrii — TASK-0318

- Domena koduje fail-closed bramkę odbiorczą: minimum 100 źródeł, 500 aktywnych
  plansz, pięć bucketów, komplet historycznych błędów, holdout i gotowa
  walidacja proweniencji. Tylko board-level `>=98%` rekomenduje
  `structured_default/virtual_default`; `95–98%` pozostaje w review, a `<95%`
  utrzymuje legacy i może uzasadnić TASK-0319.
- Audyt nie znalazł kompletnego raportu 0.10, a Outcome TASK-0317 potwierdza,
  że operacyjnego backfillu nie uruchamiano. Decyzja odbiorcza brzmi
  `insufficient_evidence`: żaden tryb gry ani domyślny engine nie został
  promowany, a TASK-0319 nie został uruchomiony bez rzeczywistego wyniku `<95%`.
- Legacy cropy, aliasy Reviewera, source geometry i dual-schema pozostają.
  Raport `V0_10_VIRTUAL_GEOMETRY_CUTOVER.md` opisuje pełny rollback operacyjny;
  nie wykonuje się destrukcyjnego downgrade'u 0082 po pojawieniu się danych
  `virtual_source`.
- Bramka sprawdza kanoniczne metadane RGB, pełną source geometry, obserwacje,
  bieżące komórki i manualne rewizje `virtual_source`. Po walidacji odtwarza
  compact candidate/fast document aktualnego właściciela, dzięki czemu lokalna
  kolejka geometrii nie zależy od historycznego board PNG.
- Lokalny Reviewer może po stanie `ready` wykonać preview i zapis ręcznej
  geometrii virtual. Obie ścieżki renderują komórki source-direct w pamięci;
  zapis utrwala tylko append-only source/board revision, render specy i
  checksumy. Etykiety człowieka pozostają, ale nowa tożsamość pikseli nie jest
  treningowa do czasu ponownego zatwierdzenia cropa.

### Eksperymentalny fallback geometrii keypoint — TASK-0319

- Bezpośrednie polecenie właściciela uruchomiło bounded eksperyment mimo braku
  raportu `<95%`; D-261 nadal blokuje automatyczną aktywację i zmianę rolloutu.
- Zamrożony dataset dopuszcza wyłącznie ręcznie zatwierdzone quady i dzieli dane
  deterministycznie według source family bez przecieku między train,
  validation i test.
- Mały model CPU przewiduje `9 × 4` heatmaps oraz obecność slotów. Eksport ONNX
  jest checksum-bound, sprawdza parity z PyTorch i ma jawny, bounded pomiar
  czasu po warm-upie.
- Dekoder respektuje active-slot maskę z poświadczonego zakresu `seq_*`, a
  niepełna obecność i nieprawidłowy quad kończą się fail-closed. Finalne quady
  przechodzą przez ten sam lokalny refiner i hard gates co Structured OpenCV.
- Nie dodano migracji, API ani połączenia z produkcyjnym workflow. Shadow runner
  nie może zastąpić primary result, trenować na danych użytkownika ani zmienić
  stanu gry.

### Ograniczenie zużycia dysku — TASK-0306

- Rozpoczęto pion `v0.9.16–v0.9.23`. Retencja odtwarzalnych danych wynosi
  24 godziny, a domyślne progi wolnego miejsca to: ostrzeżenie 80 GiB,
  automatyczny GC 60 GiB, cel po GC 80 GiB i twarda rezerwa 30 GiB.
- TASK 1 definiuje deterministyczną kwalifikację bez fizycznego usuwania.
- TASK 2 (`v0.9.17`) przełącza nowe joby na normalizację w pamięci bez trwałego
  `normalized.png`; historyczny v1 pozostaje odtwarzalny fail-closed.
- TASK 3 utrwala `ready → in_use → ingested` dla browser stagingu. `ingested`
  wymaga zweryfikowanych kopii wszystkich źródeł w managed originals i zapisuje
  24-godzinny termin retencji. Fizyczne usuwanie nadal jest wyłączone do czasu
  wdrożenia GC oraz zatwierdzenia pierwszego preview.
- TASK 4 udostępnia niezmienny dry-run oraz trwały job `storage_gc` z
  rewalidacją ścieżek, zależności, rozmiaru, mtime i fingerprintu. Destrukcja
  korzysta z same-volume trash i markerów recovery; żaden run nie został
  automatycznie uruchomiony na obecnych danych.
  `storage_gc_runs` wiąże przyszły job z niezmiennym manifestem kandydatów,
  `storage_usage_snapshots` przechowuje bounded pomiary, a
  `browser_selection_retention_states` przygotowuje trwały lifecycle stagingu.
- TASK 5 chroni upload i wykonanie pipeline'u progami per unikalny wolumin.
  Automatyczny GC jest idempotentny, ma pierwszeństwo w general lane, a job
  obrazowy przy presji zapisuje etap `waiting_for_storage` i oddaje lease bez
  utraty checkpointu. Wznowienie wymaga osiągnięcia celu 80 GiB.
- TASK 6 dodaje główny workspace Admina `Pamięć i czyszczenie`. Pełny skan
  katalogów działa jako idempotentny job `storage_inventory` w general lane i
  zapisuje trwały snapshot; zwykły GET nie skanuje drzewa plików. Panel pokazuje
  woluminy, PostgreSQL, przestrzenie nazw, presję miejsca oraz checksum-bound
  dry-run i postęp GC. Po poprawnym odbiorze TASK 8 automatyczne usuwanie jest
  domyślnie aktywne; `observe_only` pozostaje jawnym trybem diagnostycznym.
- TASK 7 (`v0.9.22`) dodaje bounded kompakcję odtwarzalnych payloadów
  `board_cell_geometry`, `board_crops`, `sequence_ocr` i `symbol_inference`.
  Niezmienny manifest terminalny zachowuje wersje adapterów, checksumy etapów
  oraz identyfikatory finalnych wyników. `discovery`, `normalization` i
  `board_detection` pozostają, ponieważ nadal uczestniczą w retry i korekcie
  geometrii. Kompakcja jest osobnym, wznawialnym jobem. Pierwszy run zakończył
  się dla 25 899 wykonań bez konfliktów.
- Pierwszy dry-run kompakcji v2 zakończył się bez modyfikacji danych: 25 899
  wykonań, 89 639 późnych payloadów i 3 095 375 375 bajtów logicznego JSON.
  Serwerowy SHA-256 ograniczył czas raportu do około 71 sekund. To nie jest
  prognoza fizycznego zmniejszenia VHDX; `VACUUM (ANALYZE)` udostępni strony
  PostgreSQL do ponownego użycia, ale nie kurczy pliku dysku.
- Bounded inventory po cleanupie zakończył się pomiarem 7/7 przestrzeni.
  `working` spadło z 85 995 384 923 B do 23 803 702 034 B. Chronione cropy
  (65 904 043 884 B), staging (11 141 120 426 B), originals
  (10 211 507 189 B), modele (115 224 119 B) i training (22 404 184 B)
  pozostały bez zmian. Wolne miejsce wzrosło do około 97,54 GiB. Snapshot
  inwentarza jest publikowany dopiero po zapisaniu terminalnego wiersza bazy,
  a skan po restarcie wznawia się od następnej przestrzeni nazw.
- Zatwierdzony run GC `9e67b906-b04f-48c7-9719-1d608ade7511` usunął
  39 514 historycznych bitmap normalizacji i odzyskał 62 191 682 889 B.
  Jeden plik zmieniony po preview pozostał jako konflikt, bez błędów usuwania.
  13 073 chronione obserwacje oraz 16 historycznych stagingów pozostały na
  dysku. Automatyczne GC jest aktywne po poprawnym odbiorze; oryginały,
  referencjonowane cropy, modele, dane treningowe i aktywne joby są chronione.
- `v0.9.17` przełącza nowe importy na normalizację RGB w pamięci. Stage result
  nie wskazuje `normalized.png`; przechowuje źródło, orientację, wymiary i
  checksumę pikseli. Historyczne joby bez snapshotu adaptera nadal używają v1
  i potrafią fail-closed odbudować brakującą bitmapę z managed original.

### Odbiór wersji 0.9 — TASK-0304

- Commity `v0.9.1–v0.9.13` rozdzielają zatwierdzoną etykietę symbolu,
  jakość cropa, proweniencję pikseli oraz zatwierdzenie geometrii. Lokalny
  Reviewer zawsze otwiera nowy workflow walidacji siatki; ograniczony zdalny
  Reviewer zachowuje istniejący kontrakt bez rozszerzenia uprawnień.
- Robocza baza jest na migracji `0075`. Bounded, wznawialny backfill zakończył
  się stanem `ready` dla `397 976` plansz i `3 572 295` komórek: zero braków
  topologii, zatwierdzenia geometrii, proweniencji zatwierdzonych cropów oraz
  zero niespójności jakości.
- Cutover usunął starą projekcję `image_board_search_documents`, tekstowe
  tokeny/GIN-y i legacy `has_grid_issue`. Raport przed/po wskazuje spadek
  monitorowanych relacji z `6 968 860 672` do `6 210 854 912` bajtów, bez
  `VACUUM FULL` i bez usuwania obrazów, obserwacji lub audytu.
- Kontrola rzeczywistych danych potwierdza zero podwójnych właścicieli w fast
  documents, zero plansz bez snapshotu topologii, zero zakończonych plansz bez
  zatwierdzonej geometrii i zero zatwierdzonych komórek bez proweniencji.
- Odroczony upload zastępczego zdjęcia jednej planszy ma osobny
  `TASK-0305`. Nie należy implementować go jako rozszerzenia 0.9.
- `v0.9.14` uniezależnia wizualną podstawę lokalnego Reviewera od arkusza
  globalnego Admina. Tokeny ciemnego motywu, tło, focusy i bazowe style
  kontrolek należą teraz także do Reviewera, dzięki czemu „Zatwierdzanie
  cięcia siatki” zachowuje wygląd aplikacji po niezależnym buildzie Reviewera.
- `v0.9.15` synchronizuje lokalną allowlistę mutacji Reviewera z endpointami
  walidacji siatki v0.9. Origin `127.0.0.1:3001` może wykonać wyłącznie
  zatwierdzenie geometrii, podgląd oraz zapis rewizji; nadal wymaga loopbacku
  i stałego nagłówka intencji. Naprawa nie rozszerza zdalnego Reviewera ani
  pozostałych mutacji Admin API.

### Niezależne ulepszanie symboli i siatki — TASK-0303

- `v0.8.50–v0.8.54` przełącza nowe kohorty symboli z pełnych plansz na
  pojedyncze, aktualne komórki `approved`. `?`, błąd siatki, nieaktywny symbol,
  stary właściciel sekwencji i zmieniona check­suma są wykluczane fail-closed.
- Kohorta `verified-symbol-cell-training-cohort-v2` priorytetyzuje korekty,
  deduplikuje identyczne i bliskie wizualnie cropy, rozkłada próbki między
  źródła oraz ogranicza wynik do celu 1000 i maksimum 2000 per symbol. Worker
  nadal odtwarza v1 i używa istniejącego CNN, splitów źródłowych, ONNX i bramki.
- Migracja `0071_symbol_cell_training_cohorts` utrwala rodzaj datasetu i
  dopuszcza kohortę komórkową. Migracja `0072_verified_training_cohort_cells`
  zapisuje wybrane próbki i ich checksumy, dzięki czemu delta kolejnej kohorty
  nie wraca błędnie do pełnej liczby cropów. Lokalna baza jest na `0072`.
- Admin pokazuje dwa jawnie niezależne workflowy: `Rozpoznawanie symboli` oraz
  `Cięcie siatki`. Aktywacja jednego nie aktywuje drugiego.
- Nie wykonano dużego benchmarku. Test zlicza ograniczoną liczbę porównań LSH;
  pula SQL, pamięć selektora i trening są liniowe względem liczby dopuszczonych
  próbek, a sam trening jest dodatkowo ograniczony hard maxem kohorty.
- Mały pomiar czystej selekcji w pamięci na obecnym komputerze: 1500 cropów
  (odpowiednik 100 plansz) `0,0482 s`, 15 000 cropów (1000 plansz) `0,3552 s`.
  Dla 1000 plansz selektor zwrócił docelowe 8000 próbek (1000 × 8 symboli).
  Pomiar nie obejmuje odczytu JPEG/PNG z dysku ani treningu CNN; potwierdza, że
  sam dobór nie jest wąskim gardłem i nie ma wzrostu kwadratowego.
- Read-only odbiór rzeczywistej gry zakwalifikował 10 736 aktualnych cropów i
  wybrał 4629 różnorodnych próbek z ośmiu klas. Pierwszy równoległy odczyt,
  kontrola checksum i dHash trwały 18,861 s; zwykły proces API utrzymuje
  ograniczony cache 32 768 deskryptorów, natomiast zamrożenie ponownie sprawdza
  bajty. Transakcyjny test zapisu/rollbacku potwierdził jeden rekord projekcji
  v2 dla jednej próbki bez pozostawienia danych audytowych.
- `v0.8.58` domyka bramkę wykonawczą kohorty v2: mała kohorta pojedynczych
  cropów przechodzi rzeczywisty trening, eksport ONNX i gate kandydata. Test
  ujawnił również dwa miejsca zależne od limitu `MAX_PATH`; zapis manifestu
  datasetu i odczyt obrazu przez klasyfikator używają teraz wspólnej obsługi
  długich ścieżek Windows.
- `v0.8.59` stabilizuje wznowienie lokalnej ręcznej selekcji w kierunku
  malejącym. Źródło ma odtąd jeden trwały, naturalny porządek, a kierunek
  steruje wyłącznie kursem. Historyczne rekordy są jednorazowo normalizowane
  z użyciem append-only trace, aby po `Wznów poprzednią sesję` nie wskazać
  lustrzanego JPEG-a. Zdalny workspace już używał ordinalu źródła i nie wymaga
  zmiany.
- `v0.8.60` usuwa fałszywe „zawieszenie” wznowionego importu plansz: zapisane
  strony `waiting_for_review` nie są już kosztownie rehydratowane i zapisywane
  ponownie po restarcie workera. Niedokończone źródła `processing` przechodzą
  jako pierwsze, a trwałe checkpointy review pozostają źródłem prawdy.
- `v0.8.61` utrwala kursor lokalnej ręcznej selekcji jako względną ścieżkę
  JPEG-a (`source_path_v2`), nie tylko indeks. Przy wznowieniu malejącego
  rekordu historycznego ostatnio zatwierdzony plik jest kotwicą naprawczą dla
  błędnie wcześniej utrwalonego indeksu; brak tej ścieżki blokuje wznowienie
  fail-closed zamiast wskazać lustrzane zdjęcie.
- `v0.8.62` rozdziela porządek JPEG-ów od kierunku numeracji plansz. Lokalny i
  operator-local workspace zawsze zaczynają od pierwszego pliku naturalnej
  listy, a `→` oraz Enter idą do następnego ordinalu katalogu. Kierunek
  rosnący/malejący zmienia wyłącznie kolejny zakres `seq_*`. Malejące rekordy
  `source_path_v2` są jednorazowo naprawiane z ostatniego zaakceptowanego JPEG-a
  do `source_path_v3`, aby indeks i zdjęcie nie wskazywały lustrzanego miejsca.

### Duże browserowe importy plansz

- Browserowy staging `seq_*` używa osobnego limitu
  `GAME_PREDICTOR_BROWSER_LAYOUT_IMPORT_MAX_BYTES`, domyślnie 20 GiB. Historyczny
  limit 1 GiB pozostaje wyłącznie dla ręcznych plików CSV/JSONL, a selekcja
  zdjęć zachowuje własny limit 128 GiB. API nadal wymaga rezerwy 512 MiB wolnego
  dysku i zwraca w błędzie limitu deklarowany oraz maksymalny rozmiar.

### Jeden właściciel oczekującej planszy — TASK-0291

- `v0.8.33` domyka trwałą ochronę przed duplikatami oczekujących plansz dla
  `game_id + sequence_number`. Migracja `0069_pending_sequence_ownership`
  denormalizuje zakres właścicielski na `image_review_items`, synchronizuje go
  triggerami i dodaje częściowy indeks unikalny dla `pending`.
- Kanoniczne `accepted/corrected` pozostaje bezwzględnym właścicielem numeru.
  Bez canonical najnowszy import według `(job.created_at, job.id)` przejmuje
  nierozwiązany numer, a starsze pending zostają zachowane jako audytowalne
  `superseded`; nie wracają do Reviewera ani Weryfikacji symboli.
- Naprawa rzeczywistej bazy rozwiązała `114 676` zduplikowanych grup sekwencji
  i `159 754` nadmiarowe pozycje pending. Nie znaleziono pending nad
  istniejącym canonical. Migracja danych zakończyła się na `0069`; bieżący
  head schematu po dodaniu kohort komórkowych symboli to `0072`.
- Dropdown `Zatwierdzanie plansz` pokazuje odtąd wyłącznie importy
  `waiting_for_review`. Importy zakończone pozostają widoczne w historii Jobów,
  ale nie zaśmiecają operacyjnego wyboru.

### Masowa weryfikacja pojedynczych symboli — TASK-0294

- Od `v0.8.19` kontrakt domenowy `image_symbol_reviews` definiuje trwały w
  przyszłości stan pojedynczego cropa: checksum-bound tożsamość, `pending` /
  `approved`, niezależną flagę błędu siatki oraz pochodzenie przypisania.
  Domena nie zależy od SQL, HTTP, UI ani jobów.
- `?` jest reprezentowane jako brak przypisanego symbolu i nie może zostać
  zatwierdzone. Zmiana geometrii unieważnia wszystkie 15 komórek, a agregacja
  domyka planszę wyłącznie przy 15 aktualnych zatwierdzeniach bez błędu siatki:
  `accepted` dla zgodności z predykcją, w przeciwnym razie `corrected`.
- TASK-0294 jest ukończony w `v0.8.28`: istnieje odczyt, wewnętrzne mutacje,
  trwałe operacje masowe cropów, filtr złej siatki w Reviewerze i lokalny
  workspace Admina. Odbiór dokumentuje teoretyczne granice pamięci i transakcji;
  fizyczny benchmark jest odroczony decyzją D-236.
- Od `v0.8.20` migracja `0066_image_symbol_review_cells` utrwala stan komórek
  i append-only audyt, a `scripts/rebuild_symbol_cell_reviews.py` wykonuje
  keysetowy, wznawialny backfill wyłącznie dla obecnego właściciela logicznej
  planszy. Ready wymaga dokładnie 15 bieżących cropów na planszę; brak sekwencji,
  cropa lub rewizji geometrii jest kontrolowanym stanem `failed`, nie cichym
  pominięciem. Backfill nie tworzy syntetycznych eventów.
- Od `v0.8.21` istnieje transakcyjny write-through dla pełnej decyzji
  Reviewera, korekty geometrii, ręcznego rozwiązania odroczonej geometrii,
  reinferencji symboli/siatki, nowych elementów pipeline’u i zmiany właściciela
  sekwencji. Migracja `0067_symbol_cell_review_catalog_revision` wprowadza
  per-game `catalog_revision`, zwiększaną co najwyżej raz w pojedynczej
  transakcji. Checkpoint transakcji canonical/staging/search oraz blokad
  współbieżności przeszedł na izolowanym PostgreSQL: równoległe decyzje
  utrzymują jednego właściciela kanonicznego, a przegrany jest superseded.
- Od `v0.8.22` lokalne Admin API ma bounded, checksum-bound odczyt komórek
  `symbol-cell-reviews`: keyset 60 (maks. 100), filtry aktywnego symbolu lub
  technicznego `?` i stanu, liczniki oraz scope-bound kursory. Odczyt i asset
  widzą wyłącznie aktualnego właściciela z fast-document i aktualną geometrię;
  asset ponownie sprawdza SHA-256 pliku. OpenAPI oraz generowany klient są
  zgodne. Nie istnieją jeszcze mutacje komórek, job masowy ani workspace
  Admina — to pozostaje TASK 5+ i TASK 8+.
- Od `v0.8.23` istnieje wewnętrzny, atomowy per plansza command path dla
  `approve`, `reassign` i `mark_grid_issue`. Każda akcja ponownie sprawdza
  aktualnego właściciela, rewizję oraz checksumę cropa pod blokadą, zapisuje
  append-only event i agreguje dokładnie 15 bieżących cropów do istniejącej
  decyzji canonical/staging/kolejki/job statusu. Flaga złej siatki otwiera
  domkniętą planszę, ale zachowuje zatwierdzenia pozostałych 14 aktualnych
  cropów; wyłącznie korekta geometrii resetuje komplet 15. Nie ma jeszcze
  publicznej mutacji, durable joba ani UI — to zakres TASK 6+ i TASK 8+.
- Od `v0.8.24` migracja `0068_image_symbol_review_bulk_operations` utrwala
  idempotentne operacje `approve`, `reassign` i `mark_grid_issue`, ich
  checksum-bound snapshoty targetów oraz częściowe wyniki. Worker general lane
  pobiera maksymalnie 100 plansz na checkpoint, zapisuje jedną planszę w jednej
  transakcji i po restarcie wznawia wyłącznie `pending`. Masowe oznaczenie złej
  siatki aktualizuje wszystkie cropy danej planszy przed jej ponownym
  otwarciem, więc canonical nie usuwa pozostałych targetów z tej samej partii.
- Od `v0.8.25` operacyjny Reviewer udostępnia rozłączny widok `Do poprawy
  siatki`. Wykorzystuje on `EXISTS` po aktualnych `pending` komórkach z
  `has_grid_issue`, więc jedna plansza z wieloma oznaczeniami występuje tylko
  raz, a terminalne pozycje nie wyciekają do listy. Odpowiedź zwraca licznik
  plansz wymagających korekty; kursor schema v3 wiąże także filtr i nie może
  zostać użyty między widokami. Zapis nowej geometrii resetuje flagi 15 komórek
  i odświeża Reviewer tak, aby plansza od razu zniknęła z filtra. Scope zdalnej
  sesji nadal jest ograniczony do jej gry i importu.
  OpenAPI i generowany klient są zgodne; UI workspace pozostaje TASK 8–9.
- Od `v0.8.26` Admin ma niezależną główną zakładkę `Weryfikacja symboli`.
  Lokalny, read-only workspace wybiera grę, aktywny symbol lub techniczne `?`
  oraz stan, czyta checksum-bound cropy keysetowo po 60, leniwie pobiera ich
  assety i ogranicza pamięć do bieżącej strony oraz dwóch sąsiednich. Karta
  pokazuje numer planszy, pozycję komórki, stan i flagę `Zła siatka`; brak
  pojedynczego assetu nie usuwa metadanych. Wybór, toolbar i masowe decyzje
  pozostają wyłącznie zakresem TASK 9.
- Od `v0.8.27` ten workspace obsługuje jawne zaznaczenie checksum-bound cropów
  (maks. 10 000) albo cały snapshot bieżącego filtra z wykluczeniami. Sticky
  toolbar uruchamia po preview `approve`, `reassign` i `mark_grid_issue` przez
  istniejący trwały job; dla technicznego `?` zatwierdzanie jest zablokowane.
  Lista transportuje także `cropSampleId`, niezbędny do bezpiecznej jawnej
  mutacji. Polling jednej aktywnej operacji nie nakłada requestów, pokazuje
  `applied/conflict/failed` i po terminalnym wyniku odświeża bounded stronę.
- Od `v0.8.35` przygotowanie projekcji nie zależy już od ręcznego skryptu.
  Lokalny Admin API udostępnia status oraz idempotentny start trwałego joba
  `image_symbol_review_backfill`. General worker zapisuje istniejące metadane
  cropów w transakcjach po maksymalnie 200 plansz i wznawia pracę z trwałego
  kursora `image_symbol_review_states`; nie kopiuje JPEG-ów ani cropów.
- Od `v0.8.36` po skanie job wykonuje maksymalnie trzy bounded przebiegi
  reconciliacji bieżących właścicieli. Uzupełnia plansze powstałe po minięciu
  kursora i odświeża zmianę geometrii, ale nigdy nie nadpisuje częściowej
  decyzji człowieka. `ready` nadal wymaga 15 aktualnych cropów per właściciel.
  Status raportuje rozmiar tabeli, indeksów i — gdy katalog danych PostgreSQL
  jest dostępny lokalnie — bieżące wolne miejsce; nie uruchamia benchmarku.
- Od `v0.8.37` workspace Admina pokazuje start, wznowienie, ID i progres tego
  joba oraz automatycznie przechodzi do cropów po `ready`. Ręczne przyciski
  stron zostały zastąpione dwukierunkowym infinite scrollem na keysetach po 60;
  bufor pozostaje ograniczony do maksymalnie 180 rekordów, a usuwanie odległej
  strony zachowuje kotwicę scrolla. Assety nadal są lazy-loaded.
- Od `v0.8.43` pierwsza strona Weryfikacji symboli pozostaje natychmiastowa, a
  do czterech następnych stron metadanych jest pobieranych sekwencyjnie w
  porządku keyset. W DOM nadal pozostają maksymalnie 3 strony/180 kart i tylko
  one pobierają lazy assety. Karty są minimalistycznymi cropami 100 × 100 px
  bez opisów. Target wysłanej operacji jest przygaszony i pokazuje spinner, a
  poprawnie przypisany do innego symbolu crop znika przed bounded odświeżeniem
  danych z serwera.
- Od `v0.8.44` karty pobierają checksum-bound miniatury WebP mieszczące się w
  100 × 100 px zamiast transferować pełne cropy; URL wiąże checksumę i rozmiar,
  a przeglądarka używa rocznego prywatnego cache `immutable`. Jedna jawnie
  zaznaczona decyzja `approve`, `reassign` lub `mark_grid_issue` przechodzi
  bezpośrednio przez istniejącą atomową mutację planszy i nie tworzy joba.
  Sukces czyści zaznaczenie, reassign od razu ukrywa crop z bieżącego filtra,
  a konflikt przywraca kartę i pokazuje toast. Bulk job pozostaje dla wielu
  targetów i snapshotu całego filtra.
- `v0.8.45` zastępuje infinite scroll i read-ahead klasyczną, keysetową stroną
  500 cropów. Admin utrzymuje wyłącznie bieżącą stronę metadanych, domyślnie
  filtruje `Oczekujące` i pozwala zaznaczyć wyłącznie pojedyncze cropy albo
  całą widoczną stronę. Po udanej bezpośredniej lub masowej decyzji ponawia
  zapytanie od zapamiętanego kursora wejściowego strony; rekordy niepasujące do
  filtra wypadają, a backend uzupełnia jej koniec do 500. Nie powstaje osobny
  cache stron ani endpoint merge po ID. Immutable cache miniaturek WebP
  pozostaje jako ochrona transferu. Aktywna decyzja blokuje kolejne akcje i
  nawigację do chwili terminalnego wyniku.
- `v0.8.46` przenosi domyślny lokalny budżet wykonawczy z nieużywanej
  automatycznej Selekcji zdjęć do general workera. `npm run workers:start`
  uruchamia tylko general z budżetem 7; preflight geometrii przetwarza do
  siedmiu stron równolegle, a OpenCV/BLAS pozostają jednowątkowe na stronę.
  Nadal istnieje dokładnie jeden aktywny general job. Jawne
  `npm run workers:start:all` przywraca historyczny bezpieczny profil 2+5,
  jeżeli automatyczna selekcja ponownie będzie potrzebna.
- `v0.8.47` naprawia kontrakt odpowiedzi strony Weryfikacji symboli. Request i
  repozytorium obsługiwały ustalony limit 500, ale schema odpowiedzi nadal
  odrzucała więcej niż 100 elementów, przez co kompletna strona kończyła się
  HTTP 500. Następnie panel i API przeszły na dodatni limit wybierany przez
  operatora; domyślną wartością pozostaje 500.
- `v0.8.48` przenosi page-local operacje masowe Weryfikacji symboli do tła UI.
  Każdy trwały job zachowuje osobny status i spinner na swoich targetach, ale
  nie blokuje przejścia na inną stronę ani wysłania kolejnej operacji. Pełny
  sukces usuwa przetworzone karty bez kosztownego uzupełniania strony; wynik
  częściowy pozostawia je do świadomego ponowienia. Toast jest stały 50 px od
  lewego i dolnego brzegu zamiast zasłaniać sticky toolbar.
- `v0.8.49` porządkuje podsumowanie strony Weryfikacji symboli. Operator widzi
  numer strony, jednoznaczny zakres pozycji `1–500`, `501–1000` itd. oraz pełne
  liczniki zatwierdzonych i oczekujących cropów; ostatni zakres jest ograniczony
  do rzeczywistej liczby wyników.
- Kontrolowane uruchomienie projekcji ujawniło, że 200 plansz daje 3000
  komórek i 66 000 parametrów jednego INSERT-u, ponad limit 65 535 psycopg.
  Zapis pozostaje jedną transakcją 200 plansz, ale dzieli komórki na trzy
  bezpieczne INSERT-y po 1000 rekordów; pierwszy błąd wystąpił przed zapisem.
  Jeżeli katalog danych PostgreSQL nie jest widoczny dla procesu API, rozmiar
  tabeli i indeksów nadal jest raportowany, a pusta pozostaje tylko metryka
  wolnego miejsca systemu plików.
- Gotowy workspace udostępnia operatorowi akcję `Uzupełnij brakujące symbole`.
  Ponowne uruchomienie zachowuje istniejące komórki i kursor, a general worker
  wykonuje idempotentną reconciliację brakujących lub nieaktualnych rekordów;
  nie uruchamia cięcia plansz ani rozpoznawania symboli. Jeżeli general lane
  jest zajęty, lista pozostaje dostępna, a stan `rebuilding` zaczyna się dopiero
  po przejęciu joba przez worker.
- Reconciliacja uruchomiona z kompletnego `ready` zapisuje w jobie trwały
  znacznik dostępności. Dzięki temu jej przejściowy stan `rebuilding` nie
  blokuje zmiany symbolu ani pozostałych operacji na już istniejących,
  checksum-bound cropach. Początkowy i niekompletny backfill nadal pozostają
  zablokowane. Podsumowanie filtra pokazuje także liczbę unikalnych cropów w
  bounded buforze względem pełnej liczby wyników wybranego symbolu.
- Pierwszy kontrolowany backfill gry `777` zakończył się statusem `ready`:
  `125 431` plansz, `1 881 465` komórek i zero błędów integralności.
- Od `v0.8.28` TASK-10 nie tworzy ani nie uruchamia w tle fizycznego benchmarku. Przyjęty
  profil teoretyczny ma `2 000 010` komórek, aby zachować pełne plansze po 15
  cropów; analiza wykazała bounded keyset i 100-planszowe checkpointy workerów.
  Historyczne założenie bufora 180 metadanych zostało zastąpione w `v0.8.45`
  pojedynczą stroną 500 rekordów. Analiza nie potwierdza czasu p95 — liczniki
  listy nadal agregują cały filtr — dlatego ewentualny pomiar wymaga osobnej
  decyzji i odizolowanego środowiska zgodnie z D-236.
- `v0.8.30` przywraca zielone bramki jakości bez uruchamiania benchmarków.
  Izolowane instancje API z wstrzykniętymi zależnościami nie wykonują
  produkcyjnego recovery przy starcie, połączenie PostgreSQL ma ograniczony czas
  zestawiania, a worker zapisuje checksum-bound cropy przez ścieżki odporne na
  historyczny limit `MAX_PATH` Windows. Zaktualizowano także kontrakty testowe
  dla joba masowej weryfikacji, migracji `0068` i filtra złej siatki.

### Wyszukiwanie plansz częściowym układem — TASK-0292

- Tor `0.7` został zamknięty dla bieżących zmian produktu. TASK-0290 pozostaje
  `blocked` wyłącznie na zewnętrzne checkpointy publicznego rolloutu; nie blokuje
  lokalnego panelu Admina ani toru `0.8`.
- TASK-0292 dostarcza wyszukiwarkę częściowego układu w zakładce gry. Wynik ma
  zawsze jednego logicznego właściciela na `game + sequence_number`: kanoniczną
  planszę `accepted/corrected`, a w pozostałym przypadku deterministycznie
  wybraną oczekującą pozycję.
- Ranking nie jest prostym porównaniem łańcucha: pełne dopasowanie ma największą
  wagę, alternatywy pending są słabszym dowodem, a przyszły `?` nie daje punktu
  ani kary. Obrazy pozostają wyłącznie assetami filesystemu; do bazy trafia
  zwarta projekcja metadanych i kodów symboli.
- TASK-0291 jest ukończony w `v0.8.33`. Projekcja wyszukiwania, operacyjne
  review i Weryfikacja symboli korzystają z jednego właściciela numeru, a baza
  blokuje utworzenie drugiej aktywnej pozycji `pending`.
- Od `v0.8.1` semantyka częściowego wzoru jest zamknięta w czystym kontrakcie
  `partial-board-ranking-v1`: primary match = `1.0`, alternatywy pending =
  `0.60/0.40/0.25/0.15`, a `?` oznacza brak dowodu. Zero-evidence candidates
  nie trafiają do wyniku; remisy są deterministyczne.
- Od `v0.8.2` migracja `0057_board_search_projection` definiuje kompaktowy
  candidate projection i jeden current document dla `game + sequence`. Candidacy
  przechowuje wyłącznie kody 15 komórek, rankowane alternatywy, statusy,
  identyfikatory, checksumy i metryki jakości. Tokeny pozycji (`cell:symbol`)
  mają osobne indeksy GIN; full board crop pozostaje assetem filesystemu.
- Od `v0.8.3` migracja `0058_board_search_projection_state` wprowadza jawny
  stan gotowości projekcji per gra. Wszystkie bieżące ścieżki write synchronizują
  candidate/document w swojej transakcji, a
  `scripts/rebuild_board_search_projection.py` odbudowuje historyczne rekordy
  stronicami po review ID. Nie dotyka obrazów, cropów, jobów ani decyzji review;
  status `rebuilding/failed` ma później blokować mylące puste wyniki API.
- Od `v0.8.4` dostępny jest read-only endpoint
  `GET /api/v1/admin/games/{gameId}/board-search`. Przyjmuje powtarzalne
  `cell={0..14}:{symbolCode}`, scope `all_searchable/approved_only` i limit do
  100. Prowadzi przez backendową walidację aktywnego katalogu symboli, nie
  zwraca obrazów binarnych i blokuje odczyt, dopóki projekcja gry nie ma stanu
  `ready`. Wygenerowany klient Admina udostępnia typowane `searchGameBoards`.
- Od `v0.8.5` zakładka wybranej gry zawiera `Wyszukaj plansze`. Lokalne
  budowanie wzoru 3 × 5 nie wysyła requestu po każdej zmianie: operator może
  wskazać komórkę albo uzupełniać sekwencyjnie z pięciokolumnowej palety,
  bezpiecznie cofnąć każdą zmianę i wyzerować wzór. Jedno jawne `Szukaj plansz`
  przekazuje wybrany scope i wyłącznie znane pozycje przez typowany klient.
- Od `v0.8.6` wynik częściowego wyszukiwania jest karuzelą pełnych,
  nieprzeskalowanych cropów planszy. Pokazuje pozycję, wynik, status i dowody
  rankingu; przyciski oraz klawisze `←/→` przesuwają dokładnie o jedną pozycję
  bez zawijania. Klient prefetchuje wyłącznie bezpośrednich sąsiadów przez
  istniejący, scope-bound asset API. Niedostępny crop daje widoczny fallback,
  a nie usuwa poprawnego wyniku z rankingu.
- Od `v0.8.7` migracja `0062_board_search_fast_documents` dodaje wąski read
  model jednego aktualnego wyniku per `game + sequence`. Jest kopiowany ze
  zweryfikowanej projekcji podczas migracji oraz synchronizowany atomowo przy
  każdej późniejszej zmianie. Endpoint zachowuje ten sam ranking i OpenAPI, ale
  czyta wyłącznie kody mobilne, znane pozycje i metadane niezbędne do wyniku.
  Ciepły benchmark na `125431` dokumentach, 20 odczytach i wzorze trzech
  symboli osiągnął p50 `387,74 ms`, p95 `432,11 ms` i maksimum `441,56 ms`
  przy bramkach odpowiednio `500 ms` i `2 s`; raport:
  `ai_docs/quality/board-search-warm-benchmark-v08.json`. TASK-0292 jest
  ukończony.
- Od `v0.8.8` paleta symboli w `Wyszukaj plansze` pokazuje grafikę referencyjną
  oraz nazwę bez technicznego kodu w kaflu. Endpoint assetu odzyskuje również
  checksum-bound crop zapisany w niezmiennym manifeście historycznego bootstrapu
  katalogu, więc katalogi utworzone przed trwałymi obserwacjami cropów nie
  zwracają już błędnie `404` dla istniejącej grafiki.
- Od `v0.8.9` edytor `Twój wzór` używa kompaktowych kafli 3 × 5. Na desktopie
  ich szerokość jest ograniczona do 56 px, a na wąskim ekranie siatka nadal
  wypełnia dostępne miejsce bez zmiany kolejności pozycji.

### Ręczne grafiki referencyjne symboli — TASK-0293

- Od `v0.8.10` domena referencji symboli jest niezależna od historycznego
  bootstrapu i zawiera checksum-bound kursor, kandydatów, weryfikację rewizji
  oraz wybór trwałej referencji.
- Od `v0.8.11` kandydaci pochodzą wyłącznie z kanonicznych decyzji
  `accepted/corrected`, według końcowego symbolu zatwierdzonego przez człowieka
  oraz cropa aktualnej geometrii; żadna predykcja ani confidence nie bierze
  udziału w przynależności lub kolejności.
- Od `v0.8.12` tabela `symbol_reference_images` i content-addressed storage
  utrwalają kopię wybranego cropa. `SymbolResponse.imagePath` jest pusty bez
  takiej proweniencji, więc stary crop nie jest pokazywany jako aktywna grafika.
- Od `v0.8.13` katalog jest ręczny: utworzenie wymaga tylko nazwy i Jokera,
  a API nadaje stabilny kod, kolejne `mobileCode` i `displayOrder`. Fizyczne
  usunięcie jest blokowane, gdy symbol ma zależności.
- Od `v0.8.14` automatyczny bootstrap symboli, jego endpointy, UI, migracyjna
  tabela oraz klient nie są już częścią uruchamialnego systemu.
- Od `v0.8.15` panel Admina udostępnia ręczny formularz oraz placeholder `?`,
  osobne akcje edycji/usuwania i czytelne liczniki blokad.
- Od `v0.8.16` kliknięcie kafla otwiera stronicowany picker maksymalnie 20
  zatwierdzonych cropów; wybór zapisuje checksum-bound referencję, a błąd
  pojedynczego assetu nie ukrywa pozostałych propozycji. TASK-0293 jest
  ukończony; odbiór rzeczywistej gry wymaga danych z zatwierdzonymi planszami
  w aktualnie podłączonej lokalnej bazie.

### Benchmark i kontrolowany rollout zdalnej ręcznej selekcji — TASK-0290

- Od `v0.8.18` `Ekran startowy` otwiera zawsze wizualnie czysty konfigurator:
  oba pickery są niewybrane, nie jest pokazywany skrót powrotu do bieżącego
  workspace'u, a operator wskazuje ponownie katalog zdjęć oraz katalog zapisu.
  Jest to nadal nawigacja niedestrukcyjna — zgodna para folderów odtwarza
  zachowany manifest, decyzje, kursor i następny zakres.

- Od `v0.7.76` aktywny workspace eksponuje niedestrukcyjny `Ekran startowy`
  jako główną akcję po lewej stronie. `Restart selekcji` pozostaje po prawej
  jako akcja wtórna, która dopiero otwiera bezpieczny modal potwierdzenia.

- Od `v0.7.75` panel `Zdalna ręczna selekcja` trwale pokazuje przy wybranej
  aktywnej sesji link i kod wraz z niezależnymi przyciskami kopiowania. Kod z
  odpowiedzi create pozostaje wyłącznie w `localStorage` komputera Admina do
  TTL albo revoke; API, baza i lista sesji nadal nie zwracają surowego kodu.
  Nie ma już osobnej, znikającej sekcji „Kod jednorazowy”.

- Od `v0.7.74` ekran startowy rozróżnia relink aktywnego źródła od świadomego
  przełączenia folderu. Lokalne batch'e pozostają oddzielne i są odnajdywane po
  nazwie oraz checksummie manifestu; ponowne wskazanie zgodnej pary folderów
  wznawia postęp zamiast zgłaszać `REMOTE_SELECTION_SOURCE_CHANGED`.

- Od `v0.7.72` aktywny workspace otrzymał przycisk `Ekran startowy` obok
  restartu. Historyczny skrót `Wróć do selekcji` został zastąpiony w `v0.8.18`
  ponownym, jawnym wyborem obu katalogów.

- Od `v0.7.71` operator-local Reviewer pokazuje od razu dwa niezależne
  pickery: katalog zdjęć i katalog zapisu. Katalog nadrzędny można zapamiętać
  przed źródłem; po indeksowaniu powstaje `<źródło> wybrane`. Poprawny wynik
  wznawia zapisany kursor i zakres, a nowy modal resetu jawnie ostrzega przed
  usunięciem i blokuje skróty oraz nawigację do czasu decyzji.

- Wspólny dla lokalnej i zdalnej ręcznej selekcji wybór skoku strzałek obejmuje
  teraz również `8` oraz `9`; kolejność klawiaturowa `↑/↓` pozostaje ciągła.

- Lokalna ręczna selekcja synchronizuje przy wznowieniu należący do sesji
  manifest wynikowy z rekordem IndexedDB. Bezpieczna korekta ciągłej numeracji
  aktualizuje pierwszy i następny zakres bez ponownego kopiowania JPEG-ów;
  niezgodny manifest blokuje wznowienie.

- Od `v0.8.31` lokalny i operator-local workspace pozwalają kliknąć bieżący
  zakres i zapisać wyłącznie dodatni przedział `start–start+8`. Po decyzji
  kolejny zakres jest wyliczany względem ręcznie podanej wartości zgodnie z
  kierunkiem sesji. Manifest odtwarza takie świadome luki dokładnie, bez
  cichego wypełniania lub przenumerowywania historii.

- Historia importów plansz pokazuje przy każdym jobie przypięty silnik cięcia:
  historyczny `v18` albo pełny import `v20` korzystający z geometrii i cropów
  `v19`; źródłem etykiety jest niezmienny snapshot joba.

- Od `v0.7.70` każdy nowy staging i ponowne przetworzenie importu przypinają
  `v20 — geometria i cropy v19`. API przy braku pola także wybiera
  `verified_v19`; historyczny v18 pozostaje wyłącznie odtwarzalnym artefaktem
  już utworzonych jobów i nie jest fallbackiem.

- Monitor jobów pokazuje pod importem katalogowym i preflightem geometrii
  zakres z nazwy stagingu, np. `Zakres 19810–45162`. Nazwa stagingu jest
  metadataną prezentacyjną i nie zmienia idempotencji preflightu.

- Zamiast technicznych etykiet `Import` i `Walidacja` monitor jobów pokazuje
  opis aktualnej pracy: ładowanie zdjęć, wyznaczanie siatki i cięcie plansz,
  rozpoznawanie symboli albo tworzenie geometrii siatek.

- Po kolejnych rzeczywistych rozjazdach transferu właściciel zmienił model
  wyniku na operator-local. Od v0.7.51 link i kod wyłącznie odblokowują stronę;
  źródło, decyzje, kursor, zoom, obie osie scrolla, manifest oraz wybrane JPEG-i
  pozostają na urządzeniu operatora. Reviewer tworzy w wybranym katalogu
  nadrzędnym folder `<źródło> wybrane`; nie wysyła decyzji ani obrazów na host.
- Zdalny viewport otrzymał brakujące bazowe reguły CSS lokalnego selektora.
  Wcześniej komponent używał tych samych nazw klas i obliczał nowy rozmiar, ale
  Reviewer nie definiował wysokości viewportu, flex layoutu ani canvasu, dlatego
  wartość zoomu zmieniała się bez widocznego efektu. Scroll i zoom są utrwalane
  per sesja/partia w storage przeglądarki operatora.
- Mobilny test operator-local wykrył drugi niezależny przypadek niewidocznego
  zoomu: naturalne wymiary JPEG-a nie zawsze trafiały do stanu przez
  `onLoadCapture`. Reviewer używa zwykłego `onLoad` zgodnego z lokalnym
  selektorem i ma fallback dla obrazu już zdekodowanego z cache.
- Panel hosta nie pokazuje już pustej tabeli serwerowych partii, limitu 100 ani
  historycznych akcji recovery/reopen. Aktywny operator-local workflow utrzymuje
  wyniki wyłącznie na urządzeniu operatora, więc host zarządza tylko sesją
  dostępu i stanem połączenia.
- Lista hosta jest ograniczona do dziesięciu najnowszych sesji w porządku
  malejącym. Starsze wpisy pozostają audytowalne, ale nie rosną bez końca w
  codziennym widoku Admina. Operator może filtrować tę listę na aktywne
  (`draft/active`) i zakończone (`completed/expired/revoked`); panel pobiera
  ograniczone 100 metadanych, aby dziesięć nowych terminalnych wpisów nie
  ukrywało starszej aktywnej sesji.
- Zdalny podgląd nie resetuje już wymiarów tego samego JPEG-a po drugim refreshu
  następującym po zatwierdzeniu. Scroll poziomy i pionowy pozostają zachowane po
  `Enter`, `F` i przycisku zapisu, nie tylko po nawigacji strzałkami.
- Folder operator-local jest teraz przyjmowany tylko jako pusty albo jako
  kompletny wynik do wznowienia. Manifest przechowuje checksumę źródła, liczbę
  JPEG-ów, pierwszy zakres i kierunek; przy nowym linku odtwarza zdjęcie,
  następny zakres i decyzje, mapując je na świeże identyfikatory IndexedDB.
  Obce pliki, brak manifestu, brak wskazanego `seq_*` lub inne źródło blokują
  start przed zapisem.
- Odtworzenie scrolla po zatwierdzeniu jest przypięte do ordinalu następnego
  JPEG-a. Wcześniejsza flaga boolean mogła zostać skonsumowana przez render
  `busy` jeszcze na starym zdjęciu; teraz dopiero załadowany docelowy podgląd
  może odtworzyć i wyczyścić oczekiwanie.
- Dodatkowa regresja ujawniła różnicę względem lokalnego selektora: pozycja była
  przechwytywana przed asynchronicznym zapisem JPEG-a. Zdalny ekran przechwytuje
  ją teraz dokładnie jak lokalny — po trwałym zapisie, bezpośrednio przed
  zmianą stanu React. Test rzeczywistego komponentu przy viewportcie 390×844
  zachował `scrollTop=388,8` po zatwierdzeniu i przejściu na kolejny JPEG.
- Próba operatorska w Chrome na macOS nadal wykazała reset wewnętrznego scrolla
  wyłącznie po zatwierdzeniu; zwykła nawigacja zachowywała pozycję. Ścieżka
  zapisu przechwytuje więc `scrollLeft/scrollTop` synchronicznie przy komendzie
  Enter/F/klik, zanim rozpocznie zapis pliku i zmieni stan `busy`.
  Dodatkowym źródłem resetu był stan przejściowy: canvas znikał i `scrollHeight`
  chwilowo malał, więc Chrome mógł wymusić `scrollTop=0` po wcześniejszym
  odtworzeniu.
  Reviewer utrzymuje teraz stary canvas i jego wymiary do `decode` następnego
  JPEG-a; odtwarzanie czeka jawnie na `decoded` docelowego ordinalu.
- Kolejna próba ujawniła, że publiczny link nadal serwował proces Reviewera
  uruchomiony o 17:05, podczas gdy aktualny build powstał o 17:40. Kod poprawek
  nie był więc obecny w testowanej stronie. Po kontrolowanym restarcie aktualny
  proces wystartował o 17:56, a ten sam Quick Tunnel pozostał aktywny.
- Kontrolery lokalnego i zdalnego Reviewera wiążą teraz readiness z aktualnym
  `.next/BUILD_ID`, który produkcyjny HTML zawiera jako identyfikator builda.
  Stary produkcyjny Node na porcie 3001 jest bezpiecznie zastępowany przed
  ponownym użyciem ingressu, a stan procesu zapisuje tożsamość rzeczywistego
  listenera zamiast krótkotrwałego wrappera `npm.cmd`.
- Operator-local przechowuje teraz również uchwyt katalogu nadrzędnego wyniku.
  Usunięcie `<źródło> wybrane` albo błąd niedostępnego źródła powoduje atomowy
  reset od pierwszego zdjęcia i odłączenie obu uchwytów. Reviewer wymaga
  ponownego wskazania zgodnego folderu zdjęć i katalogu zapisu; pusty manifest
  powstaje dopiero przy jawnym uruchomieniu. Jawny `Restart selekcji` czyści
  tylko zweryfikowany folder tej selekcji; obce lub zmienione pliki blokują
  operację.
- Bieżącym aktywnym modelem symboli gry `777` jest iteracja `#3`
  `47b6aa0d-2cea-4765-97f0-ee1f86cfc056`. Weryfikacja bazy 2026-08-24
  potwierdziła status `candidate_ready` oraz aktywację z 2026-08-19; ponowna
  aktywacja zwraca poprawnie `SYMBOL_MODEL_ALREADY_ACTIVE`. Historyczna
  iteracja v19 z błędem `lemon → orange` pozostaje odrzuconym artefaktem i nie
  jest tym aktywnym modelem.
- Historyczny control outbox, transfer i materializacja pozostają w repozytorium
  do audytu, lecz nowy workspace ich nie uruchamia. Etapy rolloutowe mierzące
  transfer do hosta wymagają ponownej decyzji przed kontynuacją.

- Rozpoczęto TASK 18 po zamknięciu bramki bezpieczeństwa v0.7.41. Pierwszy pion
  tworzy deterministyczny etap 1, wersjonowany raport content-addressed oraz
  runbook kolejnych checkpointów 10/500/1000/8000/15000.
- Etap 1 przeszedł lokalnie przez `npm run remote-selection:rollout:stage1` i
  `npm run remote-selection:rollout:check`; obejmuje także stale-generation
  i exact retry przez właściwą maszynę domenową. Nie uruchomiono jeszcze
  etapów 2–5 ani środowiska LAN/publicznego.
- Lokalna podbramka etapu 2 przeszła 100 JPEG-ów przez rzeczywisty tymczasowy
  filesystem, produkcyjny streaming, materializację i finalizację. Wykryła i
  zamknęła regresję: udane ponowienie transferu anuluje starszą próbę `failed`
  tego samego pliku/generacji, zachowując audyt i twardą bramkę finalizacji.
  Raport pozostaje świadomie `blocked`, dopóki nie przejdą wymagane próby dwóch
  profili/UI, LAN, offline host/operator, restart API, revoke i nowy URL tunelu.
- Etapy 4 i 5, prawdziwy Quick Tunnel oraz testy na zewnętrznej sieci wymagają
  osobnej zgody właściciela i nie zostaną uruchomione przez implementację.
- TASK 19 pozostaje warunkowy: decyzja o chunkowanym uploadzie może powstać
  wyłącznie na podstawie raportów TASK-0290.
- Próba UI etapu 2 wykryła blokujący błąd File System Access API: identyfikator
  pickera folderu źródłowego przekraczał limit 32 znaków Chromium. Reviewer używa
  teraz stabilnego `gp-remote-source-v1`, a test regresyjny pilnuje limitu i
  dozwolonego alfabetu identyfikatora.
- Kolejna próba UI wykryła, że natywny `window.fetch` był wywoływany z obiektem
  transportu jako odbiorcą i Chromium zwracał `Illegal invocation`. Transport
  control plane oraz transfer JPEG wywołują teraz fetch z `globalThis`; dwa
  testy regresyjne chronią oba miejsca przed powrotem błędu.
- Zdalny workspace ponownie używa klas wizualnych lokalnej selekcji zamiast
  natywnie wyglądających kontrolek. Poziomy scroll podglądu jest ukryty, obraz
  pozostaje wycentrowany, a pionowy scroll jest przywracany po gotowym layoucie
  kolejnego zdjęcia. Dwa testy kontraktu pilnują parytetu UI i scrolla.
- Próba operatorska wykryła utratę szybkich decyzji oraz możliwość finalizacji
  po cyklu synchronizacji, który nie obejmował operacji dopisanych w jego
  trakcie. Interakcje są teraz szeregowane, koordynator synchronizacji wykonuje
  zaległy kolejny przebieg, a finalizacja wymaga pustego lokalnego outboxu.
  Cofnięcie przywraca również indeks zdjęcia usuwanej decyzji.
- Mobilna próba Quick Tunnel wykryła możliwość pozostania na statycznym ekranie
  `Sprawdzanie sesji…`, gdy przeglądarka odrzuca dostęp do `sessionStorage` albo
  zapytanie przez ingress nie kończy się. Id klienta ma teraz bezpieczny
  fallback pamięciowy i UUID v4 bez `randomUUID`, a context, unlock i lease mają
  wspólny limit 12 sekund zamiast bezterminowego oczekiwania.
- Kolejna próba wykryła `selected > 0` przy `transfer = synced = 0`: aktywny
  skan mógł nadpisać przewinięcie kursora transferów wykonane przez nową decyzję
  `F`. Aktualizacja kursora jest teraz warunkowa, więc starszy skan nie pomija
  świeżych wyborów. Zdalny viewport przywraca też poziomy scroll i zachowuje
  obie osie przy przejściu strzałką, decyzji, pominięciu oraz cofnięciu.
- Mobilna próba wykryła `REMOTE_SELECTION_CLIENT_SEQUENCE_REPLAY` po otwarciu
  kolejnej karty. Klient uzgadnia teraz globalny zegar sekwencji z odpowiedzią
  hosta i jednokrotnie, atomowo przenumerowuje wyłącznie niepotwierdzony outbox,
  zachowując `operationId` oraz decyzje. Koordynacja kart rozróżnia instancję
  karty od kopiowanego `clientInstanceId`, więc duplikat karty jest read-only.
  Podgląd ma pełną szerokość, techniczne liczniki usunięto z bocznego panelu,
  a zoom i przywracanie obu osi są wymuszane po ustabilizowaniu layoutu.
- Przed publicznym pilotem TASK-0290 wymaga checkpointu polityki feature flag:
  plan architektury opisuje nieaktywny kod do odbioru, natomiast obecna
  konfiguracja/instrukcja opisują wartość domyślnie włączoną. Nie zmieniono
  tej wcześniejszej polityki w ramach benchmarku.

### Bramka bezpieczeństwa zdalnej ręcznej selekcji — v0.7.41

- TASK-0289 zamyka publiczny zakres zdalnej ręcznej selekcji dokładną,
  domyślnie blokującą allowlistą route/method powiązaną z OpenAPI. Mutacje
  wymagają zgodnego `Origin`, `Host` i `Sec-Fetch-Site: same-origin`; nagłówki
  forwarded nie mogą zmienić granicy zaufania.
- Identyfikatory klienta i transferu są walidowane jako UUID v4. Publiczne
  odpowiedzi są rekurencyjnie filtrowane z sekretów i absolutnych ścieżek
  Windows, a wspólna walidacja audit payloadów obejmuje repozytoria SQL i
  in-memory.
- Dokładny replay nadal jest idempotentny, ale zużywa sesyjny budżet operacji.
  Quota transferu i bajtów pozostaje fail-closed; rotacja client ID nie resetuje
  limitu sesji.
- Zapisano content-addressed raport
  `remote-manual-selection-security-gate-v1` o SHA-256
  `8386c3676422ecb3d98994c854bb7c447f5c5452592990485f7bd9af3e4b4360`.
  Osiem kontroli przeszło i nie ma otwartego findingu `critical`/`high`.
- Bramka: 106 testów Reviewera oraz 183 celowane testy API/filesystemu są
  zielone; jeden test symlinka jest pominięty, ponieważ host Windows nie pozwala
  utworzyć symlinka. Pięć celowanych testów PostgreSQL przeszło. Zielone są też
  Reviewer lint/typecheck/build, Ruff zmienionych plików, Prettier, OpenAPI i
  weryfikator raportu. Selektywny mypy nadal wchodzi w wcześniejszy problem
  repozytoryjny: pakiet workera nie publikuje `py.typed` i pełny graf API zgłasza
  31 błędów poza zmienionymi modułami.
- Prawdziwy test Quick Tunnel, zewnętrzny pentest oraz rollout i benchmark skali
  pozostają zakresem kolejnego checkpointu TASK 18. Feature flagi nie zostały
  włączone przez TASK-0289.

### Recovery zdalnej ręcznej selekcji — v0.7.40

- TASK-0288 dodaje ograniczony, idempotentny reconciler uruchamiany przy starcie
  API oraz przed cyklem akcji hosta w general workerze. Zgodny plik `.verified`
  jest ponownie hashowany i odzyskiwany bez uploadu; `.part`, brak pliku lub
  konflikt checksummy nigdy nie potwierdzają zapisu i pozostawiają artefakty do
  jawnej diagnozy.
- Reconciler uzupełnia brakujące akcje materializacji, używa porównania
  `updated_at` jako fencing i może zostać wyłączony przez
  `GAME_PREDICTOR_REMOTE_SELECTION_RECOVERY_ENABLED=false`. Jeden cykl ma limit
  `1..1000`, domyślnie 100; nie wykonuje automatycznego delete ani GC.
- State delta zawiera teraz zagregowane liczniki pending/uploading bytes/
  materializing/synced/conflict i `lastHeartbeatAt`. Reviewer odpytuje stan z
  backoffem `1–15 s`, nie tworzy równoległych pętli i po odzyskanym `failed`
  transferze używa nowego identyfikatora próby.
- Lokalny Admin ma path-free diagnostykę partii oraz agregatowy preview GC.
  Logi i audyt zawierają wyłącznie stabilne kody/liczniki, bez kodu dostępu,
  tokenów, lease tokenu i ścieżki hosta.
- Bramka celowana: 102 testy Reviewera, 248 testów Admina, 41 testów klienta
  oraz celowane zestawy API/workera (1 test pominięty z powodu braku symlinków
  Windows), OpenAPI, Ruff i TypeScript typecheck są zielone. Focused mypy zmienionych
  modułów jest zielony; pełny import graph nadal raportuje dwa wcześniejsze,
  niezwiązane błędy w `symbol_model_iteration_repository.py`. Pełne repozytoryjne
  `npm run lint` pozostaje czerwone na ośmiu wcześniejszych błędach Ruff w
  migracjach 0045/0046 i `test_symbol_confidence.py`, a pełny `format:check` na
  31 wcześniejszych plikach; wszystkie pliki TASK-0288 przechodzą własną kontrolę
  Ruff/Prettier.

### Finalizacja zdalnej ręcznej selekcji — v0.7.39

- TASK-0287 dodaje rewizyjną barierę finalizacji. Preview blokuje zakończenie,
  dopóki istnieje aktywna operacja, transfer, akcja hosta, oczekujące usunięcie
  albo wybrany JPEG bez potwierdzonego pliku i checksummy.
- Host publikuje kompatybilne `manual-image-selection-output-v1.json` i
  `manual-image-selection-trace-v1.json` oraz wewnętrzny manifest operacyjny.
  Rewizyjny journal i ownership pointer pozwalają wznowić crash między
  filesystemem a commitem bazy bez drugiego wyniku lub nadpisania obcego pliku.
- Zakończona partia jest w Reviewerze tylko do odczytu. Zdalny operator może
  wykonać jedynie dwuetapową finalizację; reopen nie występuje w publicznej
  allowliście i wymaga lokalnego Admina, exact targetu, rewizji oraz checksummy
  finalnego manifestu.
- Monitor hosta pokazuje rewizję i checksumę finalizacji. Ponowne otwarcie jest
  dwuetapowe i dotyczy dokładnie jednej partii.
- Bramka: celowane testy API/repozytorium/filesystemu, 100 testów Reviewera i
  248 testów Admina są zielone; Ruff, TypeScript typecheck i generowany OpenAPI
  są zgodne. Nie dodano migracji ani BLOB-ów obrazów.

### Panel hosta zdalnej ręcznej selekcji — v0.7.38

- TASK-0286 dodaje do niezależnej zakładki `Ręczna selekcja` panel właściciela:
  kontrolowany picker bazy, etykietę, TTL, jednorazową kartę kodu/linku oraz
  odzyskiwalną po reloadzie listę maksymalnie 100 sesji.
- Wybrana sesja jest monitorowana co 10 sekund, lista co 30 sekund. Detail
  ogranicza wynik do 100 najnowszych partii i pokazuje total/selected/synced,
  błędy plików, oczekujące host actions, stabilne kody błędów oraz wyłącznie
  zagregowane total/free bajty dysku bez host path.
- URL jest dynamiczną projekcją bieżącego wspólnego ingressu. Dwustopniowy
  revoke używa exact session target, czyści tylko wskazaną sesję i nie zatrzymuje
  tunelu ani innych Reviewer assignments.
- Kod dostępu istnieje wyłącznie w odpowiedzi create i pamięci komponentu; nie
  trafia do list/detail, IndexedDB, localStorage ani sessionStorage.
- Bramka: 248 testów Admina, 41 testów klienta, celowane testy API/OpenAPI i
  izolowany test agregacji PostgreSQL są zielone; Admin lint/typecheck/build,
  Ruff, focused mypy i kontrola generowanego OpenAPI są zielone.

### Zdalny workspace ręcznej selekcji — v0.7.37

- TASK-0285 łączy lokalny i zdalny tryb wspólnym resolverem skrótów bez zmiany
  zachowania Admina: Enter/F zatwierdza, Tab pomija, A/Ctrl+Z cofa, strzałki
  nawigują albo zmieniają skok z ochroną kontrolek formularza.
- Reviewer konfiguruje logiczną kolekcję i partię, rejestruje naturalnie
  uporządkowany manifest stronami po 500 metadanych i pracuje na lokalnym,
  ograniczonym cache'u siedmiu Object URL-i. JPEG przed wyborem nie opuszcza
  komputera operatora, a Blob i ścieżka absolutna nie są utrwalane.
- Stan decyzji, zakres, kursor i outbox są zapisywane atomowo w IndexedDB.
  Control plane i ograniczony scheduler transferu działają w tle, zaległości po
  refreshu są skanowane stronicami, a operator widzi osobne stany local,
  pending, confirmed, synced i error oraz offline/conflict/permission/
  backpressure.
- Zoom 10–3000%, fullscreen, pionowy scroll, kierunek, przeskok i beforeunload
  zachowują parity lokalnego workflow. Utrata folder handle wymaga relinku do
  identycznego manifestu i nie usuwa decyzji.
- Bramka: 98 testów Reviewera, 245 testów Admina i 11 testów wspólnego core są
  zielone; Reviewer/Admin lint, typecheck i build są zielone (pozostają tylko
  istniejące ostrzeżenia `no-img-element`). TASK 14 nie został rozpoczęty i
  wymaga osobnego checkpointu/review TASK 13.

### Odznaczanie zdalnej selekcji i odwracalna kwarantanna — v0.7.36

- TASK-0284 implementuje `deselect`/`undo` jako generacyjny tombstone wskazujący
  wcześniejszy zastosowany `select`. Dokładny retry pozostaje idempotentny, a
  błędny target jest odrzucany przed zmianą stanu.
- Operacja sterująca anuluje starsze queued/in-flight transfery, superseduje
  starsze akcje materializacji i enqueue'uje priorytetową host action `remove`.
  Claim materializacji jest blokowany, dopóki istnieje gotowa akcja usunięcia,
  dlatego spóźniona generacja nie może ponownie opublikować odznaczonego pliku.
- Executor przenosi wyłącznie własny `seq_*` zgodny z journalem i checksumą do
  wewnętrznej, odwracalnej kwarantanny. Rename odbywa się po przypiętym uchwycie
  Windows; obcy, zmieniony lub reparse target pozostaje nietknięty. Kwarantanna
  nie ma jeszcze finalnego GC.
- Sekwencja select/deselect/reselect zachowuje nowszy desired state, ale najpierw
  bezpiecznie usuwa starszą materializację. Reviewer trwale oznacza anulowany
  checkpoint i nie wznawia transferu starszej generacji po odświeżeniu.
- Rollback ma osobną flagę
  `GAME_PREDICTOR_REMOTE_SELECTION_DESELECT_ENABLED`; wyłącza nowe odznaczenia,
  nie usuwa journalu, kwarantanny ani wcześniej zapisanych operacji.
- Bramka: 144 celowane testy API (1 symlink pominięty na tym hoście), 16 testów
  workera, 16 testów PostgreSQL i 93 testy Reviewera; Ruff, izolowany mypy,
  Reviewer lint/typecheck/build oraz OpenAPI są zielone. TASK 12 kończy się
  obowiązkowym checkpointem przed TASK 13.

### Atomowa materializacja zdalnej selekcji — v0.7.35

- TASK-0283 zamienia checksum-verified host-internal JPEG na należący do partii
  `seq_*` przez osobną trwałą akcję `materialize`. Upload i odczyt statusu
  idempotentnie uzupełniają akcję; general worker dodatkowo reconciliuje
  historyczne rekordy `verified` bez akcji po restarcie.
- Executor działa w ograniczonych cyklach, używa PostgreSQL `SKIP LOCKED`,
  czasowego lease z fencing tokenem, maksymalnej liczby prób oraz wykładniczego
  backoffu. Wygasła akcja `processing` jest odzyskiwana, a bieżąca generacja,
  desired state, transfer i checksum są ponownie blokowane i sprawdzane przed
  dostępem do filesystemu.
- Publikacja używa same-volume pliku roboczego, `fsync`, host-internal
  checksumowanego journalu i wyłącznego utworzenia finalnej nazwy. Zgodny własny
  półstan jest adoptowany po crashu; obcy cel, zmieniony własny cel, reparse lub
  starsza generacja kończą się kontrolowanym konfliktem bez nadpisania.
- Stan pliku przechodzi do `synced`, a transfer do wewnętrznego `materialized`
  dopiero po potwierdzeniu checksummy finalnego pliku. Publiczny status mapuje
  ten stan na `synced` i nie ujawnia ścieżki hosta. Verified temp pozostaje
  odzyskiwalny; usuwanie i finalizacja partii nadal należą do TASK 12/15.
- General worker wykonuje host actions przed próbą pobrania zwykłego joba.
  Limity lease/prób/cyklu mają trwałe ustawienia środowiskowe. Nie dodano
  Redis/Celery, nowego procesu ani migracji — migracja `0056` zawiera wymagane
  pola kolejki i ścieżek.
- Bramka: 131 celowanych testów API zaliczonych i 1 pominięty test
  symlinku niedostępnego na tym hoście, 92 testy Reviewera oraz izolowany test
  PostgreSQL dwóch równoległych claimerów zaliczone. 14 celowanych testów
  lifecycle workera, Ruff zmienionych plików, izolowany mypy 9 modułów,
  Reviewer lint/typecheck/build oraz OpenAPI są zielone. Pełny Ruff nadal
  raportuje wcześniejsze formatowanie migracji `0045/0046` i testu symboli, a
  pełny mypy dependency graph nie zakończył się w limicie 60 sekund.
- TASK 11 kończy się obowiązkowym checkpointem przed TASK 12.

### Strumieniowy transfer zdalnej selekcji — v0.7.34

- TASK-0282 dodaje osobne route statusu i binarnego `PUT` dla jednego
  checksum-bound JPEG-a. FastAPI konsumuje `Request.stream()` porcjami do 1 MiB,
  zapisuje `.part` pod zweryfikowanym host mappingiem i kończy najwyżej na
  host-internal artefakcie `verified`; nie tworzy jeszcze pliku `seq_*`.
- Rozmiar i mtime muszą odpowiadać niezmiennemu source manifestowi, a checksum
  potwierdzonemu `SELECT` tej samej generacji. Serwer sprawdza długość, SHA-256,
  JPEG magic/format/decode oraz limity per plik, sesję i współbieżność.
- Przerwany lub błędny stream usuwa `.part`. Status-before-retry i trwały
  `transferId` w checkpointcie odzyskują utraconą odpowiedź bez drugiego uploadu;
  po restarcie zgodny osierocony artefakt `verified` jest adoptowany po ponownej
  walidacji.
- Reviewer proxy ma oddzielną dokładną allowlistę oraz limit 32 MiB dla
  binarnego streamu. Scheduler domyślnie dopuszcza dwa transfery, ma limit
  pending bytes, priorytet, AbortController i retry wyłącznie dla błędów
  przejściowych.
- Bramka: 54 celowane testy API, 14 testów PostgreSQL i 91 testów Reviewera;
  Ruff, Reviewer lint/typecheck/build, OpenAPI i wygenerowany klient są zielone.
  Pełna regresja API wykonana wcześniej w rozłącznych grupach dała 534 testy
  zaliczone i 2 pominięte, a późniejsze zmiany ponownie pokryła celowana bramka.
- TASK 10 kończy się na checkpointcie przed materializacją TASK 11.

### Control plane zdalnej selekcji — v0.7.33

- TASK-0281 dodaje idempotentne tworzenie kolekcji i partii, stronicowaną
  rejestrację metadanych źródła oraz aktywację dopiero po zgodności kompletnego
  manifestu. Aktywny manifest nie może być zmieniony.
- Operacje selekcji są stosowane transakcyjnie w jednej kolejności
  `clientSequence/serverRevision/selectionGeneration`. Nowa mutacja wymaga
  aktualnego writer lease, natomiast exact retry identycznego `operationId` i
  checksumy zwraca zapisany outcome także po utracie lease, bez ponownego
  zwiększenia rewizji.
- Reviewer ma zamkniętą allowlistę control plane, cyfrowe query wyłącznie dla
  bounded state delta i sekwencyjny synchronizator trwałego IndexedDB outboxu.
  Potwierdzenie usuwa tylko dokładny `operationId`; błąd sieci pozostawia
  pending, a kontrolowany konflikt zachowuje operację i uzgadnia nowszy stan.
- Historycznie publiczna powierzchnia nie przyjmowała bajtów JPEG. Od TASK 10
  przyjmuje wyłącznie dokładnie ograniczony transfer do host-internal
  `verified`; materializacja i finalizacja pozostają zakresem TASK 11+.
- Bramka: 526 top-level testów API i 2 pominięte testy symlinków Windows,
  13/13 PostgreSQL (w tym indeksowany delta dla 15 000 rekordów), 85/85 testów
  Reviewera, Ruff, Reviewer lint/typecheck/build, klient API i OpenAPI są
  zielone. Pełny mypy grafu API nadal zatrzymują dwa wcześniejsze błędy w
  `symbol_model_iteration_repository.py`; zmienione moduły przechodzą kontrolę
  izolowaną.
- TASK 9 wymaga osobnego checkpointu przed TASK 10.

### Trwałe źródło i outbox zdalnej selekcji — v0.7.32

- TASK-0280 dodaje do Reviewera osobny IndexedDB
  `game-predictor-remote-manual-selection` w wersji 1. Schemat ma jawne store'y
  `sessions`, `batches`, `sourceItems`, `outbox`, `transferCheckpoints` oraz
  `clientInstances`; nie zmienia lokalnego IndexedDB v2 Admina.
- Adapter File System Access otwiera źródło wyłącznie z `mode: read`, indeksuje
  tylko metadane JPEG w deterministycznej naturalnej kolejności i przechowuje
  uchwyt katalogu bez kopiowania Blobów. `webkitdirectory` pozostaje jawnym,
  sesyjnym fallbackiem wymagającym ponownego wskazania folderu.
- Kursor i pending outbox są odtwarzane po utworzeniu nowej instancji store.
  Exact retry zachowuje `operationId`, konflikt treści i luka
  `clientSequence` są blokowane, a ack usuwa wyłącznie jawnie wymienione ID.
- Utrata permission/handle nie usuwa kursora ani outboxu. Relink wymaga
  identycznego checksumowanego manifestu i działa fail-closed przy zmianie lub
  niekompatybilnym source kind. Ścieżki absolutne/traversal i trwały Blob są
  blokowane przed zapisem.
- `BroadcastChannel` wybiera jedną kartę zapisującą w obrębie sesji; kolejne są
  read-only. Brak API przeglądarki jest jawnie komunikowany. Persist storage
  jest best effort i nie stanowi gwarancji permission.
- Bramka: 79/79 testów Reviewera i 9/9 testów wspólnego core, w tym fake FSA,
  fake IndexedDB, crash restore, exact ack, 1000 metadanych i 15 000 rekordów
  outboxu. Reviewer lint/typecheck/build oraz typecheck core są zielone.
  Chromium fixture potwierdził IndexedDB handle roundtrip i restore po reload;
  zewnętrzny Chrome nie był podłączony do sesji i pozostaje ręcznym punktem
  odbioru przed publicznym rolloutem.
- TASK 8 nie wysyła operacji HTTP ani bajtów JPEG. Control-plane apply pozostaje
  zakresem TASK 9, transfer binarny TASK 10, a pełny workspace TASK 13.

### Izolowana powierzchnia Reviewera dla zdalnej selekcji — v0.7.31

- TASK-0279 udostępnia shell `/manual-selection` i osobny same-origin proxy
  `/selection-api` w istniejącej aplikacji Reviewer. Nie powstał drugi proces
  Reviewera ani drugi Quick Tunnel.
- Zamknięta allowlista obejmuje wyłącznie unlock, context, heartbeat i takeover
  purpose-scoped sesji. Route Admina, legacy Reviewera, jobów, storage, eksportu
  oraz binarnego uploadu kończą się przed API stabilnym `403`.
- Publiczne cookie `gp_remote_selection_token` ma `HttpOnly`, `Secure`,
  `SameSite=Strict` i `Path=/selection-api`; proxy tłumaczy je na host-only
  cookie API. Token, kod, host path i fencing token nie trafiają do URL-a,
  JavaScriptu ani odpowiedzi JSON.
- Mutacje wymagają same-origin `Origin`/Fetch Metadata, JSON i maksymalnie
  128 KiB. Proxy filtruje nagłówki i odpowiedź, wymaga JSON, blokuje odpowiedzi
  ponad 128 KiB i łączy się z API wyłącznie przez HTTP loopback. Dedykowany CSP
  nie dopuszcza połączenia przeglądarki z `127.0.0.1:8000`.
- Create sesji wykorzystuje rozgrzany wspólny ingress albo uruchamia dokładnie
  jedną brakującą instancję. `reviewUrl` jest dynamiczną projekcją bieżącego
  originu i zachowuje ten sam opaque session ID po restarcie tunelu. Revoke nie
  zależy od dostępności tunelu i nie zatrzymuje go dla innych prac.
- Bramka: 62/62 testów Reviewera, 9/9 nowych testów API dostępu, 28/28 testów
  access/ingress oraz 62/62 pozostałych celowanych testów lifecycle,
  security i kontraktu. Reviewer lint/typecheck/build, Ruff, format,
  OpenAPI i klient są zielone. Lokalny production E2E potwierdził shell, brak
  błędów konsoli i ścisły CSP; rzeczywistego publicznego tunelu nie uruchamiano.
- Mypy grafu API pozostaje czerwony na dwóch wcześniejszych błędach typów w
  `symbol_model_iteration_repository.py`, po czym sam mypy kończy się błędem
  wewnętrznym. Zmienione TypeScript i kontrakty wygenerowanego klienta są
  sprawdzone; problem nie został objęty TASK-0279.
- Workspace, remote source adapter, outbox, operacje i upload pozostają zakresem
  TASK 8+. Przed TASK 8 obowiązuje checkpoint bezpieczeństwa.

### Purpose-scoped dostęp i writer lease zdalnej selekcji — v0.7.30

- TASK-0278 wydzielił wspólne primitives kodu/tokena bez zmiany parametrów ani
  zachowania istniejącego Reviewera: PBKDF2-SHA256 `210000`, sól 16 B i SHA-256
  tokenu. Regresja Reviewera przeszła bez zmian kontraktu `game/import`.
- Lokalny Admin może zużyć jednorazową base capability i utworzyć sesję z TTL
  5 minut–24 godziny. Kod jest pokazany tylko w odpowiedzi create; list/detail
  nie zawierają kodu, tokenu, client/fencing tokenu ani host path.
- Publiczne unlock/context nie zawierają bearer w JSON. Unlock rotuje token i
  ustawia wyłącznie `HttpOnly`, `Secure`, `SameSite=Strict` cookie o ścieżce
  `/selection-api`. Purpose-scoped context nie ma `gameId/importJobId`.
- Piąta trwała błędna próba blokuje sesję. Revoke natychmiast czyści token i
  lease. Jeden 45-sekundowy writer lease jest przypisany do client instance;
  heartbeat zachowuje host-only fencing token, a takeover działa dopiero po
  expiry. Audyt pozostaje append-only i path/secret-free.
- PostgreSQL potwierdził restart, równoległy unlock, pięć współbieżnych błędnych
  prób oraz exactly-one-winner takeover. PBKDF2 kosztował średnio około
  `103 ms/hash` na pięciu próbkach na obecnym komputerze.
- Celowana bramka zakończyła się wynikiem 108/108, a izolowana bramka
  PostgreSQL 12/12. Ruff, formatowanie i focused mypy są zielone.
- Pełny historyczny pytest API doszedł do 55% bez błędu, ale został przerwany
  po 120 sekundach zgodnie z limitem; proces potomny zakończono. Celowane testy,
  12 testów PostgreSQL, Ruff, focused mypy, OpenAPI i klient są bramką TASK 6.
- Nie dodano proxy/Quick Tunnel, UI, kolekcji/partii, operacji zdjęć, uploadu ani
  materializacji. Przed TASK 7 obowiązuje osobny checkpoint bezpieczeństwa.

### Bezpieczne mapowanie hosta zdalnej selekcji — v0.7.29

- TASK-0277 wydzielił jeden współdzielony, kontrolowany picker Windows bez
  caller-controlled command/path. Równoległa próba z importu i zdalnej
  selekcji nie może otworzyć drugiego okna.
- Lokalny endpoint zwraca tylko pięciominutową, jednorazową opaque capability,
  display name i expiry. OpenAPI oraz generowany klient nie zawierają ścieżki
  hosta; request nie przyjmuje body.
- Centralna polityka nazw wymusza NFC, case-insensitive key, rzeczywiste limity
  filesystemu oraz blokuje traversal, drive/UNC, separatory, reserved names,
  kontrolne znaki i końcową kropkę/spację.
- Final-handle guard blokuje reparse/symlink/junction i trzyma uchwyty bez
  `FILE_SHARE_DELETE` podczas utworzenia collection/batch. Batch dostaje
  atomowy, checksumowany marker własności; zgodny marker pozwala odzyskać
  crash-window po rollbacku DB i wznowić po restarcie.
- Testy: 104/104 celowanych unit/API/kontraktu/security oraz 8/8 izolowanych
  PostgreSQL. Junction i podstawienie TOCTOU przeszły na realnym
  Windows. OpenAPI, klient, PowerShell, Ruff i focused mypy są zielone.
- Pełny mypy monorepo został przerwany po ponad 60 sekundach bez wyniku;
  osierocony proces został zakończony. Nie rozpoczęto TASK 6.
- Rollback: ustawić
  `GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED=false` i uruchomić API
  ponownie; endpoint znika bez zmiany bazy ani markerów.

### Trwały model zdalnej ręcznej selekcji — v0.7.28

- TASK-0276 utrwalił kontrakty TASK-0275 w ośmiu addytywnych tabelach
  PostgreSQL, modelach ORM i repozytoriach SQLAlchemy/in-memory parity.
- Composite FK egzekwują `session + batch + file` scope. Globalna unikalność
  mapowania katalogu jest chroniona advisory lockiem oraz constraintem, a
  operacje zmieniają rewizję i desired state atomowo pod row lockiem.
- Dzienniki operacji i audytu są append-only także przy bezpośrednim SQL.
  Publiczne mappery nie ujawniają base/temp path, salt/hash ani lease tokenu;
  baza nie przechowuje bajtów JPEG.
- Bounded delta i plan indeksów sprawdzono na 15 000 plików i 15 000 operacji.
  Izolowane testy TASK 4: 10/10 PostgreSQL oraz 53/53 unit/migration.
- Pełna historyczna bramka PostgreSQL ma wynik 35/39: cztery istniejące testy
  spoza zakresu wymagają osobnego uporządkowania fixture
  `expected_layout_count`, kodu błędu raportu importu i duplikatów generatora.
  Nowa migracja nie zmienia tabel używanych przez te cztery testy.
- Nie dodano API, filesystem pickera, auth, uploadu, materializacji ani UI.
  Przed TASK 5 obowiązuje osobny checkpoint/review.

### Kontrakty domenowe zdalnej ręcznej selekcji — v0.7.27

- TASK-0275 zamroził wersjonowane kontrakty sesji, kolekcji, partii, pliku,
  operacji, transferu i akcji hosta bez dodawania ORM, HTTP, filesystemu ani UI.
- Siedem jawnych maszyn stanów działa fail-closed. Operacje egzekwują scope,
  monotoniczny `clientSequence`, `serverRevision`, per-file
  `selectionGeneration` i exact retry po `operationId + checksum`.
- Starsza generacja kończy się jako `superseded` bez zmiany desired state i
  rewizji. Projekcje output/trace zachowują istniejące schema v1, w tym undo
  wskazujące konkretną decyzję.
- Python i wspólny core TypeScript mają zgodną kanoniczną serializację JSON,
  SHA-256 oraz `remote-source-manifest-v1`. Test skali objął 15 000 rekordów.
- Nie powstały route, tabela, migracja ani integracja transportowa. Przed TASK 4
  obowiązuje checkpoint/review kontraktów.

### Wspólny core ręcznej selekcji — v0.7.26

- TASK-0274 wydzielił `@game-predictor/manual-image-selection-core` z czystą
  maszyną zakresów, decyzjami, naturalnym sortowaniem, polityką bounded preview
  oraz frontend-internal portami source/output/session.
- Lokalny Admin korzysta z adapterów File System Access i istniejącego store
  IndexedDB v2. Zachowano skróty, zoom, scroll, zakresy `+9`, checksum guard i
  oba manifesty v1; nie dodano API, outboxu, formatu v2 ani zdalnego UI.
- Core ma 4/4 testy, Admin 245/245. Przeszły typecheck core/Admin, lint Admina
  i produkcyjny build Admina. TASK 2 ma wymagany checkpoint przed TASK 3.

### Browser capability zdalnej ręcznej selekcji — v0.7.25

- TASK-0273 kończy TASK 1 planu zdalnej ręcznej selekcji decyzją
  `GO_WITH_CONSTRAINTS` dla browser-only MVP na desktopowym Chrome/Edge.
- Izolowany fixture potwierdził w Chromium secure context,
  `showDirectoryPicker`, IndexedDB, OPFS i `webkitdirectory`. Uchwyt OPFS
  przeszedł zapis/odczyt IndexedDB, reload oraz zamknięcie i ponowne otwarcie
  karty z permission `granted`.
- `remote-source-manifest-v1` jest deterministyczny, naturalnie sortowany,
  checksumowany i zawiera wyłącznie względne metadane. Testy 1/500/1000 nie
  wykonały decode ani odczytu bajtów JPEG.
- Permission musi być sprawdzany przy każdym resume. Brak uchwytu, grant lub
  zmieniony manifest wymagają relinku; `webkitdirectory` jest wyłącznie
  fallbackiem sesyjnym.
- Ręczne użycie natywnego pickera, odmowa/regrant i zamknięcie całej docelowej
  przeglądarki pozostają bramką przed publicznym rolloutem, ale nie blokują
  wydzielenia wspólnego core w TASK 2.
- Raport:
  `ai_docs/quality/REMOTE_SOURCE_BROWSER_CAPABILITY_SPIKE.md`; checksum JSON
  `f04dc14c...f69cd9e`. Nie dodano route, API, uploadu, bazy ani tunelu.

### Propozycja zdalnej ręcznej selekcji zdjęć — analiza TASK-0272

- Zrekonstruowano lokalny przepływ ręcznej selekcji, IndexedDB v2, zapis
  `seq_*`, manifest output/trace oraz granice File System Access API.
- Zaproponowano reuse jednego procesu Reviewer i Quick Tunnel, lecz z osobnym
  route, cookie, purpose, sesją i zamkniętą allowlistą. Obecna sesja
  `gameId + importJobId` nie może zostać użyta bez rozszerzenia modelu.
- Rekomendowany MVP używa hosta jako źródła prawdy, trwałego IndexedDB outboxu,
  trzech oddzielnych kolejek i jednoplikowego streamowanego uploadu. Protokół
  chunked pozostaje warunkowy do czasu benchmarku.
- Plan zawiera 19 osobno weryfikowalnych tasków, bramkę security, etapowy test
  8–15 tys. operacji oraz propozycje P-001–P-003 i R-001–R-005. Żadna z nich
  nie jest jeszcze zaakceptowaną decyzją; kod produkcyjny nie został zmieniony.
- Źródło: `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md`.

### Zamknięcie rollout'u geometrii v19 i modelu symboli — v0.7.23

- TASK 10 zsynchronizował wymagania, architekturę, decyzje i instrukcję
  operatorską z faktycznym wynikiem TASK 1–9. Końcowy raport:
  `ai_docs/quality/BOARD_CELL_GEOMETRY_V19_ROLLOUT.md`.
- `historical_v18` pozostaje domyślnym trybem importu. Adapter
  `board-cell-processing-v20-verified-v19-v1` jest wyłącznie staging-local
  opt-in, ponieważ cross-staging benchmark osiągnął `93,78%` pokrycia przy
  wymaganym minimum `98%`.
- V20 zachowuje fail-closed: każda plansza daje dokładnie 15 source-direct
  cropów albo trwały deferred bez inferencji. Deferred można rozwiązać ręcznie
  na końcu w tej samej kolejce Reviewera; istniejąca plansza i decyzja człowieka
  zawsze wygrywają.
- Kandydat modelu symboli TASK 9 pozostaje `rejected` po jednym błędzie
  wysokiej pewności. Aktywny fingerprint nadal wynosi
  `19e15e92...e48db64`; nie powstało zdarzenie aktywacji.
- D-214 formalizuje kontrolowany opt-in i rollback przez nowy job v18. D-215
  formalizuje odrzucenie kandydata bez osłabienia bramki.
- Umbrella TASK-0256 oraz dokumentacyjne TASK-0271 są zamknięte. Następna praca
  wersji 0.7 wymaga nowego, osobno zleconego zadania.

### Kontrolowanie odrzucony kandydat modelu v19 — v0.7.22

- TASK 9 wytrenował od początku `spatial-symbol-cnn-v1` na zamrożonej kohorcie
  321 plansz i 4815 cropów v19. Split zachował 38 rodzin train oraz po jednej
  validation, test i regression, bez przecieku źródeł.
- Najlepsza była epoka 24/40. Kandydat poprawił accuracy symboli na połączonym
  test/regression z `98,4314%` do `99,2157%`, a accuracy całych plansz z
  `88,2353%` do `94,1176%`. Recall żadnej klasy nie spadł o więcej niż 1 pp.
- ONNX top-1 parity przeszło, maksymalny błąd logitów wyniósł `0,000002861`, a
  temperatura `0,60057958` pozostała w bezpiecznym zakresie.
- Kandydat został poprawnie oznaczony `rejected`: audyt 100 plansz znalazł
  jeden błąd wysokiej pewności `lemon -> orange` dla sekwencji 35, komórki 13,
  confidence `0,99999698`. Bramka nie została osłabiona.
- Aktywny model nie został zmieniony; jego fingerprint nadal wynosi
  `19e15e92...e48db64`. Raport decyzji ma checksumę `4e6ace22...421578`.
  Szczegóły: `ai_docs/quality/V19_SYMBOL_MODEL_CANDIDATE.md`.

### Kohorta pozostałych błędów modelu v19 — v0.7.21

- TASK 8 zamroził read-only kohortę 321 ręcznie rozwiązanych plansz, 4815
  checksum-verified cropów v19, 41 rodzin źródeł i sześciu stagingów. Każda
  plansza ma dokładnie 15 komórek row-major, a split po rodzinie źródła nie ma
  przecieku.
- Audyt błędów wysokiej pewności wykrył 12 plansz z konfliktem ręcznej etykiety
  lub pozycji. Całe plansze są wykluczone fail-closed, ich 27 cropów dowodowych
  jest przypięte checksumami, a problem ma klasyfikację `OPEN` zamiast
  fałszywego błędu modelu.
- Na oczyszczonej kohorcie aktywny model osiąga `99,3354%` accuracy symboli i
  `94,3925%` całych plansz. Parity preprocessingu przeszło `4815/4815`.
  Jedyny istotny residual to M2 `plum -> grapes`: 9 błędów na dwóch nowych
  rodzinach źródeł.
- Raport wydaje decyzję `retrain`, ale TASK 8 nie uruchamia treningu ani
  aktywacji. Manifest kohorty ma checksumę `eaa368b5...523ab88`, a raport
  `c617fdf4...07d3cc`. Szczegóły:
  `ai_docs/quality/V19_SYMBOL_RESIDUAL_COHORT.md`.

### Kontrolowany opt-in importu v20 — v0.7.20

- TASK 7 podłącza istniejący `boardCellProcessingMode=verified_v19` do startu
  gotowego browser stagingu w Adminie. Każdy staging domyślnie pozostaje w
  historycznym v18; v20 wymaga jawnego, lokalnego dla stagingu potwierdzenia.
- UI pokazuje niezaliczoną bramkę `93,78% < 98%`, brak fallbacku do v18 i
  trwałe odroczenie nierozpoznanej geometrii do końcowej korekty Reviewera.
- Checksum-bound start zawsze przesyła wybrany tryb. Admin porównuje zwrócony
  niezmienny snapshot joba z wyborem i nie raportuje sukcesu przy rozbieżności;
  komunikat końcowy podaje faktycznie przypięty tryb.
- Domyślna wartość backendu, kontrakt HTTP/OpenAPI, fingerprinty algorytmów,
  próg rollout, istniejące joby i dane kanoniczne nie zostały zmienione.
- Walidacja: Admin `243/243`, klient Admin API `40/40`, oba typechecki, lint,
  build Admina, formatowanie zmienionych plików i kontrola OpenAPI przeszły.
  Lint Admina zachowuje dwa wcześniejsze ostrzeżenia `<img>` w plikach spoza
  TASK 7. Nie uruchamiano rzeczywistego importu danych użytkownika.

### Końcowa kolejka korekty geometrii — v0.7.19

- TASK 6 udostępnia w Reviewerze osobny, bounded tryb dla trwałych
  `image_board_geometry_pending`: pobiera jeden element `pending`, zachowuje
  lokalną historię opartą na stabilnym kursorze i nie materializuje całego
  importu ani jego obrazów.
- Edytor pobiera checksum-bound kontekst i źródło, pozwala przesuwać dokładnie
  cztery narożniki perspektywicznej siatki 5 × 3 oraz wymaga aktualnego podglądu
  15 cropów source-direct przed zapisem. Zmiana narożników unieważnia preview.
- Exact retry niezmienionej komendy zachowuje idempotency key. Konflikt
  manifestu, rewizji, statusu albo human-wins odświeża kolejkę bez nadpisania
  rozstrzygnięcia. Udany zapis przechodzi do następnego deferred, a utworzona
  plansza trafia do dotychczasowej kolejki zatwierdzania symboli.
- Launcher Admina pokazuje licznik `Do korekty siatki` i pozwala uruchomić
  lokalnego lub online Reviewera także dla importu z zerową zwykłą kolejką, ale
  z niezerową liczbą odroczonych plansz.
- Backend, OpenAPI, baza, domyślny v18, opt-in v20, model symboli i numery
  `seq_*` nie zostały zmienione. TASK 6 korzysta z kontraktu dostarczonego w
  TASK 5.
- Walidacja: klient Admin API `40/40`, Admin `238/238`, Reviewer `40/40`,
  typecheck i lint wszystkich trzech workspace'ów, buildy Admina i Reviewera
  oraz kontrola aktualności OpenAPI przeszły. Interaktywny smoke test nie został
  wykonany, ponieważ lokalny Reviewer na porcie 3001 nie był uruchomiony.

### Ręczne rozwiązanie deferred geometrii komórek — v0.7.18

- TASK 5 dodaje checksum-bound kontekst, source, preview i zapis dla jednego
  `image_board_geometry_pending`. Preview czterech narożników używa dokładnie
  croppera v19 i nie zapisuje danych.
- Zapis używa modelu symboli przypiętego do źródłowego importu. Dopiero komplet
  15 cropów i 15 predykcji tworzy w jednej transakcji zwykłą planszę,
  obserwacje, rewizję oraz `pending` item istniejącej kolejki Reviewera.
- Exact retry wraca bez ponownego preview/inferencji, zmieniona komenda daje
  stabilny konflikt, a istniejąca plansza wygrywa i superseduje deferred.
- API i wygenerowany klient obsługują lokalnego administratora oraz dokładnie
  scoped bearer sesję Reviewera. Reviewer proxy nadal blokuje pozostałe Admin
  API. Komponent UI korekty jest poza TASK 5.
- Domyślny v18, opt-in v20, benchmark `93,78%`, aktywny model i dane kanoniczne
  nie zostały zmienione.

### Jawnie przypięty adapter pełnego importu v20 — v0.7.17

- Na jawne polecenie właściciela TASK 4 został wykonany mimo niezaliczonej
  bramki pokrycia TASK 2. Wyjątek nie aktywuje v19 domyślnie: zwykły start
  nadal używa v18, a v20 wymaga `boardCellProcessingMode=verified_v19`.
- Snapshot `board-cell-processing-v20-verified-v19-v1` przypina cały kontrakt
  v19 i wchodzi do fingerprintu joba. `board_cell_geometry` jest trwałym
  pre-crop substage; restart i job-local rehydration odtwarzają deferrals bez
  ponownego estymowania.
- Każda plansza daje dokładnie 15 zweryfikowanych source-direct cropów v19 albo
  zero cropów oraz trwały `image_board_geometry_pending`. Błąd v19 nigdy nie
  wraca do v18 i nie uruchamia ONNX dla tej planszy.
- Migracja `0055_board_cell_geometry_pipeline_stage` rozszerza wyłącznie
  zamknięty zbiór nazw stage results. Historyczne checkpointy i domyślny
  manifest v18 pozostają niezmienione.
- Celowane testy kontraktu, workera, API, migracji i benchmarku shadow
  przechodzą `154/154`, w tym regresja zaliczająca durable deferred do granicy
  `waiting_for_review`. Pełny worker
  doszedł do `91%` bez błędu, po czym został zatrzymany zgodnie z limitem 120 s.
  Pełny mypy nadal raportuje dwa wcześniejsze błędy
  `symbol_model_iteration_repository.py`, niezwiązane z TASK 4.
- Bramka domyślnego rollout pozostaje zamknięta: `93,78% < 98%`. Przed TASK 5
  wymagany jest osobny review/checkpoint TASK 4.

### Trwały kontrakt deferred geometrii komórek — v0.7.16

- Na jawne polecenie właściciela TASK 3 został ograniczony do warstwy kontraktu
  mimo niezaliczonej bramki pokrycia TASK 2. TASK 4 został później wykonany
  wyłącznie jako jawnie przypięty opt-in; nie zmienił domyślnego v18.
- `BoardCellProcessingManifestV1` przypina źródło, sekwencję, rewizje i
  fingerprinty. `image_board_geometry_pending` utrwala `pending`, `resolved`
  albo `superseded` bez JPEG-ów, cropów i fałszywych 15 predykcji.
- Exact retry jest serializowany na zdjęciu źródłowym. Przy rozwiązaniu
  repozytorium ponownie odczytuje planszę i review; późniejsza decyzja człowieka
  zawsze kończy automat statusem `superseded`.
- Read-only API list/get, liczniki joba, OpenAPI i klient Admina są gotowe.
  Produkcyjny zapis tych rekordów przez jawny adapter v20 jest gotowy; UI
  korekty pozostaje poza zakresem.
- Migracja `0054` definiuje rekordy, a `0055` dopuszcza trwały stage v20. Pełny zestaw API bez izolowanych testów
  PostgreSQL przeszedł `410 passed, 2 skipped`; celowany zestaw kontraktu,
  migracji i jobów przeszedł `65/65`. Pełne Ruff/mypy nadal zatrzymują się na
  wcześniejszych błędach poza plikami TASK-0264.

### Cross-staging shadow benchmark geometrii v19 — v0.7.15

- TASK 2 dodał read-only, content-addressed benchmark 300 stron / 2700 plansz:
  po 50 stron z sześciu przypiętych stagingów, kompletna galeria i challenge 81
  ręcznie poprawionych plansz odziedziczony z niezmiennego raportu TASK 1.
- Dwa niezależne zapisy i osobny `--check` odtworzyły manifest
  `8640084933f74586e2a429120ac29835c7e7fa20d9ac52d91c9c2f271c22473f`.
  Czasy są celowo przechowywane w osobnych raportach, aby obciążenie komputera
  nie zmieniało checksumy wyniku jakościowego.
- Automatyczne trafienia spełniają bramki jakości: zero katastrofalnych
  przesunięć, `95,61%` accuracy symboli i `73,68%` całych plansz w challenge.
- Checkpoint ma status `REJECTED_FOR_ROLLOUT`: pokrycie wynosi `93,78%`
  (`2532/2700`) zamiast wymaganych minimum `98%`; 168 plansz zostało bezpiecznie
  odroczonych bez częściowych cropów ani inferencji.
- Produkcyjny estymator, cropper, joby, decyzje i aktywny model nie zostały
  zmienione. Warstwa kontraktu TASK 3 i jawnie przypięty adapter TASK 4 zostały
  później wykonane na polecenie właściciela. Domyślny rollout nadal wymaga
  poprawy pokrycia i ponownego zaliczenia benchmarku.
- Raport: `ai_docs/quality/BOARD_CELL_GEOMETRY_V19_SHADOW_BENCHMARK.md`.

### Read-only diagnoza cropów v18/v19 — v0.7.14

- TASK 1 przygotował `grid-cropping-vs-symbol-model-diagnosis-v1`: powtarzalny,
  content-addressed raport A/B bez zmiany jobów, modelu, review albo danych
  kanonicznych.
- Rzeczywista kohorta obejmuje 81 ręcznie rozwiązanych plansz v19 i 1215
  symboli z sześciu stagingów. Baseline v18 oraz ponowna inferencja cropów v19
  używają tego samego przypiętego fingerprintu aktywnego modelu.
- Wynik: symbol accuracy `71,03% → 95,80%`, whole-board accuracy
  `22,22% → 72,84%`, średnia liczba poprawek `4,35 → 0,63` na planszę.
  Trzy nieaktualne rewizje zostały jawnie wykluczone.
- Dokumentacja: `ai_docs/quality/GRID_CROPPING_VS_SYMBOL_MODEL_DIAGNOSIS.md`.
  Następny krok to cross-staging shadow benchmark v19; pełny import i trening
  pozostają bez zmian.

### Trwałe usunięcie `about:blank` lokalnego Reviewera — v0.7.13

- `Otwórz lokalnie` nie tworzy już pustej karty. Synchronicznie otwiera
  przewidywany loopback-only URL wybranej gry i importu, a po odpowiedzi API
  ponawia nawigację zwróconym, zwalidowanym adresem.
- Odmowa ustawienia `window.opener = null` jest izolowana i nie może przerwać
  handlera przed `openLocalReviewerWork`. Poprzednio taki wyjątek pozostawiał
  `about:blank`, a do API nie trafiało żadne żądanie.
- Poprawny URL jest zachowywany jako link ręczny również po udanej odpowiedzi,
  dzięki czemu blokada popupu lub późniejszej nawigacji nie odbiera dostępu do
  działającego Reviewera.
- Wykonywalna regresja symuluje `SecurityError` przeglądarki. Przeszło `237/237`
  testów Admina, typecheck, lint bez błędów, Prettier i build produkcyjny.
  Idempotentne otwarcie rzeczywistej pracy zwróciło `ready=true`, a jej strona
  odpowiedziała HTTP 200. Workery, joby i decyzje review nie zostały zmienione.

### Odzyskiwanie ręcznej sesji i stabilne odczyty API — v0.7.12

- Ręczna selekcja rozpoznaje nieaktualny uchwyt źródła lub wyniku i prowadzi do
  ponownego wskazania właściwego folderu. Nie tworzy nowej sesji: zachowuje
  `sessionKey`, wszystkie decyzje, kolejny zakres i pozycję, a naprawione
  uchwyty utrwala w IndexedDB.
- Zamknięte sekcje Gry nie są już montowane, dzięki czemu nie uruchamiają
  równoległych requestów podczas wejścia na ekran. Rozwinięcie sekcji zachowuje
  dotychczasowe zachowanie i kontrakty.
- Read-only podgląd kohorty oraz jakość modelu nie używają `FOR UPDATE` i nie
  materializują cropów około 67 tys. oczekujących pozycji. Lekka projekcja
  całej historii zachowuje identyczny manifest/checksumę, a pełne plansze są
  pobierane tylko dla `accepted/corrected`. Freeze nadal stosuje blokowany
  snapshot transakcyjny.
- Panel jakości wykonuje jeden ciężki odczyt `model-quality`; preview wymagany
  do zamrożenia wyprowadza z tej samej odpowiedzi, zamiast równolegle budować
  ten sam snapshot drugi raz.
- Panel siatki jest montowany dopiero po zakończeniu podstawowego odczytu
  jakości. Jego ciężki preview oczekujących nie konkuruje już o bazę w trakcie
  requestu inicjalizującego cały ekran ani nie powoduje fałszywego timeoutu.
- Na rzeczywistej bazie endpointy wróciły z timeoutu/błędu limitu parametrów do
  HTTP 200: preview około 4,9 s, model quality około 7,2 s. Workery i joby nie
  zostały zatrzymane ani zmienione.

### Ręczna selekcja niezależna od gry — v0.7.11

- Zakładka `Ręczna selekcja` otwiera lokalny workspace bez aktywnego kontekstu
  gry. Wybór folderów, wznowienie, nawigacja, zapis `seq_*` i trace nie zależą
  od odpowiedzi API ani `activeGame`.
- IndexedDB używa jednego stabilnego namespace'u narzędzia. Przy pierwszym
  wejściu najnowsza historyczna sesja per gra i jej zdarzenia są kopiowane do
  nowego namespace'u; stary rekord pozostaje nienaruszony, a `sessionKey`
  zachowuje własność istniejących manifestów.
- Format manifestu v1, checksumy, File System Access API, automatyczna selekcja,
  import plansz i workery nie zostały zmienione.
- Walidacja: `229/229` testów Admina, typecheck, celowany ESLint bez błędów oraz
  Prettier przeszły. Widok sprawdzono lokalnie bez parametru `game`.

### Numeryczna kolejność importów i czytelny wybór Reviewera — v0.7.10

- Gotowe stagingi w `Import plansz` są sortowane rosnąco po liczbie przed
  pierwszym myślnikiem. Zakres `20000-99999` jest dzięki temu przed
  `100000-150000`; nazwy bez takiego prefiksu pozostają za zakresami w
  deterministycznej kolejności.
- Dropdown `Gotowy import plansz` używa krótkiej daty i godziny, nazwy katalogu
  źródłowego oraz skróconego statusu. Nie pokazuje już skrótu technicznego ID;
  pełne ID wybranego joba jest widoczne osobno pod kontrolką.
- Etykieta dropdownu ma ograniczoną szerokość i ellipsis. Kolejność wykonywania
  jobów, statusy domenowe, API oraz działające pipeline'y nie zostały zmienione.
- Walidacja: `227/227` testów Admina, typecheck, ESLint, Prettier i produkcyjny
  build Admina przeszły.

### Monotoniczny postęp preflightu geometrii — v0.7.9

- Preflight v2 nie publikuje już tymczasowej liczby `review_required` jako
  wspólnego licznika review przed zakończeniem ograniczonych przebiegów
  auto-kotwic. Tymczasowy wynik pozostaje w trwałym checkpointcie, natomiast
  finalny licznik review jest publikowany razem z niezmiennym manifestem.
- Naprawa usuwa `JOB_PROGRESS_REGRESSION`, który występował po pełnym skanie,
  gdy auto-kotwice przenosiły stronę z tymczasowego review do `registered`.
  Progi geometrii, kolejność źródeł i zawartość manifestu nie zostały zmienione.
- Regresja obejmuje kontekst egzekwujący monotoniczność wszystkich wspólnych
  liczników. Przeszło 18 testów preflightu i domeny jobów oraz Ruff; mypy nadal
  kończy się na dwóch istniejących błędach w
  `symbol_model_iteration_repository.py`.

### Pierwszy pion wersji 0.7 — TASK-0251

- Pierwsze zadanie 0.7 naprawiło zawieszony stan ładowania przy tworzeniu reguł.
- Rzeczywisty draft v1 został zapisany, mimo że panel nie pokazał zakończenia
  operacji. Admin otrzyma ograniczony czas oczekiwania i uzgodnienie skutecznej
  mutacji przez ponowny odczyt reguł gry.
- Zakres nie zmienia domeny reguł, API, publikacji ani payoutów.
- Kontrola ujawniła dwa zgodne drafty: v1 z `10:57:38` oraz v2 z `11:00:31`.
  UI poprawnie wybiera najnowszy v2. Żaden rekord nie został usunięty.
- Walidacja: 216 testów Admina, typecheck, celowany ESLint i Prettier przeszły.

### Uproszczenie edytora wzorców — TASK-0252

- Edytor payline pozostawia administratorowi stabilny kod, aktywność i wybór
  ścieżki na siatce. Pola opisowej nazwy oraz kolejności nie są już ręcznie
  edytowane ani prezentowane w tabeli.
- Przy utworzeniu Admin zapisuje `name = code` i następną kolejność po
  istniejących rekordach; przy edycji zachowuje historyczną nazwę i kolejność.
  Pola te nadal istnieją w kontrakcie API i bazie dla zgodności.
- D-207 potwierdza, że kolejność jest wyłącznie deterministyczną prezentacją,
  bez wpływu na wynik payoutu. Walidacja: 219 testów Admina, typecheck,
  celowany ESLint oraz Prettier przeszły.

### Staging importu plansz w Reviewerze — TASK-0253

- Gotowy browser staging nie jest jobem importu i nie zawiera kolejki
  zatwierdzania; Reviewer pokazuje go jako informację pomocniczą wyłącznie,
  gdy bieżąca gra nie ma joba `waiting_for_review` albo `completed`.
- Dropdown Reviewera nadal zawiera tylko uruchomione joby z kolejką plansz.
  Karta stagingu kieruje do `Importu plansz`, gdzie właściciel jawnie wykonuje
  raport, preflight geometrii i start importu.
- Widoczne określenie produktu zostało ujednolicone do „plansza”; techniczne
  `layout` w API, modelu i danych historycznych pozostaje niezmienione dla
  zgodności.
- Walidacja: 220 testów Admina, typecheck, celowany ESLint bez błędów,
  Prettier oraz `git diff --check` przeszły.

### Pionowe przewijanie zoomu ręcznej selekcji — TASK-0254

- Lokalna ręczna selekcja nie skaluje już JPEG-a przez wizualny `transform`,
  który nie powiększał obszaru przewijania. Zoom oblicza rzeczywiste wymiary
  layoutu z naturalnych wymiarów JPEG-a i viewportu.
- Wewnętrzny viewport przewija obraz wyłącznie pionowo. Szerokie zdjęcie jest
  wyśrodkowane, a jego boki są symetrycznie przycięte bez poziomego scrolla.
  Zmiana zdjęcia wraca na górę nowego obrazu.
- Pełny ekran utrzymuje zakres, pozycję i nazwę nad przewijanym obrazem;
  File System Access API, source Blob, nawigacja i skróty nie zostały zmienione.
- Walidacja: 221 testów Admina, typecheck, celowany ESLint, Prettier,
  `git diff --check` i produkcyjny build Admina przeszły.

### Stabilny scroll i wybór skoku ręcznej selekcji — TASK-0257

- Ręczna selekcja zachowuje bieżący pionowy `scrollTop` przy przejściu między
  JPEG-ami i przywraca go dopiero po ułożeniu nowego obrazu. Wartość istnieje
  wyłącznie w pamięci aktywnego workspace'u; scroll nie zapisuje IndexedDB ani
  nie wywołuje renderowania React.
- Select skoku zawiera `1, 2, 3, 4, 5, 6, 7, 10, 15, 20` i ma jawne ciemne tło
  oraz tekst również dla natywnych opcji rozwijanej listy.

### Klawiaturowa zmiana skoku ręcznej selekcji — TASK-0259

- Poza kontrolkami formularza `ArrowDown` wybiera następną skonfigurowaną
  wartość skoku, a `ArrowUp` poprzednią. Przykładowo `2 → 3`, natomiast `7 →
  10`; wartości krańcowe pozostają przy `1` i `20`.
- Ustawienie nadal trafia do istniejącego stanu sesji i serializowanej kolejki
  IndexedDB. Nie zmienia zdjęcia, zakresu ani śladu uczenia.
- Walidacja: `225/225` testów Admina, typecheck, produkcyjny build i celowany
  ESLint bez błędów; pozostało jedno istniejące ostrzeżenie o celowym `<img>`
  dla lokalnego Blob URL.

### Automatyczne odzyskiwanie konfliktu Reviewera — TASK-0258

- Plansza `253` importu `b2d9b299…` została faktycznie zaakceptowana i ma jedną
  append-only rewizję. Komunikat `IMAGE_REVIEW_REVISION_CONFLICT` pochodził z
  ponownej komendy opartej na starszym snapshotcie rewizji `0`, nie z utraty
  decyzji ani błędu symboli.
- Konflikt rewizji pełnej decyzji automatycznie unieważnia klucz starej komendy
  i pobiera aktualny item. Reviewer nie pozostaje na niezapisywalnym buforze,
  ale nadal nie nadpisuje decyzji zapisanej w innym oknie lub przez inną osobę.
- API, baza, bounded prefetch i konflikty geometrii pozostały bez zmian.
  Walidacja: `35/35` testów Reviewera, typecheck, ESLint i build produkcyjny.

### Odzyskiwanie otwarcia i zapisu Reviewera — TASK-0255

- Lokalny launcher przekazuje zwrócony URL do przygotowanego okna przed
  pomocniczym odświeżeniem overview. Błąd nawigacji zamyka pustą kartę i
  pozostawia w Adminie ręczny link, zamiast zatrzymywać użytkownika na
  `about:blank`.
- Zapis decyzji Reviewera ma limit 12 sekund na próbę. Po pierwszym timeoutcie
  klient wykonuje dokładnie jedno ponowienie niezmienionej, idempotentnej
  komendy. Drugi timeout odblokowuje przycisk i jawnie komunikuje, że zapis mógł
  zostać przyjęty.
- Rzeczywista decyzja zgłoszona 21 sierpnia 2026 została potwierdzona w bazie
  jako `accepted`; poprawka nie usuwa ani nie powiela istniejącego zdarzenia.
- Walidacja: 222 testy Admina, 35 testów Reviewera, typecheck obu aplikacji,
  ESLint (dwa istniejące ostrzeżenia Admina bez błędów) oraz Prettier przeszły.
  Produkcyjnych procesów i aktywnego udostępnienia nie zatrzymano.

### Przejście z wersji 0.6 do 0.7 — 2026-08-21

- Właściciel zamknął całą pozostałą kolejkę zadań bezpośrednio w
  `ai_docs/tasks/`. Każde zadanie zostało przeniesione do `tasks/completed/`
  z zachowanym Outcome oraz jawnym powodem zamknięcia.
- TASK-0149 jest zaakceptowany na podstawie ciągłego testowania panelu Admin
  przez właściciela bez zgłoszonych problemów; regresje pending-only lub
  pinningu modeli wymagają nowego zadania 0.7.
- TASK-0208 jest zamknięty po akceptacji poprawy geometrii i rozpoznawania
  symboli na bazie wcześniejszych 63 plansz. Kolejne pomiary wydajności muszą
  używać aktualnego pipeline'u i osobnej bramki 0.7.
- Historyczne zadania selektorów v9–v10.18 oraz ręcznego eksportu luk zostały
  oznaczone jako zastąpione przez późniejsze implementacje i workflow ręczny.
- Nie ma obecnie aktywnego zadania implementacyjnego. Nowy zakres 0.7 powstaje
  dopiero po osobnym planie i akceptacji właściciela.

### Domykanie statusu importu po review — v0.6.79

- Migracja `0053_image_review_job_completion` wiąże status gotowego importu z
  trwałym `image_review_queue_states`: ostatnia rozwiązana plansza przełącza
  `waiting_for_review -> completed` i ustawia `finished_at`.
- Ponowne otwarcie planszy przez korektę geometrii wykonuje przejście odwrotne i
  czyści `finished_at`; ukończony import nadal pozostaje dostępny do audytu.
- Backfill obejmuje historyczne importy z `total_count > 0` i
  `pending_count = 0`. Po lokalnej migracji rzeczywisty import `50cfdcad…` ma
  status `completed`, `63 corrected` i zero pending. Duży import `b2d9b299…`
  zachował `waiting_for_review`; przy kontroli miał `19 707 pending`.

### Przyrostowy import layoutów — implementacja v0.6.34–v0.6.37

- Dodano kanoniczną projekcję `game_id + sequence_number` oraz migracje
  `0045_canonical_image_sequences`, `0046_image_symbol_prediction_revisions`
  i `0047_pending_symbol_reinference_job`. Zatwierdzony lub poprawiony numer
  nie może zostać ponownie otwarty przez kolejny import; alternatywne źródło
  jest zapisywane wyłącznie jako metadana.
- Import tworzy snapshot znanych numerów, udostępnia preflight `seq_*` i przed
  rejestracją pomija kompletne, już rozwiązane źródła. Źródła częściowe są
  przetwarzane tylko dla brakujących pozycji. Job zapisuje ten snapshot w
  `canonical_sequence_numbers`, więc restart nie zmienia decyzji.
- Review ma dodatkową kanoniczną kolejkę gry sortowaną po numerze sekwencji
  (`/admin/image-review-items/canonical/{game_id}`); kolejka ukrywa numery już
  zajęte przez kanoniczny rejestr. Job-local review pozostaje dostępny do audytu.
- Uzgodnienia zaakceptowane podczas retry wygrywają z automatem. Starsze
  oczekujące duplikaty są oznaczane jako `reused_accepted`, a zapis stagingu
  jest usuwany.
- Dodano jawny job `image_symbol_reinference`. Worker czyta istniejące cropy,
  zapisuje append-only rewizje predykcji i przed każdym zapisem blokuje pozycję;
  akceptacja/correction/reject wykonana równolegle jest pomijana. Oryginalne
  obserwacje, decyzje i checksumy nie są nadpisywane.
- Panel jakości otrzymuje diagnostykę kohorty siatki z rozbiciem na geometrię
  automatyczną, ręcznie poprawioną, brak detekcji i niekompletne dane.
- Dodano jawny job `image_grid_reinference` oraz podgląd i przycisk
  `Przelicz oczekujące`. Worker ponownie wykrywa siatkę i tworzy source-native
  cropy tylko dla pozycji `pending`, zapisując rewizję geometrii; decyzje
  `accepted/corrected/rejected` są chronione blokadą i nie są modyfikowane.
- Przeliczenie symboli korzysta z najnowszej rewizji cropów geometrii, więc po
  odświeżeniu siatki nie wymaga ponownego importu ani OCR.

## Zamknięcie wersji 0.5

Właściciel zamknął wersję 0.5 dnia 2026-08-12 i zaakceptował selektor
`fast-image-selector-v10.9` jako wystarczająco dobrą podstawę dalszej pracy.
Akceptacja zachowuje manualny fallback, fail-closed dla niejednoznacznych
zakresów i trwające runy operatorskie. Nie oznacza zaliczenia niewykonanych
bramek pełnego importu, skali ani hardeningu.

TASK-0208, TASK-0150, TASK-0076, TASK-0080–0089, pełna publikacja około 500 000
layoutów, kolejne gry i końcowy hardening pozostają jawnie odroczone.
`massImportAllowed` nie został otwarty. Plan wejściowy następnego toru znajduje
się w `delivery/VERSION_0_6_EXECUTION_PLAN.md`.

## Aktywne tory wydań

### Wersja 0.6

- TASK-0241 wprowadza domyślny `fast-image-selector-v10.10` o fingerprintcie
  `282b08df4c3368c60e60048ac846d95bc41392631ebdeaf069f3afbdef9e4c7f`;
  v10.9 zachowuje fingerprint `6c14854d3f38744a3451da11e516bc4f10c348d3f8a4c32e9a999c69e9979720`,
- v10.10 czyta etykiety ze wszystkich trzech rzędów, odrzuca częściową kotwicę
  bez obserwowanej planszy w górnym rzędzie, kontroluje zgodność modulo 9 z
  początkiem zbioru i rozdziela tylko udowodnione kolejne zakresy ukryte w jednej
  grupie wyglądu,
- anulowany run v10.9 źródła `200557 - 222912` zatrzymał się na
  `24 896 / 42 422`; staging `31ea25c9-c1a8-425d-9756-15bd597ee9c4` został
  zachowany, a dalsza kolejka operatorska jest wstrzymana do startu świeżego
  runu v10.10,
- regresja pięciu realnych JPEG-ów przeszła `5/5`, w tym poprawne
  `208090–208098` i `208108–208116` zamiast wcześniejszych przesunięć o trzy;
  profil pierwszych 1440 zdjęć trwał `159,84 s` i zakończył 101 grup jako 88
  automatycznych, 12 duplikatów oraz 1 przypadek ręczny, bez zakresu spoza
  siatki i bez podwójnego automatycznego zakresu,
- profil nie syntetyzuje trzech zakresów bez rozpoznanego JPEG-a:
  `200710–200718`, `200800–200808` i `201367–201375`; jest to jawny brak
  dowodu w próbce, nie błąd automatycznie przypisanego numeru,
- TASK-0231 rozpoczął implementację od jakości i kompletności `Importu
layoutów`; nie zmienia ani nie zatrzymuje trwających runów selekcji zdjęć,
- detektor v3 dopuszcza częściową rekonstrukcję siatki 3 × 3 wyłącznie przy
  jednej jednoznacznej hipotezie; przypadek wieloznaczny nadal jest fail-closed,
- cropper v17 nie materializuje rozciągniętej planszy `500 × 300`: zapisuje
  natywny osiowy kontekst ze źródła, a każdą komórkę projektuje bezpośrednio do
  rozmiaru wejścia modelu w jednym resamplingu,
- Reviewer pokazuje nowy source-native context bez transformacji, zachowując
  kompatybilny viewport dla historycznych importów,
- Admin rozdziela liczbę przetworzonych zdjęć od liczby plansz do review,
  ostrzega o niekompletnym wyniku i pozwala utworzyć nowy job z zachowanych
  managed originals bez ponownego uploadu,
- ciągłość strony może naprawić pojedynczy brak albo błąd OCR tylko przy co
  najmniej trzech zgodnych kotwicach i jednoznacznej przewadze; raw OCR pozostaje
  zachowany osobno,
- rzeczywista regresja importu `04909a56-edc6-42b5-860e-70c662189d1d` została
  odtworzona na siedmiu managed originals: wynik v0.6 to 63 plansze, 945 komórek
  i ciąg `1–63`, zamiast wcześniejszych 9 plansz,
- lista procesów selekcji pokazuje krótką datę, wersję silnika i zagregowany
  zakres `seq`, bez technicznego ID i statusu w etykiecie dropdownu.
- TASK-0242 zachowuje `fast-image-selector-v10.11` o fingerprintcie
  `a3c3fcb1c36a1fe9e5a95b242aaa2d7d31ec067b28f1a16fe3f29ecb7318bc0c`
  oraz `fast-image-selector-v10.12` o fingerprintcie
  `d1f482ef3b52f62d478e9bcd3c06777d0e62eb118bb639a854fbb2cb594b0727`
  i wprowadza domyślny `fast-image-selector-v10.13` o fingerprintcie
  `b52b09737bf59eae712f7757c8e368fbfaf52e56f351889fbd3aa873a3d5fd30`
  oraz idempotentny run pochodny dla 748 historycznych grup
  `range_required`; naprawa nie ufa starym
  granicom ani reprezentantowi, lecz przebudowuje lokalne bloki z pełnej
  kolejności kandydatów i zachowuje źródłowy run bez zmian,
- worker i narzędzie dry-run używają tej samej czystej funkcji recovery;
  lokalny blok zachowuje globalną kontrolę modulo 9, ale nie jest błędnie
  kotwiczony jako początek całego zbioru. Automatyczny wynik jest dodatkowo
  cofany do `range_required`, jeżeli reprezentant nie potwierdza zakresu własnym
  OCR albo zakres pochodzi wyłącznie z kotwicy/kontynuacji,
- manualne ustalanie zakresu pozwala zmienić JPEG, podać tylko początek
  (domyślny koniec `+8`), opcjonalnie skrócić ostatnią grupę albo ją odrzucić;
  modal nie wykonuje już pełnego reconcile folderu przed otwarciem,
- dry-run ma trwały kontrakt raportu, sprawdza 748 grup, snapshot źródła,
  unikalność JPEG-ów i zakresów, pochodzenie oraz własny dowód reprezentanta.
  Losowanie 100-elementowej próby jest deterministyczne i wymaga osobnego
  audytu właściciela z zerem błędnych zakresów,
- run v10.10 `200557 - 222912` zakończył 42 422 / 42 422 w 14 823,171 s:
  3813 grup, 1967 wyników automatycznych, 512 manualnych, 1294 pominięte i zero
  błędów. Kontroler zatrzymał się naturalnie, stare API zostało zamknięte, a
  baza jest na migracji `0043_image_selection_sequence_bounds`,
- pełny dry-run v10.11 przeanalizował 748 grup, 32 079 JPEG-ów i 39 bloków w
  5350,894 s bez zmiany snapshotu źródła. Wynik 1880 automatycznych, 5
  `range_confirmed`, 283 `range_required` i 127 `skipped_existing_range` nie
  zaliczył limitu 14 oraz wykrył jeden `DUPLICATE_OUTPUT_RANGE`, dlatego run
  pochodny nie został utworzony,
- analiza niezaliczonego dry-runu wykazała, że 282 przypadki kończyły jako
  `RANGE_LABEL_LATTICE_INCOMPLETE`, a 252 nie miały żadnej alternatywnej
  hipotezy. V10.12 dopuszcza dwie etykiety od `0.90` tylko jako słaby dowód
  wymagający zgodności dwóch różnych checksum i globalnie uzgadnia duplikaty
  zakresów pomiędzy lokalnymi blokami. Konflikty i pojedynczy JPEG pozostają
  fail-closed,
- walidacja v10.12 przeszła 696 testów w pełnym przebiegu workera;
  jedyny niezależny test HTTP przerwany chwilowym `WinError 10053` przeszedł
  `1/1` przy natychmiastowej powtórce. Przeszły też 332 wykonane testy API (24
  świadomie pominięte), 198 testów Admina, skupiony Ruff/mypy, kontrola OpenAPI,
  ESLint i typecheck Admina,
- analiza liczności ujawniła, że źródło `1–19809` ma 2295 fizycznych fragmentów,
  lecz v10.12 zachowywał tylko 2167 logicznych właścicieli zamiast wymaganych 2201. V10.13 zapisuje inkluzywny koniec sekwencji, wylicza grupy jako
  `ceil((abs(last-first)+1)/9)` i uzgadnia pełną projekcję z ciągłą siatką;
  decyzje użytkownika są twardymi ograniczeniami, a duże false merge wracają do
  segmentacji,
- ostateczny dry-run v10.13 na 32 079 zachowanych JPEG-ach zakończył 50 bloków
  oraz 24 684 kandydatów bez błędów skanu i problemów strukturalnych. Projekcja
  ma 2298 fizycznych fragmentów: 2181 automatycznych, 15 manualnych, 5 wcześniej
  potwierdzonych i 97 duplikatów, czyli dokładnie 2201 logicznych właścicieli.
  Nie pozostał żaden `range_required`; automatyczne bramki przeszły. Powtórka z
  7840/7840 trafieniami cache trwała 105,395 s,
- twarda bramka pokrycia potwierdziła, że wszystkie `2201/2201` logiczne grupy
  mają co najmniej jeden rzeczywisty JPEG z manifestu 32 079 plików; liczba grup
  pustych oraz referencji spoza manifestu wynosi zero,
- `readyForRecoveryCreation=false` wynika już tylko z oczekującego audytu
  właściciela na deterministycznej próbie 100 wyników. Kolejka i utworzenie runu
  pochodnego pozostają wstrzymane do audytu z zerem błędnych zakresów.
- Etap `v0.6.11` normalizuje całe repozytorium aktualnymi konfiguracjami
  Prettier i Ruff Formatter. Pełne kontrole formatowania, lint wszystkich
  workspace'ów, Ruff, składnia 32 skryptów PowerShell oraz mypy dla 327 modułów
  przechodzą. Usunięto też flakiness lokalnego serwera symbol review na Windows:
  wczesne 403 opróżnia ograniczone body POST przed odpowiedzią, dzięki czemu
  socket nie jest zamykany przez RST; scenariusz przeszedł 10/10 powtórzeń.
- Po formatowaniu przeszły testy Admina 198/198, Mobile 82/82, Reviewera 23/23,
  klienta API 37/37 i shared-ts 24/24. Pełny przebieg Python doszedł do 98% z
  jedynym `WinError 10053`; po trwałej naprawie sam plik przeszedł 5/5, test
  krytyczny 10/10, a cały końcowy segment workera 40/40. OpenAPI, snapshot oraz
  fixture validation również przechodzą.
- Etap `v0.6.12` rozszerza rerun istniejącego managed stagingu o jawny
  `lastSequenceNumber`. Historyczny staging 32 079 JPEG-ów może dzięki temu
  utworzyć pełny run v10.13 z zakresem `1–19809`, oczekiwaną liczbą 2201 grup i
  odrębnym kontrolowanym PID/reportem, bez ponownego uploadu ani dziedziczenia
  pustego końca ze starego runu.
- Walidacja v0.6.12: 334 testy API przeszły, 24 integracje środowiskowe zostały
  jawnie pominięte; pełny Ruff potwierdził format 518 plików i brak lint errors,
  parser zaakceptował 33 skrypty PowerShell, mypy przeszedł 327 modułów, a
  OpenAPI i wygenerowany klient Admina pozostają aktualne.
- Etap `v0.6.13` atomizuje końcowy zapis uzgodnionej projekcji v10.13. Worker
  zwalnia modyfikowalne automatyczne zakresy przed ich ponownym przypisaniem,
  zachowuje decyzje użytkownika i przed commitem sprawdza dokładną liczność oraz
  siatkę. Konflikt ma stabilny kod
  `IMAGE_SELECTION_PROJECTION_PERSISTENCE_CONFLICT`, a checkpoint używa już
  projekcji po reconciliacji. Manifest i fingerprint v10.13 pozostają bez zmian.
- Raport operatorski schema v3 zawiera oczekiwane/rzeczywiste grupy logiczne,
  duplikaty, dokładne statusy, brakujące/powtórzone/pozasiatkowe zakresy i osobną
  bramkę plików. Terminalny eksport wraca do pierwszej grupy, obejmuje
  `range_confirmed` i usuwa wyłącznie stare `seq_*.jpg`; job nieudany jest
  audytowany bez mutowania wyników.
- Walidacja v0.6.13: 709 testów workera i 334 wykonywalne testy API przeszły;
  25 testów API pominięto zgodnie z warunkami środowiskowymi, a nowa regresja na
  izolowanym PostgreSQL przeszła 1/1. Ruff potwierdził format 518 plików i brak
  lint errors, mypy przeszedł 327 modułów, OpenAPI i generowany klient są
  aktualne.
- Próba wznowienia pełnego runu na v0.6.13 ujawniła drugi wariant tego samego
  problemu: grupa automatyczna zmieniała reprezentanta, ale stary element
  `top_candidates` nadal miał historyczne `selected_automatic` lub
  `selected_manual`, co kolidowało z
  `uq_image_selection_candidates_selected_group`. Transakcja poprawnie wykonała
  rollback i raport v3 nie uznał częściowego eksportu za wynik.
- Etap `v0.6.14` zwalnia przed końcowym zapisem także sloty kandydatów wszystkich
  niechronionych grup, traktuje `selected_candidate` jako jedyne źródło wyboru i
  po zapisie kontroluje dokładnie jednego reprezentanta każdej gotowej grupy.
  Diagnostyczna transakcja na rzeczywistych 2298 grupach przeszła w 81,5 s i
  została celowo wycofana bez zmiany bazy. Regresja PostgreSQL przeszła 1/1,
  testy skupione 24/24; pełny worker zakończył 709 testów poprawnie, a jedyny
  niezależny `WinError 10053` przeszedł 1/1 przy natychmiastowej powtórce.
- Wznowienie v0.6.14 trwale zapisało dokładnie 2298 grup fizycznych, 2201
  logicznych właścicieli i 97 duplikatów bez luk, duplikatów zakresu ani pozycji
  poza siatką. Job zatrzymał dopiero kolejny checkpoint kodem
  `JOB_PROGRESS_REGRESSION`: aktualna projekcja miała 1406 gotowych i 795
  manualnych grup, podczas gdy historyczny ogólny licznik sukcesów wynosił 1888. Etap `v0.6.15` zachowuje dokładne liczniki projekcji w checkpoint
  payload, a ogólne liczniki joba zapisuje jako monotoniczną kopertę również w
  retry, recovery i publikacji. Fingerprint v10.13 i wynik rozpoznawania nie
  zmieniają się.
- Po commicie v0.6.15 ten sam run `7ef1bffe-5dd8-4443-b8cc-77b50a5fefcd` i job
  `ccc8db3a-0ebb-4691-a7e4-c68c9c59ddd7` zostały wznowione z checkpointu
  `32079/32079`, bez OCR. Job zakończył jako `waiting_for_review`: 2298 grup
  fizycznych, 2201 logicznych właścicieli, 97 duplikatów, 1406 wyborów
  automatycznych i 795 manualnych. Brak luk, powtórzonych zakresów i pozycji poza
  siatką; `logicalCoverageValid` oraz `outputCoverageValid` są prawdziwe, a
  katalog `C:\Users\user\Documents\1-19809 v10.13` zawiera dokładnie 1406
  plików dla 1406 gotowych grup. Raport:
  `artifacts/image-selection-v1013-resume-v0615-1-19809.json`.
- Walidacja v0.6.15: 711 testów workera, 30 testów domeny/API jobów, Ruff i mypy
  dla 327 modułów przeszły. Jedna próba długiej transakcji została odzyskana
  przez ten sam worker po lease i zakończyła idempotentnie na `attemptCount=6`;
  dla kolejnych dużych projekcji czas transakcji względem lease pozostaje
  obserwowaną metryką operatorską.
- Następny pełny run v10.13 został uruchomiony z kompletnego historycznego
  stagingu 42 403 JPEG-ów dla zakresu `19810–45152`, bez ponownego uploadu. Run
  `13db48f3-7551-498c-aec2-a62016f23f3c` i job
  `09d131ab-f1e0-4172-b372-749db511166e` zapisują do nowego katalogu
  `C:\Users\user\Documents\19810-45152 v10.13`; oczekiwana liczba logicznych
  grup wynosi 2816. Raport i PID state to odpowiednio
  `artifacts/image-selection-v1013-live-19810-45152.json` oraz
  `.runtime/live-image-selection-v1013-19810-45152.pid.json`. Nie uruchamiać
  drugiego runu ani workera; przed ingerencją sprawdzić oba pliki i heartbeat.
- Etap `124129–149634` na v10.13 zakończył skan wszystkich 21 211 JPEG-ów, ale
  nie przeszedł bramki `IMAGE_SELECTION_GROUP_CARDINALITY_UNDERFLOW`: powstało
  2678 fragmentów wobec 2834 wymaganych grup. Audyt wykazał false merge 110
  kolejnych JPEG-ów obejmujących wiele różnych zakresów, bez błędów odczytu
  plików. Kolejka pozostaje zatrzymana na tym etapie.
- Domyślny selektor v10.14 nakłada dla pełnego runu limit fizycznego fragmentu
  wyliczony z liczby źródeł i oczekiwanych grup. Dla `124129–149634` limit wynosi
  7, co gwarantuje co najmniej 3031 fragmentów przed uzgodnieniem dokładnych
  2834 właścicieli. Fingerprint v10.14 to
  `f74178fb612e636d3b7a501f4e0490d450f2bb69903e5dfdde47d9c5a24dc5a8`;
  v10.13 pozostaje niezmienne.
- Izolowany rerun v10.14 `124129–149634` zakończył 21 211 / 21 211 JPEG-ów jako
  `waiting_for_review`: 3904 fragmenty fizyczne, dokładnie 2834 grupy logiczne,
  2743 automatyczne, 91 manualnych i 1070 duplikatów. Brak luk, powtórzeń oraz
  pozycji poza siatką; obie bramki raportu przeszły, a błąd liczności nie
  powrócił.
- Run v10.14 `149626–177288` zakończył 21 211 / 21 211 JPEG-ów jako
  `waiting_for_review`: 4273 fragmenty fizyczne, dokładnie 3074 grupy logiczne,
  2971 automatycznych, 103 manualne i 1199 duplikatów. Selekcja trwała
  24 377,456 s. Kolejka ma stan `paused_after_current` i nie uruchamia następnego
  etapu podczas prac nad wydajnością.
- Domyślny v10.15 zastępuje stały limit v10.14 adaptacyjnym
  `ceil(remaining_sources / remaining_groups)`. Zachowuje naprawę false merge,
  ale nie wymusza nadmiarowych fragmentów wyłącznie przez zaokrąglenie w dół.
  Fingerprint v10.15 to
  `70914754a2e0c2c339d2ce8adb9fdaab869ad137b88bb9e1596837bcaa3fe93d`;
  v10.14 i starsze manifesty pozostają rozwiązywalne i niezmienne.
- Domyślny v10.16 zachowuje partycjonowanie v10.15 i dodaje szybki etap OCR:
  center-first `1 → 2 → 4`, szeroki poziom 12 oraz wymóg dwóch mocnych zgodnych
  odczytów z różnych JPEG-ów. Słaby dowód, konflikt lub brak konsensusu wraca do
  pełnej ścieżki z poziomem 18. Fingerprint v10.16 to
  `15c9631000d9deb077b6907dc8cda34309a1e328ffe49273fb802fdb91851bad`.
  Kolejka pozostaje zatrzymana do walidacji i benchmarku na tym samym stagingu.
- Walidacja kodu v10.16 przeszła 724 testy workera, 188 testów skupionych,
  Ruff/format dla 208 plików i mypy dla 255 modułów. Benchmark realnego stagingu
  pozostaje jedyną bramką wydajności przed decyzją o wznowieniu kolejki.
- Benchmark prefiksu 100 rzeczywistych JPEG-ów wykazał regresję v10.16:
  177,692 s i 144 weryfikacje wobec 137,677 s i 101 weryfikacji v10.15.
- Domyślny v10.17 ogranicza reprezentantów do pięciu wewnętrznych kwantyli
  `50%, 35%, 65%, 15%, 85%`, etapami `1 → 3 → 5`. Pierwszy i ostatni JPEG nie
  są próbkowane. Każdy JPEG przechodzi najwyżej raz przez progresywny verifier
  `12 → 18`; nie ma drugiej ścieżki ani ponownego OCR reprezentanta.
  Fingerprint v10.17 to
  `1cc0406ec6a908bb2609d1a331b4ec7a025fabbcb9fd5c38ab488f0ae2066726`.
  Siedem próbek pozostaje wyłączone do czasu pomiaru skuteczności pięciu.
- Kolejka nadal ma stan `paused_after_current`; wdrożenie v10.17 nie uruchomiło
  żadnego joba ani następnego etapu.
- Benchmark na identycznym prefiksie 100 JPEG-ów i 15 grupach zakończył v10.17
  w `79,855540 s` oraz dokładnie 75 weryfikacjach, wobec `131,386839 s` i 101
  weryfikacji v10.15. Zysk wall time wynosi `39,221051%`. Raport znajduje się w
  `artifacts/image-selection-v1017-v1015-real-149626-prefix100.json`.
- Walidacja v10.17 objęła 207 testów selektora/joba/adapterów/benchmarku, pełny
  zestaw 733 testów workera, Ruff i Ruff Formatter dla 519 plików oraz mypy dla 328
  modułów. W ostatnim powtórzeniu pełnego zestawu 732 testy przeszły, a
  niezależny test niezmienności APK zaliczył natychmiastowy izolowany retry;
  zmieniony smoke benchmark selekcji także przechodzi osobno.
- TASK-0243 rozdziela lokalne i zdalne uruchomienie Reviewera. Przycisk
  `Otwórz lokalnie` uruchamia stały proces na `127.0.0.1:3001` bez Internetu,
  tunelu, sesji i kodu oraz otwiera wybraną grę/import. Publiczny workflow z
  Cloudflare, linkiem, kodem i revoke pozostaje bez zmian.
- Lokalny Reviewer może wykonywać z originu `127.0.0.1:3001` wyłącznie trzy
  mutacje należące do workbencha: podgląd geometrii, zapis rewizji geometrii i
  zapis decyzji. Pozostałe mutacje Admin API nadal wymagają originu Admina.
- Kontroler Quick Tunnel uznaje publiczny URL za uruchomiony dopiero po
  poprawnym rozwiązaniu DNS i odpowiedzi HTTP. Martwy przydział jest zamykany,
  a kontroler wykonuje drugi ograniczony start zamiast publikować niedziałający
  link.
- Ręczna korekta siatki zachowuje stały natywny kadr referencyjny z numerem;
  zapis aktualizuje cropy 15 pól, ale nie perspektywę ani skalę prawego
  podglądu. Osobne CORS-safe klucze cache pozwalają ponownie otworzyć edytor po
  dowolnej zapisanej rewizji.
- Kohorta kalibracji siatki obejmuje także zatwierdzone plansze z bezpośredniego
  importu bez `imageSelectionRunId`; takie próbki uczą i wykorzystują fallback
  pozycji. Bieżące 63 plansze nie są już błędnie raportowane jako pusta kohorta.
- Trening symboli można rozpocząć od dowolnej dodatniej liczby kompletnych
  plansz. Progi 100/1000 są tylko ostrzeżeniami, a aktywna Selekcja Zdjęć nie
  udaje blokującego joba treningowego.
- Właściciel odrzucił jakość v10.18 po wykryciu częstych przesunięć zakresu.
  Run `229913–248184` został anulowany przy `8160/42420`; kolejka nie ma być
  wznawiana. Audyt wykazał, że wszystkie 3904 automatyczne wybory dwóch
  ukończonych runów v10.18 dostały `RANGE_CARDINALITY_INFERRED`, a reconciler
  mógł promować JPEG bez własnego zakresu. TASK-0244 wdraża proof-first v10.19:
  minimum trzy zgodne etykiety, zero automatu z liczności i zimny limit 7 h.
- Kandydat v10.19 ma fingerprint
  `18886fe8f54aaa161f4ab59fd793a6c8c498d9046ec565b45e23d4cb857da351`.
  Automat wymaga trzech pozycji z jedną parą sąsiadującą i wspólną bazą,
  zapisuje surowe obserwacje OCR, używa progresywnych poziomów `6 -> 12`,
  wyłącza poziom 18 oraz nie korzysta z historycznej promocji cache. Zakotwiczona
  trasa najpierw wykonuje jeden batch wariantu przetworzonego i uruchamia surowe
  cropy tylko przy braku jednoznacznego dowodu. Reconciler nie wypełnia luk ani
  nie promuje `RANGE_CARDINALITY_INFERRED`; nieudowodnione grupy pozostają bez
  zakresu w `range_required`.
- Admin pokazuje dla kandydata sugestię albo mocny dowód wraz z pozycjami i
  confidence. Raport v10.19 oddziela automaty, potwierdzenia ręczne, oczekujące,
  duplikaty i brakujące zakresy; częściowy `waiting_for_review` nie jest błędem,
  ale `logicalCoverageValid` pozostaje fałszywe do rzeczywistego domknięcia.
- Pełne testy workera przechodzą `750/750`, API `339` z `25` jawnymi skipami,
  Admin `201/201`; Ruff, OpenAPI, typecheck Admina i mypy `329` plików są zielone.
  Pierwszy zimny benchmark v10.19 na 5000 zdjęć zajął `3552,458 s`; dominował OCR
  (`3214,957 s`, 13 134 cropy). Po optymalizacji przetworzonego batcha i poziomów
  `6 -> 12` powtórka zajęła `666,585 s` (poprawa `81,2%`) i prognozuje około
  `1,57 h` dla 42 500 zdjęć. OCR spadł do `438,076 s` i 10 560 cropów; nadal jest
  zero naruszeń dowodu i zero automatu z liczności.
- Kontrolowany run v10.19 `7bd76e70-8c9a-4204-bab7-1dbfae32ac27` przeskanował
  `32079/32079` i początkowo wycofał końcową transakcję kodem
  `IMAGE_SELECTION_PROJECTION_PERSISTENCE_CONFLICT`: sugerowany kandydat grupy
  `range_required` był błędnie materializowany jako `selected_automatic`.
  Warstwa SQL ogranicza teraz flagę wyboru do gotowych statusów i zwalnia oba
  historyczne warianty wyboru. Ten sam job wznowiono bez OCR; zakończył jako
  `waiting_for_review` z 1776 automatami, 491 grupami do ustalenia zakresu,
  316 udowodnionymi duplikatami oraz 1776 plikami w
  `C:\Users\user\Documents\1-19809 v10.19`.
- Po tej walidacji uruchomiono pojedynczy kolejny run v10.19
  `7dbd3a54-8f6f-435d-bdbd-bf9e8373657a` z kompletnego stagingu 42420 JPEG-ów
  anulowanego v10.18 `229913–248184`. Job
  `c9524e66-552a-426b-ae54-b36ddd16bad5` zapisuje do
  `C:\Users\user\Documents\229913-248184 v10.19`; nie uruchamiać równoległego
  runu selekcji.

### Wersja 0.1

- TASK-0118 jest ukończony,
- lokalna paczka `0.1.5 (6)` zawiera jedną grę i 500 000 layoutów,
- APK ma SHA-256
  `d94061734d1e141ee9e68bf0e532eeb0ac1d485b68796f853c0dc3589326c522`,
- snapshot ma SHA-256
  `ddbfa90e673811efe2acad8e8049acc2435389bbbcaf256715573a744ef66de8`,
- APK `0.1.5 (6)` zainstalowano aktualizacyjnie na Google Pixel 10 Pro XL;
  Android potwierdził wersję, zachowany `firstInstallTime` i poprawny start,
- TASK-0119 został ukończony 2026-08-01: właściciel potwierdził podstawowe
  scenariusze offline, matching, duplikaty, Target, Undo/Reset, restart i
  płynność tabeli bez błędu blokującego,
- wersja 0.1 jest odebrana; ponowny test Mobile nastąpi po zmianach 0.3.

### Wersja 0.2

- rozwój może rozpocząć się przed zakończeniem TASK-0119,
- TASK-0120 zakończył kontrolowany reset lokalnego PostgreSQL,
- TASK-0121 zakończył przebudowę Admina na trzy workspace’y, jeden kontekst gry
  i accordion zależnych sekcji ze stanem w URL,
- TASK-0122 dodał trzy filtry katalogu gier, spójny wybór kontekstu oraz
  odwracalne przywrócenie zarchiwizowanej gry jako szkicu,
- TASK-0123 dodał źródło folderu, jednorazowy token, typowany image import oraz
  wznawialne kopiowanie JPEG-ów do content-addressed `data/originals` z
  niezmiennym manifestem; pierwotny dialog Windows został zastąpiony podczas
  odbioru przez przeglądarkowy wybór i kontrolowany upload,
- TASK-0124 dodał konfigurowalny cel liczby layoutów, raport kompletności i luk,
  walidację ręcznych numerów sekwencji oraz deterministyczny wybór najlepszego
  źródła z audytowalnym ręcznym override,
- TASK-0125 dodał checksum-bound bootstrap katalogu symboli z rzeczywistych
  cropów, automatyczne utworzenie przy zgodnej liczbie grup oraz jawne
  rozstrzygnięcie merge/split przy konflikcie,
- TASK-0126 dodał kafelki z rzeczywistą grafiką, modal z deterministycznymi
  stronami po 10 cropów oraz atomową zmianę nazwy i obrazu bez zmiany
  stabilnego `code` ani `mobileCode`,
- TASK-0127 uprościł reguły do jednego bieżącego workspace'u, zachowując
  wewnętrzną niezmienną historię oraz pełne, idempotentne kopiowanie
  opublikowanej konfiguracji do edytowalnego draftu,
- TASK-0128 dodał jawną akcję przeliczania layoutów, preflight kompletnego
  opublikowanego datasetu i reguł, widoczny `payout-v2`, postęp oraz wznowienie
  tego samego joba od checkpointu,
- TASK-0129 powiązał jedno wejście do osobnej aplikacji Reviewer z aktywną grą,
  najnowszym gotowym image importem i faktycznymi planszami oraz dodał jawne
  blokady i przejście z powrotem do importu,
- TASK-0130 usunął z widocznego workspace'u techniczny katalog Dataset i
  zabezpieczył brak powrotu dawnych wejść `datasets` oraz `manual-review` przez
  URL; encje, endpointy i audyt pozostały nienaruszone,
- TASK-0131 uprościł wydanie Android do jednej aktywnej gry, automatycznej
  najnowszej zgodnej pary dataset/reguły i pojedynczej akcji create → build;
  zwijana historia, bezpieczny draft po częściowej awarii, retry, checksumy i
  pobieranie APK pozostały dostępne,
- TASK-0132 uprościł osobny workspace `Joby` do jednego filtra statusu i
  zwartego podsumowania typu, kontekstu, postępu, czasu oraz błędu; techniczne
  metadane i dotychczasowe operacje pozostały dostępne po rozwinięciu joba,
- TASK-0133 dodał read-only preview i mocno potwierdzane usunięcie pojedynczego
  wydania oraz reset game-scoped danych layoutów bez usuwania gry; aktywne
  workflow i współdzielone wydania blokują operację, współdzielone artefakty i
  joby są zachowywane, a wykonanie ma idempotentne potwierdzenie,
- TASK-0134 dodał powtarzalną, ograniczoną czasowo bramkę końcową; cztery testy
  izolowanego PostgreSQL, 126 testów Admina, TypeScript, ESLint, OpenAPI i
  produkcyjny build przeszły, a przeglądarka przy 1366 × 768 potwierdziła trzy
  workspace'y, URL, puste stany, czystą konsolę i brak poziomego overflow,
- TASK-0142 jest aktywnym zadaniem stabilizacyjnym odbioru właściciela; pierwszy
  pion poprawił layout, style, pomoc i stany operacji sekcji `Import layoutów`;
  trzeci rozszerzył wybór gry na cały kafelek i dodał uzgadnianie skutecznego
  zapisu edycji; piąty uprościł wejście do sekcji symboli; szósty ostatecznie
  zastąpił zawodny dialog Windows standardowym selektorem przeglądarki,
  kontrolowanym uploadem JPEG-ów, postępem i sprzątanym stagingiem. Historyczne
  próby drugiego i czwartego pionu zostały supersedowane; siódmy uporządkował
  hierarchię kafelka gry i przeniósł czyszczenie na dół konfiguracji. Przechodzi
  138 testów Admina, 24 testy klienta i siedem skupionych testów API importu.
  Ósmy pion poprawił kontrakt checkpointu image importu i diagnostykę domenowych
  błędów workera. Dziewiąty podłączył pod tę samą akcję istniejący pełny
  pipeline obrazu i batchowy OCR strony; naprawczy job `777` jest wznawiany z
  checkpointu bez ponownego uploadu i tworzy cropy oraz pozycje review. Panel
  `Joby` mapuje techniczne dwie fazy na rzeczywiste `X / 739 zdjęć`. Dziesiąty
  pion usunął konflikt Windows `Path`/`PATH` przy generowaniu publicznego linku:
  API i skrypt używają wspólnej normalizacji, smoke test uruchamia proces z
  przekierowanymi logami, a nadal ograniczony cold-start ma do 60 sekund.
  Rzeczywisty start uzyskał HTTPS Quick Tunnel i został kontrolowanie
  zatrzymany; trwały profil użytkownika ma jeden `Path` oraz zweryfikowane
  zmienne Node/JDK/Android/Gradle. Jedenasty pion ograniczył edytor geometrii
  Reviewera do pojedynczego layoutu z marginesem, zachowując mapowanie narożników
  do współrzędnych oryginału oraz istniejący immutable recrop. Korekta poprawia
  bieżący layout, ale nie trenuje automatycznie globalnego profilu geometrii.
  Dwunasty pion rozdzielił koniec automatycznego image importu od terminalnego
  końca joba: `Wymaga review` pokazuje teraz datę, godzinę i czas zakończonego
  importu z pipeline'em, bez doliczania ręcznego zatwierdzania. Trzynasty pion
  usunął zależny od checkoutu Windows fałszywy drift klienta OpenAPI: LF/CRLF
  jest normalizowane przy porównaniu, ale zmiany semantyczne nadal blokują
  bramkę. Powtórna pełna bramka przeszła 2026-08-02: PostgreSQL 4/4, Admin
  140/140, klient API 26/26, typecheck, lint, OpenAPI i produkcyjny build.
- Czternasty pion TASK-0142 naprawił odbiór rzeczywistego szkicu `777 v0.2`:
  Reviewer i launcher dopuszczają `draft`/`active`, nadal wykluczając
  `archived`, a bootstrap symboli mapuje `None` do SQL `NULL`. Rzeczywisty
  bootstrap zakończył się `applied` i utworzył osiem symboli; produkcyjna sesja
  pokazała układ #8 oraz pełną kolejkę 4050 plansz.
- Piętnasty pion TASK-0142 naprawił edycję i odświeżanie ręcznej geometrii.
  Wskaźnik canvas jest mapowany przez rzeczywisty obszar `object-fit: contain`,
  więc narożniki działają dla różnych proporcji layoutu. Po zapisie UI przyjmuje
  item zwrócony przez backend, a URL-e source/board/cell są wersjonowane
  checksumą, dlatego nowa rewizja nie jest zasłaniana starym immutable cache.
  Korekta dostarcza lepsze cropy do uczenia symboli; uczenie samej geometrii
  nadal wymaga osobnego, wersjonowanego profilu i benchmarku.
- Szesnasty pion TASK-0142 dodał do edycji symbolu read-only podgląd zapisanej
  grafiki referencyjnej. Modal używa istniejącego checksum-bound assetu, pokazuje
  pełną ścieżkę i obsługuje loading, błąd, retry, `Escape` oraz jawne zamknięcie;
  nie zmienia grafiki ani metadanych. Admin przechodzi 162/162 testów, typecheck,
  lint i produkcyjny build; endpoint symboli przechodzi 10/10 testów.
- Admin i workflow powstają od czystej bazy,
- testy używają jednej gry i małego kontrolowanego datasetu,
- pełne 500 000 rzeczywistych layoutów i nowe gry nie należą do 0.2,
- zakres zadań 0.2 to TASK-0120–0134.

### Wersja 0.3

- właściciel dopuścił niezależne rozpoczęcie Mobile 0.3 na branchu
  `ft/change-mobile-app`; trwający odbiór Admina 0.2 nie blokuje tego toru,
- obejmuje dostosowanie aplikacji mobilnej: kompaktowy header, planszę i
  Selection, `Next`, wybierany zasięg Targetu, skonsolidowany wynik i powrót na
  górę,
- zakres jest rozpisany jako TASK-0135–0141,
- TASK-0135 został ukończony 2026-08-01: nagłówek pokazuje `ver {releaseVersion}`,
  wybór gry i rząd `Next`, `Undo`, `Reset`; usunięto tytuły i liczniki planszy,
  status gotowości danych oraz opis Selection. `Next` pozostaje nieaktywnym
  kontraktem UI do TASK-0138. Testy Mobile przeszły 67/67 wraz z typecheckiem i
  lintem,
- TASK-0136 został ukończony 2026-08-01: opcjonalne nazwy PL/EN przechodzą przez
  PostgreSQL, Admin API/OpenAPI, snapshot SQLite schema v3 i Mobile; Selection
  wybiera krótszą nazwę (remis: PL), używa fallbacku `name` i zawija pojedynczo
  opisane kafelki bez poziomego przewijania. Testy Mobile przeszły 68/68,
- TASK-0137 został ukończony 2026-08-01: kontrolowany input zaczyna od 10 000 i
  dopuszcza dowolną liczbę całkowitą 1 000–500 000; engine oraz pojedynczy
  cykliczny odczyt SQLite oceniają `min(limit, N - 1)` spinów. Zmiana limitu
  unieważnia stary wynik i ignoruje spóźnioną odpowiedź. Testy Mobile przeszły
  74/74, a shared engine 24/24,
- TASK-0138 został ukończony 2026-08-01: `Next` działa wyłącznie od
  jednoznacznego anchora, czyta dokładny kolejny rekord po `sequence_number`,
  zawija ostatni rekord do pierwszego i uruchamia Target dla bieżącego limitu.
  Anchor jest częścią atomowej historii `Undo`; jawnie załadowany duplikat nie
  traci znanej pozycji, a błąd lub spóźniona odpowiedź nie zmienia planszy.
  Pełna regresja Mobile przeszła 81/81 wraz z typecheckiem, lintem i formatem,
- TASK-0139 został ukończony 2026-08-01: osobne karty matchingu i Targetu
  zastąpiła jedna dostępna karta. Sukces pokazuje `Układ znaleziony i obliczony`
  oraz numer; rozwijane szczegóły zawierają tylko koszt spinu, koszt i sumę
  końcową. Duplikat jest ostrzeżeniem, brak layoutu i błędy mają czerwony stan z
  opisem, a retry Targetu pozostał dostępny. Usunięto powtarzane wartości i
  opisy bez zmiany algorytmu ani tabeli. Regresja Mobile przeszła 81/81 wraz z
  typecheckiem, lintem i formatem,
- TASK-0140 został ukończony 2026-08-01: pływający przycisk powrotu na górę
  pojawia się po osiągnięciu zmierzonej kotwicy wyników Targetu, przewija ten
  sam wirtualizowany `FlatList` do początku i nie zasłania końca tabeli dzięki
  powiększonemu footerowi. Przycisk pozostaje w safe area i ma dostępny obszar
  52 × 52. Regresja Mobile przeszła 82/82 wraz z typecheckiem i lintem,
- TASK-0141 jest aktywny: Mobile przechodzi 82/82, shared engine 24/24,
  typecheck, lint, format zmienionych plików i walidację snapshotu schema 3.
  Podpisane APK `0.3.0 (7)` ma 42 267 190 bajtów i SHA-256
  `80dfb99fa85c466689d69901f0aea57d3fdf03d425c46fd71bb0f883569e1332`.
  Statyczny audyt potwierdził `arm64-v8a`, bundle JS, zgodny snapshot i brak
  `INTERNET`; lokalne wydanie wraz z manifestem, checksumą i instrukcją jest
  zachowane w `artifacts/v03-ready-for-pixel/`. Instalacja i manualny odbiór
  czekają na podłączenie Pixela,
- odbiór kończy się testem offline na Google Pixel 10 Pro XL,
- nie obejmuje końcowych testów dużych rzeczywistych zbiorów.

### Wersja 0.4

- TASK-0151 ukończył fundament domenowy na branchu
  `codex/image-selection-domain-storage`: migracja `0025_image_selection`, job
  `image_selection`, trzy lekkie tabele bez BLOB, idempotentne create/get runu,
  stronicowana lista grup oraz wygenerowany klient OpenAPI,
- TASK-0152 dodał czwarty responsywny workspace `Selekcja zdjęć`, naturalnie
  uporządkowany i wznawialny browser staging do 100 000 JPEG-ów, postęp plików i
  bajtów, bounded concurrency równe 4, 24-godzinny checkpoint oraz token
  `photo_selection` izolowany per gra; selekcja nie uruchamia ciężkiego
  pipeline'u layoutów,
- TASK-0153 dodał wersjonowany `fast-image-selector-v1`: jawne porty miniatury,
  jakości, lattice/fingerprint i zakresu, strumieniowe grupowanie z bounded
  guardem, top-k równym 3, fail-closed quality gate, obsługę dowolnych skoków,
  późniejszych duplikatów i końcowych stron 1–9. Pełniejsza geometria oraz trzy
  kotwice OCR działają wyłącznie dla top-k. CLI zapisuje JSONL metryk, grupy i
  checkpoint poza read-only stagingiem; run bez modelu OCR ma odmienny
  fingerprint i pozostaje manualny. Golden syntetyczny oraz pięć prywatnych
  obserwacji rzeczywistych przeszły, podobnie jak 469 testów workera,
- TASK-0154 dodał atomowy content-addressed output z jednym JPEG-em na zakres,
  kanoniczny checksumowany manifest i ponowną weryfikację wszystkich plików.
  Handoff jest idempotentny przez `selectionId = runId`, blokuje nierozwiązane
  grupy i checksum drift, przenosi token do `Importu layoutów`, ale nie uruchamia
  ciężkiego pipeline'u. Job importu zachowuje `imageSelectionRunId`,
- TASK-0155 dodał kompaktowy, opcjonalny modal wyjątków manualnych z pojedynczym
  pickerem JPEG, podglądem, nawigacją strzałkami i idempotentnym zatwierdzeniem
  Enterem. Główna akcja może pominąć nierozpoznane zestawy bez zakresu i bez
  JPEG-a, nie wymyślając numeracji; korekty zachowują append-only audyt, a
  opublikowany output pozostaje niezmienny. Przy 1366×768 modal nie wymaga
  przewijania i zachowuje widoczny focus,
- TASK-0156 podłączył selektor do trwałego workera z lease/fencing,
  checkpointem bounded stanu, uzgadnianiem projekcji po awarii, retry od
  następnego potwierdzonego pliku, anulowaniem w safe poincie i zwalnianiem slotu
  w `waiting_for_review`. Pojedynczy uszkodzony JPEG jest izolowany, panel Joby
  pokazuje pliki X/N, grupy, wybory, manual, błędy i top-k, a czas uploadu jest
  oddzielony od czasu aktywnych obliczeń. Diagnostyka jest checksumowana,
  bounded i nie zawiera obrazów ani ścieżek absolutnych,
- techniczna część TASK-0157 przeszła 2026-08-03: profil 10k zakończył skan w
  252,51 s przy +76,2 MiB peak RSS, a profil 30k w 792,43 s przy +194,0 MiB.
  Oba mają zero fałszywych scaleń, pełne grouping/auto-selection precision,
  bounded `grupy × top-k` sparse verification, niezmienione źródła i pełny
  cleanup. Decyzja techniczna to `ready`; krótki odbiór właściciela pozostaje
  ostatnią otwartą częścią TASK-0157,
- stabilizacja odbioru TASK-0157 dodała automatyczne, ograniczone do 45 minut
  odświeżanie aktywnego runu w `Selekcji zdjęć`. Każdy request ma timeout 10 s,
  polling kończy się po stanie terminalnym lub zmianie gry, a powtarzające się
  błędy są widoczne bez blokowania panelu. Dzięki temu zakończenie workera i
  gotowy manifest nie wymagają ręcznego odświeżenia strony,
- ostatnia decyzja manualna TASK-0157 automatycznie wznawia ten sam job z
  checkpointu. Backend serializuje akceptacje blokadą `FOR UPDATE`, nie ponawia
  jobów `failed`, a Admin po zapisie odczytuje nowy stan i ponownie uruchamia
  bounded polling bez przechodzenia do workspace'u `Joby`,
- przepływ odbiorowy TASK-0157 ma główną akcję
  `Kontynuuj z wybranymi zdjęciami`: wszystkie nierozpoznane wyjątki zapisuje
  jako `missing_image`, również bez zakresu, a następnie publikuje pewne zdjęcia.
  Modal pokazuje `Zakres layoutów nierozpoznany`, deterministyczny numer zestawu,
  liczbę źródeł i nazwy zapisanych kandydatów; numer zestawu nie jest numerem
  layoutu. Zbiorcza akcja nie utrwala frontendowych sugestii zakresu, a modal
  sugeruje zakres tylko dla pojedynczej grupy w jednoznacznej luce.
  Zweryfikowany output można skopiować browser-native pickerem do wybranego
  folderu jako `seq_<od>-<do>.jpg` albo przekazać do `Importu layoutów`,
- eksport TASK-0157 obsługuje również wcześniejsze, niezmienne manifesty, w
  których managed JPEG miał padding i suffix checksumy. Publiczna nazwa nadal
  wynika wyłącznie z zakresu (`seq_1-9.jpg`). `api:dev` obserwuje tylko kod API i
  automatycznie go przeładowuje, aby działający Admin nie korzystał ze starego
  zestawu endpointów po zmianie źródeł,
- limit pojedynczego browser stagingu selekcji wynosi 100 000 JPEG-ów. Panel
  pokazuje loader `Przygotowywanie…` przed lokalnym filtrowaniem i sortowaniem;
  zaliczona bramka czasu i pamięci nadal obejmuje profile do 30 000, a pierwszy
  większy rzeczywisty run jest testem właściciela, nie automatycznym benchmarkiem,
- pierwszy rzeczywisty upload 32 079 JPEG-ów ujawnił koszt `O(n²)`: schema v1
  przepisywała cały `_upload_state.json` i odsyłała pełną listę indeksów po
  każdym pliku; przebieg trwał 2346,44 s. Następne uploady używają compact state
  schema v2, append-only `_upload_files.jsonl` oraz małej odpowiedzi PUT.
  Zgodność wsteczna migruje niedokończony stan v1 bez utraty postępu,
- obserwacja pracującego runu 32 079 zdjęć przy 13 408 plikach wykazała 1166
  grup, 3461 kosztownych weryfikacji, 1042 przypadki manualne, 99 wyborów
  automatycznych i 0 błędów. Pamięć pozostawała stabilna, ale średnio 11,5
  zdjęcia na grupę wobec typowych 50–100 ujawniło fragmentację przy zmianach
  perspektywy. `fast-image-selector-v3` dodał bounded ostatnią obserwację jako
  kotwicę ciągłości i nie traktuje pustej geometrii jako maksymalnej zmiany.
  `fast-image-selector-v4` dodatkowo traktuje progi jakości jako ranking,
  wybiera najlepszy dostępny dostatecznie ostry obraz i odzyskuje dokładnie
  jedną nierozpoznaną grupę z luki 1–9 między dwoma pewnymi zakresami. Nie
  zwiększa top-k ani liczby wywołań OCR. Nowe runy użyją fingerprintu v4, a
  rejestr manifestów zachowuje dokładne wznowienie runów v2/v3 również po
  restarcie. Run v2 zakończył się naturalnie przy
  14 144 przez `StatisticsError` w niepełnym przypisaniu siatki. Geometria
  odrzuca teraz takie przypisanie, a adapter izoluje błąd pojedynczego obrazu.
  Ten sam job wznowiono jako próbę nr 3 od checkpointu 14 144 i potwierdzono
  postęp do 14 336 bez powtórnego uploadu. Rzeczywista regresja v4 na tym samym
  stagingu zostanie uruchomiona dopiero po zakończeniu wznowionego joba v2, aby
  nie konkurować z nim o CPU i dysk,
- karta aktywnego runu TASK-0157 pokazuje bezpośrednio w `Selekcji zdjęć`
  czytelny status i etap, postęp `X/N` z procentem, liczbę grup, wyborów
  automatycznych, przypadków manualnych, pominięć, błędów i weryfikacji oraz
  oddzielne czasy uploadu i obliczeń. Identyfikatory techniczne pozostają
  dostępne w zwijanych szczegółach,
- odbiór rzeczywistego katalogu 180 zdjęć wykrył manual rate `32/32` w
  `fast-image-selector-v1`. Wersja `fast-image-selector-v2` usuwa zależność
  fingerprintu od zmiennej liczby czerwonych ramek, potwierdza pełny zakres z
  przestrzennej siatki jasnych numerów i nie tworzy singletonów z
  niepotwierdzonej klatki przejściowej. Lokalna regresja tych samych danych
  zakończyła się w 44,2 s wynikiem 7 auto-selected zakresów, 4 powtórzeń i 0
  przypadków manualnych; pozostaje powtórzyć run z poziomu Admina,
- wznowiony rzeczywisty run v2 zakończył 32 079 źródeł wynikiem 2795 grup. Po
  częściowej zbiorczej kontynuacji pozostało 2288 nierozpoznanych zestawów;
  licznik 25 opisuje grupy-duplikaty, a nie zdjęcia lub layouty. Konflikt
  powtarzanej sugestii zakresu został usunięty bez zmiany istniejących decyzji,
- inspekcja trwałego runu potwierdziła, że grupa dla layoutów `73–81` ma czytelne
  kandydaty, ale v2 odrzuca je przez miękkie ostrzeżenia jakości i brak OCR.
  Regresje v4 potwierdzają wybór najlepszego obrazu oraz odzyskanie `73–81`
  pomiędzy `64–72` i `82–90`; jawnie zasłonięty lub uszkodzony obraz nadal nie
  jest wybierany automatycznie,
- rzeczywisty rerun v4 zakończył 32 079 źródeł, ale nie przeszedł bramki
  jakości: tylko 40 z 743 grup zostało wybranych automatycznie, 703 wymagały
  review, 700 miało niepełną geometrię, a 692 nie znalazły siatki widocznych
  etykiet. Wszystkie 703 decyzje `missing_image` pozostają historycznym wynikiem
  v4 i nie są modyfikowane,
- ukończony TASK-0160 dodał `fast-image-selector-v5` z digit-aware fallbackiem obejmującym
  dolny rząd numerów, guarded grid recovery w pełnym verifierze oraz grupowaniem
  opartym na kolejnych obserwacjach zamiast historycznego veto `topK`.
  Fingerprinty i zachowanie v2–v4 pozostają niezmienne. Ograniczona regresja
  rozpoznała 24/29 realnych próbek odrzuconych przez v4, a pierwsze 160 zdjęć
  rozdzieliła na sześć kolejnych pełnych zakresów `1–9` do `46–54`; ostatni
  niepełny obraz pozostał manualny. Pełny rerun v5 nie został uruchomiony
  automatycznie,
- TASK-0161 dodał bezpieczny rerun z istniejącego stagingu. Karta runu ma akcję
  `Przelicz ponownie załadowane zdjęcia`; backend bierze źródło i checksum z
  historycznego runu, weryfikuje manifest oraz tworzy albo przywraca idempotentny
  run aktualnego selektora. Staging 32 079 zdjęć nadal istnieje, zajmuje około
  7,55 GB i ma checksum zgodny z runem v4, dlatego uploadu nie należy powtarzać,
- TASK-0162 utrwalił realny przypadek `73–81`: grupa pomiędzy `64–72` i `82–90`
  może przekazać do cięcia najlepsze dostępne zdjęcie mimo przyciętej ramy,
  słabej ekspozycji, niepełnej geometrii oraz braku bezpośredniego OCR. Twarde
  błędy pliku/skanu i jawne zasłonięcie pozostają blokujące. W trakcie skanowania
  Admin nazywa licznik `Wstępnie nierozpoznane`, ponieważ końcowe bounded-gap
  recovery może go zmniejszyć. Trwający run v5 nie został zatrzymany ani
  przeładowany; zachowanie finalne i fingerprint nie zmieniły się,
- po ukończeniu TASK-0162 właściciel jawnie poprosił o przerwanie pierwszego
  pełnego rerunu v5, aby rozpocząć selekcję ponownie z aktualnym UI i
  zabezpieczonym kontraktem. Job `309e5d00-f2dd-4207-a531-a180ffd299b3`
  bezpiecznie przyjął cancel przy `1984/32079` i zakończył się jako `cancelled`
  na checkpointcie `2016/32079`. Staging oraz historyczne runy pozostały bez
  zmian; następny run nie wymaga uploadu,
- TASK-0163 domknął ścieżkę po tym anulowaniu: ponowne przeliczenie istniejącego
  stagingu wznawia run `cancelled` lub `failed` od zachowanego checkpointu,
  zamiast tylko przywrócić jego terminalną kartę. Stan błędu i anulowania jest
  czyszczony, staging i postęp pozostają niezmienne, a Admin komunikuje jawnie
  wznowienie pracy,
- TASK-0164 dodał `fast-image-selector-v6`. Realny snapshot v5 przy 519 grupach
  miał 54 grupy bez numerów; 50 z nich należało do jednoznacznych bloków między
  kotwicami, które można dokładnie podzielić na pełne strony po 9. V6 odzyskuje
  takie bloki all-or-nothing i zapisuje poprawione projekcje od razu po prawej
  kotwicy. Skoki oraz niepasujące luki pozostają jawne. V5 zachowuje fingerprint
  `ff7521…`, a domyślny v6 ma fingerprint `22b0d1…`,
- odbiór właścicielski dodał `fast-image-selector-v7` o fingerprintcie
  `21d634…`. Produkcyjny test dokładnie na wskazanym JPEG-u potwierdził zakres
  `73–81` z confidence `0.962379` i wynik `auto_selected`. V7 rozszerza maskę
  ciemniejszych/ciepłych etykiet i traktuje zasłonięcie, blur oraz słabe plansze
  jako ranking, nie blokadę, gdy zakres jest jednoznaczny. Ręczny upload JPEG-a
  został odblokowany trwale przez dodanie `X-Image-File-Name` do CORS i test
  rzeczywistego preflightu `PUT`,
- po obserwacji zbyt wolnej pełnej weryfikacji dodano `fast-image-selector-v8`
  o fingerprintcie `9dc754…`. Nowe runy zachowują pierwsze dostatecznie czytelne
  zdjęcie grupy i kończą kosztowny OCR po pierwszym jednoznacznym zakresie.
  Następny kandydat jest sprawdzany tylko po braku zakresu albo twardym błędzie;
  typowy koszt spada z trzech do jednej pełnej weryfikacji na grupę. V7 pozostaje
  rozwiązywalny po niezmienionym fingerprintcie `21d634…`,
- właściciel zaakceptował zmianę odpowiedzialności następnej wersji selektora:
  v9 ma wyłącznie szybko grupować kolejne wizualnie różne ekrany i wybierać
  pierwszy dostatecznie czytelny JPEG albo best-available fallback. OCR numerów,
  `PageBoardDetector`, homografia, cropy, symbole, właściwe `sequence_number` i
  deduplikacja zakresów przechodzą do `Importu layoutów`. Upload schema v2 oraz
  jego zmierzony czas około 20 minut dla 32 079 zdjęć pozostają poza zakresem
  zmiany. TASK-0165 dostarczył instrumentację i read-only runner bez przerywania
  historycznego joba; plan iteracyjny obejmuje TASK-0166–0171,
- TASK-0166 dodał wersjonowany `pillow-jpeg-draft-thumbnail-v2`: JPEG jest
  redukowany przez dekoder przed pełnym odczytem pikseli, przy zachowaniu EXIF,
  wymiarów źródła i roboczego boku 960 px. Warianty 384/480 zostały odrzucone
  przez realny golden granic. OpenCV używa jednego wątku wewnętrznego, historyczny
  fingerprint v8 `9dc754…` zachowuje stary adapter, a nowy fingerprint wynosi
  `284eb7…`. Upload i staging schema v2 nie zostały zmienione. Pomiar scan workers
  1/2/4 oraz końcowa aktywacja pozostają w TASK-0171 zgodnie z decyzją właściciela,
- TASK-0167 dodał nieaktywny jeszcze `fast-image-selector-v9`; jego pierwszy
  przedaktywacyjny fingerprint wynosił `711ce8…`. Skan używa 97-elementowego
  pHash/HSV/edge descriptor, bez
  `PageBoardDetector` i bez konstrukcji OCR. Granica porównuje bezpośredniego
  poprzednika z rolling centroidem i wymaga dwóch zgodnych klatek; odrzucone
  przejście nie przesuwa centroidu przed oceną powrotu. Checkpoint przechowuje
  stały centroid, licznik, bounded top-k i pending guard. Golden realnych stron
  1–9, 10–18 i 19–27 ma zero false merge, a mała zmiana perspektywy nie dzieli
  strony. Domyślny manifest pozostaje v8 do aktywacji w TASK-0171,
- TASK-0168 dodał range-free wybór reprezentanta bez pełnej weryfikacji. V9
  zachowuje pierwsze źródło spełniające wersjonowane progi ostrości, ekspozycji,
  clippingu i widoczności oraz najwyżej jeden najlepszy fallback. Każda grupa z
  dekodowalnym JPEG-em kończy jako `auto_selected`; słaby fallback dostaje
  `QUALITY_BEST_AVAILABLE`, a pojedynczy błąd skanu nie kończy runu. Checkpoint
  przechowuje najwyżej dwa rekordy kandydata, verifier/OCR nadal ma zero wywołań,
  a fingerprint tej przedaktywacyjnej rewizji v9 wynosił `65c19a…`. Domyślny
  manifest pozostał v8 do TASK-0171,
- TASK-0169 dodał kanoniczny output manifest v2 i przekazanie bez wymaganego
  zakresu. Wybrany JPEG bez numerów ma stabilną nazwę
  `selection_<groupOrder>.jpg`; manifest zachowuje oryginalną ścieżkę, checksumy,
  metryki, ostrzeżenia i sposób wyboru. Handoff uzgadnia trwałe decyzje po
  `groupOrder`, a istniejący `image_directory` ustala numery dopiero w OCR i
  geometrii Importu layoutów. Odczyt manifestu v1 i publiczne nazwy `seq_*`
  pozostają zgodne. Schemat PostgreSQL już dopuszczał zakres nullable, więc nie
  była potrzebna migracja Alembic. OpenAPI, klient i panel rozróżniają teraz
  wybrane grupy od rozpoznanych layoutów,
- TASK-0170 dodał odtwarzalny cache bounded obserwacji lekkiego skanu pod
  `data/cache/image-selection-scan/`. Klucz stanowią checksum JPEG-a i osobny
  fingerprint adaptera skanu, więc zgodny retry nie dekoduje ponownie pliku, a
  zmiana dekodera, deskryptora, jakości lub checksumy daje miss. Wpisy są
  kanonicznymi JSON-ami zapisywanymi atomowo, nie zawierają obrazów ani ścieżek;
  częściowy wpis jest ignorowany i odbudowywany. Checkpoint nadal jest źródłem
  prawdy, publikator ponownie sprawdza pełną checksumę wybranego JPEG-a, a
  checkpoint i diagnostyka pokazują cache hit/miss oraz szacowany zaoszczędzony
  czas. Cache można bezpiecznie wyczyścić tylko jako osobny katalog przy
  zatrzymanym workerze; nie dotyka to stagingu ani outputu,
- TASK-0171 jest w toku na świeżej bazie. Historyczny job został anulowany,
  lokalny PostgreSQL wyzerowano również z gier i zmigrowano do head; staging
  32 079 JPEG-ów oraz APK zachowano. Niezależny golden pierwszych 500 zdjęć
  obejmuje 20 ekranów. Realny profil v9 po korekcie binarnego pHash na ciągłą,
  znormalizowaną sygnaturę DCT przeszedł 500 zdjęć w 16,725 s (29,8947/s,
  20/20 grup, recall 100%, zero false merge/split) oraz 3000 zdjęć w 131,558 s
  (22,8036/s, 217 reprezentantów; golden pierwszych 500 nadal bez regresji).
  Peak RSS delta wyniósł odpowiednio około 78,2 i 94,4 MiB, warm-cache rerun
  był identyczny, a liczniki OCR/geometrii/homografii/cropów/symbol inference
  wynoszą zero. Bieżący przedaktywacyjny fingerprint v9 to `eaca91…`, a
  fingerprint adaptera skanu `408bd8…`. Domyślny manifest pozostaje v8, ponieważ
  staging ma 32 079 zdjęć, a D-146 wymaga dokładnie 40 000 naturalnych zdjęć i
  jawnej decyzji właściciela,
- TASK-0172 rozdzielił wykonanie lokalne na dwa trwałe lane bez nowego URL,
  mikroserwisu ani brokera. General worker (`execution_slot = 1`) obsługuje
  Import layoutów i pozostałe joby, a image-selection worker
  (`execution_slot = 2`) wyłącznie Selekcję zdjęć. Atomowy claim filtruje typy
  przed lease, więc oba procesy mogą działać równolegle, ale w każdym lane nadal
  działa najwyżej jeden job. Migracja `0031_job_execution_lanes` jest lokalnym
  head; test izolowanego PostgreSQL potwierdził dwa równoległe claimy i blokadę
  drugiej selekcji. Operator uruchamia `npm run worker:poll` oraz osobno
  `npm run worker:image-selection:poll`,
- TASK-0173 zakończył lokalny supervisor, który uruchamia oba worker lanes w
  ukrytym tle, zapisuje PID, nazwę i dokładny czas startu oraz osobne logi w
  `.runtime`. `workers:start` jest idempotentny, `workers:status` rozpoznaje
  stary proces, a `workers:stop` nie zatrzymuje PID bez zgodnej tożsamości.
  Kontrolowany test obu lane, pojedynczego lane i odzyskania stale state
  przeszedł bez osieroconych procesów,
- TASK-0174 zakończył niedestrukcyjną bramkę operacyjną obu lane. Izolowany
  PostgreSQL potwierdził równoległy claim, blokadę drugiego workera w każdym
  lane i przejęcie pozostałych jobów po zwolnieniu slotów. Jedna bounded komenda
  zapisała raport `passed`; nie uruchamiała workerów ani nie korzystała z danych
  właściciela,
- TASK-0175 zakończył fizyczną regresję recovery i fencing dwóch lane. General
  oraz selection lease wygasają i są wznawiane niezależnie z zachowanym
  checkpointem, stare tokeny są odrzucane, a anulowanie general w safe poincie
  nie narusza aktywnej selekcji. Rozszerzona bramka zakończyła się `passed`,
- TASK-0176 zakończył brakujący pion operacyjny: trwały, tokenowany heartbeat
  bezczynnych i zajętych procesów, niezależny status obu lane w Adminie oraz
  jawne budżety wątków `general=2` i `image_selection=4` z wyłączoną
  nadsubskrypcją bibliotek natywnych. Bounded smoke potwierdził przejście obu
  lane `running -> stopped` bez osieroconych procesów. Historyczne
  TASK-0174/0175 zachowują faktyczny wykonany zakres; nie są przepisywane,
- TASK-0177 zakończył rzeczywistą bramkę równoległych procesów na izolowanej
  bazie i kontrolowanych fixture. Oba joby były jednocześnie `processing`,
  cancel/retry general nie zatrzymał selekcji, oba workflow zakończyły się
  poprawnie, a oba lane przeszły do `stopped` bez osieroconego procesu. Próba
  `100 obrazów + 10 000 rekordów` trwała `12,219 s`; raport zawiera osobne
  metryki CPU, RAM i I/O obu drzew procesów oraz decyzję `passed`,
- właściciel potwierdził dostępność dokładnie 40 000 naturalnych zdjęć i polecił
  aktywować v9 przed pełnym runem. Nowe runy używają teraz
  `fast-image-selector-v9` o fingerprintcie `eaca91…4afb`; historyczne v2–v8
  pozostają wznawialne. Regresja aktywacji przeszła `88 passed`. TASK-0171
  pozostaje otwarty do wykonania pomiaru i decyzji `accepted | optimize`,
- TASK-0159 dodał wykonawczy, niewpływający na selector fingerprint bounded
  ordered prefetch taniego skanu. `worker-v7` używał czterech
  wątków i najwyżej ośmiu futures; grupowanie, OCR, checkpoint i output nadal są
  sekwencyjne. Pomiar bieżącego worker-v6 przed zmianą wyniósł około 5,1
  zdjęcia/s przy wykorzystaniu jednego rdzenia i stabilnych 430–450 MiB RAM.
  Działający run nie został przerwany ani hot-reloadowany; realny pomiar v7
  nastąpi w kolejnym runie. `worker-v8` zachowuje ten mechanizm i dodaje selektor
  v5; przed nowym runem API i worker muszą zostać uruchomione ponownie, aby oba
  procesy używały nowego fingerprintu,
- TASK-0158 usunął nieliniowy koszt pełnego pipeline'u `Import layoutów`:
  `ImageBatchHandler` wykonuje pełne `batch_stats` tylko na wejściu i końcu
  przebiegu, a pomiędzy nimi wyprowadza liczniki z trwałych przejść pliku.
  Świeży `waiting_for_review` przechodzi pierwszą kontrolę bez ponownej
  rehydratacji plansz i 15 cropów każdej planszy; istniejący stan po restarcie
  nadal jest rehydratowany. Modele, wyniki adapterów, fingerprint, file
  checkpoint, fencing, retry i anulowanie pozostają bez zmian. Kolejny pion
  wydajnościowy może zbatchować zapis plansz i komórek po pomiarze tej zmiany,
- kontroler publicznego Reviewera wykonuje bounded test wychodzącego HTTPS przed
  startem `cloudflared`. Proces API z zablokowanym dostępem do
  `api.trycloudflare.com:443` zwraca teraz właściwą przyczynę zamiast ogólnego
  timeoutu 30 sekund. Rzeczywisty start spoza izolacji sieciowej utworzył
  poprawny URL Quick Tunnel 2026-08-03,
- obejmuje wyłącznie M7.0 i TASK-0151–0157, czyli niedestrukcyjny preselektor:
  czwarty workspace
  `Selekcja zdjęć` redukuje katalog 10 000–30 000 kolejnych ujęć do jednego
  checksumowanego JPEG-a na dowolny rozpoznany zakres, a niepewne grupy kieruje
  do małego manualnego modala,
- TASK-0151–0157 obejmują model domenowy, skalowalny folder staging, szybki
  selector, output i handoff, manual fallback, operacje oraz bramkę 10k/30k,
- folder użytkownika pozostaje read-only; pełny pipeline dostaje jawnie
  przekazany manifest wybranych kopii i nie jest uruchamiany przez sam selector,
- testy 10k/30k mierzą sam selektor na surowych zdjęciach; nie są pełnym
  importem layoutów i nie odblokowują `massImportAllowed`.

### Wersja 0.5

- rozpoczyna pracę na większych rzeczywistych datasetach po zaakceptowaniu
  selektora 0.4,
- M6.6 został zaakceptowany jako obowiązkowy tor iteracyjnego ulepszania modelu
  symboli przed pełnym automatycznym importem,
- na jawne polecenie właściciela TASK-0143 został wykonany przed odroczonym
  manualnym odbiorem selektora 0.4; nie otwiera to bramki release ani masowego
  importu 0.5,
- TASK-0143 dodał skumulowaną, game-scoped kohortę treningową: preview,
  idempotentne freeze, content-addressed manifest, pozycje wiążące review,
  źródło, geometrię, pipeline i 15 cropów oraz twardą politykę automatycznych
  zapisów wyłącznie do aktualnego `pending`,
- TASK-0144 dodał game-scoped sekcję `Jakość rozpoznawania` w Adminie oraz
  endpoint `model-quality`. Panel pokazuje brak albo aktywną wersję modelu,
  pełne i nowe plansze liczone po checksumach względem ostatniej kohorty,
  źródła, pokrycie każdego aktywnego symbolu, progi doradcze 100/1000,
  ostrzeżenia oraz wszystkie chronione decyzje człowieka. `Ulepsz
rozpoznawanie` wymaga jawnego potwierdzenia dokładnej checksumy preview;
  zmiana manifestu albo aktywny ciężki job tej gry blokują freeze. Operacja
  tworzy wyłącznie niezmienną kohortę i nie uruchamia jeszcze treningu,
- TASK-0145 dodał deterministyczny builder
  `verified-symbol-training-dataset-v1`. Builder weryfikuje checksumę kohorty,
  komplet 15 etykiet planszy, aktywny katalog symboli oraz każdy plik cropu;
  rodziny tego samego źródła trafiają przez stabilny hash wyłącznie do
  train/validation/test/regression. Artefakty i manifest są content-addressed
  pod `data/training`, powtórny build jest idempotentny, a raport pokazuje
  splity, źródła, klasy, wykluczenia i niedoreprezentowanie. Zadanie nie
  uruchamia jeszcze treningu ani nie zmienia decyzji review,
- TASK-0146 dodał migrację `0035_symbol_model_training_jobs`, trwały typ joba
  `symbol_training` i game-scoped iterację modelu. Request HTTP jedynie tworzy
  idempotentny job; ogólny worker buduje przypięty dataset i trenuje wybrany
  `spatial-symbol-cnn-v1` od zera. Każda epoka zapisuje content-addressed
  checkpoint modelu, optimizera, najlepszego stanu, historii i fingerprintu,
  a heartbeat działa także wewnątrz długiej epoki i kopiowania datasetu.
  Anulowanie zachowuje ostatni checkpoint, retry odrzuca dryf wejścia, a status
  `trained` nie aktywuje modelu. Admin uruchamia trening po freeze i pokazuje
  postęp oraz stabilne błędy w `Joby`,
- TASK-0143–0150 obejmują skumulowane kohorty per gra, panel jakości,
  source-aware dataset, trwały trening, bramkę ONNX, kontrolowaną aktywację,
  przeliczenie wyłącznie `pending` oraz odbiór dwóch iteracji,
- `accepted`, `corrected` i `rejected` są nienaruszalnymi decyzjami człowieka;
  żadna automatyczna operacja modelu nie może ich przeliczyć ani zmienić,
- TASK-0076 realizuje pełny import około 500 000 rzeczywistych layoutów na grę,
- nowe gry, wielogrowy snapshot/APK, benchmarki pełnego pipeline'u i
  TASK-0080–0089 domykają skalę oraz hardening 0.5.
- zaakceptowano iteracyjny import ukończonego manifestu Selekcji Zdjęć:
  automatyczne następne N, trwały monotoniczny kursor i brak ponownego
  przetwarzania wcześniejszych partii,
- nowe modele symboli i profile siatki mają działać wyłącznie dla importów
  utworzonych po jawnej aktywacji; TASK-0149 został odroczony poza ten przepływ,
- TASK-0198–0207 są ukończone: checksum-bound źródło i atomowe partie
  następnych N zdjęć, wykonanie dokładnego wycinka przez worker, trwały postęp
  w Adminie, natywny kontekst z numerem w Reviewerze oraz wersjonowana
  kalibracja siatki z osobną aktywacją i rollbackiem,
- profil siatki jest przypinany do nowego joba wraz z payloadem, checksumą i
  fingerprintem; działa tylko dla dokładnego `imageSelectionRunId +
positionIndex`, a brak dopasowania bezpiecznie pozostawia wynik detektora,
- TASK-0208 ma gotową obserwowalność i bounded skrypt pomiarowy; rzeczywiste
  pomiary 10/100/1000 oraz warunkowe 5000 pozostają odbiorem właściciela,
- Selekcja Zdjęć pozostaje oddzielnym, niezmienianym modułem v0.4.

## Dane i artefakty

### Chronione

- `artifacts/v01-representative-release/` — kompletna paczka odbiorowa 0.1,
- `artifacts/v01-ready-for-pixel/Game-Predictor-0.1.5-v6-Pixel.apk` — prosta
  kopia APK gotowa do instalacji na Pixelu,
- `artifacts/v02-clean-baseline/pre-reset/` — pełny dump i inwentarz danych
  istniejących bezpośrednio przed resetem 0.2,
- `.tooling/android-signing/` — prywatny klucz i konfiguracja podpisu,
- zdjęcia źródłowe i ręczne materiały wejściowe poza PostgreSQL,
- dokumentacja decyzji, migracje, kod i raporty jakości.

### Robocze

- Repozytorium ma head `0039_grid_calibration_profiles`; lokalny PostgreSQL pozostaje
  tymczasowo na `0035_symbol_model_training_jobs`, ponieważ trwa rzeczywisty run
  selekcji 32 079 zdjęć. Migracje `0036–0037` zostaną zastosowane przy
  kontrolowanym zatrzymaniu usług przed użyciem rejestru modelu. Migracja `0030` pozwala zapisać
  nierozpoznany `missing_image` bez zakresu. Migracja
  `0029_image_selection_missing_images` dodaje terminalny stan `missing_image`,
  opcjonalny `candidate_id` powiązany z jawnym typem decyzji oraz pozwala
  kontynuować selekcję bez ręcznego JPEG-a. Poprzednia migracja
  `0028_image_selection_versioned_reruns` usuwa błędną unikalność
  samego `source_selection_id`, dzięki czemu ten sam niezmienny staging może
  otrzymać nowy run po zmianie fingerprintu selektora. Poprzednik
  `0027_image_selection_manual_decisions`; wcześniejszy
  `0026_merge_v03_v04_heads` łączy niezależne migracje
  `0025_symbol_localized_names` i `0025_image_selection` bez przepisywania
  historii baz, które mogły zastosować już jeden z tych pionów. Migracja 0027
  dodaje append-only audyt ręcznych decyzji selektora,
- ręczne wyjątki selekcji nie wymagają już pliku: użytkownik może podać sam
  zakres, np. `1–9`, a Admin zapisuje i pokazuje `Brak zdjęcia dla layoutów
1–9`; opcjonalny JPEG nadal można dodać przed zatwierdzeniem,
- 4 sierpnia 2026 lokalny PostgreSQL został wyczyszczony przed rozpoczęciem
  rzeczywistego, etapowego zasilania docelowego zbioru 500 000 layoutów;
  wszystkie 38 tabel domenowych ma zero rekordów, a schemat jest na migracji
  `0030_image_selection_optional_exceptions`,
- stan bezpośrednio przed resetem jest odzyskiwalny z
  `artifacts/pre-full-import-reset-20260804/game_predictor.dump`; starszy
  chroniony baseline 0.2 pozostaje w `artifacts/v02-clean-baseline/pre-reset/`,
- pierwsza rzeczywista partia obejmuje około 32 000 zdjęć reprezentujących
  około 5 000 layoutów; właściciel ma łącznie 28 katalogów do etapowego
  przeprocesowania. Zdjęcia źródłowe pozostają poza resetowaną bazą,
- 4 sierpnia 2026, na jawne polecenie właściciela, usunięto z PostgreSQL
  wszystkie 4 joby selekcji oraz ich robocze runy, grupy, kandydatów i decyzje
  manualne. Nie usunięto gry ani stagingu źródłowego: katalog selekcji
  `a34c92da-87fd-4245-a0c9-29ee0f6c39c9` nadal zawiera manifest i 32 079
  zdjęć wejściowych. Obie lokalne kopie workera zatrzymano przed transakcją,
- `apps/mobile/assets/snapshot/m1-snapshot.db` jest małym fixture’em
  deweloperskim; pozostaje do świadomego zastąpienia fixture’em 0.2.

## Ukończony fundament

- aplikacja mobilna działa całkowicie offline i używa SQLite w APK,
- matching rozróżnia unique, duplicate i not found,
- payout-v2 ocenia prefiks od pierwszej kolumny i precomputed payout,
- Target przechodzi pełny cykl i pokazuje dodatnie lokalne maksima,
- lokalny Admin, FastAPI, PostgreSQL i wersjonowanie domenowe działają,
- import ręczny, snapshot/release pipeline i kontrolowane joby działają,
- pipeline zdjęć, geometria, OCR adapter, klasyfikacja i manual review mają
  działające piony oraz raporty jakości,
- osobny Reviewer działa lokalnie i przez ograniczony link z kodem,
- lokalny Admin API jest chroniony przez loopback/origin/intencję i audyt.

Szczegółowe wyniki historyczne znajdują się w `tasks/completed/`,
`process/DECISION_LOG.md` i raportach `quality/`; nie są powtarzane tutaj.

## Otwarte pytania

- Q-020 — dozwolony zakres analizy aplikacji referencyjnej,
- Q-022–Q-032 zostały rozstrzygnięte; Admin 0.2 nie ma otwartego pytania
  blokującego rozpoczęcie TASK-0122,
- finalny model OCR nie blokuje najbliższego pionu mobilnego; nazwa i sposób
  prezentacji wyniku zostały rozstrzygnięte dla 0.3.

Q-020 pozostaje niezależne od Admina 0.2 i nie blokuje TASK-0134.

## Blocked / deferred

- TASK-0076 i publikacja masowego datasetu nadal wymagają jawnego otwarcia
  bramki `massImportAllowed`; rozpoczęte jest przygotowanie rzeczywistych danych
  wejściowych 0.5, a nie automatyczna publikacja 500 000 layoutów,
- TASK-0080–0089 należą do pełnego hardeningu 0.5,
- TASK-0148 jest ukończony; TASK-0149 został odroczony decyzją o stosowaniu
  ulepszeń tylko do nowych partii, a TASK-0150 pozostaje końcowym odbiorem
  iteracyjnego przepływu. TASK-0143–0148 wykonano wcześniej na jawne polecenie
  właściciela, bez otwierania pozostałych bramek,
- TASK-0151–0156 są ukończone. Syntetyczna część TASK-0157 jest zaliczona, ale
  rzeczywiste runy ujawniły fragmentację i koszt pełnego dekodowania, geometrii
  oraz OCR. Decyzja ma status `optimize`. TASK-0165–0171 implementują i mierzą
  range-free `fast-image-selector-v9`; dopiero po ich zakończeniu manualny
  odbiór właściciela pozostanie końcową bramką M7.0. Nie zastępuje odbioru 0.2
  ani 0.3,
- masowy import, nowe gry i pełne benchmarki danych nie mogą wejść do bramki 0.2.

## Kandydat ONNX i bramka regresji (TASK-0147)

TASK-0147 jest ukończony. Migracja `0036_symbol_model_candidate_gate` utrwala
statusy `evaluating`, `candidate_ready` i `rejected`, konfigurację bramki,
checksumy manifestu i raportu, metryki oraz powody odrzucenia. Trwały job
`symbol_training` po checkpointcie `trained` wykonuje eksport ONNX, parity,
kalibrację, ocenę na test/regression oraz manifest. Artefakty są
content-addressed i nie zmieniają aktywnego modelu. Admin pokazuje wynik
ostatniej bramki, a typed client pobiera historię i szczegóły iteracji.

## Next recommended task

Utworzyć pierwsze zadanie wersji 0.6 dotyczące wspólnego przeglądu i ulepszenia
workspace’ów `Gry` oraz `Import layoutów`. Przed kodowaniem należy zapisać
rzeczywisty przebieg właściciela, problemy, docelowe zachowanie i kryteria
odbioru. Odroczone TASK-0208 i TASK-0150 nie są automatycznym pierwszym zakresem
0.6 i wymagają osobnej decyzji priorytetowej.

TASK-0194 wykonał powtórny profil pierwszych 200 zdjęć. Wariant dwóch
verifierów trwał 366,322600 s, a jednego 310,859984 s wobec baseline
377,530649 s; cel 113–151 s nie został osiągnięty. Dziewięć granic grup
pozostało identycznych, ale grupa 159–180 bez dowodu OCR trafiła do
`manual_required` zamiast odziedziczyć zgadywany zakres 55–63. Produkcja wróciła
do jednego verifiera. Właściciel wybrał `optimize` 2026-08-08; TASK-0194 jest
zamknięty, a run 5000/32 000 nie został uruchomiony.

TASK-0195 jest ukończony. Adapter v6 odzyskuje zakres 55–63 z co najmniej
siedmiu lokalnych inlierów siatki 3×3, widocznej etykiety brzegowej i pełnego
pokrycia wierszy/kolumn, bez cursora ciągłości. Cold profile indeksów 159–180
wybrał `1/1_010522.jpg`, zwrócił `auto_selected` 55–63 i trwał 25,701488 s.
Historyczny manifest v5 pozostaje rozwiązywalny; pełny run nie został
uruchomiony.

TASK-0196 jest ukończony. Dokładna suma integralna zastąpiła 163 tys. skanów
border/interior bez zmiany kanonicznego wyniku detektora. Profil 0–199 trwał
91,714346 s zamiast 310,859984 s TASK-0194, zachował dziewięć granic, wszystkie
zakresy 1–9…73–81, dotychczasowe reprezentanty oraz zero błędów skanu.
Fingerprint nie zmienił się; skalowanie i crop odrzucono jako regresyjne.

TASK-0194 powtórzono po TASK-0195 i TASK-0196. Cold profile indeksów 0–199 trwał
109,111404 s, zachował dokładnie dziewięć granic, zakresy `1–9` do `73–81`,
wszystkie checksumy reprezentantów oraz zero błędów skanu. Jest o 71,10% szybszy
od baseline v10 i mieści się w pierwotnym celu czasu; raport to
`artifacts/image-selection-v101-first-200-task0194-repeat.json`.

TASK-0197 zakończył się decyzją właściciela `rejected`. Poprzedni
profil 0–4999 zatrzymano na polecenie właściciela przy około 660
źródłach, aby powtórka TASK-0194 nie konkurowała o zasoby. Nie powstał raport
końcowy, a staging 32 079 zdjęć jest niezmieniony. Po zaliczeniu powtórki
TASK-0194 właściciel 2026-08-09 zastąpił ponowny etap 5000 bezpośrednim profilem
całego stagingu 0–32078. Pierwszą próbę zatrzymano przy 180 źródłach, ponieważ
jej bieżące tempo wskazywało około dziewięciu godzin, a limit 21 600 s
odrzuciłby ukończony raport. Finalny profil używa limitu bezpieczeństwa 43 200 s,
trzech scan workers i jednego verifiera. Wystartował jako PID `3472`; kontrola
startowa potwierdziła postęp co najmniej 40/32 079 i brak tracebacku. Proces
jest read-only, bez publikacji i Importu layoutów; wynik czasu i jakości podlega
ręcznej ocenie właściciela.

TASK-0198–0207 zakończyły pion implementacyjny v0.5. TASK-0149 pozostaje
odroczony; bieżący przepływ nie przelicza wcześniejszych pending ani decyzji
człowieka.
Manualny odbiór TASK-0186 nadal jest bramką wersji 0.4, ale rozpocznie się
dopiero po TASK-0188–0194.

TASK-0178 implementuje accuracy-first `fast-image-selector-v10`. Kod domeny,
migracja `0033_image_selection_sequence_order`, shortlistowanie top-12,
konsensus OCR, porządek rosnący/malejący, historyczne nazwy `seq_*` oraz
progresywny zapis są w repozytorium. Migracja lokalnego PostgreSQL do 0033
przeszła 2026-08-08.

TASK-0185 został domknięty: regresje, typecheck, OpenAPI i migracja przeszły.
Poglądowy smoke v10 na 240 zdjęciach rozpoznał 12/12 grup bez false merge/split
w 30,252698 s. Jest to około 4,95 raza dłużej od zachowanego historycznego
smoke 6,110191 s i mieści się na górnej granicy dopuszczonego kosztu. Raport:
`ai_docs/quality/image-selection-v10-smoke-report.json`.

Planowany wcześniej bezpośredni krok TASK-0186 został przesunięty za
TASK-0188–0194. Najpierw obowiązuje powtórny profil tych samych 200 zdjęć;
dopiero po jego ocenie właściciel odbiera około 5000, a następnie 32 000 zdjęć.
Nie otwierać automatycznej publikacji 500 000 layoutów bez bramki
`massImportAllowed`.

TASK-0187 usunął pętlę utraty lease ujawnioną przez realny run 32 079 zdjęć.
Wspólny runtime odnawia lease niezależnie od checkpointów, monitoring czyta
zagnieżdżony kontrakt `progress`, a regresje workera i selektora przeszły.
Po restarcie wyłącznie lane `image-selection` ten sam job wznowił się z
checkpointu i zwiększył postęp z 96 do co najmniej 160 bez ponownego uploadu.

Na polecenie właściciela ten rzeczywisty job został następnie anulowany na
checkpointcie 704/32 079; staging 32 079 zdjęć pozostał nienaruszony. Izolowany
profil pierwszych 200 zdjęć, bez cache, publikacji i zapisu domenowego, trwał
377,530649 s i rozpoznał 9 grup bez błędu skanu. Mediana wyniosła 45,519357 s
na grupę, a osiem pełniejszych grup domykało się w 44,1–47,7 s. OCR zużył
291,673863 s i jest dominującym kosztem. Raport:
`artifacts/image-selection-v10-first-200-timing.json`. Profil nie jest odbiorem
5000/32 000 i nie zamyka TASK-0186.

Właściciel zaakceptował plan v10.1: zachować pełny lekki scoring grupy, ale
oddzielić wybór reprezentanta od OCR numeru, uruchamiać szybkie kotwice,
adaptacyjny konsensus `2 -> 4 -> 8 -> 12` oraz progresywny fallback
`18 -> 36 -> 72`. Pierwszym celem jest 60–70% krótszy czas bez pogorszenia
jakości. Plan TASK-0188–0194 jest zapisany; implementacja rozpoczyna się od
TASK-0189. Pełny run 5000/32 000 pozostaje wstrzymany do profilu 200.

TASK-0188 jest ukończony. Nowe runy używają osobnego manifestu
`fast-image-selector-v10.1`; historyczny fingerprint v10 pozostaje
rozwiązywalny i zachowuje wcześniejsze zachowanie. W v10.1 kotwica pierwszego
numeru dotyczy wyłącznie pierwszej grupy, a dalsze zakresy pochodzą z dowodu OCR,
więc skok `19–27 -> 400–408` nie jest zastępowany cursorem. Konflikt kotwicy
lub OCR trafia do `manual_required` z `RANGE_CONFLICT`. Ruff, zawężony mypy,
95 testów obszaru selekcji i 28 testów API przeszły; nie wykonywano jeszcze
profilu 200.

TASK-0189 jest ukończony. Wewnętrzny wynik pełnej weryfikacji rozdziela teraz
`RepresentativeAssessment` od `RangeEvidence`. V10.1 nie uznaje skutecznego
fallbacku OCR za dowód kompletnej geometrii, a ranking reprezentanta nie zależy
od confidence ani dostępności numeru na tym samym JPEG-u. Najlepszy pełny kadr
może użyć zakresu z innej klatki; kadr przycięty nie wygrywa tylko dlatego, że
ma czytelną etykietę. Publiczne API i baza nie zmieniły się. Ruff, mypy oraz 108
testów obszaru przeszły; profil 200 pozostaje zadaniem późniejszej bramki.

TASK-0190 jest ukończony. Manifest v10.1 ma fingerprintowaną politykę pełnej
geometrii `1–9`, confidence co najmniej `0.64`. Stabilna pełna detekcja może
ustalić lokalny `board_count` mimo `None` z appearance scan, uruchomić jeden
batch OCR pierwszej, środkowej i ostatniej etykiety oraz pominąć fallback po
sukcesie. Konflikt lub brak kotwic nadal uruchamia fallback. Telemetria rozdziela
liczniki `anchoredOcr*` i `fallbackOcr*`; poprzedni fingerprint v10.1 pozostaje
rozwiązywalny. Ruff, mypy, 111 testów workera i 28 testów API przeszły. Profil
200 nie był jeszcze wykonywany.

TASK-0191 jest ukończony. Fingerprintowana polityka konsensusu wykonuje OCR na
poziomach `2 -> 4 -> 8 -> 12` i kończy zbieranie zakresu po dwóch zgodnych
odczytach wysokiej pewności. Pozostałe klatki top-12 nadal przechodzą ocenę
reprezentanta bez OCR. Brak wyniku rozszerza kolejny poziom, a konflikt wymusza
całą shortlistę. Telemetria zapisuje liczbę dowodów, liczbę kandydatów i powód
zatrzymania. Poprzednie fingerprinty v10.1 pozostają rozwiązywalne. Ruff, mypy,
114 testów workera i 28 testów API przeszły; profil 200 pozostaje niewykonany.

TASK-0192 jest ukończony. Nowy fingerprint v10.1 uruchamia fallback widocznych
etykiet progresywnie `18 -> 36 -> 72`, wykonując OCR tylko dla nowej części
rankingu. Wczesny wynik jest przyjmowany wyłącznie po pełnej bramce lattice, a
trudny przypadek dochodzi do tego samego deterministycznego zbioru 72 co
historyczny adapter v4. Telemetria raportuje próby poziomów, liczbę cropów,
poziom rozstrzygnięcia i wyczerpanie fallbacku. Historyczne fingerprinty
pozostają rozwiązywalne. Ruff, mypy, 119 testów workera i 28 testów API
przeszły; profil 200 pozostaje niewykonany.

TASK-0193 jest ukończony. Adaptacyjne poziomy mogą działać jako deterministyczne
bounded batche na odizolowanych verifierach, ale pomiar TASK-0194 wykazał, że
dwa predyktory Paddle/OpenCV konkurują o zasoby i są wolniejsze od jednego.
Produkcyjny budżet lane cztery został więc trwale ustawiony na trzy scan workers
i jeden verifier. Wyniki nadal zachowują kolejność shortlisty i parity trybu
pojedynczego; aktywacja dwóch verifierów pozostaje wycofana.

TASK-0177 zakończono z decyzją `passed`; test nie użył ani nie zmodyfikował
bieżących gier, stagingu oraz zdjęć właściciela.

TASK-0197 został przełączony z profilu read-only na produkcyjny rerun z
progresywnym eksportem. Profil PID `3472` zatrzymano; staging 32 079 zdjęć
pozostał niezmieniony. Aktualny run
`8d86fb77-531a-4999-a9c1-d02ed15d0af0` i job
`6b7289da-2312-4b08-8c42-5a6a42aeb3c9` pracują na fingerprintcie v10.1
`286b652ea8f19e3afb73017b54f096c0eb5dff828f0020f0b7454e9e42b76f40`.
Monitor PID `18844` zapisuje każdy gotowy reprezentant natychmiast do
`C:\Users\user\Documents\1 - 19809`; przy 128/32 079 istniały już pliki
`seq_1-9.jpg`, `seq_10-18.jpg` i `seq_19-27.jpg`. Raport przyrostowy:
`artifacts/image-selection-v101-live-32079-task0197-current.json`.

Run anulowano przy 29 888 / 32 079 po 30 590,702 s. Monitor zakończył się, a
automatyczny start kolejnego zbioru jest wstrzymany. Grupa 2109 błędnie połączyła
ekrany `18406-18414` i `18415-18423`; zakres pierwszych klatek został przypisany
lepszemu reprezentantowi drugiego ekranu. Plan TASK-0209–0218 wprowadza
bezpieczniejsze wykonanie, bramkę zgodności reprezentanta, historię runów i
ręczną galerię kandydatów.

Implementacja planu TASK-0209–0218 jest aktywna. Selektor v10.2 ma nowy
fingerprint i blokuje automatyczny eksport, gdy zakres finalnego reprezentanta
nie zgadza się z zakresem grupy. Skrypt live oraz Admin używają przyrostowego
kursora eksportu, pełna weryfikacja ma rekonstruowalny cache, a checkpoint/API
zawierają telemetrię ostatniego okna. Admin udostępnia historię runów i galerię
miniatur; nowe runy zachowują metadane wszystkich źródeł grupy, natomiast starsze
jawnie pokazują tylko dostępną shortlistę. Ręczne uzupełnienie opublikowanego
wcześniej runu unieważnia jego manifest, wznawia kontrolowaną rewizję i dopisuje
brakujący plik do ponownie wskazanego katalogu bez cichego nadpisania.

Automatyczne testy na tym etapie: 149 skupionych testów selektora, adapterów,
telemetrii, monitora i API oraz Admin 179/179 z typecheckiem klienta i aplikacji. Nie
uruchomiono kolejnego dużego runu. Dwa bieżące cykle stop/start lane selekcji
przeszły bez osieroconego PID; aktywny worker ma root PID 19540 i interpreter
PID 14656. Otwarte pozostają: powtórzenie kontroli po restarcie komputera,
pomiar realnego eksportera i warm cache oraz manualny odbiór galerii.

TASK-0210, TASK-0212, TASK-0213, TASK-0214, TASK-0215 i TASK-0216 są ukończone.
Przyrostowy eksporter, cache pełnej weryfikacji oraz bezpieczna historia/preview
mają zaliczone kontrakty automatyczne; rzeczywiste pomiary eksportera i warm
cache pozostają składową bramki TASK-0218. Read-only profil rzeczywistego
wycinka `29640–29739` skierował mieszaną grupę z klatkami `1_040014` i
`1_040025` do `manual_required`, bez wybranego pliku i bez ponownego utworzenia
błędnej nazwy `seq_18406-18414.jpg`. Telemetria wskazała OCR jako dominujący
koszt trudnego wycinka: 219,648 s z 254,422 s. Bramka pierwszych 200 zdjęć
potwierdziła identyczne decyzje jednego i dwóch verifierów, ale poprawa czasu
wyniosła tylko 4,10%, dlatego produkcja pozostaje przy jednym verifierze.

TASK-0219 usuwa regresję ujawnioną przez pierwszy produkcyjny run v10.2. Job
`14d281a2-7d9d-4331-b34a-3c96677092bb` zatrzymał się przy 864 / 32 079 z
`IMAGE_SELECTION_PERSISTENCE_CONFLICT`. Zakres `280–288` występował w kilku
grupach review; późniejszy wiarygodny kandydat rozstrzygał wcześniejszą grupę,
ale pozostawał również w `top_candidates` późniejszego
`skipped_existing_range`. Silnik utrzymuje teraz jednego właściciela kandydata,
a store pozwala promować wyłącznie tymczasowy rekord galerii z identycznym
checksumem. Regresja 83/83, Ruff i zawężony mypy przeszły. Ponowny duży run
pozostaje osobnym krokiem operatorskim po wdrożeniu poprawionego kodu.

Ukończony TASK-0220 wprowadza `fast-image-selector-v10.3` o fingerprintcie
`b5210620e3127fa4addebcb158d4e717df7d89ed08c6d09f354756bf18cab7e4`.
Korekta ogranicza nadmierny `manual_required`: JPEG z miękkim problemem
geometrii, kadru, ekspozycji albo liczby wykrytych plansz może zostać wybrany,
jeżeli jego własny OCR dokładnie potwierdza zakres grupy z confidence `>= 0.90`.
Inny lub nieznany zakres, konflikt, blur, okluzja i błąd techniczny nadal są
twardą blokadą. Bieżący run 32 079 zdjęć kończy się na zapisanym fingerprintcie
v10.2. Dopiero po jego stanie terminalnym oraz zakończeniu monitora API i lane
selekcji zostaną przeładowane, a run 42 403 zdjęć zostanie utworzony na v10.3.
Historia i galerie ręczne runu 32 079 pozostają dostępne do późniejszej pracy.
Regresja selektora, adapterów i joba przeszła 124/124; Ruff oraz skupiony mypy
manifestu i silnika również przeszły. Duży run v10.2 nie został zmodyfikowany.
Kolejność odbioru została rozszerzona: po terminalnym stanie tego runu usługi
zostaną przeładowane na v10.3, a te same 32 079 zdjęć zostanie przeliczone z
istniejącego stagingu do `C:\Users\user\Documents\1 - 19809 new`. Dopiero po
zakończeniu tego rerunu rozpocznie się zbiór 42 403 zdjęć. Oba wcześniejsze runy
i ich galerie ręczne pozostają zachowane.
Przed uruchomieniem 42 403 zdjęć obowiązuje bramka właścicielska: udział grup
`manual_required` jest liczony jako
`manual / (selected + manual + skipped)`. Wynik powyżej `20%` wstrzymuje automat
i wymaga jawnej decyzji właściciela, czy kontynuować, czy ponownie poprawić
algorytm. Wynik równy lub niższy niż `20%` pozwala uruchomić kolejny zbiór.

Manualny odbiór galerii TASK-0217 ujawnił brak prefiksu `/api/v1` w URL-u
JPEG-a kandydata. Metadane grupy działały, lecz miniatury oraz wybrany duży
podgląd pobierały nieistniejącą trasę `/admin/...` i otrzymywały HTTP 404.
Frontend korzysta teraz z pełnej trasy OpenAPI
`/api/v1/admin/image-selections/.../file`; staging, decyzje i aktywne joby nie
zostały zmienione. Ten sam pion rozszerza manualny odbiór o przewijaną galerię
wszystkich zachowanych miniaturek oraz pełnoekranowy podgląd z pojedynczym
poziomem powiększenia; funkcje nie wpływają na algorytm ani kolejkę workera.
Kolejna korekta TASK-0217 rozdziela liczniki `manually_selected` i
`missing_image`, wybiera domyślnie środkowy JPEG dla galerii do 20 zdjęć albo
dziesiąty dla większej oraz wymaga jawnego zatwierdzenia. `Enter`, strzałka w
prawo i przycisk zatwierdzają wybór i przechodzą do następnej nierozwiązanej
grupy; strzałka w lewo tylko wraca. Enter na miniaturze nie jest już ignorowany,
a niedokończone ładowanie galerii nie może omyłkowo zapisać pominięcia.
TASK-0217 udostępnia teraz również osobny, tylko do odczytu podgląd grup
`auto_selected`. Użytkownik wybiera run, otwiera `Weryfikuj wybory algorytmu`,
widzi oznaczony reprezentant selektora, wszystkie zachowane miniatury grupy,
pełny ekran i zoom. Porównywanie miniaturek nie zmienia decyzji, aktywnego joba
ani wyeksportowanych plików.

Implementacja TASK-0221–0227 wprowadza domyślny
`fast-image-selector-v10.4` o fingerprintcie
`8e913c923036ba7aa3f448d1049a37676d133b603103d0b641912ef17004ee7e`.
Grupowanie używa ROI siatki i potwierdza zmianę względem stabilnej poprzedniej
grupy, OCR dopasowuje siatkę `3×3` i wykonuje najwyżej dziewięć cropów na JPEG,
a dowód zakresu jest bounded do dwóch najlepszych kandydatów. Wszystkie zdjęcia
grupy nadal przechodzą tani scoring i najlepszy czytelny reprezentant jest
wybierany bez early exit. Blur, okluzja, brak widocznej planszy, konflikt
zakresu oraz błąd techniczny pozostają twardymi blokadami.

Nowe runy v10.4 wymagają dodatniego `first_sequence_number` w Adminie, API,
skrypcie live i CLI; worker powtarza tę kontrolę przed pracą. Historyczne runy
z nullable kotwicą oraz manifesty v9–v10.3 pozostają odtwarzalne. Panel ręczny
utrwala decyzje po ponownym otwarciu, pokazuje przewijaną pełną galerię, używa
świadomego zatwierdzenia klawiaturą lub przyciskiem oraz ma pełnoekranowy zoom.
Osobny tryb tylko do odczytu pozwala sprawdzać automatyczne wybory bez zmiany
runu albo plików wynikowych.

TASK-0229 dodaje jawne zakończenie grupy, która powiela już rozwiązany zakres.
Modal pokazuje `Odrzuć jako duplikat`; backend wymaga innej grupy z dokładnie
tym samym zakresem, audytuje `duplicate_range` i ustawia terminalny
`skipped_existing_range`. Grupa znika z kolejki bez nadpisywania istniejącego
pliku `seq_<start>-<end>`.

Automatyczna weryfikacja implementacji obejmuje deterministyczne testy granic,
fuzzy OCR, korekty `7300 -> 300`, limitów batcha, wyboru reprezentanta, kontraktu
kotwicy, API i panelu: 130 testów workera, 4 monitora live, 28 API/OpenAPI oraz
186 Admina przeszło wraz z lintem, typecheckiem i kontrolą wygenerowanego
klienta. TASK-0228 pozostaje aktywny: zgodnie z decyzją właściciela nie
uruchomiono jeszcze prób 200/4032/5000/42403 na rzeczywistych danych.

TASK-0228 zakończył się negatywnym odbiorem v10.4 na pełnym runie 42 403
JPEG-ów. Run `edf8625d-776c-4a73-8db9-29115fe05c14` utworzył 3 840 grup, z
czego 3 388 (`88,23%`) wymagało ręcznej obsługi, a tylko 452 miały znany zakres.
7 401 z 7 680 prób grid OCR zakończyło się bez hipotezy. Ścieżka grid-only jest
odrzucona i nie może być ponownie promowana bez oddzielnego dowodu na danych.

Implementacja TASK-0230 wprowadza domyślny `fast-image-selector-v10.5` o
fingerprintcie
`6ba81ff5a277c92a0cbf01b88aea7f8c896eee76aebb8323b2ed9cb4b3e28a32`.
v10.5 łączy szeroki descriptor wyglądu ze stabilnym buforem granicy grupy,
lekkim progresywnym OCR końców zakresu i obowiązkowym potwierdzeniem zakresu
przez reprezentanta. Dokładny odczyt może zamknąć dowód po jednym kandydacie;
odczyt fuzzy wymaga dwóch zgodnych kandydatów. Nie zmniejszono zakresu taniego
scoringu zdjęć w grupie.

Historia procesów otrzymuje `selectorVersion` rozwiązywane przez backend na
podstawie zapisanego fingerprintu; Admin pokazuje wersję w dropdownie obok daty
i statusu. Automatyczna weryfikacja v10.5 przeszła: Ruff, mypy, OpenAPI, oba
typechecki, 137 testów workera, 19 API i 186 Admina. Kontrakt odbioru znajduje
się w `ai_docs/quality/image-selection-v105-acceptance-contract.json`.
Implementacja jest gotowa, ale v10.5 nie jest jeszcze zaakceptowane na danych:
najpierw obowiązuje zestaw około 200 grup, potem około 5 000 zdjęć, a pełne
42 403 zdjęcia dopiero po zaliczeniu obu bramek i ręcznej ocenie właściciela.

TASK-0231 poprawia ręczne odzyskiwanie po `IMAGE_SELECTION_RANGE_CONFLICT`.
Pierwsza próba zatwierdzenia nadal tylko wykrywa zajęty zakres. Modal pokazuje
wtedy przy błędzie akcję `Odrzuć duplikat i dalej`, a główny przycisk oraz
ponowne `Enter`/`→` wykonują tę samą świadomą, idempotentną decyzję. Backend
potwierdza istnienie właściciela zakresu przed ustawieniem
`skipped_existing_range`; zmiana zakresu anuluje stan konfliktu. Typecheck i
186 testów Admina przeszły. Aktywny run v10.5 nie został przerwany.

TASK-0230 zakończył się negatywnie. Run v10.5
`b93de523-83f1-41bb-9f6d-4402936ebd6d` został anulowany po 4064 / 42 403
przeskanowanych zdjęć. Utworzył 271 grup: 13 automatycznych, 251 manualnych i 7
pominiętych, czyli 92,62% grup wymagało ręcznej pracy. 968 z 997 prób OCR
zakończyło się `RANGE_LABEL_LATTICE_INCOMPLETE`, mimo czytelnych rzeczywistych
zdjęć. V10.5 nie jest zaakceptowane.

TASK-0232 utrwala katalog wynikowy w IndexedDB per run, wymaga dostępu przed
review, wykonuje pełne uzgodnienie historycznych decyzji i czeka na zapis JPEG-a
przed przejściem do następnej grupy. Run `252cb5cb…` można naprawić przez
ponowne wskazanie `C:\Users\user\Documents\1 - 19809`; zgodne pliki zostaną
pominięte, a brakujące odtworzone. Przeszło 188 testów Admina i typecheck.

TASK-0233 ogranicza dropdown zapisanych procesów do runów aktywnych i
użytecznych. Widoczne są `created`, `processing`, `completed` oraz pełne
`waiting_for_review`; anulowane, nieudane i niepełne terminalne runy są ukryte.
Reguła obejmuje również localStorage oraz run, który właśnie zakończył się
anulowaniem. Przeszło 190 testów Admina i typecheck.

TASK-0234 dodaje fizyczne usuwanie wyłącznie anulowanych jobów
`image_selection` z workspace `Joby`. Mocne potwierdzenie wymaga prefiksu joba;
backend blokuje dane przekazane dalej i opublikowane, zachowuje współdzielony
staging oraz nigdy nie dotyka zewnętrznego folderu wynikowego. Zarządzane pliki
są obejmowane kwarantanną skoordynowaną z transakcją bazy. Przeszło 35
skupionych testów backendu, OpenAPI, 35 testów klienta i 192 testy Admina.

TASK-0235 rozdziela niepewność obrazu od niepewności zakresu. Admin pokazuje
osobne kolejki `Wybierz zdjęcie`, `Ustal grupę` i `Odrzucone`; potwierdzenie
zakresu zachowuje automatyczny JPEG, a odrzucenie można przywrócić do dokładnej
poprzedniej kolejki. `skipped_unreadable` nie trafia do review ani outputu.
Migracja `0041_image_selection_review_queues` rozszerza statusy i append-only
audyt. Przeszło 97 skupionych testów API/workera, 36 klienta, 194 Admina, Ruff,
oba typechecki, ESLint i OpenAPI.

TASK-0236 wprowadza domyślny `fast-image-selector-v10.6` o fingerprintcie
`bedb6d0fcba5e44faffcad849d5aa40d4ecc0e5277a7b0d5876dc000e33c3050`.
Verifier zaczyna od pięciu klatek ze środka grupy, a po ich odrzuceniu sprawdza
po trzy z obu brzegów. Czytelny JPEG bez zakresu zachowuje automatyczny wybór i
trafia do `Ustal grupę`; grupa bez żadnego czytelnego zdjęcia kończy się bez OCR
jako `skipped_unreadable`. Historyczne v10.5 pozostaje rozwiązywalne. Przeszło
181 skupionych testów API/workera i Ruff; nie uruchomiono nowego realnego runu.

TASK-0237 wprowadza domyślny `fast-image-selector-v10.7` o fingerprintcie
`322d4f5319f036cd0e1dc01f2dc781e68cb0a17dbb05f25abba409f842a732d6`.
Zakres dziewięciu layoutów może wynikać z dowolnych czterech kolejnych etykiet
przypisanych do czterech kolejnych pozycji lokalnej siatki. OCR kończy się
progresywnie na `9`, `18` albo najwyżej `36` cropach. Remis, trzy etykiety lub
zła geometria pozostają nierozwiązane. V10.7 zachowuje center-first v10.6 i
historyczne fingerprinty. Przeszło 187 skupionych testów API/workera; nie
uruchomiono nowego realnego runu.

Po jawnej decyzji właściciela rozpoczęto pełny run v10.7 na wszystkich 42 403
JPEG-ach bez wcześniejszych bramek 200/5000. Run
`45c80055-5beb-43bc-bc35-8c84b3e2b19c` i job
`39699f88-566f-4a09-b115-4bb9b2ea0349` używają niezmiennego stagingu
anulowanego runu v10.5, więc nie wykonują ponownego uploadu 11,2 GB. Kotwica to
`19810`, output to `C:\Users\user\Documents\19810 - 45152`, a raport i stan PID
znajdują się odpowiednio w
`artifacts/image-selection-v107-live-19810-45152.json` oraz
`.runtime/live-image-selection-v107-19810-45152.pid.json`. Lokalna baza jest na
migracji `0041`, API działa na `http://127.0.0.1:8003`, a wczesny snapshot przy
`256 / 42 403` potwierdził etap `image_selection:scanning`, świeży heartbeat i
zero błędów. Z 26 grup 3 miały automatyczny zakres, 22 miały automatycznie
wybrany JPEG i trafiły wyłącznie do `range_required`, a 1 była duplikatem;
`manual_required` i `skipped_unreadable` wynosiły zero. OCR zajmował 167,30 z
172,37 s czasu etapowego, więc skuteczność zakresów i tempo pozostają wczesnym
ryzykiem. Wynik jest niezaakceptowany do zakończenia runu i kontroli
właściciela; proces może zostać wcześniej anulowany.

Run v10.7 został kontrolowanie anulowany na checkpointcie 10 176 / 42 403 bez
usuwania stagingu ani outputu. Wynik końcowy to 648 grup: 34 automatyczne, 603
`range_required` i 11 duplikatów. Dominujący koszt stanowił OCR, a v10.7 nie
został zaakceptowany.

TASK-0238 wprowadza domyślny `fast-image-selector-v10.8` o fingerprintcie
`eb5006f3b6ed5e63b668074bf2e81d8b162d5794d542fd00457ee6a860682769`.
Selektor odtwarza pozycje `3×3` z większości widocznych ramek, rozpoznaje zakres
z jednego spójnego okna czterech etykiet mimo błędów OCR poza oknem, odrzuca
większościowo silny blur oraz ogranicza ogólny fallback do `9/18` cropów.
Fragmenty przejścia pomiędzy bezpośrednio kolejnymi zakresami nie trafiają do
review; jedna dokładna luka dziewięciu layoutów scala wiele fragmentów do
jednego wyniku.

Rzeczywisty profil 20 zdjęć poprawił się z 50,72 s i trzech nieznanych grup do
7,98 s i trzech poprawnych zakresów. Profil 1000 trwał 335,63 s i wykonał 5130
cropów OCR zamiast 9486. Końcowy profil 400 trwał 151,68 s: 15 wyborów
automatycznych, 11 duplikatów, 27 odrzuconych fragmentów i zero elementów review.
Profil 5000 z ręczną kontrolą właściciela i pełny run 42 403 pozostają
wstrzymane w TASK-0197.

Pełne testy v10.8 przeszły: 658 workera, 327 API (23 świadomie pominięte) i 194
Admina. Zmienione pliki przechodzą Ruff, rdzeń selektora przechodzi mypy, a
OpenAPI, ESLint i TypeScript są aktualne. Repozytorium zachowuje wcześniejszy
dług: pełny Ruff zgłasza 6 błędów E501 w migracji `0035`, a pełne mypy 10 błędów
w trzech niezmienionych modułach workera; szczegóły są w TASK-0238.

Po restarcie komputera właściciel jawnie polecił ominąć pośredni profil 5000 i
uruchomić pełny rerun v10.8 na istniejącym stagingu 42 403 JPEG-ów. Aktywny run
`d43aa481-7efe-467b-8dbc-998b609d4ae8` i job
`861a42d0-e3e0-4425-b9ba-f45665bb33b2` używają stagingu runu v10.5
`b93de523-83f1-41bb-9f6d-4402936ebd6d`, kotwicy `19810` oraz outputu
`C:\Users\user\Documents\19810 - 45152`. API v10.8 działa na porcie 8003 jako
PID `11492`, dedykowany worker jako PID `12068` (launcher `13608`), a monitor
ma PID `2608`. Raport i stan monitora znajdują się w
`artifacts/image-selection-v108-live-19810-45152.json` oraz
`.runtime/live-image-selection-v108-19810-45152.pid.json`. Snapshot przy
`160 / 42 403` potwierdził 10 grup, 10 automatycznych wyborów, zero manualnych,
zero pominiętych, zero błędów i 10 zapisanych JPEG-ów. Nie uruchamiać drugiego
API, workera ani runu; najpierw sprawdzić raport oraz PID state.

Właściciel następnie zatrzymał run v10.8. Został anulowany na checkpointcie
1440 / 42 403 z wynikiem 100 grup: 50 automatycznych, 39 `range_required` i 11
pominiętych. Przetwarzanie trwało 472,633 s, z czego OCR 395,427 s. Wszystkie 39
środkowych JPEG-ów z `range_required` zostało obejrzanych: każdy miał czytelny
zakres, więc żaden przypadek nie uzasadniał review. Artefakt audytu znajduje się
w `artifacts/range-required-v108-review/manifest.csv`. Nie wznawiać v10.8.

TASK-0239 wprowadza domyślny `fast-image-selector-v10.9` o fingerprintcie
`6c14854d3f38744a3451da11e516bc4f10c348d3f8a4c32e9a999c69e9979720`.
Częściowa kotwica działa od trzech ramek na dwóch osiach, OCR sprawdza najpierw
ramki widoczne, a dowód ma trzy poziomy: cztery etykiety od `0.72`, trzy od
`0.82` i dwie od `0.90` potwierdzone na drugim JPEG-u o innym checksumie.
Historyczny fingerprint v10.8 pozostaje bez zmian, a fingerprint taniego skanu
v10.9 jest identyczny z v10.8.

Powtórna kontrola tych samych 39 środkowych JPEG-ów początkowo dała 35 poprawnych
zakresów, cztery bez decyzji i zero błędnie zaakceptowanych zakresów. Dalsza
analiza wykazała zachłanny wybór surowego albo przetworzonego wariantu OCR dla
pojedynczego pola. v10.9 zachowuje oba warianty i rozstrzyga je jako hipotezy
całej pozycyjnej siatki; konflikt nadal kończy się fail-closed. Fragment
ograniczony z obu stron tym samym dokładnym zakresem jest bezpiecznie oznaczany
jako `skipped_existing_range`, bez pliku wynikowego.

Finalna bramka pierwszych 1440 źródeł została zaliczona. Profil
`artifacts/image-selection-v109-first-1440-gate-final.json` trwał 110,883022 s,
wykonał 148 pełnych weryfikacji i miał 1624 trafienia cache przy zerze chybień.
Pierwszych 100 domkniętych grup dało dokładnie 60 automatycznych unikalnych
zakresów i 40 duplikatów, bez review, nieznanego zakresu ani
`skipped_unreadable`. Pełne testy przeszły: 665 workera i 327 API, przy 23
świadomie pominiętych integracjach API. Ruff i mypy dla zmienionych plików
przechodzą; pełne repozytoryjne kontrole nadal pokazują tylko wcześniejszy dług z
TASK-0238. Pełny run 42 403 jest odblokowany, ale musi użyć nowego pustego
katalogu, aby zachować 50 plików anulowanego v10.8.

Po commicie `04c2f44` (`v0.5.13`) uruchomiono jeden pełny run v10.9 na
istniejącym immutable stagingu, bez ponownego uploadu. Run
`2fa7f363-a9d4-406e-8b51-ed22da21f259` i job
`9974c3e1-505c-43dd-be22-becc86a688b1` przetwarzają 42 403 źródła z kotwicą
`19810`. Output to nowy katalog
`C:\Users\user\Documents\19810 - 45152 v10.9`; stary katalog nadal zawiera 50
plików v10.8. API działa na `http://127.0.0.1:8003`, jedyny worker ma launcher
PID `7252` i worker PID `16748`, a monitor PID `1960`. Raport i PID state to
`artifacts/image-selection-v109-live-19810-45152.json` oraz
`.runtime/live-image-selection-v109-19810-45152.pid.json`.

Checkpoint 1568 / 42 403 nastąpił po około 112 s: 63 zapisane unikalne zakresy,
39 duplikatów, zero błędów i 152 weryfikacje. Jedyny chwilowy `range_required`
ma `groupOrder=35` i odpowiada znanemu fragmentowi pomiędzy tym samym zakresem
`19918–19926`; pełny profil potwierdził jego końcową klasyfikację jako duplikatu.
Nie uruchamiać drugiego API, workera ani runu. Przed ingerencją sprawdzić raport,
PID state i świeży heartbeat joba.

TASK-0240 usuwa regresję powiązania folderu wynikowego w Adminie. Folder
wybrany przed nowym uploadem jest teraz stanem oczekującym i nie jest
przypisywany do aktualnie wyświetlanego historycznego runu. Dopiero pomyślne
utworzenie runu wiąże katalog z jego `runId`; progresywny oraz ręczny zapis
dodatkowo odrzucają uchwyt należący do innego runu. Regresję potwierdził
wcześniej plik starego runu `252cb5cb…` zapisany do katalogu przygotowanego dla
zakresu od `45163`. Po poprawce Admin przechodzi 195 testów, typecheck i ESLint.

Pełne runy v10.9 ujawniły końcowy `IMAGE_SELECTION_PERSISTENCE_CONFLICT` dla
dokładnej luki dziewięciu layoutów rozłożonej na kilka fragmentów
`range_required`. Przyczyną nie był duplikat numeru zakresu, lecz próba
technicznego przepięcia rekordu kandydata pomiędzy grupami podczas korekty
fragmentacji. Poprawka zachowuje najlepszy JPEG w jego źródłowej grupie, a inne
fragmenty oznacza jako `skipped_existing_range` z tym samym zakresem i jawnym
właścicielem. Prawdziwe konflikty indeksu albo checksumy nadal blokują zapis.
Przeszło 105 testów skupionych, Ruff, mypy i 666 testów workera. Run
`823c5b99-9447-4f25-940f-b2aaba8db56f` został kontrolowanie wznowiony z
checkpointu 42 400 i zakończył 42 422 / 42 422 jako `waiting_for_review` bez
błędu. Grupa 3264 jest właścicielem `88507–88515`, a grupa 3263 ma
`skipped_existing_range`. Terminalne uzgodnienie monitora przechodzi teraz przez
wszystkie strony grup; dopisało 21 brakujących JPEG-ów i potwierdziło 2 567
plików wynikowych. Skupiona regresja po tej korekcie przechodzi 111/111.

Kontrolery dalszej kolejki zostały przeładowane po poprawce odpowiedzi listy
jobów w PowerShell `StrictMode`: endpoint może zwrócić obiekt z `items` albo
bezpośrednią tablicę. Etap `93853 -117828` rozpoczął świeże przygotowanie źródła,
a sześć dalszych kontrolerów czeka sekwencyjnie; nie działa drugi job selekcji.

Benchmark przepustowości v10.13 z 2026-08-15 porównał w układzie ABBA ten sam
wycinek 1000 JPEG-ów. `3 scan + 1 verification` uzyskało średni wall time
`210,338 s`, a `4 scan + 1 verification` — `194,425 s`, czyli poprawę
`7,566%`. Kanoniczne wyniki wszystkich grup były identyczne. Etap `v0.6.18`
podnosi dlatego domyślny budżet lane selekcji z czterech do pięciu; manifest i
fingerprint v10.13 pozostają bez zmian. Po walidacji i commicie lane selekcji
ma zostać kontrolowanie przeładowany przed kontynuacją istniejącej kolejki.

Run v10.17 `177220–179082` zakończył się po `2771,868 s` selekcji.
Przeanalizował 1570 JPEG-ów, wykonał 964 weryfikacje i utworzył 229 grup
fizycznych: 174 automatyczne, 33 manualne oraz 22 pominięte duplikaty. Bramka
potwierdziła dokładnie `207/207` logicznych właścicieli, ciągłość zakresu i 174
pliki wynikowe. Kontroler kolejki został wcześniej zatrzymany, więc żaden
następny etap nie rozpoczął się na v10.17.

V10.18 wprowadza mocny single-frame early exit przy zachowaniu kwantyli
`50%, 35%, 65%, 15%, 85%`. Czytelny środek z dokładnym, niefuzzy zakresem,
zgodnym board countem i pełną bramką jakości kończy grupę bez OCR pozostałych
czterech klatek. W przeciwnym razie wykonywane są kolejno pary wewnętrzna i
zewnętrzna; konflikt pozostaje fail-closed. Fingerprint v10.18 to
`122bfcf412f6a8bbdb5714f2de012e223366f7b234f9e409c4d0d2e231dc51d6`.

Dwa zimne benchmarki po 100 rzeczywistych JPEG-ów potwierdziły poprawę bez
zwiększenia kolejki manualnej. Dla `149626` v10.18 wykonał 67 zamiast 75
weryfikacji, trwał `89,938996 s` zamiast `102,199397 s` i dał 4 automaty wobec
zera. Dla `177220` wykonał 57 zamiast 68 weryfikacji, trwał `83,049762 s`
zamiast `93,853847 s` i dał 7 automatów wobec 2. Raporty to
`artifacts/image-selection-v1018-v1017-real-149626-prefix100.json` oraz
`artifacts/image-selection-v1018-v1017-real-177220-prefix100.json`.

Walidacja v10.18: pełny worker `738/738`, Ruff i Ruff Formatter dla 519 plików
oraz mypy dla 328 modułów przechodzą. Następna kolejka ma ruszyć dopiero po
commicie i kontrolowanym przeładowaniu API oraz lane selekcji na v10.18.

## Bieżąca korekta selekcji v10.20 — 2026-08-18

- Właściciel odrzucił wynik v10.19 po wykryciu błędnych zakresów. Run
  `70363–93861` (`e6ec9f6f-b424-437d-b2d0-0b94c609e61b`) anulowano przy
  `19200/42422`; kontroler kolejki PID 19016 został zatrzymany. Nie ma aktywnego
  joba ani zgody na start następnego etapu.
- Dla runu `1–19809` zapisano 2583 fizyczne fragmenty: 1776 automatów, 491
  `range_required` i 316 duplikatów. Wcześniejszy raport błędnie zsumował
  `1776 + 491 = 2267`; kolejka ustalenia zakresu nie jest liczbą wyborów zdjęcia
  ani liczbą logicznych właścicieli. Oczekiwana siatka nadal ma 2201 zakresów.
- V10.20 używa oczekiwanej kolejności jako hipotezy sprawdzanej lokalnym OCR.
  Akceptuje dwa dokładne odczyty z pełnej geometrii albo trzy pozycje z
  częściowego viewportu (co najmniej jedna dokładna, dwa wiersze i kolumny).
  Mocny odczyt innego zakresu oraz twardy problem jakości pozostają fail-closed.
- Domyślny manifest to `fast-image-selector-v10.20`, adapter v18, fingerprint
  `5b979eb826bbf943047bff41a98e293ecf9f3cb46ba95044b606edd32a33bd86`.
  V10.19 zachował fingerprint `18886fe8...` i dawne zachowanie.
- Liczniki `manual` oraz `rangeRequired` są rozdzielone w checkpointach, API,
  OpenAPI, Adminie i runnerze. Syntetyczne uzgodnienie 2583/2201 trwa 1,922 s.
- Następny test produkcyjny zaczyna się od `1–19809` po E2E na małym korpusie.
  Kolejny prawidłowy folder źródłowy to
  `E:\777 zd\19810 - 45162`, czyli 2817 zakresów; historyczny staging kończący
  się na 45152 nie może być użyty.
- Powtarzający się błąd dostępu pytest usunięto trwale: skasowano niedostępny
  katalog `%TEMP%\pytest-of-user`, zweryfikowano nowy proces i rozszerzono
  `run_python_tests.ps1` o izolowany basetemp z PID-em również dla `api:test`.
- Dodano checksumowany korpus regresyjny 283 zdjęć w kolejności malejącej:
  17 czytelnych właścicieli zakresów i 3 negatywne przypadki jakościowe. Zimny
  benchmark trwa `68,298789 s`, wykonuje 48 weryfikacji, osiąga 17/17 logicznych
  właścicieli, 9 pominiętych fragmentów, bramkę 20/20 i 0 naruszeń dowodu.
  Raport: `artifacts/image-selection-v1020-low-quality-descending-v18-final.json`.
- Końcowa walidacja przed `v0.6.26`: pełny Python `1109 passed, 26 skipped`,
  skupiona regresja selektora `222/222`, Admin `201/201`, Mobile `82/82`,
  Reviewer `25/25`, Admin API Client `38/38`, Shared TS `24/24`. Ruff, mypy dla
  329 plików, Prettier, lint, typecheck, OpenAPI oraz składnia 34 skryptów
  PowerShell przechodzą. TASK-0245 jest zamknięty; kontrolowany run `1–19809`
  nie został automatycznie uruchomiony.

## Do not start yet

- automatycznej publikacji pełnych 500 000 layoutów przed kontrolą pierwszych
  partii i jawnym otwarciem `massImportAllowed`,
- dodawania i testowania kolejnych gier,
- wielogrowego wydania mobilnego,
- pełnej macierzy urządzeń i odroczonego hardeningu bez nowego jawnego planu,
- Celery/Redis, mikroserwisów, chmury, Google Play lub publicznego Admin API.

## Lokalna ręczna selekcja — TASK-0246

Admin ma niezależną zakładkę `Ręczna selekcja` dla awaryjnego przypisywania
oryginalnych JPEG-ów do kolejnych zakresów `start–start+8`. Działa lokalnie przez
File System Access API, zapisuje sesję per gra w IndexedDB i nie uruchamia API,
workera, stagingu ani OCR. Enter zapisuje `seq_*.jpg` i przechodzi do następnego
zdjęcia, F jest jednoklawiszową alternatywą, Tab pomija zakres przy tym samym
zdjęciu, a A jest jednoklawiszową alternatywą dla Ctrl+Z i usuwa wyłącznie
zweryfikowany plik zapisany przez tę sesję. Skróty ignorują fokus formularzy.
Podgląd można powiększyć do 3000%. Implementacja jest gotowa do testu
manualnego w przeglądarce; zadanie `0246` pozostaje `in_progress` do akceptacji.

W ramach `v0.6.28` sesja otrzymała IndexedDB v2 z append-only magazynem
`traceEvents`. Widok zapisuje zdarzenie dopiero po `decode()` i 300 ms
widoczności, a Enter/Tab/Ctrl+Z zapisują odpowiednio decyzje i ich cofnięcia.
Folder wynikowy jest synchronizowany przez
`manual-image-selection-output-v1.json`; pełny ślad można jawnie wyeksportować
jako `manual-image-selection-trace-v1.json`. Artefakty są chronione przez
`sessionKey` i checksumy, a stare sesje pozostają `anchor_only`.

W `v0.6.29` import layoutów rozpoznaje foldery `seq_<start>-<end>.jpg|jpeg`.
Managed manifest przechowuje poświadczony zakres, worker sortuje go numerycznie,
a `sequence-number-from-attested-range-v1` pomija OCR numerów i przypisuje
plansze row-major. Niepełna geometria pozostaje w korekcie bez przesunięcia
pozostałych numerów; zwykłe nazwy nadal korzystają z historycznego OCR.

W `v0.6.30` worker ma kohortę `representative-quality-ranking-cohort-v1`,
deterministyczny trening `representative-quality-mlp-v1`, eksport ONNX i
snapshot `shadow`. Job może przypiąć snapshot przez
`representative_ranker_snapshot`; diagnostyka zapisuje ranking rekomendowany
przez model bez zmiany wyniku v10.21. Migracja `0044_representative_ranking`
tworzy osobne tabele kohort, iteracji i historii aktywacji. Promocja do v10.22
nie została wykonana.

W `v0.6.31` eksport ONNX jest sprawdzany na tych samych wektorach cech co
PyTorch, a maksymalny błąd zgodności trafia do raportu treningowego. Snapshot
shadow jest weryfikowany checksumą przed utworzeniem rekomendacji; ranking jest
wyłącznie diagnostyczny i nie zmienia wyniku selekcji.

Po `v0.6.31` poświadczony zakres jest również przenoszony do geometrii planszy.
Reviewer pokazuje komunikat „Numer z nazwy pliku seq_*” i blokuje pole numeru
do czasu jawnego odblokowania korekty. Korekta geometrii zachowuje tę informację,
aby późniejszy zapis nie zamienił deklaracji operatora w niejawny OCR.

## Naprawa startu importu layoutów z browser stagingu — v0.6.39/v0.6.40

Wdrożono manifest-aware przepływ dla gotowego stagingu
`31259729-de6a-4962-b8df-7aa0c0b7c49b`. Odczyt `_browser_manifest.json` zachowuje
logiczne nazwy `seq_*` mimo fizycznych plików `00000001.jpg`, a worker zapisuje
również fizyczną ścieżkę potrzebną do bezpiecznego kopiowania. Staging layoutów
nie wygasa po restarcie API; Admin może go wylistować, przygotować preflight,
usunąć jawnie albo wznowić bez ponownego uploadu.

Start importu wymaga teraz aktualnej checksumy manifestu i preflightu. Jest
idempotentny i po ponownym kliknięciu zwraca istniejący job zamiast tworzyć
duplikat. Panel pokazuje raport przed przyciskiem startu oraz komunikat
`Job utworzony — oczekuje na worker`. Dla bieżącego stagingu read-only preflight
potwierdzono: `2201` źródeł, `19746` nowych numerów, `63` użyte ponownie,
`7` pominiętych źródeł, `0` częściowych, `7` alternatywnych oraz pierwszy
nierozwiązany numer `64`. Iteracja symboli v2 `47b6aa0d-2cea-4765-97f0-ee1f86cfc056`
przeszła bramkę (`candidate_ready`) i została aktywowana. Następnie utworzono
świeży job importu `b0575f5f-8ec1-46d6-8262-8ef0309055c7` w trybie
`rerun_current_models`; stary anulowany job `be0a204d-e515-4a64-8716-2ac708454862`
pozostaje tylko audytowy. Ostatni odczyt: `2232/4402`, etap
`image_pipeline:sequence_ocr`, `1` błąd źródła i `30` pozycji review; proces
pozostaje aktywny.

Weryfikacja: skupione testy API/workera dotyczące manifestu, preflightu i
idempotentnego startu przechodzą; Admin typecheck, Ruff i wygenerowany OpenAPI
są aktualne. Pełne mypy repozytorium nadal zgłasza istniejące błędy w
`images/selection/ranker.py`, niezwiązane z tą zmianą.

## Diagnostyka siatki i stabilny split symboli — v0.6.41/v0.6.42

Diagnostyka kohorty siatki korzysta z tej samej kwalifikacji co budowa profilu i
raportuje `eligibleGeometryCount`, `excludedGeometryCount` oraz konkretne
powody wykluczenia. Dla bieżącej gry oczekiwane jest 63/63 kwalifikujących
próbek; ponowne utworzenie niezmienionej kohorty jest jawnie idempotentne.

Dataset symboli używa polityki `source-family-balanced-split-v2`. Przy co
najmniej czterech źródłach manifest zapisuje deterministyczny, niezależny split
train/validation/test/regression; dla siedmiu źródeł kohorty 63 plansz jest to
4/1/1/1, czyli 540/135/135/135 cropów. Przypisania źródeł są częścią
konfiguracji, więc późniejsze rozszerzenie kohorty nie zmienia starszych splitów.
Kohorta z mniej niż czterema źródłami kończy się kontrolowanym `rejected`, a nie
technicznym `failed`.

Browserowy import layoutów otrzymał schema v5. Nowy job przypina aktywny model
symboli i profil siatki oraz ich fingerprinty. Anulowany job z wcześniejszymi
snapshotami nie jest wznawiany; ponowne kliknięcie tworzy nowy job na tym samym
stagingu, bez ponownego uploadu, zachowując stary rekord do audytu.

W `v0.6.48` preflight browserowego importu zwraca również fingerprint aktywnego
modelu symboli i profilu siatki, a start odrzuca nieaktualny snapshot stabilnym
błędem `IMAGE_SEQUENCE_MODEL_SNAPSHOT_STALE`. Panel Admina przekazuje te wartości
przy starcie. Naprawiono też brak zależności `JobService` w endpointcie preflight,
który ujawniałby się dopiero po restarcie API. Aktywny świeży job
`b0575f5f-8ec1-46d6-8262-8ef0309055c7` pozostaje przypięty do modelu symboli
`47b6aa0d-2cea-4765-97f0-ee1f86cfc056` i profilu siatki
`d1046ab9-95db-4467-aae9-ee91fe18dfac`.

## Fail-closed geometria stron `seq_*` — v0.6.49–v0.6.53

- Bieżący job `b0575f5f-8ec1-46d6-8262-8ef0309055c7` nie jest źródłem geometrii
  ani treningu. Zostanie oznaczony jako zastąpiony dopiero po zaliczeniu nowego
  preflightu; nie wznawiać go zwykłym retry.
- Nowy preflight `page-geometry-preflight-v1` przypina profil maksymalnie siedmiu
  ręcznie poprawionych stron, snapshot override'ów i content-addressed manifest
  dziewięciu quadów per checksum. Import `seq_*` bez ukończonego manifestu
  geometrii jest blokowany; nie wraca do detektora v3.
- Wynik bez kompletnej, niezależnie zweryfikowanej siatki trafia do lokalnej
  korekty całej strony. Cropy i symbole otrzymują tylko geometrię verified;
  `geometryValidity`, `cropValidity` i confidence klasyfikatora są rozdzielone.
- Kontrola rzeczywistych stron `64–72`, `91–99`, `577–585`, `694–702`,
  `991–999`, `1603–1611`, `1648–1656`, `1702–1710` i `1918–1926` zaliczyła
  rejestrację `9/9`. Czterowątkowy pomiar trwał 2,225 s dla dziewięciu stron;
  szacunek dla 2194 nierozwiązanych źródeł wynosi około 9–12 min plus I/O.
- Migracja `0048_image_page_geometry_overrides` musi zostać zastosowana przed
  użyciem edytora korekty. Następny krok operacyjny to preflight stagingu
  `31259729-de6a-4962-b8df-7aa0c0b7c49b`, a następnie ewentualna korekta stron
  wskazanych przez manifest. Pełny import zostanie uruchomiony wyłącznie przy
  `reviewRequiredSourceCount = 0`.

W `v0.6.54` preflight weryfikuje checksumę poświadczonego
`_browser_manifest.json` przed utworzeniem job-specific manifestu managed
originals. Te dwa manifesty mają różne, prawidłowe checksumy; porównywanie ich
ze sobą błędnie odrzucało każdy rzeczywisty staging po restarcie workera.

Preflight `66a4ad95-da52-4939-ac88-c9fc82c8b480` z wersją ORB 500 zakończył
się bez błędów technicznych, lecz bezpiecznie skierował `575` czytelnych stron
do korekty. Kontrola trzech takich stron oraz równomiernej próbki `60/575`
pokazała, że przyczyną jest zbyt mały limit ORB, nie jakość zdjęć ani próg
geometrii: `1000` cech daje `60/60` poprawnych rejestracji. `v0.6.56` podnosi
ten limit, a `featuresVersion` jest częścią przypiętego profilu, więc wymagany
jest świeży preflight; manifest `e27e03c4…` pozostaje wyłącznie audytowy.

W `v0.6.57` executor preflightu przetwarza ograniczone partie po 25 stron i
zapisuje checkpoint po każdej z nich. Nie wysyła już całego stagingu do jednego
`executor.map`, dzięki czemu restart workera nie może ukrywać postępu ani
opóźniać anulowania do końca pełnego zbioru.

W `v0.6.58` retry preflightu geometrii resetuje wyłącznie jego pochodne
liczniki postępu i checkpoint. Job przelicza cały staging deterministycznie,
więc zachowanie częściowego kursora z przerwanej próby byłoby błędne; retry
pozostałych rodzajów jobów nadal zachowuje swój trwały postęp.

W `v0.6.59` profil rejestracji używa wersjonowanego fallbacku ORB
`1000 → 1500 → 3000` wyłącznie dla strony, która nie przeszła niższego budżetu.
Rzeczywiste osiem czytelnych stron pozostawionych przez preflight 1000
przechodzi w tej polityce: siedem przy 1500, a `11710–11718` przy 3000, przy
niezmienionych progach RANSAC i czerwonych ramek. Następny preflight będzie
świeży, a pełny import nadal jest zablokowany aż do zera stron review.

W `v0.6.60` kontroler workerów porównuje czas startu procesu po normalizacji
UTC, niezależnie od tego, czy PowerShell odczytał go jako tekst czy `DateTime`.
Równoważne duplikaty `PATH`/`Path` w środowisku hosta nie blokują już samego
odczytu stanu; rozbieżne wartości nadal zatrzymują bezpiecznie operację. Dzięki
temu kontroler nie oznacza zdrowego workera jako `stale` i nie tworzy drugiej
kopii lane'u.

Preflight geometrii `9950ec44-146b-4219-9e23-0de6e83b4b89` dla stagingu
`31259729-de6a-4962-b8df-7aa0c0b7c49b` zakończył się `2194` zarejestrowanymi
stronami, `7` źródłami pominiętymi przez kanoniczne numery `1–63` i `0` stronami
do korekty. Używa manifestu geometrii
`61e8c5b2ec489aa8c18f4d7ec57008d90b9305a50092feb78c5a9a23932e6cf4` i trwał
`10 min 37 s`, więc spełnia bramkę `≤15 min`.

W `v0.8.32` worker preflightu akceptuje opcjonalne metadane prezentacyjne
`source_display_name`, które API zgodnie z kontraktem przypina do nowych jobów,
ale nadal odrzuca nieznane pola oraz pustą lub zbyt długą etykietę. Rozjazd
zamkniętych list pól powodował, że poprawne joby stagingu
`124129 - 149634` kończyły się przed pierwszym zdjęciem błędem
`INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD`. Dane stagingu, profil rejestracji i
manifest źródłowy nie były przyczyną błędu.

Stary job `b0575f5f-8ec1-46d6-8262-8ef0309055c7` został anulowany jako
zastąpiony. Świeży job `b2d9b299-a851-4e17-9ba3-dacaa7966978` zachowuje ten
manifest, aktualne snapshoty modelu i staging. Jego pierwsza próba przerwała
się przed pierwszą stroną, ponieważ konstruktor fallbackowego rejestratora
szukał anchorów w `artifacts/data/data/originals/...`; staging i wszystkie 2201
JPEG-ów są poprawne. Bieżąca poprawka ładuje anchor względem zarządzanego rootu
`data/` i nie inicjalizuje fallbackowych anchorów, gdy job ma już przypięty
manifest geometrii. Test regresyjny obejmuje oba warianty. Retry tego samego,
poprawnie przypiętego joba jest aktywne; nie utworzono nowego uploadu ani joba.

Pierwszy jawny recrop v19 `9363e55b-3493-4dc5-b296-3e6a21efdb24` został
odebrany przez proces workera uruchomiony przed wprowadzeniem payloadu schema
v2. Stary kod skierował go do historycznej ścieżki v1 i zakończył przed
pierwszą planszą błędem `IMAGE_GRID_PROFILE_SNAPSHOT_INVALID`; staging i dane
importu nie zostały zmienione. Nowy recrop wymaga restartu kontrolowanego lane'u
po wdrożeniu kodu v2, a nie dodawania historycznego `gridProfile` do payloadu.
Preview i oba workery reinferencji ograniczają teraz pracę do oczekujących
plansz importów `waiting_for_review`, dzięki czemu anulowany `b057…` nie jest
wliczany do bieżącego `b2d9…`. Każdy zapis nadal ponownie sprawdza status
planszy; decyzje `accepted/corrected/rejected` są chronione.
Świeży worker potwierdził wejście do ścieżki v2, po czym pierwsza próba
checkpointu wykryła brak wspólnego `schema_version=1`. Poprawka obejmuje
checkpointy grid v1/v2 i symbolowej reinferencji; job nie doszedł przed nią do
zapisu żadnej planszy.

Po poprawkach i restarcie kontrolowanego lane'u recrop
`9363e55b-3493-4dc5-b296-3e6a21efdb24` zakończył `19 745/19 745`: utworzył
`19 364` rewizje v19, pozostawił `381` plansz do ręcznej geometrii i nie miał
błędów technicznych. Kolejny job symboli
`23f37219-2964-412a-a7f6-0284d334ad9a` zakończył `19 745/19 745` bez błędu.
Fingerprint wszystkich `64` chronionych decyzji i ich projekcji geometrii był
identyczny przed i po jobach (`e6395e30…`). Anulowany duplikat `b057…` oraz
testowy import `0490…` usunięto transakcyjnie; aktywny `b2d9…`, jego staging i
`19 745` oczekujących pozycji pozostały zachowane.

## TASK-0249 — baseline geometrii komórek i Reviewera

Na podstawie problemów z cropami symboli, dużą kolejką review i równoległym
udostępnianiem zaakceptowano D-204–D-206. Następny pion geometrii zachowuje
lokalizację dziewięciu plansz, ale tworzy osobny
`BoardCellGeometryManifestV1`: finalne komórki wynikają z wielopunktowej siatki
5 × 3, bez wymuszania prostopadłości w obrazie źródłowym. Cztery punkty ręcznej
korekty oznaczają zewnętrzne narożniki tej siatki.

Operacyjna kolejka ma docelowo używać niezmiennego klucza
`(source_order_index, position_index, review_item_id)` i transakcyjnego
first-save-wins. Wiele różnych importów ma dzielić jeden produkcyjny Reviewer i
jeden Quick Tunnel; zatrzymanie pojedynczej sesji nie może kończyć pozostałych.

TASK 1 obejmuje wyłącznie baseline, decyzje i aktualizację testu migracji:
`0048_image_page_geometry_overrides` jest jedyną oczekiwaną głową po `0047`.
Był to stan po TASK 1; obecnie istnieje już nieaktywny estymator TASK 3, ale
pełna integracja produkcyjnego pipeline'u geometrii v19, kolejki i assignments
nie została rozpoczęta. Ręczny preview, append-only zapis i jawny pending-only
recrop mają już osobny API i UI.
Punktem bazowym pozostaje `3595a32` (`v0.6.59`). Wcześniejsze niezacommitowane
zmiany fallbacku importu, kontrolera workerów oraz `apps/admin/next-env.d.ts`
są zachowane i jawnie wykluczone z przyszłych commitów TASK-0249; następny numer
`v0.6.*` jest przydzielany dopiero przy zamknięciu każdego osobnego TASK.

TASK 2 dodał nieaktywny `BoardCellGeometryManifestV1` oraz rzeczywisty corpus
v19. Kontrakt oddziela quady plansz z `PageGeometryManifestV1` od granic siatki
symboli 5 × 3, wyprowadza 15 komórek row-major w pikselach źródła i waliduje
automatyczne albo ręczne evidence bez wymuszania prostopadłości na zdjęciu.
Manifest jest kanoniczny, content-addressed i ma fingerprint
`45a82dbb0f86ca62646e1d680f2a0d9ea78a62f38b1d24b72be2ce50764aeb25`.

Corpus wykorzystuje 27 istniejących decyzji właściciela z
`cell-grid-golden-v1`: trzy geometrie dla każdej z dziewięciu pozycji oraz dwie
grupy źródłowe. Loader ponownie sprawdza checksumy źródłowego manifestu,
adnotacji i każdego JPEG-a. TASK 2 nie implementuje estymatora, nie podłącza
manifestu do pipeline'u i nie zmienia aktywnego croppera v18, API, bazy ani UI.
JPEG-i są lokalnym, ignorowanym przez Git corpusem: test kontraktu działa z
przypiętymi manifestami w czystym checkoutcie, a pełna bramka bajtów i wymiarów
wykonuje się jawnie tam, gdzie `examples/imgs` jest dostępne.

TASK 3 dodał nieaktywny estymator
`board-cell-geometry-v19-multi-point-source-direct-v1`. Wykorzystuje globalne
komponenty, ograniczone hipotezy wspólnych osi 5 × 3 i istniejący guarded
RANSAC, ale projektuje granice oraz 15 komórek z płaszczyzny analizy z powrotem
do oryginalnego JPEG-a. Nie materializuje cropów i nie jest podłączony do
pipeline'u.

Na lokalnym rzeczywistym corpusie automatycznie przeszło `25/27` plansz, a
maksymalny średni błąd czterech narożników wyniósł `6,25 px`. Sekwencja `37`
pozostała fail-closed przy 8 inlierach, a `112` przy 9 globalnych przypisaniach;
bramki 10 wiarygodnych centrów, 9 inlierów oraz pełnego 3 × 5 nie zostały
obniżone.

TASK 4 zamknął osobny checkpoint 100 rzeczywistych stron. Deterministyczna
próbka z 2194 dostępnych stron objęła 900 plansz. Estymator wyemitował 888
geometrii, a 12 plansz skierował fail-closed do przyszłej korekty. Ręczna kontrola
25 arkuszy nie znalazła przesunięcia o wiersz/kolumnę, symbolu poza komórką ani
fałszywego sukcesu. Content-addressed raport ma checksumę
`320c9b1089b1481e8e4eea71c955eaf796c61554391783d2ac34020aa2421691`; pełny
protokół jest w `ai_docs/quality/board-cell-geometry-v19-100-page-audit.md`.
Cropper v18, pipeline, API, baza i UI pozostają bez zmian.

TASK 5 dodał nieaktywny
`board-cell-crops-v19-multi-point-source-direct-fixed-padding-v1`. Adapter
sprawdza cały `BoardCellGeometryEntry` przed pierwszym resamplingiem, stosuje
kanoniczny inset `10/100` i tworzy 15 komórek bezpośrednio z oryginalnego RGB,
po jednym `warpPerspective` na finalny crop. Nie powstaje pośrednia plansza
`500 × 300`, dodatkowy resize ani częściowy wynik po błędzie późnej komórki.
Fingerprint dla aktualnego wejścia modelu `64 × 64` wynosi
`49146bca0f232a8d8e5e744811577b9f9d01a3cf791d31894775dfb5a677195d`.
Rzeczywisty corpus daje `27/27` plansz i `405/405` cropów. Cropper pozostaje
niepodłączony; aktywny v18, pipeline, modele, baza, API i UI nie zostały
zmienione.

TASK 6 podłączył cropper v19 wyłącznie do read-only podglądu ręcznego edytora.
Cztery numerowane uchwyty oznaczają teraz zewnętrzne granice siatki symboli
5 × 3, overlay korzysta z projekcji perspektywicznej, a cztery szare uchwyty
krawędziowe są wyłącznie pochodne i nie wchodzą do payloadu. Endpoint preview
zwraca jeden PNG będący contact sheetem `5 × 3` z dokładnie 15 finalnych cropów
`64 × 64`; nie materializuje planszy `500 × 300`, nie zapisuje plików ani
rewizji. W samym TASK 6 historyczny zapis geometrii został odłączony od edytora,
aby nie pomylić semantyki narożników. Produkcyjny pipeline, aktywny cropper v18,
baza, modele symboli i istniejące decyzje pozostały wtedy bez zmian.

TASK 7 zastąpił aktywną ścieżkę zapisu v1 kontraktem
`manual-board-cell-geometry-v19-append-only-v1`. Preview i zapis używają teraz
tego samego `BoardCellGeometryEntry`, walidatora i source-direct croppera v19.
Zapis tworzy dokładnie 15 nowych, niezmiennych cropów w rewizjonowanym
namespace, a istniejący source-native obraz referencyjny pozostaje bez
dodatkowego przeskalowania.

Checksum decyzji wiąże źródło, pozycję, numer planszy, quad, wersje, oczekiwane
rewizje, checksumę komendy i aktora. Pełna proweniencja oraz 15 source/padded
quadów trafiają do append-only `image_board_geometry_revisions`; historyczne
rewizje v1 pozostają czytelne z `decisionChecksumSha256 = null`. Reviewer
zapisuje tylko aktualnie wygenerowany podgląd, blokuje podwójny submit i
natychmiast pokazuje zwróconą rewizję tej samej planszy ponownie otwartej do
weryfikacji symboli.

TASK 8 aktywował automatyczny v19 wyłącznie jako jawną operację
`Przelicz oczekujące`. Nowy job schema v2 przypina snapshot
`pending-board-cell-recrop-v19-v1`, wszystkie wersje i fingerprinty geometrii
oraz croppera, a także checksumę zaliczonego audytu 100 stron. Historyczne joby
schema v1 nadal wykonują historyczny detektor i cropper v17; pełny pipeline
importu nadal korzysta z v18.

Worker schema v2 bierze istniejący zweryfikowany quad planszy, szacuje pełną
geometrię 3 × 5 i wykonuje dokładnie 15 source-direct cropów v19. Brak pełnego
dowodu pozostawia element w `needsManualGeometry` bez częściowego zapisu.
Źródło jest sprawdzane checksumą i wymiarami oraz dekodowane raz na stronę.
Przed zapisem worker blokuje item i planszę oraz ponownie sprawdza status,
rewizje, źródło, numer, pozycję, geometrię i checksumy. Decyzja człowieka lub
równoległa korekta zawsze wygrywa; `accepted/corrected/rejected`, istniejące
v19, OCR, discovery, staging, modele i katalog symboli pozostają nietknięte.

Preview Admina rozróżnia wszystkie oczekujące, `recalculableBoardCount`, już
aktualne v19 i chronione. Start jest blokowany, gdy nie ma faktycznej pracy.
TASK 8 nie uruchomił żadnego rzeczywistego joba użytkownika i nie rozpoczął
pionów kolejki ani wspólnego Reviewera.

TASK 9 rozpoczął pion stabilnej kolejki wyłącznie od warstwy danych. Migracja
`0049_image_review_queue_projection` tworzy trwałe pozycje per import pod
kluczem `(source_order_index, position_index, review_item_id)` oraz stan z
licznikami `pending/accepted/corrected/rejected` i `queueVersion`. Triggery
PostgreSQL obejmują wszystkie ścieżki zapisu API i workera; status aktualizuje
liczniki bez zmiany topologii, a dodanie lub usunięcie pozycji zmienia wersję.
Istniejące elementy są backfillowane fail-closed i zachowują source-order po
restarcie. Endpointy, kursory, resume, Admin i Reviewer nadal nie korzystają z
nowej projekcji — jest to zakres następnego, osobno zlecanego TASK 10.

TASK 10 przepiął job-local listowanie Reviewera na projekcję 0049. Wszystkie
widoki, keyset cursor v2, poprzedni/następny i wznowienie używają teraz tego
samego klucza `(source_order_index, position_index, review_item_id)`;
`sequence_number` nie wpływa na położenie. Odpowiedź zwraca trwały
`queueVersion`, a kursor jest unieważniany wyłącznie po zmianie topologii, nie
po decyzji zmieniającej status lub liczniki. Liczniki są czytane z
`image_review_queue_states`. OpenAPI i klient zostały wygenerowane ponownie.
First-save-wins, `superseded`, rozróżnienie konfliktów komendy oraz mały bufor
Reviewera pozostają zakresem kolejnych osobno zlecanych zadań.
Read-only smoke największego rzeczywistego importu (`19 746` pozycji,
`19 745 pending`) zwrócił pierwszą pending i oba kierunki nawigacji w około
`72 ms`.

TASK 11 wdrożył first-save-wins dla równoległych decyzji tego samego
`game_id + sequence_number`. Migracja `0050_image_review_first_save_wins`
dodaje status/event oraz trwały licznik `superseded`. Zapis jest serializowany
wyłącznie per numer; atomowa projekcja kanoniczna ma jednego właściciela, a
pozostałe pending zachowują źródło i append-only audyt jako `superseded` bez
zmiany `queueVersion` i bez staging row. Równoległa przegrana komenda zwraca
kontrolowany wynik, a jej exact retry pozostaje idempotentny. Worker używa tej
samej semantyki dla ponownie napotkanego kanonicznego zakresu. Reviewer pokazuje
osobny status i licznik.

TASK 12 rozdzielił konkurencyjność komendy bieżącej planszy od zmian stanu
całej kolejki. Resolution zwraca teraz autorytatywny `queueVersion` i liczniki
odczytane z trwałej projekcji po zapisie. Zmiana sąsiedniego itemu nie blokuje
komendy; rzeczywisty konflikt bieżącego itemu ma stabilny
`IMAGE_REVIEW_REVISION_CONFLICT` z oczekiwaną i aktualną rewizją. Reviewer ufa
snapshotowi serwera i zachowuje UUID idempotencji przy ponowieniu niezmienionej
komendy po niejednoznacznym błędzie transportu.

TASK 13 dodał bounded bufor Reviewera `previous/current/next two`. Każda z
maksymalnie czterech stron nadal pochodzi z osobnego żądania `limit = 1`;
poprzednik i pierwszy następnik są pobierani równolegle, a drugi następnik
sekwencyjnie po własnym kursorze. Przejście po gotowym sąsiedzie nie pokazuje
pełnoekranowego loadingu, a brakujący brzeg jest uzupełniany w tle.

Reviewer prefetchuje również widoczne zasoby trzech sąsiadów, ale nie utrzymuje
pełnej kolejki w React. Autorytatywne liczniki i `queueVersion` z resolution są
propagowane do wcześniej pobranych stron, więc przejście dalej nie przywraca
starego snapshotu. Konflikt topologii podczas prefetchu pozostaje fail-closed;
zwykły błąd transportu zachowuje bieżącą planszę i foreground fallback. API,
OpenAPI, baza, pipeline oraz pion wspólnego Reviewera pozostały bez zmian.

TASK 14 rozpoczął pion wspólnego Reviewera od trwałej warstwy danych i
lifecycle'u `reviewer_work_assignments`. Migracja `0051` zapisuje scope
`game_id + import_job_id`, typ `local/online`, właściciela, fencing token,
heartbeat i wygaśnięcie lease oraz pełne dane zamknięcia. Częściowy unikalny
indeks gwarantuje najwyżej jedno aktywne przypisanie na import; po zamknięciu
można utworzyć następcę bez utraty historii.

Odnowienie wymaga aktualnego, niewygasłego tokenu, a zapis SQL powtarza fencing
condition. Wygasły wpis jest jawnie zamykany jako `lease_expired`. Scope jest
walidowany pod blokadą gotowego image import joba i wymaga istniejącej pozycji
review. Lokalna baza działa na `0051_reviewer_work_assignments (head)`. TASK 14
nie zmienił API/OpenAPI, Admina, Reviewera, sesji dostępowych, procesu Windows,
Quick Tunnel ani limitu trzech przypisań online; są to następne etapy pionu C.

TASK 15 połączył lifecycle assignmentu online z właściwą scoped sesją, nadal
oddzielając oba od procesu Reviewera i Quick Tunnel. Migracja `0052` dodaje
opcjonalny `reviewer_access_session_id`, wymagany dokładnie dla trybu online;
złożony FK obejmujący sesję, grę i import nie pozwala powiązać obcego scope'u.
Jedna sesja należy najwyżej do jednego assignmentu.

Nowy `ReviewerWorkLifecycleService` używa zdrowego loopback Reviewera ponownie
dla pracy lokalnej i online, a kolejne sesje online otrzymują ten sam aktywny
publiczny origin. Każdy import ma osobną sesję i assignment. Zamknięcie pracy
unieważnia wyłącznie jej sesję i nie ma dostępu do globalnego `stop`; nieudane
otwarcie kompensuje utworzenie sesji przez revoke. Lokalna baza działa na
`0052_reviewer_assignment_sessions (head)`. Synchronizacja start/status/stop
między procesami Windows, limit trzech online, `stop-if-unused`, endpointy i UI
pozostają poza TASK 15.

TASK 16 zabezpieczył współdzielony proces Reviewera i Quick Tunnel przed
równoległymi kontrolerami Windows. Zdalny start/status/stop i lokalny start
używają jednego nazwanego mutexu per repozytorium z ograniczonym oczekiwaniem.
Stan schema v2 jest publikowany atomowo dopiero po health checku i wiąże PID z
czasem startu, pełną ścieżką executable, nazwą procesu oraz losowym
`instanceId`; stary stan ani PID użyty ponownie nie pozwala zatrzymać obcego
procesu.

Każda próba startu ma unikalne logi w
`.runtime/reviewer-lifecycle-logs`, a każde wywołanie z API osobny plik wyniku w
`.runtime/reviewer-ingress-controller-results`. Wewnętrzny compare-and-stop po
`instanceId` stanowi fencing dla następnego etapu. Publiczne API, baza, Admin i
Reviewer nie zmieniły się. Limit trzech prac online oraz decyzja
`stop-if-unused` na podstawie ostatniego aktywnego assignmentu pozostają w
TASK 17.

TASK 17 domknął domenowy lifecycle współdzielonego ingressu. Online capacity
jest ograniczona do trzech różnych aktywnych importów i serializowana
transakcyjnym advisory lockiem PostgreSQL; local assignment nie zajmuje limitu.
Sprawdzenie istniejącego scope'u i limitu odbywa się przed ensure-running oraz
utworzeniem scoped sesji, więc odrzucona czwarta praca nie pozostawia sesji ani
nie uruchamia dodatkowego procesu.

Zamknięcie jednego assignmentu odwołuje wyłącznie jego sesję. Ostatni online
close oraz jawne lazy recovery wygasłych lease'ów używają compare-and-stop po
`instanceId` z TASK 16. Blokada capacity obejmuje także ensure-running i zapis,
dlatego równoległy open nie otrzyma linku do tunelu zatrzymywanego przez close.
Rzeczywisty test czterech transakcji PostgreSQL dał dokładnie trzy sukcesy i
jeden `REVIEWER_ASSIGNMENT_ONLINE_LIMIT_REACHED`. Publiczne endpointy, OpenAPI,
Admin i Reviewer pozostały bez zmian w TASK 17.

TASK 18 wystawił typowany, assignment-scoped kontrakt list/open/heartbeat/close
i przepiął na niego sekcję `Zatwierdzanie plansz`. Select nadal pokazuje gotowe
importy i ich liczniki, a pod nim widoczny jest stan wybranego scope'u oraz lista
wszystkich aktywnych prac gry. Import bez assignmentu oferuje `Otwórz lokalnie`
oraz `Utwórz link online`; aktywne udostępnienie ma własny stop, który nie
wywołuje globalnego endpointu tunelu.

Pierwszy open online zwraca kod jednorazowo. Lista, reload i idempotentne
ponowienie nie zwracają kodu, bearer tokenu, fencing tokenu ani identyfikatora
sesji. Wygenerowany klient OpenAPI dodaje dokładne high-impact targety per import
i assignment. Celowane testy HTTP potwierdzają idempotencję, listę bez sekretów,
heartbeat oraz niezależny close. Pełny zestaw API daje `393 passed, 30 skipped`,
klient `39 passed`, Admin `211 passed`; produkcyjny build Admina, OpenAPI,
typecheck TypeScript, Ruff oraz ograniczony mypy zmienionej warstwy domenowej
przechodzą. Końcowy rzeczywisty scenariusz wielu scope'ów oraz pomiar cold/warm
stanowiły osobny checkpoint po TASK 18 i zostały ukończone w TASK 19.

TASK 19 zamknął checkpoint współdzielonego Reviewera. Izolowany E2E potwierdza
`3 online + 1 local`, idempotentny równoległy open, reload bez sekretów oraz
stop dopiero po ostatnim online assignmentcie. Rzeczywisty odbiór wykorzystał
wszystkie trzy dostępne gotowe importy jako `2 online + 1 local`: cold start
wyniósł `13,396 s`, warm reuse `1,243 s`, oba linki użyły jednego originu i
jednego procesu. Obcy import oraz publiczne endpointy stagingu, assignments i
storage zwróciły `403`; Admin nie był wystawiony.

Odbiór wykrył i naprawił dwa błędy środowiskowe. Local assignment po restarcie
API jest gotowy także przy prawidłowym stanie tunelu `stopped`. Tożsamość
procesu Windows zachowuje pełny fencing, ale ścieżkę executable odczytuje z
ograniczonym retry przez `Process.Path`, `MainModule` i WMI. Health check nowego
Quick Tunnel jest odporny na lokalny negatywny cache DNS dzięki ograniczonym
fallbackom `1.1.1.1`, `8.8.8.8` i Cloudflare DNS-over-HTTPS; połączenie po
adresie nadal weryfikuje hostname, SNI i certyfikat TLS. Po teście nie pozostał
aktywny assignment, cloudflared ani testowy plik cookie. TASK-0249 jest
ukończony.

## TASK-0256 — automatyczna geometria z korektą odroczoną

Preflight `page-geometry-preflight-v2-auto-anchor` zachowuje dotychczasowe
twarde bramki rejestracji, a następnie wykonuje najwyżej dwa ponowienia dla
nierozpoznanych stron. Każdy przebieg używa maksymalnie 21 pełnych wyników 3 × 3
spełniających ostrzejszą bramkę jako dodatkowych perspektyw. Manifest schema v2
zapisuje promocje i liczbę rozwiązanych stron; manifesty v1 pozostają czytelne.

Import z częściowym manifestem kopiuje i przetwarza wyłącznie `registered`.
`review_required` pozostają w trwałym stagingu i nie docierają do croppera ani
symbol inference. Admin automatycznie tworzy lub odzyskuje preflight po
pokazaniu raportu, pokazuje nierozpoznane strony jako odroczone i ukrywa ich
ręczną korektę pod sekcją „zostaw na koniec”. Wygasający 15-minutowy token
legacy nie usuwa już sfinalizowanego browser stagingu.

## Wersja 0.9 — fundament domenowy geometrii i jakości symboli

- `Weryfikacja symboli` nie pobiera już domyślnej strony 500 cropów po samym
  wejściu do zakładki. Operator jawnie zatwierdza grę, symbol, stan oraz limit
  `1..500`; po zatwierdzeniu parametry są zablokowane do akcji `Zmień wybór`, a
  keysetowa paginacja i zakres strony używają zatwierdzonego limitu.

TASK-0304 rozpoczął tor 0.9. Commit `v0.9.1` dodaje wyłącznie czystą domenę:
topologię planszy wyprowadzaną z wersji reguł, wyliczany stan walidacji
geometrii oraz niezależne osie etykiety, jakości i proweniencji cropa.

Recrop zatwierdzonego pola zachowuje decyzję logiczną, ale nowy crop ma stan
`changed_since_approval` i nie kwalifikuje się do treningu. `grid_issue` wraca
po recropie jako pending bez problemu jakości, natomiast `unreadable` może być
rozwiązane realnym symbolem albo domenowym `?` i nadal pozostaje nietreningowe.
Agregacja planszy wymaga zatwierdzonej geometrii oraz kompletnej liczby komórek
wynikającej z topologii.

Commit `v0.9.2` przygotowuje addytywną migrację
`0073_topology_geometry_crop_provenance`, zgodne modele ORM oraz bounded,
idempotentny backfill. Schemat zachowuje `has_grid_issue` i zapisuje równolegle
nowe `quality_issue`; zatwierdzone komórki otrzymują dokładną tożsamość cropa,
a plansze `accepted/corrected` zatwierdzenie bieżącej geometrii. Pending z
pipeline'u pozostaje do walidacji. Skrypt operatorski utrwala checkpoint po
każdej transakcji obejmującej maksymalnie 200 plansz i raportuje niespójności
bez heurystycznej naprawy.

Cykl upgrade/downgrade 0073 przeszedł na izolowanej bazie testowej. Robocza
baza użytkownika nadal pozostaje na `0072`; indeksy i backfill 0073 nie zostały
uruchomione podczas aktywnego przetwarzania. Wymagają osobnego checkpointu SQL
i kontrolowanego okna. API, worker, Admin i Reviewer nie zostały jeszcze
przełączone na nowy workflow.

Commit `v0.9.3` usuwa stałą 15 ze wspólnej ścieżki geometrii i croppera.
Snapshot nowego importu, fingerprint croppera i manifest odroczenia przypinają
topologię oraz wersję reguł, a `recognized_boards` zapisuje użyte wymiary.
Ręczna geometria działa dla dowolnego `rows × columns` w row-major i wykonuje
pojedynczy finalny resampling każdej komórki. Automatyczny v20 pozostaje
wersjonowanym adapterem 3 × 5 i dla innych wymiarów zwraca
`IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED`. Historyczne artefakty bez topologii
zachowują dotychczasowy fingerprint i interpretację 3 × 5.

Commit `v0.9.4` spina zatwierdzenie geometrii, stan komórek i materializowaną
decyzję planszy w jednej transakcji. Agregacja wymaga zatwierdzonej bieżącej
rewizji geometrii oraz kompletnego zestawu `rows × columns`; do aktualizacji
canonical, stagingu, kolejki, statusu joba i szybkiej projekcji wyszukiwania
wykorzystuje istniejący mechanizm pełnej decyzji.

Recrop zwykłego zatwierdzonego pola zachowuje etykietę i tożsamość poprzednio
zatwierdzonych pikseli, dlatego nowy crop jest `changed_since_approval` i nie
trafia do treningu. Pole oznaczone `grid_issue` po recropie wraca jako
`pending` bez problemu jakości. Ręczny zapis geometrii zatwierdza utworzoną
rewizję, zapisuje append-only event i może ponownie domknąć planszę tylko przy
komplecie logicznych etykiet. Rewizja katalogu wzrasta najwyżej raz w tej samej
transakcji. Publiczne endpointy kolejki geometrii pozostają zakresem TASK 5.

Commit `v0.9.5` dodaje lokalne Admin API game-wide kolejki walidacji geometrii.
Widoki `needs_validation`, `needs_correction` i `all` używają bounded keysetu
`(sequence_number, review_item_id)`, opcjonalnego scope importu i wyłącznie
bieżącego właściciela z `image_board_search_fast_documents`. Opaque cursor jest
związany z grą, filtrem, importem i kierunkiem.

Źródło jest serwowane wyłącznie po ponownej kontroli ścieżki oraz SHA-256.
Zatwierdzenie, preview i zapis wiążą rewizję decyzji i geometrii, checksumę i
wymiary źródła oraz snapshot topologii. Aktor zapisu pochodzi z lokalnego
kontekstu API. Nowa odpowiedź rewizji nie dziedziczy historycznego limitu 15:
zwraca dynamiczne `rows × columns` i oblicza indeks row-major z bieżącej liczby
kolumn. OpenAPI i generowany klient TypeScript są zgodne. UI pozostaje TASK 6.

Commit `v0.9.6` przełącza lokalnego Reviewera na `Zatwierdzanie cięcia siatki`.
Widok pobiera po jednej pozycji bounded keysetem, ma filtry `Do walidacji`, `Do
poprawy`, `Wszystkie`, checksum-bound oryginał z canvasowym overlayem oraz
zatwierdzanie `Enter`/`F` z blokadą podwójnego zapisu i automatycznym przejściem.

Edytor przyjmuje cztery punkty LT/PT/PD/LD, pozwala przeciągać narożnik albo
całą siatkę, cofać i resetować szkic oraz generuje preview zależne od
`rows × columns`. Zapis używa source-direct endpointu TASK 5 i jednocześnie
zatwierdza nową rewizję. Nie edytuje symboli i nie tworzy pliku overlay.
Zdalny Reviewer pozostaje na ograniczonej ścieżce operacyjnej; lokalny
fallback był czasowy i zostaje usunięty przy końcowym cutoverze TASK 13.

Commit `v0.9.7` rozdziela w `Weryfikacji symboli` dwa problemy jakościowe.
`Zła siatka` zapisuje `quality_issue = grid_issue` i kieruje planszę do kolejki
geometrii. `Nieczytelny symbol` zapisuje `quality_issue = unreadable`, pozostawia
przypisaną etykietę wyłącznie jako audyt i nie pojawia się w kolejce geometrii.
Obie akcje są checksum-bound, działają bezpośrednio dla jednego cropa oraz przez
trwałą operację masową dla większego zaznaczenia.

Lista API zwraca jakość, logiczne `isUnknown` oraz stan proweniencji cropa.
Admin pokazuje odpowiednie badge'e, a po sukcesie usuwa targety z bieżącej
strony. Źródło kohort symboli wymaga teraz `quality_issue IS NULL`, dzięki czemu
nieczytelny crop nie trafia do treningu. Migracja 0073 uwzględnia akcję
`mark_unreadable` w constraintcie append-only eventów; cykl migracji i dwa
scenariusze transakcyjne przeszły na izolowanej bazie PostgreSQL.

Commit `v0.9.8` dodaje w grze sekcję `Weryfikacja symbolu na planszy`.
Bounded kolejka `Do ustalenia / Wszystkie nieczytelne` wybiera wyłącznie
bieżącego właściciela logicznej planszy i renderuje komplet komórek według
snapshotu topologii. Operator rozwiązuje nieczytelne pole aktywnym symbolem
albo domenowym `?`; request jest związany z rewizją oraz dokładną tożsamością i
checksumą cropa.

Rozwiązane pole pozostaje `quality_issue = unreadable`, więc słaby crop nigdy
nie staje się treningowy. Ostatnie pole domyka planszę atomowo przez istniejący
canonical flow. Dla `?` szybki właściciel i audyt pozostają aktywne, ale staging
datasetu jest celowo pomijany do TASK 10, który wprowadzi sentinel 0, migrację
0074 i snapshot v4. Test izolowanego PostgreSQL potwierdził reopen, recrop,
rozwiązanie unknown, canonical oraz brak nieprawidłowego stagingu.

Commit `v0.9.9` wersjonuje wyszukiwanie jako
`partial-board-ranking-v2-unknown-missing-evidence`. Edytor wzoru pozwala
jawnie wstawić `?`, zachowuje je w undo/reset i wizualizacji, lecz do API wysyła
wyłącznie znane symbole. API akceptuje także literalne `cell=index:?` od innych
klientów i usuwa je przed rankingiem; wzór bez znanego symbolu kończy się
`BOARD_SEARCH_QUERY_EMPTY`.

Zapisane unknown pozostaje w szybkiej projekcji jako brak dowodu. Nie daje
punktu, exact match ani mismatch, a denominator obejmuje wyłącznie znane pola
zapytania. Kolejność remisów w domenie i SQL pozostaje zgodna: score, exact,
ważone alternatywy, mniej sprzeczności, zatwierdzony status, sekwencja i UUID.

Commit `v0.9.10` wprowadza sentinel `mobileCode = 0` wyłącznie dla trwałych
layoutów. Migracja 0074 dopuszcza zero w stagingu, imporcie i datasetach oraz
usuwa constraint stałej liczby 15 komórek ze stagingu; walidacja aplikacyjna
pozostaje zależna od `rows × columns`. Katalog symboli i plansza użytkownika
nadal odrzucają zero.

Nowe snapshoty produkcyjne mają schema v4 i deklarują
`unknown_layout_mobile_code = 0`. Aktualny mobile czyta schema v3/v4 i renderuje
zero jako `?`. `payout-v3-unknown-prefix-stop` kończy prefiks na pierwszym
unknown, zachowując kwalifikującą wygraną sprzed niego i ignorując sufiks.
Historyczne joby payout-v2 pozostają obsługiwane do replayu.

Commit `v0.9.11` uszczelnia źródło kohort treningowych symboli po recropie.
Nowa kohorta `verified-symbol-cell-training-cohort-v3-crop-provenance` wymaga
zgodności bieżącego `cropSampleId`, checksummy i rewizji geometrii z dokładną
tożsamością cropa zatwierdzonego przez człowieka. Plik jest ponownie
weryfikowany przed materializacją manifestu. Historyczne manifesty v1 i v2
pozostają odtwarzalne, ale nie są tworzone przez bieżący workflow.

Preview jakości raportuje wykluczenia `unknown`, `unreadable`, `grid_issue`,
`changed_crop` i `missing_asset`. Kohorta geometrii korzysta wyłącznie z
bieżącego właściciela logicznej planszy oraz zatwierdzonej rewizji geometrii;
nie zależy od statusu ani treści etykiet symboli. Nie zmieniono architektury
modelu ML, nie uruchomiono treningu ani operacji na danych użytkownika.

Commit `v0.9.12` kończy runtime'owy cutover wyszukiwania plansz na
`image_board_search_candidates` i `image_board_search_fast_documents`.
Synchronizator nie zapisuje już starej szerokiej projekcji ani tekstowych
tokenów. `quality_issue` jest jedynym trwałym źródłem problemu jakości cropa;
publiczne `hasGridIssue` pozostaje polem wyliczanym dla zgodności kontraktu.

Migracja 0075 usuwa legacy tabelę, tokeny, GIN-y i bool jakości. Jej downgrade
odtwarza dane deterministycznie z bieżących kandydatów i fast documents.
Dodano read-only raport rozmiarów przed/po. Migracja została sprawdzona na
izolowanym PostgreSQL, ale nie została wykonana na bazie użytkownika; przed tym
wymagany jest osobny checkpoint. Nie uruchomiono `VACUUM FULL` ani operacji na
plikach obrazów.

TASK-0320 domyka kontrakt końcowej, częściowej strony ręcznej selekcji. Lokalny
Admin i operator-local Reviewer przyjmują opcjonalny `sequenceUpperBound`,
zapisują zakres `start..min(start+8, upperBound)` i zatrzymują dalsze decyzje po
osiągnięciu granicy. Cofnięcie ostatniej decyzji ponownie otwiera sesję.

Bieżący writer materializuje schema v2 w zachowanym pliku
`manual-image-selection-output-v1.json`; wersja zawiera granicę, stan terminalny
i `activeBoardCount`, natomiast reader nadal wznawia schema v1 jako pełne strony
dziewięciu plansz. Read-only skrypt diagnostyczny raportuje propozycję v2 dla
niespójnych historycznych nazw bez zmiany plików. Preflight `seq_*` blokuje
numery przekraczające `games.expected_layout_count`.

TASK-0321 wprowadza dualny kontrakt tożsamości komórki bez migracji danych.
Historyczne `logical-cell-v1` i `render-id-v1` pozostają bitowo niezmienione.
Nowe `logical-cell-v2` wiąże komórkę z wystąpieniem
`importJobId + fileExecutionKey`, fingerprintem przypiętej topologii, slotem
planszy oraz pozycją komórki. `render-id-v2` dodatkowo wiąże bieżącą geometrię,
padding, interpolację i rozmiar wyjścia.

Automatyczny pipeline oraz ręczny source-direct preview/save wyprowadzają
occurrence z tego samego rekordu źródła. Render spec v2 zapisuje równolegle
identyfikatory v1/v2, occurrence i fingerprint topologii. Bieżąca kolumna
`logical_cell_key` nadal przechowuje v1; addytywna migracja, backfill i cutover
indeksowanych odczytów pozostają osobnym kolejnym zadaniem.

TASK-0322 dodaje wyłącznie czysty kontrakt
`symbol-verification-outcome-v2`. Wyniki `unassigned`, `unknown`, `unreadable`,
`grid_issue`, `requires_review` i `verified_symbol` są rozłączne, a tylko
ostatni może posiadać realne `assigned_symbol_id`. Modelowa predykcja pozostaje
sugestią; `?` jest reprezentacją UI i nie występuje w enumie ani assignment.

Deterministyczny adapter interpretuje obecne pola legacy bez zmiany bazy.
Pending wynik modelu staje się `requires_review` albo `unknown`, błąd siatki i
nieczytelność pozostają osobne, a zatwierdzony realny symbol przechodzi jako
`verified_symbol`. Podejrzane pending przypisanie człowieka oraz zatwierdzony
NULL bez unreadable są fail-closed. Addytywna kolumna, raport/backfill, API i UI
pozostają po późniejszym schema ownership review.

TASK-0323 dodał read-only feasibility spike istniejącego Structured OpenCV.
Wersjonowany manifest wiąże rzeczywiste JPEG-i i ich SHA-256, a runner zapisuje
wyłącznie regenerowalne JSON-y diagnostyczne, source overlaye i contact sheets.
Nie zmieniono bazy, API, OpenAPI, canonical ownership, pipeline'u ani trybu
rolloutu gry.

Ograniczony przebieg objął 43 zdjęcia i 387 plansz jednej gry. Korpus jest
formalnie niewystarczający: nie zawiera drugiej gry, częściowych stron,
rozmycia ani trzech false-success. Wynik techniczny pokazał 323/324 poprawnych
w granicy eksperymentalnej projekcji znanego układu oraz 380/382 lokalnych
doprecyzowań z oracle. Generyczna inicjalizacja bez profilu nie zwróciła
finalnych quadów, a bieżące hard gates odrzuciły wszystkie plansze, głównie z
powodu braku kompletnego dowodu linii wewnętrznych.

Rekomendacja pozostaje warunkowa: rozszerzyć wyłącznie read-only corpus i
zbadać połączenie ramki zewnętrznej, znanego układu oraz regularności. Wynik nie
zalicza bramki 95/98 i ma `rolloutAuthorized=false`. Raport znajduje się w
`ai_docs/quality/STRUCTURED_GEOMETRY_FEASIBILITY_SPIKE_V1.md`.

TASK-0324 zakończył przegląd własności schematu geometrii wirtualnej bez zmian
bazy i kodu wykonawczego. Jedynym właścicielem finalnego payloadu quadów jest
`image_source_geometry_revisions.board_geometries`, a bieżąca plansza wybiera
go przez `recognized_boards.source_geometry_revision_id + position_index`.
Pole `recognized_boards.board_geometry` pozostaje projekcją zgodnościową,
board revisions przechowują komendę i audyt, a observations dokładną
proweniencję renderu.

Active slots oraz snapshot topologii należą do source revision. Rollout
pozostaje osobnym stanem operacyjnym i jest zamrażany w input joba. Następne
zadanie może przygotować wyłącznie addytywną migrację po 0082/0083: trwałość
topology/attestation fingerprint, logical-cell-v2, outcome v2 i związanie
rollout readiness z dokładnym wejściem walidacji. Nie wykonano backfillu,
cutoveru, operacji na danych ani zmiany progów geometrii. Pełna mapa znajduje
się w `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`.

TASK-0325 dodał migrację 0084 po faktycznym headzie 0083. Schemat nullable
utrwala fingerprint topologii i attestation, logical-cell/render-identity v2,
jawny outcome weryfikacji z osobnym `verified_symbol_id_v2` oraz dokładne
związanie walidacji rolloutu z rewizją, input checksum i jobem. Legacy
`assigned_symbol_id`, read pathy oraz API pozostają bez zmian.

Nowe automatyczne i ręczne ścieżki virtual wykonują dual-write. Bounded
diagnostyka tylko odczytuje maksymalnie 500 historycznych kandydatów i nie
mapuje stanów niejednoznacznych. Migracji 0084 ani backfillu nie uruchomiono na
bazie użytkownika; osobne zadanie musi wykonać resumowalny backfill oraz
cutover dopiero po raporcie zgodności.

TASK-0326 rozszerzył istniejący trwały `image_geometry_rollout_backfill` o
metadata-only backfill kontraktów dodanych przez 0084. Job w general lane
przetwarza maksymalnie 100 source images w transakcji, wznawia pracę z trwałego
kursora i zapisuje osobne liczniki source revisions, observations, current
review cells oraz frozen verified training cells.

Historyczny render spec wraz z occurrence i przypiętą topologią daje dokładne
logical/render identity v2 bez dekodowania obrazu. Bieżący outcome jest
uzupełniany tylko dla jednoznacznego stanu; sugestia modelu pozostaje
`requires_review`, a niejasność lub konflikt istniejącej wartości blokuje
`ready`. Finalizacja ponownie sprawdza nowe źródła oraz brakujące pola.
Append-only eventy, etykiety człowieka, canonical ownership i publiczne read
pathy pozostają niezmienione. Backfillu ani cutoveru nie uruchomiono na danych
użytkownika.

TASK-0327 wzmacnia kontrakt source-direct renderera bez zmiany pikseli i
rolloutu. Nowy `virtual-cell-render-spec-v3-complete-provenance-v1` jawnie
przechowuje occurrence źródła, snapshot topologii, wersję geometrii,
normalized-pixel checksum oraz wersję checksummy RGB. Konstruktor renderu
niezależnie przelicza logical-cell v1/v2 i render identity v1/v2, więc
wewnętrznie niespójna proweniencja kończy się fail-closed.

Checksum specu i checksum pikseli pozostają rozłączne. Skorygowano preview,
który wcześniej wymagał checksummy wynikowych pikseli wewnątrz specu, mimo że
produkcyjny writer zapisywał ją osobno. Dokładna parity z cropperem v19, jeden
warp na komórkę, walidacja całej partii przed pierwszym warpem oraz brak
trwałych PNG pozostają zachowane. Nie zmieniono Structured OpenCV, bazy,
canonical ownership ani trybu rolloutu.

TASK-0328 dodaje wyłącznie eksperymentalny
`structured-opencv-geometry-config-v2-multi-evidence-experimental-v1`.
Konfiguracja jest deterministycznie checksummowana, dobiera skalę adaptacyjnie,
wyraża reprojekcję względem przekątnej komórki i dopuszcza jawne profile gry.
LSD nie jest wyłączną bramką: mocna ramka, znany układ i regularność mogą
utworzyć kandydata bez LSD, ale samo LSD bez niezależnych rodzin dowodu kończy
się fail-closed. Homografia, source support, alignment, kolejność i overlap
pozostają twardymi invariantami.

V2 ma zawsze `experimental_measurement_only`, `activationAllowed=false` i
wymaga rozłącznych źródeł strojenia oraz ewaluacji. Nie podłączono jej do
produkcyjnego engine'u, pipeline'u, jobów ani rolloutu; v1 i jego fingerprinty
pozostają bez zmian. Rozszerzony read-only corpus wymagany przez D-266 nadal
nie jest kompletny.

TASK-0329 podłącza config Geometry v2 wyłącznie jako diagnostyczny sidecar
nowych jobów `structured_shadow`. Addytywny snapshot rolloutu v2 zamraża pełny
config i checksumę; historyczny snapshot v1 oraz legacy fingerprint pozostają
niezmienione. Worker mierzy rzeczywiste sygnały na finalnym quadzie Structured
OpenCV v1 i zapisuje osobny, checksummowany
`structuredGeometryCandidateV2` w checkpointach detekcji oraz geometrii
komórek.

Kandydat deklaruje `measurement_only`, `activationAllowed=false` i brak
własności geometrii. Nie steruje cropami, inferencją, review, canonical ani
treningiem. Brak finalnego quada albo awaria pomiaru daje jawne
`not_evaluated`, a nie sztuczną decyzję. Nie zmieniono trybu żadnej gry, nie
uruchomiono migracji, backfillu ani operacji na danych. Korpus D-266 pozostaje
niekompletny i rollout produkcyjny nadal nie jest autoryzowany.

TASK-0330 przywrócił zielony pełny typecheck repozytorium bez zmiany zachowania
produktu. Browserowy upload zależy od minimalnego, statycznie sprawdzalnego
portu capacity guarda, a liczniki z JSONB, checkpointów i manifestów storage są
dekodowane fail-closed jako nieujemne liczby całkowite. Doprecyzowano też
granice typów iteratorów manifestów, opcjonalnych crop artifacts i wyników
OpenCV oraz usunięto niepotrzebne wyciszenia mypy.

Pełny `python:typecheck` przechodzi dla 470 plików źródłowych, Ruff jest zielony,
a 70 skoncentrowanych testów API, workera, storage i geometrii przechodzi.
Nie zmieniono API, OpenAPI, schematu bazy, UI ani polityki storage.
### TASK-0331 — bezpieczny silnik importu per gra

Dodano trwałą politykę nowych importów osobno dla każdej gry. Stabilny preset
v20/v19 pozostaje dostępny dla gry historycznej, a nowa gra może używać
strukturalnej geometrii wyłącznie w trybie shadow. Polityka jest chroniona
preview tokenem i rewizją oraz unieważnia preflight po zmianie.

### TASK-0332 — cold-start structured shadow

Usunięto cykliczną zależność pierwszego importu nowej gry od profilu geometrii
budowanego z wcześniej zatwierdzonych plansz. Browser preflight zwraca teraz
`geometryPreflightRequired`: stabilny `verified_v19` nadal wymaga zakończonego,
checksum-bound preflightu geometrii, natomiast `structured_shadow` pomija ten
etap i nie przyjmuje legacy manifestu. Admin pokazuje jawny stan cold-start i
odblokowuje start raportu bez tworzenia joba kończącego się
`IMAGE_PAGE_GEOMETRY_PROFILE_EMPTY`.

### TASK-0333 — wybór silnika przed uploadem

Picker polityki silnika jest teraz widoczny przed wskazaniem folderu oraz
gotowego stagingu. Admin nie pozwala rozpocząć uploadu, dopóki nie odczyta
ustawienia gry. Zmiana polityki przy aktywnym stagingu automatycznie odtwarza
raport, dzięki czemu nowa gra może wybrać `structured_shadow` przed próbą
utworzenia historycznego preflightu `verified_v19`.

### TASK-0334 — etykieta jobów structured shadow

Historia importów rozpoznaje teraz rollout `structured_shadow` przed snapshotem
stabilnego primary. Job zawierający oba kontrakty pokazuje
`0.10 — nowy silnik w cieniu · primary v20/v19` i nie może zostać uznany za
zgodny z polityką `verified_v19`. Istniejące joby nie wymagają ponownego
przetwarzania; poprawka dotyczy interpretacji ich niezmiennego payloadu.

### TASK-0335 — bootstrap geometrii strony dla nowych gier

Usunięto false-success cold-startu, w którym `structured_shadow` uruchamiał
primary v20/v19 bez manifestu geometrii i kończył wszystkie źródła na
`board_detection`. Oba presety wymagają teraz ukończonego preflightu. Nowa gra
może utworzyć go bez historycznego profilu: pierwszy przebieg tworzy kolejkę
korekty, a ręczny override jednej strony staje się kotwicą kolejnego
preflightu. Tylko źródła z kompletną geometrią trafiają do croppera i
inferencji; Geometry v2 pozostaje pomiarem shadow.

### Usuwanie pustych stagingów — v0.10.35

Naprawiono rozjazd, w którym `Usuń nieużywany staging` kasowało wyłącznie pliki
uploadu, pozostawiając puste joby w `Zatwierdzaniu cięcia siatki`. Usunięcie
jest teraz atomowo koordynowane z bazą i obejmuje puste preflighty/importy,
źródła bez plansz oraz niewspółdzielone wykonania pipeline'u. Istnienie
jakiejkolwiek planszy, review, aktywnego joba albo chronionej referencji blokuje
operację. Z lokalnej bazy usunięto zweryfikowane pozostałości stagingów gry
`7777` z `10:09` i `10:16`; nie miały plansz, review ani wpisów canonical.

### TASK-0371 — podgląd ręcznej korekty geometrii strony

Edytor korekty strony utrzymuje komplet `expectedBoardCount` propozycji:
częściowo wczytane quady są zachowane, a brakujące pozycje otrzymują roboczą
geometrię do jawnej korekty. Na każdym kompletnym quadzie widoczne są
projektowane granice komórek 5 × 3 zgodne z rektyfikacją planszy.

Po rozpoczęciu trybu `Wyznacz 4 narożniki` albo `Wyznacz N plansz osobno`
poprzednia nakładka systemu jest ukrywana. Tryb osobnych plansz pokazuje jedynie
quady ukończone w bieżącej operacji i ich linie 5 × 3. Zmiana jest wyłącznie
narzędziem ręcznej korekty; nie promuje `structured_default`, nie zmienia
progów Structured OpenCV ani zaakceptowanej bramki cutoveru v0.10.
