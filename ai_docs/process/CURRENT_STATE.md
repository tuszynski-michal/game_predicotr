---
title: Current project state
status: active
last_updated: 2026-08-18
---

# Current State

Tor `0.5` został zamknięty. Ostatni commit implementacyjny to `v0.5.15`, a
commit dokumentacyjny zamknięcia otrzymuje `v0.5.16`. Następny tor rozpoczyna
się od `v0.6.0`; jego pierwszy pion dotyczy workspace’ów `Gry` i
`Import layoutów`.

## Phase

`Version 0.6 implementation: source-native Layout Import quality and completeness`

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
zdjęcia, Tab pomija zakres przy tym samym zdjęciu, a Ctrl+Z usuwa wyłącznie
zweryfikowany plik zapisany przez tę sesję. Implementacja jest gotowa do testu
manualnego w przeglądarce; zadanie `0246` pozostaje `in_progress` do akceptacji.
