---
title: Virtual geometry schema ownership
status: accepted
last_updated: 2026-08-30
---

# Virtual geometry schema ownership

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

### Source geometry revision

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

Przyszły stan `ready` musi być związany z dokładną rewizją polityki, checksumą
wejścia walidacji i jobem walidującym. Zmiana polityki unieważnia gotowość
poprzedniego snapshotu, ale nie zmienia historycznych jobów ani source geometry
revisions.

## Macierz ścieżek zapisu

| Ścieżka | Zapis kanoniczny | Projekcje i audyt |
|---|---|---|
| automatyczna geometria structured | nowa `image_source_geometry_revision` ze wszystkimi aktywnymi slotami | `recognized_boards` wskazują właściwe sloty; obserwacje zapisują render provenance |
| ręczna korekta virtual | nowa pełna source revision z podmienionym jednym slotem | tylko poprawiana plansza zmienia selektor; powstaje board geometry event/revision i nowe obserwacje |
| ręczna korekta legacy | historyczna board geometry revision i jej assety | `recognized_boards` materializuje bieżący stan; brak fałszywej source revision virtual |
| preview | brak trwałego właściciela | wynik efemeryczny związany z oczekiwanym źródłem, rewizją i topologią |
| trening | brak zmiany geometrii | manifest kohorty wskazuje zatwierdzoną rewizję i checksumy cropów |

Każdy zapis planszy blokuje i waliduje w kolejności: gra, wystąpienie źródła,
sekwencja, review item/plansza, komórki. Zmiana jednej planszy jest atomowa dla
jej selektora, obserwacji, review, canonical i projekcji wyszukiwania.

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
