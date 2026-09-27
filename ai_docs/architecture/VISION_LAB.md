---
title: Laboratorium geometrii i symboli — architektura
status: accepted
last_updated: 2026-09-27
---

# Architektura laboratorium wizji

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

Proponowany `vision_lab/runs.py::RunManager` powstaje w T04 i jest
właścicielem trwałego kontraktu runów; panel T08 jest jego klientem.
Stan jest zapisywany atomowo pod
blokadą międzyprocesową i tokenem lease. `requestId` oraz fingerprint
manifestu, konfiguracji, modelu, topologii, preprocessingu i seeda są
trwałe przed spawnem. To samo żądanie zwraca ten sam run; ten sam ID z
innym payloadem daje konflikt. Stany: `queued → running →
succeeded|failed|cancelled`, bez pauzy. `running` wiąże PID, czas startu,
lease i heartbeat, więc restart nie uruchamia duplikatu. Wygasły lease po
sprawdzeniu tożsamości procesu daje recoverable `failed`. Cancel jest
utrwaloną intencją i kończy się po checkpointcie; awaria zachowuje ostatni
poprawny checkpoint. Retry jest jawną nową próbą z nowym lease po kontroli
fingerprintu; stary proces zostaje odgrodzony. Sukces wymaga atomowo
opublikowanych checksumowanych artefaktów i raportu.
