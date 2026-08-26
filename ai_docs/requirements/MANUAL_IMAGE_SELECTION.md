---
title: Local manual image selection
status: accepted
last_updated: 2026-08-25
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
  Operator wybiera trwały skok `1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15` albo `20` zdjęć;
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

Przy wznowieniu aplikacja odczytuje należący do tej samej sesji manifest
`manual-image-selection-output-v1.json`. Jeżeli komplet istniejących wyborów
został świadomie przenumerowany przy zachowaniu tych samych źródłowych ścieżek
i sum kontrolnych, sesja jest atomowo synchronizowana z manifestem: zmienia pierwszy
oraz następny zakres i nazwy własnych decyzji, nie zmieniając indeksu zdjęcia
ani plików. Niezgodny manifest, inna sesja, źródło, kierunek, checksumy lub
nieciągły stan blokują wznowienie zamiast nadpisać wynik błędną numeracją.

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

### Obowiązujący tryb operator-local od v0.7.51

Link i ośmioznakowy kod służą wyłącznie do czasowego odblokowania strony
Reviewera. Po odblokowaniu komputer właściciela nie jest miejscem zapisu
decyzji ani wybranych JPEG-ów. Operator wskazuje na swoim urządzeniu folder
źródłowy oraz katalog nadrzędny z prawem zapisu. Reviewer tworzy w nim folder
`<nazwa folderu źródłowego> wybrane`, na przykład `1 - 19 wybrane`.

Ekran przygotowania od początku pokazuje `Wybierz katalog ze zdjęciami` i
`Wybierz katalog do zapisu`. Katalog nadrzędny może zostać wskazany przed
źródłem; jego uchwyt jest trwały w IndexedDB, a folder wynikowy powstaje po
poznaniu nazwy źródła. Pusty wynik prowadzi do konfiguracji pierwszej planszy i
kierunku, a kompletny manifest automatycznie wznawia zapisane zdjęcie i następny
zakres.

Po rozpoczęciu selekcji główny przycisk `Ekran startowy`, umieszczony po lewej
stronie obok wtórnego `Restart selekcji`, wraca do tego konfiguratora, aby
operator mógł ponownie wskazać katalogi. Po wejściu konfigurator ma zawsze
wizualnie czysty stan początkowy: nie pokazuje poprzednio wybranych katalogów
ani skrótu powrotu do workspace'u. Nie jest to reset: nie usuwa manifestu,
decyzji ani zapisanych JPEG-ów. Ponowne wskazanie zgodnej pary katalogów
odtwarza bieżący kursor i zakres.
W tym trybie wybór innego katalogu zdjęć tworzy albo odnajduje jego własny
lokalny batch. Ponowne wskazanie katalogów zgodnych z istniejącym wynikiem
wznawia jego kursor i zakres; różnica źródła nie jest błędem relinkowania
poprzedniego katalogu. Katalog wyniku z zapisanymi decyzjami musi jednak
zawierać zgodny manifest — pusty lub obcy wynik nie może zastąpić postępu.

Oryginalne bajty zaakceptowanego JPEG-a są zapisywane bezpośrednio w tym
folderze jako `seq_<start>-<end>.jpg`. Decyzja, kursor, następny zakres, uchwyty
folderów oraz konfiguracja sesji są zapisywane w osobnym IndexedDB przeglądarki
operatora. Zoom i obie pozycje scrolla są przechowywane w localStorage tego
samego originu i urządzenia. Host przechowuje wyłącznie kontrolną sesję dostępu,
hash kodu, TTL, lease i audyt odblokowania; nie otrzymuje źródłowego manifestu,
decyzji, JPEG-ów ani wynikowego manifestu operatora.

Panel hosta pokazuje dziesięć najnowszych sesji dostępu i stan połączenia,
posortowane malejąco po dacie utworzenia. Filtr `Aktywne` obejmuje statusy
`draft` i `active`, a `Zakończone` obejmuje `completed`, `expired` i `revoked`;
każdy widok pokazuje maksymalnie dziesięć najnowszych pasujących sesji. Starsze
sesje pozostają w audycie, ale nie zaśmiecają aktywnego widoku. Panel nie
pokazuje serwerowych partii, ich limitu, transferów ani diagnostyki
materializacji, ponieważ aktywny tryb operator-local nie tworzy tych danych na
hoście.

Kod zdalnego dostępu po utworzeniu sesji jest utrwalany wyłącznie w
`localStorage` przeglądarki lokalnego właściciela, pod identyfikatorem sesji i
najpóźniej do jej `expiresAt`. Dane wybranej aktywnej sesji stale pokazują link
oraz kod z przyciskami `Kopiuj link` i `Kopiuj kod`; odświeżenie strony nie
ukrywa kodu na tym samym komputerze. Revoke, lokalne wygaśnięcie albo status
nieaktywny usuwa go z cache. API, baza i logi nadal przechowują wyłącznie hash,
a inny komputer Admina oraz sesje utworzone przed tą zmianą nie mogą odzyskać
surowego kodu.

Zdalny workspace zachowuje semantykę lokalnego narzędzia: naturalne sortowanie,
okno podglądów `±3`, `Enter/F`, `Tab`, `A/Ctrl+Z`, zmianę skoku, fullscreen i
zoom `100–3000%`. Viewport ma poziomy i pionowy scroll przy powiększeniu;
pozycje są przechwytywane bezpośrednio przed zmianą kursora React, po trwałym
zapisie decyzji, i odtwarzane po załadowaniu docelowego podglądu. Oczekujące
odtworzenie jest przypięte do docelowego ordinalu; render stanu `busy` na
poprzednim zdjęciu nie może go skonsumować.
Ścieżka zatwierdzenia przechwytuje pozycję wewnętrznego viewportu zdjęcia już w
momencie komendy Enter/F/klik, przed zapisem pliku i stanem `busy`; automatyczny
scroll wywołany później przez Chrome nie może nadpisać tego snapshotu. Podczas
zmiany ordinalu canvas nie może zostać zastąpiony krótkotrwałym pustym stanem
ani utracić poprzednich wymiarów. Poprzedni JPEG pozostaje szkieletem do chwili
zdekodowania następnego, a scroll jest odtwarzany dopiero dla zdekodowanego
docelowego obrazu. Dzięki temu `scrollHeight` nie spada do wysokości viewportu i
nie wymusza `scrollTop=0`.
Bazowe klasy CSS i funkcja dopasowania obrazu są takie same jak w lokalnym
selektorze. Licznik nie może wyprzedzić trwałego zapisu:
interakcje są szeregowane, plik jest weryfikowany checksumą, a dopiero potem
decyzja i kursor są atomowo zapisywane lokalnie.

Przeglądarka nie ujawnia uchwytu rodzica wybranego folderu źródłowego. Dlatego
operator wskazuje katalog nadrzędny drugim pickerem, a Reviewer tworzy w nim
folder z sufiksem ` wybrane`. Po restarcie uprawnienie do obu uchwytów może
wrócić jako `prompt`; ponowne wyrażenie zgody nie usuwa lokalnego postępu.
Przeglądarka bez trwałego File System Access API nie może wykonywać tego trybu
zapisu i ma pokazać jawny błąd zamiast obiecać synchronizację.

Folder `<źródło> wybrane` jest przyjmowany tylko w jednym z dwóch stanów:

- jest całkowicie pusty i rozpoczyna nową selekcję,
- zawiera poprawny `manual-image-selection-output-v1.json` oraz dokładnie
  wskazane przez niego pliki `seq_*`, dzięki czemu Reviewer odtwarza pozycję
  źródłowego JPEG-a, następny dziewięcioplanowy zakres i wszystkie decyzje.

Folder niepusty bez manifestu, z obcym plikiem, brakującym `seq_*`, inną nazwą
źródła, liczbą plików albo checksumą manifestu źródłowego blokuje rozpoczęcie.
Nowy manifest zapisuje tożsamość źródła, liczbę JPEG-ów, pierwszy zakres i
kierunek. Podczas wznowienia przez nowy link losowe identyfikatory plików z
poprzedniej sesji są bezpiecznie mapowane na bieżący indeks według ordinalu i
względnej ścieżki; sesja dostępu nie jest właścicielem danych operatora.

Reviewer utrwala również uchwyt wskazanego katalogu nadrzędnego. Jeżeli
utworzony przez aplikację folder `<źródło> wybrane` zostanie później usunięty,
powrót do karty, ponowne otwarcie strony albo pierwsza operacja zakończona
`NotFoundError` zeruje decyzje, kursor i następny zakres oraz odłącza oba
nieaktualne uchwyty. Operator musi ponownie wskazać ten sam folder zdjęć, który
jest sprawdzany względem zachowanego manifestu, a następnie katalog nadrzędny
wyniku. Dopiero jawne uruchomienie zapisuje nowy pusty manifest i rozpoczyna od
pierwszego zdjęcia. Jawny przycisk `Restart selekcji` wykonuje ten sam reset od
pierwszego zdjęcia i może wyczyścić istniejący folder dopiero po potwierdzeniu
operatora.
Przed usunięciem Reviewer musi zweryfikować manifest, źródło i checksumy
wszystkich zarządzanych JPEG-ów; obcy albo zmieniony plik blokuje restart.
Potwierdzenie resetu jest własnym modalem z liczbą usuwanych zdjęć, informacją o
nieodwracalności i gwarancją, że katalog źródłowy pozostaje nienaruszony.
Podczas wyświetlania modala skróty oraz akcje workspace'u są zablokowane.

Poniższy opis control outboxu, transferu i materializacji na hoście dokumentuje
historyczny wariant v0.7.27–v0.7.50. Nie jest wykonywany przez obowiązujący
workspace operator-local. Pozostaje odtwarzalny dla audytu i nie może zostać
ponownie włączony bez nowej decyzji architektonicznej.

### Historyczny wariant transferu do hosta

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

TASK-0284 zachowuje zdalne cofanie po materializacji. `Deselect` i `undo` są
trwałymi operacjami nowej generacji, które wskazują wcześniejszy potwierdzony
wybór. Starsze transfery są anulowane, a istniejący własny plik może zostać
wyłącznie przeniesiony do odwracalnej kwarantanny po zgodności journalu i
checksummy. Spóźniony upload lub materializacja starszej generacji nie może
wskrzesić wyniku. Obcy albo zmieniony plik pozostaje nietknięty, a brak dostępu
kończy się kontrolowanym konfliktem zamiast deklaracji sukcesu. Finalne usuwanie
z kwarantanny nie jest częścią tego etapu.

TASK-0285 udostępnia właściwy zdalny workspace na tym samym modelu zakresów i
skrótów co lokalny Admin. Operator najpierw rejestruje logiczną kolekcję i
partię z naturalnie uporządkowanego manifestu, a potem pracuje wyłącznie na
lokalnych podglądach z ograniczonego okna bieżący indeks ±3. Object URL-e są
zwalniane po wyjściu z okna; nazwa folderu jest tylko etykietą i żadna
absolutna ścieżka ani Blob nie trafia do transportu lub IndexedDB.

Zdalne `Enter/F`, `Tab` i `A/Ctrl+Z` zapisują stan zakresu oraz odpowiadającą mu
operację atomowo przed zmianą widoku. Nawigacja, przeskok, zoom do 3000%, pełny
ekran i pionowy scroll pozostają lokalne i nie czekają na sieć. UI rozróżnia
`selected_local`, pending, potwierdzenie operacji, finalne `synced` i błąd;
potwierdzenie operacji nigdy nie jest przedstawiane jako zapis finalnego JPEG-a.
Synchronizacja control plane oraz maksymalnie dwa transfery działają w tle.
Offline, konflikt, utrata permission i backpressure są jawne, a zamknięcie karty
z outboxem lub transferem wyświetla ostrzeżenie.

Zdalny workspace używa tego samego systemu wizualnego co lokalna ręczna
selekcja: nagłówka, toolbaru, przycisków nawigacji, płótna zdjęcia i paska
decyzji. Viewport udostępnia poziomy i pionowy scroll dla powiększonego zdjęcia;
obraz mieszczący się w widoku pozostaje wycentrowany. Po zmianie zdjęcia obie
pozycje scrolla są odtwarzane dopiero po załadowaniu obrazu i przeliczeniu jego
rozmiaru, również gdy przejście wynika z decyzji `Enter/F`, pominięcia albo
cofnięcia. Odtworzenie następuje po dwóch kolejnych klatkach layoutu, aby
mobilna przeglądarka nie ograniczyła pozycji do wymiarów poprzedniego obrazu.
Podgląd zajmuje pełną szerokość bez bocznego panelu; legenda skrótów znajduje
się pod zdjęciem, a nad workspace'em pozostają jedynie operacyjne przyciski
synchronizacji i sprawdzenia gotowości.

Polecenia operatora są szeregowane i nie mogą być po cichu odrzucane przez
trwający lokalny zapis. Cofnięcie wraca do zdjęcia, którego decyzję usuwa.
Finalizacja czeka na wcześniejsze interakcje i jest blokowana, dopóki lokalny
outbox nie jest pusty; żądanie synchronizacji dopisane podczas aktywnego cyklu
powoduje kolejny cykl przed zwolnieniem bariery.
Skan transferów używa kursora odpornego na równoległe przewinięcie wstecz przez
nową decyzję. Starszy przebieg nie może przesunąć kursora za świeżo zatwierdzony
plik; potwierdzony `select` musi rozpocząć transfer JPEG-a i materializację.
Stan delta zawsze aktualizuje także kanoniczny `lastClientSequence`. Jeżeli
inna karta zużyła numer, jednorazowa naprawa zachowuje treść i `operationId`
każdej niepotwierdzonej operacji, nadaje całemu outboxowi kolejne numery od
zegara hosta i ponawia go w pierwotnej kolejności. Koordynator kart używa
osobnego, pamięciowego identyfikatora karty, dlatego dwie karty ze skopiowanym
`sessionStorage` nie mogą równocześnie zostać writerem.

### Panel hosta zdalnej selekcji

Niezależna od gry zakładka Admina pokazuje nad lokalnym narzędziem osobny panel
hosta. Właściciel wybiera bazę kontrolowanym pickerem, nadaje sesji czytelną
etykietę i TTL od 5 minut do 24 godzin. Ścieżka bazy nie jest wyświetlana ani
zwracana przez API. Surowy kod z odpowiedzi create jest utrwalany tylko w
lokalnym `localStorage` tego panelu do TTL albo revoke i jest pokazywany przy
wybranej aktywnej sesji obok dynamicznego linku. Nie trafia do listy API,
bazy, logów ani na inny komputer właściciela.

Lista do 100 sesji odtwarza się po reloadzie bez sekretów serwera. Dla jednej
wybranej sesji Admin odpytuje ograniczony monitor maksymalnie 100 najnowszych partii i
pokazuje stan ingressu, writer lease, wolne miejsce, liczniki wybranych i
zsynchronizowanych plików, oczekujące akcje oraz stabilne kody błędów. URL jest
dynamiczną projekcją bieżącego wspólnego ingressu, dlatego po restarcie tunelu
można skopiować nowy link bez tworzenia nowej sesji.

Zatrzymanie jest dwustopniowe i wskazuje dokładny identyfikator sesji. Revoke
czyści dostęp tej sesji, ale nie zatrzymuje wspólnego tunelu ani innych prac
Reviewera. Panel nie finalizuje partii i nie edytuje plików.

### Finalizacja zdalnej partii

Operator może zakończyć aktywną partię dopiero po jawnym sprawdzeniu gotowości.
Serwer jest źródłem prawdy dla blokad: outbox musi być uzgodniony, transfery i
akcje hosta zakończone, a każdy aktualnie wybrany JPEG musi istnieć pod własną
nazwą `seq_*` z potwierdzoną checksumą. Stan lokalnego UI nie może samodzielnie
zadeklarować sukcesu.

Finalizacja zapisuje w katalogu partii istniejące, niezmienione semantycznie
manifesty v1. Output zawiera tylko bieżące materializowane generacje; trace
zawiera zastosowane zdarzenia w porządku klienta, w tym jawne undo. Manifest
operacyjny z rewizjami, transferami i ownership pozostaje pod wewnętrznym
katalogiem hosta i nie jest wejściem importu plansz.

Po sukcesie Reviewer zachowuje nawigację i podgląd, ale blokuje decyzje. Tylko
lokalny właściciel może ponownie otworzyć dokładną partię, podając bieżącą
rewizję oraz checksumę finalnego manifestu. Publiczny proxy nigdy nie
udostępnia reopen ani zapisu manifestu.

### Recovery i diagnostyka zdalnej partii

Po restarcie API i general workera ograniczony reconciler sprawdza wyłącznie
aktywne próby starsze od timeoutu. Plik `.verified` może zostać odzyskany tylko
po zgodności rozmiaru i SHA-256 z deklaracją transferu. `.part`, brak pliku,
obca zawartość lub niezgodna generacja nigdy nie zmieniają stanu na
`verified`; próba staje się kontrolowanym `failed`, a lokalny scheduler tworzy
nowy `transferId` bez utraty decyzji.

State delta pokazuje oddzielnie pending operations, uploady i oczekujące bajty,
materializacje, wszystkie akcje hosta, zsynchronizowane pliki, konflikty oraz
ostatni heartbeat writera. Polling działa z ograniczonym backoffem i nie może
tworzyć równoległych pętli. Lokalny Admin może pobrać zagregowany preview
osieroconych artefaktów; wynik nie zawiera ścieżek i nie oferuje operacji
usuwania. Automatyczny GC pozostaje zabroniony.

### Bramka bezpieczeństwa trybu zdalnego

Publiczny proxy jest default-deny, a jego dokładna macierz metod i ścieżek musi
odpowiadać publicznym operacjom z OpenAPI. Dodanie nowej operacji backendu bez
jawnej aktualizacji allowlisty i testu ma blokować bramkę. Admin, legacy
Reviewer, joby, importy, storage i dowolne ścieżki hosta nie są osiągalne przez
`/selection-api`.

Każda mutacja wymaga zgodnego `Origin` oraz
`Sec-Fetch-Site: same-origin`. Nagłówki `X-Forwarded-*` nie mogą zmieniać hosta,
z którym porównywany jest Origin. Cookie selekcji nie autoryzuje Reviewera i
odwrotnie; token jednej sesji nie może odczytać ani zmienić drugiej sesji.

Publiczne odpowiedzi oraz audit payloady są sprawdzane rekurencyjnie. Sekret,
credential-like key lub absolutna ścieżka Windows/UNC powoduje kontrolowany
błąd zamiast publikacji danych. Rate limit jest liczony per sesja także dla
exact replay, a zmiana `clientInstanceId` nie odnawia budżetu. Limity pliku,
łącznych bajtów tymczasowych i współbieżności pozostają fail-closed.

Bramkę potwierdza content-addressed raport
`remote-manual-selection-security-gate-v1`. Raport nie może mieć otwartego
findingu `critical` lub `high`. Test przez publiczny Quick Tunnel i etapowy
rollout pozostają osobnym TASK 18.
