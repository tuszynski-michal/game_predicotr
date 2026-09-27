---
title: Laboratorium geometrii i symboli — architektura
status: accepted
last_updated: 2026-09-28
---

# Architektura laboratorium wizji

T05 rejestruje `hybrid-mobilenet-v1` leniwie: odkrywanie trenerów przez API
nie importuje torch. `hybrid_data` jest obrazowym adapterem propozycji/cropu,
matchingu i metryki; `hybrid_model`/`hybrid_training` działają tylko w workerze,
a `hybrid_inference` używa CPU ONNX Runtime. BaselineEngine pozostaje domyślny.
Opcjonalny `run_id` w istniejącym POST /geometry jest rozłączny z manual preview.
Przed Catalog.image sprawdza się completed run, aktualny manifest, dozwoloną
partycję i zamknięty protokół; holdout daje HOLDOUT_NOT_RELEASED.

`hybrid_protocol` wiąże kanoniczny preset, pełny SHA pretrained wag i wersję
generatora. Create-only kopia w LAB/cache/protocols jest sprawdzana wraz z
rzeczywistymi wagami przed etapami cyklu życia. Opcjonalny protocol_digest
w StartRunRequest jest usuwany z canonical request, jeśli None: istniejące
receipts/fingerprinty/bindingi T04 pozostają identyczne. Checkpoint i raport
zawierają pełny preset. Deterministyczny CUDA runtime wymaga ustawienia cuBLAS
przed inicjalizacją, deterministic algorithms oraz zamrożonych buforów BatchNorm;
gwarancja odtworzenia dotyczy zgodnego sprzętu i bibliotek, nie dowolnego GPU.

RunManager publikuje fenced immutable `onnx` i `best_weights` oraz ich SHA.
Wskaźniki pochodzą wyłącznie z serwera, nie z dowolnych ścieżek w metrics.
Oddzielne best_state w checkpointcie zachowuje wybraną epokę; resume nadal
odtwarza ostatnią ukończoną epokę. Deadline obejmuje eksport i publikację.
Parity odrzuca także NaN/Inf, zanim porówna tolerancje. Proces workera ma UTF-8
logi niezależne od domyślnej strony kodowej Windows. Lista modeli i odczyt
ponownie sprawdzają SHA artefaktów; galeria pokazuje tylko jawnie wybrany model.

Szybki przegląd używa istniejącego POST /annotations: PhotoReviewRequest ma
additive reject, PhotoReview.rejected domyślnie false. CAS/SHA/mapa i receipt
chronią reject jak accept. Reject czyści zaakceptowaną mapę bez geometrii/issues;
tylko accept usuwa rejected. photo_accepted wyklucza rejected. Historia,
backup i rebase zachowują pole. QuickReview ma lokalną stabilną kolejkę i
snapshot wyświetlonej mapy/rewizji, loadguard źródła oraz blokadę pending/ref;
stare odpowiedzi nie powodują przejścia ani obniżenia wspólnego stanu.

T03d rozszerza istniejący POST /annotations o PhotoReviewRequest, a stan o
photo_reviews z domyślnym pustym zbiorem. Source SHA i mapa rewizji wszystkich
pozycji są sprawdzane pod tym samym exclusive/CAS co zapis, przed decyzją.
Review przechowuje aktora/czas, zaakceptowaną mapę i oddzielne issues
needs_correction/needs_review; historia i receipts zachowują zdarzenia.
Zapis geometrii unieważnia akceptację zdjęcia; accept zamyka needs_review tylko
dla full/present, a needs_correction blokuje. Nie ma dodatkowego resolve.
Klient generowany z OpenAPI; panel korzysta ze wspólnego AnnotationState.
Rebase uwzględnia bieżące/historyczne referencje review. Freeze wymaga aktualnej
akceptacji obok dotychczasowej kwalifikacji; nigdy nie zmienia roli źródła.

CLI `vision_lab.rebase_annotations` przenosi payload anotacji pomiędzy dwoma
zweryfikowanymi Catalog, wyłącznie do nowego katalogu. Domyślny preflight jest
bez zapisu; `--apply` ponownie czyta aktualny state pod blokadą exclusive.
Sprawdza referencje bieżących anotacji, timingów, requestów i wyników historii,
całe metadane Source oraz zgodność receipts. Rodziny/split i nieznany format
blokują operację. Zmienia tylko state.snapshot_id (digest katalogu, odrębny od
snapshotId manifestu); oryginalny payload i obrazy pozostają nietknięte.
State i checksummed rebase-report z digestami wejścia/wyjścia publikowane są
w jednym rename tymczasowego katalogu na tym samym wolumenie. Retry akceptuje
tylko identyczny raport i payload; istniejący nowszy cel kończy konfliktem bez
nadpisania. API należy zatrzymać przed końcowym apply i uruchomić na nowych
ścieżkach. Import zdjęć pozostaje istniejącym snapshot.import_folder.

UI ma jednego właściciela AnnotationState dla galerii, geometrii i rodzin.
Odczyt GET /annotations oraz wyniki zapisu odświeżają ten stan monotonicznie
według rewizji. Istniejący GET /sources jest pobierany partiami do pełnego
katalogu metadanych; filtry anotacji poprzedzają paginację UI. Nie zmienia się API.
Statusy i liczniki wynikają wyłącznie z trwałych anotacji; obecna pełna geometria
wymaga full_approved i presence=present. Nawigacja porzuca lokalne zmiany
bez confirm i bez autosave; brak beforeunload. Busy/pending blokuje
nawigację w aplikacji do retry lub jawnego odczytu przyciskiem bez modalu.
Wspólna baza powiadomień packages/ui obsługuje kolejkę, deduplikację i zegar
niezależnie od operacji; zamknięcie toastu nie zmienia stanu zapisu.
Wszystkie warianty mają 4 s widocznego czasu; hover/focus/hidden pauzuje.
Przycisk Kopiuj używa clipboard wyłącznie dla wiadomości i izoluje kliknięcie
od zamykania. Wynik kopiowania pozostaje lokalny w toaście, bez nowych toastów.

POST `/geometry` przyjmuje opcjonalne `preview_board` zgodne z Board.
Bez niego zachowuje detekcję baseline; z nim waliduje bieżące węzły przez
`cell_quads` i generuje cropy przez wspólne `crop_cell`. GeometryResult
oznacza wynik `manual-preview`; assety pozostają w ograniczonym rejestrze
pamięci, bez mutacji anotacji. UI unieważnia odpowiedzi po zmianie węzłów
i przyjmuje wyłącznie najnowsze żądanie. Viewport jest osobną transformacją
źródło→ekran, zamrożoną na czas gestu; nie zmienia pikseli źródła ani węzłów.

Właścicielami reguł i kolejności są `requirements/VISION_LAB.md` oraz
`delivery/VISION_LAB_EXECUTION_PLAN.md`. Eksporter jest osobnym narzędziem
głównego środowiska. Czyta manifestem wskazane źródła, dostępne rewizje,
metadane pochodzenia, słowniki i związane zatwierdzenia; używa krótkiej
transakcji `REPEATABLE READ READ ONLY`, limitów czasu i partii. Snapshot
publikuje atomowo po kontroli checksum. Pierwotny `selective_board_review_v1_1`
i późniejsza ręczna reweryfikacja są odrębne; brak pierwszej wyklucza
porównanie. Laboratorium nie ma połączenia z bazą.

Manifest wejściowy v1 ma `schemaVersion`, `datasetName` i pozycje
`{gameId, sourceImageId, expectedSourceSha256, sourceFamilyId, role}`.
`role` przyjmuje `data`, `comparison_only` albo `777_v2_declared`; ostatnia
wartość dokumentuje deklarację pochodzenia, nie rozstrzyga samodzielnie
kwalifikacji treningowej. Format uruchomienia i katalogu wynikowego opisuje
`guides/VISION_LAB_EXPORT.md`.

Powyższe role opisują niezmienny format źródeł. D-453
dopuszcza historyczne zdjęcia 777 do uczenia geometrii z nowych ręcznie
zatwierdzonych siatek labu, zachowując ich historyczne pochodzenie. Dawne
geometrie v1.1 nie są targetami. T03e zapisuje jawne
`GeometryQualificationRequest` w istniejącym AnnotationStore: jeden atomowy
batch, CAS, receipts, historia i backup, bez zmiany anotacji i photo review.
Wersja `historical-777-lab-geometry-v1`, referencja D-453 i zakres geometry
wiążą dokładny game_id, source_id/SHA, mapę rewizji plansz, autora i czas.
Pierwszy wariant akceptuje tylko źródła folderowe o dokładnej tożsamości
777 (game_name i pierwszy segment filename), z rolą comparison_only;
inne comparison_only, V2 i źródła DB pozostają wykluczone.
Walidacja wymaga aktualnego photo_accepted i pełnego obecnego ręcznego targetu.
Kwalifikacja nie wymaga wcześniejszego mapowania rodzin, ale nie zastępuje go.

CLI `vision_lab.qualify_geometry` domyślnie czyta checksummed payload bez
tworzenia katalogu/.lock; `--apply` ponownie waliduje typed request pod blokadą
AnnotationStore. Nie ma dodatkowego endpointu ani UI. Addytywna odpowiedź
AnnotationState jest objęta OpenAPI i generowanym klientem. API nie przyjmuje
requestu kwalifikacji przez istniejący POST /annotations.

SplitRequest bez purpose zachowuje tryb legacy (w tym dotychczasowe receipts)
i odrzuca role inne niż data. Jawne purpose geometry może użyć skutecznej
kwalifikacji D-453. FrozenSplit zapisuje purpose, `lab-geometry-split-v1`,
fingerprints kwalifikacji oraz osobną mapę pełnych obecnych human targetów;
wyłącznie te targety liczą pokrycie topologii. Rodziny, duplikaty, pomiar
i photoacceptance nadal są wymagane. Stare split fingerprints nie są
przeliczane przy odczycie. Zmiana geometrii, review, rodziny lub kwalifikacji
oznacza istniejący split stale; odczyt dodatkowo sprawdza skuteczność
i fingerprint zamrożonej kwalifikacji. Ponowne accept tej samej mapy może
przywrócić skuteczność kwalifikacji, ale nie kasuje split_stale.
Nie zmienia się Source.training_eligible ani żadna bramka symboli.
Rebase jawnie odrzuca bieżące kwalifikacje i ich historię; import/rebase
nowych zdjęć musi poprzedzać realną kwalifikację do czasu osobnego rozszerzenia.
Implementacja T03e nie oznacza wykonania kwalifikacji lub splitu na danych.

T03f rozszerza istniejący SplitRequest o geometry_source_ids=None (do 10000 ID).
Jawna niepusta unikalna lista znanych źródeł wymaga purpose geometry. Kolejność
requestu pozostaje częścią receipt; pominięcie pola/None usuwa je z hashowanego
requestu, zachowując stare receipts obu trybów. Bez kohorty fingerprint splitu
nie zawiera nowych pól. Błędy domenowe /splits pozostają 409, schematu 422.
build_components obejmuje cały katalog; bramki roli i verified dotyczą całego
komponentu, a akceptacja, targety i assignments wyłącznie jego wybranych źródeł.
Measurement wymaga ID z kohorty, trudności wszystkich członków, jednej gry
i trudności oraz dwóch niezależnych komponentów na stratum. Wszystkie wybrane
źródła komponentu trafiają razem do pomiaru lub jednego podziału.

FrozenSplit policy lab-geometry-cohort-split-v1 wiąże posortowaną kohortę,
leakage_components całego katalogu oraz leakage_component_fingerprints pełnych
Source, StoredFamily (albo null) i kwalifikacji każdego członka niedata (albo
null). Wszystkie te mapy wchodzą do fingerprintu; stare odczyty mają None/{}/{}.
_view porównuje graf i fingerprints oraz skuteczność kwalifikacji wszystkich
członków niedata komponentów z assignments, także niewybranych. Stały brak
kwalifikacji w wykluczonym komponencie nie daje stale. Zmiana daje stale bez
przeliczania zapisanych assignments/fingerprintu; mutacje zachowują wcześniejsze
konserwatywne unieważnianie. Atomowość, CAS, retry, historia i backup należą
do AnnotationStore. Rebase splitu pozostaje zablokowany. Brak nowej trasy/UI.

T03j/D-455 dodaje opcjonalne SplitRequest.geometry_policy o wartości
`lab-geometry-cohort-777-targets-v2`; None jest usuwane przed hashowaniem
requestu/historii, więc legacy, T03e i T03f zachowują receipts i fingerprints.
V2 wymaga purpose geometry oraz jawnej niepustej kohorty. Błędy kombinacji
to GEOMETRY_POLICY_PURPOSE_REQUIRED, GEOMETRY_POLICY_COHORT_REQUIRED oraz
istniejący GEOMETRY_COHORT_EMPTY (HTTP409); nieznany enum daje HTTP422.
FrozenSplit zapisuje v2 w policy_version, bez dodawania pól do starych hashy.
Wspólny geometry_role_eligible jest używany przez freeze i _view; zwalnia
z kwalifikacji jedynie źródła poza geometry_source_ids spełniające ścisły
historical_folder_777 (folder, game_name=777, filename zaczyna się segmentem
777 i zawiera nazwę pliku, role=comparison_only). Brak assignmentu sam w sobie
nie oznacza kontekstu. validate_binding D-453 korzysta z tej samej tożsamości.
Wybrane niedata wymagają własnej skutecznej kwalifikacji. Pełne komponenty
i ich fingerprints pozostają niezmienione; _view v1 nadal wymaga kwalifikacji
wszystkich członków niedata. V2 nie daje fałszywego stale od stałego braku
kwalifikacji kontekstu, ale wykrywa zmiany pełnych metadanych, rodzin,
kwalifikacji i grafu. Konserwatywne stale po mutacjach pozostaje bez zmian.

T03k/D-456 dodaje geometry_policy `lab-geometry-whole-game-pilot-v1` oraz
opcjonalne game_partitions w SplitRequest/FrozenSplit. Mapa obejmuje dokładnie
wszystkie game_id katalogu: co najmniej jedno development, dokładnie jedno
validation, final_test i unseen_game, zgodne z unseen_game_id. Każda część
musi mieć co najmniej jeden pełny target. None jest usuwane z requestu przed
hashowaniem, a starsze polityki nie dodają mapy do danych hashowanych splitu.
Mapa poza pilotem, niepełna/błędna mapa i pusty przydział dają
PILOT_GAME_PARTITIONS_INVALID; brak mapy PILOT_GAME_PARTITIONS_REQUIRED.
Niepusty measurement lub difficulties daje PILOT_MEASUREMENT_NOT_SUPPORTED.

whole_game_split.freeze_whole_game_split jest czystą gałęzią po walidacji
purpose/kohorty. Nie wymaga verified i nie zapisuje rodzin. Każdy komponent
całego katalogu sprawdza wobec mapy (PILOT_CROSS_PARTITION_COMPONENT), a role
kontekstu sprawdza w komponentach dotykających kohorty wspólnym predykatem
D-455. Każdy target ma photo_accepted i pełną geometrię human 5 × 3;
brak targetu daje PILOT_FULL_GEOMETRY_REQUIRED, inna pełna topologia
PILOT_TOPOLOGY_NOT_SUPPORTED. Żaden błąd nie zmniejsza kohorty po cichu.
FrozenSplit wiąże mapę, całą kohortę, pełne komponenty i fingerprints;
assignments/targety są tylko wybrane, measurement pusty.
Odczyt nowej polityki rekonstruuje oczekiwany wynik na bieżącym stanie
z pierwotnym numerem rewizji splitu i porównuje go z zamrożonym rekordem,
bez zastępowania rekordów lub przeliczania starych wersji. W ten sposób
kontroluje także mapę, przydziały, pełne metadane, aktualność targetów i graf
odległych wykluczonych komponentów; różnica lub błąd walidacji daje stale.
Receipts, CAS, backup/restore i zakaz ponownego freeze pozostają w AnnotationStore.

Eksporter czyta tylko wskazane `source_images`, związane
`image_source_geometry_revisions`, `image_page_geometry_overrides`,
`recognized_boards`, `image_board_geometry_revisions`,
`image_board_geometry_review_events`, `image_symbol_review_cells` i
`image_symbol_review_events` oraz niezbędne `games`, `symbols` i
`rules_version_symbols`. Pierwsza krótka transakcja RO zamraża ID,
rewizje i fingerprinty powiązanych wierszy. Kolejne partie w nowych
transakcjach czytają dokładnie te ID; zmiana albo brak wiersza blokuje
publikację. Następuje kopia zarządzanych obrazów po kontroli SHA-256,
tymczasowy manifest, fsync plików i atomowy rename na jednym wolumenie
(fsync katalogu tam, gdzie wspiera go system). Snapshot ID jest SHA-256
kanonicznego wejścia, wersji eksportera oraz zamrożonych ID/rewizji.
Idempotentny retry weryfikuje opublikowane pliki; konflikt kończy błędem.

Dane poza repo pod `C:\Users\tuszy\Documents\game_predictor_vision_data`
obejmują niezmienne manifesty, zarządzane kopie obrazów, anotacje,
checkpointy, raporty i backupy. Zapisy są atomowe; wykonuje się próbę
odtworzenia. `GeometryEngine`, `GeometryResult` i `SymbolRecognizer` są
wspólnymi kontraktami dla baseline oraz przyszłych hybrid i neural_grid.
Wynik zachowuje źródło, topologię, plansze, węzły, pochodzenie punktów,
wersję modelu i powody korekty. Układ plansz ekranu jest niezależny od
`BoardTopology` pojedynczej planszy. 5 × 3 ma 24 węzły, 3 × 3 ma 16.
Nie zakłada się dziewięciu plansz; nieobecność, zasłonięcie i nieczytelność
są osobnymi stanami. Bramka kontroluje kolejność, przecięcia, dodatnie pola
i kompletność bez wymogu konkretnej techniki OpenCV.

T02 przyjmuje również dostarczony przez użytkownika folder zdjęć bez
powiązania z DB. Importer plikowy tworzy osobno wersjonowany snapshot,
lokalne identyfikatory, pochodzenie pliku, SHA-256 i zarządzane kopie.
Publikacja jest atomowa, ponowienie sprawdza checksumy, a konflikt nie
nadpisuje istniejącego snapshotu. Snapshot plikowy nie udaje eksportu DB
i nie tworzy zatwierdzeń ani uprawnień do treningu. Prefiks nazwy nagrania
jest kandydatem rodziny, wymagającym weryfikacji w T03. Oba formaty wejścia
są adaptowane do wspólnego katalogu galerii, bez zależności runtime od bazy.

Deklaracja operatora o odległych brzegach i innych folderach nagrań pięciu
gier jest wejściem do mapowania źródło–rodzina (D-453). Granicę rodziny
wyznacza wspólne nagranie i powiązane pochodne, nie odległość w numeracji
lub liczba katalogów. Końce tego samego filmu pozostają razem. Kontrole
SHA i podobieństwa rozstrzygają konflikty z deklaracją; brak trafienia
nie dowodzi niezależności. Przed freeze trzeba powiązać nowy i dotychczasowy
zbiór, bez automatycznego potwierdzania rodzin z samych nazw.

Hybryda używa MobileNetV3-Small, narożników, perspektywy i opcjonalnego
dopasowania. Neural_grid przewiduje pełne węzły. Symbole bazują na
`SpatialSymbolCnn`: RGB, szarość powielona na trzy kanały i fuzja z
udziałem RGB 0/0,1/0,2/0,3. Kalibracja jest tylko na walidacji;
niezgodność modeli jest sygnałem niepewności.

FastAPI `game_predictor_worker.vision_lab` działa na
`127.0.0.1:8102`, a Next.js `apps/vision-lab` na `127.0.0.1:3102`.
Frontend używa proxy z zamkniętą listą tras. FastAPI posiada OpenAPI i
osobny generowany klient kontrolowany w `openapi:check`/`quality`.
Oba wejścia kontrolują Host; zapis wymaga dozwolonego Origin i JSON.
Assety są identyfikowane w rejestrze, bez dowolnych ścieżek od klienta.
Zajęty port zgłasza błąd bez zabijania procesu; brak tunelu.

Testy importów chronią granice: lab nie importuje `storage`, `psycopg` ani
produkcyjnego handlera treningu; produkcyjne wejścia nie importują labu;
neutralny rdzeń nie zależy od bazy ani UI. Izolowane środowisko przypina
PyTorch 2.12.1, torchvision 0.27.1 i CUDA 13.0; główne środowisko pozostaje
bez zmian. Integracja CPU używa ONNX Runtime. Checkpoint v2 zawiera optimizer,
scheduler, RNG, konfigurację i SHA-256 danych. Odczyt v1 pozostaje możliwy
bez obietnicy numerycznie identycznego wznowienia. Produkcyjny
`training_job.py` użyje neutralnego rdzenia dopiero w T12 po regresjach.

`vision_lab/runs.py::RunManager` dostarczony w T04 jest
właścicielem trwałego kontraktu runów; panel T08 jest jego klientem.
Stan jest zapisywany atomowo pod
blokadą międzyprocesową i tokenem lease. `requestId` oraz fingerprint
manifestu, konfiguracji, modelu, topologii, preprocessingu i seeda są
trwałe przed spawnem. To samo żądanie zwraca ten sam run; ten sam ID z
innym payloadem daje konflikt. Stany: `queued → running →
succeeded|failed|cancelled`, bez pauzy. `running` wiąże PID, czas startu,
lease i heartbeat, więc restart nie uruchamia duplikatu. Żywy zgodny proces
pozostaje obserwowany nawet przy starym heartbeat/lease. Dopiero potwierdzony
brak zgodnego PID/czasu utworzenia wraz z wygaśnięciem lease daje recoverable
`failed`. Budżet jest naliczany trwale poza checkpointem; crash i retry nie
zwracają kroków ani niepotwierdzonego czasu (szczegóły T04). Cancel jest
utrwaloną intencją i kończy się po checkpointcie; awaria zachowuje ostatni
poprawny checkpoint. Retry jest jawną nową próbą z nowym lease po kontroli
fingerprintu; stary proces zostaje odgrodzony. Sukces wymaga atomowo
opublikowanych checksumowanych artefaktów i raportu.

Stan wszystkich runów i receipts ma checksumowaną kopertę w katalogu runów,
nie w AnnotationStore. Run-local lock ponawia wyłącznie konflikt blokady do
10 sekund; zwykłe odczyty panelu nie przerywają writera. `queued` zawiera
lease/fence oraz launch_deadline. Worker sam zapisuje PID i OS creation time
przy claim. Utworzenie procesu i ponowna kontrola queued są pod tym samym
lockiem; anulowany queued nie uruchamia pracy. Każda próba ma osobny katalog
niezmiennych artefaktów, a dopiero poprawny checkpoint v2 zmienia wskaźnik.

Trwałe rezerwacje kroków i naliczenie czasu są niezależne od checkpointu.
Worker ma dodatkowy monotoniczny watchdog obejmujący walidację, GPU i eksport;
po limicie kończy tylko własny proces. Odczyt po wygasłym lease rozpoznaje jego
brak, zapisuje failed i konserwatywnie nalicza odcinek bez potwierdzenia.
Nie kasuje ostatniego checkpointu. Cofnięty zegar wyczerpuje pozostały budżet.

`ManifestAdapter` sprawdza kopertę `{payload,sha256}`, zamrożony split i pełną
listę targetów T03k względem aktualnych anotacji. `TrainingInputs` udostępnia
wyłącznie development/validation; obraz jest odczytywany przez Catalog z SHA
i EXIF. Kontrola integralności holdoutów nie dostarcza ich do modelu.
POST /runs i cancel/retry, GET /runs oraz /runs/{id} korzystają z tego samego
loopback boundary i generowanego klienta. Ścieżki interpretera, manifestów,
runów i anotacji pochodzą wyłącznie z konfiguracji operatora. Katalog runów
nie może nachodzić na snapshot, anotacje lub manifesty. Rejestr trenerów jest
zamknięty; T05 dodaje leniwą hybrydę, a produkcyjny handler pozostaje niezależny.

## Narzędzia etykiet symboli T06a

D-458 rozdziela budowę narzędzi od kwalifikacji rzeczywistego zbioru.
Oddzielny, jawnie skonfigurowany magazyn symboli nie zmienia formatu
AnnotationStore ani jego receipts i podziałów. Wersje słownika, decyzje
operatora oraz dokładne cropy mają trwałą tożsamość. Zmiana geometrii,
źródła, cropa lub zatwierdzonego słownika unieważnia aktualność etykiety.
Adapter DB czyta wyłącznie zweryfikowany eksport; nie otwiera sesji bazy
i nie tworzy mapowania ani rekordów produkcyjnych.

Nowe trasy pozostają częścią istniejącego lokalnego API i zamkniętego
proxy. OpenAPI jest źródłem klienta. Szczegółowy kontrakt przed kodowaniem
określa `ai_docs/delivery/VISION_LAB_SYMBOL_LABELS_CONTRACT.md`.
Poprawna etykieta nie jest automatycznie próbką dopuszczoną do treningu.
T06b zachowuje bramki pochodzenia, ról i podziału symboli; D-456 ich nie
zastępuje. Holdout sprawdzany jest przed udostępnieniem pikseli.

TASK-0716/D-459 rozszerza istniejące trasy o podgląd lab_board i atomowe
label_board_decide. Podgląd tworzy jeden ograniczony kadr planszy z dokładnie
przeliczonymi węzłami oraz 9/15 niezmienionych cropów RGB96, z jednego odczytu
obrazu po kontrolach roli/holdoutu. Wspólny snapshot obejmuje rewizję symboli,
słownik i aktualne decyzje. Batch ponownie sprawdza wszystkie bindingi pod
blokadami geometry-first; publikuje jeden state z jedną rewizją i receipt,
zachowując odrębne decision_id i historię każdej komórki. Nie wywołuje mutate
rekurencyjnie. Stare requesty i receipts pozostają zgodne; szczegółowy kontrakt
i testy zapisuje TASK-0716, bez zmiany bramek dopuszczenia danych do treningu.
