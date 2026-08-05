---
title: Current project state
status: active
last_updated: 2026-08-05
---

# Current State

## Phase

`Version 0.4 in development — TASK-0151–0156, TASK-0165–0170 and TASK-0172 complete; TASK-0157 and TASK-0171 in progress; owner acceptance 0.2/0.3 deferred`

## Aktywne tory wydań

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
- TASK-0143–0150 obejmują skumulowane kohorty per gra, panel jakości,
  source-aware dataset, trwały trening, bramkę ONNX, kontrolowaną aktywację,
  przeliczenie wyłącznie `pending` oraz odbiór dwóch iteracji,
- `accepted`, `corrected` i `rejected` są nienaruszalnymi decyzjami człowieka;
  żadna automatyczna operacja modelu nie może ich przeliczyć ani zmienić,
- TASK-0076 realizuje pełny import około 500 000 rzeczywistych layoutów na grę,
- nowe gry, wielogrowy snapshot/APK, benchmarki pełnego pipeline'u i
  TASK-0080–0089 domykają skalę oraz hardening 0.5.

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

- PostgreSQL ma w repozytorium head
  `0030_image_selection_optional_exceptions`; migracja pozwala zapisać
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
- TASK-0143–0150 są zaplanowane w M6.6 wersji 0.5; nie rozpoczynają się przed
  przejściem bramki selektora 0.4 i spełnieniem warunków wejścia M6.6,
- TASK-0151–0156 są ukończone. Syntetyczna część TASK-0157 jest zaliczona, ale
  rzeczywiste runy ujawniły fragmentację i koszt pełnego dekodowania, geometrii
  oraz OCR. Decyzja ma status `optimize`. TASK-0165–0171 implementują i mierzą
  range-free `fast-image-selector-v9`; dopiero po ich zakończeniu manualny
  odbiór właściciela pozostanie końcową bramką M7.0. Nie zastępuje odbioru 0.2
  ani 0.3,
- masowy import, nowe gry i pełne benchmarki danych nie mogą wejść do bramki 0.2.

## Next recommended task

Kontynuować TASK-0171 od końcowej bramki: uzupełnić naturalny korpus z 32 079 do
dokładnie 40 000 zdjęć, wykonać jeden kontrolowany profil i przedstawić czas,
throughput, peak RSS oraz jakość właścicielowi do decyzji `accepted | optimize`.
Krótkie bramki 500 i 3000 są zaliczone. Nie aktywować v9 ani nie uzupełniać
brakujących 7921 pozycji sztucznymi duplikatami przed tą decyzją.
Nie otwierać automatycznej publikacji 500 000 layoutów bez bramki
`massImportAllowed`. Odbiory Admina 0.2 i Mobile 0.3 pozostają niezależne.

## Do not start yet

- automatycznej publikacji pełnych 500 000 layoutów przed kontrolą pierwszych
  partii i jawnym otwarciem `massImportAllowed`,
- dodawania i testowania kolejnych gier,
- wielogrowego wydania mobilnego,
- pełnej macierzy urządzeń i hardeningu przypisanego do 0.5,
- Celery/Redis, mikroserwisów, chmury, Google Play lub publicznego Admin API.
