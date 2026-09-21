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

Obejmuje tylko gry `777`, `blazing`, `gang`, `reels` i `mummies`.
Treasure jest poza zakresem. `reels_test` jest zarezerwowany dla V7, a
`rells_big` nie jest niezależnym holdoutem; żaden z nich nie może być użyty.

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

Każda z pięciu gier ma jawnie zadeklarowaną topologię pełnej strony: 3 × 3
plansze, dziewięć aktywnych slotów row-major i 3 × 5 komórek na planszę.
Inna topologia jest błędem corpusów, nie kandydatem do automatycznej adaptacji.

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
`not_evaluable`, nigdy 0% ani sukces. G00 nie definiuje tolerancji,
minimalnych liczności ani progów; ustali je i przedstawi do zatwierdzenia G01.

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
```

Pliki wynikowe są operator-owned artefaktami lokalnymi. Nie należy dodawać
JPEG-ów, bezwzględnych ścieżek, anotacji acceptance ani raportu G08 do repozytorium.
