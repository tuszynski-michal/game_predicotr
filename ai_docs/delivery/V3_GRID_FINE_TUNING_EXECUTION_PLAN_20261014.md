---
title: Doszkalanie siatek V3 z korekt w aplikacji
status: proposed
last_updated: 2026-10-14
revision: 2
---

# Doszkalanie siatek V3 z korekt w aplikacji

## Cel i status

Operator poprawia siatki w Reviewerze, przygotowuje dane, doszkala model,
porównuje wynik, aktywuje wybraną wersję i ponownie rozpoznaje pozostałe
siatki z poziomu wybranej gry. Nie musi używać skryptów laboratorium ani
przenosić ręcznie plików. Edytor udostępnia cztery rogi oraz opcjonalną
edycję wszystkich 24 punktów siatki 5 × 3.

Plan jest propozycją, nie zgodą na implementację, trening, migrację bazy
operatora, aktywację ani masową zmianę danych. Polecenie operatora obejmuje
usunięcie starego bloku „Ulepszanie geometrii / Cięcie siatki” w ramach tego
planu. Doprecyzowanie z 2026-10-14: sekcja jest dostępna w każdej grze,
ale historyczna gra „777” (kod `7`) pozostaje archiwalna. Nie przełączamy
jej na V3 i nie przetwarzamy ponownie jej zakończonych danych.

Rewizja 2 uwzględnia raport
`quality/V3_GRID_FINE_TUNING_PLAN_REVIEW_CLAUDE_20261014.md` (REVISE).
Raport pierwszej wersji pozostaje bez zmian. Ścieżka tworzenia nowych gier
oraz osobny odbiór zakresu ponownego rozpoznania są teraz pełnymi taskami.
Operator wybrał wykonawcę Codex i audytora Claude Code. Wskazał też kierunek
wspólnego modelu geometrii Mumii i 777, zamiast automatycznego zakładania
oddzielnej rodziny dla każdej nowej gry. TASK-1006 sprawdza taki model przed
publikacją; rozpoczęcie implementacji i koszt nadal wymagają akceptacji planu.

## Stan obecny i potwierdzone miejsca zmiany

| Obszar | Istniejący plik i symbol | Wniosek |
| --- | --- | --- |
| Stary panel | `apps/admin/src/features/model-quality/model-quality-workspace.tsx::ModelQualityWorkspace`, okolice 878–906; `grid-quality-panel.tsx::GridQualityPanel` | „Cięcie siatki” korzysta z klasycznej kalibracji, a nie z doszkalania sieci V3. |
| Nawigacja gry | `apps/admin/src/features/catalog/catalog-workspace.tsx::CatalogWorkspace`; `admin-navigation-state.ts::GAME_SECTIONS` | Panel jakości i wejście do korekty są już osadzone w zakresie wybranej gry. Stała nawigacji jest w osobnym module. |
| Nowa gra | API `domain/catalog.py::GameShapeGeometryConfiguration`, `schemas/catalog.py::GameCreate`, `application/catalog.py`; Admin `features/games/game-catalog.tsx`, `game-catalog-state.ts`, `game-catalog-actions.ts` | Zamknięty enum wybiera obecnie także profil. Formularz nie potrafi wybrać konkretnej opublikowanej wersji ani utworzyć własnej rodziny od wersji bazowej. |
| Edytor planszy | `apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx::BoardGeometryCorrectionEditor`, także `DeferredBoardCellGeometryEditor` | Dokładna siatka 24 punktów oraz cztery rogi już istnieją. Obecna akcja zamiany na szkic usuwa dokładne węzły i zaokrągla obrys; trzeba ją zastąpić. |
| Stan geometrii | `board-lattice-state.ts::parseBoardLattice`, `boardLatticeCorners`; `board-lattice-draft-storage.ts::BoardLatticeDraft` w tym samym katalogu | Zachowane są dokładne punkty, walidacja 15 komórek i lokalny szkic. |
| Eksport korekt | `scripts/vision_lab_geometry_export.py::_exact_lattice`, `_build_row`; `vision_lab/production_geometry.py::derive_consistent_lattice_nodes` | Eksporter potrafi odczytać zatwierdzone 24 punkty, lecz wybiera tylko zdjęcia `geometry_complete`. |
| Model | `services/worker/src/game_predictor_worker/vision_lab/neural_grid_model.py`; `neural_grid_training.py::compute_losses`, `train_run` | Sieć ma etap wykrywania plansz na zdjęciu i etap 24 węzłów na cropie planszy. Obecne straty zakładają kompletną anotację wejścia. |
| Trwały trening | `vision_lab/neural_grid_finetune.py::train_iteration`, `export_iteration`; `vision_lab/production_snapshot.py::build_snapshot`; `training_core/` | Istnieją checkpointy, niezmienne wejścia i eksport ONNX. Orkiestracja fine-tune jest specyficzna dla Mumii i wymaga adaptera produkcyjnego. |
| Wybór wag | `services/api/src/game_predictor_api/domain/grid_engine_profiles.py`; `storage/grid_profile_snapshot_resolver.py::resolve_neural_grid_proposal`; `domain/neural_grid_proposal.py::NeuralGridSnapshot` | Profile 777 v2 i Mumii wskazują zamrożone pakiety. Nie ma jeszcze dynamicznego rejestru wersji V3 z aktywacją per gra. |
| Bezpieczny zapis | `application/image_grid_reviews.py::ImageGridReviewService`; rewizje i zdarzenia geometrii w `storage/models.py`; `geometry_core/` | Korekta, rendering, ochrona sekwencji i historia mają już właścicieli. Nowy przebieg musi użyć tych samych reguł. |

Ścieżki `vision_lab/`, `training_core/` i `geometry_core/` w tabeli są
względem `services/worker/src/game_predictor_worker/`. Pozycje w dalszych
sekcjach oznaczone „nowe” są proponowane, nie istnieją w chwili planowania.

Źródła: D-522–D-527, D-541, D-544; wymagania `ADMIN_APP.md`,
`SUPERVISED_MODEL_IMPROVEMENT.md`, `IMAGE_INGESTION.md`, `VISION_LAB.md`;
architektura `SUPERVISED_MODEL_IMPROVEMENT.md`, `VISION_LAB.md`;
`APP_V3_FUNCTIONAL_INVENTORY.md`, MODEL-06, MODEL-07, MODEL-09 i MODEL-10.
TASK-0802 opisuje historyczny trening modelu bazowego; ten plan nie wznawia
jego budżetu ani nie zmienia jego wyników. TASK-0991 jest osobną operacją
rozpoznawania symboli; nie jest częścią tego zakresu.

### Stan danych operatora i artefaktów bazowych

Poniższe liczby pochodzą z odczytu bazy tylko do odczytu wykonanego przez
audytora Claude 2026-10-14. Nie są gwarancją bieżącego stanu przy wdrożeniu;
preview ma pobrać je ponownie w prawidłowym zakresie gry/RLS.

| Gra | Plansze | Geometrie zatwierdzone ręcznie | Zdjęcia `geometry_complete` | Zdjęcia `geometry_incomplete` |
| --- | --- | --- | --- | --- |
|777a2|341 564|0|0|37 990 z 37 993|
|Mumie|492 215|44|4|54 790|

W 777a2 wszystkie plansze mają `completeness_status=complete`, natomiast
odroczona kolejka ma 373 wiersze. Nie znamy jeszcze pełnego rozkładu pozycji
`ok/uncertain/missing/partial/deferred/superseded`; liczniki te ma zbudować
TASK-0999. Z `geometry_incomplete` nie wolno wyprowadzić liczby błędnych
siatek ani zakresu recropu. Aktualna kohorta ręcznych korekt 777a2 jest pusta.

Pierwszy run 777a2 po zgromadzeniu minimalnych korekt będzie **grid-only**,
dopóki nie ma pełnych ręcznych anotacji zdjęć. Cztery kompletne zdjęcia Mumii
nie dowodzą jeszcze minimalnego pokrycia ani niezależności nagrań.

Bazowy checkpoint 777 v2 zweryfikowany w odczycie plików jest pod
`C:/Users/tuszy/Documents/game_predictor_vision_data/neural-grid-runs/43933ac8d7d443c8b9079630a83de2e6/attempt-1/2cd19738367121e6a36cf0630b4fd7d275d1966fbe25ca73d1329fa979183fe8.pt`:
106 729 511 B, SHA-256
`2cd19738367121e6a36cf0630b4fd7d275d1966fbe25ca73d1329fa979183fe8`.
Eksport `exports/2cd19738367121e6-round3/bundle.json` ma SHA
`64d815d8af168f79fd53f0dcb9e80823c3006ebae3e08225fc9e25f178c27b7b`.
Pakiet produkcyjny na D zawiera ONNX i manifest, lecz nie ten checkpoint.
TASK-0994 kopiuje potrzebne checkpointy/manifesty na D z kontrolą hashów;
nie kopiuje automatycznie całych około 7 GB runów i snapshotów. Analogicznie
weryfikuje bazę Mumii. `VISION_LAB_DATA_ROOT` jest konfiguracją laboratorium,
a nie źródłem ścieżek produkcyjnego trenera.

## Docelowy przebieg operatora

Nowa sekcja gry nazywa się **Doszkalanie siatek V3**. Pokazuje bieżący model,
nowe korekty od poprzedniego snapshotu, kwalifikowane i wykluczone plansze,
pochodzenie zdjęć, niezależne dane oceny, stan zadania i historię wersji.

0. **Przygotuj przykłady** pokazuje brakujące liczby plansz, zdjęć i nagrań.
   Minimalny pierwszy run opisano poniżej: 30 plansz TRAIN, 15 VALIDATION,
   15 REGRESSION z niezależnych grup. Kontrolne pule bazowe mogą zmniejszyć
   liczbę nowych korekt dopiero po potwierdzeniu zgodności i proweniencji.
   Bez pełnych anotacji zdjęć uczymy tylko położenie węzłów, nie odzysk
   niewykrytych plansz.
1. **Popraw siatki** otwiera istniejący Reviewer z wybraną grą.
2. **Przygotuj dane** pokazuje podgląd kwalifikacji i zamraża snapshot po
   potwierdzeniu. Wyjaśnia braki, bez uruchamiania treningu przy wejściu.
3. **Doszkol model** uruchamia jeden ograniczony run od przypiętej wersji.
   Operator widzi postęp, limit czasu, błąd, anulowanie i wznowienie.
4. **Porównaj wynik** pokazuje te same kontrolne zdjęcia dla wersji bieżącej
   i kandydata, metryki i konkretne pogorszenia.
5. **Aktywuj w tej grze** zmienia tylko jej przypisanie wersji. Odrębna
   publikacja udostępnia ocenioną wersję zgodnym grom. Powrót do wcześniejszej
   wersji jest osobną akcją z historią.
6. **Rozpoznaj ponownie pozostałe siatki** pokazuje rozkład stanów pozycji,
   zakres, możliwe zmiany cropów i pominięcia. Domyślne filtry to
   `uncertain` i `deferred`, z ograniczoną pierwszą próbą do 100 zdjęć;
   szeroki zakres oraz „wszystkie automatyczne” wymagają jawnego wyboru,
   następnie uruchamia trwałe zadanie na oryginalnych zdjęciach. Wynik
   raportuje poprawione automatycznie, nadal wymagające korekty, chronione
   i zmienione w czasie przebiegu.

W każdej grze widoczność sekcji wynika z nawigacji, a możliwość działania
z kontraktu backendu, nie z nazwy gry. Obecne modele V3 obsługują 5 × 3.
Dla innej topologii sekcja podaje brak zgodnego modelu i wyłącza działania;
nie dopełnia planszy do 15 pól. Implementacja nowej sieci 3 × 3/16 węzłów
nie jest częścią tego planu. Historyczna 777 pokazuje status archiwalny.

Stary blok jest usunięty globalnie ze wspólnego komponentu. „Ulepsz
rozpoznawanie” dla symboli, korekta siatek, diagnostyka i ich historia
pozostają. Usunięcie UI nie usuwa klasycznych profili, tabel, endpointów ani
artefaktów potrzebnych do odtworzenia zakończonych importów.
Archiwalna 777 zachowuje w nowej sekcji jedynie odczyt nazwy aktywnego
klasycznego profilu oraz historii przypisań. Nie pozostawiamy przycisków
treningu, aktywacji, cofania lub ponownego przetwarzania klasycznej geometrii.

### Nowa gra bez własnych korekt

Formularz tworzenia gry wybiera format strony/topologię osobno od modelu.
Katalog backendu pokazuje wyłącznie opublikowane kompatybilne wersje:
rodzinę, wersję, pochodzenie, wyniki oceny, obsługiwaną topologię i kontrakt
wejścia. Nowe pole `gridModelVersionId` zastępuje używanie enumu profilu
do wyboru wag. Enum `shapeGeometryConfiguration` pozostaje opisem formatu
strony oraz zgodnym odczytem danych historycznych; nowe wartości enumu
nie powstają dla kolejnych modeli.

Opcjonalna akcja **Utwórz własną rodzinę z tej wersji** tworzy rodzinę,
jej wersję początkową oraz grę/przypisanie w jednej idempotentnej transakcji.
Wersja początkowa wskazuje te same niezmienne pliki i parentVersionId,
bez kopiowania wag lub etykiet gry bazowej. Gang może zacząć od modelu 777 v2,
gdy kontrakt geometryczny jest zgodny. Domyślny kierunek to dołączenie do
zgodnej rodziny, docelowo wspólnej rodziny geometrii z TASK-1006. Nowa rodzina
jest opcją izolacji, nie obowiązkiem dla nowej nazwy gry. Operator widzi
docelową pulę korekt przed zapisem. Nie zmienia to istniejących przypisań
777a2 ani Mumii; przełączenie jest zawsze osobną aktywacją.

Nowa rodzina dziedziczy wyłączenia źródeł kontrolnych i aliasów całej linii
wersji bazowych. Fork nie pozwala wykorzystać w TRAIN holdoutu rodzica.
Wyniki Reels 29/30 i Treasure 30/30 przy bazie 777 v2 opisują historyczną ocenę,
nie stanowią dowodu zgodności każdej nowej gry ani zgody na użycie tych
holdoutów jako danych treningowych lub wielokrotnej walidacji.
Bez własnych korekt gra może importować z przypiętą bazą, ale przycisk
doszkalania pokazuje `GRID_TRAINING_COVERAGE_INSUFFICIENT`.

Migracja wypełnia jawne przypisania istniejących gier z dwóch dotychczasowych
profili, z kontrolą wersji i hashów. Nie przełącza archiwalnej 777 na V3.
Testy creation/update obejmują pełny pion API/OpenAPI/klient/formularz.

### Wspólny model geometrii Mumii i 777

Oba istniejące modele przewidują siatkę 5 × 3 i mają wspólne pochodzenie
architektury; fine-tune Mumii korzystał również z danych 777. Różne ramki
nie przesądzają o konieczności oddzielnych wag. Sprawdzamy możliwość jednego
modelu geometrii, niezależnie od osobnych modeli symboli i zasad wypłat.

TASK-1006 tworzy nową rodzinę wspólnej geometrii i jednego kandydata od
zweryfikowanego bazowego checkpointu, a nie średnią wag dwóch modeli.
Zgodność preprocessing/topologii obu pakietów jest warunkiem startu.
Bazę777 i bazę Mumie porównuje się na zamrożonej VALIDATION obu gier,
a wybór jednej bazy/presetu zostaje zapisany przed treningiem. Korekty TRAIN
obu gier są próbkowane z równą wagą gry, potem równą wagą nagrania i planszy;
duża kolekcja 777 nie może zagłuszyć Mumii. Samo powielenie etykiety nie
zwiększa liczby przykładów ani pokrycia.

Candidate wspólny musi przejść bramkę osobno dla 777 i Mumii względem ich
bieżących modeli, na tych samych niezależnych danych każdej gry. Wymagana
jest poprawa przynajmniej jednej miary walidacyjnej i brak regresji w każdej
grze; średnia łączna nie maskuje pogorszenia jednej z nich. Gdy nie przejdzie,
aplikacja zachowuje dwa dotychczasowe modele i przedstawia wynik próby,
zamiast wymuszać połączenie. Nowe gry wybierają zgodną opublikowaną wersję;
brak etykiet nowej gry oznacza „jakość niezmierzona dla tej gry”, nie PASS.

Rodzina wspólna dziedziczy wszystkie wyłączenia i role kontrolne obu linii
bazowych, także po aliasie między grami/rodzinami. Akceptacja planu wymaga
zapisania decyzji rozszerzającej rozdział rodzin geometrii z D-527; modele
symboli pozostają poza tym połączeniem. Historyczna777 pozostaje archiwalna.

## Reguły edytora czterech rogów i 24 punktów

- Domyślny tryb interakcji: **4 rogi**. Przełącznik **Dokładna korekta —
  24 punkty** zmienia uchwyty, a nie zapisane współrzędne.
- Wczytanie zapisanej lub proponowanej siatki zachowuje wszystkie 24 punkty
  z pełną precyzją. Samo przełączenie trybu niczego nie przebudowuje.
- Przeciągnięcie całej siatki przesuwa wszystkie punkty o ten sam wektor.
  Zmiana rogu stosuje homografię między starym i nowym obrysem do wszystkich
  24 punktów, zachowując wcześniejsze lokalne odchylenia. Aktualizacja tylko
  czterech węzłów przy nieruchomych pozostałych jest niedopuszczalna.
- **Wyznacz od nowa z 4 rogów** pozwala wskazać kolejno TL, TR, BR, BL
  zewnętrznych granic symboli i generuje regularną siatkę projekcyjną.
  Jest świadomym resetem lokalnego kształtu z możliwością cofnięcia w szkicu.
  Nie należy wskazywać zewnętrznej czerwonej ramki maszyny.
- W trybie dokładnym można przesuwać każdy punkt niezależnie. Powrót do
  4 rogów zachowuje te poprawki. Przywrócenie sugestii pozostaje osobną akcją.
- Każdy ruch waliduje obrys i wszystkie komórki: brak przecięcia,
  odwrócenia, degeneracji i liczb niefinitywnych. Niepoprawny ruch nie
  zastępuje ostatniej poprawnej geometrii ani nie umożliwia zapisu.
- Zapis dla V3 zawsze przekazuje dokładne 24 punkty wraz z istniejącymi
  tokenami rewizji, kwalifikacją, bindingiem propozycji i checksumami.
  Podgląd 15 cropów musi odpowiadać dokładnie bieżącej geometrii.
- Szkic utrwala tryb i dokładną geometrię. Stare szkice mają domyślny tryb
  4 rogów, lecz nie tracą węzłów. Zmiana źródła/rewizji unieważnia szkic
  zgodnie z istniejącym bindingiem. Dotyk, zoom i przeciąganie zachowują
  obecny workflow kwalifikacji planszy częściowej.

## Dane uczące i niezależna ocena

Źródłem etykiety jest aktualna zatwierdzona przez człowieka geometria
konkretnej planszy, związana z grą, zdjęciem, sekwencją, rewizją i renderem.
Predykcje, stara rewizja po cofnięciu korekty i samo kliknięcie „Zła siatka”
nie są etykietami. Kohorta jest kumulatywna; „nowe korekty” to informacja
o różnicy względem poprzedniej kohorty, nie nakaz trenowania tylko na różnicy.

### Korekta jednej planszy na niekompletnym zdjęciu

Nowy adapter kwalifikuje pojedyncze pełne, zatwierdzone plansze niezależnie
od stanu pozostałych slotów zdjęcia. Nie zmienia bramki operacyjnej zdjęcia.
Snapshot rozdziela dwa rodzaje nadzoru:

| Rodzaj próbki | Etap treningu | Ochrona przed fałszywą etykietą |
| --- | --- | --- |
| Pełna zatwierdzona plansza, inne sloty nieznane | Etap węzłów na cropie tej planszy | Pozostałe plansze nie są przykładami braku detekcji. Straty i stan etapu ekranu są zamrożone, także BatchNorm. |
| Zdjęcie z zatwierdzonym kompletnym zestawem oczekiwanych plansz | Etap ekranu oraz etap węzłów | Liczba i pozycje muszą być jednoznacznie powiązane z sekwencją; żaden slot nie jest dorabiany. |
| Plansza częściowa, odrzucona lub bez aktualnego approval | Wykluczona z pierwszej wersji treningu | UI pokazuje konkretny powód; ekstrapolowane niewidoczne węzły nie są pełnymi targetami. |

Przy braku kompletnej anotacji zdjęć można doszkolić sam etap węzłów. Panel
wyraźnie informuje, że taki run nie uczy odzyskiwania niewykrytych plansz.
Odzysk brakujących plansz wymaga próbek pełnych zdjęć i treningu etapu
ekranu. Nie wymuszamy ręcznej korekty całej kolekcji, żeby poprawić przesunięcia.

### Tożsamość, podział i zamrożenie

Proponowany minimalny próg dopuszczenia pierwszego runu, wymagający
zatwierdzenia przy akceptacji planu:

| Rola | Pełne ręcznie zatwierdzone plansze | Różne zdjęcia | Niezależne nagrania |
| --- | --- | --- | --- |
|TRAIN|30|10|co najmniej 1|
|VALIDATION|15|5|co najmniej 1, rozłączne z TRAIN|
|REGRESSION|15|5|co najmniej 1, rozłączne z TRAIN i VALIDATION|

W obu rolach kontrolnych wymagamy również pięciu w pełni anotowanych
zdjęć, aby mierzyć kompletność D-483, także przy treningu grid-only. Limit
15 plansz jest dolną granicą; dla zdjęć z 9 planszami daje to faktycznie
45 plansz VALIDATION i 45 REGRESSION. Z 30 planszami TRAIN operator przygotowuje
co najmniej 120 plansz na 20 zdjęciach z trzech niezależnych nagrań, jeżeli
wszystkie pule buduje od początku. To próg technicznego pilota,
nie statystyczna gwarancja poprawy kolekcji. Gdy kompatybilne kontrolne
pule już istnieją i mają dowód niezależności, operator poprawia przynajmniej
30 plansz TRAIN z 10 zdjęć, a wymagania obu ról kontrolnych nie maleją.
Nie wolno przenosić chronionych zestawów final_test/unseen_game do walidacji.

Preview zwraca `required/eligible/missing` dla plansz, zdjęć i nagrań każdej
roli oraz przyczyny wykluczeń. TRAIN bez VALIDATION/REGRESSION nie uruchamia
runu. Dla treningu etapu ekranu dodatkowe minimum to 10 kompletnych zdjęć
TRAIN i 5 kompletnych zdjęć dla każdej roli kontrolnej, z etykietą każdego
oczekiwanego slotu. Brak tego pokrycia nie blokuje prawidłowego grid-only,
lecz wyłącza etap ekranu i pełną metrykę detekcji dla nowych źródeł.

- Deduplikacja: SHA pliku oraz SHA zorientowanych pikseli, identyfikator
  źródła i grupa nagrania. Aliasy w różnych grach tej samej rodziny należą
  do tej samej partycji. Obecne rodziny pozostają oddzielne do zatwierdzenia
  wspólnego kandydata TASK-1006; jego wyłączenia obejmują obie linie bazowe.
- Nowe pojęcie **nagranie źródłowe** ma trwały identyfikator w bazie.
  Operator przypisuje istniejące importy/zdjęcia do nagrania w panelu.
  Nazwa katalogu jest propozycją powiązania, nie dowodem niezależnego filmu.
  Nieznane grupy nie kwalifikują się jako niezależna ocena.
- Podział całymi nagraniami na TRAIN, VALIDATION i REGRESSION jest trwały
  dla rodziny. Źródło i alias raz kontrolne nie przechodzą później do TRAIN.
  Nowe korekty kontrolnego źródła aktualizują przyszłą ocenę, a nie trening.
- Niezależna kontrola nie może pochodzić z nagrania użytego w TRAIN
  którejkolwiek wersji bazowej, także gdy nowy run nie czyta już jej dawnych
  targetów. Rejestracja bazy zachowuje manifesty ról i inventory źródeł
  z całej linii checkpointów. Preview wyklucza `seen_by_base_training`;
  brak udowodnionej tożsamości nagrania daje brak niezależności, nie PASS.
  Dawny foto-disjoint holdout Mumii nie staje się przez samą nazwę
  niezależnym filmem w nowej policy.
- Pierwszy rozdział wybiera deterministycznie TRAIN/VALIDATION według
  zamrożonego seedu, z docelowym udziałem 80/20 całych grup. REGRESSION jest
  osobną, jawnie przypiętą pulą kontrolną modelu bazowego albo nową grupą
  operatora. Każda rola musi zawierać dane; brak niezależnych grup daje
  `GRID_TRAINING_COVERAGE_INSUFFICIENT` przed runem. Nie dzielimy sąsiednich
  klatek tego samego filmu między uczenie i kontrolę.
- Można użyć istniejącej kompatybilnej puli kontrolnej rodziny po sprawdzeniu
  jej pochodzenia, praw i wyłączeń. Nie używamy automatycznie historycznego
  GOLD/test ani nie odblokowujemy holdoutów Reels/Treasure D-456.
- Kohorta zamraża źródła, targety, role, dostępność anotacji ekranu, 24 punkty,
  revisions, approval events, preprocessing, model bazowy i policy version.
  Zatwierdzenia są weryfikowane przed publikacją snapshotu. Dane po freeze
  nie są odczytywane jako nowsze etykiety tego samego runu.
- Snapshot przechowuje pliki na dysku z checksumami i atomowym publish.
  Obejmuje niezmienne kopie używanych obrazów, adresowane treścią i sprawdzone
  po skopiowaniu; nie zależy od późniejszej dostępności aktywnej tabeli źródeł.
  Baza zawiera metadane, ścieżki i hashe. Utrata odpowiedzi zwraca tę samą
  kohortę/run po powtórzeniu operationId, a nie kolejną kopię.
- Cofnięcie/usunięcie etykiety po freeze nie zmienia historycznego snapshotu;
  zaznacza jego dowód jako wycofany. Taki kandydat wymaga nowej kwalifikacji
  przed aktywacją, zamiast wykorzystać zakwestionowaną etykietę po cichu.

Nowy feedback policy dopuszcza ręczne korekty G do TRAIN, jeśli mają rolę
TRAIN. Jest to proponowane rozszerzenie ograniczenia D-480 dla historycznego
snapshotu. Przy akceptacji planu trzeba zapisać nową decyzję; historyczne
snapshoty i role G nie zostają przeklasyfikowane.

## Rejestr modeli, zadania i kontrakt API

### Właściciele i schemat

Backend utrzymuje jeden rejestr modeli siatek: rodzina, niezmienna wersja
i przypisanie wersji do gry. Adaptujemy istniejący resolver profili i format
pakietu `GridEngineModelVersion`; nie umieszczamy wag w klasycznych tabelach
`GridCalibrationProfileModel` ani w rejestrze klasyfikatorów symboli.

Proponowane nowe encje, nazwy do utrzymania w taskach implementacyjnych:

- `grid_model_families`, `grid_model_versions`, `game_grid_model_assignments`
  i append-only `game_grid_model_activation_events` w rejestrze wspólnym;
- `source_recording_groups` i powiązania źródeł z grupą, z pochodzeniem
  deklaracji operatora i ochroną aliasów;
- `grid_training_cohorts`, `grid_training_samples` i trwałe przypisania ról
  grup do rodziny; jednoznaczny klucz próbki obejmuje approval/revision;
- `grid_training_runs` oraz `grid_reinference_operations`, powiązane z
  istniejącymi `jobs`; wyniki i cel przebiegu mają stabilne klucze idempotencji.

Rodzina nie jest nazwą gry. Wersja ma `kind=neural_grid`, topologię, wejście,
preprocessing, wersję decode/gate, bazowy model, snapshot i podział danych,
metryki, pochodzenie, ścieżki/hashe checkpointów i ONNX. Gra zachowuje profil
zgodności; efektywna wersja jest jej jawnie wybranym przypisaniem. Historyczny
profil daje domyślną wersję tylko przy braku nowego przypisania. Błąd
przypisanego pakietu nie uruchamia cichego fallbacku.

Doszkalanie wymaga również checkpointu PyTorch, z którego wyeksportowano
przypięte wagi ONNX, oraz zgodnego opisu architektury. Podczas rejestracji
bazowych pakietów należy odnaleźć i zweryfikować ten checkpoint na podstawie
manifestu eksportu/runu. Sam plik ONNX nie jest wejściem trenera. Brak dowodu
lub checkpointu daje `GRID_BASE_CHECKPOINT_UNAVAILABLE`; nie wybieramy
innego runu o podobnej nazwie ani nie uruchamiamy treningu od zera.

Migracje Alembic są addytywne. Rejestracja bazowych wersji 777/Mumie sprawdza
niezmienione hashe istniejących pakietów i nie zmienia decyzji operatora.
Numerów migracji nie rezerwujemy na podstawie tego planu; ostatni plik w
chwili odczytu to `0154`. Przed implementacją sprawdzić aktualne heads.

### Proponowany pion HTTP

Przestrzeń `/admin/games/{gameId}/grid-models` jest właścicielem operacji.
Wszystkie nazwy poniżej są propozycją nowego API, nie istniejącymi trasami.

| Operacja | Kontrakt |
| --- | --- |
| GET overview, versions, capabilities | Lekki odczyt metadanych i rzeczywistego aktywnego pakietu, bez budowania kohorty, dekodowania obrazów i GPU. |
| POST cohort-preview, cohorts | Podgląd kwalifikacji; freeze z operationId i tokenem aktualności. Zmiana danych daje 409 i nowy preview. |
| POST runs; GET runs/{id}; POST resume/cancel | Snapshot, baseVersionId i budżet niezmienne; idempotencja, checkpoint i konkretne statusy. |
| GET versions/{id}/comparison | Metryki i zdjęcia kontrolne z tego samego manifestu dla obu modeli, z błędami per przypadek. |
| POST activate, rollback, publish | Oddzielne jawne operacje; expectedAssignmentRevision, operationId, zgodność i zaliczona bramka. |
| POST reinference-preview, reinference-operations; GET operation/{id} | Zamrożony zakres, wersja, rewizje i checksumy; rozpoczęcie i wznowienie osobno od treningu/aktywacji. |
| GET/POST recording-groups i bindings | Odczyt/propozycje oraz świadome deklaracje nagrań i aliasów, bez zmiany nazw/plików/sekwencji. |

Katalog przed utworzeniem gry używa nowego globalnego
`GET /admin/grid-models/catalog` z filtrem topologii/kontraktu. Istniejący
`POST /admin/games` przyjmuje nowe pole wersji i tryb join/fork; nie wymaga
gameId przed utworzeniem gry. Registry obsługuje rodzinę/wersję w jednym
use case, a tworzenie gry i jej przypisania jest jedną transakcją.

Nowe żądanie tworzenia z przypisaniem modelu ma operationId/checksum;
formularz przechowuje klucz do rozstrzygnięcia utraconej odpowiedzi.
Powtórzenie zwraca zapisany wynik tej samej gry, a inne polecenie z tym
samym kluczem daje konflikt. Dotychczasowy create bez nowego przypisania
zachowuje kontrakt legacy. Warstwa zgodności mapuje stare wartości enumu
profilu na format strony; nowe wagi wybiera wyłącznie jawne przypisanie.

Read-only overview archiwalnej 777 obejmuje klasyczny profil i historię
istniejących aktywacji bez podłączania dawnego panelu działań.

Backend/OpenAPI definiują odpowiedzi, frontend używa wygenerowanego klienta
i wrappera. Preview/start/status muszą działać po utracie odpowiedzi oraz
odświeżeniu strony. Każdy kontrakt zmieniający API ma test żądania w tym samym
tasku. Lokalne joby wymagają tego samego zakresu gry i autoryzacji co obecny Admin.

### Trening i ocena

Model bazowy jest aktualną wersją gry przypiętą przy tworzeniu runu.
Wyjątkiem jest jawny run wspólny TASK-1006: targetFamilyId, lista
sourceGameIds i dwie wersje porównawcze są zamrożone przed treningiem,
a jedna baza zostaje wybrana zgodnie z jego protokołem walidacji.
Zgodne gry mogą dostarczyć korekty do tego kandydata przed przełączeniem
swoich aktywnych przypisań. Snapshot zachowuje ich gameId oraz proweniencję.
API sprawdza uprawnienia do każdej gry; eksporter odczytuje ją w oddzielnej
krótkiej transakcji związanej z jej game storage scope/RLS. Nie używa
wyłączenia RLS ani globalnego zapytania obchodzącego zakres gry.
Adapter produkcyjny korzysta z wydzielonych neutralnych funkcji istniejącego
trenera oraz `training_core`; laboratorium pozostaje konsumentem tych samych
funkcji. Kod produkcyjny nie importuje jego store anotacji, CLI Mumii ani
specyficznego ledgera presetów D/E/F.

Nie utrzymujemy arbitralnego presetu 20 epok/5000 kroków/30 min. TASK-1005
przygotowuje preset na podstawie raportów iteracji Mumii i aktualnej kohorty.
W iteracji03 raport podaje próby 443/666/728 kroków (1837 łącznie), wybór
pierwszej próby i 900,328 s treningu na 16 zdjęciach TRAIN/4 holdout.
To historyczna obserwacja, nie uniwersalny limit dla innych gier.
TASK-1005 wylicza kroki z liczby unikalnych targetów, batch size i wymaganych
przejść danych; limit czasu uwzględnia zmierzony koszt kroku w ograniczonym
smoke. Raport zawiera wcześniejszy koszt/best-step oraz uzasadnienie nowego
max_steps/max_epochs/max_seconds i early stopping. Brak zatwierdzonego
presetu blokuje start runu. UI pokazuje liczby i koszt przed potwierdzeniem.
Domyślnie jeden run; budżet obejmuje wszystkie wznowienia. Zwiększenie limitu
jest jawną operacją operatora, nie retry. Dawne D-481 nie daje nowego budżetu.
Parametry jakości i tolerancje decode dziedziczymy z przypiętego pakietu
bazowego i zamrażamy przed treningiem. Zmiana tworzy nowy policy/preset.

Pierwsza wersja wyklucza równoległe joby treningu siatek w aplikacji przez
ich wspólną trwałą dzierżawę. Nie obiecuje blokady wszystkich programów GPU.
Aktualny `symbols/training_job.py` pracuje na CPU; jego algorytmu nie zmieniamy.
Operator rezerwuje okno GPU bez równoległych treningów laboratoryjnych
lub innych programów CUDA. Kontrola gotowości sprawdza aktywne runy aplikacji
i zgłasza rozpoznaną obcą pracę GPU. Nie kończy jej procesu. Wspólna dzierżawa
obejmująca przyszłe CUDA treningi symboli pozostaje poza tą wersją.
GPU nie pracuje w procesie API. Job używa istniejącego runtime workera;
postęp nigdy nie maleje. Checkpoint zawiera model, optimizer, sampler/RNG,
epoch/step, wykorzystany budżet i pełny fingerprint. Anulowanie jest
kontrolowane, z ostatnim poprawnym checkpointem. Brak GPU albo niezgodny
runtime jest widocznym stanem `blocked`, bez cichego wielogodzinnego CPU runu.

Lifecycle: `queued → snapshot_building → training → evaluating → exporting
→ candidate_ready`, z `failed`, `cancelled`, `blocked` i kontrolowanym resume.
Samo `trained` nie oznacza działającego kandydata. Eksport dwóch etapów ONNX
i zgodność CPU PyTorch–ONNX muszą być potwierdzone przed `candidate_ready`.

Bramka porównuje bazę i kandydata na identycznych danych VALIDATION oraz
stałej REGRESSION. Najpierw mierzy odsetek zdjęć z kompletem poprawnych
plansz (D-483), następnie image-macro z kosztem braku 1, odzysk plansz,
NME p95 i poprawność komórek. Pełne metryki zdjęcia liczy wyłącznie na
kompletnych ręcznych anotacjach zdjęć. Test pojedynczej planszy nie dowodzi
kompletności pozostałych plansz.

Proponowana bramka: brak pogorszenia każdej powyższej miary na niezależnych
grupach oraz istniejącym kompatybilnym zestawie regresji; co najmniej jedna
miara VALIDATION musi poprawić się ściśle. Tolerancje geometryczne i parity
pochodzą z niezmiennego protokołu bazowego. Brak porównywalnej miary oznacza
brak dowodu, nie zero błędów. Checkpoint wybierany jest wyłącznie na VALIDATION;
REGRESSION nie służy do strojenia ani do wyboru checkpointu. Niezaliczony
kandydat zostaje zapisany z raportem, lecz nie można go aktywować/publikować.

Publikacja dodaje wersję do katalogu zgodnych modeli. Nie aktywuje jej
w pozostałych grach rodziny. Wybór wersji dla nowej gry korzysta z tego
samego rejestru, nie dodaje stałej opcji dla każdej iteracji.

## Ponowne rozpoznanie pozostałych siatek

Preview liczy aktualne stany każdej pozycji według istniejącej funkcji
`domain/image_geometry_completeness.py::classify_position`, bez zmiany D-484:
`ok`, `uncertain`, `partial`, `missing`, `deferred`, `superseded`.
`uncertain` to również pełna automatyczna siatka bez human/engine acceptance;
nie oznacza dowiedzionego błędu. Pełne cropy V3 i stan kompletności zdjęcia
to odrębne pojęcia. UI pokazuje liczby pozycji, zdjęć i komórek dla każdej
kategorii, powody odroczeń oraz liczbę zgłoszeń „Zła siatka”.

Domyślny filtr obejmuje tylko pozycje `uncertain` i `deferred`, nigdy całe
zdjęcie ze wszystkimi jego planszami na podstawie `geometry_incomplete`.
Pierwsza próba wybiera stabilnie do 100 zdjęć i wyłącznie wybrane sloty.
Może się okazać, że prawie wszystkie plansze 777a2 są `uncertain`; wtedy
preview pokazuje pełną skalę, a limit pierwszej próby zapobiega przypadkowemu
recropowi 341 tys. plansz. Ograniczenie do 100 jest proponowaną ochroną
pierwszego odbioru, nie limitem wielkości całej gry.

Poszerzenie do całego przefiltrowanego zakresu oraz tryb **Wszystkie
automatyczne** wymagają osobnego świadomego wyboru i aktualnego preview.
Tryb wszystkich może obejmować także automatyczne `ok`, ale nie chronione
ręczne geometrie ani odrzucone/superseded/kanoniczne pozycje.
`missing` i `partial` mają osobne jawne filtry; nie są po cichu włączane
przez stan zdjęcia. Liczby przewidywanej inferencji, wybranych plansz,
15-komórkowych recropów i potencjalnie unieważnionych approvals są osobne.
Zdjęcie trafia do inferencji raz; zapis dotyczy tylko slotów frozen planu.

Przed preview/start/resume należy sprawdzić aktywne zadania symboli,
importu i inne przebiegi geometrii w tym samym zakresie. Aktywny runner
typu użytego w TASK-0991 lub inna operacja dotycząca tych zdjęć blokuje start,
aż operator potwierdzi ukończenie albo osobno zatrzyma operację. Nie
przejmujemy ani nie kończymy jej procesu. Start jobów aplikacji stosuje
wspólny guard w `application/jobs.py` dla kolidujących operacji gry;
ta wąska zmiana admission jest w zakresie TASK-0999. Ukończony TASK-0991
sam w sobie nie blokuje operacji; zawsze liczy się świeży status jobów.
Algorytmy rozpoznawania
symboli pozostają bez zmian. CAS każdego zapisu chroni także przed nową
zewnętrzną zmianą, której nie obejmuje guard aplikacji.

Jednostką inferencji jest zdjęcie źródłowe; wynik przypisujemy do istniejących
slotów przez jednoznaczne bindingi i `sequence_number`. Brak bindingu nie
przesuwa numerów sąsiadów, nie tworzy nowego kanonu i pozostaje do korekty.
Ręcznie poprawione sąsiednie plansze pozostają chronione; nie blokują
rozpoznania innych slotów tego zdjęcia. Konflikt rewizji planszy pomija
ten cel, natomiast zmiana źródła unieważnia wszystkie cele z tego zdjęcia.

Przed startem freeze zapisuje model/decode/policy, source SHA, zakres zdjęć
i slotów, expected source/board geometry revisions, human approval,
rejection i ownership revisions. Worker strumieniuje manifest po stabilnym
kluczu; nie ładuje całej kolekcji do pamięci i nie używa offset pagination.
Jedna inferencja zdjęcia, a zapis w krótkiej transakcji tego zdjęcia z
istniejącą globalną kolejnością blokad D-543. Artefakty są publikowane
przed wskazaniem ich w bazie. Ponowienie wykorzystuje receipt tej samej
wersji i tego samego stanu źródła.

| Stan celu przy zapisie | Zachowanie |
| --- | --- |
| Nadal automatyczny, rewizje zgodne, pełne węzły i pewny binding | Nowa automatyczna rewizja V3, dokładne 24 punkty i cropy przez obecny renderer. Nie tworzy human approval ani etykiet treningowych. |
| Ręczna geometria, nowy approval lub szkic aktywnie chroniony przez istniejący kontrakt | Pominięcie `human_geometry_protected`; nie nadpisujemy korekty. |
| Zmieniona rewizja/źródło, nowa decyzja symbolu albo odrzucenie | Pominięcie `state_changed`; raport pozwala przygotować nowy preview. Nie retry ze starą rewizją. |
| Niepełne węzły, ucięta plansza, konflikt sekwencji/bindingu | Zapis propozycji/odroczenia i powód, bez zmiany właściciela sekwencji ani cropów wymagających pewnego bindingu. |
| Odrzucona, superseded, canonical/accepted chroniona pozycja | Pominięcie z powodem; nie ponawiamy przyjęcia ani przejęcia sekwencji. |

Decyzje człowieka dla symboli nie są nadpisywane inferencją. Recrop stosuje
D-462: identyczne piksele/tożsamość zachowują approval; zmieniony crop zachowuje
wybrany symbol i historię, ale wymaga ponownego zatwierdzenia tych pikseli.
Preview uprzedza o liczbie pól, których crop może zmienić się. Automatyczne
podpowiedzi dla nowych cropów używają przypiętej bieżącej wersji modelu
symboli, bez jego doszkalania lub aktywacji w tym przebiegu.

Zmiana przypisania modelu w trakcie joba nie zmienia zamrożonych wag.
Rollback modelu wpływa na przyszłe zadania/importy; nie odwraca automatycznie
recropów zakończonego przebiegu. Ich rewizje i historia pozostają dostępne.

Na skali z ekranów operatora (około 38 tys. zdjęć) manifest, wyniki i postęp
są strumieniowane; jedna krótka transakcja odczytu/zapisu, bez transakcji
na całą grę. Roboczy limit to jedno zdjęcie w części wykonawczej i bounded
prefetch do 8 zdjęć. Indeksy scope/status/cursor weryfikuje plan zapytań.
ETA jest wyliczane po pierwszych rzeczywistych zdjęciach, nie obiecywane
z góry. Rezerwa dysku 5 GiB D-530/D-534 obowiązuje również przy snapshotach,
checkpointach, eksporcie i recropie. Brak miejsca daje trwałe wznowienie.

## Zadania i kolejność wykonania

Wszystkie taski mają status `todo`. Istniejące numery 0993–1001 pozostają
zgodne z raportem audytu; dodane taski 1002–1006 nie zmieniają ich znaczenia.
Przed utworzeniem aktywnych plików sprawdzić ponownie kolizje numerów.
Kolejność zależności poniżej jest ważniejsza od rosnących numerów.

Wspólne Relevant docs: AGENTS.md, README.md, CURRENT_STATE.md, DECISION_LOG.md,
ten plan, TASK_TEMPLATE.md i DEFINITION_OF_DONE.md. Każdy task otrzymuje
przed startem osobny plik w ai_docs/tasks/. Poniższe nowe moduły i symbole
są propozycjami. Ścieżki API/worker/Admin są względem ich katalogów src.
Wspólne kryterium: pełny pion OpenAPI/generowany klient przy zmianie API,
testy, wymagany audyt Claude, Outcome, osobny commit i aktualizacja stanu.
Testy w taskach są planowane, nie zaliczone.


### Etap A — korekta, rejestr i dane


### TASK-0993 — Edytor czterech rogów i dokładnych 24 punktów

- **Status:** `todo`.
- **Goal / Context:** Edytor czterech rogów i dokładnych 24 punktów. Istniejący kontrakt i edytor; głównym ryzykiem jest utrata dokładnych węzłów.
- **Dependencies / entry conditions:** Akceptacja reguł edytora; niezależny od migracji rejestru.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; audyt `claude-fable-5-1`, `medium`, w sesji Claude Code. Istniejący kontrakt i edytor; głównym ryzykiem jest utrata dokładnych węzłów. Zmiana konfiguracji wymaga jawnej aktualizacji tabeli.
- **Relevant docs:** requirements/ADMIN_APP.md (korekta), architecture/API_CONTRACT.md (preview/save).
- **Scope / Technical notes:** Oddzielić tryb uchwytów od geometrii. Ruch rogu transformuje wszystkie węzły homografią. Osobna rekonstrukcja z 4 rogów, cofnięcie i trwały szkic. Preview i zapis V3 używają dokładnych 24 punktów.
- **Expected files:** Reviewer: istniejące deferred-board-cell-geometry-editor.tsx, board-lattice-state.ts, board-lattice-draft-storage.ts, operational-review-state.ts; nowe testy interakcji w test-interactions/.
- **Acceptance criteria / Test cases:** Przełączenie 24→4→24 zachowuje wszystkie liczby. Ruch rogu i translacja zmieniają także wnętrze. Reset/cofnięcie, błędny quad, dotyk, reload i zmiana źródła są sprawdzone. Preview i zapis używają tych samych24 punktów. Starsza korekta4 i wybory symboli zachowują regresję.
- **Verification:** Reviewer test/test:geometry/lint/typecheck oraz test transportu przy zmianie żądania. Każda skończona kontrola ma twardy timeout według sekcji komend.
- **Risks / Out of scope:** nie zmieniać danych operatora, nie rozszerzać topologii, nie wykonywać treningu ani inferencji bez właściwej bramki i budżetu.
- **Outcome:** do uzupełnienia po wykonaniu: changed, verification results, not completed, documentation, wersja/hash commita.


### TASK-0994 — Rejestr modeli, przypisania istniejących gier i zabezpieczenie checkpointów na D

- **Status:** `todo`.
- **Goal / Context:** Rejestr modeli, przypisania istniejących gier i zabezpieczenie checkpointów na D. Migracje, pochodzenie checkpointów i zgodność zamrożonych importów.
- **Dependencies / entry conditions:** Akceptacja encji; aktualne Alembic heads; inwentaryzacja dokładnych bazowych artefaktów.
- **Recommended execution:** `gpt-6.1-sol`, `high`; audyt `claude-fable-5-1`, `high`, w sesji Claude Code. Migracje, pochodzenie checkpointów i zgodność zamrożonych importów. Zmiana konfiguracji wymaga jawnej aktualizacji tabeli.
- **Relevant docs:** architecture/DATA_MODEL.md, API_CONTRACT.md, SUPERVISED_MODEL_IMPROVEMENT.md; tasks/0957-disk-d-cleanup-and-job-paths.md.
- **Scope / Technical notes:** Addytywny registry rodzin/wersji/assignments/events. Backfill dwóch profili w istniejących grach bez zmiany wag; archiwalna 777 bez neural assignment. Kopia wybranych .pt, weights, export/deployment manifests i potrzebnych metadanych na D przez staging, SHA i atomowy publish. Registry przechowuje wyłącznie zarządzane ścieżki produkcyjne na D. Receipt kopii odblokowuje późniejszą osobną ocenę sprzątania C.
- **Expected files:** API: istniejące domain/grid_engine_profiles.py, domain/neural_grid_proposal.py, storage/grid_profile_snapshot_resolver.py, storage/grid_engine_model_store.py, storage/models.py i api/router.py. Nowe domain/grid_model_registry.py, application/grid_model_registry.py, storage/grid_model_registry.py, schemas/grid_models.py, api/grid_models.py, migracja Alembic i adapter importu bazowego checkpointu. OpenAPI/klient/wrapper.
- **Acceptance criteria / Test cases:** Brak checkpointu lub niezgodny hash blokuje rejestrację. Przerwany publish i powtórzenie kopii nie tworzą drugiej wersji ani nie nadpisują obcego pakietu. Nowy proces odczytuje wyłącznie D. Backfill/up/down na bazie testowej zachowują istniejące wersje i zamrożone preflighty; archiwalna 777 nie przechodzi na V3.
- **Verification:** Focused API registry/resolver/migration/manifest tests, lint/typecheck/OpenAPI; bez migracji operatora i bez kopiowania całych 7 GB korpusu. Każda skończona kontrola ma twardy timeout według sekcji komend.
- **Risks / Out of scope:** nie zmieniać danych operatora, nie rozszerzać topologii, nie wykonywać treningu ani inferencji bez właściwej bramki i budżetu.
- **Outcome:** do uzupełnienia po wykonaniu: changed, verification results, not completed, documentation, wersja/hash commita.


### TASK-1002 — Nagrania, aliasy i trwałe role kontrolne

- **Status:** `todo`.
- **Goal / Context:** Nagrania, aliasy i trwałe role kontrolne. Proweniencja danych i ochrona przed przeciekiem między nagraniami oraz liniami modeli.
- **Dependencies / entry conditions:** TASK-0994 i zaakceptowane reguły ról/nagrań.
- **Recommended execution:** `gpt-6.1-sol`, `high`; audyt `claude-fable-5-1`, `high`, w sesji Claude Code. Proweniencja danych i ochrona przed przeciekiem między nagraniami oraz liniami modeli. Zmiana konfiguracji wymaga jawnej aktualizacji tabeli.
- **Relevant docs:** requirements/VISION_LAB.md, SUPERVISED_MODEL_IMPROVEMENT.md (D-527), architecture/VISION_LAB.md.
- **Scope / Technical notes:** Trwałe grupy nagrań, deklaracje operatora, deduplikacja SHA pliku/pikseli i przypisania TRAIN/VALIDATION/REGRESSION. Folder jest propozycją, nie dowodem niezależności. Dziedziczenie wyłączeń rodziców przy fork/wspólnej rodzinie. API oraz niewielki panel deklaracji nagrań stanowią jeden pion.
- **Expected files:** Nowe API domain/source_recording_groups.py, application/source_recording_groups.py, storage/source_recording_groups.py, encje/migracja/schema/router/client; nowe Admin recording-groups-panel.tsx w features/model-quality/.
- **Acceptance criteria / Test cases:** Dwa katalogi jednego filmu i alias zdjęcia w innej grze mają wspólną rolę. Brak deklaracji nie dowodzi niezależności. Holdout rodzica nie trafia do TRAIN dziecka; film wcześniejszego TRAIN nie staje się niezależną kontrolą. Role i idempotencja przetrwają restart. Zmiana chronionej roli jest blokowana.
- **Verification:** Focused API/domain/UI tests, lint/typecheck/OpenAPI; deklaracje użytkownika bez zmiany plików/sekwencji. Każda skończona kontrola ma twardy timeout według sekcji komend.
- **Risks / Out of scope:** nie zmieniać danych operatora, nie rozszerzać topologii, nie wykonywać treningu ani inferencji bez właściwej bramki i budżetu.
- **Outcome:** do uzupełnienia po wykonaniu: changed, verification results, not completed, documentation, wersja/hash commita.


### TASK-0995 — Kwalifikacja korekt i niezmienny snapshot

- **Status:** `todo`.
- **Goal / Context:** Kwalifikacja korekt i niezmienny snapshot. Dokładne etykiety, current approval i zamrożone dane dowodowe.
- **Dependencies / entry conditions:** TASK-0993/0994/1002; decyzja rozszerzająca D-480 przy akceptacji.
- **Recommended execution:** `gpt-6.1-sol`, `high`; audyt `claude-fable-5-1`, `high`, w sesji Claude Code. Dokładne etykiety, current approval i zamrożone dane dowodowe. Zmiana konfiguracji wymaga jawnej aktualizacji tabeli.
- **Relevant docs:** guides/VISION_LAB_EXPORT.md, requirements/VISION_LAB.md, architecture/VISION_LAB.md.
- **Scope / Technical notes:** Preview required/eligible/missing dla każdej roli i per gra. Current human-approved exact lattice także na niekompletnym zdjęciu. Board targets oddzielone od pełnych screen targets. Freeze/copie źródeł/policy/preprocessing/base/checksums/roles/CAS. Stare snapshoty i stary eksporter bez zmiany domyślnej semantyki. Cofnięte dowody blokują nową aktywację.
- **Expected files:** Istniejące scripts/vision_lab_geometry_export.py, worker vision_lab/production_geometry.py i production_snapshot.py jako wzorce. Nowe API domain/grid_training_cohorts.py, application/grid_training_cohorts.py, storage/grid_training_cohorts.py, encje/migracja; neutralny training_core/grid_dataset.py; pełny API pion. Nowy Admin grid-cohort-preview.tsx w features/model-quality/ pokazuje kwalifikację i braki przed treningiem oraz ma test interakcji.
- **Acceptance criteria / Test cases:** Zero korekt 777a2 zwraca brakujące liczby. Stare approval, partial i rejected nie są etykietami. Jedna poprawiona plansza z 9 daje tylko targety węzłów; pełne 9 może dać targety ekranu. Źródła/role są rozłączne. Zmiana podczas freeze daje 409. Kopia źródła, rezerwa 5 GiB, cofnięcie dowodu, restart i utrata odpowiedzi są sprawdzone.
- **Verification:** Focused kwalifikacja/freeze/renderer parity i regresje historycznego eksportera; OpenAPI. Bez budowania snapshotu całej kolekcji przy wejściu do UI. Każda skończona kontrola ma twardy timeout według sekcji komend.
- **Risks / Out of scope:** nie zmieniać danych operatora, nie rozszerzać topologii, nie wykonywać treningu ani inferencji bez właściwej bramki i budżetu.
- **Outcome:** do uzupełnienia po wykonaniu: changed, verification results, not completed, documentation, wersja/hash commita.


### Etap B — zasoby, trening i modele


### TASK-1005 — Preset i dopuszczenie zasobów na podstawie danych iteracji

- **Status:** `todo`.
- **Goal / Context:** Preset i dopuszczenie zasobów na podstawie danych iteracji. Istniejące raporty oraz ograniczony pomiar pozwalają wycenić jeden run bez arbitralnych limitów.
- **Dependencies / entry conditions:** TASK-0994/0995; rzeczywista liczność kohorty; zgoda na ograniczony smoke GPU.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; audyt `claude-fable-5-1`, `medium`, w sesji Claude Code. Istniejące raporty oraz ograniczony pomiar pozwalają wycenić jeden run bez arbitralnych limitów. Zmiana konfiguracji wymaga jawnej aktualizacji tabeli.
- **Relevant docs:** architecture/VISION_LAB.md; finetune-D/ledger.json i iterations/03/report.json wskazane w sekcji treningu, traktowane jako dane.
- **Scope / Technical notes:** Odczyt raportów Mumii z krokami, wybranym checkpointem i czasem. Zapisać uzasadniony preset: batch size, liczba przejść, max_steps/max_epochs/max_seconds i early stopping. Oddzielić grid-only od screen+grid. Smoke do 50 kroków lub 120 s kończy się po pierwszym limicie. Jedna dzierżawa dla app grid runs; operator rezerwuje wyłączne okno względem innych CUDA programów. Żadnej obietnicy globalnej dzierżawy ani zmiany trenera symboli.
- **Expected files:** Istniejące worker vision_lab/neural_grid_protocol.py, neural_grid_runs.py, run_worker.py; nowe training_core/grid_training_admission.py, wersjonowane presety i API admission/report.
- **Acceptance criteria / Test cases:** Brak GPU, niezgodny runtime, inny aktywny run lub niezatwierdzony preset blokuje start. Duża kohorta nie odnawia dawnego budżetu. Smoke ma limit i czyszczenie własnego procesu. Parametry są zamrożone przed treningiem; resume nie resetuje wykorzystanego czasu. Dwa tryby treningu mają osobne uzasadnienia.
- **Verification:** Unit admission/runtime/limit tests; bounded GPU smoke tylko za zgodą, bez pełnego runu lub benchmarku. Każda skończona kontrola ma twardy timeout według sekcji komend.
- **Risks / Out of scope:** nie zmieniać danych operatora, nie rozszerzać topologii, nie wykonywać treningu ani inferencji bez właściwej bramki i budżetu.
- **Outcome:** do uzupełnienia po wykonaniu: changed, verification results, not completed, documentation, wersja/hash commita.


### TASK-0996 — Trwałe doszkalanie V3 w aplikacji

- **Status:** `todo`.
- **Goal / Context:** Trwałe doszkalanie V3 w aplikacji. Dwa etapy, checkpoint/RNG i trwały budżet runu.
- **Dependencies / entry conditions:** TASK-0994/0995/1005; kwalifikowane dane i zatwierdzony preset dla runu.
- **Recommended execution:** `gpt-6.1-sol`, `high`; audyt `claude-fable-5-1`, `medium`, w sesji Claude Code. Dwa etapy, checkpoint/RNG i trwały budżet runu. Zmiana konfiguracji wymaga jawnej aktualizacji tabeli.
- **Relevant docs:** architecture/VISION_LAB.md, requirements/VISION_LAB.md; TASK-0802 tylko jako opis modelu bazowego.
- **Scope / Technical notes:** Wydzielić neutralne funkcje istniejącego fine-tune; produkcja i lab są konsumentami tego samego rdzenia. Job/lease/checkpoint/progress/cancel/resume/export. Grid-only zamraża screen, także BatchNorm. Model version wskazuje ukończony checkpoint-bound export, bez automatycznej aktywacji.
- **Expected files:** Istniejące worker vision_lab/neural_grid_training.py, neural_grid_finetune.py, neural_grid_data.py, neural_grid_model.py, neural_grid_onnx.py, training_core/checkpoint.py i jobs/. Nowe training_core/grid_training.py, images/grid_training_handler.py, API application/grid_training_runs.py i repository/schema/router/client.
- **Acceptance criteria / Test cases:** Restart odtwarza checkpoint, sampler/RNG i lease. Crash po eksporcie przed receipt nie tworzy drugiej wersji. Budżet i postęp nie zerują się. VALIDATION nie trafia do TRAIN. Grid-only nie zmienia parametrów ani statystyk etapu ekranu. Uszkodzony checkpoint nie daje candidate_ready. CPU parity i dotychczasowy lab mają regresje.
- **Verification:** Focused API/worker/unit tests, lint/typecheck/OpenAPI; ograniczony GPU odbiór dopiero po danych/preset/zgodzie. Każda skończona kontrola ma twardy timeout według sekcji komend.
- **Risks / Out of scope:** nie zmieniać danych operatora, nie rozszerzać topologii, nie wykonywać treningu ani inferencji bez właściwej bramki i budżetu.
- **Outcome:** do uzupełnienia po wykonaniu: changed, verification results, not completed, documentation, wersja/hash commita.


### TASK-0997 — Ocena osobno dla każdej gry i bramka kandydata

- **Status:** `todo`.
- **Goal / Context:** Ocena osobno dla każdej gry i bramka kandydata. Pogorszenie jednej gry nie może zostać ukryte przez średnią wspólnego modelu.
- **Dependencies / entry conditions:** TASK-0996; zamrożone niezależne pełne zdjęcia kontrolne i tolerancje.
- **Recommended execution:** `gpt-6.1-sol`, `high`; audyt `claude-fable-5-1`, `medium`, w sesji Claude Code. Pogorszenie jednej gry nie może zostać ukryte przez średnią wspólnego modelu. Zmiana konfiguracji wymaga jawnej aktualizacji tabeli.
- **Relevant docs:** D-483/D-480/D-527; architecture/VISION_LAB.md; quality/GRID_V3_COMPARISON_REPORT_20261004.md.
- **Scope / Technical notes:** Identyczne VALIDATION/REGRESSION dla bieżącego i nowego modelu. D-483 pierwszy, potem image-macro/recall/NMEp95. Per-game/per-recording wyniki i dokładne overlays. Checkpoint wybierany tylko na VALIDATION. Brak porównywalnego dowodu nie jest PASS. UI comparison stanowi część tego pionu.
- **Expected files:** Istniejące worker vision_lab/neural_grid_metrics.py, geometry_core/metrics.py i gate.py. Nowe training_core/grid_evaluation.py, API application/grid_model_evaluation.py i Admin grid-model-comparison.tsx plus API klient.
- **Acceptance criteria / Test cases:** Poprawa średniej przy pogorszeniu 777 lub Mumii blokuje kandydata. Brak planszy ma koszt 1. Niepełna anotacja nie dowodzi kompletności zdjęcia. Kandydat bez poprawy, błąd parity i wycofany dowód blokują aktywację. REGRESSION nie służy do wyboru checkpointu.
- **Verification:** Focused metryki/gate/HTTP/UI tests; raporty z rozdzieleniem znanej i niezmierzonej jakości. Każda skończona kontrola ma twardy timeout według sekcji komend.
- **Risks / Out of scope:** nie zmieniać danych operatora, nie rozszerzać topologii, nie wykonywać treningu ani inferencji bez właściwej bramki i budżetu.
- **Outcome:** do uzupełnienia po wykonaniu: changed, verification results, not completed, documentation, wersja/hash commita.


### TASK-1006 — Kandydat wspólnej geometrii Mumii i 777

- **Status:** `todo`.
- **Goal / Context:** Kandydat wspólnej geometrii Mumii i 777. Kwalifikacja wielu źródeł i linii bazowych oraz ryzyko regresji między grami.
- **Dependencies / entry conditions:** TASK-0994/0995/0996/0997/1005; decyzja rozszerzająca D-527; pokrycie obu gier i oddzielna zgoda na jeden run.
- **Recommended execution:** `gpt-6.1-sol`, `high`; audyt `claude-fable-5-1`, `high`, w sesji Claude Code. Kwalifikacja wielu źródeł i linii bazowych oraz ryzyko regresji między grami. Zmiana konfiguracji wymaga jawnej aktualizacji tabeli.
- **Relevant docs:** Sekcja wspólnego modelu tego planu; requirements/SUPERVISED_MODEL_IMPROVEMENT.md; D-527; architecture/VISION_LAB.md.
- **Scope / Technical notes:** Nowa wspólna rodzina geometryczna po zgodności input/topology. Wybór bazowego checkpointu 777 albo Mumie na zamrożonej VALIDATION i jeden joint fine-tune, bez uśredniania wag. TRAIN z obu gier z równymi wagami gier/nagrań; inherited protected sets obu rodziców. Wszystkie approvals zachowują gameId. Publikacja dopiero po per-game gate; brak PASS pozostawia dotychczasowe dwa modele.
- **Expected files:** Rejestr/cohort/trainer/evaluation z poprzednich tasków; nowe API application/shared_grid_model_candidate.py i wersjonowana joint policy; testy mieszanej kohorty. Bez zmiany modeli symboli i wypłat.
- **Acceptance criteria / Test cases:** Kontrolny alias jednej gry nie trafia do TRAIN drugiej. Większa gra nie dominuje próbkowania. Regresja dowolnej gry blokuje publikację wspólną. Nie ma automatycznej zmiany przypisań. Brak etykiet nowej gry oznacza jakość niezmierzoną. Restart zachowuje wspólną policy i lineage.
- **Verification:** Focused mixed-cohort/sampler/lineage/gate tests; jeden faktyczny run tylko za zgodą z przygotowanymi danymi, nie automatyczna pętla eksperymentów. Każda skończona kontrola ma twardy timeout według sekcji komend.
- **Risks / Out of scope:** nie zmieniać danych operatora, nie rozszerzać topologii, nie wykonywać treningu ani inferencji bez właściwej bramki i budżetu.
- **Outcome:** do uzupełnienia po wykonaniu: changed, verification results, not completed, documentation, wersja/hash commita.


### TASK-0998 — Aktywacja, publikacja i powrót do wersji

- **Status:** `todo`.
- **Goal / Context:** Aktywacja, publikacja i powrót do wersji. CAS, immutable snapshots rozpoczętych importów i historia aktywacji.
- **Dependencies / entry conditions:** TASK-0994/0997; wspólny kandydat opcjonalnie z TASK-1006, gdy zaliczony.
- **Recommended execution:** `gpt-6.1-sol`, `high`; audyt `claude-fable-5-1`, `medium`, w sesji Claude Code. CAS, immutable snapshots rozpoczętych importów i historia aktywacji. Zmiana konfiguracji wymaga jawnej aktualizacji tabeli.
- **Relevant docs:** requirements/IMAGE_INGESTION.md; D-544/D-527; architecture/API_CONTRACT.md i DATA_MODEL.md.
- **Scope / Technical notes:** Activate jednej wskazanej gry/wersji z expectedAssignmentRevision i operationId. Publish oraz rollback oddzielne. Dynamic resolver bierze assignment, nie profile.current. Błąd pakietu bez fallbacku. Baseline katalogu dopuszczony istniejącymi dowodami i jawną publikacją operatora, bez nowego treningu.
- **Expected files:** Registry i resolver/neural snapshot z TASK-0994, worker geometry_core/proposal_runtime.py; API/schema/client i HTTP testy preflight/start/activate.
- **Acceptance criteria / Test cases:** Wyścig aktywacji/preflightu i dwie aktywacje mają poprawnyCAS. Utrata odpowiedzi jest idempotentna. Niezaliczona bramka blokuje aktywację. Nowy job wybiera nową wersję, rozpoczęty zachowuje starą. Rollback nie zmienia cropów. Brak ONNX blokuje bez fallbacku. Publikacja nie aktywuje innych gier; archiwalna 777 bez zmian.
- **Verification:** Focused registry/resolver/import/activation HTTP tests i OpenAPI; bez aktywacji na żywej bazie. Każda skończona kontrola ma twardy timeout według sekcji komend.
- **Risks / Out of scope:** nie zmieniać danych operatora, nie rozszerzać topologii, nie wykonywać treningu ani inferencji bez właściwej bramki i budżetu.
- **Outcome:** do uzupełnienia po wykonaniu: changed, verification results, not completed, documentation, wersja/hash commita.


### Etap C — nowe gry, pozostałe siatki i panel


### TASK-1004 — Wybór modelu i rodziny przy tworzeniu nowej gry

- **Status:** `todo`.
- **Goal / Context:** Wybór modelu i rodziny przy tworzeniu nowej gry. Spójny pion tworzenia gry, migracja legacy enumów i dziedziczenie modeli/wyłączeń.
- **Dependencies / entry conditions:** TASK-0994/0998; opublikowane wersje bazowe; decyzja operatora o zgodności/przynależności.
- **Recommended execution:** `gpt-6.1-sol`, `high`; audyt `claude-fable-5-1`, `high`, w sesji Claude Code. Spójny pion tworzenia gry, migracja legacy enumów i dziedziczenie modeli/wyłączeń. Zmiana konfiguracji wymaga jawnej aktualizacji tabeli.
- **Relevant docs:** requirements/ADMIN_APP.md, SUPERVISED_MODEL_IMPROVEMENT.md (D-527/MODEL-10); architecture/DATA_MODEL.md i API_CONTRACT.md.
- **Scope / Technical notes:** Rozdzielić format strony od version selection. GameCreate dodaje gridModelVersionId, gridModelFamilyMode join/fork i opcjonalną nazwę rodziny. Domyślnie join zgodnej rodziny; fork jest świadomą opcją. Utworzenie gry, fork/root version i assignment w jednej idempotentnej transakcji. GameUpdate nie omija activation gate. Grid snapshot routing opiera się na assignment/capabilities, bez nowego enumu dla każdej wersji. Katalog pokazuje dostępność, zgodność oraz znany zakres oceny.
- **Expected files:** Istniejące API domain/catalog.py, schemas/catalog.py, api/catalog.py, application/catalog.py, storage/catalog_repository.py, domain/grid_engine_profiles.py i resolver. Admin games/game-catalog.tsx, game-catalog-state.ts, game-catalog-actions.ts; OpenAPI/generated client/wrapper; nowe testy creation/model assignment i katalogu.
- **Acceptance criteria / Test cases:** Gang/Treasure bez korekt importuje z jawnie wybranej zgodnej bazy. Brak modelu symboli nie blokuje geometrii. Nieopublikowana lub niezgodna wersja jest blokowana. Fork nie kopiuje wag ani etykiet. Utrata odpowiedzi nie tworzy drugiej gry. Korekty trafiają do jawnie wybranej rodziny, a holdouty rodziców pozostają chronione. Legacy create/update i archiwalna 777 mają regresje.
- **Verification:** Focused API creation/update/request/OpenAPI oraz Admin formularz/actions tests, lint/typecheck; migracyjny backfill zweryfikowany z TASK-0994. Każda skończona kontrola ma twardy timeout według sekcji komend.
- **Risks / Out of scope:** nie zmieniać danych operatora, nie rozszerzać topologii, nie wykonywać treningu ani inferencji bez właściwej bramki i budżetu.
- **Outcome:** do uzupełnienia po wykonaniu: changed, verification results, not completed, documentation, wersja/hash commita.


### TASK-0999 — Backend wybranego zakresu ponownego rozpoznania

- **Status:** `todo`.
- **Goal / Context:** Backend wybranego zakresu ponownego rozpoznania. Zmiana geometrii/cropów, sekwencje, blokady i wznowienie na dużym zbiorze.
- **Dependencies / entry conditions:** TASK-0994/0998; brak kolidującego aktywnego runnera, w tym TASK-0991.
- **Recommended execution:** `gpt-6.1-sol`, `high`; audyt `claude-fable-5-1`, `high`, w sesji Claude Code. Zmiana geometrii/cropów, sekwencje, blokady i wznowienie na dużym zbiorze. Zmiana konfiguracji wymaga jawnej aktualizacji tabeli.
- **Relevant docs:** requirements/ADMIN_APP.md, IMAGE_INGESTION.md; architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md, DATA_MODEL.md; D-462/D-523/D-543.
- **Scope / Technical notes:** Rozkład state/reason i liczb zdjęć/slotów/komórek. Default uncertain+deferred z pierwszą próbą do 100, wszystkie jako opt-in. Freeze wybranych slotów, onephoto inference i zapisy tylko selected. Preview collision guard + atomic job admission dla geometrii/symbolinference. CAS, sequenceownership, renderer, receipts/checkpoint; potwierdzenia człowieka nie są nadpisywane.
- **Expected files:** Istniejące API application/image_grid_reviews.py, managed_reprocess_evidence.py, image_imports.py, jobs.py, domain/image_geometry_completeness.py, storage/sequence_ownership_lock.py oraz worker geometry_core/proposal_runtime.py i renderer. Nowe application/grid_reinference.py, storage/grid_reinference.py, images/grid_reinference_handler.py; schema/router/client.
- **Acceptance criteria / Test cases:** uncertain nie jest dowodem błędnego cropa. Niekompletne zdjęcie nie wybiera wszystkich sąsiadów. Histogramy i pilot 100 są zgodne z zamrożonym planem. Kolidujący runner i wyścig nowych jobów blokują start. CAS chroni geometrię i symbole. Brak środkowego slotu nie przesuwa sekwencji. Odrzucone, superseded i kanon są chronione. Zmieniony crop zachowuje etykietę/historię; identyczny zachowuje approval. Restart/utrata odpowiedzi/brak miejsca nie powtarzają recropu ani nie cofają postępu.
- **Verification:** Focused API/worker/integration i renderer parity; ograniczony pilot na źródłach operatora po osobnym preview/zgodzie, bez benchmarku 38 tys. zdjęć. Każda skończona kontrola ma twardy timeout według sekcji komend.
- **Risks / Out of scope:** nie zmieniać danych operatora, nie rozszerzać topologii, nie wykonywać treningu ani inferencji bez właściwej bramki i budżetu.
- **Outcome:** do uzupełnienia po wykonaniu: changed, verification results, not completed, documentation, wersja/hash commita.


### TASK-1003 — Podgląd, potwierdzenie i raport ponownego rozpoznania w UI

- **Status:** `todo`.
- **Goal / Context:** Podgląd, potwierdzenie i raport ponownego rozpoznania w UI. Gotowy kontrakt pozwala oddzielnie ocenić zakres oraz koszty recropu.
- **Dependencies / entry conditions:** TASK-0999 i jego wygenerowany klient.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; audyt `claude-fable-5-1`, `medium`, w sesji Claude Code. Gotowy kontrakt pozwala oddzielnie ocenić zakres oraz koszty recropu. Zmiana konfiguracji wymaga jawnej aktualizacji tabeli.
- **Relevant docs:** requirements/ADMIN_APP.md; D-541; sekcja rozpoznania tego planu.
- **Scope / Technical notes:** State/reason histogram, domyślne wybrane filtry i pilot, jawny szeroki opt-in, potencjalnie zmienione crop approvals, blocked-by-job z linkiem do postępu. Frozen operationId po utracie odpowiedzi, progress/resume/report i powrót do korekt. UI nie tworzy geometrii ani nie zgaduje zakresu z liczby niekompletnych zdjęć.
- **Expected files:** Nowe Admin features/model-quality/grid-reinference-preview.tsx, grid-reinference-report.tsx i stan/akcje klienta; istniejące jobs UI jako link; nowe interaction tests.
- **Acceptance criteria / Test cases:** ok nie jest wybrane domyślnie; uncertain/deferred i limit 100 są widoczne. Liczby zdjęć, slotów i komórek są osobne. Szeroki zakres wymaga opt-in. Stary preview daje 409. Zmiana gry, blokada przez TASK-0991, utrata odpowiedzi, resume i raport zachowują właściwy stan. Komunikat zmiany cropa wyjaśnia ponowną weryfikację bez utraty etykiety. Klawiatura i mobile działają.
- **Verification:** Admin focused test/test:geometry/lint/typecheck, snapshoty stanu i wizualny odbiór preview/raportu. Każda skończona kontrola ma twardy timeout według sekcji komend.
- **Risks / Out of scope:** nie zmieniać danych operatora, nie rozszerzać topologii, nie wykonywać treningu ani inferencji bez właściwej bramki i budżetu.
- **Outcome:** do uzupełnienia po wykonaniu: changed, verification results, not completed, documentation, wersja/hash commita.


### TASK-1000 — Pełna sekcja doszkalania i wycofanie starego panelu

- **Status:** `todo`.
- **Goal / Context:** Pełna sekcja doszkalania i wycofanie starego panelu. Integracja gotowych pionów i regresja istniejącej jakości symboli/diagnostyki.
- **Dependencies / entry conditions:** TASK-0993–0999, 1002–1006; backend capabilities/registry/cohort/run są źródłem prawdy.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; audyt `claude-fable-5-1`, `medium`, w sesji Claude Code. Integracja gotowych pionów i regresja istniejącej jakości symboli/diagnostyki. Zmiana konfiguracji wymaga jawnej aktualizacji tabeli.
- **Relevant docs:** requirements/ADMIN_APP.md, APP_V3_FUNCTIONAL_INVENTORY.md, SUPERVISED_MODEL_IMPROVEMENT.md; D-541/D-527.
- **Scope / Technical notes:** Sekcja gry dane→train→comparison→activation→rescan, z panelami wcześniejszych tasków i informacją grid-only. Liczniki braku danych oraz źródeł/kohorty. Usunąć globalny mount starego GridQualityPanel. Archival777 zachowuje wyłącznie do odczytu active classical profile/history; symboltraining pozostaje oddzielny. Wejście nie uruchamia joba.
- **Expected files:** Istniejące Admin model-quality-workspace.tsx, grid-quality-panel.tsx, model-quality-actions.ts, catalog/catalog-workspace.tsx i admin-navigation-state.ts; nowe grid-model-workspace.tsx, grid-model-client.ts, grid-model-state.ts; model-quality contract/loading/interactions tests.
- **Acceptance criteria / Test cases:** Brak danych pokazuje liczby braków, nie uruchamia treningu. Archiwalna 777 ma czytelny profil bez dawnych działań. Stary blok znika, trening symboli pozostaje. Unsupported, zmiana gry i refresh podczas runu są sprawdzone. Bramka blokuje aktywację. Panel obsługuje oba modele bazowe i odrzuconego albo zaliczonego kandydata wspólnego. Cały workflow działa bez skryptów operatora.
- **Verification:** Focused Admin tests/interactions/lint/typecheck i wizualny odbiór pełnego panelu; backend klasyczny i historia pozostają. Każda skończona kontrola ma twardy timeout według sekcji komend.
- **Risks / Out of scope:** nie zmieniać danych operatora, nie rozszerzać topologii, nie wykonywać treningu ani inferencji bez właściwej bramki i budżetu.
- **Outcome:** do uzupełnienia po wykonaniu: changed, verification results, not completed, documentation, wersja/hash commita.


### Etap D — odbiór


### TASK-1001 — Odbiór i instrukcja operatora

- **Status:** `todo`.
- **Goal / Context:** Odbiór i instrukcja operatora. Spójny przepływ i dowody świeżego procesu zamiast deklaracji sukcesu.
- **Dependencies / entry conditions:** Wszystkie wcześniejsze taski, audyty, zgoda na dane/GPU/migrację i etykiety operatora.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; audyt `claude-fable-5-1`, `medium`, w sesji Claude Code. Spójny przepływ i dowody świeżego procesu zamiast deklaracji sukcesu. Zmiana konfiguracji wymaga jawnej aktualizacji tabeli.
- **Relevant docs:** process/DEFINITION_OF_DONE.md; wszystkie dokumenty właścicielskie wskazane wyżej; quality/AUDIT_REPORT_TEMPLATE.md.
- **Scope / Technical notes:** Izolowany E2E na bazie testowej i ograniczony odbiór operatora: correction→cohort→training→comparison→activate→selected reinference→restart. Dwa game scopes, nowa gra i shared candidate. Dokumentacja, decyzje D-480/D-527/budżet, mapy oraz instrukcja migracji i powrotu. Odbiór wyniku i zgoda na integrację dopiero na końcu zleconego zakresu.
- **Expected files:** Nowe guides/V3_GRID_FINE_TUNING_OPERATOR.md i quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md; acceptance test; wymagania ADMIN_APP/SUPERVISED_MODEL_IMPROVEMENT/IMAGE_INGESTION, architektura DATA_MODEL/API_CONTRACT/SUPERVISED_MODEL_IMPROVEMENT/VISION_LAB, inventory/mapy/stan.
- **Acceptance criteria / Test cases:** E2E potwierdza dowody niezależności, ochronę ręcznych decyzji/symboli/sekwencji, utratę odpowiedzi i restart. Trener używa wyłącznie D. Pusta kohorta, budżet, tworzenie gry, fork, wspólny lineage i per-game gate są sprawdzone. Archiwalna 777 pozostaje identyczna. Recrop obejmuje tylko wybrane sloty i odpowiada liczbom preview.
- **Verification:** Ograniczony E2E, lint/typecheck/build/OpenAPI/docs/code-map; operator lifecycle/migracja ręczne; bez gwarancji dla 38 tys. zdjęć z małego testu. Każda skończona kontrola ma twardy timeout według sekcji komend.
- **Risks / Out of scope:** nie zmieniać danych operatora, nie rozszerzać topologii, nie wykonywać treningu ani inferencji bez właściwej bramki i budżetu.
- **Outcome:** do uzupełnienia po wykonaniu: changed, verification results, not completed, documentation, wersja/hash commita.


### Faza operatora O — przygotowanie etykiet przed pierwszym runem

Kod wszystkich etapów może powstawać i być testowany na standardowych
izolowanych fixture'ach bez oczekiwania na korekty żywej kolekcji. Pierwszy
rzeczywisty run jest jednak zablokowany progami kohorty. Operator może zacząć
zbieranie korekt po TASK-0993, a deklaracje/preview ról po TASK-1002/0995.
Niezależne pule bazowe trzeba kwalifikować, nie zakładać ich dostępności.

Planowanie pracy operatora: poprawić najpierw 10 plansz, zmierzyć czas,
sprawdzić zapis i kwalifikację. Następnie preview wycenia brakującą liczbę
plansz według mediany tego pomiaru plus czas deklaracji źródeł. Wstępny
budżet dla samodzielnego przygotowania 120 plansz to 2–6 h przy założeniu
1–3 min/plansza; to scenariusz do sprawdzenia, nie zmierzona wydajność.
Dobór trzech niezależnych nagrań i ich zdobycie są osobnym czasem operatora.
Wspólny model wymaga pokrycia obu gier osobno, więc preview nie sumuje
ich etykiet do jednego minimum. UI pokazuje grid-only, dopóki TRAIN nie ma
pełnych anotacji zdjęć potrzebnych etapowi ekranu.

## Weryfikacja planowana i pokrycie wymagań

| Wymaganie lub uwaga | Task | Dowód |
| --- | --- | --- |
| Edytor 4/24 bez utraty geometrii |0993| Roundtrip/homografia/restart/preview i zapis 24 punktów. |
| P1-1: nowe gry i bazowa wersja bez korekt |0994/1004| Backfill, creation API/formularz, version selection, join/fork i izolacja. |
| P1-2: pusta kohorta i praca operatora |1002/0995, faza O| required/eligible/missing, minimalne role i jawne przygotowanie danych. |
| P1-3: stany pozycji i bezpieczny zakres |0999/1003| Histogram, domyślne uncertain/deferred, pilot 100, szeroki opt-in i admission guard. |
| P1-4: checkpointy na D, ochrona C |0994/0957| Hash/receipt, immutable publish i nowy proces D-only. |
| P1-5: wykonawca/audytor |Wszystkie| Codex wykonuje, Claude Code audytuje; tabela i każda rekomendacja spójne. |
| P2-1: granulacja |1002/0995/0999/1003| Nagrania, snapshot, backend i UI rozdzielone. |
| P2-2: rzeczywista koordynacja GPU |1005/0996| Wykluczenie app grid runs, jawne okno operatora; brak fikcyjnej globalnej dzierżawy. |
| P2-3: klasyczny profil archiwalnej 777 |1000| Wyłącznie odczyt profilu/historii, bez starego workflow. |
| P2-4: preset na podstawie danych |1005| Raporty iteracji, aktualna kohorta, ograniczony smoke, preset i budżet zatwierdzone. |
| P2-5: prawidłowy moduł GAME_SECTIONS |1000| admin-navigation-state.ts i test regresji nawigacji. |
| Wspólny model Mumii/777 — kierunek operatora |1006| Balanced TRAIN, inherited holdouts, bramka osobno w każdej grze. |
| Trening/ocena/wersje w aplikacji |0996/0997/0998/1000| Checkpoint, per-game gate, CAS i frozen jobs. |
| Cały proces i ochrona danych |1001| E2E po restarcie, operator guide, niezmienność archiwalnej 777/symboli/sekwencji. |

Potwierdzone istniejące komendy, uruchamiane z `D:\game_predicotr`.
Każdą skończoną komendę należy wykonać z twardym limitem procesu do 120 s,
np. wrapperem poniżej. Nie uruchamiać wszystkich komend automatycznie
w każdym tasku; najpierw focused tests, następnie lint/typecheck, dopiero
potem wymagany szerszy zakres. Nowe testy opisane wyżej dopiero powstaną.

```powershell
function Invoke-PlanCheck([string]$File, [string[]]$Arguments) {
  $p = Start-Process -FilePath $File -ArgumentList $Arguments -PassThru -NoNewWindow
  if (-not $p.WaitForExit(120000)) {
    taskkill.exe /PID $p.Id /T /F | Out-Null
    throw 'Kontrola przekroczyła 120 s; sprawdź potomne procesy przed ponowieniem.'
  }
  if ($p.ExitCode -ne 0) { throw "Kontrola zakończyła się kodem $($p.ExitCode)." }
}
Invoke-PlanCheck 'npm.cmd' @('run','test','--workspace','@game-predictor/reviewer')
Invoke-PlanCheck 'npm.cmd' @('run','test:geometry','--workspace','@game-predictor/reviewer')
Invoke-PlanCheck 'npm.cmd' @('run','lint','--workspace','@game-predictor/reviewer')
Invoke-PlanCheck 'npm.cmd' @('run','typecheck','--workspace','@game-predictor/reviewer')
Invoke-PlanCheck 'npm.cmd' @('run','test','--workspace','@game-predictor/admin')
Invoke-PlanCheck 'npm.cmd' @('run','test:geometry','--workspace','@game-predictor/admin')
Invoke-PlanCheck 'npm.cmd' @('run','lint','--workspace','@game-predictor/admin')
Invoke-PlanCheck 'npm.cmd' @('run','typecheck','--workspace','@game-predictor/admin')
Invoke-PlanCheck 'npm.cmd' @('run','openapi:check')
Invoke-PlanCheck 'npm.cmd' @('run','docs:check')
Invoke-PlanCheck 'npm.cmd' @('run','code-map:check')
```

Python focused tests: `.venv\Scripts\python.exe -m pytest <test taska>`;
ruff/mypy dla zmienionych modułów według repozytorium. GPU smoke używa
zweryfikowanego środowiska treningowego, nie zakłada dawnej ścieżki na C.
Wcześniejsze unrelated failures pozostają poza zakresem i są jawnie zapisane.

## Bramki wykonania, koszty i zakres wyłączony

Kontrole rewizji 2 (2026-10-14): `docs:check`, `git diff --check` i kontrola
zgodności 14 tasków z końcową tabelą modeli zaliczone. To weryfikacja
dokumentacji; testów aplikacji i nowego audytu Claude nie uruchamiano.

- Raport Claude pierwszej wersji pozostaje REVISE. Odpowiedź na uwagi jest
  w quality/V3_GRID_FINE_TUNING_PLAN_REMEDIATION_CODEX_20261014.md; nie jest
  drugim niezależnym audytem ani deklaracją PASS.
- Planowanie nie uruchomiło treningu, benchmarku, inferencji, migracji,
  aktywacji ani usług. Liczby bazy przyjęto z datowanego raportu audytora;
  dokładne artefakty checkpointu/eksportu zweryfikowano tylko do odczytu.
- Operator wybrał Codex jako wykonawcę oraz Claude Code jako audytora.
  Istniejąca sesja Claude Code jest dostępna według przekazanego raportu
  (claude-fable-5-1/medium), a rekomendacja high dla danych/migracji jest
  stosowana w repo. Brakclaude wPATH procesu Codex nie zatrzymuje startu.
  Brief i diff mogą być przekazane tej sesji w trybie read-only; raport
  ma format repo, zakres -Paths i jedną rundę. Nie logować/instalować CLI
  ani zastępować audytu drugim modelem GPT bez zgody operatora.
- Przed implementacją: akceptacja rewizji 2, kosztu i nowych propozycji
  minimum kohorty/pilota; kontrola numerów; decyzje rozszerzające D-480
  (ręczne TRAIN) oraz D-527 (wspólna geometria Mumii/777). Numery decyzji
  sprawdzić przy zapisie, nie rezerwować D-548 z historycznego audytu.
- Przed rzeczywistym treningiem: checkpointy na D, kwalifikowane etykiety,
  niezależne pełne dane kontroli, runtime GPU, zatwierdzony preset i
  wyłączne okno zasobów. Dawne budżety D-481 nie odnawiają się automatycznie.
- Przed live reinference: aktualny preview liczb i wybranych slotów,
  zakończenie/oddzielne zatrzymanie kolidujących runnerów, aktywna zgodna
  wersja i jawny start. Migawka i CAS nadal chronią przed zmianą w trakcie.
- Zaktualizowany zgrubny szacunek 14 tasków: około 9–21 dni roboczych
  implementacji, kontroli i jednej rundy audytu na task. To korekta
  optymistycznych 3–6 dni; więcej migracji/pionów HTTP i wspólny model
  wymagają osobnej kwalifikacji. Faktyczny czas agentów będzie aktualizowany
  po etapie A, bez obietnicy niezmiennego terminu. Koszt/tokeny pakietu nie
  są wiarygodnie znane. Przed startem wymagana wyraźna zgoda na taki koszt.
- Przygotowanie etykiet przez operatora jest osobną fazą O (scenariusz 2–6 h
  dla 120 plansz od początku, do weryfikacji próbą 10); oczekiwanie na nagrania,
  GPU i odbiór nie mieści się w szacunku implementacji.
- Etapy uruchamia operator; task ma własny audit/commit/Outcome. Akceptacja
  wyniku i zgoda na integrację dopiero na końcu zleconego taska/etapu/planu.
  Brak automatycznego merge/push. Migracje i lifecycle usług ręczne oraz
  oddzielnie autoryzowane; nie wykonujemy cleanupu C w tym planie.
- Poza zakresem: uczenie/łączenie modeli symboli i wypłat, zmiana OCR lub
  numeracji, przeniesienie archiwalnej 777 do V3, sieć 3 × 3, chmura/Redis/Celery,
  globalna dzierżawa wszystkich programów CUDA, usuwanie danych, pętla
  wielu runów i benchmark 38 tys. zdjęć. Wąski guard admission kolidujących
  zadań symbolinference w TASK-0999 jest jawnie w zakresie.

## Przypisanie modeli do zadań

Wybór operatora: Codex wykonuje, sesja Claude Code audytuje. Dokładne
konfiguracje poniżej obowiązują zarówno w taskach, jak i w ich briefach.
Audyt jest z innej rodziny niż wykonawca; brak CLI w tym procesie nie
wyklucza audytu w istniejącej sesji Claude. Same przypisania nie są zgodą
na implementację lub delegowanie wykonawców.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
| --- | --- | --- | --- | --- |
|TASK-0993|gpt-6.1-sol|medium|Istniejący kontrakt i edytor; głównym ryzykiem jest utrata dokładnych węzłów.|claude-fable-5-1 medium, read-only w sesji Claude Code.|
|TASK-0994|gpt-6.1-sol|high|Migracje, pochodzenie checkpointów i zgodność zamrożonych importów.|claude-fable-5-1 high, read-only w sesji Claude Code.|
|TASK-1002|gpt-6.1-sol|high|Proweniencja danych i ochrona przed przeciekiem między nagraniami oraz liniami modeli.|claude-fable-5-1 high, read-only w sesji Claude Code.|
|TASK-0995|gpt-6.1-sol|high|Dokładne etykiety, current approval i zamrożone dane dowodowe.|claude-fable-5-1 high, read-only w sesji Claude Code.|
|TASK-1005|gpt-6.1-sol|medium|Istniejące raporty oraz ograniczony pomiar pozwalają wycenić jeden run bez arbitralnych limitów.|claude-fable-5-1 medium, read-only w sesji Claude Code.|
|TASK-0996|gpt-6.1-sol|high|Dwa etapy, checkpoint/RNG i trwały budżet runu.|claude-fable-5-1 medium, read-only w sesji Claude Code.|
|TASK-0997|gpt-6.1-sol|high|Pogorszenie jednej gry nie może zostać ukryte przez średnią wspólnego modelu.|claude-fable-5-1 medium, read-only w sesji Claude Code.|
|TASK-1006|gpt-6.1-sol|high|Kwalifikacja wielu źródeł i linii bazowych oraz ryzyko regresji między grami.|claude-fable-5-1 high, read-only w sesji Claude Code.|
|TASK-0998|gpt-6.1-sol|high|CAS, immutable snapshots rozpoczętych importów i historia aktywacji.|claude-fable-5-1 medium, read-only w sesji Claude Code.|
|TASK-1004|gpt-6.1-sol|high|Spójny pion tworzenia gry, migracja legacy enumów i dziedziczenie modeli/wyłączeń.|claude-fable-5-1 high, read-only w sesji Claude Code.|
|TASK-0999|gpt-6.1-sol|high|Zmiana geometrii/cropów, sekwencje, blokady i wznowienie na dużym zbiorze.|claude-fable-5-1 high, read-only w sesji Claude Code.|
|TASK-1003|gpt-6.1-sol|medium|Gotowy kontrakt pozwala oddzielnie ocenić zakres oraz koszty recropu.|claude-fable-5-1 medium, read-only w sesji Claude Code.|
|TASK-1000|gpt-6.1-sol|medium|Integracja gotowych pionów i regresja istniejącej jakości symboli/diagnostyki.|claude-fable-5-1 medium, read-only w sesji Claude Code.|
|TASK-1001|gpt-6.1-sol|medium|Spójny przepływ i dowody świeżego procesu zamiast deklaracji sukcesu.|claude-fable-5-1 medium, read-only w sesji Claude Code.|
