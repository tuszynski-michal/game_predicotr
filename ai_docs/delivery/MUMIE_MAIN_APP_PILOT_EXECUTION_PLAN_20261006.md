---
title: Mumie — pilot głównej aplikacji, foldery i uczenie z korekt
status: accepted_scope
last_updated: 2026-10-06
---

# Stan, cel i zakres decyzji

Operator wybrał rekomendowany wcześniejszy RGB R2 i zlecił podłączenie silnika
do głównej aplikacji. Niniejszy plan konkretyzuje wykonanie tego zlecenia.
Nie wymaga kolejnej porcji etykiet ani kolejnego filmu przed implementacją.

Praca: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3,
branch feat/grid-engine-v3, HEAD v1.7.220 / 4afedc11682cb7d378363710c78467c19d3bb12a.
Cel wdrożenia: C:\Users\tuszy\Documents\game_predicotr,
branch v1.1-vision-lab-hybrid-geometry. Odczytany HEAD głównej gałęzi to
v1.7.222 / 48b6e0e104e19e915bde30cd89a80d508e81c0b3. Stan sprawdzić ponownie
przed integracją; gałęzie rozeszły się od 73ae0b6f, nie wystarcza skopiowanie plików.

Gra już istnieje: Mumie, fea55cc1-ebf4-4cee-b3ab-a520017ed1be, 500000 pozycji,
profil grid_profile_mumie_v1. Nie tworzyć duplikatu. Obecnie brak aktywnego
wspólnego profilu geometrii; staging preflight wymaga ręcznej korekty.
V3 shadow obsługuje zapisane source_images i pozostaje osobną funkcją.
Samo włączenie flagi shadow nie obsłuży nowego folderu w stagingu.

RGB R2: ONNX e4f9b2610407be8724fe0b5f26a5efa595b7b575af8434b73c19a39e04737095,
temperatura 1.05. Eligibility RGB-only:
5b6af3ef03d77ff7dbc3e7c2f45f0586f92d24088b5871316acc4aadf044ac7c.
Dziewięć kontroli klas/grup PASS; human26+human8 = 34/34.
To wybrane kontrole, nie oszacowanie accuracy całego filmu. Dane development
R2 obejmują 283 human i 44 AI; AI zachowuje swoje pochodzenie.
Para R2 RGB+gray pozostaje odrzucona, V4 pozostaje dawną kwalifikowaną parą.
Nowszy V5 pozostaje odrzucony: human34 29/34, 10/18 bramek FAIL.

# Reguły pilota

1. Oddzielna kwalifikacja operacyjna dla Mumii: wynik modelu jest propozycją.
   Nie nadaje etykiety human-approved ani kwalifikacji geometrii.
2. Model siatek: zamrożony preset D, iteration03-f896da7196431be2, run
   5bc981568c3f42bd96f6f9238e57aedc. Zachować pełne 24 węzły 5×3, wersje i SHA.
   Bramka NEURAL_GRID_GATE_UNCALIBRATED kieruje do review.
3. Źródło kolejności: potwierdzony zakres pliku i aktywne sloty.
   Pięć pozycji z nazwy oznacza pięć slotów. Brak środkowej detekcji nie zmienia
   numerów kolejnych plansz. Bez jednoznacznego przypisania nie ma sequence
   ani kalkulacji targetu. Nadmiar detekcji jest diagnostyką.
4. Słownik indeksów CNN, dokładnie w tej kolejności:
   10, J, Q, K, A, RA, SARKOFAG, MUMIA, FARAON, SFINKS.
   Etykiety lab Ra/Sarkofag/Mumia/Faraon/Sfinks mapować jawnie na kody katalogu.
   UUID pobierać z aktywnego katalogu tej gry; nie używać kolejności wyświetlania.
5. R2 oczekuje RGB96, float32 NCHW, bilinear antialias 96→64, następnie
   /255, -0.5, /0.5. Snapshot przypina osobno cropSize96 oraz inputSize64;
   zmienić renderer importu/recropu i manual preview tak, aby nie renderował64
   przed transformacją. Obecny INTER_AREA na uint8 jest innym preprocessingiem.
   Nowy wersjonowany adapter musi zachować transformację i odtworzyć logity
   rzeczywistego R2. Nie zmieniać preprocessingu istniejących modeli 777.
6. Nieczytelny lub nieobecny fragment obrazu nie staje się targetem treningowym.
   Partial może być poprawiany dla widocznych komórek; outside nie ma cropa.
7. Każdy upload wykonuje inferencję. Trening jest późniejszą jawną iteracją
   na skumulowanych zatwierdzonych korektach. Predykcje nie są etykietami.
8. Złota ramka/Super: zachować obraz i obserwacje; w pilocie rozpoznajemy
   dziesięć bazowych symboli. Nie włączać nieocenionego klasyfikatora ramek,
   reguł wypłat ani rozszerzania kolumn do tej integracji.
9. Błędny symbol można poprawić przy otwarciu planszy, bez zmiany siatki.
   Zachować klawiaturę i szybki zapis z zamrożoną kolejką do odświeżenia.
10. Aktualne importy/jobs zachowują przypięte wersje. Nowy model wpływa na
    nowe jobs; reinferencja istniejących pending wymaga osobnej jawnej akcji.

# Zadania i kolejność

## TASK-0879 — plan i rozstrzygnięcie kwalifikacji pilota

Utrwalić D-521, ten plan i taski. Skorygować odwołanie do niewykonanego etapu C
większego eksperymentu: jego warunek PASS nie został spełniony; niniejszy pilot
jest nowym zaakceptowanym zakresem z R2 RGB. TASK-0873 jest już zajęty na głównej
gałęzi przez RGB 777, więc nie używać go dla Mumii.

Odbiór: każde wymaganie ma właściciela i test, sprawdzone punkty wejścia,
brak fałszywej kwalifikacji R2-pair/V5, niezależny review planu.

## TASK-0880 — adapter RGB R2 i niezmienny pakiet kandydata

Proponowane nowe moduły:
services/worker/src/game_predictor_worker/images/lab_rgb_preprocessing.py
i domain/lab_symbol_candidate.py w API; proponowany CLI
scripts/prepare_mumie_rgb_pilot.py. Dokładne lokalizacje są względem wskazanego
wyżej absolutnego katalogu worktree; wszystkie komendy operują absolutnie.

Reuse images/symbol_onnx.py::LocalSymbolOnnxAdapter, wersjonowany dispatch
we wspólnej ścieżce preprocessingu importu i ManualBoardCellSymbolPredictor.
Adapter działa bez Torch w API/workerze. Torch jest tylko referencją testową
w istniejącym środowisku .venv-vision-lab.

Przypięty eksport R2 ma opset17. Wersjonowany kontrakt lab-rgb-symbol-onnx-v1
dopuszcza dokładnie17; istniejący M6/777 nadal wymaga18. Torch/Tensor/nn przenieść
do TYPE_CHECKING albo lokalnych importów export/parity. Odbiór obejmuje nowy
proces z blokadą importów torch/torchvision i rzeczywistą inferencją ONNX.
cropSize96 staje się częścią fingerprintu wyłącznie nowego kontraktu; stare
snapshoty, jobs i fingerprinty zachowują domyślne cropSize=inputSize.

Pakiet content-addressed pod managed artifact root zawiera ONNX, classes,
calibration, manifest origin i raport porównania. CLI przed publikacją odczytuje
autorytatywną RGB-only eligibility, sprawdza wszystkie pins i semantyczne
powiązania źródłowych raportów; sam passed=true nie wystarcza.
Nie przyjmować arbitralnego eksportu z podstawionym manifestem.
Publikacja atomowa, istniejące identyczne bajty idempotentne, drift odrzucany.
Żadnych wpisów DB ani aktywacji. Pakiet ma modelVersion lab-rgb-symbol-onnx-v1,
origin lab_import, scope mumie_pilot, powiązane eligibility, dataset i run.

Odbiór: rzeczywiste cropy odtwarzają klasy i logity R2; zachowany dotychczasowy
preprocessing; katalog pasuje; podmieniony model, temperatura, kolejność,
report lub wejście są odrzucane. Odtworzenie pakietu w nowym procesie.

## TASK-0881 — import kandydata do istniejącego rejestru

Istniejące punkty: storage/models.py::SymbolModelIterationModel,
storage/symbol_model_snapshot_resolver.py::SqlAlchemySymbolModelSnapshotResolver,
storage/symbol_model_registry_repository.py,
api/symbol_model_iterations.py, schemas/symbol_model_iterations.py,
apps/admin/src/features/model-quality, packages/admin-api-client.

Nie tworzyć fikcyjnej verified_training_cohort ani zatwierdzeń plansz.
Proponowana migracja 0144 po 0143, po ponownym sprawdzeniu heads:
iteration_origin (production_training domyślnie / lab_import), nullable cohort_id
wyłącznie dla lab_import, origin_manifest path/SHA i constraint wymagający
dokładnie właściwego pochodzenia. Unikalność game+origin fingerprint.
Istniejące rekordy pozostają production_training z rzeczywistym cohort_id.
Manifesty pozostają na dysku, w DB wyłącznie tożsamość i metadane.

Rozszerzyć istniejący zasób: proponowane POST
/admin/games/{gameId}/symbol-model-iterations/imports z candidateFingerprint
i idempotencyKey. Serwer wybiera tylko zweryfikowany managed pakiet dla tej gry;
klient nie podaje ścieżek systemowych. Job VALIDATE, nie fikcyjny TRAIN.
Stany created→evaluating→candidate_ready albo failed/rejected, epochCount=0
dla importu. Powtarzana utracona odpowiedź zwraca ten sam job/iteration;
inny payload z tym samym kluczem daje konflikt. Hash/catalog drift blokuje
rejestrację oraz późniejszą aktywację i inferencję.

Activation-preview jawnie pokazuje pilot, 34 wybranych kontroli, brak pomiaru
populacji i AI-origin. Reuse istniejącej aktywacji i idempotency/fencing.
Snapshot resolver odczytuje modelVersion/preprocessing z właściwego kontraktu
origin; nie przypisuje R2 nazwy spatial production M6.

Recovery pierwszej aktywacji: dotychczasowy rollback wymaga uprzedniej aktywnej
iteracji. Proponowana jawna akcja deaktywacji w istniejącym registry:
append-only action deactivate, model_iteration_id NULL tylko dla tego action,
expectedCurrentIteration + idempotency. Deaktywacja blokuje nową inferencję
SYMBOL_MODEL_ACTIVATION_REQUIRED, zachowuje stare jobs i korekty.
Nie obiecywać powrotu do niezgodnego bootstrapu.

Odbiór: pełny backend→OpenAPI→wygenerowany klient→wrapper→UI→request test,
migracja testowana na lokalnym testowym schemacie, brak wpływu na 777.
Nie stosować migracji na danych użytkownika w tym tasku.

## TASK-0882 — siatki neural w stagingu, import i korekta

Istniejące punkty: images/page_geometry_preflight.py::PageGeometryPreflightHandler,
images/production_workflow.py::ProductionImageStageAdapterSuite,
images/board_cell_geometry_deferred_writer.py::BoardCellGeometryDeferredWriter,
geometry_core/inference.py, domain/grid_engine_profiles.py,
application/virtual_grid_geometry.py::VirtualGridGeometryService,
schemas/image_grid_reviews.py oraz reviewer grid-audit-correction-workspace.tsx.

Proponowany neural adapter stagingu używa geometry_core, nigdy lab wrappera.
Job zamraża model/preset/profile/plik/ranges. Wersjonowany manifest zawiera
source SHA/dimensions, 24 nodes, 15 quads/visibility per proposal, active slots,
slot association, engine SHA i review reasons. Stary format zachować dla 777.
Nie oznaczać neural proposal jako verified/canonical registration.

Mumie pilot może zaimportować źródło z geometrią wymagającą review:
reuse durable pending/deferred workflow i istniejącej kolejki korekty.
Nie wymagać zatwierdzenia wszystkich źródeł przed pokazaniem pierwszego.
Idempotentna tożsamość source+slot+pipeline fingerprint, krótkie transakcje.
Dla jednoznacznego slotu proposal trafia do draftu i od razu daje symbolpreview;
przy braku przypisania źródło trafia do korekty źródła, bez wymyślonej planszy.

Właściciel source-level pending bez sequence: istniejący PageGeometryOverrideService,
browser page-geometry routes w api/image_imports.py oraz Admin
features/imports/page-geometry-correction-panel.tsx. Rozszerzyć manifest
stagingu o source-keyed neural proposals i stan slot_binding_required.
Binding upload selection ID + source SHA + dimensions + manifest revision
pozwala wznowić korektę po restarcie bez RecognizedBoard ani sequence.
Idempotentny override zapisuje ręcznie przypisane detectionID→positionIndex
i checksum propozycji, zgodnie z istniejącym page-geometry workflow.
Zmiana pliku/proposal/revision odrzuca override jako stale. Ponowne preflight
korzysta z zapisanego bindingu; dopiero wtedy może wywołać board deferred writer.

Proponowana czysta funkcja associate_expected_slots: zakres daje expectedCount
i expectedSlots, nigdy dowód miejsca brakującej detekcji. Bez override można
tworzyć wyłącznie propozycję ordered binding przy dokładnie expectedCount
strukturalnie poprawnych, niepokrywających się detekcjach z jednoznacznym
porządkiem przestrzennym. Nadal wymaga review, bez canonical qualification.
Inna liczność, niepoprawna struktura albo niejednoznaczny porządek daje
slot_binding_required dla źródła; nie kompaktować żadnych sequence.
Ręczny binding ma unikalne detectionID i active positionIndex, pozostałe sloty
są jawnie missing. Przykład: zakres101–105, detekcje a,b,d,e; operator przypisuje
a→0,b→1,d→3,e→4; slot2/sequence103 pozostaje pending bez cropa.
Detekcja d zachowuje sequence104, a nie103. Extra detection zostaje diagnostyką.
Istniejący reading_order służy tylko do sortowania, nie do naprawy braków.

Strukturalnie wadliwa detekcja nie jest renderowana jako pełna siatka.
Wynik NN nie nadpisuje zatwierdzonej geometrii.

Rozszerzyć zgodnie istniejący geometry-preview/save o opcjonalne pełne
latticeNodes i checksum-bound proposal binding. Zachować domyślne corners
dotychczasowych konsumentów. Pełne 24 nodes przechodzą przez preview, render,
rewizję i manifest bez rekonstrukcji wnętrza z czterech rogów.
UI edytuje węzły oraz symbole; jawne przejście na tryb czterech rogów tworzy
nowy draft i wymaga ponownego preview. Zapis symbolu zachowuje dobry crop.

Odbiór: folder→source→właściwe sloty→drafty→symbole→manual correction,
pięć końcowych slotów, brak środkowej detekcji, partial/outside, stale revision,
utracona odpowiedź, restart każdego etapu. To nowy jawny workflow importu;
nie jest samoczynnym uruchomieniem dodatkowych shadow jobs.

## TASK-0883 — uczenie z korekt i odbiór pełnego przepływu

Reuse istniejących verified cohorts i akcji Ulepsz rozpoznawanie dla etykiet DB;
lab_human_approved pozostaje oddzielne. Crop po recropie wymaga ponownego
zatwierdzenia pikseli. Zachować provenance prawdziwych decyzji oraz nieczytelność.

Dla neural geometrii reuse scripts/vision_lab_geometry_export.py i
scripts/vision_lab_production_snapshot.py. Export kwalifikuje aktualną geometrię
zaakceptowaną przez człowieka i visibility mask, nie sam fakt predykcji.
Porównywać geometry i symbol targets oddzielnie. Akcja zbiorczej iteracji
zamraża snapshot, podział po całych źródłach i ograniczony budżet;
trening tworzy kandydata do porównania, bez automatycznej aktywacji.
Nie zmieniać limitu wycinków, źródeł ani dawnych protokołów po cichu.

Granica pilota: DB source-family split gwarantuje whole-photo, nie whole-film.
Nie deklarować niezależności filmów dla nowych DB iteracji ani accuracy filmu.
Dotychczasowe trzy katalogi mają potwierdzone pochodzenie z różnych nagrań,
ale to nie nadaje recordingID przyszłym DB source_images. Trwały rejestr nagrań
jest poza tym pilotem; jego brak jawnie pokazywać w raporcie treningu.

Przed kwalifikowaniem nowego DB TRAIN proponowany frozen manifest
protected-source-exclusions-v1 wiąże model/eligibility i wszystkie całe zdjęcia
stałych R2 validation/diagnostic, human26/human8 oraz odrębnego AI audit.
Zachować rozdział kontrolnych regresji development od held-out źródeł.
Owner: istniejący preview/freeze verified cohort oraz dataset builder; dodać
wersjonowany per-game exclusion descriptor do fingerprintów kohorty/treningu.
Każda pozycja exclusions ma source byteSHA i SHA exif-normalized decoded RGB.
Freeze/import aliasów odczytuje managed original; reencoded alias o tych samych
decoded pikselach nadal jest chroniony. Nie ma identyfikacji przez samą nazwę.
Protected zdjęcie może być zaimportowane i prawdziwie zatwierdzone w aplikacji,
ale preview/freeze raportuje PROTECTED_EVALUATION_SOURCE i wyklucza jego wszystkie
komórki z TRAIN. Builder niezależnie ponawia gate przed pierwszą epoką.
Nie zmieniać historycznych manifestów ani decyzji human. Korekty kontrolnego
obrazu nie przesuwają jego splitu ani nie nadpisują zamrożonej prawdy testowej;
konflikt testowej etykiety oznaczyć OPEN i blokować promocję do rozstrzygnięcia.
Brak exclusions/drift chronionego źródła blokuje nowy Mumie TRAIN, pozostawiając
upload i korektę dostępne. Wystarczająca liczba różnych zdjęć nadal podlega
istniejącej all-class split gate; bez dodatkowej obietnicy whole-recording.

Testować najpierw istniejące rzeczywiste pliki bez zapisów produkcyjnych.
Pierwszy odbiór: 100 deterministycznie dobranych zdjęć z trzech nagrań,
po maksymalnie 20 na krok z checkpointem i limitem 120 s.
Raportować wykryte/oczekiwane sloty, nieprzypisane, cropy widoczne/partial/outside,
kolejkę review, błędy, czas i pamięć. Poprawności symboli całego folderu nie
wyliczać bez prawdziwych etykiet. Kontrole R2, V5 FAIL i 777 pozostają osobne.
To ograniczony test istniejących danych, bez sztucznych wielomilionowych fixture.

Odbiór UI i API na odizolowanym testowym schemacie, restart/response-loss,
approved-protection, tylko nowe pending po jawnej reinferencji,
focused tests→lint/types→kontrakt→build. Udokumentować operatorowi workflow.

## TASK-0884 — wdrożenie i pilotaż w głównej aplikacji

Warunek: 0880–0883 odebrane, niezależny audit bez otwartych P0–P2,
konkretny preview migracji/importu/aktywacji i zgoda na wykonanie na bazie.
Polecenie podłączenia aplikacji obejmuje przygotowanie kodu i odbioru.
Dawne zgody na 0140–0143 nie zastępują preview nowej 0144.
Nie prosić ponownie o wybór modelu, źródła filmów ani zgodę na implementację.

1. Sprawdzić bieżący MAIN HEAD, dirty files, Alembic current/heads, joby i PID.
   Na głównej gałęzi trwają operacje RGB 777 (TASK-0878). Wdrożenie poczeka na
   bezpieczny checkpoint zakończenia kroku; nie przerywać aktywnego zapisu.
2. Przygotować backup i możliwość odtworzenia, stopped/restartable services
   zgodnie z istniejącymi skryptami operatorskimi. Zapisać preview:
   bazę i revision, zakres migracji, liczbę dotkniętych istniejących iteracji,
   dokładne SHA modeli i gry, nowe wpisy registry, zakres pilota.
3. Po konkretnym potwierdzeniu operacji zatrzymać API --reload przed scaleniem.
   Zintegrować gałęzie z zachowaniem nowszej pracy RGB głównego checkoutu;
   rozwiązać kolizje CURRENT/tasków i wykonać regresje.
4. W głównym checkoutcie npm install, admin:build, reviewer:build,
   db:migrate do zweryfikowanego head zawierającego 0144.
   Przygotowany plan rollbacku danych to backup/restore z zatrzymanymi writes,
   nie obietnica automatycznego downgrade aktywnych rekordów lab_import.
5. Instalacja zweryfikowanych model artifacts, import kandydata, preview i
   jawna aktywacja tylko Mumie. Uruchomić API/Admin/Reviewer/worker jako
   kontrolowane procesy ukryte, zapisać PID, readiness polling maks. 10 s.
6. Zatwierdzony test operacyjny 100 zdjęć bez duplikowania już zapisanych
   pozycji. Dopiero po odbiorze zwiększyć partię do 500, potem 2000.
   To limity partii pilota, nie limit wyświetlania kolejki.
7. Przy problemie zatrzymać nowe importy Mumii, zdezaktywować pilot zgodnie
   z nowym registry, zachować źródła, jobs, korekty i raport. 777 bez zmiany modelu.

# Co robi operator po wdrożeniu

1. Otwiera istniejącą grę Mumie w Admin i wybiera folder zdjęć z jednego filmu.
   Na początek system przyjmie pilotażową partię 100; reszta pozostanie dostępna
   do kolejnego uploadu. Potwierdza zakresy z nazw plików tylko jeśli UI tego wymaga.
2. Otwiera kolejkę korekty siatek. Poprawia położenie/podział tylko przy złym
   cięciu. Siatka wymagająca oceny od razu pokazuje widoczne komórki i sugestie.
3. Przy dobrym cięciu zmienia wyłącznie symbol. Może używać numerów klawiatury
   pokazanych przy katalogu. Nie musi zmieniać siatki ani ponawiać podglądu.
4. Nieczytelne oznacza jako nieczytelne. Zatwierdza wyłącznie to, co widzi.
   Złota ramka nie zmienia bazowej etykiety symbolu.
5. Po zgromadzeniu różnorodnych korekt uruchamia zbiorcze Ulepsz rozpoznawanie.
   System pokazuje kwalifikujące próbki i braki pokrycia. Niewystarczający split
   blokuje sam trening, ale nie blokuje uploadów i dalszej korekty.
   Dalsza iteracja geometrii ma osobny snapshot i raport.
6. Nową wersję ocenia się na zachowanych kontrolach i odrębnych źródłach.
   Aktywacja kolejnej wersji jest osobną świadomą akcją.

# Odbiór, weryfikacja i granice

| Wymaganie | Task | Kryterium/test |
|---|---|---|
| Rekomendowany R2 bez fałszywej kwalifikacji V5 | 0879, 0880 | Dowody dziewięciu kontroli; pair/V5 nadal FAIL |
| Zachowanie wejścia wytrenowanego modelu | 0880 | Real RGB96 i logity reference/production, default777 regression |
| Model w aplikacji z pochodzeniem i recovery | 0881 | Migration/import/activate/deactivate/restart/catalog/hash/request tests |
| Folder automatycznie daje propozycje siatek | 0882 | Staging→deferred→review bez aktywnego wspólnego profilu |
| Pięć slotów, brak środkowego, partial | 0882 | Deterministyczne range/slot mapping; brak nieistniejących cropów |
| Dobry crop, zły symbol | 0882, 0883 | Edycja na otwarciu bez zmiany geometrii; szybki zapis |
| Poprawki szkolą kolejne wersje | 0883 | Human-only DB cohort, geometry export, anti-leakage, no autoactivation |
| Główna aplikacja i rzeczywiste partie | 0884 | Migracja/readiness, 100→500→2000, per-game recovery |

Sprawdzone narzędzia repo: python -m pytest, ruff check/format --check,
mypy; npm run openapi:generate/openapi:check, admin:build, reviewer:build,
db:migrate. Interpreter: C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe.
Każdy task podaje dokładne absolutne pliki i właściwe testy przed kodowaniem.
Finite komendy uruchamiać przez istniejący run_step.py z timeout 120 s.
Znane buildy mogą mieć dłuższy limit po informacji o czasie. Nie uruchamiać
drugiego serwera ani nie czekać bez limitu.

Testy odbioru0880–0884 są planowane, nie zaliczone. Plan0879 ma niezależny
review PASS, brak otwartych P0–P2 po zamknięciu slot/source i holdout guards.
Odczytano kod, schemat, metadata artefaktów i read-only API gry/katalogu.
Wykonano ograniczony preflight405 prawdziwych wycinków z3 zdjęć: numpy adapter
vs laboratoryjny antialias, input max7.153e-7, ONNX logit max1.908e-6,
0 zmian klas. To dowód zgodności wejścia, nie accuracy ani test pełnej integracji.
Raport: C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-main-app-pilot-20261006\input-preflight.json.
Nie zmieniono DB,
runtime ani aktywacji. Nie obiecujemy terminu zakończenia przed przejściem
pionów kontraktu i stagingu. Ryzyka: różne preprocessing/cropper, brak pomiaru
populacji, niejednoznaczne sloty, kolizje dwóch gałęzi, żywa operacja RGB.
Nie są powodem wymagania nowych oznaczeń od operatora teraz.

Po każdym tasku: niezależny wymagany review, osobny commit z wersją według
rzeczywistej historii tej gałęzi, Outcome/CURRENT_STATE, przeniesienie done.
Prace implementacyjne kontynuować do gotowego preview wdrożenia.
Nie wykonywać push, dodatkowego refitu, destrukcji ani operacji poza pilotem.

# Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0879 — plan pilota | gpt-6.1-sol | high | Decyzje kontraktu i ochrony danych wymagają spójnego sprawdzenia istniejącego workflow. | Niezależny review gpt-6.1-sol/high |
| TASK-0880 — RGB adapter i pakiet | gpt-6.1-sol | high | Różnica preprocessingu i pochodzenie eksportu wymagają actual-inference porównania. | Niezależny review gpt-6.1-sol/high |
| TASK-0881 — rejestr kandydata | gpt-6.1-sol | high | Migracja, provenance, snapshot i recovery muszą zachować stare aktywacje. | Niezależny audit gpt-6.1-sol/high |
| TASK-0882 — neural staging i korekta | gpt-6.1-sol | high | Sloty, 24 węzły, częściowe obrazy i rewizje wymagają analizy całego pionu. | Niezależny audit gpt-6.1-sol/high |
| TASK-0883 — feedback i odbiór | gpt-6.1-sol | medium | Reuse istniejących kohort i testów; high przy naruszeniu granic label/geometry. | Niezależny audit gpt-6.1-sol/high |
| TASK-0884 — wdrożenie pilota | gpt-6.1-sol | high | Współbieżna praca głównej gałęzi i nowa migracja wymagają konkretnego preview i odtworzenia. | Niezależny odbiór preview gpt-6.1-sol/high |
