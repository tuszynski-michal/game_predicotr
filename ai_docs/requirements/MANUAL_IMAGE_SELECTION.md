---
title: Local manual image selection
status: accepted
last_updated: 2026-08-18
---

# Lokalna ręczna selekcja zdjęć

## Cel

Zakładka `Ręczna selekcja` jest awaryjnym, deterministycznym narzędziem do
przypisania pojedynczych JPEG-ów do kolejnych dziewięcioplanowych zakresów.
Pozwala kontynuować pracę, gdy automatyczny selektor nie daje wystarczającej
pewności, bez uruchamiania API, workera, OCR ani uploadu do stagingu.

## Przebieg

- Ręczna selekcja jest niezależna od gry. Przed rozpoczęciem operator wybiera
  pierwszy numer layoutu, kierunek kolejności zdjęć, folder źródłowy i folder
  wynikowy.
- Folder źródłowy jest odczytywany rekurencyjnie. Uwzględniane są wyłącznie
  `.jpg` i `.jpeg`, sortowane naturalnie po względnej ścieżce (tak jak numery w
  nazwach plików), z możliwością odwrócenia kolejności.
- Początkowe indeksowanie nie otwiera zawartości każdego JPEG-a. Podczas pracy
  aplikacja wyprzedzająco odczytuje i dekoduje ograniczone okno trzech zdjęć z
  każdej strony bieżącej pozycji, aby nawigacja nie wymagała stagingu.
- Zakres jest inkluzywny i zawsze ma dziewięć pozycji: `start–start+8`.
  Po zaakceptowaniu następny zakres zaczyna się od `start+9`.
- `Enter` zapisuje bieżące zdjęcie jako `seq_<start>-<end>.jpg` w wybranym
  folderze i przechodzi do następnego zdjęcia oraz zakresu.
- `Tab` pomija bieżące zdjęcie dla zakresu i przechodzi do następnego zakresu,
  pozostawiając ten sam obraz do ponownego wykorzystania.
- Strzałki lewo/prawo zmieniają wyświetlane zdjęcie bez zmiany zakresu ani
  decyzji. Strzałka w dół wybiera następną wartość skoku, a strzałka w górę
  poprzednią; na krańcach lista pozostaje odpowiednio przy `1` albo `20`.
  Operator wybiera trwały skok `1, 2, 3, 4, 5, 6, 7, 10, 15` albo `20` zdjęć;
  Enter po zapisie nadal przechodzi dokładnie o jedno zdjęcie. Select zachowuje
  czytelne ciemne tło również po rozwinięciu natywnej listy opcji.
- Podgląd ma natywny tryb pełnoekranowy oraz zoom `100–3000%`; oba dotyczą
  wyłącznie prezentacji bieżącego JPEG-a i nie zmieniają pliku zapisywanego na
  dysku. Powiększony obraz ma pionowy viewport, więc można przewinąć go od
  góry do dołu; poziomo pozostaje wyśrodkowany, a nadmiar jest celowo obcięty
  po bokach bez poziomego scrolla. Pełny ekran zawsze pokazuje także bieżący
  zakres, pozycję i nazwę pliku. Przejście między JPEG-ami zachowuje bieżącą
  pionową pozycję viewportu w ramach aktywnej sesji; krótszy obraz jest
  naturalnie ograniczany do własnego maksymalnego scrolla.
- `Ctrl+Z` albo pojedyncze `A` cofa ostatnią decyzję i usuwa tylko plik, który
  aplikacja wcześniej zapisała oraz którego checksum nadal odpowiada źródłu.
- `Enter` albo pojedyncze `F` zatwierdza bieżące zdjęcie; skróty nie działają,
  gdy fokus znajduje się w polu formularza, selectu, przycisku lub innym
  elemencie edytowalnym. Ta sama ochrona dotyczy pionowych strzałek zmiany
  skoku, dzięki czemu select zachowuje własną natywną obsługę klawiatury.

## Trwałość i bezpieczeństwo

Stan sesji (foldery, indeks zdjęcia, zakres i decyzje) jest zapisywany w
IndexedDB pod jednym stabilnym kluczem lokalnego narzędzia i odtwarzany po
ponownym wejściu do zakładki, niezależnie od bieżącej nawigacji gry. Przy
pierwszym wejściu po zmianie najnowsza historyczna sesja zapisana wcześniej per
gra jest kopiowana do niezależnego namespace'u razem ze swoim śladem; rekord
historyczny nie jest usuwany. Uchwyt folderu może wymagać ponownego nadania
uprawnień przez przeglądarkę.

Jeżeli zapisany uchwyt wskazuje folder usunięty, przeniesiony albo utworzony
ponownie pod tą samą ścieżką, workspace nie może porzucić sesji ani tworzyć
nowego postępu. Pokazuje osobno brak folderu źródłowego lub wynikowego, pozwala
wskazać go ponownie i zachowuje `sessionKey`, decyzje, kolejny zakres oraz
indeks zdjęcia. Naprawione uchwyty są ponownie zapisywane w IndexedDB.

W danym momencie może być aktywne tylko jedno okno wyboru folderu. Oba przyciski
wyboru są blokowane podczas aktywnego pickera, a ponowne kliknięcie jest
obsługiwane jako komunikat zamiast drugiego wywołania przeglądarkowego dialogu.

Zapis korzysta z File System Access API i kopiuje oryginalne bajty JPEG-a, bez
skalowania, obrotu ani zmiany perspektywy. Istniejący plik wynikowy jest
idempotentny, gdy checksum jest taki sam; obcy plik o tej samej nazwie blokuje
nadpisanie. Nie są wysyłane obrazy ani decyzje do backendu.

### Manifest i ślad uczenia

IndexedDB ma wersję 2. Oprócz sesji utrzymuje append-only magazyn zdarzeń
`traceEvents`. Zdarzenie `viewed` powstaje dopiero po udanym `decode()` i co
najmniej 300 ms rzeczywistej widoczności obrazu. `Enter` zapisuje zdarzenie
`accepted` z zakresem, ścieżką, indeksem i checksumą; `Tab` zapisuje `skipped`
bez tworzenia negatywnej etykiety. `Ctrl+Z` zapisuje `undo`, powiązane z cofniętą
decyzją. Niedekodowane lub szybko przewinięte obrazy nie są etykietowane.

W folderze wynikowym utrzymywany jest kompaktowy
`manual-image-selection-output-v1.json`. Zawiera wyłącznie zaakceptowane pliki,
ich zakresy i checksumy. Zapis jest bezpieczny dla obcych plików: istniejący
manifest innej sesji albo o nieprawidłowej strukturze blokuje nadpisanie.
Pełny `manual-image-selection-trace-v1.json` jest tworzony dopiero po jawnej
akcji `Eksportuj ślad uczenia`; jego źródłem są zdarzenia z IndexedDB.

Dotychczasowe sesje nie mają pewnego czasu widoczności i pozostają
`anchor_only`: można je eksportować i używać jako kotwic, ale nie tworzą
automatycznie par treningowych rankera.

Ta zakładka jest narzędziem lokalnym i nie zmienia automatycznego kontraktu
selekcji zdjęć, stagingu ani importu layoutów.

## Fundament trybu zdalnego

Zdalny Reviewer utrzymuje osobny, wersjonowany IndexedDB i nie współdzieli
namespace'u ani migracji lokalnego narzędzia Admina. W wersji 1 przechowuje
wyłącznie sesję, partię, metadane źródłowych JPEG-ów, kursor, client instance,
transfer checkpoints oraz niepotwierdzony outbox. Blobów JPEG i absolutnych
ścieżek nie wolno zapisywać w IndexedDB.

Źródło File System Access jest otwierane wyłącznie do odczytu. Po każdym resume
permission jest sprawdzany ponownie. Brak uchwytu lub prawa odczytu zachowuje
kursor oraz outbox i wymaga relinku. Relink jest dozwolony tylko dla identycznego
checksumowanego manifestu; inny folder, zmieniony plik albo inny rodzaj źródła
jest odrzucany. `webkitdirectory` jest fallbackiem sesyjnym i po reloadzie
wymaga ponownego wskazania tego samego manifestu.

Każda przyszła zdalna mutacja wpływająca na wynik musi najpierw zostać trwale
dopisana do outboxu. Lokalna decyzja pozostaje `pending`, dopóki host nie
potwierdzi dokładnego `operationId`; ack nie może usuwać innych operacji.
Odświeżenie albo utrata procesu odtwarza ten sam kursor i pełny zbiór pending ID.
TASK-0280 przygotował tę trwałość, TASK-0281 uruchomił operacje HTTP, a
TASK-0282 dodaje jednoplikowy transfer JPEG. Blob nadal nie trafia do IndexedDB:
checkpoint przechowuje tylko stały `transferId`, generację, oczekiwany rozmiar i
checksumę, liczbę potwierdzonych bajtów oraz stan.

Transfer może wystartować wyłącznie po potwierdzonym `SELECT` bieżącej
generacji. Klient najpierw odczytuje status; istniejący stan `verified` kończy
retry bez ponownego wysyłania. Nowy upload jest ograniczony schedulerem i
wysyłany jako jeden strumień `application/octet-stream`. Host zapisuje `.part`,
liczy SHA-256 w locie, sprawdza długość, magic i pełny decode JPEG, a dopiero
potem atomowo publikuje prywatny artefakt `verified`. Finalna nazwa `seq_*` nie
powstaje przed osobną materializacją.

TASK-0283 realizuje tę materializację jako trzecią, host-only kolejkę. Dla
bieżącej potwierdzonej generacji powstaje idempotentna akcja z lease, fencing,
ograniczonym retry i backoffem. Worker przed zapisem ponownie sprawdza desired
state, generację i checksumę, a następnie publikuje plik `seq_*` wyłącznie pod
zweryfikowanym markerem partii. Same-volume plik roboczy, flush i wewnętrzny
journal pozwalają wznowić każdy półstan po crashu. Istniejący cel bez zgodnego
journalu własności albo ze zmienioną checksumą nie może zostać nadpisany.

Publiczne potwierdzenie `synced` jest dozwolone dopiero po zgodności finalnego
pliku i atomowym commicie stanu pliku, transferu, akcji oraz licznika partii.
Status i odpowiedzi publiczne nadal nie zawierają host path. Reconciliacja przy
statusie i w general workerze uzupełnia brakującą akcję dla istniejącego
`verified`; stara generacja zostaje `superseded`. Materializacja nie finalizuje
manifestu partii i nie usuwa verified temp.
