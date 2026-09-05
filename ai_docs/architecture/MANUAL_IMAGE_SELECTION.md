---
title: Local manual image selection architecture
status: accepted
last_updated: 2026-08-30
---

# Architektura lokalnej ręcznej selekcji

Workspace React działa wyłącznie w przeglądarce Admina. Wspólny lokalny
koordynator `showDirectoryPicker` serializuje tylko aktywne natywne dialogi
wszystkich workflowów Admina i zawsze wywołuje metodę z `window` jako receiver.
Nie kolejkuje późniejszego dialogu, bo browser wymaga bezpośredniego user gesture;
zamiast tego zwraca stabilny błąd, a po sukcesie, anulowaniu lub konflikcie
zewnętrznego dialogu natychmiast zwalnia lock. Nie obejmuje on jobów ani
operacji plikowych. Picker udostępnia dwa uchwyty File System Access API: źródło
tylko do odczytu oraz folder wynikowy z prawem odczytu i zapisu. Rekurencyjne listowanie i naturalne
sortowanie są czystą logiką w `manual-image-selection.ts`. Indeks przechowuje
uchwyty i ścieżki bez otwierania wszystkich Blobów. Workspace utrzymuje
ograniczony cache Object URL dla bieżącego JPEG-a i trzech sąsiadów z każdej
strony, wywołuje `decode()` jako read-ahead oraz zwalnia URL-e poza oknem.
Lista `images` zawsze pozostaje w naturalnym porządku. `currentIndex` jest
trwałym ordinalem tego źródła; nowa sesja zaczyna od `0`, `→` i Enter zwiększają
ordinal, a `←` go zmniejsza. Kierunek sesji steruje wyłącznie zmianą zakresu
`seq_*` po zatwierdzeniu. Dzięki temu IndexedDB, cache, trace i wznowienie
wskazują ten sam fizyczny JPEG niezależnie od kierunku numeracji plansz.

Sesje są przechowywane w osobnej bazie IndexedDB
`game-predictor-manual-image-selection`, w magazynie `sessions`. Historyczne
pole klucza `gameId` pozostaje dla zgodności schematu v2, ale nowy workspace
zawsze używa stabilnego lokalnego identyfikatora
`local-independent-manual-image-selection`; nie jest to identyfikator domenowej
gry. Rekord obejmuje uchwyty folderów i serializowalny stan decyzji, więc nie
wymaga migracji backendowej ani tabel domenowych. Magazyn `traceEvents` nadal
ma klucz złożony `(gameId, sessionKey, eventIndex)`.

Jeżeli niezależny rekord jeszcze nie istnieje, store wybiera deterministycznie
najnowszą historyczną sesję per gra, kopiuje ją oraz należące do niej zdarzenia
do nowego namespace'u i zachowuje stary rekord. `sessionKey` nie zmienia się,
więc istniejący manifest w folderze wynikowym nadal należy do tej samej sesji.
LocalStorage służy tylko do szybkiego odtworzenia kursora diagnostycznego i
używa tego samego niezależnego identyfikatora.

Przed wznowieniem workspace czyta output manifest przez zapisany uchwyt folderu
i porównuje go ze stanem IndexedDB. Wyłącznie manifest należący do tej samej
sesji, z tym samym źródłem, kierunkiem, kolejnością wybranych plików i
checksumami może przesunąć numerację wszystkich decyzji o jeden stały offset.
Synchronizacja utrwala nowy rekord IndexedDB przed pokazaniem następnego JPEG-a;
nie modyfikuje źródłowych obrazów, istniejących wyników ani append-only trace.
Operator może także jawnie zmienić wyłącznie bieżący `nextRangeStart` przez
zakres do dziewięciu plansz. Bez granicy jest to `start–start+8`; końcowa
strona sesji z `sequenceUpperBound` kończy się na
`min(start+8, sequenceUpperBound)`. Taka korekta nie zmienia `firstLayout`, poprzednich
decyzji ani plików, a po akceptacji następny zakres jest liczony od ręcznie
podanej wartości zgodnie z kierunkiem sesji. Dlatego stan i manifest sprawdzają
każdy zakres niezależnie; nie wymagają sztucznej ciągłości między decyzjami.
Niepoprawny zakres, obca nazwa `seq_*` lub niezgodna checksum pozostają
fail-closed.

Rekord lokalnej sesji zapisuje `cursorSemantics: source_path_v3` oraz
`cursorImagePath`. Ta ścieżka jest trwałą tożsamością bieżącego JPEG-a i przy
wznowieniu jest ponownie mapowana w naturalnie posortowanym źródle; indeks
pozostaje wyłącznie pomocniczym ordinalem cache i nawigacji. Rekordy
historyczne bez ścieżki są jednorazowo migrowane. Rekord `source_path_v2` z
kierunkiem malejącym jest także historyczny: jego ścieżka mogła już wskazywać
lustrzany ordinal. W takim przypadku ostatni zatwierdzony plik jest silniejszą
kotwicą, a następnym zdjęciem jest zawsze kolejny ordinal naturalnej listy.
Trace `viewed` nie jest dowodem formatu, ponieważ mógł powstać już po błędnym
wznowieniu. Brak zapisanej ścieżki w źródle blokuje wznowienie zamiast wskazać
niewłaściwy JPEG. Wynik migracji jest utrwalany przed pokazaniem zdjęcia.

Uchwyt File System Access API reprezentuje tożsamość katalogu, a nie wyłącznie
jego tekstową ścieżkę. `NotFoundError` po usunięciu, przeniesieniu lub ponownym
utworzeniu katalogu uruchamia kontrolowane ponowne powiązanie. Operator wskazuje
osobno źródło albo wynik, aplikacja najpierw potwierdza możliwość listowania,
a następnie zastępuje wyłącznie uchwyty i nazwę źródła w istniejącym rekordzie.
Stan, `sessionKey` i trace pozostają niezmienne, a poprawiony rekord jest
utrwalany przed otwarciem przeglądarki zdjęć.

Workspace zapisuje dwa jawne artefakty przez wybrany uchwyt folderu wynikowego:
kompaktowy `manual-image-selection-output-v1.json` oraz, na żądanie operatora,
`manual-image-selection-trace-v1.json`. Manifest wyjściowy jest synchronizowany
po każdym Enterze, Tabie i Ctrl+Z, natomiast pełny ślad jest materializowany
poza ścieżką krytyczną sesji. Każdy zapis sprawdza właściciela `sessionKey`, aby
nie nadpisać artefaktu innej sesji.

Nazwa pliku output pozostaje historyczna, lecz bieżący writer materializuje
schema v2 z `sequenceUpperBound`, `selectionComplete` oraz
`activeBoardCount` dla każdego zaakceptowanego zakresu. Reader rozpoznaje
wersję z pola `schemaVersion`: v1 zawsze oznacza pełne strony dziewięciu
plansz, a v2 może zakończyć sesję krótszą, ciągłą stroną. Ta sama domena i
walidacja są współdzielone przez lokalny Admin i operator-local Reviewer;
historyczny host-transfer pozostaje na kontrakcie v1.

W aktywnej sesji globalny handler klawiatury obsługuje `Enter`/`F` jako
zatwierdzenie, `Ctrl+Z`/`A` jako cofnięcie, lewo/prawo jako nawigację po
zdjęciach oraz góra/dół jako przejście po sąsiednich pozycjach wersjonowanej
listy skoku. Zmiana skoku przechodzi przez tę samą serializowaną kolejkę zapisu
sesji w IndexedDB. Handler ignoruje pola edycyjne, selecty, przyciski i elementy
`contenteditable`, aby skróty nie przejmowały interakcji formularza.

Zapis pliku jest atomizowany na poziomie uchwytu: źródłowy Blob jest kopiowany
bez transformacji, checksum SHA-256 jest porównywany z istniejącym plikiem,
zapis jest zamykany, a wynik jest odczytywany ponownie i weryfikowany. Usunięcie
przez undo wymaga zgodnego checksumu; plik obcy lub zmieniony nigdy nie jest
nadpisywany ani usuwany automatycznie.

Nie ma endpointu HTTP, joba, workera ani API/OpenAPI dla tego workspace'u.
Kontrakt serwerowy pozostaje właścicielem automatycznej selekcji i importu;
lokalny fallback zapisuje wyłącznie pliki przygotowane do późniejszego,
jawnego importu layoutów. Pełny ekran używa `requestFullscreen` na kontenerze
podglądu. Zoom oblicza rzeczywiste wymiary layoutu z naturalnego rozmiaru JPEG-a
i aktualnego viewportu, dzięki czemu pionowy scroll obejmuje cały obraz;
viewport ukrywa poziomy overflow i centruje nadmiar obrazu bez ingerencji w
Blob.

Bieżący `scrollTop` viewportu jest przechowywany w zwykłym `useRef`. Przejście
na inny indeks oznacza pozycję jako oczekującą na odtworzenie; dopiero po
dekodowaniu obrazu i obliczeniu jego rzeczywistych wymiarów pojedynczy
`requestAnimationFrame` ustawia `scrollTop`. Zdarzenia scrolla nie zmieniają
stanu React, IndexedDB ani trace manifestu, więc nie dodają pracy do ścieżki
zapisu i dekodowania JPEG-a.

Podczas przejściowego odmontowania canvasa przeglądarka może zgłosić techniczne
`scrollTop=0`. Viewer przyjmuje nowe współrzędne wyłącznie wtedy, gdy Object URL
nadal odpowiada bieżącemu indeksowi; zdarzenie z pustego/loading viewportu nie
może nadpisać ostatniej pozycji. Ta sama reguła obejmuje zwykłą selekcję, fill i
delete.

## Architektura lokalnej korekty selekcji

`ManualSelectionRepairWorkspace` jest montowany bezpośrednio po lokalnym
workspace i korzysta ze współdzielonego `ManualImageViewer`. Viewer odpowiada
wyłącznie za bounded cache Object URL, zoom, fullscreen, scroll i prezentacyjne
skróty. Domena zakresów i manifestów znajduje się w niezależnym eksporcie
`@game-predictor/manual-image-selection-core/repair`, dlatego nie zależy od
Reacta ani File System Access API.

Adapter Admina `manual-selection-repair-storage.ts` jest jedynym miejscem
mutacji katalogu. Skanuje top-level JPEG-i, weryfikuje SHA-256, zapisuje
manifesty i utrzymuje osobną IndexedDB v1 bez Blobów. Wszystkie polecenia
workspace'u przechodzą przez jedną serializowaną kolejkę. Zmiana katalogu lub
trybu jest blokowana podczas zapisu.

Pełny skan i weryfikacja output manifestu odbywają się przy otwarciu katalogu
oraz recovery. Po udanej mutacji adapter zwraca finalny repair/output manifest
i uchwyt zmienionego pliku, a workspace aktualizuje posortowany snapshot przez
dodanie albo usunięcie jednego wpisu. Dzięki temu delete nie wykonuje dwóch
pełnych przebiegów SHA-256 po wszystkich JPEG-ach; nadal hashuje dokładnie
usuwany plik i zachowuje journal fail-closed.

Paczka `Usuwanie sekwencji` jest tylko wygodnym frontem tej samej kolejki
adaptera. Jej autocomplete indeksuje `start` ze zweryfikowanych nazw
`seq_<start>-<end>`, filtruje go prefiksem tekstowym i przekazuje do kolejki
dokładne nazwy, a nie wyprowadzony zakres liczbowy. Każdy plik ma własną
transakcję journal → mutacja → manifest; sukcesy są raportowane inkrementalnie.
Awaria checksummy jednego pliku jest izolowana, natomiast błąd zapisu journalu,
odzyskania uprawnienia uchwytu lub synchronizacji manifestu zatrzymuje kolejkę,
aby nie obiecać spójnego lokalnego stanu. Nie ma trash ani Blobowego restore.

Przy pełnej inspekcji reload/recovery znana checksuma jest weryfikowana w
`reconcileRepairManifest`; następna synchronizacja output manifestu dostaje
ten sam wynik i nie odczytuje JPEG-a ponownie. Workspace ma niezależny numer
generacji recovery: ręczny wybór katalogu lub katalogu bazowego zwiększa go,
więc późniejsza odpowiedź starego IndexedDB recovery nie może nadpisać
aktualnego snapshotu ani uchwytu. Fazy wyboru systemowego, inspekcji i
listowania są stanem UI, a nie pozornym zawieszeniem; natywny picker pozostaje
jedyną blokadą współdzielonego pickera katalogów.

`manual-image-selection-repair-v1.json` zachowuje niezmienne granice kolekcji,
aktywny indeks plików, checksumy, usunięte zakresy, append-only historię oraz
co najwyżej jedną operację oczekującą. Każda mutacja ma trzy fazy:

1. zapis zamiaru z oczekiwaną nazwą i checksumą;
2. dokładna zmiana jednego pliku przez uchwyt katalogu;
3. ponowny odczyt, kontrola SHA-256 i finalizacja obu manifestów.

Reconciler po reloadzie rozstrzyga stan na podstawie pliku, rozmiaru i
checksummy. Obcy lub zmieniony cel pozostaje fail-closed. Katalog bazowy fill
jest zawsze read-only, a zapisany JPEG zachowuje oryginalne bajty. Delete undo
przechowuje ostatni `File` wyłącznie w pamięci komponentu, więc nie jest
możliwy po reloadzie.

Pochodny `manual-image-selection-filled-gaps-v1.json` jest materializowany przy
każdym zapisie repair manifestu. Jego wpisy są deterministycznie wyprowadzane z
append-only operacji `fill` oraz bieżącego `activeFiles`; nie jest drugim
źródłem decyzji. Konsument może odtworzyć brakujący handoff bezpośrednio z
repair manifestu, a uszkodzony plik handoffu blokuje użycie fail-closed.

Output manifest pozostaje bieżącym źródłem aktywnych wyborów i jest
synchronizowany po fill, undo, delete oraz restore. Repair trace jest osobnym
źródłem proweniencji. Ranker może scalić z pierwotnym trace tylko poprawnie
zdekodowane zdarzenia `viewed` i `fill`; pozytywem jest wyłącznie plik nadal
obecny w aktywnym output manifeście. Zdarzenia delete, restore i undo nie mogą
samodzielnie utworzyć próbki treningowej.

Zwykły lokalny selector sprawdza obecność repair manifestu przed startem i
resume. W takim przypadku nie modyfikuje katalogu ani starej sesji, tylko
kieruje operatora do nowej sekcji. Zapobiega to dwóm writerom utrzymującym
różne listy aktywnych `seq_*`.

## Architektura lokalnego przycinania wybranych zdjęć

Poprawka TASK-0472 usuwa sztuczne halo dylatacji przed pomiarem bboxa; halo
dotykające brzegu pozostaje konserwatywnie niepełnym wsparciem źródła.
Scalanie wymaga pokrycia większego komponentu, nie tylko zawierania mniejszego.
Kontrola szerokości i proporcji etykiet poprzedza ranking odległości od dolnej
granicy. Zmiany identyfikuje fingerprint v11; wariant pozostaje nieaktywny po
nieprzejściowej bramce, bez zmiany historycznych algorytmów v10.

Eksperymentalny v11 (0469–0471, bez aktywacji) analizuje luminancję i strukturę
całego 3×3. Wspólny sampler z kanonicznego RGBA ogranicza dłuższy bok do
960/1600, a wynik zapisuje fingerprint i wykonane poziomy. Brak dziewięciu
obszarów numerów lub układu zwraca pełną wysokość i trwały obowiązek korekty.
Obowiązek jest wyprowadzany z wyników i ręcznych decyzji, nie ze zbioru zaznaczeń.
Node zapisuje `.crop-preparation-v11`: metadane, intencje per plik, shardy 64,
blokadę właściciela i raport błędów. JPEG jest publikowany bez nadpisania,
następnie weryfikowany SHA przed finalizacją. Browser przejmuje wyłącznie
zakończony handoff; aktywna blokada lub intencja blokuje równoległy zapis.
Stare katalogi z ręcznym stanem przeglądarki nie są mutowane przez Node.

TASK-0468 ustanawia niezależny test-only oracle jakości poziomego pasa:
SHA-256 źródeł, wizualne obwiednie plansz/numerów, przedziały linii i split po
katalogach. Runner odtwarza v10 bez zapisu obrazów. Adnotacje nie są zależnością
detektora ani referencją do treningu narożników. Opis v10 poniżej jest opisem
implementacji z wykrytymi regresjami, nie potwierdzeniem jej bezpieczeństwa.
V11 pozostaje do wdrożenia w kolejnych taskach; brak nowych kontraktów API.

`SelectedImageCropWorkspace` jest lokalnym konsumentem współdzielonego
`ManualImageViewer`. Viewer zachowuje ograniczone okno Object URL, zoom,
fullscreen i scroll; opcjonalny overlay renderuje dwie poziome linie bez
zmiany zachowania istniejących selektorów.

Czysta domena jest eksportowana jako
`@game-predictor/manual-image-selection-core/crop`. Operuje na współrzędnych
całkowitych `topY`/`bottomY` w obrazie po jednokrotnej kanonizacji EXIF i nie
zna Reacta, canvasa ani File System Access API. Adapter Admina skanuje tylko
główny poziom źródła, ponownie wykorzystuje rygorystyczny parser `seq_*` i
utrzymuje osobną IndexedDB v1 bez Blobów.

Adapter ma dwa rozłączne tryby inwentarza: pełny katalog zapisuje do
`<źródło> cut`, a aktywne uzupełnienia do `<źródło> filled-gaps cut`. Drugi tryb
czyta handoff repairu, odrzuca pusty lub obcy manifest i sprawdza checksumę
każdego wskazanego JPEG-a przed utworzeniem albo wznowieniem sesji. Dzięki
osobnym nazwom katalogów manifest v1 nadal jednoznacznie wiąże swój inwentarz.

Detektor `@game-predictor/manual-image-selection-core/auto-crop` otrzymuje
wyłącznie RGBA ograniczonego podglądu o szerokości najwyżej 512 px. Polityka
v10 buduje lekką maskę czerwonych ramek, łączy jej komponenty i szuka trzech
podobnych kandydatów o rosnących współrzędnych X, zgodnych wysokościach oraz
lokalnie wspólnej linii. Kandydaci muszą leżeć w ograniczonym sąsiedztwie
górnej granicy uzyskanej z detektora panelu. Wynik wyznacza wyłącznie górę;
dół oraz fail-safe nadal pochodzą z v9. Brak pełnego dowodu jest no-opem.

Polityka v9
dzieli środkowe 88% obrazu na dziewięć pasów i w każdym niezależnie znajduje
długi klaster niebieskiego tła. Dopiero co najmniej pięć zgodnych klastrów,
obejmujących lewą, środkową i prawą grupę, tworzy granicę panelu. Rozrzut
górnych i dolnych granic jest ograniczony, dzięki czemu boczne światła lub
pojedyncze elementy nie mogą udawać plansz.

Potwierdzony w ten sposób panel jest niezależnym dowodem i może zastąpić
`safe_wide` ogólnego detektora. Naprawia to regresję v5, która odrzucała nawet
mocny panel, gdy drugi detektor nie dostarczył równocześnie kandydata.
Historyczne wyniki v4/v5 pozostają czytelne i nie są przeliczane automatycznie.

Jeżeli nie ma takiego kandydata, zachowana ścieżka wielokolumnowa v4
analizuje środkowe 94% obrazu w dziewięciu pionowych pasach. Dla każdego pasa
buduje wygładzone profile chromatyczne i strukturalne, a kandydat musi mieć
wsparcie co najmniej pięciu pasów oraz wszystkich trzech grup szerokości.
Zgodne kandydatury obu rodzin dowodu dają `high_confidence`; rozbieżność tworzy
bezpieczną sumę `conservative`, natomiast brak dowodu zwraca `safe_wide` 5–95%.
`safe_wide` jest automatycznie utrwalany w kolejce korekty i nie może zostać
potraktowany jak zwykły gotowy wynik bez świadomego review.

Lokalne granice są agregowane percentylami, więc pochylenie obrazu nie wymusza
ciasnego cropa według jednego pasa. Padding wynosi 4,5% nad i pod panelem.
4,5% pod panelem. Górna granica nie jest rozszerzana w stronę panelu wypłat.
Dolna strefa bezpieczeństwa 3% odsuwa granicę na zewnątrz najwyżej raz, jeżeli
nadal przecina szeroko wspartą zawartość. Wynik niższy niż 28% wysokości jest
odrzucany na rzecz `safe_wide`. Adapter mapuje granice proporcjonalnie na
kanoniczne piksele źródła. Cache propozycji jest ograniczony do bieżącej sesji
i związany z nazwą, rozmiarem oraz mtime źródła.

Proweniencja propozycji jest częścią `SelectedImageCropResult` w shardzie, a
nie osobnym globalnym plikiem. Zawiera dokładną politykę, klasę, confidence,
lokalne granice obu rodzin sygnału, wykorzystane pasy, IoU, informację o
rozszerzeniu granicy i reason code fallbacku. Ta sama proweniencja znajduje się
w operacji oczekującej, dlatego recovery po zapisie JPEG-a finalizuje dokładnie
ten sam wynik.

Mały session journal przypina `preparationPolicyVersion`. Nowa sesja zaczyna z
v10, natomiast brak pola w historycznym stanie jest interpretowany jako legacy,
bez zgadywania wersji. Taka sesja nie przygotuje brakujących plików nową
polityką, dopóki operator jawnie nie uruchomi przeliczenia. Recalculator
wyprowadza zamknięty zbiór nazw z shardów i review state; chroni `reviewed`,
`corrected` oraz `needs_correction`, a każdy dopuszczony wynik zastępuje przez
istniejący checksum-bound journal. Po przypięciu v10 zwykłe wznowienie może
przygotować pozostałe, dotąd brakujące wyniki.

Renderer używa źródłowego JPEG-a bez pośredniej bitmapy na dysku. Canvas ma
szerokość obrazu kanonicznego i wysokość wybranego pasa, a `drawImage` kopiuje
ten obszar w skali 1:1. Wynik jest JPEG-em jakości 0.98. Operacja przebiega jako
manifest intencji → SHA-256 źródła → render → zapis → ponowny SHA-256 →
finalizacja manifestu. Przy restarcie brak wyniku cofa zamiar, zgodna checksuma
go finalizuje, a obcy wynik blokuje wznowienie.

Przy pierwszym wznowieniu writer migruje manifest v1 do podkatalogu
`.manual-image-crop-state`: niezmiennego inwentarza, małego session journalu,
osobnego review state i shardów wyników obejmujących najwyżej 64 sloty. Plik
inwentarza jest publikowany jako ostatni krok migracji, dlatego jej przerwanie
jest idempotentne. Istniejących cropów ani checksum nie przelicza się.

Przygotowanie pozostaje sekwencyjne, lecz decode, detekcja i pierwszy render są
wykonywane przez okresowo odtwarzany Web Worker z `OffscreenCanvas`. Brak tej
funkcji uruchamia zgodny fallback. Błąd jednego źródła jest zapisywany z etapem
i kodem, po czym kolejka przechodzi dalej; retry otrzymuje zamknięty zbiór nazw.

Review używa atlasów WebP po najwyżej 100 cropów. Klucz atlasu obejmuje nazwy,
checksumy wyników, rozmiar i renderer. Pierwszy atlas jest pokazywany przed
zakończeniem całej kolejki, stare klucze są usuwane bounded. Grid utrzymuje
trwały zbiór `needs_correction`; pełny `ManualImageViewer` dekoduje oryginały
tylko dla tej kolejki. Poprawka aktualizuje jeden shard, review state i atlas.
Zbiorcze zaznaczenie aktualizuje wyłącznie mały review state jednym zapisem;
nie przepisuje shardów, JPEG-ów ani atlasów. Przełącznik działa na bieżącym
filtrze i nie usuwa zaznaczeń niewidocznych w tym filtrze.

Hydratacja po reloadzie kończy się na odczycie rekordu IndexedDB. Wywołanie
`requestPermission`, skan katalogu i odczyt obrazów następują dopiero w obsłudze
jawnego kliknięcia wznowienia. Atlasy v2 144×96 px, kodowane jako WebP jakości
0.58, są budowane osobną akcją operatora i prezentowane w poziomym pasku; samo
otwarcie sesji ich nie dekoduje.
Wyjście anuluje kolejkę pomiędzy źródłami i unieważnia późne callbacki, ale nie
cofa zakończonego journalowanego zapisu bieżącego pliku.

Katalog wynikowy jest bezpieczny wyłącznie, gdy jest pusty albo zawiera zgodny
`manual-image-crop-output-v1.json` i wskazane przez niego wyniki. Import plansz
filtruje wejście do JPEG-ów, dlatego pomocniczy JSON jest ignorowany. To nowa
tożsamość importu; reprocess historycznego importu nadal czyta jego managed
originals. Prostowanie perspektywy pozostaje poza tym adapterem, ponieważ
globalna homografia nie modeluje krzywizny ekranu ani dziewięciu niezależnych
quadów obsługiwanych przez geometrię 36 narożników.
