---
title: Architecture decision log — index
status: active
last_updated: 2026-10-09
---

# Decision Log

Ten plik jest **indeksem** decyzji i obowiązkowym odczytem startowym. Pełne wpisy
(kontekst, alternatywy, konsekwencje) leżą w
[decisions/DECISION_LOG_2026.md](decisions/DECISION_LOG_2026.md) w niezmienionym
kształcie, z nagłówkami `## D-NNN — …` (kotwice `#d-nnn-…` jak dawniej).

Reguły:

- Czytaj indeks poniżej oraz pięć najnowszych wpisów w pełnej postaci na końcu
  tego pliku. Pełny wpis otwieraj dopiero, gdy `Relevant docs` taska go wskazuje
  albo gdy indeks nie wystarcza do oceny sprzeczności.
- Indeks obejmuje 534 wpisów. Ten plik zawiera wiersze od D-359 wzwyż
  (177 wierszy); starsze (357 wierszy) są w
  [decisions/DECISION_INDEX_ARCHIVE.md](decisions/DECISION_INDEX_ARCHIVE.md).
  Numery D-416..D-429 występują w dwóch torach (kolizja numeracji); wiersze
  rozróżnia tytuł i kotwica.
- Nowa decyzja: dopisz pełny wpis na początku
  `decisions/DECISION_LOG_2026.md`, dodaj wiersz na górze tabeli poniżej, podmień
  najstarszą pełną kopię w sekcji „Najnowsze wpisy” na nowy wpis, a gdy cały
  ten plik zbliża się do limitu 100 000 B (sprawdza go `docs:check`), przenieś
  najstarsze wiersze indeksu do `decisions/DECISION_INDEX_ARCHIVE.md`. Spójność sprawdza
  `python scripts/check_decision_links.py` (część `npm run docs:check`).
- Hierarchia źródeł prawdy (`AGENTS.md`) odnosi się do pełnych wpisów; indeks to
  tylko ich skrót.

## Indeks

| Nr | Tytuł | Status | Data | Jedno zdanie |
|---|---|---|---|---|
| [D-537](decisions/DECISION_LOG_2026.md#d-537--wypłata-planszy-w-serii-supergry-wynik-prowizoryczny-i-koszt-per-pozycja) | Wypłata planszy w serii supergry, wynik prowizoryczny i koszt per pozycja | accepted | 2026-10-09 | plansza na pozycji objętej opublikowaną serią supergry jako jej spin jest liczona oceną planszy serii… |
| [D-536](decisions/DECISION_LOG_2026.md#d-536--serie-supergry-manifest-v6-licznik-wejścia-i-generacje) | Serie supergry: manifest v6, licznik wejścia i generacje | accepted | 2026-10-09 | serie supergry są danymi pochodnymi wyprowadzanymi z komórek pociętych plansz z przypisanym symbolem… |
| [D-535](decisions/DECISION_LOG_2026.md#d-535--gra-mumie-wild-symbol-uruchamiający-supergrę-i-rodzaj-supergry-wild-super-spins) | Gra Mumie: Wild, symbol uruchamiający supergrę i rodzaj supergry „Wild super spins” | accepted | 2026-10-08 | dotychczasowy „Joker” nazywa się w UI i dokumentach „Wild” (kolumna symbols.is_wildcard zostaje). |
| [D-534](decisions/DECISION_LOG_2026.md#d-534--image-import-resumption-uses-the-hard-reserve-not-the-gc-target) | Image import resumption uses the hard reserve, not the GC target | accepted | 2026-10-07 | source ingestion and in-flight image pipeline checks use the configured hard reserve in every job stage,… |
| [D-533](decisions/DECISION_LOG_2026.md#d-533--pointsmachines-panel-with-durable-stake-saves-and-whole-panel-links) | Points/machines panel with durable stake saves and whole-panel links | accepted | 2026-10-07 | add Panel Administracyjny with points (name/city/street), named machines and editable active-game assignments. |
| [D-532](decisions/DECISION_LOG_2026.md#d-532--integrate-the-complete-v7-code-into-the-main-vision-lab-branch) | Integrate the complete V7 code into the main vision lab branch | accepted | 2026-10-07 | transplant the V7 product and tests from calibration HEAD b087ad08b62992c54f5e26191e6408d287b64273 onto… |
| [D-531](decisions/DECISION_LOG_2026.md#d-531--main-admin-offers-a-local-entry-to-the-approved-v7-test-panel) | Main Admin offers a local entry to the approved V7 test panel | accepted | 2026-10-07 | when main V7 remains blocked and selection is enabled, offer ordinary local navigation to the separate V7… |
| [D-530](decisions/DECISION_LOG_2026.md#d-530--managed-image-operations-retain-five-gib-after-estimation) | managed image operations retain five GiB after estimation | accepted | 2026-10-07 | the default hard reserve for managed image writes is 5 GiB, measured after the existing conservative… |
| [D-529](decisions/DECISION_LOG_2026.md#d-529--metadata-overview-precedes-exact-training-cohort-preparation) | metadata overview precedes exact training cohort preparation | accepted | 2026-10-07 | page entry reads current-owner logical symbol approvals and registry metadata through the existing… |
| [D-528](decisions/DECISION_LOG_2026.md#d-528--one-explicit-save-and-approve-action-in-symbol-verification) | one explicit save-and-approve action in symbol verification | accepted | 2026-10-07 | replace the separate approve and apply-change buttons with Symbol do zatwierdzenia and Zapisz i zatwierdź. |
| [D-527](decisions/DECISION_LOG_2026.md#d-527--shared-model-families-and-published-game-creation-catalog) | shared model families and published game creation catalog | accepted | 2026-10-07 | a model family is independent of a game record. |
| [D-526](decisions/DECISION_LOG_2026.md#d-526--neural-proposals-are-not-mandatory-correction-shared-laboratory-direction) | neural proposals are not mandatory correction; shared Laboratory direction | accepted | 2026-10-07 | neural review source counts describe unapproved proposals, not rejected geometry or mandatory manual work. |
| [D-525](decisions/DECISION_LOG_2026.md#d-525--grid-diagnostics-belong-to-correction-not-import) | grid diagnostics belong to correction, not import | accepted | 2026-10-07 | move the existing whole-image grid diagnostics out of Import plansz into Korekta cięcia siatki, alongside… |
| [D-524](decisions/DECISION_LOG_2026.md#d-524--show-the-actual-neural-import-and-retire-old-ui-choices) | show the actual neural import and retire old UI choices | accepted | 2026-10-06 | Mumie's existing game profile identifies V3 in Admin. |
| [D-523](decisions/DECISION_LOG_2026.md#d-523--operational-neural-crops-and-recoverable-symbol-verification) | operational neural crops and recoverable symbol verification | accepted | 2026-10-06 | new neural imports pin neural-auto-crop-v1. A bound full structurally valid 24-node lattice can produce… |
| [D-522](decisions/DECISION_LOG_2026.md#d-522--current-manual-neural-slot-approval-permits-its-own-symbol-save) | current manual neural slot approval permits its own symbol save | accepted | 2026-10-06 | a bound neural slot retaining its proposal checksum and exact 24-node lattice, saved as manual_v1 with the… |
| [D-521](decisions/DECISION_LOG_2026.md#d-521--explicit-mumie-rgb-and-neural-folder-pilot) | explicit Mumie RGB and neural folder pilot | accepted | 2026-10-06 | selection of the recommended earlier RGB and request to connect the engine to main-app folder uploads,… |
| [D-520](decisions/DECISION_LOG_2026.md#d-520--rgb-v2-jako-źródło-nowej-wersji-predykcji-oczekujących-komórek) | RGB v2 jako źródło nowej wersji predykcji oczekujących komórek | accepted | 2026-10-05 | oczekujące komórki z przypisaniem od modelu dostają symbol wybrany metodą RGB v2 z D-494 (argmax zamrożonej… |
| [D-506](decisions/DECISION_LOG_2026.md#d-506--explicit-larger-local-rgb-experiment) | explicit larger local RGB experiment | accepted | 2026-10-06 | autonomous larger-training instruction and accepted TASK-0871–0873 plan. |
| [D-505](decisions/DECISION_LOG_2026.md#d-505--explicitly-authorized-isolated-ai-symbol-experiment) | explicitly authorized isolated AI symbol experiment | accepted | 2026-10-06 | request to continue training autonomously and use internal AI to inspect graphics. |
| [D-504](decisions/DECISION_LOG_2026.md#d-504--qualified-feedback-inference-and-case-scoped-review-provenance) | qualified feedback inference and case-scoped review provenance | accepted | 2026-10-06 | operator-authorized third-recording diagnosis and existing exact crop review. |
| [D-503](decisions/DECISION_LOG_2026.md#d-503--exact-source-relocation-and-recording-declarations) | exact source relocation and recording declarations | accepted | 2026-10-06 | C:\Users\tuszy\Documents\mumie and instruction to continue with its cut folders. |
| [D-502](decisions/DECISION_LOG_2026.md#d-502--qualification-of-exact-reviewed-symbol-rasters) | qualification of exact reviewed symbol rasters | accepted | 2026-10-05 | freeze separate symbol_crop_feedback inputs from actual latest batch_crop_review approve decisions and exact… |
| [D-501](decisions/DECISION_LOG_2026.md#d-501--scoped-human-correction-of-independent-batch-crops) | scoped human correction of independent batch crops | accepted | 2026-10-05 | add optional batch_queue/batch_label_decide to existing symbol API. |
| [D-500](decisions/DECISION_LOG_2026.md#d-500--bounded-appearance-experiment-without-model-activation) | bounded appearance experiment without model activation | accepted | 2026-10-05 | one isolated RGB/gray v2 pair with deterministic, versioned lighting/payline augmentation, using only… |
| [D-499](decisions/DECISION_LOG_2026.md#d-499--niezależne-propozycje-symboli-i-granica-plansz-folderu) | niezależne propozycje symboli i granica plansz folderu | accepted | 2026-10-05 | osobny, niezmienny batch inferencji600 zdjęć z pełnym wykluczeniem komponentów D-498 i źródeł chronionych. |
| [D-498](decisions/DECISION_LOG_2026.md#d-498--potwierdzone-nagrania-i-osobny-split-symboli-mumii) | potwierdzone nagrania i osobny split symboli Mumii | accepted | 2026-10-05 | osobna kwalifikacja bieżącej kohorty symboli, z jawnie przypiętymi deklaracjami i całymi komponentami. |
| [D-497](decisions/DECISION_LOG_2026.md#d-497--zamrożony-widok-symboli-i-pojedynczy-odczyt-2000-cropów) | zamrożony widok symboli i pojedynczy odczyt 2000 cropów | accepted | 2026-10-05 | addytywny limit odczytu 2000, domyślny 30 i limit zapisu 30 zachowane; |
| [D-496](decisions/DECISION_LOG_2026.md#d-496--jawna-wersja-referencji-do-etykietowania-symboli-po-korektach-siatek) | jawna wersja referencji do etykietowania symboli po korektach siatek | accepted | 2026-10-05 | create-only, checksumowana referencja zachowuje cały oryginalny payload/historię/receipts geometrii i symboli. |
| [D-495](decisions/DECISION_LOG_2026.md#d-495--v3-d-oddzielny-ograniczony-shadow-i-ręczna-korekta) | V3-D: oddzielny, ograniczony shadow i ręczna korekta | accepted | 2026-10-05 | domyślnie wyłączony pion działa na zmaterializowanych źródłach 5 × 3 przez istniejące joby VALIDATE,… |
| [D-494](decisions/DECISION_LOG_2026.md#d-494--propozycja-głowicy-rgb-z-dodatkowym-potwierdzeniem-biblioteki-w-audycie) | propozycja głowicy RGB z dodatkowym potwierdzeniem biblioteki w audycie | accepted | 2026-10-05 | audyt wybiera propozycję z głowicy już zamrożonego, aktywnego checkpointu na pełnym RGB 64px, z normalizacją… |
| [D-493](decisions/DECISION_LOG_2026.md#d-493--najlepsza-propozycja-symbolu-wstępnie-wybrana-w-audycie-siatek) | najlepsza propozycja symbolu wstępnie wybrana w audycie siatek | accepted | 2026-10-05 | aktualne cięcie audytu pokazuje pewną propozycję albo najlepszego kandydata z sumy wag obu opisów biblioteki. |
| [D-492](decisions/DECISION_LOG_2026.md#d-492--poprawki-symboli-przez-link-wyszukiwarki-i-przegląd-operatora) | poprawki symboli przez link wyszukiwarki i przegląd operatora | accepted | 2026-10-05 | sesja board-search-share może poprawiać symbole aktualnych operacyjnych plansz swojej gry. |
| [D-491](decisions/DECISION_LOG_2026.md#d-491--nowe-podpowiedzi-symboli-dla-korekt-istniejących-siatek-audytu) | nowe podpowiedzi symboli dla korekt istniejących siatek audytu | accepted | 2026-10-05 | kolejka audytu istniejących plansz 777 pokazuje wyłącznie nowe propozycje biblioteki wzorców dla żółtej… |
| [D-490](decisions/DECISION_LOG_2026.md#d-490--run-3-sieci-siatek-przygotowuje-nowe-gry-mumie-blazing-i-gang-w-treningu-wagi-startowe-zmienia-d-456-i-ustawienia-d-481) | run 3 sieci siatek przygotowuje nowe gry: Mumie, Blazing i Gang w treningu, wagi startowe (zmienia D-456 i ustawienia D-481) | accepted | 2026-10-02 | 1. Run 2 (preset B) zostaje dokończony. |
| [D-489](decisions/DECISION_LOG_2026.md#d-489--symbole-dla-silnika-v3-są-wybierane-i-uczone-od-nowa-bez-dotychczasowych-etykiet) | symbole dla silnika V3 są wybierane i uczone od nowa, bez dotychczasowych etykiet | accepted | 2026-10-02 | rozpoznawanie symboli dla zdjęć ciętych siatkami silnika V3 (nowe importy 777 i nowe gry) powstaje od nowa:… |
| [D-488](decisions/DECISION_LOG_2026.md#d-488--korekta-cięcia-siatki-może-zatwierdzić-symbole-wskazane-przez-operatora-zmienia-d-462) | korekta cięcia siatki może zatwierdzić symbole wskazane przez operatora (zmienia D-462) | accepted | 2026-10-02 | zapis geometrii z ekranu „Korekta cięcia siatki” może zawierać symbole narzucone przez operatora dla… |
| [D-487](decisions/DECISION_LOG_2026.md#d-487--dziennik-linku-zapisuje-stawkę-wybraną-przez-odbiorcę-zmienia-d-472-i-d-478) | dziennik linku zapisuje stawkę wybraną przez odbiorcę (zmienia D-472 i D-478) | accepted | 2026-10-02 | strona linku zgłasza każdą parę (zakres, stawka), którą pokazuje odbiorcy, przez GET… |
| [D-486](decisions/DECISION_LOG_2026.md#d-486--dziennik-linku-grupuje-wyszukiwania-tego-samego-wzoru-zmienia-d-478) | dziennik linku grupuje wyszukiwania tego samego wzoru (zmienia D-478) | accepted | 2026-10-02 | widok dziennika pokazuje jeden wpis na wzór 3 × 5 w ramach linku (klucz: request.cells; |
| [D-485](decisions/DECISION_LOG_2026.md#d-485--bramka-kompletności-stan-trwały-zdjęcia-dokument-sekwencji-bez-dowodu-symboli-przepinanie-plansz-uzupełnia-d-484) | bramka kompletności: stan trwały zdjęcia, dokument sekwencji bez dowodu symboli, przepinanie plansz (uzupełnia D-484) | accepted | 2026-10-02 | 1. source_images ma trwały stan geometry_complete, geometry_incomplete, geometry_exception albo NULL… |
| [D-484](decisions/DECISION_LOG_2026.md#d-484--kompletność-geometrii-zdjęcia-jest-bramką-przed-cięciem-na-symbole) | kompletność geometrii zdjęcia jest bramką przed cięciem na symbole | accepted | 2026-10-01 | jednostką geometrii jest zdjęcie źródłowe. |
| [D-483](decisions/DECISION_LOG_2026.md#d-483--metryka-nadrzędna-silnika-siatek-odsetek-zdjęć-kompletnych-i-poprawnych) | metryka nadrzędna silnika siatek: odsetek zdjęć kompletnych i poprawnych | accepted | 2026-10-01 | silnik siatek 5 × 3 ocenia się najpierw odsetkiem zdjęć, na których wszystkie oczekiwane plansze mają siatkę… |
| [D-482](decisions/DECISION_LOG_2026.md#d-482--etap-d-sieć-węzłów-rusza-bez-ukończenia-etapu-c-symbole) | etap D (sieć węzłów) rusza bez ukończenia etapu C (symbole) | accepted | 2026-10-01 | T10 / TASK-0675 dla geometrii 5 × 3, realizowany jako TASK-0802, nie wymaga ukończenia T09 ani STOP C planu… |
| [D-481](decisions/DECISION_LOG_2026.md#d-481--budżet-treningu-geometrii-v3-do-3-runów-po-4-godziny-gpu-na-zadanie-modelu) | budżet treningu geometrii V3: do 3 runów po 4 godziny GPU na zadanie modelu | accepted | 2026-10-01 | zadanie modelu planu V3 (TASK-0802) może wykonać do trzech runów, każdy do 4 godzin GPU, z presetem i… |
| [D-480](decisions/DECISION_LOG_2026.md#d-480--zatwierdzona-geometria-produkcyjna-777-jako-dane-uczące-geometrii-zmienia-d-453) | zatwierdzona geometria produkcyjna 777 jako dane uczące geometrii (zmienia D-453) | accepted | 2026-10-01 | plansze 777 z zatwierdzoną geometrią w game_data_v2 (poziom S: zatwierdzone po reweryfikacji… |
| [D-479](decisions/DECISION_LOG_2026.md#d-479--przybliżona-wygrana-bez-kafelków-i-wyboru-zakresu-nazwy-operatora-zmienia-d-476) | „Przybliżona wygrana” bez kafelków i wyboru zakresu; nazwy operatora (zmienia D-476) | accepted | 2026-10-02 | w „Przybliżonej wygranej” i oknie planszy „bilans” nazywa się „kasa na czysto”, a „wypłata” — „wygrana”… |
| [D-478](decisions/DECISION_LOG_2026.md#d-478--dziennik-linku-pokazuje-wyszukiwania-z-wykresem-wpis-można-usunąć-zmienia-d-472) | dziennik linku pokazuje wyszukiwania z wykresem; wpis można usunąć (zmienia D-472) | accepted | 2026-10-02 | widok dziennika w Adminie listuje wyłącznie wyszukiwania (kind=search), po 10. Wpis pokazuje wzór 3 × 5… |
| [D-477](decisions/DECISION_LOG_2026.md#d-477--trwałe-usunięcie-wzorca-wypłat-w-wersji-roboczej-zmienia-d-026) | trwałe usunięcie wzorca wypłat w wersji roboczej (zmienia D-026) | accepted | 2026-10-01 | DELETE /rules-versions/{id}/paylines/{paylineId}/permanent fizycznie usuwa wzorzec, wyłącznie w wersji o… |
| [D-476](decisions/DECISION_LOG_2026.md#d-476--przybliżona-wygrana-statyczna-stawka-wybierana-per-wzór-złote-domyślnie) | „Przybliżona wygrana” statyczna, stawka wybierana per wzór, złote domyślnie | accepted | 2026-10-01 | sekcja jest statyczna i liczy od razu dla wybranej planszy (żądanie po ustaleniu wyboru na ~0,4 s; |
| [D-475](decisions/DECISION_LOG_2026.md#d-475--zapis-dziennika-zapytań-linku-w-osobnej-transakcji-uzupełnia-d-472) | zapis dziennika zapytań linku w osobnej transakcji (uzupełnia D-472) | accepted | 2026-09-30 | wpis jest zapisywany w osobnej, krótkiej transakcji, która jest zatwierdzana, zanim odpowiedź z danymi… |
| [D-474](decisions/DECISION_LOG_2026.md#d-474--nieaktualny-odczyt-planszy-w-oknie-linii-i-odświeżenie-jednej-planszy) | nieaktualny odczyt planszy w oknie linii i odświeżenie jednej planszy | accepted | 2026-09-30 | szczegóły planszy przy niezgodnej sumie tożsamości nie zwracają 409, tylko documentStale = true z liniami i… |
| [D-473](decisions/DECISION_LOG_2026.md#d-473--poprawianie-symbolu-pola-z-okna-planszy-przybliżonej-wygranej) | poprawianie symbolu pola z okna planszy „Przybliżonej wygranej” | accepted | 2026-09-30 | okno planszy z liniami wypłat ma tryb „Popraw symbole”. |
| [D-472](decisions/DECISION_LOG_2026.md#d-472--dziennik-zapytań-udostępnionego-linku-i-odtworzenie-w-adminie) | dziennik zapytań udostępnionego linku i odtworzenie w Adminie | accepted | 2026-09-30 | serwer zapisuje każde publiczne zapytanie o dane udostępnionej wyszukiwarki (wyszukiwanie, przybliżona… |
| [D-471](decisions/DECISION_LOG_2026.md#d-471--udostępnianie-wyszukaj-plansze-online-przez-link-z-kodem) | udostępnianie „Wyszukaj plansze” online przez link z kodem | accepted | 2026-09-30 | operator tworzy w Adminie link do kopii sekcji „Wyszukaj plansze” razem z „Przybliżoną wygraną”. |
| [D-470](decisions/DECISION_LOG_2026.md#d-470--stawka-złote-i-linie-wypłat-w-przybliżonej-wygranej) | stawka, złote i linie wypłat w „Przybliżonej wygranej” | accepted | 2026-09-30 | 1 zł = 10 kredytów. Stawka bazowa to koszt spinu opublikowanych reguł (dziś 100 kredytów = 10 zł). |
| [D-467](decisions/DECISION_LOG_2026.md#d-467--usunięcie-pozostałości-v1legacy-manifest-renderu-per-plansza-zamiast-cell_observations) | usunięcie pozostałości V1/legacy: manifest renderu per plansza zamiast `cell_observations` | accepted | 2026-09-30 | aplikacja i baza mają być V2-only bez danych i kodu z ery V1. Specyfikację renderu przechowuje jedna tabela… |
| [D-466](decisions/DECISION_LOG_2026.md#d-466--nowa-wersja-predykcji-z-biblioteki-wzorców-dla-oczekujących-komórek) | nowa wersja predykcji z biblioteki wzorców dla oczekujących komórek | accepted | 2026-09-29 | dla oczekujących komórek z przypisaniem od modelu biblioteka wzorców zapisuje nową wersję predykcji… |
| [D-465](decisions/DECISION_LOG_2026.md#d-465--dobór-wzorców-symboli-zasłonięcia-i-zatwierdzenia-masowe) | dobór wzorców symboli: zasłonięcia i zatwierdzenia masowe | accepted | 2026-09-29 | planu biblioteki wzorców (D-464). - Occlusion: symbol częściowo zasłonięty (dłoń, przycisk nawigacji) lub… |
| [D-464](decisions/DECISION_LOG_2026.md#d-464--propozycje-symboli-z-biblioteki-zweryfikowanych-komórek) | propozycje symboli z biblioteki zweryfikowanych komórek | accepted | 2026-09-29 | oczekująca komórka może otrzymać propozycję symbolu wyliczoną z podobieństwa do komórek zweryfikowanych… |
| [D-463](decisions/DECISION_LOG_2026.md#d-463--ponowne-task-0603-kalibruje-etykiety-v2-na-obu-nagraniach-777) | ponowne TASK-0603 kalibruje etykiety V2 na obu nagraniach 777 | accepted | 2026-09-29 | nowa sesja T0603 używa standard_3x3_numeric_labels_v2 i osobnego ignorowanego manifestu… |
| [D-462](decisions/DECISION_LOG_2026.md#d-462--weryfikacja-per-komórka-bez-zatwierdzania-planszy-i-siatki) | weryfikacja per komórka bez zatwierdzania planszy i siatki | accepted | 2026-09-29 | źródłem prawdy jest pojedyncza komórka (image_symbol_review_cells). |
| [D-461](decisions/DECISION_LOG_2026.md#d-461--niezależny-przebieg-v3-dla-istniejącej-gry-v11) | niezależny przebieg v3 dla istniejącej gry v1.1 | accepted | 2026-09-28 | tożsamość i wydanie gry nie wybierają automatycznie silnika. |
| [D-460](decisions/DECISION_LOG_2026.md#d-460--wyliczana-poczekalnia-cropów-bez-nowej-hierarchii-symboli) | wyliczana poczekalnia cropów bez nowej hierarchii symboli | accepted | 2026-09-28 | cropy z aktualnych zaakceptowanych geometrii są pokazywane stronicowaną poczekalnią. |
| [D-459](decisions/DECISION_LOG_2026.md#d-459--atomowe-etykietowanie-całej-planszy-w-laboratorium) | atomowe etykietowanie całej planszy w laboratorium | accepted | 2026-09-27 | addytywne warianty lab_board w POST /symbol-crops i label_board_decide w POST /symbols. |
| [D-458](decisions/DECISION_LOG_2026.md#d-458--rozdzielenie-narzędzi-t06-od-kwalifikacji-zbioru-symboli) | rozdzielenie narzędzi T06 od kwalifikacji zbioru symboli | accepted | 2026-09-27 | T06a dostarcza narzędzia, izolowany magazyn symboli i adapter zweryfikowanego eksportu DB. |
| [D-457](decisions/DECISION_LOG_2026.md#d-457--techniczny-kontrakt-pierwszej-hybrydy-d-456) | techniczny kontrakt pierwszej hybrydy D-456 | accepted | 2026-09-27 | pierwszy pilot to obrazowe propozycje BaselineEngine oraz MobileNetV3-Small poprawiający cztery narożniki… |
| [D-456](decisions/DECISION_LOG_2026.md#d-456--pilotaż-geometrii-5--3-z-podziałem-całymi-grami) | pilotaż geometrii 5 × 3 z podziałem całymi grami | accepted | 2026-09-27 | osobna jawna polityka lab-geometry-whole-game-pilot-v1 zastępuje dla tego pilota wymóg verified rodzin oraz… |
| [D-455](decisions/DECISION_LOG_2026.md#d-455--kwalifikacja-targetów-777-bez-kwalifikowania-kontekstu) | kwalifikacja targetów 777 bez kwalifikowania kontekstu | accepted | 2026-09-27 | nowa, jawnie wybierana polityka geometry-only z niepustą kohortą wymaga kwalifikacji D-453 od każdego… |
| [D-454](decisions/DECISION_LOG_2026.md#d-454--jawna-kohorta-geometrii-nie-usuwa-powiązań-źródeł) | jawna kohorta geometrii nie usuwa powiązań źródeł | accepted | 2026-09-27 | opcjonalny wybór źródeł geometrii ogranicza wyłącznie targety i przypisania przykładów. |
| [D-453](decisions/DECISION_LOG_2026.md#d-453--historyczne-zdjęcia-777-dopuszczone-do-uczenia-geometrii) | historyczne zdjęcia 777 dopuszczone do uczenia geometrii | accepted | 2026-09-27 | historyczne zdjęcia 777 mogą służyć do uczenia geometrii przyszłych podobnych zdjęć. |
| [D-452](decisions/DECISION_LOG_2026.md#d-452--atomowe-pokwitowania-uzupełnienia-pozycji-pilota) | atomowe pokwitowania uzupełnienia pozycji pilota | accepted | 2026-09-27 | - Podgląd jest niezmiennym, wersjonowanym dokumentem z SHA, dokładną listą 70 numerów, bieżącym… |
| [D-451](decisions/DECISION_LOG_2026.md#d-451--każda-pozycja-niepełnej-planszy-dostępna-w-weryfikacji-symboli) | każda pozycja niepełnej planszy dostępna w weryfikacji symboli | accepted | 2026-09-27 | wszystkie 15 logicznych pozycji planszy 3 × 5 pozostają dostępne operatorowi. |
| [D-450](decisions/DECISION_LOG_2026.md#d-450--przegląd-zdjęcia-jako-dodatkowa-bramka-laboratoryjna) | przegląd zdjęcia jako dodatkowa bramka laboratoryjna | accepted | 2026-09-27 | akceptacja zdjęcia wiąże SHA źródła i mapę rewizji wszystkich zapisanych pozycji; |
| [D-449](decisions/DECISION_LOG_2026.md#d-449--niepełna-plansza-w-odroczonej-korekcie-geometrii-komórek-opt-in-bez-osłabienia-współdzielonego-croppera) | niepełna plansza w odroczonej korekcie geometrii komórek (opt-in, bez osłabienia współdzielonego croppera) | accepted | 2026-09-26 | derive_board_cell_quads/_parse_quad (board_cell_geometry_contract.py) i… |
| [D-448](decisions/DECISION_LOG_2026.md#d-448--game_data_v2-jako-jedyny-magazyn-game-owned-public-zachowuje-catalogcontrolshared) | `game_data_v2` jako jedyny magazyn game-owned; `public` zachowuje catalog/control/shared | accepted | 2026-09-25 | w PostgreSQL game_data_v2 jest jedynym fizycznym data plane relacji game-owned z zamrożonego manifestu v1.… |
| [D-447](decisions/DECISION_LOG_2026.md#d-447--laboratoryjne-zatwierdzenia-i-plan-wizji) | laboratoryjne zatwierdzenia i plan wizji | accepted | 2026-09-25 | lokalne laboratorium może używać osobnych zatwierdzeń lab_human_approved. |
| [D-446](decisions/DECISION_LOG_2026.md#d-446--przybliżona-wygrana-w-adminie-dolne-ograniczenie-z-payout-v3-bez-cache-serwerowego) | „Przybliżona wygrana” w Adminie: dolne ograniczenie z payout-v3, bez cache serwerowego | accepted | 2026-09-25 | „Wyszukaj plansze” zyskuje niezależny input „Liczba wyników” (domyślnie 5, 1–100 — istniejący limit… |
| [D-445](decisions/DECISION_LOG_2026.md#d-445--reweryfikacja-siatek-777-nie-opiera-się-na-lokalnym-estymatorze-kierunek-silnik-v3-bez-wzorca-per-gra) | reweryfikacja siatek 777 nie opiera się na lokalnym estymatorze; kierunek: silnik v3 bez wzorca per gra | accepted | 2026-09-24 | estimate_board_cell_geometry nie jest weryfikatorem „pewności” siatek 777 — przy tej samej podpowiedzi… |
| [D-444](decisions/DECISION_LOG_2026.md#d-444--zdarzenie-zatwierdzenia-geometrii-planszy-virtual_source-identyfikuje-checksum-geometrii-ręczna-korekta-cold-start-nie-woła-onnx) | zdarzenie zatwierdzenia geometrii planszy `virtual_source` identyfikuje checksum geometrii; ręczna korekta cold start nie woła ONNX | accepted | 2026-09-24 | (1) image_board_geometry_review_events.board_checksum_sha256 dla akcji approved =… |
| [D-443](decisions/DECISION_LOG_2026.md#d-443--skrypt-legacy-gc-odmawia-skanu-jeśli-jakakolwiek-gra-ma-magazyn-per-game-v2) | skrypt legacy GC odmawia skanu, jeśli jakakolwiek gra ma magazyn per-game (V2) | superseded | 2026-09-24 | scripts/preview_legacy_game_managed_asset_gc.py's _operation_guard (współdzielony punkt wejścia obu ścieżek:… |
| [D-442](decisions/DECISION_LOG_2026.md#d-442--trasy-z-gameid-wyłącznie-w-query-muszą-jawnie-bindować-game_storage_scope) | trasy z `gameId` wyłącznie w query muszą jawnie bindować `game_storage_scope` | accepted | 2026-09-24 | cztery trasy /admin/image-reviews/{review_item_id}/… (source-asset, geometry-approval, geometry-preview,… |
| [D-441](decisions/DECISION_LOG_2026.md#d-441--adjacentmanualnavigationstep-musi-stąpać-po-manual_image_navigation_steps-nie-po-surowej-liczbie) | `adjacentManualNavigationStep` musi stąpać po `MANUAL_IMAGE_NAVIGATION_STEPS`, nie po surowej liczbie | accepted | 2026-09-24 | adjacentManualNavigationStep (packages/manual-image-selection-core/src/index.ts) z powrotem szuka bieżącej… |
| [D-440](decisions/DECISION_LOG_2026.md#d-440--board-import-coverage-musi-jawnie-bindować-gamestoragerouter-ten-sam-brak-dotyczy-sąsiednich-endpointów-image-review-items) | `board-import-coverage` musi jawnie bindować `GameStorageRouter`; ten sam brak dotyczy sąsiednich endpointów `image-review-items` | accepted | 2026-09-24 | SqlAlchemyBoardImportCoverageRepository.board_import_coverage wywołuje teraz jawnie… |
| [D-439](decisions/DECISION_LOG_2026.md#d-439--wstępna-geometria-strony-z-automatycznej-propozycji-automaticpageproposal) | Wstępna geometria strony z automatycznej propozycji (`automaticPageProposal`) | accepted | 2026-09-24 | review-sources może dołączyć opcjonalne automaticPageProposal dla źródeł review_required bez istniejącej… |
| [D-438](decisions/DECISION_LOG_2026.md#d-438--komórki-blurry-pozostają-widoczne-pod-filtrem-swojego-symbolu) | Komórki `blurry` pozostają widoczne pod filtrem swojego symbolu | accepted | 2026-09-24 | komórka Weryfikacji symboli z quality_issue = 'blurry' (checkbox „Niewyraźny") jest widoczna w liście… |
| [D-437](decisions/DECISION_LOG_2026.md#d-437--definicja-planszy-dodanej-dla-pokrycia-importu-bez-nowej-flagi) | Definicja „planszy dodanej" dla pokrycia importu, bez nowej flagi | accepted | 2026-09-24 | plansza n gry g jest dodana wtedy i tylko wtedy, gdy 1 ≤ n ≤ games.expected_layout_count oraz spełniony jest… |
| [D-436](decisions/DECISION_LOG_2026.md#d-436--częściowo-widoczne-komórki-trafiają-do-weryfikacji-symboli-jako-wymuszony-nierozpoznany-t2ef) | Częściowo widoczne komórki trafiają do Weryfikacji symboli jako wymuszony „nierozpoznany" (T2/E–F) | accepted | 2026-09-23 | komórka partially_visible (D-434) na planszy virtual_source z kwalifikacją v3 (D-435) trafia teraz do… |
| [D-435](decisions/DECISION_LOG_2026.md#d-435--geometryqualification-v3-wprowadza-fully_unavailable_cell_indices-t2ad) | GeometryQualification v3 wprowadza fully_unavailable_cell_indices (T2/A–D) | accepted | 2026-09-23 | GeometryQualification dostaje nową wersję manual-geometry-qualification-v3 (backend-only — request/response… |
| [D-434](decisions/DECISION_LOG_2026.md#d-434--częściowo-widoczne-komórki-mogą-być-renderowane-do-ręcznej-oceny-t1-domena--renderer) | Częściowo widoczne komórki mogą być renderowane do ręcznej oceny (T1: domena + renderer) | accepted | 2026-09-23 | komórka planszy z 1–3 (nie 4) rogami quada poza granicami zdjęcia może zostać zmaterializowana jako… |
| [D-433](decisions/DECISION_LOG_2026.md#d-433--lekki-skok-stron-w-weryfikacji-symboli-zamiast-paginacji-offsetowej) | Lekki skok stron w Weryfikacji symboli zamiast paginacji offsetowej | accepted | 2026-09-23 | dodano GET /api/v1/admin/games/{game_id}/symbol-cell-review-skip, zwracający wyłącznie kursor keyset count… |
| [D-432](decisions/DECISION_LOG_2026.md#d-432--routing-wpisów-manifestu-wymaga-registrationversion-manualnego-overrideu) | Routing wpisów manifestu wymaga registrationVersion manualnego override'u | accepted | 2026-09-23 | w production_workflow.py::_detect_structured_geometry warunek kierujący wpis manifestu geometrii strony do… |
| [D-431](decisions/DECISION_LOG_2026.md#d-431--quad-słabej-planszy-relaksacji-d-420-pochodzi-z-projekcji-homografii) | Quad słabej planszy relaksacji D-420 pochodzi z projekcji homografii | accepted | 2026-09-23 | na stronie akceptowanej wyłącznie ścieżką relaksacji D-420 (relaxed_accepted and not baseline_accepted),… |
| [D-430](decisions/DECISION_LOG_2026.md#d-430--maska-czerwieni-odporna-na-ciemną-ramkę-v--30) | Maska czerwieni odporna na ciemną ramkę (V ≥ 30) | accepted | 2026-09-23 | page_geometry_registration._red_mask obniża dolny próg jasności (V) z 50 do 30 w obu pasmach barwy (hue 0–18… |
| [D-429](decisions/DECISION_LOG_2026.md#d-429--v12-dopuszcza-testowy-import-po-kompletnym-preflighcie) | V1.2 dopuszcza testowy import po kompletnym preflighcie | accepted | 2026-09-22 | jawny wariant contrast_frame_grid_v1_2 może uruchomić przeglądarkowy import wyłącznie z ukończonym,… |
| [D-428](decisions/DECISION_LOG_2026.md#d-428--rzeczywiste-gry-używają-siatki-ramek-plansz-jako-wariantu-v21) | Rzeczywiste gry używają siatki ramek plansz jako wariantu V2.1 | accepted | 2026-09-22 | nowy, testowy wariant board-frame-lattice-v2.1 wykrywa dziewięć osobnych ramek plansz i ich układ 3 × 3.… |
| [D-427](decisions/DECISION_LOG_2026.md#d-427--odbiór-g08-jest-odrębną-lokalną-bramką-acceptance) | Odbiór G08 jest odrębną, lokalną bramką acceptance | accepted | 2026-09-22 | odbiór używa wyłącznie manifestu i truthu acceptance, a osobny manifest executor służy wyłącznie do kontroli… |
| [D-426](decisions/DECISION_LOG_2026.md#d-426--pilot-shared-shape-v2-publikuje-tylko-kompletny-wynik-pomiaru) | Pilot shared shape v2 publikuje tylko kompletny wynik pomiaru | accepted | 2026-09-22 | lokalny pilot wiąże checksumami corpus executor, inwentarz, anotacje i pięć etapów: zaakceptowaną korektę… |
| [D-425](decisions/DECISION_LOG_2026.md#d-425--kwalifikacja-shared-shape-v2-publikuje-wyłącznie-pełny-bezwyciekowy-raport) | Kwalifikacja shared shape v2 publikuje wyłącznie pełny, bezwyciekowy raport | accepted | 2026-09-21 | kandydat globalnego profilu może zmienić status tylko przez idempotentną kwalifikację zapisaną jako… |
| [D-424](decisions/DECISION_LOG_2026.md#d-424--deklaracja-rodziny-strony-gry-nie-jest-lokalnym-profilem-geometrii) | Deklaracja rodziny strony gry nie jest lokalnym profilem geometrii | accepted | 2026-09-21 | katalog gry zapisuje wyłącznie framed_full_page_v2 albo requires_clarification; |
| [D-423](decisions/DECISION_LOG_2026.md#d-423--profil-shared-shape-v2-jest-przypiętą-propozycją-preflightu-nie-zgodą-na-import) | Profil shared shape v2 jest przypiętą propozycją preflightu, nie zgodą na import | accepted | 2026-09-21 | resolver wybiera wyłącznie jeden aktywny profil framed_full_page_v2 dla topologii 3 × 3 / 3 × 5. Zamyka go w… |
| [D-422](decisions/DECISION_LOG_2026.md#d-422--globalna-biblioteka-shape-v2-jest-publicznym-descriptor-only-control-plane) | Globalna biblioteka shape v2 jest publicznym, descriptor-only control plane | accepted | 2026-09-21 | wersje wspólnego profilu framed_full_page_v2, ich dowody i receipty retry są przechowywane wyłącznie w… |
| [D-421](decisions/DECISION_LOG_2026.md#d-421--rdzeń-v2-daje-tylko-deterministyczną-propozycję-z-dowodem-per-slot) | Rdzeń v2 daje tylko deterministyczną propozycję z dowodem per slot | accepted | 2026-09-21 | wspólny rdzeń v2 wykrywa ramkę bez zależności od jej koloru, rektyfikuje ją do W−1/H−1 i wyprowadza dziewięć… |
| [D-420](decisions/DECISION_LOG_2026.md#d-420--relaksacja-red-edge-dla-powtarzalnej-zasłony-planszy) | Relaksacja red-edge dla powtarzalnej zasłony planszy | accepted | 2026-09-22 | verified page registration akceptuje stronę, gdy jedna plansza ma słabe pokrycie czerwonej krawędzi, pod… |
| [D-420](decisions/DECISION_LOG_2026.md#d-420--trwały-zamiar-może-być-widoczny-przed-receiptem-serwera) | Trwały zamiar może być widoczny przed receiptem serwera | accepted | 2026-09-22 | po pomyślnym zapisie operacji do IndexedDB Admin projektuje niepotwierdzone sloty bieżącego źródła wyłącznie… |
| [D-420](decisions/DECISION_LOG_2026.md#d-420--rozszerzalny-kontrakt-corpusów-i-fail-closed-eksperyment-transferu) | Rozszerzalny kontrakt corpusów i fail-closed eksperyment transferu | accepted | 2026-09-21 | corpus schema v1 zachowuje dokładnie pięć początkowych gier i własny fingerprint. |
| [D-419](decisions/DECISION_LOG_2026.md#d-419--manual-grid-placement-używa-drag-hold-zamiast-dwukliku) | Manual grid placement używa drag-hold zamiast dwukliku | accepted | 2026-09-22 | w edytorze geometrii plansz operator wyznacza siatkę 3 × 5 przeciągnięciem z wciśniętym przyciskiem myszy:… |
| [D-419](decisions/DECISION_LOG_2026.md#d-419--v2-normalizuje-numery-względem-lokalnej-siatki-nie-całego-kadru) | V2 normalizuje numery względem lokalnej siatki, nie całego kadru | accepted | 2026-09-22 | standard_3x3_numeric_labels_v2 wykrywa wyłącznie lokalną, kompletną i jednoznaczną siatkę dziewięciu etykiet… |
| [D-419](decisions/DECISION_LOG_2026.md#d-419--automatyczna-kwalifikacja-wspólnej-wiedzy-i-ciągłe-wykonanie-planu-v2) | Automatyczna kwalifikacja wspólnej wiedzy i ciągłe wykonanie planu v2 | accepted | 2026-09-21 | cały plan geometrii v2 jest realizowany w jednej serii na osobnej gałęzi. |
| [D-418](decisions/DECISION_LOG_2026.md#d-418--diagnostyka-niepełnego-cropa-nie-unieważnia-pełnej-kalibracji) | Diagnostyka niepełnego cropa nie unieważnia pełnej kalibracji | accepted | 2026-09-21 | profil geometrii etykiet V7 oraz lokalny wskaźnik gotowości używają wyłącznie slotów annotated z oceną… |
| [D-418](decisions/DECISION_LOG_2026.md#d-418--wspólny-rdzeń-geometrii-różnice-tylko-jako-konfiguracja-gry) | Wspólny rdzeń geometrii, różnice tylko jako konfiguracja gry | accepted | 2026-09-21 | v2 ma jeden współdzielony rdzeń wykrywania obrysu, perspektywy, układu 3 × 3, siatki 3 × 5 i kompletności. |
| [D-417](decisions/DECISION_LOG_2026.md#d-417--t05-zapisuje-surowe-predykcje-i-tworzy-adopcję-wyłącznie-z-passed-reportu) | T05 zapisuje surowe predykcje i tworzy adopcję wyłącznie z passed reportu | accepted | 2026-09-21 | report T05 przyjmuje tylko niezależny truth źródeł oraz surowy snapshot automatu bez client-supplied… |
| [D-417](decisions/DECISION_LOG_2026.md#d-417--podział-danych-nie-ogranicza-listy-gier-tworzenia) | Podział danych nie ogranicza listy gier tworzenia | accepted | 2026-09-21 | 777, Blazing, Gang, Reels i Mumie pozostają kandydatami do tworzenia gier. |
| [D-416](decisions/DECISION_LOG_2026.md#d-416--tracker-wystąpień-jest-jedynym-właścicielem-słabego-dowodu-v7-33) | Tracker wystąpień jest jedynym właścicielem słabego dowodu V7 3+3 | accepted | 2026-09-21 | obserwator związany z profilem zwraca wyłącznie source-local weak evidence trzech zgodnych etykiet,… |
| [D-416](decisions/DECISION_LOG_2026.md#d-416--korpus-eksperymentalnej-geometrii-rozdziela-dostęp-wykonawczy-od-odbioru) | Korpus eksperymentalnej geometrii rozdziela dostęp wykonawczy od odbioru | accepted | 2026-09-21 | testowy silnik geometrii shape_frame_geometry_v2_0 używa osobnego manifestu wykonawczego, zawierającego… |
| [D-415](decisions/DECISION_LOG_2026.md#d-415--kalibracja-t0603-używa-odrębnego-manifestu-v2-obu-katalogów-777) | Kalibracja T0603 używa odrębnego manifestu V2 obu katalogów 777 | accepted | 2026-09-21 | rzeczywista sesja pierwszej rodziny geometrii używa nowego, lokalnego i ignorowanego manifestu T0603.… |
| [D-414](decisions/DECISION_LOG_2026.md#d-414--ekran-kalibracji-zachowuje-zamiar-lokalnie-a-rewizję-na-serwerze) | Ekran kalibracji zachowuje zamiar lokalnie, a rewizję na serwerze | accepted | 2026-09-21 | ekran Admina zapisuje przed requestem uporządkowany zamiar operationId w IndexedDB wraz z pierwotną… |
| [D-413](decisions/DECISION_LOG_2026.md#d-413--api-kalibracji-v7-rozwiązuje-korpus-po-stronie-serwera) | API kalibracji V7 rozwiązuje korpus po stronie serwera | accepted | 2026-09-21 | konfiguracja operatora wskazuje manifest korpusu i runtime root; |
| [D-412](decisions/DECISION_LOG_2026.md#d-412--sesje-geometrii-etykiet-v7-są-server-owned-i-append-safe) | Sesje geometrii etykiet V7 są server-owned i append-safe | accepted | 2026-09-21 | sesja anotacji ma przypięty inwentarz źródeł calibration-only, rewizję i receipt operationId; |
| [D-411](decisions/DECISION_LOG_2026.md#d-411--profil-etykiet-v7-jest-wersjonowany-różnorodny-i-adoptowany-jawnie) | Profil etykiet V7 jest wersjonowany, różnorodny i adoptowany jawnie | accepted | 2026-09-21 | pierwszy profil standard_3x3_numeric_labels_v1 kalibruje wyłącznie środki etykiet liczbowych na kanonicznym… |
| [D-410](decisions/DECISION_LOG_2026.md#d-410--worker-v7-wybiera-wyłącznie-własny-runtime-i-zablokowaną-kalibrację) | Worker V7 wybiera wyłącznie własny runtime i zablokowaną kalibrację | accepted | 2026-09-21 | job półautomatu schema 4 jest obsługiwaną wersją V7. Handler ładuje jego LocalSourceManifest tak jak schema… |
| [D-409](decisions/DECISION_LOG_2026.md#d-409--reels_test-jest-wyłącznym-holdoutem-odbioru-v7) | `reels_test` jest wyłącznym holdoutem odbioru V7 | accepted | 2026-09-21 | lokalny manifest TASK-0597 przypina reels_test jako jedyny case splitu holdout; |
| [D-408](decisions/DECISION_LOG_2026.md#d-408--v7-ma-osobny-workflow-i-twardą-bramkę-aktywacji) | V7 ma osobny workflow i twardą bramkę aktywacji | accepted | 2026-09-21 | V7 używa workflow_mode=v7_selection, payloadu schema v4 i server-owned konfiguracji pełnej strony. |
| [D-407](decisions/DECISION_LOG_2026.md#d-407--kalibracja-v7-zachowuje-pomiar-nieudanego-progu-ale-blokuje-aktywację) | Kalibracja V7 zachowuje pomiar nieudanego progu, ale blokuje aktywację | accepted | 2026-09-21 | kalibracja geometrii V7 wymaga co najmniej pięciu niezależnych źródeł na każdą z dziewięciu pozycji… |
| [D-406](decisions/DECISION_LOG_2026.md#d-406--nieczytelny-kadr-i-nieznana-widoczność-nie-mogą-wygrać-przez-brak-danych) | Nieczytelny kadr i nieznana widoczność nie mogą wygrać przez brak danych | accepted | 2026-09-21 | po własnym proof kandydaty V7 są porównywane według najgorszej planszy. |
| [D-405](decisions/DECISION_LOG_2026.md#d-405--v7-rozdziela-occurrence-kursor-sekwencji-i-podgląd-operatora) | V7 rozdziela occurrence, kursor sekwencji i podgląd operatora | accepted | 2026-09-21 | V7 utrzymuje osobno indeks następnego źródła, monotoniczny kursor oczekiwanych zakresów oraz indeks źródła… |
| [D-404](decisions/DECISION_LOG_2026.md#d-404--pierwotna-próbka-holdoutu-v7-jest-wyłączona-z-niezależnego-odbioru) | Pierwotna próbka holdoutu V7 jest wyłączona z niezależnego odbioru | accepted | 2026-09-21 | plik rells big/reels 218400_000114.jpg, otwarty przez wycofany probe przed ograniczeniem splitów, nie może… |
| [D-403](decisions/DECISION_LOG_2026.md#d-403--v7-nie-uznaje-statycznych-cropów-za-dowód-geometrii) | V7 nie uznaje statycznych cropów za dowód geometrii | accepted | 2026-09-21 | początkowy lokalizator OCR v7 emituje position_confidence=0.00. Tylko konfiguracja pomierzona i zatwierdzona… |
| [D-402](decisions/DECISION_LOG_2026.md#d-402--status-importu-plansz-jest-niezależny-od-review-symboli-i-historii-jobów) | Status importu plansz jest niezależny od review symboli i historii jobów | accepted | 2026-09-20 | browser staging przechowuje trwały boardImportStatus o wartościach ready, importing, boards_imported, failed. |
| [D-401](decisions/DECISION_LOG_2026.md#d-401--nierozstrzygnięte-źródło-v11-wraca-do-pełnej-ręcznej-geometrii) | Nierozstrzygnięte źródło v1.1 wraca do pełnej ręcznej geometrii | accepted | 2026-09-17 | lateralRegistrationCandidate jest wyłącznie roboczą propozycją. |
| [D-400](decisions/DECISION_LOG_2026.md#d-400--v11-jest-domyślnym-wyborem-nowych-stagingów-plansz) | v1.1 jest domyślnym wyborem nowych stagingów plansz | accepted | 2026-09-17 | brak geometryEngineVariant w raporcie, preflighcie i starcie importu przeglądarkowego oznacza… |
| [D-399](decisions/DECISION_LOG_2026.md#d-399--podmiana-źródła-przez-nową-rewizję-stagingu) | Podmiana źródła przez nową rewizję stagingu | accepted | 2026-09-16 | podmiana JPEG-a przed akceptacją jego ręcznej geometrii tworzy nowy, checksummowany staging. |
| [D-398](decisions/DECISION_LOG_2026.md#d-398--tylko-gotowy-staging-tworzy-nowy-import-plansz) | tylko gotowy staging tworzy nowy import plansz | accepted | 2026-09-16 | usunąć z publicznego API i panelu tokenowy start importu, lokalny picker importu i tokenowy preflight. |
| [D-397](decisions/DECISION_LOG_2026.md#d-397--v11-odzyskuje-tylko-niepewne-plansze-po-wyniku-bazowym) | v1.1 odzyskuje tylko niepewne plansze po wyniku bazowym | accepted | 2026-09-16 | v1.1 pozostawia wyniki przyjęte przez v1.0. Ukończony zgodny manifest v1.0 jest bazą ponownego użycia, a… |
| [D-396](decisions/DECISION_LOG_2026.md#d-396--v10-jest-domyślnym-wyborem-nowych-stagingów-plansz) | v1.0 jest domyślnym wyborem nowych stagingów plansz | superseded | 2026-09-16 | structured_lattice_v4_partial_sides zachowuje techniczny identyfikator, a w panelu jest nazwany v1.0 i… |
| [D-395](decisions/DECISION_LOG_2026.md#d-395--preflight-geometrii-używa-przypiętej-bazy-i-trwałych-shardów) | Preflight geometrii używa przypiętej bazy i trwałych shardów | accepted | 2026-09-16 | API przypina do inputu najnowszy zgodny ukończony manifest tej samej gry, selekcji i source manifestu. |
| [D-394](decisions/DECISION_LOG_2026.md#d-394--nowe-preflighty-wracają-z-polityki-słabych-obramowań-v3-do-v1v2) | Nowe preflighty wracają z polityki słabych obramowań v3 do v1/v2 | accepted | 2026-09-16 | nowe runy wariantu structured_lattice_v4_partial_sides przypinają v1 bez profilu niepełnych siatek albo v2 z… |
| [D-393](decisions/DECISION_LOG_2026.md#d-393--proporcja-cropa-jest-niezależną-bramką-jakości) | Proporcja cropa jest niezależną bramką jakości | accepted | 2026-09-16 | automatyczny crop przekraczający 78% kanonicznej wysokości źródła otrzymuje crop_too_tall przed oceną… |
| [D-392](decisions/DECISION_LOG_2026.md#d-392--błędy-workera-cropów-odzyskujemy-do-osobnego-preview) | Błędy workera cropów odzyskujemy do osobnego preview | accepted | 2026-09-15 | wpis session-v2.json.failures bez wyniku w shardzie może być przeliczony aktywnym v12 wyłącznie przez… |
| [D-391](decisions/DECISION_LOG_2026.md#d-391--listowanie-źródła-fill-nie-czeka-na-pomocniczy-zapis-sesji) | Listowanie źródła fill nie czeka na pomocniczy zapis sesji | accepted | 2026-09-15 | listowanie katalogu bazowego publikuje liczbę odwiedzonych wpisów i znalezionych obrazów co najwyżej co 64… |
| [D-390](decisions/DECISION_LOG_2026.md#d-390--ostatni-pomiar-przycinania-jest-pomocniczym-stanem-widoku) | Ostatni pomiar przycinania jest pomocniczym stanem widoku | accepted | 2026-09-15 | lokalny rekord IndexedDB może przechować ostatnią niepustą próbkę telemetrii przygotowania cropów, z nazwą… |
| [D-389](decisions/DECISION_LOG_2026.md#d-389--fill-przełącza-podgląd-przed-zapisem-z-dwoma-slotami-cofania) | Fill przełącza podgląd przed zapisem, z dwoma slotami cofania | accepted | 2026-09-15 | po fill'u workspace natychmiast ustawia lokalny target i następny sourceCursor, a następnie wykonuje… |
| [D-388](decisions/DECISION_LOG_2026.md#d-388--repair-przechowuje-stan-luk-nie-historię-interakcji) | Repair przechowuje stan luk, nie historię interakcji | accepted | 2026-09-15 | manual-image-selection-repair-v2.json zastępuje rosnący log napraw aktualnym stanem: aktywnymi plikami,… |
| [D-387](decisions/DECISION_LOG_2026.md#d-387--słaba-ozdobna-ramka-kieruje-kompletną-siatkę-do-walidacji) | Słaba ozdobna ramka kieruje kompletną siatkę do walidacji | accepted | 2026-09-15 | mocno zarejestrowana strona może zachować najwyżej trzy sloty ze słabym dowodem czerwonej ramki. |
| [D-386](decisions/DECISION_LOG_2026.md#d-386--ostrzeżenie-cropa-nie-jest-wyborem-ręcznej-poprawki) | Ostrzeżenie cropa nie jest wyborem ręcznej poprawki | accepted | 2026-09-15 | automatyczny powód review pozostaje poradą w filtrze Niepewne. |
| [D-385](decisions/DECISION_LOG_2026.md#d-385--obliczenia-cropów-są-równoległe-a-publikacja-uporządkowana) | Obliczenia cropów są równoległe, a publikacja uporządkowana | accepted | 2026-09-15 | koordynator analizuje stałe paczki najwyżej czterech zdjęć w puli 1–4 browserowych workerów, lecz publikuje… |
| [D-384](decisions/DECISION_LOG_2026.md#d-384--pusty-snapshot-cropów-może-przyjąć-aktywną-politykę) | Pusty snapshot cropów może przyjąć aktywną politykę | accepted | 2026-09-14 | wersjonowana sesja bez preparationPolicyVersion może automatycznie przypiąć aktywny v12 wyłącznie przed… |
| [D-383](decisions/DECISION_LOG_2026.md#d-383--automatyczna-niepełna-siatka-jest-propozycją-do-walidacji) | Automatyczna niepełna siatka jest propozycją do walidacji | accepted | 2026-09-14 | odroczony slot z kanonicznym automaticPartialProposal i poprawnym czteropunktowym symbolGridQuad należy do… |
| [D-382](decisions/DECISION_LOG_2026.md#d-382--v12-jest-głównym-silnikiem-nowych-sesji-cropów) | V12 jest głównym silnikiem nowych sesji cropów | accepted | 2026-09-14 | po jawnej ocenie podglądów przez operatora polityka… |
| [D-381](decisions/DECISION_LOG_2026.md#d-381--pełne-33-wystarcza-do-automatycznego-cropa) | Pełne 3×3 wystarcza do automatycznego cropa | accepted | 2026-09-14 | bezpośrednio wykryte dziewięć plansz jest wystarczającym dowodem cropa. |
| [D-380](decisions/DECISION_LOG_2026.md#d-380--niepełne-siatki-uczą-osobny-profil-bocznych-masek) | Niepełne siatki uczą osobny profil bocznych masek | accepted | 2026-09-14 | manual-geometry-qualification-v2 wprowadza jawny opt-in do oddzielnej puli bocznie uciętych siatek. |
| [D-379](decisions/DECISION_LOG_2026.md#d-379--lifecycle-partycji-jest-manifest-bound-i-checkpointowany-per-tabela) | Lifecycle partycji jest manifest-bound i checkpointowany per tabela | accepted | 2026-09-09 | - Provisioning i usuwanie wykonują najwyżej jedną tabelę manifestu w jednej transakcji, a receipt niezależny… |
| [D-378](decisions/DECISION_LOG_2026.md#d-378--lista-symboli-czyta-bieżącą-projekcję-partycji-gry) | Lista symboli czyta bieżącą projekcję partycji gry | accepted | 2026-09-09 | - V2 materializuje confidence razem z bieżącą komórką i listuje bez owner join oraz bez historycznych JSON-ów. |
| [D-377](decisions/DECISION_LOG_2026.md#d-377--zamknięty-schemat-game_data_v2-i-wspólny-koordynator-jobów) | Zamknięty schemat game_data_v2 i wspólny koordynator jobów | accepted | 2026-09-08 | - Wszystkie 65 game-owned tabel (również zależne małe metadane) ma LIST(game_id) i composite FK w jednym… |
| [D-376](decisions/DECISION_LOG_2026.md#d-376--trwałe-porcje-przed-usunięciem-legacy-i-migracją-partycji) | Trwałe porcje przed usunięciem legacy i migracją partycji | accepted | 2026-09-08 | - Osobny maintenance receipt i journal nie zależą FK od usuwanej gry. |
| [D-375](decisions/DECISION_LOG_2026.md#d-375--v0104-udostępnione-wyłącznie-jako-testowy-wariant-per-run) | v0.10.4 udostępnione wyłącznie jako testowy wariant per-run | accepted | 2026-09-08 | LATERAL_PARTIAL_RELEASED=True otwiera istniejący jawny wybór structured_lattice_v4_partial_sides. |
| [D-374](decisions/DECISION_LOG_2026.md#d-374--v0104-jest-rozszerzeniem-runu-nie-zmianą-polityki-gry) | v0.10.4 jest rozszerzeniem runu, nie zmianą polityki gry | accepted | 2026-09-07 | geometryEngineVariant=structured_lattice_v4_partial_sides przypina osobną politykę i checksumę w rollout… |
| [D-374](decisions/DECISION_LOG_2026.md#d-374--nowe-gry-wymagają-kompletnego-magazynu-v2) | Nowe gry wymagają kompletnego magazynu V2 | accepted | 2026-09-09 | po usunięciu wszystkich gier produkcyjny PostgreSQL nie tworzy location legacy. |
| [D-373](decisions/DECISION_LOG_2026.md#d-373--niedostępna-komórka-zachowuje-historię-nie-bieżący-obraz) | Niedostępna komórka zachowuje historię, nie bieżący obraz | accepted | 2026-09-07 | source_available jest addytywną projekcją dostępności bieżącej komórki. |
| [D-373](decisions/DECISION_LOG_2026.md#d-373--nowa-półautomatyczna-selekcja-czyta-lokalne-źródło-bez-stagingu) | Nowa półautomatyczna selekcja czyta lokalne źródło bez stagingu | accepted | 2026-09-08 | nowe runy workflowu selection używają schema v3 i małego, content-addressed manifestu lokalnego katalogu. |
| [D-372](decisions/DECISION_LOG_2026.md#d-372--szkic-nie-zastępuje-rewizji-a-pionowe-ucięcie-wymaga-poprawy-źródła) | Szkic nie zastępuje rewizji, a pionowe ucięcie wymaga poprawy źródła | accepted | 2026-09-07 | lokalne szkice geometrii zachowują bazową rewizję i wszystkie oznaczenia. |
| [D-372](decisions/DECISION_LOG_2026.md#d-372--półautomat-rezerwuje-miejsce-tylko-dla-swoich-rzeczywistych-danych) | Półautomat rezerwuje miejsce tylko dla swoich rzeczywistych danych | accepted | 2026-09-08 | browser staging semi_automatic_selection pomija ImageWriteCapacityGuard, którego estymacja obejmuje przyszłe… |
| [D-371](decisions/DECISION_LOG_2026.md#d-371--kwalifikacja-geometrii-jest-wersjonowaną-częścią-decyzji-slotu) | Kwalifikacja geometrii jest wersjonowaną częścią decyzji slotu | accepted | 2026-09-07 | manual-geometry-qualification-v1 używa istniejących pending_partial i unavailableCellIndices, dopuszcza… |
| [D-370](decisions/DECISION_LOG_2026.md#d-370--szeroki-licznik-symboli-ufa-gotowej-projekcji) | Szeroki licznik symboli ufa gotowej projekcji | accepted | 2026-09-07 | licznik całej gry bez filtra confidence zachowuje kanonicznego właściciela z… |
| [D-369](decisions/DECISION_LOG_2026.md#d-369--ewaluacja-symboli-wymaga-pokrycia-każdej-klasy) | Ewaluacja symboli wymaga pokrycia każdej klasy | accepted | 2026-09-06 | nowe iteracje używają wersjonowanej polityki source-family-class-stratified-split-v3. Całe rodziny źródłowe… |
| [D-369](decisions/DECISION_LOG_2026.md#d-369--archiwum-wyszukiwania-nie-zależy-od-operacyjnego-review) | Archiwum wyszukiwania nie zależy od operacyjnego review | superseded | 2026-09-07 | zachowywany zakres starej gry może zostać zamrożony w legacy_board_search_archive_documents. |
| [D-368](decisions/DECISION_LOG_2026.md#d-368--gotowość-rozliczonego-importu-jest-odtwarzana-z-api) | Gotowość rozliczonego importu jest odtwarzana z API | accepted | 2026-09-06 | kolejka bramki geometrii wylicza aktualny manifest z najnowszych rewizji decyzji i zwraca go razem z… |
| [D-368](decisions/DECISION_LOG_2026.md#d-368--overlay-pełnego-zdjęcia-jest-wystarczającym-podglądem-korekty-guard) | Overlay pełnego zdjęcia jest wystarczającym podglądem korekty guard | accepted | 2026-09-06 | Admin nie wymaga wygenerowania 15 cropów A/B przed zapisem korekty bramki importu. |
| [D-367](decisions/DECISION_LOG_2026.md#d-367--import-z-ręczną-korektą-zamiast-bramki-skuteczności) | Import z ręczną korektą zamiast bramki skuteczności | accepted | 2026-09-06 | nowa polityka image-geometry-systemic-guard-v2-manual-review kontynuuje import przy niskiej lub zerowej… |
| [D-367](decisions/DECISION_LOG_2026.md#d-367--operator-może-poprawić-także-pozytywny-slot-bramki-importu) | Operator może poprawić także pozytywny slot bramki importu | accepted | 2026-09-06 | wszystkie sloty źródła w raporcie bramki są edytowalne. |
| [D-366](decisions/DECISION_LOG_2026.md#d-366--pierwszy-import-materializuje-niewiadome-bez-fałszywej-inferencji) | Pierwszy import materializuje niewiadome bez fałszywej inferencji | accepted | 2026-09-06 | gra bez zatwierdzonych komórek, kohort, iteracji i aktywacji może wykonać jawny import… |
| [D-365](decisions/DECISION_LOG_2026.md#d-365--nieczytelność-pozostaje-właściwością-bieżących-pikseli) | Nieczytelność pozostaje właściwością bieżących pikseli | accepted | 2026-09-06 | zwykłe zatwierdzenie lub zmiana przypisanego symbolu zachowuje quality_issue=unreadable dla tej samej… |
| [D-364](decisions/DECISION_LOG_2026.md#d-364--wykluczenie-źródła-zamiast-mutowania-browser-stagingu) | Wykluczenie źródła zamiast mutowania browser stagingu | accepted | 2026-09-06 | zdjęcie odrzucone w korekcie geometrii jest wykluczane przez append-only decyzję związaną z grą, stagingiem,… |
| [D-363](decisions/DECISION_LOG_2026.md#d-363--czteropunktowy-obrys-całego-33-jako-kotwica-cropa) | Czteropunktowy obrys całego 3×3 jako kotwica cropa | accepted | 2026-09-06 | lokalny wariant v12 opisuje wiarygodny układ dziewięciu plansz czterema zewnętrznymi punktami i przenosi go… |
| [D-362](decisions/DECISION_LOG_2026.md#d-362--deferred-jest-obowiązkowym-slotem-źródła-nie-nieistniejącą-planszą) | Deferred jest obowiązkowym slotem źródła, nie nieistniejącą planszą | accepted | 2026-09-06 | lokalny edytor geometrii łączy istniejące review plansz z nierozwiązanymi rekordami… |
| [D-361](decisions/DECISION_LOG_2026.md#d-361--nachylone-etykiety-i-zachowanie-niezależnej-bramki) | Nachylone etykiety i zachowanie niezależnej bramki | accepted | 2026-09-05 | na kolejne zlecenie naprawy wdrożono poziomą dylatację oraz analizę etykiet w nachyleniu rzędu, bez… |
| [D-360](decisions/DECISION_LOG_2026.md#d-360--niezależny-odbiór-po-poprawce-bez-dopasowania-referencji-do-wyniku) | Niezależny odbiór po poprawce, bez dopasowania referencji do wyniku | accepted | 2026-09-05 | użytkownik zlecił naprawę TASK-0472. Stare dwa przypadki po analizie służą jako regresje; |
| [D-359](decisions/DECISION_LOG_2026.md#d-359--zatrzymanie-rollout-v11-po-nieudanej-bramce-jakości) | Zatrzymanie rollout v11 po nieudanej bramce jakości | accepted | 2026-09-05 | implementacja eksperymentalna pozostaje nieaktywna. |

---

# Najnowsze wpisy (pełne kopie)

Poniżej pełne kopie pięciu najnowszych wpisów (D-533..D-537), identyczne z `decisions/DECISION_LOG_2026.md`.
Przy dodaniu nowego wpisu usuń z tej sekcji najstarszą kopię.

## D-537 — Wypłata planszy w serii supergry, wynik prowizoryczny i koszt per pozycja

- **Date:** 2026-10-09.
- **Status:** accepted; TASK-0936 (etap S-C) w ramach zaakceptowanego planu
  `delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md` (D-535, D-536).
- **Decision:** plansza na pozycji objętej opublikowaną serią supergry jako jej
  spin jest liczona oceną planszy serii rodzaju gry; dla `wild_super_spins`
  (`evaluate_series_board`) obowiązują cztery kroki planu: `k` = liczba
  kolumn planszy oryginalnej z super symbolem `X` (także niesąsiednich);
  przekształcenie tylko przy `k ≥ minimum_match_length(X)` — wtedy kolumny są
  w całości wypełnione `X` i przykrywają symbole pod spodem, także Wildy;
  linie liczone na planszy rozwiniętej, sztuki symbolu uruchamiającego na
  oryginalnej; wygrane liniowe `X` są zastępowane wartością
  `payout_line(X, k) × liczba aktywnych linii`, wygrane innych symboli
  zostają; koszt spinu 0. Przy `k < minimum(X)` plansza jest liczona jak w
  trybie bazowym. Plansza wyzwalająca serię pozostaje w trybie bazowym.
  Wynik ma osobne składowe (linie, sztuki, rozwinięcie); rodzaj supergry
  udostępnia ocenę planszy w rejestrze (`SuperGameKindDefinition.evaluate_series_board`).
- **Provisional:** wynik planszy serii jest `exact` tylko dla planszy w pełni
  znanej, ze zdefiniowanym super symbolem i przy świeżej generacji serii;
  brak symbolu (także symbol, który w liczonej wersji reguł nie jest zwykłym
  symbolem liniowym), `superGameState.fresh = false` albo jakakolwiek
  nieznana komórka daje `provisional`. Wynik prowizoryczny nie jest dolnym
  ograniczeniem (rozwinięcie może dodać albo przykryć wygraną), dlatego nie
  wchodzi do rozpoznanych wypłat, narastających sum ani bilansu; podsumowanie
  pokazuje osobno liczbę takich pozycji (`provisionalCount`, także z wypłatą 0)
  i ich sumę (`provisionalPayoutCredits`). `confirmed_minimum` w trybie
  `super` nie występuje. Przy `superGameState.fresh = false` prowizoryczna
  jest **każda** oceniona plansza gry, także w trybie bazowym, bo nowy
  trigger mógł już objąć ją serią (decyzja leada po audycie Codex TASK-0936,
  zgodnie z planem, który ma pierwszeństwo przed pierwotnym brzmieniem tego
  wpisu).
- **Cost per position:** projekcja per pozycja (`mode`, symbol, pozostałe
  spiny, koszt, wypłata, rodzaj wypłaty) powstaje z jednego odczytu znaczników
  supergry TASK-0935 (jedno zapytanie, jeden snapshot ze znacznikami wierszy
  i `superGameState`); zapytanie jest teraz tekstowym SELECT-em, więc router
  magazynu gry wiąże je z intencją odczytu i działa w migawce tylko do odczytu
  zapisu stawki. Przybliżona wygrana §D i kalkulator stawek panelu sumują koszt
  per pozycja; brakująca plansza w serii zużywa darmowy spin. Podsumowanie
  odpowiedzi niesie dokładne zakresy darmowych spinów (`superSpinRanges`,
  `superSpinCost`), z których klient liczy wykres, piny i wkład (start w
  serii nie wymaga wkładu). Kalkulator zakresu i szczegóły planszy czytają
  reguły, plansze, znaczniki i stan w jednej migawce `REPEATABLE READ` sesji
  żądania (dla wszystkich gier; dla 777 bez zmiany liczb), szczegóły panelu
  w osobnej migawce. Świeży podgląd panelu zwraca kalkulację, którą zapis by
  zamroził. Zamrożony wynik zostaje w formacie 1, a pola `superSpinRanges`,
  `superSpinCost` i niezerowe pola prowizoryczne jego podsumowania są
  zapisywane tylko wtedy, gdy niosą informację.
- **Boundaries:** gra bez rodzaju supergry (777) ma wszędzie tryb bazowy i
  stały koszt; jej liczby, odcisk danych, zamrożony wynik i skrót treści są
  bajt w bajt takie jak przed zmianą (test regresji na fixture v3). Zapisana
  wcześniej historia panelu nie jest przeliczana. Reguła „× liczba linii” i
  wypłaty za sztuki w kredytach bezwzględnych (Z-1) czekają na weryfikację na
  pierwszej serii z pełnymi zdjęciami; rozbieżność to korekta rodzaju w kodzie,
  nie w danych. Aplikacja mobilna i prekomputacja wydań poza zakresem.

## D-536 — Serie supergry: manifest v6, licznik wejścia i generacje

- **Date:** 2026-10-09.
- **Status:** accepted; TASK-0933 w ramach zaakceptowanego planu
  `delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md` (D-535).
- **Decision:** serie supergry są danymi pochodnymi wyprowadzanymi z komórek
  pociętych plansz z przypisanym symbolem (decyzja człowieka albo predykcja),
  przechowywanymi w czterech nowych tabelach gry (`super_game_series`, tabela
  robocza generacji, stan wyprowadzania i audyt super symbolu). Nowa tabela gry
  wymaga nowej wersji manifestu własności, dlatego migracja `0152` wprowadza
  manifest v6 (v5 plus dokładnie cztery tabele) i przenosi lokalizacje gier na
  v6; downgrade odmawia, gdy istnieje zdefiniowany super symbol, wpis audytu
  albo aktywny job wyprowadzania.
- **Input version:** każdy zapis zmieniający wejście wyprowadzania (predykcje
  i ich usunięcie, korekty symboli i siatki, materializacja plansz importu,
  role symboli, rodzaj gry, `expected_layout_count`, publikacja reguł, reset
  gry i usuwanie źródeł) podbija licznik `input_version` gry w tej samej
  transakcji; lista punktów zapisu jest wyliczona w kodzie i pilnowana testem
  statycznym w obie strony oraz testami PostgreSQL na realnych operacjach.
  Nieaktualność serii wynika z porównania `input_version` z wersją
  opublikowanej generacji, bez osobnej flagi.
- **Generations:** job `super_game_series_derive` (lane `general`, jeden
  w kolejce na grę) buduje kompletną generację w tabeli roboczej partiami,
  publikuje ją w jednej transakcji pod blokadą wiersza stanu i odrzuca
  kandydata przy zmianie wersji wejścia, kolejkując dokładnie jeden ponowny
  przebieg; tożsamość serii `(game_id, trigger)` zachowuje super symbol i
  rewizję przy przedłużeniu retriggerem. Kompletność porównuje rzeczywisty
  koniec serii z ostatnią znaną pociętą planszą, także na końcu sekwencji.
- **Cleanup:** job wyprowadzania blokuje czyszczenie jak każdy inny job
  (`ACTIVE_GAME_JOB`); po czyszczeniu podbicie licznika kolejkuje nowe
  wyprowadzenie. Odczyty listy, plansz serii i stanu świeżości wykonują się
  w jednym snapshocie `REPEATABLE READ`, żeby seria i `fresh` pochodziły z
  tej samej generacji.
- **Boundaries:** pole `superGameState` w odpowiedziach wyszukiwania plansz i
  kalkulacji dostarcza TASK-0935; wypłaty serii TASK-0936; `apply_board_repoint`
  nie jest punktem zapisu (zmienia tylko identyfikatory geometrii).

## D-535 — Gra Mumie: Wild, symbol uruchamiający supergrę i rodzaj supergry „Wild super spins”

- **Date:** 2026-10-08.
- **Status:** accepted; plan `delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
  (TASK-0929–0939) zaakceptowany przez operatora po czterech przeglądach
  Codex zakończonych PASS (v1.7.264).
- **Decision:** dotychczasowy „Joker” nazywa się w UI i dokumentach „Wild”
  (kolumna `symbols.is_wildcard` zostaje). Symbol dostaje w katalogu gry
  osobną rolę „Uruchamia supergrę” z progiem 3/4/5 sztuk na pociętej
  planszy (`super_game_trigger_count`); jego reguły wypłat są wypłatą za
  liczbę sztuk na planszy, niezależnie od pozycji. Gra ma rodzaj supergry
  (`super_game_kind`, domyślnie `none`); pierwszy rodzaj `wild_super_spins`:
  10 darmowych spinów o koszcie 0 na kolejnych pozycjach sekwencji, ≥N
  symboli uruchamiających w serii przedłuża ją o 10 bez nowego symbolu,
  super symbol (zwykły symbol wylosowany przez automat, widoczny jako złota
  ramka) rozwija się na całe kolumny i przykrywa symbole pod sobą, liczy się
  liczba kolumn (także niesąsiednich) od progu symbolu, wypłata = wypłata
  liniowa × liczba linii. Mechanika rodzajów jest zaszyta w kodzie w
  rozszerzalnym rejestrze; operator steruje rolami i rodzajem z Adminu.
- **Series and data:** serie wyprowadzane deterministycznie z komórek z
  przypisanym symbolem (także predykcje plansz `pending`), tylko plansze
  pocięte; sekwencja startuje w trybie bazowym; brakująca plansza w serii
  jest pusta i zużywa spin. Super symbol definiuje operator ręcznie.
  Nieaktualność serii wynika z licznika wejścia per gra; wynik planszy serii
  bez symbolu, w stanie nieaktualnym albo z nieznaną komórką jest
  prowizoryczny, nie dolnym ograniczeniem. Role w katalogu są niezmienne po
  publikacji wersji reguł używającej symbolu; testy na drafcie przez wybór
  wersji reguł w Adminie.
- **Boundaries:** 777 i 777 v2 bez zmian zachowania (bramka regresji);
  aplikacja mobilna poza zakresem do odrębnej decyzji; wersjonowanie ról
  per wersja reguł poza zakresem; trening modelu złotej ramki po pilocie.
- **Process:** audyt krzyżowy po każdym tasku (TASK-0929 daje skill);
  operator 2026-10-08 zdecydował, że wszystkie taski wykonuje ta sesja
  Claude Code przez subagentów według tabeli planu, a audyt Codex jest do
  czasu dostępności CLI zastępowany niezależnym subagentem Claude z innym
  modelem niż wykonawca. Etap T (TASK-0938 przed S-B, TASK-0939 równolegle)
  obniża zużycie tokenów bez obniżania jakości, z pomiarem.

## D-533 — Points/machines panel with durable stake saves and whole-panel links

- **Date:** 2026-10-07.
- **Status:** accepted explicit whole-plan implementation request, T1–T7 /
  TASK-0921–0927, MANAGEMENT_PANEL_EXECUTION_PLAN.md.
- **Decision:** add Panel Administracyjny with points (name/city/street), named
  machines and editable active-game assignments. Archive/detach preserves saves
  and audit. Six independent stakes20/10/6/4/2/1.20PLN save query/start/range and
  zero to six pinned spin positions only on explicit **Zapisz układ**. Confirmed
  Clear removes only the current choice. Symbol corrections retain immediate
  game-wide semantics. Recalculate current results on opening and preserve
  immutable previous numeric/chart/start-symbol/rules versions in history.
- **Consistency:** PostgreSQL owns data, stable identity independent of name,
  compact deduplicated result versions, no image blobs. Mutation/audit atomic,
  operation-bound receipts and revision conflicts; no historical deletion UI.
- **Access:** local admin and one known recipient. Named link plus separate code
  gives full module management across assigned active games. Link administration
  stays local; unrelated Admin/model/import/rules operations excluded. Separate
  multi-game session/proxy with expiry/revoke/lockout; old one-game links retain
  scope. Add48/72h options to new panel and old board-search shares, default8h.
- **Operations:** local first, existing Reviewer ingress, computer availability
  required. No new Redis/accounts/hosting/synchronization, automatic service
  lifecycle, production data manipulation, push or deployment. User controls
  API/Admin and rollout. See requirements/architecture/MANAGEMENT_PANEL.md.
- **T2 transaction clarification:** mutation/receipt locks use READ COMMITTED;
  a bounded read-only REPEATABLE READ application-role game session captures
  coherent rows/rules/start symbols. Numeric snapshots represent that read
  instant; result/slot/receipt/audit commit together in the primary transaction.
  This preserves concurrent exact retries without privileged database reads.
- **T5 authorization clarification:** public requests bind the originating
  session UUID in a header, or asset URL, in addition to the dedicated cookie.
  Equal human labels never share actor/receipt identity. Session locks and
  post-flush authorization checks protect commit; obsolete-tab failures cannot
  clear a newer browser session. Panel-link creation and automatic shared
  ingress shutdown share a transaction lock. These implement the accepted
  access and retry boundary without broadening old one-game capabilities.

## D-534 — Image import resumption uses the hard reserve, not the GC target

- **Date:** 2026-10-07.
- **Status:** accepted explicit repair instruction, TASK-0928.
- **Decision:** source ingestion and in-flight image pipeline checks use the
  configured hard reserve in every job stage, including persisted
  `waiting_for_storage`; default 5 GiB and equality allowed. The 80 GiB GC
  target cannot become a separate condition for restarting an import.
- **Liveness:** retain durable checkpoint/requeue and fenced leases. The
  polling worker waits its existing positive interval after storage deferral
  rather than entering an immediate reclaim loop. Restarted code interprets
  existing storage-wait checkpoints with the same reserve, without changing
  their job identity or reprocessing settled source checkpoints.
- **Preserved:** conservative admission estimates, reserve override,
  warning/automatic-GC/GC-target thresholds, deletion eligibility and all
  domain/sequence/source protections. No schema or API shape change.
- **Operations:** the user separately authorizes only the general-worker
  restart after tests for the existing Mumie import. API/Admin, cleanup,
  manual state mutation, push and merge are outside this authorization.
