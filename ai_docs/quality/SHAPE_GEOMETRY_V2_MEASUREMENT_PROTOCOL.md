---
title: Shape geometry v2 corpus and measurement protocol
status: active
last_updated: 2026-09-21
---

# Protokół corpusów i pomiaru geometrii shape v2

## Cel i granica

Protokół ustanawia dane wejściowe dla eksperymentalnego wariantu
`shape_frame_geometry_v2_0`. Nie zmienia domyślnego
`selective_board_review_v1_1`, nie uruchamia jobów ani importów i nie jest
bramką aktywacji produkcyjnej.

Schema corpusu v1 obejmuje wyłącznie gry `777`, `blazing`, `gang`, `reels` i
`mummies`. Schema v2 dopuszcza kolejną zgodną grę po jawnym zadeklarowaniu
rodziny `framed_full_page_v2`; nie zmienia rdzenia ani topologii. Treasure jest
poza zakresem. `reels_test` jest zarezerwowany dla V7, a `rells_big` nie jest
niezależnym holdoutem; żaden z nich nie może być użyty.

## Widoczność danych i manifesty

Są dwa osobne lokalne manifesty:

| Widoczność | Dozwolone splity | Dostęp |
| --- | --- | --- |
| `executor` | `development`, `calibration` | Projektowanie, diagnoza, baseline v1.1 i G01. |
| `acceptance` | `acceptance` | Wyłącznie niezależny odbiór G08. |

Runner baseline i przyszłe eksperymenty odrzucają manifest `acceptance`.
Niezależny operator może jednorazowo uruchomić kontrolę granicy obu już
zamrożonych manifestów. Raport tej kontroli zawiera wyłącznie fingerprinty i
liczności, bez ścieżek źródeł.

Każdy wpis źródła deklaruje:

- identyfikator gry i źródła;
- bezpieczną ścieżkę względną do operator-owned corpus rootu;
- SHA-256 i deterministyczny `sourceOrdinal`;
- `captureFamilyId`, który grupuje podobne klatki jednego nagrania;
- split oraz rolę `measurement` albo `anchor_pool`;
- trudności/scenariusze.

Jedna rodzina ujęć nie może trafić do dwóch splitów. Identyczne SHA wewnątrz
jednego splitu są raportowane jako kopie, a nie niezależne dowody. Identyczny
SHA lub rodzina po obu stronach granicy executor/acceptance blokuje protokół.

Każda gra ma jawnie zadeklarowaną topologię pełnej strony: 3 × 3 plansze,
dziewięć aktywnych slotów row-major i 3 × 5 komórek na planszę. Inna topologia
jest błędem corpusów, nie kandydatem do automatycznej adaptacji.

## Anotacje i kotwica

Anotacje są tworzone przed uruchomieniem predykcji. Format nie przyjmuje pola
predykcji. Dla źródła zapisuje się jego SHA, stan strony, potwierdzenie
topologii, widoczność siatki, zgodę na kandydaturę kotwicy i aktywny czas
operatora.

Jedna kotwica v2 na grę jest wybierana wyłącznie z `anchor_pool` w
`development`. Musi mieć ręcznie oznaczony stan `complete`, potwierdzoną
topologię, widoczną siatkę oraz `anchorCandidate=true`. Kandydaci są
sortowani po `captureFamilyId`, `sourceOrdinal`, SHA i `sourceId`.
Raport zachowuje wszystkie wcześniejsze odrzucenia. Kotwica nie może mieć roli
`measurement`, dlatego nie ocenia własnej gry.

Stan `vertical_crop`, `side_partial`, `occluded` albo `not_a_page`
nigdy nie kwalifikuje źródła jako kotwicy. Ucięcie góra/dół pozostaje do
korekty, wymiany albo wykluczenia; protokół nie tworzy pionowego importu
częściowego.

## Baseline v1.1

Baseline wykorzystuje istniejący, przypięty profil
`VerifiedPageRegistrar`. Jest read-only: ładuje JPEG przez normalizację EXIF
do RGB i zapisuje tylko raport JSON. Nie tworzy joba, importu, korekty, migracji
ani danych w bazie.

W każdym przebiegu wybierane jest najwyżej dziesięć źródeł `measurement` na
grę, w trwałej kolejności rodziny, ordinalu, SHA i ID. Raport dla źródła ma
jednoznaczny stan:

| Stan | Znaczenie |
| --- | --- |
| `registered` | v1.1 zwrócił geometrię i pełną diagnostykę wejściowego profilu. |
| `review_required` | v1.1 nie uzyskał dowodu; zapisano ograniczoną diagnostykę. |
| `source_error` | Nie można było zdekodować danego, wcześniej zadeklarowanego JPEG-a. |
| `not_configured` | Gra ma materiał pomiarowy, lecz brak używalnego przypiętego profilu v1.1. |
| `not_evaluable` | Gra nie ma źródeł `measurement` w manifeście wykonawczym. |

Raport jest kanoniczny. Ponowne uruchomienie z `--check` musi dać dokładnie
te same bajty; różnica oznacza drift i blokuje porównanie v2.

## Metryki

Każdy późniejszy raport per gra ma osobne liczniki i mianowniki:

| Miara | Licznik | Mianownik |
| --- | --- | --- |
| Poprawność propozycji plansz | ręcznie potwierdzone propozycje planszy | wszystkie propozycje z zamrożonego źródła |
| Poprawne automaty plansz | plansze automatycznie poprawne bez korekty | wszystkie automaty plansz |
| Poprawne źródła bez interwencji | źródła kompletne i automatycznie poprawne | wszystkie oceniane źródła |
| Błędne automaty | dowolny błędny automatyczny obrys, slot, siatka lub kompletność | wszystkie automaty |
| Interwencje | źródła/plansze z korektą lub review | wszystkie oceniane źródła/plansze |
| Tylko potwierdzenie | automaty wymagające wyłącznie jawnego potwierdzenia | wszystkie automaty |
| Czas operatora | suma aktywnego czasu z anotacji i workflowu | raportowany osobno, bez procentowego mianownika |
| Koszt konfiguracji | aktywny czas ramki, koloru i pierwszej kotwicy | raportowany osobno dla każdej gry |

Nieudane dekodowanie, review, wykluczenie po uruchomieniu oraz source error
pozostają w odpowiednim raporcie ogólnym. Pusty mianownik daje
`not_evaluable`, nigdy 0% ani sukces. G01 utrwala parametry wariantu,
fingerprinty i mianowniki; liczbową politykę jakości można utworzyć wyłącznie z
niepustych danych executor. Jej kwalifikacja i automatyczna aktywacja należą do
G07, więc brak danych nie jest wymówką dla fikcyjnego progu ani blokadą G02–G06.

## Eksperyment G01 i izolacja transferu

Runner `run_shape_geometry_v2_experiment.py` przyjmuje wyłącznie executor,
zamrożony inventory, checksum-bound anotacje oraz obserwacje operatora. Nie
dekoduje obrazu poza ponowną kontrolą inventory, nie uruchamia detektora, joba,
importu ani zapisu do bazy. Każda obserwacja przypina manifest, inventory,
anotacje, identyfikator i parametry wariantu algorytmu oraz wynik jednego
źródła.

Stałe warianty to `shape_contrast_v1`, `shape_contrast_color_assist_v1`,
`shape_contrast_local_anchor_v1` i `shape_contrast_shared_profile_v1`. Raport
osobno podaje automaty poprawne i błędne, review, korekty, tylko potwierdzenie,
czas operatora, oczekiwaną i ocenioną liczbę źródeł oraz brakujące źródła.
Niepełna macierz obserwacji, brak anotacji któregokolwiek źródła pomiarowego
albo brak lokalnej kotwicy daje `not_evaluable` dla tego wariantu.

Wariant profilu wspólnego wymaga checksummy profilu i niepustej listy gier,
które go zbudowały. Badana gra nie może znaleźć się na tej liście; naruszenie
jest błędem fail-closed, a nie lokalnym fallbackiem. Dla jednego wariantu gry
wszystkie źródła muszą wskazać tę samą proweniencję profilu.

## Kolejność operatorska

```powershell
# Zamrożenie executor corpus.
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe scripts\freeze_shape_geometry_v2_corpus.py --manifest <executor-manifest.json> --output <executor-inventory.json>

# Niezależny operator: zamrożenie i kontrola granicy acceptance.
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe scripts\freeze_shape_geometry_v2_corpus.py --manifest <executor-manifest.json> --output <executor-inventory.json> --acceptance-manifest <acceptance-manifest.json> --boundary-output <split-boundary.json>

# Odtwarzalny baseline v1.1, maksymalnie 10 źródeł na grę.
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe scripts\run_shape_geometry_v2_v11_baseline.py --manifest <executor-manifest.json> --inventory <executor-inventory.json> --output <v11-baseline.json>

# Kontrola driftu przed G01.
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe scripts\run_shape_geometry_v2_v11_baseline.py --manifest <executor-manifest.json> --inventory <executor-inventory.json> --output <v11-baseline.json> --check

# Read-only raport G01 i jego odtwarzalna kontrola.
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe scripts\run_shape_geometry_v2_experiment.py --manifest <executor-manifest.json> --inventory <executor-inventory.json> --annotations <annotations.json> --observations <observations.json> --output <g01-experiment.json>
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe scripts\run_shape_geometry_v2_experiment.py --manifest <executor-manifest.json> --inventory <executor-inventory.json> --annotations <annotations.json> --observations <observations.json> --output <g01-experiment.json> --check
```

Pliki wynikowe są operator-owned artefaktami lokalnymi. Nie należy dodawać
JPEG-ów, bezwzględnych ścieżek, anotacji acceptance ani raportu G08 do repozytorium.
