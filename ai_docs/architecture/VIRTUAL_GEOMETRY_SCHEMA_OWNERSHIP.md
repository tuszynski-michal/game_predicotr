---
title: Virtual geometry schema ownership
status: accepted
last_updated: 2026-09-22
---

# Virtual geometry schema ownership

## Pilot Mumie → Gang shared shape v2 — TASK-0609

Lokalny runner G05 jest wyłącznie właścicielem pomiaru i raportu operator-owned
corpusów. Wymusza kolejność istniejącego aktywnego profilu, zaakceptowanej
korekty Mumii, replayu, regresji pełnej kohorty wcześniejszych gier oraz
transferu do gry spoza wkładu. Każda obserwacja zawiera checksumę badanego
profilu; zmiana kandydata lub baseline unieważnia jej użycie. Wynik mierzy
osobno automaty, review, korektę, potwierdzenie i czas operatora, dlatego
porównanie przed/po odnosi się wyłącznie do identycznej kohorty.

Jedynie wynik `measured` może przejść przez wewnętrzną granicę publicznego
control plane; runner nie otwiera magazynu gry, nie zapisuje geometrii lokalnej
ani nie uruchamia importu. Kandydat i raport przekazywane dalej pozostają
identifier-free względem źródeł: nie zawierają obrazów, ścieżek, `game_id`,
OCR, symboli, sekwencji ani lokalnych kotwic.

## Kwalifikacja i aktywacja shared shape v2 — TASK-0608

`global_geometry_profile_qualification_results` i receipty kwalifikacji należą
do globalnego publicznego control plane. Są audytem decyzji o wspólnym profilu,
nie właścicielem lokalnej geometrii: przechowują wyłącznie descriptor-only
raport, checksumy i krótkie referencje proweniencji bez `game_id`, obrazów,
plików, kotwic albo routingu gry. Zmieniają status wersji profilu tylko w
jednej transakcji po kwalifikacji `passed`; `not_evaluable` i `rejected` nie
mogą uruchomić preflightu, importu ani wpłynąć na historyczny snapshot joba.

## Deklaracja gry i projekcja gotowości shape v2 — TASK-0607

`games.shape_geometry_configuration` należy do control plane katalogu gry i
określa tylko rodzinę strony. Nie jest profilem lokalnym, nie wskazuje kotwicy
ani obrazu i nie przenosi danych importu między grami. `NULL` rekordu
historycznego jest odczytywany fail-closed jako `requires_clarification`.

Read model katalogu może odczytać tylko jeden integralny globalny profil
`active` rodziny `framed_full_page_v2` i ujawnia wyłącznie jego immutable
referencję. Nie odczytuje JPEG-ów, dowodów, routingu ani `game_id` z biblioteki;
candidate/rejected/retired, konflikt i uszkodzenie nie dają gotowości. Projekcja
nie ma prawa uruchomić preflightu, importu ani zmienić historycznego joba.

## Resolver i preflight shape v2 — TASK-0606

Nowy preflight `page-geometry-preflight-v4-shape-geometry-v2-profile` przypina
tylko jeden aktywny profil `framed_full_page_v2` 3 × 3 / 3 × 5. Snapshot joba
zawiera identyfikator, numer i checksumę profilu, pełną kontrolę checksumy
z descriptorowymi dowodami, checksumę zamkniętych descriptorów oraz
lokalną politykę `structural_only`; wpis manifestu nie może później odczytać
innej aktywnej wersji ani użyć `game_id` z biblioteki.

Worker kontroluje bieżące piksele rdzeniem G02 i zapisuje per źródło jego dowód,
aspect ratio oraz werdykt. Nawet kompletna propozycja dostaje
`review_required` bez `quads` i bez statusu `registered`; istniejący importer
nie może jej wykorzystać przed późniejszym, jawnym etapem. Brak aktywnego
profilu zachowuje preflighty v2/v3, a ręczna override nadal ma pierwszeństwo.
V4 nie tworzy legacy registrara ani nie ładuje jego kotwic.

## Wspólna biblioteka shape v2 — TASK-0605

Globalna biblioteka `framed_full_page_v2` jest osobnym publicznym control
plane, a nie właścicielem geometrii konkretnego źródła. Zapisuje jedynie
checksummowany szablon, topologię, descriptor ramki i metryki dowodu; nie
zawiera obrazu, cropa, kotwicy ORB, symbolu, OCR, payoutu ani sekwencji.
`source_game_ref` pozostaje opisową proweniencją bez `game_id` i bez routingu.

Profil ma status `candidate` po G06. Dopiero G03 może przypiąć zgodny snapshot
do nowego preflightu, a G07 kwalifikuje i aktywuje go automatycznie. Lokalna
geometria, snapshot joba, ręczna kwalifikacja i wynik importu nadal należą do
jednej gry i nie są nadpisywane przez bibliotekę.

## Finalna bramka wariantu v0.10.4 (TASK-0515)

`LATERAL_PARTIAL_RELEASED` jest teraz `True` na podstawie immutable raportu
związanego checksumami korpusu i polityki. Jest to pozwolenie na istniejący,
jawny wariant per-run, a nie nowy stan schematu, flaga środowiskowa ani zmiana
domyślnej polityki gry. Snapshot v4, provenance automatycznej propozycji i
obowiązek ręcznego potwierdzenia pozostają bez zmian. Nie dodano migracji.

## Opt-in snapshot v0.10.4 (TASK-0510)

### Trwałe źródła i własność przy reprocessingu (TASK-0513)

Istniejący job/import i preflight otrzymują opt-in rozszerzenia, bez migracji.
Manifest przypina politykę, source selection, SHA browser inventory, quady oraz
dowód lateral do checksumy pojedynczego źródła. Loader nie wykonuje detekcji.
Powtórzenie tego samego requestu jest idempotentne, stary run pozostaje niezmienny.

Preflight z `managed_source_job_id` i SHA managed inventory nie odczytuje plików
browser stagingu. Weryfikuje oryginały i wykorzystuje ich istniejące ścieżki;
tylko mały manifest pochodzenia jest klonowany pod nowy job. Restart odtwarza
przypięte wejście. Stary descriptor strony nie jest wymagany przy jawnym nowym.

Projekcja v4 rezerwuje wszystkie sekwencje przed blokadą źródła; lease joba
nadal jest sprawdzany w transakcji. Edytor i deferred writer stosują również
sequence → source, a wspólny state katalogu symboli jest blokowany później.
Mutacja symboli blokuje sequence i bieżące rows przed state; eliminuje to cykl
state → sequence wobec workerowego sequence → source → state.
Wybór pending ownera blokuje tylko mutowane review i board; nie blokuje
niezmiennego JobModel używanego wyłącznie do porównania kolejności importów.
Nie zmienia się reguła legacy newest-import-wins dla niechronionych wyników.

Pod sequence lock v4 nie zastępuje ręcznych geometrii, kwalifikacji, masek ani
decyzji symboli. Odrzucenie jest wiązane również z SHA źródła. Rozliczenie guard
bez recognized_board wymaga osobnego przepięcia niezmiennego manifestu;
aktualnie fail-closed przed tworzeniem runu, zamiast utraty odrzucenia/partiala.

`geometryEngineVariant` jest żądaniem rozszerzenia pojedynczego runu, nie
wartością globalnego `image_geometry_rollout_states.geometry_mode`. Nowy
`virtual-geometry-rollout-snapshot-v4` zawiera niezmienione `activeLatticeGeometry`
bazy v3 oraz `lateralPartialGeometry` z pełną wersjonowaną polityką i checksumą.
Checksum całego rolloutu oraz fingerprint pipeline'u obejmują rozszerzenie.
Stare schematy nie emitują nowego pola; pole v4 pod historyczną wersją jest
odrzucane. Retry czyta przypięty payload, a nie aktualne ustawienie gry.

`automatic-lateral-partial-proposal-v1` jawnie deklaruje `automatic_proposal`
i obowiązek ręcznego potwierdzenia. Używa istniejącej maski/kwalifikacji
dostępności, ale nie staje się decyzją operatora ani zatwierdzoną kotwicą.
Publiczne uruchomienie oraz worker są fail-closed do wdrożenia detektora
i zaliczenia bramki jakości. Ten fundament nie wymaga migracji bazy.

## Boczne kandydatury rejestracji (TASK-0511)

Opcjonalny wynik `lateral-page-registration-candidate-v1` jest dowodem do
lokalnego przeszukania, nie rewizją geometrii. Ma `analysisQuads`, jawne
aktywne sloty, kotwicę, homografię i checksumę przypiętej polityki v4.
Nie emituje `quads` ani `finalQuad` i pozostawia wynik rejestracji odrzucony.
Nie wolno uczynić go auto-kotwicą ani renderować bez lokalnego dopasowania.

Kandydat powstaje wyłącznie w istniejącym przebiegu po dopasowaniu ORB/RANSAC,
przy bocznym braku podparcia źródłem. Progi inlierów, reprojekcji i czerwonych
krawędzi pozostają niezmienione. Walidacja wypukłości, kolejności i overlapu
wykorzystuje ten sam algorytm w przesuniętej przestrzeni współrzędnych, bez
alokacji powiększonej bitmapy. Oryginalna i dopasowana propozycja muszą mieć
pełne podparcie pionowe; horyzont homografii oraz całkiem brakująca plansza
odrzucają kandydaturę. Jeżeli zwykły wynik zostanie znaleziony w dalszej
istniejącej próbie, ma pierwszeństwo. Integracja nowego manifestu jest
oddzielnym TASK-0513; historyczne manifesty nie są rozszerzane w miejscu.

## Wewnętrzny adapter lateral lattice v4 (TASK-0512)

`lattice_refinement_v4` nie modyfikuje refinerów v19/v3. Najpierw wywołuje v3,
a potem opcjonalnie analizuje odrzucony slot związany z kandydaturą 0511.
Wiązanie kandydatury z checksumą źródła jest odpowiedzialnością wersjonowanego
manifestu/runu (0513); lokalny adapter porównuje przypiętą politykę, slot i quad.

Analiza ma bitmapę 500×300 i osobną maskę rzeczywistego podparcia źródłem.
Niepodparte próbki nie stają się kandydatami symboli. Bbox komponentu wraz
z obwódką musi być całkowicie podparty. Są to dane analizy, nie cropy.
Jeden deterministyczny RANSAC ocenia maksymalnie 256 czteropunktowych podzbiorów
z lokalnym RNG i wykonuje jeden refit konsensusu. Nie zmienia globalnego RNG
OpenCV ani stanu następnego wywołania v3. Hipotezy początków kolumn wynikają
z algebraicznego przesunięcia tej samej macierzy, bez powtórnego dopasowania.

Polityka lateral-partial-v1 konserwatywnie wymaga zgodności indeksowania z
obszarem wyszukiwania: maksymalnie 45 px różnicy narożników w analizie 500×300,
nie zewnętrznego quada jako wyniku awaryjnego. Progi area 0,55–1,15, spacing,
residual 10 px i ochrona bbox pozostają zgodne z bramkami lokalnej geometrii.
Brak dowodu, większa niepewność lub konkurencyjne hipotezy oznaczają review.

Wynik przechowuje `automaticPartialProposal` obok `symbolGridQuad`, a nie
ręczną rewizję. Domenowy guard VirtualBoardGeometry nadal zabrania renderu
automatycznej częściowej planszy; jawne potwierdzenie przechodzi istniejącą
ścieżką ręcznej kwalifikacji. Nie wprowadzamy równoległego mechanizmu maski.

Projekcja kolejki review rozdziela obecność gotowej geometrii od jej braku.
Odroczony slot z kanoniczną propozycją i poprawnym czteropunktowym
`symbolGridQuad` ma stan `needs_validation`, `manualGeometryRequired=false` i
udostępnia quad jako nakładkę startową. Współrzędne bocznej siatki mogą być
ujemne, ponieważ brakująca kolumna leży poza źródłem. Slot bez poprawnego quada
pozostaje `needs_correction` i dostaje ręczny szablon.

Potwierdzenie źródła zawierającego automatyczną propozycję używa istniejącego
atomowego zapisu geometrii całego źródła. Przenosi quad, `pendingGeometryId` i
kwalifikację `pending_partial`; dopiero utworzona rewizja jest decyzją
operatora. Edycja źródła mieszanego zachowuje wszystkie dostępne quady i
otwiera ręczne wskazywanie tylko dla slotów z
`manualGeometryRequired=true`.

## Historyczna kompletna siatka przy osłabionej ramce (TASK-0549, TASK-0561)

Polityka `structured-lattice-v4-lateral-partial-v3` zachowuje
historyczne zachowanie v1/v2 i dodaje kandydaturę
`lateral-page-registration-candidate-v2`. Pole `recoveryKind` rozdziela
dotychczasowy brak bocznego podparcia od `frame_support_review`, a
`reviewRequiredSlots` wiąże decyzję ze slotami, których ozdobna ramka nie
przeszła progu automatycznego. Checksumowany snapshot zawiera przełącznik tej
gałęzi, dlatego retry i nowy proces odtwarzają dokładnie tę samą politykę.

Kandydatura ramki nie jest geometrią domenową. Powstaje dopiero po pełnych
bramkach rejestracji strony, bezpiecznym średnim dowodzie czerwonych krawędzi i
ograniczeniu liczby słabych slotów. Jej quad inicjalizacyjny jest jedynie
obszarem lokalnego refinera. Refiner musi niezależnie odzyskać kompletną siatkę
3×5 z podparciem treścią; wynik zapisuje jako
`automatic-frame-geometry-proposal-v1`, nigdy jako część boczną.

`automaticFrameProposal` ma kwalifikację `complete`, pustą maskę i jawne
wykluczenie ze zwykłego uczenia geometrii. Projekcja kolejki klasyfikuje go jako
`needs_validation`, udostępnia quad do nakładki i ustawia
`manualGeometryRequired=false`. Atomowe potwierdzenie źródła materializuje
quad oraz tę kwalifikację; brak propozycji zachowuje `needs_correction`.
`automaticPartialProposal` i jego `pending_partial` pozostają odrębnym
kontraktem.

TASK-0561 wycofuje tę gałąź z nowych preflightów po regresji rzeczywistego
stagingu `45163 - 70371 cut`: v2 miała 40 pozycji ręcznej korekty, a v3 355.
Produkcja ponownie tworzy snapshot v1 bez profilu albo v2 z profilem. Parser,
worker, API i Reviewer zachowują obsługę v3 oraz `automaticFrameProposal`
wyłącznie po to, aby istniejące joby i manifesty pozostały odtwarzalne.

## Szkice ręcznej kwalifikacji (TASK-0507)

Szkic przeglądarki nie jest rewizją źródła. Przechowuje tylko współrzędne,
oznaczenia i bazową rewizję w kontekście gry/importu/preflightu/SHA zdjęcia.
API page override i guard przyjmują opcjonalny expected revision; niezgodny
zapis kończy się konfliktem. Identyczny, już utrwalony wynik może być zwrócony
przy ponowieniu po utracie odpowiedzi. Constraint konflikt równoległych
rewizji jest tłumaczony w savepoincie, bez nadpisania zwycięskiej decyzji.
Usuwanie lokalnego szkicu po sukcesie porównuje własny wysłany stan z
aktualnym storage; nie usuwa szkicu drugiej karty ani nowszej rewizji.
Nawigacja nie zapisuje API. Nowe flagi nadal wymagają integracji konsumentów
TASK-0508, przed zdjęciem bramek `QUALIFICATION_NOT_ENABLED`.

## Cel i granica decyzji

Ten dokument ustala jednego właściciela każdego elementu geometrii po
addytywnym fundamencie migracji 0082. Opisuje stan docelowy dla kolejnej
addytywnej korekty schematu, ale sam nie uruchamia migracji, backfillu ani
cutoveru.

Obowiązują trzy rozłączne pojęcia:

1. **niezmienny snapshot geometrii źródła** — geometrie wszystkich aktywnych
   slotów konkretnego wystąpienia zdjęcia;
2. **bieżący wybór geometrii planszy** — wskazanie, z którego snapshotu i slotu
   korzysta aktualna logiczna plansza;
3. **proweniencja renderu i decyzji** — dokładny przepis utworzenia cropa oraz
   append-only historia działań człowieka.

Kopia danych służąca projekcji, audytowi albo deterministycznemu replayowi nie
staje się drugim właścicielem semantycznym.

## Mapa odpowiedzialności

| Nośnik | Odpowiedzialność | Klasyfikacja |
|---|---|---|
| `source_images` | Tożsamość wystąpienia źródła w imporcie, oryginalna i zorientowana przestrzeń współrzędnych, wymiary, EXIF i checksumy źródła | źródło prawdy dla wystąpienia i przestrzeni źródłowej |
| `image_source_geometry_revisions` | Niezmienny snapshot topologii, attested range, aktywnych slotów i finalnych quadów wszystkich slotów danej rewizji źródła | kanoniczny właściciel bajtów geometrii wirtualnej |
| `recognized_boards` | Bieżąca plansza dla jednego slotu oraz selektor `source_geometry_revision_id + position_index`; status i rewizja workflow | materializowana projekcja bieżącego wyboru |
| `image_board_geometry_revisions` | Append-only komenda/audyt ręcznej korekty, rewizja planszy i historyczny manifest assetów | historia decyzji; nie właściciel virtual quada |
| `cell_observations` | Niezmienna obserwacja pipeline'u, predykcja oraz dokładny render spec/crop provenance | wynik i proweniencja renderu |
| `image_symbol_review_cells` | Bieżąca decyzja człowieka, jakość i proweniencja zatwierdzonego cropa | projekcja operacyjna review |
| `image_symbol_review_events` | Append-only historia decyzji i zmian cropa | audyt review |
| `image_geometry_rollout_states` | Bieżąca polityka rolloutu gry oraz bounded checkpoint jej walidacji/backfillu | stan operacyjny, nie geometria |
| job input i stage results | Niezmienny snapshot oczekiwań konkretnego wykonania | kontrakt replayu, nie bieżący właściciel |

`image_sequence_canonical` i `image_board_search_fast_documents` nadal wybierają
logicznego właściciela numeru sekwencji. Nie wybierają geometrii wewnątrz
`recognized_board` i nie powinny przechowywać quadów.

## Reguły własności

### Wersjonowana kwalifikacja ręcznej geometrii

Kontrakt `manual-geometry-qualification-v1` jest metadanymi decyzji, nie nowym
algorytmem geometrii. W rewizji źródła właścicielem jest
`board_geometries[position_index].geometryQualification`; przed importem
odpowiada mu append-only `image_page_geometry_overrides.slot_qualifications`
lub decyzja guard. `recognized_boards.geometry_qualification` jest wyłącznie
zgodną projekcją wraz z istniejącymi `completeness_status` i maską.
Nie wolno usunąć kwalifikacji przez zapis historycznego kontraktu.

Migracja 0100 dodaje nullable JSONB bez backfillu dawnych rewizji i rozszerza
ograniczenia maski do 15. SQL NULL pozostaje SQL NULL, nie JSON `null`.
Nowe CHECK constraints są `NOT VALID`: nie skanują danych historycznych przy
wdrożeniu, ale obowiązują dla nowych zapisów. Semantykę nowego payloadu oraz
kompletność listy slotów sprawdza wspólny czysty model domenowy.
Downgrade zatrzymuje się przed utratą dowolnej nowej kwalifikacji albo maski
15/15. Wdrożenie ma limit blokady 5 s i statement timeout 120 s; przekroczenie
kończy migrację rollbackiem, nie oczekiwaniem bez końca.

Brak nowych pól nie zmienia bajtów ani checksum historycznych payloadów.
Nowy payload wchodzi do checksum decyzji i wymaga nowej wersji manifestu guard.
Aktywacja konsumentów oraz wykluczenie kohort/kotwic należą do TASK-0506–0508;
foundation nie może przekazać oznaczeń do starego konsumenta, który je zignoruje.

TASK-0506: kwalifikowana ręczna geometria 3×5 dopuszcza narożniki w zakresie
jednej dodatkowej szerokości/wysokości po każdej stronie źródła. Automaska
korzysta z projekcji właściwych komórek, przed zastosowaniem parametrów cropa;
brakujące indeksy nie tworzą VirtualCell ani pikseli. Maska ręczna może tylko
rozszerzyć automaskę. Tolerancja numeryczna 1e-6 px chroni przed błędami float
na brzegu i dotyczy wyłącznie nowego kontraktu. Stare walidacje i fingerprinty
bez kwalifikacji pozostają niezmienione. UI otoczenie jest transformacją
współrzędnych, nie powiększeniem bitmapy źródła lub renderera.

### Source geometry revision

TASK-0508: migracja 0101 dodaje `image_symbol_review_cells.source_available`
z domyślnym `true`, bez backfillu obrazów. Niedostępne pola zachowują swoje
ID, poprzednią tożsamość cropa i FK audytu; predykaty list/liczników/operacji
oraz kwalifikacji treningu wyłączają je z bieżącej projekcji. Kwalifikowana
rewizja wymaga dokładnego zbioru dostępnych indeksów; 0 obrazów jest poprawne
wyłącznie dla jawnej maski 15/15. Pierwotne observations pozostają niezmienne.

Zapis virtual geometry wspólnie aktualizuje maskę, selektor, dostępne review
cells i fast search document; odrzuca niekompletną synchronizację zamiast
zapisać resolved deferred bez obrazów. Licznik otrzymuje deltę maksymalnie
dziewięciu właścicieli sekwencji. Stan przed pierwszym backfillem powstaje
tylko podczas zapisu jako `rebuilding`; preview czyta istniejącą proweniencję
i nie mutuje bazy. Rozpoznawanie kwalifikowanych pending plansz jest dostępne
przez jawny refresh również po zakończeniu importu.

Kwalifikacja nie zmienia wersji automatycznego detektora. Ręczny override
przenosi pełny source snapshot i maski do nowego importu; signed współrzędne
są sprawdzane względem rzeczywistej kanonicznej orientacji EXIF. Guard v3
i nowe source overrides są obsługiwane przez worker; nie wolno ich zapisać
jako stary kontrakt bez kwalifikacji. Wykluczony slot odrzuca kotwicę całego
źródła; pewne plansze mogą kalibrować niezależnie. Profile, snapshoty starych
jobów i frozen crops nie są przepisywane.

Jedynym właścicielem finalnych quadów geometrii wirtualnej jest
`image_source_geometry_revisions.board_geometries[position_index]`.

Rewizja może i powinna zawierać wszystkie aktywne sloty danego snapshotu.
`active_board_slots`, attested sequence range, wersja reguł i topologia są
niezmiennym kontekstem tego snapshotu. Checksum rewizji obejmuje ten kontekst i
geometrię.

Nie istnieje globalna reguła „jedna bieżąca source revision na zdjęcie”. Ręczna
korekta pojedynczej planszy tworzy nowy kompletny snapshot źródła, lecz każda
plansza może nadal wskazywać inną rewizję. Pozwala to poprawiać sloty niezależnie
bez automatycznej zmiany pozostałych decyzji.

### Bieżąca board geometry revision

Bieżącą geometrię planszy wybiera para:

```text
recognized_boards.source_geometry_revision_id
+ recognized_boards.position_index
```

`recognized_boards.geometry_revision` jest rewizją workflow planszy, a nie
numerem source geometry revision.

Dla geometrii wirtualnej:

- wskazana source revision musi należeć do tego samego `source_image` i gry;
- `position_index` musi należeć do `active_board_slots` i występować w
  `board_geometries`;
- `recognized_boards.board_geometry` jest tylko zgodną checksumowo projekcją
  kompatybilnościową;
- przy ręcznej rewizji najnowszy rekord
  `image_board_geometry_revisions(recognized_board_id, revision)` musi wskazywać
  tę samą source revision i jej checksumę.

Dla historycznej geometrii legacy aktualna `image_board_geometry_revision` i
materializowana `recognized_boards.board_geometry` pozostają niezbędne do
replayu. Nie wolno interpretować ich jako alternatywnego właściciela geometrii
wirtualnej.

### Render provenance

`cell_observations.render_spec` może zawierać wyprowadzony quad, ale jego rolą
jest odtworzenie dokładnych pikseli cropa. Musi wskazywać source geometry
revision, logiczną tożsamość komórki, topologię, padding, interpolację i rozmiar
wyjścia. Nie może samodzielnie zmienić geometrii planszy.

Po TASK-0321 logical cell v2 wiąże komórkę z occurrence źródła, topologią,
slotem i pozycją. Render identity v2 dodatkowo wiąże geometrię i parametry
renderowania. Historyczne identyfikatory v1 pozostają niezmienne.

Bieżący read path mutacji symbolu zawsze zaczyna od selektora planszy i jej
aktualnej rewizji. Dla ręcznej geometrii `virtual_source` materializuje komórki
z kompletnego `virtual_render_spec`; pole `crop_artifacts` pozostaje SQL NULL
zgodnie z kontraktem i jest sprawdzane wyłącznie dla `legacy_file`. Canonical
owner przechowuje checksumę bieżącej geometrii jako tożsamość planszy
wirtualnej. Ścieżka i checksuma managed original służą osobno do wyświetlenia
kontekstu i regeneracji pikseli.

## Active slots i topologia

Źródła prawdy są rozdzielone według czasu życia:

- bieżąca topologia gry: przypięta wersja reguł gry;
- topologia konkretnego wykonania: niezmienny snapshot w job input;
- topologia i aktywne sloty konkretnej geometrii: source geometry revision;
- `recognized_boards.grid_rows/grid_columns`: projekcja kompatybilnościowa;
- liczba rekordów `recognized_boards`: materializacja slotów, nie deklaracja
  aktywnych slotów.

W migracji 0082 attestation opisuje ciągły prefiks 1–9. Obsługa częściowej
strony TASK-0320 wymaga w przyszłości wersjonowanej attestation, ale nie wolno
przepisywać 0082. Do czasu addytywnej korekty importer musi walidować zgodność
job input, source revision i utworzonych plansz.

## Rollout

`image_geometry_rollout_states` pozostaje osobną tabelą. Rollout jest mutable,
operacyjną polityką i checkpointem walidacji, a nie trwałą konfiguracją domenową
gry ani właścicielem geometrii. Każdy job zamraża jego wersję w input.

Snapshot v2 joba `structured_shadow` może dodatkowo zamrozić config kandydata
Structured Geometry v2. Jego wynik `structuredGeometryCandidateV2` jest
wyłącznie checksummowanym pomiarem zapisanym w stage result. Nie jest payloadem
`image_source_geometry_revisions`, nie może zmienić selektora planszy ani
zostać użyty jako proweniencja cropa. Jedyną geometrią shadow pozostaje wynik
Structured OpenCV v1; sidecar v2 deklaruje pochodzenie
`reuse_v1_final_quad_without_authority`.

Przyszły stan `ready` musi być związany z dokładną rewizją polityki, checksumą
wejścia walidacji i jobem walidującym. Zmiana polityki unieważnia gotowość
poprzedniego snapshotu, ale nie zmienia historycznych jobów ani source geometry
revisions.

## Macierz ścieżek zapisu

| Ścieżka | Zapis kanoniczny | Projekcje i audyt |
|---|---|---|
| automatyczna geometria structured | nowa `image_source_geometry_revision` ze wszystkimi aktywnymi slotami | `recognized_boards` wskazują właściwe sloty; obserwacje zapisują render provenance |
| ręczna korekta virtual | nowa pełna source revision z podmienionym jednym slotem | tylko poprawiana plansza zmienia selektor; powstaje board geometry event/revision i nowe obserwacje |
| ręczna korekta wszystkich slotów virtual | jedna nowa pełna source revision ze wszystkimi quadami wyznaczonymi przez operatora w kolejności row-major | wszystkie aktywne plansze aktualizują selektor, obserwacje i audyt w jednej transakcji albo żadna |
| ręczna korekta legacy | historyczna board geometry revision i jej assety | `recognized_boards` materializuje bieżący stan; brak fałszywej source revision virtual |
| preview | brak trwałego właściciela | wynik efemeryczny związany z oczekiwanym źródłem, rewizją i topologią |
| trening | brak zmiany geometrii | manifest kohorty wskazuje zatwierdzoną rewizję i checksumy cropów |
| decyzja `partial` bramki importu | source revision zachowuje quad slotu i maskę niedostępnych pól | renderer i observations obejmują tylko dostępne logiczne indeksy; brak kanonicznego layoutu |
| decyzja `rejected` bramki importu | brak właściciela geometrii planszy w projekcji importu | audyt pozostaje w append-only decyzji i zamkniętym manifeście; brak recognized board oraz cropów |
| opt-in do uczenia niepełnych siatek | najnowsza `image_page_geometry_overrides.slot_qualifications` z kwalifikacją v2 | profil jest deterministyczną pochodną bieżących rewizji; nie powstaje drugi mutable owner ani wpis w zwykłej kohorcie geometrii |

Każdy zapis planszy blokuje i waliduje w kolejności: gra, wystąpienie źródła,
sekwencja, review item/plansza, komórki. Zmiana jednej planszy jest atomowa dla
jej selektora, obserwacji, review, canonical i projekcji wyszukiwania.

Osobny profil niepełnych siatek jest snapshotem joba, a nie aktywnym modelem
gry. Buduje się go z najnowszych page override'ów oznaczonych
`includeInPartialGridTraining=true`, grupuje boczne maski pełnych kolumn i
wiąże payload checksumą. Preflight przypina cały profil, a import i retry
odczytują dokładnie ten snapshot. Zapis kolejnej ręcznej rewizji może zmienić
dopiero nowy preflight; nie zmienia już uruchomionego ani historycznego joba.

## Odpowiedzi na pytania schema ownership

1. **Która tabela posiada finalny quad?**
   `image_source_geometry_revisions.board_geometries` dla virtual geometry.
2. **Czy source revision może zawierać wszystkie quady źródła?**
   Tak; jest kompletnym, niezmiennym snapshotem wszystkich aktywnych slotów.
3. **Za co odpowiada board geometry revision?**
   Za append-only komendę człowieka, rewizję workflow, audyt i legacy asset
   manifest; virtual quad wybiera przez FK do source revision.
4. **Czy `recognized_boards` kopiuje czy wskazuje geometrię?**
   Wskazuje przez source revision i slot. `board_geometry` jest walidowaną kopią
   kompatybilnościową, nie właścicielem.
5. **Czy `cell_observations` przechowuje geometrię pochodną?**
   Może utrwalać pochodny render spec do replayu cropa, ale nie może być źródłem
   wyboru geometrii planszy.
6. **Czy rollout ma pozostać osobną tabelą?**
   Tak, ponieważ jest stanem operacyjnym, wersjonowanym i mutowalnym.
7. **Czy rollout należy do konfiguracji gry?**
   Gra wskazuje scope polityki, lecz same tryby i checkpointy nie wchodzą do
   podstawowego rekordu gry. Job przechowuje ich immutable snapshot.
8. **Gdzie są aktywne sloty?**
   Kanonicznie w source geometry revision; job input przechowuje oczekiwany
   snapshot, a plansze materializują pojedyncze sloty.
9. **Czy sloty/topologia są duplikowane?**
   Są snapshotowane w kilku cyklach życia. Duplikaty są dozwolone tylko jako
   jawne projekcje i muszą przechodzić walidację zgodności/checksumy.
10. **Które legacy tabele przestaną otrzymywać nowe dane po cutoverze?**
    Virtual write paths przestaną tworzyć board/cell bitmapy i page overrides.
    `recognized_boards`, board revisions i observations nadal dostają rekordy
    metadanych/proweniencji; ich historyczne rekordy nie są usuwane.
11. **Które tabele można później połączyć?**
    Żadnej z trzech głównych osi: observation, current review i audit. Ewentualne
    usunięcie projekcji jest możliwe dopiero po udowodnionym braku konsumentów.
12. **Jak unikamy wielu właścicieli?**
    Każde pole ma rolę owner/projection/audit, write path zapisuje ownera przed
    projekcjami, a read path virtual zawsze zaczyna od source revision + slotu.

## Addytywna korekta schematu — następny task

Korekta musi powstać jako nowa migracja po 0082 i 0083. Nie wolno edytować
zastosowanych migracji. Minimalny projekt obejmuje:

1. source geometry revision:
   - `topology_fingerprint_sha256`,
   - wersję i checksumę attestation sekwencji/aktywnych slotów;
2. trwałość logical-cell-v2 i render identity v2 obok v1 w observation, current
   review, eventach oraz manifestach kohort;
3. addytywną trwałość `symbol-verification-outcome-v2`, bez heurystycznego
   mapowania niejednoznacznej historii;
4. związanie rollout readiness z rewizją polityki, checksumą wejścia i jobem;
5. constraints lub walidację repozytorium gwarantującą zgodność source/game,
   obecność slotu, checksumę projekcji, board revision i cell provenance.

Nie rekomenduje się teraz normalizacji `board_geometries` do osobnej tabeli
slotów. JSON snapshot wraz z selektorem planszy zachowuje atomowość kompletnej
rewizji i odpowiada bieżącym odczytom. Osobna tabela wymagałaby dowodu w planie
zapytań lub constraintu, którego nie da się osiągnąć obecnym modelem.

Backfill ma być bounded i resumowalny. Najpierw obejmuje aktualnych właścicieli,
pending review i zweryfikowane cropy; nie renderuje całej historii i nie zmienia
etykiet człowieka. Niejednoznaczne rekordy trafiają do raportu i blokują cutover
odpowiedniego scope'u.

## Cutover, rollback i kryteria następnego checkpointu

Przed przełączeniem odczytu na nowe pola wymagane są:

- dual write v1/v2 i raport zgodności;
- 100% aktualnych virtual boards z prawidłowym source revision i slotem;
- zgodność projekcji `recognized_boards.board_geometry` z właścicielem;
- zgodność board revision oraz wszystkich aktualnych observations/cells;
- brak automatycznej naprawy niejednoznacznych wyników symboli;
- odtwarzalny legacy replay.

Rollback wyłącza dual read/write nowych pól, ale zachowuje kolumny i dane.
Historyczne 0082/0083, source revisions, etykiety i eventy pozostają
niezmienione. Fizyczne usuwanie kopii kompatybilnościowych wymaga osobnego,
destrukcyjnego checkpointu po pełnym cutoverze.

## Otwarte ryzyka

- niezależne korekty slotów tworzą wiele kompletnych source revisions; cleanup
  nie może uznać starszej rewizji za osieroconą, jeśli wskazuje ją choć jedna
  bieżąca plansza albo audyt;
- prefixowa attestation 0082 nie opisuje wszystkich częściowych końcówek;
- readiness rolloutu bez związania z checksumą wejścia może stać się nieaktualne;
- projekcja `board_geometry` może się rozjechać, dopóki zgodność jest tylko
  aplikacyjną walidacją;
- wynik feasibility TASK-0323 nie autoryzuje zmiany produkcyjnych progów ani
  rolloutu i pozostaje niezależny od niniejszej decyzji schematu.

## Addytywna trwałość po TASK-0325

Migracja 0084 utrwala kontrakty v2 obok pól historycznych. Nowe source geometry
revisions zapisują `topology_fingerprint_sha256` oraz wersję i checksumę
attestation. Virtual observations, current review, eventy i zamrożone komórki
kohort otrzymały nullable logical/render identity v2. Brak wartości nadal
oznacza rekord historyczny oczekujący na późniejszy bounded backfill, a nie
błędną próbę automatycznego naprawienia historii.

Outcome v2 zapisuje realny symbol w `verified_symbol_id_v2`. Nie korzysta do
tego celu z legacy `assigned_symbol_id`, ponieważ pending rekord może tam
przechowywać sugestię modelu. Dzięki temu `requires_review` nie staje się
fałszywie zatwierdzonym symbolem, a kontrakt HTTP v1 pozostaje bez zmiany.

`image_geometry_rollout_states` wiąże walidację z
`validation_rollout_revision`, SHA-256 pełnego inputu i `validation_job_id`.
Stan nie może przejść do `ready`, gdy job albo polityka różnią się od
zamrożonego snapshotu. TASK-0325 nie przełącza read pathów i nie wykonuje
backfillu; diagnostyka jest limitowana i read-only.

## Bounded backfill po TASK-0326

Istniejący general-lane job `image_geometry_rollout_backfill` wykonuje teraz
addytywny backfill kontraktów v2 razem z walidacją rolloutu. Przetwarza najwyżej
100 source images w jednej transakcji i zachowuje trwały kursor source-level.
Checkpoint raportuje osobno source revisions, observations, current review
cells oraz zamrożone verified training cells.

Backfill nie dekoduje ani nie renderuje obrazów. `logical-cell-v2` i
`render-identity-v2` są wyprowadzane z checksummed legacy render specu oraz
niezmiennego occurrence/topology context. Istniejąca wartość musi dokładnie
odpowiadać wyliczeniu; konflikt kończy scope fail-closed. Source revisions
otrzymują dokładny fingerprint topologii oraz wersjonowaną checksumę
attestation.

Outcome v2 jest uzupełniany wyłącznie w bieżącej projekcji aktualnego
właściciela logicznej planszy. Modelowa sugestia pozostaje
`requires_review`; nie staje się verified symbolem. Niejednoznaczny legacy
stan pozostaje nullable, przerywa partię i blokuje `ready`. Zamrożone komórki
verified cohorts zachowują swój historyczny board/geometry context, nawet gdy
nie są już bieżącym właścicielem sekwencji. Append-only eventy pozostają
niezmienione.

Finalizacja sprawdza ponownie nowe źródła oraz wszystkie brakujące pola v2.
Nowy zapis, który pojawił się po przejściu kursora, uniemożliwia `ready` i jest
obsługiwany w następnym idempotentnym przebiegu. TASK-0326 nadal nie przełącza
publicznych read pathów ani indeksów na v2 i nie wykonuje backfillu na danych
użytkownika.
