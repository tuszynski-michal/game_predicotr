---
title: Iterative image import architecture
status: accepted
last_updated: 2026-08-23
release: "0.7"
---

# Architektura iteracyjnego importu

## Przepływ

```text
curated image-selection manifest
  -> durable import source
  -> atomic reservation of next N entries
  -> image import job pinned to manifest slice + symbol model + grid profile
  -> operational review
  -> immutable symbol and geometry cohorts
  -> independent candidate gates
  -> explicit activation
  -> next batch
```

## Import ręcznie nazwanych zakresów

Gdy źródłem jest folder lokalnej ręcznej selekcji, worker rozpoznaje tryb
`seq_*` po nazwach plików i zapisuje deklarację w managed manifest. Parser
akceptuje wyłącznie `seq_<start>-<end>.jpg|jpeg`, gdzie zakres obejmuje od 1 do
9 plansz. Sortowanie odbywa się po liczbie `start`, nie po tekście nazwy ani
checksumie. Duplikaty i nakładanie blokują start; luki są ostrzeżeniem.

Pipeline przypina adapter `sequence-number-from-attested-range-v1`. Adapter
pomija OCR numerów i przypisuje numery row-major tylko wtedy, gdy geometria ma
dokładnie oczekiwaną liczbę uporządkowanych plansz. Przy częściowym wykryciu
zachowuje brak numeru i kieruje obraz do korekty, bez przesuwania pozostałych
pozycji. Zakres, jego źródło i checksum pozostają w manifestach oraz wynikach
stage, dzięki czemu retry nie może zmienić deklaracji operatora.

## Model trwały

`curated_image_import_sources` przechowuje grę, run Selekcji Zdjęć, ścieżkę i
checksumę manifestu, liczbę wpisów oraz monotoniczny `next_entry_index`.

`curated_image_import_batches` przechowuje numer partii, półotwarty zakres
`[start_index, end_index)`, status i powiązany image import job. Rekord źródła
jest blokowany podczas rezerwacji. Unikalny numer partii i sprawdzenie zakresu
chronią przed podwójnym użyciem zdjęcia.

Manifest jest ponownie weryfikowany przy tworzeniu joba i przez worker. Job nie
skanuje całego katalogu: ładuje wyłącznie wpisy z przypiętego wycinka, zachowując
`groupOrder`.

## Snapshot pipeline'u

Image import schema v3 zawiera:

- identyfikator źródła i partii,
- checksumę i ścieżkę manifestu,
- początek oraz liczbę wpisów,
- snapshot modelu symboli,
- snapshot profilu kalibracji siatki.

Efektywny fingerprint obejmuje wszystkie te wersje. Aktywacja podczas pracy
joba nie zmienia jego zachowania.

Browserowy import z trwałego stagingu używa schema v5. Oprócz manifestu `seq_*`
zawiera snapshot aktywnego modelu symboli i profilu siatki oraz ich fingerprinty.
Tryb `rerun_current_models` tworzy nowy job dla terminalnego importu z innymi
snapshotami, pozostawiając poprzedni job audytowalny; identyczne żądanie jest
idempotentne. Staging nie jest ponownie przesyłany, a kanoniczne numery są
ponownie sprawdzane przed startem.

Odczyt raportu stagingu rozwiązuje snapshot modelu symboli w trybie preview.
Znane braki gotowości (`ACTIVATION_REQUIRED` lub `COMPATIBLE_MODEL_REQUIRED`)
są częścią odpowiedzi, a nie błędem transportowym, dzięki czemu niezależny job
geometrii może powstać przed treningiem. Utworzenie joba importu używa nadal
rygorystycznego resolvera i nie może zapisać schema v5 bez zgodnego snapshotu.

### Ponowne przetwarzanie z dokładną geometrią strony

Nowy managed reprocess używa schema v6. API odczytuje manifest managed
originals wybranego joba, a następnie przechodzi bounded, same-game łańcuch
`managed_source_job_id` / `previous_job_id` do najbliższego przypiętego
`PageGeometryManifestV1`. Oba artefakty są sprawdzane pod względem checksum,
gry, browser stagingu, kompletnego inwentarza i disposition źródeł przed
utworzeniem joba. Ich checksumy wchodzą do fingerprintu.

Worker przed pipeline'em ponownie sprawdza manifest źródłowy oraz zgodność
każdego wpisu geometrii. Schema v6 nie ma ścieżki bez manifestu strony:
brak dowodu daje `IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_REQUIRED`, a drift,
obca proweniencja lub niepełne pokrycie
`IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_INCOMPATIBLE`. Schema v4 pozostaje
obsługiwana wyłącznie jako historyczny kontrakt replayu.

### Jawnie przypięty adapter komórek v20

Schema v5 może opcjonalnie zawierać snapshot
`board-cell-processing-v20-verified-v19-v1`. Pole nie jest dodawane domyślnie:
operator wybiera `verified_v19`, a zwykły start zachowuje historyczny v18.
Konfiguracja estymatora i croppera wchodzi do efektywnego fingerprintu.

Historyczna lista checkpointów pliku pozostaje niezmienna. V20 wykonuje
`board_cell_geometry` jako trwały, niezmienny pre-crop substage etapu
`board_crops`. Jeśli worker zakończy się po zapisaniu geometrii, resume używa
stage result bez ponownego estymowania. Replayer po zapisie oraz przy
rehydration materializuje job-local `image_board_geometry_pending`
idempotentnie, co jest konieczne również przy współdzieleniu file execution
przez dwa joby.

Wynik strony może zawierać udane i odroczone pozycje. Tylko udane pozycje
tworzą 15 cropów v19 i przechodzą przez numer z poświadczonego zakresu oraz
model symboli. Odroczone pozycje tworzą zero cropów i zero predykcji. Nie
istnieje przejście z błędu v19 do v18. Dzięki temu historyczne checkpointy i
manifesty są odtwarzalne, a rollback nowych jobów polega na ponownym jawnym
wyborze `historical_v18`.

Oczekujący deferred geometrii należy do granicy `waiting_for_review`. Blokuje
przedwczesną walidację ciągłości i nie jest interpretowany jako brakująca
sekwencja.

### Stan rollout'u i rollback

Cross-staging benchmark obejmujący 300 stron i 2700 plansz potwierdził jakość
automatycznych trafień v19, ale osiągnął `2532/2700 = 93,78%` pokrycia przy
bramce co najmniej `98%`. Z tego powodu `historical_v18` pozostaje domyślnym
snapshotem, a `verified_v19` jest wyłącznie staging-local opt-in. Jawna decyzja
właściciela pozwoliła zintegrować i używać bezpiecznego adaptera v20, lecz nie
zmieniła wyniku bramki ani domyślnego trybu.

Rollback nie mutuje działającego ani historycznego joba. Operator wybiera
`historical_v18` podczas tworzenia kolejnego joba z tego samego lub innego
stagingu. Efektywny fingerprint i checkpointy v18/v20 są rozłączne, więc retry
zawsze zachowuje snapshot pierwotnego joba.

### Ręczne rozwiązanie deferred komórek

Końcowy fallback nie tworzy równoległej kolejki plansz. Dla jednego
`image_board_geometry_pending` API odczytuje niezmienny source i detekcję
planszy oraz snapshot modelu symboli z tego samego importu. Cztery narożniki
przechodzą przez ten sam source-direct cropper v19 co zwykła korekta. Preview
pozostaje read-only; zapis jest dozwolony dopiero po uzyskaniu dokładnie 15
cropów i 15 predykcji w kolejności 3 × 5.

Repozytorium serializuje zapis na rekordzie deferred i w jednej transakcji
tworzy `recognized_board`, 15 `cell_observations`, `image_review_item` oraz
`image_board_geometry_revision`. Istniejący trigger kolejki projektuje nowy
item we właściwe miejsce `sequence_number + position_index`; nie istnieje
druga implementacja kolejki. Wcześniejsza materializacja planszy kończy próbę
statusem `superseded`. Klucz idempotencji i checksumę komendy sprawdza się
przed kosztownym preview/inferencją oraz ponownie pod blokadą zapisu.

Artefakty ręcznych komend używają niezmiennych, command-scoped namespace'ów o
stałej długości ścieżki zgodnej z Windows. Model ONNX jest ładowany wyłącznie z
checksum-bound snapshotu źródłowego joba; aktualnie aktywny model gry nie może
zmienić wyniku historycznego importu.

Reviewer prezentuje trwałe wyjątki jako osobny tryb UI, ale konsumuje istniejące
scope-bound API zamiast budować drugą projekcję domenową. Lista używa
`status=pending`, limitu jednego elementu i stabilnego kursora; klient zachowuje
jedynie bounded historię odwiedzonych stron. Źródło jest wersjonowane checksumą,
a preview i resolution niosą checksumę manifestu oraz oczekiwane rewizje.

Stan klienta wiąże wygenerowany preview z dokładnym zestawem czterech narożników.
Zmiana komendy unieważnia podgląd i jej idempotency key. Ten sam klucz pozostaje
wyłącznie dla ponowienia niezmienionej komendy po niejednoznacznym błędzie
transportu. Konflikt rewizji, manifestu lub statusu powoduje odczyt kolejki od
początku. Po materializacji Reviewer odświeża wyjątki, a zwykłą kolejkę pobiera
ponownie przy powrocie do zatwierdzania symboli, dzięki czemu nowy item przechodzi
przez istniejący bounded bufor plansz.

## Kohorta i profil geometrii

Kohorta jest game-scoped, kumulacyjna i niezmienna. Rekordy plansz nadal
zachowują pierwotny i finalny quad, ale profil schema v2 grupuje je według
źródła i kwalifikuje wyłącznie kompletny układ pozycji 0–8. Pełna próbka ma
9 niezależnych quadów, 36 narożników, wspólną przestrzeń współrzędnych źródła
oraz spójne wymiary. Niekompletne i nieuporządkowane źródła są raportowane, a
nie uzupełniane średnią.

Podział jest source-image-disjoint. Z części treningowej wybieranych jest do
16 kotwic przez deterministyczny algorytm medoid + farthest point na wektorze
72 znormalizowanych współrzędnych. Walidacyjne źródło nigdy nie staje się
kotwicą. Lista checksum kotwic i jej polityka są częścią checksum-bound profilu
i snapshotu joba.

Na zdjęciu docelowym ORB estymuje osobną homografię względem najlepiej
dopasowanej kotwicy. Homografia przenosi pełne 36 narożników, po czym każdy z
dziewięciu quadów jest niezależnie dopasowany do czerwonych krawędzi. Runtime
zatwierdza wynik tylko przy kompletnej kolejności 3 × 3 oraz przejściu bramek
inlierów, reprojekcji i pokrycia krawędzi wszystkich plansz. Niepowodzenie jest
`review_required`, bez fallbacku do czterech narożników strony lub globalnej
mediany. Rejestr aktywacji jest append-only i umożliwia rollback.

Profile schema v1 zachowują historyczny algorytm medianowych przesunięć i są
odtwarzane tylko przez już przypięte fingerprinty. Utworzenie nowej kohorty
używa schema v2, dzięki czemu stary odrzucony profil nie blokuje kandydata
opartego na 36 narożnikach.

### Końcowa bramka profilu strony

Komplet 36 narożników jest wejściem do kandydata, a nie dowodem gotowości do
produkcji. Profil schema v2 otrzymuje `candidate_ready` dopiero po dołączeniu
raportu `grid-profile-end-to-end-gate-report-v1`, utworzonego z wyników tych
samych adapterów, które wykonują produkcyjną rejestrację strony, estymację
siatki 3×5 oraz kontrolę 15 cropów.

Korpus raportu jest rozłączny od źródeł treningowych i kotwic po checksumie.
Ma co najmniej 100 źródeł, 500 aktywnych plansz, pięć niepustych bucketów
jakości/kąta oraz pełne pokrycie wersjonowanego korpusu znanych regresji.
Raport wiąże checksumę kohorty, checksumę korpusu, agregaty odroczeń i liczniki
niezmienników checksumy, kolejności, topologii, overlapu i source support.

Przejście wymaga co najmniej 98% plansz z końcową, gotową geometrią 3×5, zera
naruszeń niezmienników oraz spadku nie większego niż 0,5 punktu procentowego
wobec stabilnego baseline'u uruchomionego na identycznych źródłach. Brak,
niepełność albo drift raportu jest wynikiem fail-closed. Nie obniża się progów
`incomplete_lattice`, residualu ani source support.

Kohorta i każda rewizja profilu pozostają niezmienne. Ponowna ewaluacja tej
samej kohorty tworzy następny profil z inną checksumą raportu, zamiast
nadpisywać poprzedni wynik. Aktywny profil schema v2 bez aktualnego raportu nie
może zostać przypięty do nowego joba; job utworzony wcześniej zachowuje swój
snapshot i replay.

### Bramka systemowa przed materializacją dużego importu

Po ingestowaniu managed originals, sprawdzeniu przypiętego manifestu strony i
odfiltrowaniu źródeł kanonicznych worker oblicza rozmiar faktycznego pipeline'u.
Dla co najmniej 100 źródeł albo 500 plansz wybiera deterministycznie do 25
źródeł: granice, środek, równomierne pozycje oraz pierwszy reprezentant każdego
dostępnego bucketu geometrii.

API przypina `geometrySystemicGuardPolicy` wyłącznie do nowych browserowych
importów i managed reprocessów, a checksumę polityki włącza do fingerprintu
pipeline'u. Worker uruchamia bramkę tylko dla joba z tym dokładnym snapshotem.
W ten sposób stary schema v5 bez polityki zachowuje replay, a nowy job nie może
niepostrzeżenie ominąć bramki.

Próba używa osobnej instancji `ProductionImageStageAdapterSuite` bez
`BoardCellGeometryDeferredWriter`. Dzięki temu wykonuje produkcyjne discovery,
normalizację, geometrię strony, fixed/structured geometrię komórek i finalne
cropy, ale nie może zapisać kolejki ręcznej. Dopiero zaliczony raport pozwala
wywołać `register_files` i uruchomić właściwy `ImageBatchHandler`.

Raport `image-geometry-systemic-guard-v1` jest artefaktem append-only pod
identyfikatorem joba. Jego fingerprint zawiera obie checksumy manifestów,
fingerprint pipeline'u i listę próby. Checkpoint przechowuje checksumę raportu,
pokrycie 3×3, skuteczność końcowej siatki 3×5 i liczbę naruszeń. Każdy późniejszy
checkpoint zachowuje ten dowód, więc UI i restart widzą ten sam wynik.

### Przyrostowe kotwice preflightu strony

Preflight strony może zbudować tymczasową kohortę auto-kotwic dla jednego
niezmiennego stagingu. Kohorta nie jest modelem aktywnym gry i nie zmienia
profilu bazowego. Obejmuje wyłącznie wyniki kompletne, które przeszły
zaostrzoną bramkę, ma ograniczenie dwóch przebiegów i 21 nowych kotwic na
przebieg. Dzięki temu kolejne kąty kamery mogą zostać rozwiązane automatycznie,
ale błąd nie propaguje się przez obniżanie bramek ani syntetyczną geometrię.

Kotwica ręcznego cold-startu jest rozwiązywana względem niezmiennego manifestu
bieżącego stagingu, zanim powstanie managed original. Loader używa kolejno
pliku stagingowego o tej samej checksumie i historycznego content-addressed
originalu. Ta kolejność dotyczy również pierwszej instancji rejestratora, nie
tylko kolejnych przebiegów auto-kotwic. Brak źródła bieżącego i utrata
historycznej kotwicy pozostają odrębnymi błędami fail-closed.

Manifest końcowy jest również planem częściowego wykonania: `registered`
wchodzi do pipeline'u, `review_required` pozostaje w stagingu do późniejszego
ponowienia lub ręcznej korekty. Kolejny import ze świeżym manifestem ponownie
wykorzystuje rejestr kanoniczny, więc wcześniej zatwierdzone plansze nie są
przetwarzane drugi raz.

## Walidacja geometrii w Reviewerze

Etap OCR zachowuje quad obszaru etykiety numeru. Reviewer pobiera checksum-bound
oryginał i renderuje w canvasie viewport będący sumą planszy oraz etykiety.
Nie tworzy kolejnego dużego artefaktu. Dla danych historycznych viewport
rozszerza quad planszy o margines z przewagą dolnej części.

Pierwszy `sourceContextBounds` pozostaje metadanym kadrem referencyjnym przez
wszystkie ręczne rewizje geometrii. Rewizja materializuje nową planszę roboczą
i `rows × columns` cropów bezpośrednio z oryginału, ale nie tworzy obrazu z
narysowanym overlayem. Overlay jest wyłącznie warstwą canvasa w lokalnym
Reviewerze.

Kolejka game-wide korzysta z jednego właściciela logicznego numeru oraz
bounded keysetu. Szybkie zatwierdzenie i edycja wiążą rewizję decyzji,
geometrii, checksumę i wymiary źródła oraz snapshot topologii. Edytor używa
czterech narożników w kolejności LT, PT, PD, LD; linie wewnętrzne i cropy są
wyprowadzane z topologii planszy. Nowy widok nie ładuje katalogu symboli.

Rollout pozostaje lokalny. Remote Reviewer nadal używa dotychczasowego,
scope-bound API i jego proxy nie dopuszcza nowych game-wide endpointów.

## Obserwowalność

Każdy etap pipeline'u zapisuje czas wykonania. Raport skali agreguje czas,
throughput i liczbę elementów bez skanowania całej historii przy każdym
checkpointcie. Obowiązują istniejące lane'y i kolejki; ten pion nie dodaje
Redis, Celery, mikroserwisu ani nowego workera.

Końcowy raport rollout'u oraz przypięte checksumy benchmarków znajdują się w
`ai_docs/quality/BOARD_CELL_GEOMETRY_V19_ROLLOUT.md`.

## Model neuronowy — ścieżka awaryjna

Jeżeli rejestracja 36-punktowa nie osiąga akceptowalnego pokrycia, te same
niezmienne, kompletne źródła stają się datasetem `image -> 9 × 4 corners`.
Prototyp keypointów pozostaje shadow-only do czasu osobnego odbioru jakości i
wydajności. Nie wolno wracać do kontraktu `image -> four page corners`, bo nie
opisuje niezależnego pochylenia dziewięciu plansz.
