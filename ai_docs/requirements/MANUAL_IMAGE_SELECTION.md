---
title: Local manual image selection
status: accepted
last_updated: 2026-08-31
---

# Lokalna ręczna selekcja zdjęć

## Cel

Zakładka `Ręczna selekcja` jest awaryjnym, deterministycznym narzędziem do
przypisania pojedynczych JPEG-ów do kolejnych zakresów obejmujących od jednej
do dziewięciu plansz.
Pozwala kontynuować pracę, gdy automatyczny selektor nie daje wystarczającej
pewności, bez uruchamiania API, workera, OCR ani uploadu do stagingu.

## Przebieg

- Ręczna selekcja jest niezależna od gry. Przed rozpoczęciem operator wybiera
  pierwszy numer layoutu, opcjonalny ostatni numer planszy, kierunek numeracji,
  folder źródłowy i folder wynikowy.
- Folder źródłowy jest odczytywany rekurencyjnie. Uwzględniane są wyłącznie
  `.jpg` i `.jpeg`, sortowane naturalnie po względnej ścieżce (tak jak numery w
  nazwach plików). Ten naturalny porządek jest trwałym porządkiem źródłowym
  sesji i indeksu w IndexedDB. Pierwsze zdjęcie ma ordinal `0`, a `→` i Enter
  zawsze przechodzą do kolejnego ordinalu katalogu; `←` przechodzi do
  poprzedniego. Kierunek wpływa wyłącznie na kolejną numerację `seq_*` po
  zatwierdzeniu, nigdy na kolejność zdjęć.
- Początkowe indeksowanie nie otwiera zawartości każdego JPEG-a. Podczas pracy
  aplikacja wyprzedzająco odczytuje i dekoduje ograniczone okno trzech zdjęć z
  każdej strony bieżącej pozycji, aby nawigacja nie wymagała stagingu.
- Zakres jest inkluzywny i domyślnie ma dziewięć pozycji: `start–start+8`.
  Jeżeli sesja ma jawną górną granicę, końcowa strona ma postać
  `start–min(start+8, sequenceUpperBound)` i może zawierać 1–8 plansz.
  Domyślnie po decyzji następny zakres zaczyna się od `start+9` dla kolejności
  rosnącej albo od `start-9` dla malejącej; wartość nie spada poniżej `1`.
  Po osiągnięciu górnej granicy w kierunku rosnącym albo `1` w malejącym
  selekcja przechodzi w stan zakończony i nie przyjmuje kolejnej decyzji;
  cofnięcie ostatniej decyzji ponownie ją otwiera.
  Operator może kliknąć bieżący zakres i jawnie podać nowe `Od` oraz `Do`.
  Formularz przyjmuje wyłącznie dodatni zakres do dziewięciu kolejnych plansz,
  zgodny z granicą sesji.
  Jest to świadoma korekta numeracji: luka między decyzjami może zostać
  zachowana, ale aplikacja nigdy nie uzupełnia jej ani nie zmienia zakresów
  poprzednich decyzji po cichu.
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

`currentIndex` lokalnej sesji jest zawsze ordinalem naturalnie posortowanego
źródła. Nowa sesja zaczyna się od ordinalu `0`, a pozycja pokazywana operatorowi
to `currentIndex + 1`, niezależnie od kierunku numeracji plansz. Nowe sesje
utrwalają także względną ścieżkę bieżącego JPEG-a; wznowienie najpierw mapuje
ten plik w bieżącej naturalnej liście, a indeks pozostaje wyłącznie pomocą dla
starych rekordów. Historyczna sesja bez ścieżki odzyskuje pozycję z ostatniego
zatwierdzonego pliku i ustawia następny ordinal katalogu, po czym utrwala nowy
format. Brak zapisanego JPEG-a blokuje wznowienie zamiast otworzyć inne zdjęcie.

Przy wznowieniu aplikacja odczytuje należący do tej samej sesji manifest
`manual-image-selection-output-v1.json`. Jeżeli komplet istniejących wyborów
został świadomie przenumerowany jednym przesunięciem przy zachowaniu tych samych
źródłowych ścieżek i sum kontrolnych, sesja jest atomowo synchronizowana z
manifestem: zmienia pierwszy oraz następny zakres i nazwy własnych decyzji, nie
zmieniając indeksu zdjęcia ani plików. Jawnie poprawione, nieciągłe zakresy są
odtwarzane dokładnie tak, jak zapisano je w manifestie. Schema v1 zachowuje
historyczną semantykę pełnych stron `start–start+8`; schema v2 wiąże każdą
decyzję z `sequenceUpperBound`, `selectionComplete` i `activeBoardCount`.
Niezgodny manifest, inna sesja,
źródło, kierunek, checksumy, niepoprawny pojedynczy zakres lub próba nadpisania
obcego pliku blokują wznowienie zamiast nadpisać wynik błędną numeracją.

Jeżeli zapisany uchwyt wskazuje folder usunięty, przeniesiony albo utworzony
ponownie pod tą samą ścieżką, workspace nie może porzucić sesji ani tworzyć
nowego postępu. Pokazuje osobno brak folderu źródłowego lub wynikowego, pozwala
wskazać go ponownie i zachowuje `sessionKey`, decyzje, kolejny zakres oraz
indeks zdjęcia. Naprawione uchwyty są ponownie zapisywane w IndexedDB.

W całym lokalnym Adminie może być aktywne tylko jedno okno wyboru folderu.
Wspólny koordynator File System Access utrzymuje blokadę wyłącznie do
rozstrzygnięcia natywnego pickera; drugi klik nie wywołuje przeglądarkowego
dialogu i otrzymuje czytelny komunikat. Job weryfikacji zakresów, skan folderu,
upload i zapis pliku nie trzymają tej blokady, więc `Uzupełnij luki` oraz `Usuń
sekwencje` mogą działać równolegle z OCR po zamknięciu dialogu wyboru folderu.

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
ich zakresy, liczbę aktywnych plansz i checksumy. Historyczna nazwa pliku
pozostaje niezmienna, natomiast nowy zapis ma `schemaVersion = 2`; reader nadal
obsługuje schema v1 bez zmiany jego znaczenia. Zapis jest bezpieczny dla obcych plików: istniejący
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
poznaniu nazwy źródła. Pusty wynik prowadzi do konfiguracji pierwszej planszy,
opcjonalnej ostatniej planszy i kierunku, a kompletny manifest automatycznie
wznawia zapisane zdjęcie, granicę i następny zakres.

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

Zdalny workspace zachowuje semantykę lokalnego narzędzia: naturalne sortowanie
i zawsze rosnący ordinal zdjęcia dla `→`/Enter, niezależny od kierunku
numeracji plansz, okno podglądów `±3`, `Enter/F`, `Tab`, `A/Ctrl+Z`, zmianę
skoku, fullscreen i zoom `100–3000%`. Viewport ma poziomy i pionowy scroll przy powiększeniu;
pozycje są przechwytywane bezpośrednio przed zmianą kursora React, po trwałym
zapisie decyzji, i odtwarzane po załadowaniu docelowego podglądu. Oczekujące
odtworzenie jest przypięte do docelowego ordinalu; render stanu `busy` na
poprzednim zdjęciu nie może go skonsumować.
Kliknięcie bieżącego zakresu otwiera ten sam walidowany edytor `Od`/`Do` co w
lokalnym workspace. Zapis zakresu jest lokalny dla urządzenia operatora,
natychmiast aktualizuje manifest i wstrzymuje skróty workspace'u do zamknięcia
formularza.
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
  źródłowego JPEG-a, następny zakres, granicę końcową i wszystkie decyzje.

Folder niepusty bez manifestu, z obcym plikiem, brakującym `seq_*`, inną nazwą
źródła, liczbą plików albo checksumą manifestu źródłowego blokuje rozpoczęcie.
Nowy manifest schema v2 zapisuje tożsamość źródła, liczbę JPEG-ów, pierwszy
zakres, kierunek, opcjonalną granicę końcową, stan zakończenia oraz semantykę
naturalnego przechodzenia po źródle. Starszy malejący manifest bez tej
semantyki jest wznawiany od zdjęcia bezpośrednio po ostatniej zaakceptowanej
decyzji, a nie od historycznego lustrzanego indeksu. Pominięcie zakresu nie
zmienia tego zdjęciowego punktu odniesienia. Podczas
wznowienia przez nowy link losowe identyfikatory plików z
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

## Lokalna korekta gotowej selekcji

Pod lokalną `Ręczną selekcją zdjęć` Admin pokazuje niezależną kartę
`Popraw selekcję`. Operator wskazuje katalog zawierający wybrane JPEG-i
`seq_<start>-<end>.jpg|jpeg`; narzędzie nie wymaga gry, API ani workera.
Skanowany jest wyłącznie główny poziom katalogu. Zakres ma od jednej do
dziewięciu plansz, a zła nazwa JPEG-a, duplikat, overlap, obcy manifest albo
drift checksummy blokują mutację.

Granice kolekcji pochodzą najpierw z
`manual-image-selection-repair-v1.json`, następnie z poprawnego output
manifestu, a dopiero na końcu z nazw JPEG-ów. Dzięki temu usunięcie skrajnego
pliku pozostawia jawną lukę. Braki są sortowane rosnąco i dzielone od lewej na
targety nie większe niż dziewięć plansz.

### Uzupełnianie luk

Po wybraniu trybu operator wskazuje osobny bazowy katalog zdjęć. Jest on
rekurencyjnie listowany i pozostaje tylko do odczytu. Podgląd rozpoczyna się od
pierwszego naturalnie posortowanego JPEG-a; skok ma wartości
`1, 2, 5, 10, 20, 50, 100`, natomiast target zmienia się po rzeczywistych
lukach. `Enter`, `F` lub przycisk zapisują niezmienione bajty jako dokładny
target `seq_*`, ponownie odczytują plik i weryfikują SHA-256. Akceptacja jest
dostępna dopiero po poprawnym dekodowaniu i co najmniej 300 ms widoczności.

`A`, `Ctrl+A`, `Ctrl+Z` lub przycisk cofają wyłącznie ostatni fill wykonany
przez ten workflow. Cofnięcie wymaga zgodnej checksummy i nigdy nie usuwa
obcego albo zmienionego pliku.

### Usuwanie sekwencji

Tryb `Usuń sekwencje` pokazuje jeden istniejący plik `seq_*` i nawiguje zawsze
o jeden. `F` usuwa bieżący, checksummowany JPEG. `A` lub `Ctrl+A` może
przywrócić wyłącznie ostatni plik, którego `File` pozostaje w pamięci otwartej
karty. Reload, zamknięcie karty albo następne usunięcie usuwa możliwość tego
jednopoziomowego przywrócenia. Trwały repair manifest zachowuje samą decyzję i
lukę, ale nie przechowuje Blobu.

Obok tej akcji dostępne jest `Usuwanie sekwencji` dla paczki plików. Po
wskazaniu katalogu `seq_*` modal przyjmuje wyłącznie numeryczny prefiks
`start` z nazwy `seq_<start>-<end>.jpg|jpeg`: wpis `45` znajduje zakresy
zaczynające się od `45`, a wpis `678` nie znajduje `45678`. Enter lub kliknięcie
dodaje dokładną nazwę pliku do listy „Nazwa pliku”; każdy wiersz można usunąć z
listy ikoną kosza. Dopiero jawne potwierdzenie usuwa wskazane pliki lokalnie,
bez kosza i bez możliwości przywrócenia. Wynik pokazuje osobno każdy sukces
i izolowany błąd. Błąd uchwytu katalogu albo journalu zatrzymuje pozostałą
paczkę fail-closed; błąd pojedynczego pliku nie unieważnia poprawnie
przetworzonych pozostałych pozycji.

Zmiana zdjęcia, fill, delete, restore ani undo nie mogą zerować zapamiętanej
pozycji viewportu. Wspólny viewer ignoruje przejściowe zdarzenie scrolla
powstałe podczas wymiany Object URL i odtwarza pozycję dopiero po dekodowaniu
docelowego zdjęcia. Po bezpiecznej mutacji jednego pliku workspace aktualizuje
indeks katalogu inkrementalnie; nie wolno ponownie hashować całego katalogu po
każdym usunięciu. Pełna walidacja nazw i checksum pozostaje obowiązkowa przy
pierwszym otwarciu oraz po reloadzie.

Jedna inspekcja odczytuje i hashuje każdy znany JPEG najwyżej raz. Jeżeli
repair manifest zawiera już checksumę, reconciler weryfikuje ją na rzeczywistym
pliku, a synchronizacja output manifestu wykorzystuje ten sam zweryfikowany
wynik zamiast wykonywać drugi pełny odczyt Blobu. Podczas recovery, wyboru
katalogu `seq_*` i rekurencyjnego listowania katalogu bazowego UI pokazuje
aktualną fazę; ręczne wskazanie katalogu unieważnia spóźnione recovery i jest
natychmiast utrwalane w IndexedDB.

### Trwałość i instrukcja operatora

Repair manifest jest journalem intencji `fill`, `undo_fill`, `delete` i
`restore`. Przed zmianą pliku zapisuje operację oczekującą, a po restarcie
obecność pliku i SHA-256 pozwalają ją bezpiecznie dokończyć albo wycofać
logicznie. Osobna IndexedDB przechowuje tylko uchwyty, tryb, kursory i
preferencje podglądu — nigdy JPEG-i.

Każdy zapis repair manifestu synchronizuje też pochodny
`manual-image-selection-filled-gaps-v1.json`. Zawiera on wyłącznie nadal
aktywne pliki utworzone przez `fill`: docelową nazwę i zakres `seq_*`, SHA-256,
ścieżkę źródłową, indeks oraz identyfikator i czas operacji. Cofnięte albo
ponownie usunięte uzupełnienie znika z aktywnej listy. Repair manifest pozostaje
źródłem prawdy, więc brakujący historyczny handoff można odtworzyć bez zmiany
JPEG-ów.

Operator wykonuje kolejno:

1. wybiera katalog gotowych `seq_*`;
2. wybiera `Uzupełnij luki` albo `Usuń sekwencje`;
3. w trybie uzupełniania wskazuje bazowy katalog zdjęć;
4. wykonuje checksummowane decyzje i może cofnąć ostatnią operację;
5. po zakończeniu importuje bieżącą zawartość katalogu `seq_*`.

Jeżeli zwykła ręczna selekcja wykryje repair manifest, nie próbuje przejąć
katalogu. Kieruje operatora do `Popraw selekcję`. Aktywny output manifest jest
jedynym źródłem wybranych pozytywów; usunięte wpisy nie mogą trafić do importu
ani kohorty treningowej.
## Przycinanie wybranych zdjęć przed importem

Pod `Semi-auto selekcja` działa lokalna karta `Przytnij wybrane zdjęcia`.
Operator wskazuje katalog nadrzędny z prawem zapisu i wybiera jego bezpośredni
podkatalog zawierający poprawnie nazwane JPEG-i
`seq_<start>-<end>.jpg|jpeg`. Narzędzie tworzy obok katalog
`<nazwa źródła> cut`; źródła nigdy nie są modyfikowane.

Operator może zamiast pełnego katalogu wybrać `Tylko uzupełnione luki z
manifestu`. Narzędzie pobiera wtedy dokładną aktywną listę z repair handoffu i
przed startem sprawdza obecność oraz SHA-256 każdego pliku. Wyniki trafiają do
osobnego katalogu `<nazwa źródła> filled-gaps cut`, dlatego pełna i ograniczona
sesja nie współdzielą inwentarza ani postępu.

Automat dla każdego jeszcze niezatwierdzonego zdjęcia niezależnie analizuje
ograniczoną kopię podglądową do 512 px i proponuje pas obejmujący zwarty panel
plansz. Polityka `selected-image-board-band-v8-tight-top-boundary`
wyznacza niebieski panel niezależnie w dziewięciu pionowych pasach i wymaga
zgodnych granic w co najmniej pięciu pasach oraz w lewej, środkowej i prawej
części obrazu. Tak potwierdzony panel jest wystarczającym dowodem nawet wtedy,
gdy ogólny detektor nie zbudował własnego kandydata. Panel wypłat, boczne
światła i pojedynczy niebieski element nie spełniają tej bramki.

Jeżeli niebieski panel nie ma pełnego wsparcia, automat korzysta z
wielokolumnowego detektora v4. Historyczna polityka v5 pozostaje akceptowana w
manifestach i nie jest przeliczana po cichu.
Historyczna polityka `selected-image-board-band-v4-conservative-multicolumn`
dzieli środkowe 94% obrazu na dziewięć pasów i łączy niezależny sygnał koloru,
nasycenia, kontrastu oraz powtarzalnych krawędzi. Automatyczna granica wymaga
wsparcia w co najmniej pięciu pasach oraz w lewej, środkowej i prawej części;
pojedyncza tabela, światło albo dłoń nie mogą przesunąć całego cropa.

Pochylenie jest uwzględniane przez lokalne granice pasów i bezpieczną
obwiednię: 10. percentyl górnych granic minus 3% wysokości oraz 90. percentyl
dolnych granic plus 4,5%. Górna granica nie rozszerza się w stronę panelu
wypłat. Mocny, szeroki sygnał przy dolnej granicy rozszerza crop na zewnątrz
najwyżej o jeden krok 3%. Kandydat niższy niż 28% obrazu nie jest używany.
Brak wystarczającego dowodu daje jawny `safe_wide` równy 5–95% wysokości i
automatycznie kieruje plik do kolejki `Do poprawy`. Propozycja nie jest decyzją
i zawsze pozostaje edytowalna dwiema liniami.

Każdy nowy wynik zapisuje w swoim shardzie wersję polityki, klasę
`high_confidence | conservative | safe_wide`, confidence, lokalne granice,
użyte rodziny sygnału oraz powód fallbacku. Kafelki pokazują odpowiednio
`Pewne`, `Zachowawcze` albo `Szerokie — sprawdź`, a filtr `Niepewne` obejmuje
dwie ostatnie klasy. Wynik historyczny bez tej proweniencji pozostaje czytelny
i nie jest automatycznie przeliczany.

Jawna akcja `Przelicz nieprzejrzane nowym detektorem` może przełączyć
rozpoczętą sesję na bieżącą politykę. Obejmuje wyłącznie wyniki nieprzejrzane, niepoprawione
ręcznie i niezaznaczone do poprawy, a następnie przygotowuje brakujące pliki.

W widoku kafelkowym jeden przycisk przełącza `Zaznacz wszystkie` i `Odznacz
wszystkie`. Działa na przygotowanych wynikach bieżącego filtra, zachowuje
zaznaczenia ukryte przez filtr i utrwala cały zbiór jednym małym zapisem review.
Każda zmiana ponownie sprawdza SHA-256 źródła i bieżącego wyniku oraz przechodzi
przez ten sam journal co pojedyncza poprawka. Akcja nigdy nie zmienia wyników
zaakceptowanych przez operatora.

Narzędzie usuwa wyłącznie obszar nad górną i pod dolną przeciąganą linią.
Zachowuje pełną szerokość, kanoniczną orientację EXIF, perspektywę oraz
rozdzielczość 1:1 wybranego pasa. Nie wykonuje obrotu, homografii, prostowania
zakrzywionego ekranu ani automatycznej geometrii dziewięciu plansz.

Automat kolejno renderuje brakujące JPEG-i do katalogu `cut`, ale błąd jednego
pliku nie zatrzymuje pozostałych. Każdy błąd zachowuje nazwę, etap i kod, a
operator może ponowić wyłącznie brakujące wyniki. Przygotowane cropy są dostępne
do przeglądu od razu, również gdy dalsze pliki są jeszcze przetwarzane.

Review pokazuje jeden ciągły grid wszystkich źródeł. Gotowe wyniki są
prezentowane przez lokalne, progresywnie tworzone atlasy WebP po maksymalnie 100
miniaturek; brakujący lub błędny wynik ma jawny placeholder. Kliknięcie kafelka
oznacza `Do poprawy`, nie zatwierdza ani nie modyfikuje JPEG-a. `Popraw
zaznaczone` otwiera wyłącznie wybrane oryginały z liniami cięcia. Zapis poprawki
zastępuje jeden własny crop i unieważnia tylko jego atlas. Zakończenie przeglądu
jest możliwe po przygotowaniu wszystkich plików, rozwiązaniu błędów i opróżnieniu
kolejki korekt. Miniatury 144×96 px pozostają w jednym poziomym, przewijanym
rzędzie, bez automatycznego zmniejszania albo zawijania.

Historyczny `manual-image-crop-output-v1.json` jest przy pierwszym wznowieniu
indeksowany do wersji v2 bez ponownego renderowania i hashowania istniejących
JPEG-ów. Wersja v2 rozdziela niezmienny inwentarz, mały stan sesji, kompaktowy
stan review oraz wyniki w shardach po maksymalnie 64 pozycje. IndexedDB nadal
zawiera wyłącznie uchwyty, kursor, zoom i scroll.

Reload nie może automatycznie odczytywać utrwalonego uchwytu ani żądać
uprawnienia do katalogu. Pokazuje wyłącznie lekką informację o zapisanej sesji;
operator wznawia ją jawnym kliknięciem. Atlasy miniaturek również są opt-in i
powstają dopiero po kliknięciu `Wczytaj miniaturki`. Kafelki mają poglądową,
obniżoną rozdzielczość oraz jakość WebP. `Wyjdź i wybierz inny katalog`
zatrzymuje przygotowanie między plikami, zachowuje dotychczasowe wyniki i wraca
do wyboru katalogu.

Po zakończeniu operator wykonuje nowy import katalogu `cut`. Ponowne
przetworzenie starego importu nadal świadomie używa jego niezmiennych managed
originals, więc nie może zostać po cichu przełączone na nowe, przycięte pliki.
Profil geometrii i model symboli pozostają wersjonowane niezależnie.
