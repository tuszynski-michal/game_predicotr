---
title: Laboratorium geometrii plansz i rozpoznawania symboli — plan wykonawczy
status: accepted
last_updated: 2026-09-27
---

# Laboratorium geometrii i symboli

## Stan, cel i granice

Obecny worker ma geometrię i `SpatialSymbolCnn` dla aplikacji, a historyczny
eksperyment keypoint (D-262) pozostał shadow. Prototyp `screen_layout_v3`
(TASK-0648) i hybryda 777 pokazują błędy na zasłonięciach, refleksach i
skrajnych planszach. Budujemy lokalne laboratorium do oglądania siatek,
poprawiania anotacji, treningu i porównywania kandydatów. Startujemy od
hybrydy; bezpośrednia sieć węzłów jest wymiennym silnikiem uruchamianym
warunkowo. Kandydat trafia później do aplikacji wyłącznie jako review/shadow.

Laboratorium obsługuje topologie **5 kolumn × 3 wiersze** i **3 × 3**.
Integracja z obecną aplikacją obejmuje tylko 5 × 3; pełne 3 × 3 wymaga
osobnego planu zależności od 15 komórek. Historyczne 777 ma uczestniczyć
w uczeniu geometrii z nowych ręcznych siatek labu (D-453); bramki symboli
pozostają odrębne. 777 V2 jest osobną grą. Pracujemy w bieżącym katalogu na gałęzi
przygotowanej przez użytkownika. Nie ma automatycznego push, merge, aktywacji
modelu ani wdrożenia. Liczności zdjęć i podziałów zapisuje manifest konkretnej
wersji danych, a nie ten plan.

## Dane, etykiety i podziały

### Aktualny wariant B — zatwierdzony pilot D-456

Operator zatwierdził realizację pilota na obecnych danych 2026-09-27.
T03k wdraża osobną politykę podziału całymi grami, bez verified rodzin
wewnątrz gry i bez measurement. Nie zmienia istniejących polityk ani zgód.
Wymagania pełnego protokołu rodzin i czasu opisane dalej są odroczone dla
tego pilota, nie uznane za spełnione. Po T03k z aktualnym zamrożonym splitem
wykonujemy kolejno T04 i T05, z osobnymi audytami i commitami, do STOP B.

Przydział ustalony przed wynikami: development 777/blazing zd/gang zd,
validation mumie wybrane, final_test reels, unseen_game tresure zd.
63 zdjęcia i 180 siatek 5 × 3 dają 90/30/30/30 siatek. Pełny katalog,
duplikaty i powiązania także poza targetami nie mogą przeciąć przydziałów.
Podział jest niezmienny; nie losujemy ponownie po słabym wyniku.
T05 ocenia development/validation; final_test/unseen pozostają nietknięte
do końcowego odbioru. Brak oceny symboli, 3 × 3 i oszczędności czasu.
Limit treningu i brak automatycznej aktywacji pozostają bez zmian.

T03k i T04 odebrane (v1.7.28/v1.7.29). Kontrakt techniczny T05/D-457
jest zapisany przed kodem i wynikami w TASK-0670: image-only propozycje,
MobileNetV3-Small refinement, homografia, unknown-mask bez presence-head,
image-macro walidacja z karą za braki, gate uncalibrated i ONNX w galerii.
Kontrakt ma PASS audytu pre-code Astra medium; wykonawca pozostaje
Sol high. Kod i dokładne żądania runów podlegają audytowi przed treningiem,
a artefakty po treningu. Brak dopasowania propozycji do targetu pozostaje raportowanym
błędem, a nie cicho odrzuconą próbką. Dotychczasowy baseline bez zmian.

T05 odebrany technicznie2026-09-27: smoke1ep/10steps oraz train20ep/200steps
w568,53s, checkpoint20/best1, ONNXparity i model w galerii PASS. Audyty
pre-code/kodu/requestów/artefaktów Astra medium PASS. DEVscore0,153640529
vsbaseline0,156461470; VAL0,046985619 vs0,046131665 — brak poprawy walidacji,
bez rekomendacji promocji. Pełne mianowniki90/30 obejmują missing15/1.
Dokładnie dwa runy, dane rev268 niezmienione, holdouty zamknięte. STOP B.
Raport: `../quality/VISION_LAB_HYBRID_20260927.md`; dalszy etapC wymaga
jawnego uruchomienia, bez dodatkowego tuningu lub aktywacji w tej pracy.

### Wznowienie B po przeglądzie operatora

Użytkownik zaakceptował wybrane geometrie i polecił kontynuację etapu B po
zakończeniu równoległego toru zmian. Zgoda obejmuje lokalizację/siatkę, nie
poprawność symboli na zdjęciu lub ich etykiet. Geometrie mogą zawierać pojedyncze
pomyłki; nie traktujemy deklaracji „większość poprawna” jako gwarancji jakości.
T03 wykonuje odczytowy preflight aktualnych akceptacji, SHA/rewizji, topologii,
węzłów, źródeł i podziałów. Błąd symbolu nie jest automatycznie błędem geometrii;
błędna geometria wymaga korekty przed wykorzystaniem próbki. Nie tworzymy
zatwierdzeń symboli z akceptacji zdjęcia i nie uruchamiamy etapu C.

Raport preflight rozdziela kontrolę mechaniczną, ocenę wizualną i dowody
niezależności źródeł. Kandydaci z nazw oraz brak duplikatu SHA nie dowodzą
odrębnych nagrań. T04 nadal wymaga ukończonego T03 i zamrożonego podziału;
nie obchodzimy tej zależności. Niejasne pochodzenie blokuje zależny trening,
ale nie odczyt danych i przygotowanie raportu. Decyzja D-453 rozstrzyga
użycie historycznych zdjęć 777 w modelu geometrii: targetami są nowe ręcznie
zatwierdzone siatki labu, nie dawne geometrie v1.1. Zastępuje ograniczenie
D-447 tylko w tym zakresie, bez zmiany historycznego pochodzenia na 777 V2.
Obecne role i niezmienne snapshoty pozostają nietknięte. Jawna kwalifikacja
geometrii jest wdrożona i odebrana w T03e według kontraktu TASK-0668,
z zachowaniem ważnych zgód niezmienionych źródeł i bramek symboli.
Geometry-only purpose nie zmienia zachowania legacy splitów ani ról.
Rzeczywiste apply kwalifikacji wykonał T03h po imporcie T03g; zamrożenie
splitu nadal wymaga rozstrzygnięcia rodzin i pozostałych bramek danych.

Operator deklaruje, że zdjęcia pozostałych pięciu gier z
`C:\Users\tuszy\Documents\game_predictor_traning_set` pochodzą z innych
zakresów/folderów nagrań niż wskazane do dotychczasowych siatek; ocenia je
jako odległe brzegi nagrań, oddzielone kilkoma katalogami. Nie wyprowadzamy
tej deklaracji z nazw ani nie ponawiamy ogólnego pytania o pochodzenie.
Pozostaje mapowanie konkretnych źródeł do rodzin i kontrola konfliktów:
brzegi tego samego filmu pozostają jedną rodziną, a różne foldery nie
dowodzą niezależnych filmów. T03 pozostaje `blocked` na mapowaniu rodzin
i zamrożonym podziale; T04/T05 nie rozpoczęto.

Dowody i wynik: TASK-0668 oraz
`ai_docs/quality/VISION_LAB_STAGE_B_DATA_PREFLIGHT.md`. Wykonawca T03
`gpt-6-sol` / `medium`, niezależny audyt `gpt-6-astra` / `medium` według
końcowej tabeli. T04/T05 zachowują `gpt-6-sol` / `high` i audyt Astra medium.

Kontynuacja T03 po doprecyzowaniu operatora: oba zakresy Treasure mają
konkretne katalogi zapisane w TASK-0668; Mumie są wiązane przez seq i wskazany
katalog źródłowy. Wykonawca przygotowuje pełną mapę dowodów oraz dry-run
istniejącego podziału na kopii stanu. Raport
`ai_docs/quality/VISION_LAB_SOURCE_MAPPING_20260927.md` rozdzieli rzeczywiste
dowody, deklaracje i unresolved; brak JSON sam nie unieważnia deklaracji.
Realne zapisy wymagają audytu dokładnej propozycji i przejścia istniejących
bramek, bez automatycznego verified z prefiksów lub fikcyjnego pomiaru.
Nie ponawiać rozstrzygniętych pytań o Treasure. Zakres pozostaje T03;
przypisanie wykonawcy i audytora nie zmienia się.

Wynik kontynuacji: mapa 1466 źródeł i 365 metadanych, siedem requestów
unresolved po audycie zapisanych z backupem i kontrolą nowych procesów.
436 powiązań, rewizja 267; 180 siatek i 63 akceptacje bez zmian. Dry-run v2
nie przechodzi nadal bramki VERIFIED_MEASUREMENT_SOURCES_REQUIRED.
Wariant pilotażu całymi grami bez pomiaru czasu został następnie zatwierdzony
w D-456. T03k zastępuje bramkę danych dla pilota; pełny protokół pozostaje
odroczony, bez deklaracji jego spełnienia.

D-447 dopuszcza dwa jawnie różne źródła etykiet: zatwierdzenie w aplikacji i
`lab_human_approved`. Laboratorium zapisuje tożsamość gry i wersję słownika,
obraz oraz SHA-256, planszę, komórkę, rewizję geometrii, dokładny crop oraz
SHA-256, etykietę, rewizję zatwierdzenia i czas decyzji. Zmiana geometrii lub
cropa wyłącza próbkę z treningu do ponownego zatwierdzenia. Predykcja nie jest
zatwierdzeniem. Gra bez rekordu DB ma lokalną tożsamość i ręcznie zatwierdzony
słownik; rejestracja w aplikacji wymaga jawnego mapowania gry i symboli.
Istniejące reguły zatwierdzeń DB pozostają bez zmian.

Eksporter działa w głównym środowisku tylko do odczytu. Manifest wejściowy
ogranicza źródła, ich dostępne rewizje, metadane pochodzenia, słowniki,
powiązane zatwierdzone etykiety i historyczne 777. Dotychczasowy format
eksportu zapisuje dla niego rolę porównawczą; mechanizm kwalifikacji
geometrii D-453 dostarczył T03e, a realne apply wykonał T03h. Transakcja
`REPEATABLE READ READ ONLY` jest krótka, ma limity czasu i partie. Snapshot
publikuje się atomowo po sprawdzeniu kompletności i checksum. Pierwotny wynik
`selective_board_review_v1_1` i późniejsza ręczna reweryfikacja to odrębne
pozycje; brak pierwotnej rewizji oznacza brak porównania.

Manifest wejściowy v1 ma `schemaVersion`, `datasetName` i listę
`{gameId, sourceImageId, expectedSourceSha256, sourceFamilyId, role}`;
`role` rozróżnia zwykłe dane, historyczne 777 i zadeklarowane 777 V2.
Snapshot ID jest SHA-256 kanonicznego wejścia, wersji eksportera i
zamrożonych identyfikatorów/rewizji DB. Pierwsza krótka transakcja przypina
dokładne ID, rewizje i fingerprinty wierszy. Kolejne krótkie transakcje
czytają tylko te ID i sprawdzają fingerprint; drift lub brak rekordu
odrzuca publikację. Kolejność: freeze metadanych → eksport partiami →
kopia zarządzanych obrazów z kontrolą SHA → tymczasowy manifest z checksumami
→ fsync plików → atomowy rename na tym samym wolumenie. Retry z tym samym
fingerprintem weryfikuje snapshot i zwraca go; konflikt kończy błędem.

Folder `777` zachowuje historyczne pochodzenie także przy kwalifikacji
do geometrii według D-453. 777 V2 wymaga deklaracji użytkownika dla nagrania/rodziny źródeł
oraz kontroli konfliktów checksum i podobieństwa. Brak trafienia podobieństwa
nie dowodzi niezależności. Sprzeczne lub nierozstrzygnięte źródła są wyłączone
z treningu. Ten projekt nie uzupełnia slotów siecią w reweryfikacji
historycznego 777 (TASK-0645–0647).

Anotacja ma trzy warstwy: lokalizacja (obecność, topologia, cztery narożniki),
pełna geometria (wszystkie węzły i granice komórek) oraz symbole (dokładny
crop i klasa). Interpolacja z narożników jest propozycją, nie referencją
pełnej siatki. Pilot: do 40 zdjęć na grę z co najmniej 10 rodzin, jeśli są
dostępne; początkowe 30 pełnych siatek na kombinację gra–topologia. Pierwsze
10 zdjęć na grę mierzy czas anotacji. Niedobory i rozszerzenia są jawne.

Podział grupuje nagrania/rodziny, duplikaty i pochodne obrazu. Przed pierwszym
treningiem geometrii zamrażamy development, validation, final test i grę
niewidzianą przez geometrię. Na STOP A pokazujemy kandydatów; domyślnie grę
o środkowej liczbie niezależnych rodzin, bez zabrania jedynej topologii z
treningu. Wybór zapisuje T03 przed treningiem. Jeśli dane nie wystarczają,
raportujemy brak wiarygodnego testu między grami. Symbole mają własny podział
per gra.

## Kontrakty, środowisko i bezpieczeństwo

Wznowienie etapu A (2026-09-26): użytkownik dostarczył surowe JPEG-i w
`C:\Users\tuszy\Documents\new_traning_set` i katalog danych laboratorium.
T02 obejmuje przygotowanie snapshotu plikowego tego wejścia, obok obsługi
snapshotów eksportera DB z T01. Import zachowuje oryginały, publikuje kopie
z SHA-256 atomowo i nadaje lokalne tożsamości gry/źródła. Nie tworzy rekordów
DB, zatwierdzeń, podziału train/test ani etykiet. W etapie A wszystkie zdjęcia
służyły podglądowi/testowaniu, a folder `777` otrzymał `comparison_only`.
Ten zapis opisuje wcześniejszy stan i istniejący snapshot; aktualną
politykę użycia geometrii określa D-453, bez automatycznej zmiany danych.
Prefiksy nazw są wyłącznie kandydatami rodzin do sprawdzenia w T03.
Liczność galerii nie rozszerza budżetu pilota anotacji ani treningów.

Proponowane `GeometryEngine`, `GeometryResult` i `SymbolRecognizer` pozwalają
podmienić `baseline`, `hybrid` i `neural_grid` bez zmiany odbiorców. Wynik
zawiera źródło, topologię, plansze, wszystkie węzły, pochodzenie punktów,
wersję modelu i powody korekty. Układ plansz na ekranie jest oddzielony od
`BoardTopology` pojedynczej planszy. 5 × 3 ma 24 węzły, 3 × 3 ma 16.
Nie wymuszamy dziewięciu plansz; nieobecność, zasłonięcie i nieczytelność są
odrębne. Bramki sprawdzają kolejność, przecięcia, dodatnie pola i kompletność
bez zależności od jednego algorytmu OpenCV.

Hybryda używa lekkiego `MobileNetV3-Small`, narożników, perspektywy i
opcjonalnego lokalnego dopasowania. Pełna sieć przewiduje węzły bezpośrednio.
Symbole porównują RGB, szarość powieloną do 3 kanałów i fuzję z udziałem RGB
`0`, `0,1`, `0,2`, `0,3`, bazując na `SpatialSymbolCnn`. Każdy wariant ma
wersję preprocessingu. Kalibracja i wybór są tylko na walidacji; niezgodność
modeli oznacza niepewność. Testy obejmują wiśnia–winogrono, refleksy i
kontrolowane zmiany barwy.

Proponowany FastAPI `game_predictor_worker.vision_lab` działa na
`127.0.0.1:8102`, Next.js `apps/vision-lab` na `127.0.0.1:3102`.
Zajęty port zgłasza błąd bez zabijania procesu. Frontend używa proxy Next.js
z zamkniętą listą tras. FastAPI jest właścicielem OpenAPI i osobnego
generowanego klienta; kontrola wchodzi do głównego `openapi:check` i
`quality`. Oba wejścia HTTP kontrolują `Host`; zapis wymaga dozwolonego
`Origin` i JSON, także przez proxy. Assety mają zarejestrowane identyfikatory,
bez ścieżek podanych przez klienta. Brak tunelu.

Dane poza repo: `C:\Users\tuszy\Documents\game_predictor_vision_data`.
Niezmienne manifesty, zarządzane kopie obrazów, anotacje, checkpointy i
raporty zapisują się atomowo. T03 obejmuje backup i próbę odtworzenia.
Laboratorium nie importuje `storage`, `psycopg` ani produkcyjnego handlera
treningu; produkcyjne punkty wejścia nie importują `vision_lab`; neutralny
rdzeń nie zależy od laboratorium ani bazy. Eksporter jest osobnym narzędziem.

Izolowane środowisko przypina PyTorch `2.12.1`, torchvision `0.27.1` i CUDA
13.0: najpierw pakiety CUDA, potem projekt z constraints, na końcu kontrola
wersji, `torch.version.cuda`, GPU i krótkie obliczenie. Główne środowisko
pozostaje nietknięte; integracja CPU używa ONNX Runtime. Checkpoint v2
zawiera optimizer, scheduler, RNG, konfigurację i checksumę danych. Odczyt v1
pozostaje możliwy, lecz nie obiecuje identycznego numerycznie wznowienia.

## Zadania i punkty STOP

Każdy task ma własny audyt, commit, Outcome i aktualizację `CURRENT_STATE.md`.
Polecenie uruchomienia etapu obejmuje wszystkie jego taski. P00 zapisuje plan,
reguły pracy etapami i D-447, a **nie uruchamia A**.

| Etap | Task | Wynik i bramka |
|---|---|---|
| P00 | [TASK-0665](../tasks/completed/0665-vision-lab-plan.md) | Plan, dokumenty, zadania i spójne reguły; stary plan zastąpiony. |
| A | [TASK-0666](../tasks/completed/0666-vision-lab-export.md) | Ograniczony eksporter read-only; bez częściowych snapshotów. |
| A | [TASK-0667](../tasks/completed/0667-vision-lab-gallery.md) | Kontrakty, baseline, galeria i bezpieczne lokalne API; błędny obraz nie zatrzymuje galerii. |
| B | [TASK-0668](../tasks/0668-vision-lab-geometry-annotations.md) | Edytor, warstwowy zbiór, backup, zamrożony split i pomiar kosztu. |
| B | [TASK-0669](../tasks/completed/0669-vision-lab-training-core.md) | Done: neutralny rdzeń, trwały backend runów, izolowane GPU, checkpoint v2 i odczyt v1; bez przepięcia produkcji. Audyt Astra medium PASS. |
| B | [TASK-0670](../tasks/completed/0670-vision-lab-hybrid.md) | Done: hybryda, checkpoint w galerii i ONNX; audyty PASS. Walidacja bez poprawy, brak promocji. STOP B. |
| C | [TASK-0671](../tasks/0671-vision-lab-symbol-labels.md) | T06a done: narzędzia DB/lab, audyt i testy PASS. T06b blocked: brak rzeczywistych zatwierdzeń i kwalifikacji symboli; T07–T09 nieuruchomione. |
| C | [TASK-0672](../tasks/0672-vision-lab-symbol-models.md) | RGB, szarość, fuzja, kalibracja i metryki per klasa. |
| C | [TASK-0673](../tasks/0673-vision-lab-training-panel.md) | Panel start/cancel/postęp/retry i historia korzysta z trwałego backendu T04. |
| C | [TASK-0674](../tasks/0674-vision-lab-validation.md) | Walidacja i zamrożenie modelu/progów przed testem. |
| D | [TASK-0675](../tasks/0675-vision-lab-neural-grid.md) | Warunkowa sieć pełnych węzłów; brak danych daje konkretny plan anotacji. |
| E | [TASK-0676](../tasks/0676-vision-lab-geometry-integration.md) | Review/shadow tylko 5 × 3, 3 × 3 jawnie nieobsługiwane w aplikacji. |
| E | [TASK-0677](../tasks/0677-vision-lab-symbol-integration.md) | ONNX, pochodzenie i mapowanie; dopiero teraz przepięcie handlera na wspólny rdzeń. |
| E | [TASK-0678](../tasks/0678-vision-lab-final-acceptance.md) | Zamrożony test, niewidziana gra, restart i raport bez automatycznej aktywacji. |

**STOP A:** galeria, manifest, kandydaci gry testowej, cele anotacji per gra,
lista pobrań i budżet B; koszt czasu jest wstępny. **STOP B:** wynik hybrydy,
rzeczywisty czas anotacji i błędy. **STOP C:** raport walidacji i rekomendacja.
**STOP D:** kandydat lub raport brakujących danych. **STOP E:** kandydat
review/shadow i ograniczenia. Każdy etap wymaga jawnego uruchomienia. Przed
wydatkiem lub operacją poza zatwierdzonym zakresem następuje stop.

### Brama skali przed wdrożeniem v3 — nie jest zadaniem obecnego pilota

Teraz badamy wykonalność geometrii, cięcia i rozpoznawania symboli na
ograniczonym zbiorze. Nie wymagamy w tym pilocie jakości 100% ani
przebudowy magazynu laboratoryjnego. Po wyniku pilota operator może
przygotować nowe dane i wytrenować oba modele od początku; obecne
checkpointy i etykiety nie są obowiązkowym wejściem produkcyjnym.

Przed propozycją produkcyjnej aktywacji lub masowego przetwarzania v3
trzeba odrębnie sprawdzić docelową skalę, także scenariusz orientacyjny
20 gier × 500 000 plansz × 15 pól = 150 mln potencjalnych cropów.
To założenie planistyczne, nie zmierzona liczność ani zgoda na tworzenie
takiego fixture'u. Odbiór musi objąć liczbę gier i źródeł, rozmiar danych,
czas i pamięć odczytu/zapisu, przepustowość oraz wznowienie po przerwaniu.
Należy rozdzielić mały, plikowy magazyn laboratorium od produkcyjnych
partycji `game_data_v2`; nie zakładać, że obecny `state.json`, pełne skany
lub pobieranie 500 miniatur nadają się na skalę produkcyjną. Trzeba
zweryfikować model przechowywania obrazów, geometrii, etykiet i pochodnych
cropów, indeksy/filtrowanie per gra, ograniczone strony i porcje jobów.
Konkretne progi czasu, pamięci i przepustowości ustala się dopiero dla
rzeczywistego profilu użycia, przed pomiarem — nie dopisuje ich po wyniku.

Brak profilu, brak pomiaru na reprezentatywnych danych albo niespełnione
progi oznaczają **STOP: nie wdrażać v3 produkcyjnie**. Wtedy wymagany jest
osobny plan zmiany zapisu/przetwarzania z migracją i ponownym odbiorem;
nie wykonywać migracji, masowego importu ani treningu w ramach tego wpisu.
Ograniczony pilot i porównanie review/shadow mogą trwać bez tej bramy,
o ile nie są przedstawiane jako gotowość produkcyjna.

Budżet początkowy T05 i T10: do 50 kroków testowych oraz jeden trening do
20 epok lub 30 minut. T07: dwa treningi (RGB, szarość), każdy do 20 epok lub
30 minut; fuzja używa ich wyników. Dostępne zależności, wagi i koszt pokazuje
się przed etapem. Trening ma kontrolowany PID, timeout i raport postępu.

T04 jest właścicielem trwałego protokołu runów backendu; T08 dodaje panel
jako klienta tego kontraktu. Kanoniczny
fingerprint wiąże manifest danych, konfigurację, model, topologię,
preprocessing i seed. Trwały `requestId` z identycznym payloadem zwraca ten
sam run po utracie odpowiedzi; inny payload daje konflikt. Backend zapisuje
`queued` przed startem procesu, a `running` wiąże PID, czas startu, token
lease i heartbeat. Terminalne stany to `succeeded`, `failed`, `cancelled`;
panel nie obiecuje pauzy. Po restarcie żywy proces jest tylko obserwowany,
a dopiero potwierdzony brak zgodnego PID/czasu utworzenia wraz z wygasłym
lease pozwala na recoverable `failed`, bez drugiej kopii. Żywy proces
pozostaje obserwowany nawet przy starym heartbeat. Cancel utrwala intencję
i kończy proces po checkpointcie. T04 nalicza budżet trwale poza checkpointem;
crash i retry nie zwracają kroków ani niepotwierdzonego czasu.
Jawne retry tworzy nową próbę tego samego runu po sprawdzeniu fingerprintu
i nowym lease; stary token nie może zapisać. `succeeded` wymaga atomowego
raportu i checksum artefaktów.

## Pomiar, mapa wymagań i kontrole

### Bootstrap T06 w etapie C

Operator uruchomił etap C po T05. Preflight wykazał pusty zbiór słowników i
etykiet symboli. Dlatego T06a buduje narzędzia ich jawnego zatwierdzania,
natomiast T06b zachowuje wymagania kwalifikacji rzeczywistego zbioru.
Ukończenie narzędzi nie oznacza ukończenia T06, T03 ani zgody na trening.
T06b i zależne T07–T09 zatrzymują się przy braku danych lub niezbędnej
decyzji operatora. D-453/D-456 pozostają wyłącznie geometryczne.
Każde podzadanie ma osobny audyt i commit. Szczegółowy kontrakt techniczny:
[T06a](VISION_LAB_SYMBOL_LABELS_CONTRACT.md), wymagany przed kodowaniem.

### Pomiar geometrii

W T03, przed hybrydą, zamrażamy rozłączne zestawy baseline/hybryda. Losujemy
przydział w obrębie gry i trudności. Użytkownik nie poprawia tego samego
zdjęcia obiema metodami; materiał nie trafia do treningu. Referencja jest
oceniana bez informacji o silniku. Aktywny czas wyklucza przerwę > 30 s.
Raport obejmuje czas, liczbę korekt i końcową jakość. Redukcja 30% to cel
badany, a wynik małej próby jest wstępny.

| Wymaganie | Zadania | Dowód |
|---|---|---|
| Wymiana hybrydy na sieć | T02, T05, T10 | Jeden kontrakt i niezmienieni odbiorcy. |
| Wczesny podgląd | T02, T05 | Galeria przed treningiem, potem pierwszy checkpoint. |
| Obie topologie w labie | T02–T05, T10 | 24/16 węzłów i właściwe cropy. |
| Integracja tylko 5 × 3 | T11–T13 | 3 × 3 odrzucone bez modyfikacji danych. |
| Pochodzenie etykiet | P00, T06, T12 | Typ decyzji, SHA cropa, mapowanie gry. |
| Geometria 777 i brak przecieku | T01, T03, T09, T13 | D-453: nowe ręczne siatki, jawna kwalifikacja, pochodzenie i rozłączne rodziny; bez zatwierdzania symboli. |
| Refleksy i kolor | T07, T12, T13 | Wiśnia–winogrono, per klasa, test zmiany barwy. |
| Ochrona HTTP | T02 | Obcy Host/Origin, prosty POST i obca trasa odrzucone. |
| Trwałość i izolacja | T03, T04, T08 | Restart, backup, importy, checkpoint v1/v2. |
| Praca etapami | P00 i taski | Audyt, commit, Outcome i STOP etapu. |

D-261 obowiązuje przy późniejszej aktywacji domyślnej; liczby zdjęć w folderze
nie zastępują wymaganej liczby źródeł, plansz, kategorii i jakości. D-262
pozostaje odniesieniem do wcześniejszego eksperymentu. Testy zmienionego
przepływu poprzedzają lint/typecheck i uzasadnione szersze kontrole. `quality`
obejmuje generowany kontrakt labu. Nie uruchamia się nieograniczonych prób.

Zatrzymanie w trakcie etapu następuje przy sprzeczności wymagań, brakującej
koniecznej decyzji, niedostępnym modelu/reasoning, nierozwiązanych P0–P2 po
dwóch cyklach poprawek albo przed operacją/kosztem poza zakresem. Jeden
wykonawca naraz zapisuje kod, a audytor pracuje w osobnej sesji. Modelu nie
podmienia się niejawnie. Sama tabela modeli nie jest zgodą na delegowanie;
wyraźne polecenie etapu jest taką zgodą. Reguła właścicielska jest w
`AGENTS.md`.

T02 dostarczył galerię, snapshot plikowy i adapter baseline. Wyniki kontroli,
kandydat gry testowej oraz granice STOP A są zapisane w
`quality/VISION_LAB_STAGE_A_ACCEPTANCE.md`. Nie wykonano instalacji środowiska
GPU ani treningu hybrydy. Porty, gałąź, dostępność GPU i wolne numery są
ponownie sprawdzane na początku odpowiednich etapów.

## T03b — uproszczenie zatwierdzania i następna plansza (wdrożone)

Na polecenie użytkownika zapisano podzadanie dla laboratorium 3102,
z uruchomieniem implementacji całości: stały niewidoczny `operator`, odstępy
między przyciskami, pełne zatwierdzenie samym jawnym kliknięciem bez
dodatkowego checkboxa oraz przejście do następnej pozycji na tym samym
zdjęciu dopiero po potwierdzonym zatwierdzeniu. Szkic nie zmienia pozycji.
Po pozycji 9 nie przechodzimy na inne zdjęcie ani automatycznie na pozycję 10.
Nie oznacza to wymagania dziewięciu plansz dla każdego źródła ani zmiany
kontraktu topologii. Istniejące zapisy następnej pozycji są wczytywane,
nie nadpisywane. Szczegóły, błędy i regresje: T03b w TASK-0668.

T03b obejmuje również wszystkie powiadomienia laboratorium w toastach
w lewym dolnym rogu, bez bannerów sukcesu/błędu/ostrzeżenia w body.
Kolory: zielony/czerwony/pomarańczowy; timeout4 s dla wszystkich rodzajów,
pauza hover/focus/hidden, zamknięcie kliknięciem body. Przycisk Kopiuj zamiast
Zamknij kopiuje tylko wiadomość, bez zamykania; sukces dopiero po clipboard,
błąd lokalny w toaście bez alertu/rekurencji. Korekta T03b z2026-09-27;
testy fakeclock/pauzy/kolejka, clipboard success/fail oraz niezależność retry.
Szczegółowy kontrakt dostępności, kolejki i retry zapisano w TASK-0668.

Rozszerzenie użytkownika: liczniki obecnych pełnych siatek, lokalizacji i szkiców
na zdjęciu, filtry całej gry przed paginacją, statusy pozycji 1–9 i istniejących
dalszych, dokładne wczytanie zapisanej geometrii oraz klikalne numerowane obrysy
na pełnym zdjęciu. Filtr „Z pełną siatką” oznacza co najmniej jeden taki zapis,
nie kompletność zdjęcia ani kwalifikację treningową. Stan anotacji ma jednego
właściciela. Zgodnie z korektą T03d nawigacja porzuca niezapisane zmiany
bez potwierdzenia; busy/pending nadal blokuje nawigację w aplikacji.
Testy obejmują ponowny odczyt, aktualizację po zapisie, paginację i różne topologie.

## T03e — jawna kwalifikacja geometrii historycznego 777

**Status:** `done`, wznowienie B przez użytkownika 2026-09-27.
Podzadanie TASK-0668 realizuje D-453, bez zmiany niezmiennych snapshotów,
importów produkcyjnych ani zgód symboli. Pełny kontrakt i testy poniżej
w aktywnym TASK-0668. Nie oznacza domknięcia bramki danych całego T03.

Jeden atomowy request kwalifikuje dokładne źródła, SHA i bieżące mapy rewizji
zaakceptowanych zdjęć. Decyzja jest przechowywana w AnnotationStore z jego
CAS, receipt, historią i backupem, nie w równoległym magazynie. CLI domyślnie
wykonuje odczytowy preview; apply ponownie waliduje identyczny request.
Jawny zakres geometry i wersja polityki odróżniają nowe splity od starych;
pełne ręczne targety są odrębne od ogólnej mapy anotacji. Role i
training_eligible źródeł pozostają bez zmian. Kwalifikacja 777 nie omija
rodzin, fotoakceptacji, pomiaru ani rozłączności podziału.

Istniejące odpowiedzi API dostają additive stan; istniejący split request
opcjonalny purpose z zachowaniem dotychczasowego zachowania przy pominięciu.
OpenAPI, generowany klient, wrapper i test odpowiedzi są aktualizowane razem.
Brak nowego endpointu/UI. Szczegóły bezpieczeństwa i regresje określa task.
Rebase zachowuje dotychczasowy zakres i jawnie odrzuca kwalifikacje, dopóki
ich przenoszenie nie będzie osobno wdrożone. To ograniczenie nie usuwa zapisów.

Aliasy Reels i kohorta wejściowa to osobny kolejny pion T03, nie część T03e.
Przed realnym apply potrzebny jest dokładny preview i kopia stanu; trening
nie rozpoczyna się przed pozostałymi bramkami T03. Wykonawca Sol medium,
audyt Astra medium, osobny commit/Outcome; brak automatycznego push.
Backend 54/54, klient 5/5, lint/typecheck i kontrola kontraktu PASS;
niezależny audyt PASS bez P0–P2. W odbiorze samego T03e wykonano tylko preview
11 zdjęć / 30 siatek; późniejszy T03g/T03h wykonał import/rebase i kwalifikację.
Pełne wyniki i osobne commity w Outcome odpowiednich podzadań TASK-0668.

## T03f — jawna kohorta targetów geometrii

**Status:** `done`; kontrakt i kod odebrane, niezależny audyt Astra medium
PASS bez P0–P2. Podzadanie TASK-0668 po odebranym T03e; nie zamyka
T03 i nie uruchamia T04/T05. Wykonawca `gpt-6-sol` / `medium`, audyt
`gpt-6-astra` / `medium`. Pełny zakres, błędy, pliki i testy w sekcji T03f taska.

Opcjonalne geometry_source_ids=None zachowuje dokładnie dotychczasowy
legacy i geometry T03e, wraz z receipts. Jawna niepusta unikalna kohorta
(do 10000 znanych ID) dozwolona tylko dla purpose geometry. Pełny graf
całego Catalog po SHA/rodzinach/powiązaniach pozostaje źródłem grup.
Role/D-453 i verified provenance dotyczą wszystkich członków komponentu;
approval/photoacceptance/full human target wymagane są tylko od wybranych.
Aliasy poza kohortą nie otrzymują zgód, assignments ani targetów.

Wersja lab-geometry-cohort-split-v1 zamraża posortowaną kohortę, kompletne
leakage_components oraz fingerprints pełnych Source/StoredFamily i kwalifikacji
każdego członka niedata (jawny null przy braku) wszystkich komponentów katalogu.
Pola wchodzą do fingerprintu nowego splitu;
stare wyniki i retry nie są przepisywane. Gry/unseen, difficulty i niezależność
grup pomiarowych ocenia się na całych komponentach, a pokrycie topologii
wyłącznie na wybranych pełnych human targetach. Measurement musi należeć
do kohorty i nigdy nie rozdziela powiązanej grupy między pomiar i trening.

Mutacja jest atomowa przez istniejący AnnotationStore/CAS/receipt/history.
_view kontroluje pełny graf/fingerprints nowej wersji oraz skuteczność D-453
wszystkich członków niedata komponentów zakwalifikowanych do assignments,
także niewybranych mostów. Stała niekwalifikowana grupa całkowicie wykluczona
nie daje stale; aliasy nie dostają targetów. Konserwatywne stale po zmianie także poza kohortą
pozostaje; retry/reaccept go nie usuwa. Backup/restore zachowują nowe dane.
Addytywne istniejące API /splits, OpenAPI/generated client, wrapper i test
requestu aktualizowane spójnie; bez nowego endpointu/UI lub magazynu decyzji.

DoD: alias SHA bez skopiowania zgody, przechodnie powiązania przez niewybrane
źródła, wszystkie bramki provenance/role/unseen/measurement/topology,
legacy receipts w nowym procesie, atomicity/race/retry, pełne fingerprints,
stale, backup/restore oraz zgodny API/client. Implementacja odebrana:
backend 78 różnych przypadków PASS (w tym dziewięć regresji rebase),
klient6, Ruff/mypy/TypeScript i OpenAPI/generated checks PASS.
Małe izolowane fixture; timeouty do 120 s, bez benchmarków.
Audyt Astra medium PASS, niezależnie backend24 i klient6; commit v1.7.22
i pełny hash w Outcome TASK-0668. Realny import/rebase/apply/freeze,
automatyczne potwierdzanie rodzin, symbole i trening poza tym pionem.

## T03g/T03h — operacje danych po kontroli T03

T03g `done`: zaudytowany addytywny import 473 zdjęć i rebase zachowujący
993 stare źródła, 180 siatek i 63 akceptacje. Nowy snapshot/store, backup
i pełny raport pochodzenia; brak nowych zgód, zmiany ról, rodzin i splitu.
Świeże procesy po restarcie potwierdziły integralność i already_applied.
Raport: `ai_docs/quality/VISION_LAB_ADDITIVE_DATA_20260927.md`.

T03h `done`: po osobnym commicie T03g zastosowano istniejącą kwalifikację D-453
do 11 zaakceptowanych zdjęć / 30 siatek 777 na nowym store. Preview dokładnego
requestu, backup, CAS/apply, nowy proces i identyczne retry PASS; geometrie,
akceptacje i role niezmienione. Audyt przed i po zapisie PASS bez P0–P2.
Rewizja 260, jeden nowy event/receipt; nie jest to wykonany trening.
Pełne kontrakty, pliki, błędy i kryteria obu operacji zapisuje TASK-0668.
Wykonawca obu Sol medium, audyt Astra medium, osobny commit każdego podzadania.
Nie potwierdzać automatycznie rodzin, nie zamrażać splitu i nie rozpoczynać
T04/T05 bez brakujących danych. Bez automatycznego startu usług i treningu.

## T03i — odzyskanie metadanych selekcji z Kosza

Na jawną zgodę operatora z 2026-09-27 przeszukać Kosz i odzyskać wyłącznie
projektowe metadane selekcji do nowego katalogu `recovered_metadata` pod
`Documents/game_predictor_vision_data`. Kopiowanie zachowuje Kosz, bez
nadpisywania plików, przywracania zdjęć i filmów oraz bez zmian anotacji.
Znaleziono dziewięć kandydatów JSON; zakres, kontrola SHA i ponownego odczytu,
analiza pokrycia oraz kryteria odbioru są w T03i aktywnego TASK-0668.
Odzyskane pochodzenie jest dowodem pomocniczym, nie automatyczną weryfikacją
rodzin ani zgodą na freeze lub trening. Status: `done` — dziewięć kopii,
trwały manifest, świeży odczyt i niezależny audyt Astra medium PASS bez P0–P2.
Pokrycie nazw 121/473, zgodność SHA obrazów 0/121; pełny raport w
`ai_docs/quality/VISION_LAB_RECOVERED_METADATA_20260927.md`. Osobny commit
i pełny hash zapisuje Outcome T03i. Nadrzędny T03 nadal blocked.

## T03j — kwalifikacja targetów 777, D-455

Jawnie zatwierdzone 2026-09-27. Nowa opcjonalna polityka requestu istniejącego
POST /splits zwalnia wyłącznie niewybrane historyczne folderowe 777
comparison_only z posiadania własnej kwalifikacji geometrii. Targety zawsze
wymagają własnej D-453, SHA/rewizji, akceptacji i pełnej ręcznej geometrii.
Pełny graf, verified całego komponentu, unseen, measurement i fingerprints
pozostają bez osłabienia. Brak nowych zgód, danych ani endpointu.
Stare requesty/receipts, None oraz istniejące v1 frozen splity zachowują reguły.
Kontrakt, konkretne pliki, regresje i bramki odbioru: T03j w TASK-0668.
Status `done`; Sol medium, niezależny audyt Astra medium PASS bez P0–P2.
Backend 76/76, klient 7/7 i kontrole jakości PASS; osobny commit w Outcome.

## T03k — pilot całymi grami, D-456

`done`. Jawna nowa polityka splitu z mapą wszystkich gier, bez
measurement i bez zmiany unresolved na verified. Pełne SHA/families/related
nie mogą przecinać partycji, także poza targetami. Pełny kontrakt, pliki,
błędy, testy i bezpieczne apply opisuje T03k w TASK-0668. Po audycie kodu
i exact requestu freeze z backupem, nowym procesem, retry i manifestem.
T03k done z aktualnym splitem otwiera T04/T05 tylko dla pilota; pełny
protokół T03 pozostaje odroczony. Osobny commit i audyt Sol medium/Astra medium.
Odbiór: 82 backend + 8 client, lint/typecheck/OpenAPI i niezależny audyt
kodu/danych PASS. Freeze rev268, 63 zdjęcia/180 siatek, create-only manifest,
backup/restore i retry w nowych procesach PASS; szczegóły w Outcome T03k.

## T14 — końcowe ujednolicenie toastów w aplikacjach webowych


**Status:** `todo`, zaplanowane na polecenie użytkownika; bez implementacji
w tej turze i poza automatycznym zakresem etapu B. Ostatnie zadanie
refaktoryzacyjne po dotychczasowym T13, uruchamiane osobno.

**Cel/scope:** wszystkie ekrany aplikacji webowych (Admin, Reviewer,
laboratorium i inne webowe powierzchnie ustalone przy inwentaryzacji)
korzystają z tego samego komponentu i kontraktu toastów T03b. Usunąć
rozproszone bannery/statusy sukcesów, ostrzeżeń i błędów w body. Nie usuwać
danych, instrukcji, potwierdzeń wymagających decyzji ani stanu blokad operacji.
Aplikacja mobilna wyłączona; ewentualne poprawki mobilne są osobnym torem.

**Dependencies/wykonanie:** wspólna baza sprawdzona w T03b; przed kodowaniem
zinwentaryzować każdy ekran i producenta komunikatów, uzupełnić osobny task
według TASK_TEMPLATE o sprawdzone pliki i testy. Relevant docs: wymagania
oraz architektura każdego migrowanego obszaru, AGENTS, PLAN_STANDARD,
TASK-0668/T03b. Potwierdzony istniejący wzorzec to lokalny toast w
`apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`
i `.toast` w sąsiednim module CSS, obecnie z timeoutem 4 s.
Nie tworzyć równoległych systemów powiadomień. Nie zmieniać kontraktów API,
reguł zatwierdzeń, retry, danych ani mobilnych konsumentów przy okazji.

**Acceptance/testy planowane:** macierz ekran → komunikaty → test;
widoczność po scrollu/nawigacji wewnątrz aplikacji, poprawne kolory i treści,
4 s oraz Kopiuj/ręczne zamknięcie body, dostępność klawiaturą/czytnikiem,
kolejka bez utraty błędów, brak kopii w body, brak zasłaniania kluczowych
kontrolek na małych ekranach, regresje istniejącego workflow zapisu i retry.
Najpierw testy danego pionu, lint/typecheck, następnie build i browser
każdej aplikacji. Skończone komendy z limitem do 120 s. Audyt przed commitem;
nierozwiązane P0–P2 po dwóch cyklach wymagają zatrzymania.

**Outcome:** zapisano zakres; wdrożenie i testy jeszcze niewykonane.
T14 nie zastępuje odbioru modelu T13 i nie odblokowuje treningu.

## Przypisanie modeli do zadań

T03d: zlecony przegląd zdjęcia z poprawkami wybranych plansz oraz dodatkową
bramką akceptacji. Rozszerzenie 2026-09-27: Szybki przegląd ukrywa inne panele,
pokazuje całe zdjęcie ze wszystkimi zapisanymi siatkami i dwa przyciski
Zatwierdź/Odrzuć → następne po sukcesie. Kolejka katalogu full/present/review;
reject całego zdjęcia (rejected=false dla starych danych) bez edycji geometrii
lub masowych issues, stan Do poprawy do jawnego accept. Snapshot wyświetlonych
rewizji/SHA, loadguard, ref-lock, exactretry/pending i monotoniczność chronią
decyzje. Szczegółowe pliki, granice i testy w rozszerzeniu T03d TASK-0668.
Dotychczasowy przegląd pozostaje narzędziem korekty z dodatkową
bramką akceptacji. Istniejący POST /annotations rozszerzony o decyzje review;
SHA i mapa wszystkich rewizji chronią zestaw przed wyścigiem. Mark→zapis→
ponowny przegląd→jawny accept; withdraw wycofuje błędne zgłoszenie.
Akceptacja niepustego zestawu full/present nie wymaga9 i nie promuje szkiców.
Zmiana zdjęcia unieważnia jego akceptację, split wymaga jej dodatkowo.
Statusy/filtry/cropy i toasty korzystają ze wspólnego stanu. Stare dane i
backup/rebase zachowują historyczne decyzje; domyślnie nieprzejrzane. Testy
kontraktu, race/retry/restart i UI oraz granice w T03d TASK-0668 i D-450.
Korekta ergonomii T03d z 2026-09-27: istniejący przegląd całego zdjęcia
domyślnie zwinięty przy wejściu; ręczne rozwijanie przez natywne `details`.
Wyłącznie usunięcie `open`, regresja UI, lint/typecheck i zgodna dokumentacja;
bez nowego stanu, API lub zmiany danych. Przypisanie modeli T03d bez zmian.
Kolejna korekta T03d: usunięcie window.confirm i beforeunload z laboratorium.
Nawigacja świadomie porzuca lokalny szkic bez autosave/autoapproval; busy/
pending, CAS i retry pozostają. Jawny przycisk reconcile działa bez modalu.
Regresje obejmują brak dialogów, brak zapisów przy nawigacji i blokadę pending.

T03c (done po T03b): aktualizacja niezmiennego snapshotu folderu istniejącym
importerem i bezpieczne przeniesienie anotacji do nowego katalogu. Preflight
kontroluje wszystkie zapisane referencje także w historii; zmienione id/SHA/
metadane oraz rodziny lub split blokują. Jawne apply zachowuje cały payload,
zmienia tylko powiązanie snapshot_id i zapisuje osobny raport pochodzenia.
Retry nie nadpisuje istniejącego/nowszego celu. Testy i kryteria w T03c TASK-0668.
Bez zmiany roli 777, treningu i zmian API; realną operację wykonuje koordynator
po audycie, zachowując oba snapshoty i oba katalogi anotacji.

T03a (podzadanie TASK-0668, zlecone 2026-09-26) poprawia wyłącznie ergonomię
laboratorium: duży edytor i zwarte cropy, stabilne etykiety, dopasowanie kadru
po puszczeniu uchwytu i automatyczny preview bieżących węzłów. Zgodne
rozszerzenie POST `/geometry` o opcjonalne `preview_board` używa istniejącego
croppera. Podgląd pozostaje nietrwały. Szczegóły i kryteria są w aktywnym
TASK-0668; bramka danych T03 pozostaje obowiązująca.

Decyzja użytkownika z 2026-09-26: audyt wykonuje najmniejszy model
wystarczający do ryzyka; najwyższa dopuszczona konfiguracja audytora to
`gpt-6-astra`, reasoning `medium`. Najtrudniejsze zadania wykonuje najwyżej
`gpt-6-sol` / `high`; trudne i bardzo trudne `gpt-6-sol` / `medium`.
Dla pozostałych wybieramy `gpt-5.6-terra` / `high` albo `xhigh`, jeśli
wystarcza do zakresu. Dostępny poziom `xhigh` odpowiada określeniu użytkownika
„very high”; nie istnieje osobny parametr o tej nazwie. Konfiguracje są
potwierdzone w narzędziu agentów bieżącej sesji. W razie zmiany dostępności
obowiązuje ponowna weryfikacja, bez niejawnego zamiennika.
Tabela określa dalsze wykonanie i ewentualne ponowienia. Zakończone P00/T01
zachowują historyczny zapis faktycznych wykonawców i audytów w Outcome.


| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| P00 / TASK-0665 | `gpt-5.6-terra` | `high` | Spójność wymagań, decyzji i reguł etapów. | `gpt-6-sol`, `medium` |
| T01 / TASK-0666 | `gpt-6-sol` | `medium` | Ochrona DB i snapshotu. | `gpt-6-astra`, `medium` |
| T02 / TASK-0667 | `gpt-6-sol` | `medium` | Kontrakt UI/API i HTTP. | `gpt-6-astra`, `medium` |
| T03 / TASK-0668 | `gpt-6-sol` | `medium` | Trwałość anotacji i podziały. | `gpt-6-astra`, `medium` |
| T03a / TASK-0668 | `gpt-6-sol` | `medium` | Transformacja widoku i aktualność cropów bez zapisów. | `gpt-6-astra`, `medium` |
| T03b / TASK-0668 | `gpt-6-sol` | `medium` | Jawna zgoda, retry i bezpieczne przejście między zapisami plansz. | `gpt-6-astra`, `medium` |
| T03c / TASK-0668 | `gpt-6-sol` | `medium` | Zachowanie zatwierdzeń i atomowe powiązanie z nowym snapshotem. | `gpt-6-astra`, `medium` |
| T03d / TASK-0668 | `gpt-6-sol` | `medium` | Trwałe review zdjęcia, wersje geometrii i zgodny pion API/UI. | `gpt-6-astra`, `medium` |
| T03e / TASK-0668 | `gpt-6-sol` | `medium` | Kwalifikacja geometry-only, trwałość decyzji i ochrona podziałów. | `gpt-6-astra`, `medium` |
| T03f / TASK-0668 | `gpt-6-sol` | `medium` | Jawna kohorta targetów z pełnym grafem przecieku i zgodnością receipts. | `gpt-6-astra`, `medium` |
| T03g / TASK-0668 | `gpt-6-sol` | `medium` | Addytywny snapshot, pełna kontrola zachowania zapisów i restart. | `gpt-6-astra`, `medium` |
| T03h / TASK-0668 | `gpt-6-sol` | `medium` | Jawny zapis D-453, backup i idempotencja bez zmiany geometrii. | `gpt-6-astra`, `medium` |
| T03i / TASK-0668 | `gpt-6-sol` | `medium` | Bezpieczne odzyskanie metadanych i rozróżnienie powiązań nazw od pikseli. | `gpt-6-astra`, `medium` |
| T03j / TASK-0668 | `gpt-6-sol` | `medium` | Wąska zmiana kwalifikacji targetów z ochroną grafu, wersji i receipts. | `gpt-6-astra`, `medium` |
| T03k / TASK-0668 | `gpt-6-sol` | `medium` | Wersjonowany podział całymi grami, ochrona grafu i trwały freeze pilota. | `gpt-6-astra`, `medium` |
| T04 / TASK-0669 | `gpt-6-sol` | `high` | Izolacja, trwały protokół runów i checkpointy. | `gpt-6-astra`, `medium` |
| T05 / TASK-0670 | `gpt-6-sol` | `high` | Geometria i trening. | `gpt-6-astra`, `medium` |
| T06 / TASK-0671 | `gpt-6-sol` | `medium` | Słowniki i tożsamość cropów. | `gpt-6-sol`, `medium` |
| T06a / TASK-0671 | `gpt-6-sol` | `medium` | Narzędzia, adaptery i trwałe zatwierdzenia symboli. | `gpt-6-sol`, `medium` |
| T06b / TASK-0671 | `gpt-6-sol` | `medium` | Rzeczywisty zbiór, pochodzenie i bramki danych. | `gpt-6-sol`, `medium` |
| T07 / TASK-0672 | `gpt-6-sol` | `medium` | Kalibracja i odporność na kolor. | `gpt-6-astra`, `medium` |
| T08 / TASK-0673 | `gpt-5.6-terra` | `high` | UI gotowych kontraktów. | `gpt-5.6-terra`, `high` |
| T09 / TASK-0674 | `gpt-6-sol` | `medium` | Ocena dowodów i wybór kierunku. | `gpt-6-astra`, `medium` |
| T10 / TASK-0675 | `gpt-6-sol` | `high` | Sieć obu topologii. | `gpt-6-astra`, `medium` |
| T11 / TASK-0676 | `gpt-6-sol` | `medium` | Rewizje i przepływ 5 × 3. | `gpt-6-astra`, `medium` |
| T12 / TASK-0677 | `gpt-6-sol` | `high` | ONNX, pochodzenie i regresja produkcji. | `gpt-6-astra`, `medium` |
| T13 / TASK-0678 | `gpt-6-sol` | `medium` | Test końcowy i odbiór. | `gpt-6-astra`, `medium` |
| T14 / końcowa refaktoryzacja web | `gpt-6-sol` | `medium` | Wspólny komponent i regresje komunikatów w wielu aplikacjach. | `gpt-6-astra`, `medium` |
