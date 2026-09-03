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
