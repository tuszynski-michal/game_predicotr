# T03i — odzyskane metadane selekcji, 2026-09-27

Wykonawca: gpt-6-sol / medium. Dziewięć wskazanych JSON skopiowano z Kosza
bez przenoszenia, usuwania lub nadpisywania. Nowy proces potwierdził poprawny
JSON, identyczny rozmiar i SHA każdej kopii oraz zachowanie wszystkich źródeł.
Niezależny audyt gpt-6-astra / medium zakończony PASS, bez otwartych P0–P2.

## Zakres i dowody operacji

Koordynator wcześniej zakończył autoryzowane przeszukanie: 375 wpisów głównych,
dwa usunięte katalogi, 65 katalogów / 70914 plików; bez błędów, pominiętych
reparse points i pozostałej kolejki. Nie powtarzano rekurencyjnego skanu.
Wykonawca ponownie odczytał Shell.Application Namespace(10) wyłącznie dla
metadanych dziewięciu wskazanych pozycji. Data usunięcia poniżej jest surową
wartością zwróconą przez Shell bez oznaczenia strefy; nie jest opisana jako
czas lokalny. Audyt wskazał, że pierwsza wartość odpowiada UTC z pliku $I,
a nie czasowi lokalnemu. Surowe deletedAt w manifeście pozostają niezmienione.

Odczytano tylko dziewięć JSON i aktualne 473 JPG pod
`C:/Users/tuszy/Documents/game_predictor_traning_set`. Nie hashowano zdjęć
ani filmów w Koszu. Sprawdzono brak dowiązań/reparse points w źródłach i celach,
położenie celów pod recovered_metadata i niezmienione SHA źródeł po kopii.
Każdy cel otrzymał osobny katalog. Istniejący plik dopuszczony wyłącznie przy
identycznym rozmiarze i SHA; kopiowanie bez overwrite.

Nowe kopie: `C:/Users/tuszy/Documents/game_predictor_vision_data/recovered_metadata`.
Każda ścieżka ma postać `<katalog kopii z tabeli>/manual-image-selection-output-v1.json`.

Pełny manifest dziewięciu plików z absolutnymi sourcePath/copyPath/originalPath,
deletedAt, bytes, SHA-256 oraz każdym trafieniem nazwy i obiema sumami obrazów:
`C:/Users/tuszy/Documents/game_predicotr/artifacts/vision-lab/t03i-verify-run1.stdout.json`.
Wszystkie pola tożsamości i statystyki dziewięciu rekordów są identyczne
w preview, copy i świeżym verify. Kolejność kluczy serializacji JSON jest
nieistotna i może się różnić. Łączny rozmiar dziewięciu kopii: 737005 B.

Trwałą, bajtowo identyczną kopię manifestu zapisano obok odzyskanych plików:
`C:/Users/tuszy/Documents/game_predictor_vision_data/recovered_metadata/recovery-manifest-20260927.json`.
Rozmiar 74899 B, SHA-256
`954cadcfc97e71cf8636a0b0d6f3dafaa72192c299ff79a0b84d9412e71f38a2`.
Kopia bez overwrite, kontrola położenia i reparse points PASS (proces 26588).
Kolejny niezależny proces odczytowy zweryfikował SHA/JSON manifestu oraz SHA
wszystkich dziewięciu wskazanych kopii i zachowanych źródeł. Oba kroki miały
limit 60 s i zakończyły się bez timeoutu.

## Inwentarz kopii

Dla ośmiu pierwszych wpisów źródło to
`C:/$Recycle.Bin/S-1-5-21-102869703-676133570-4043641020-1001/<ID>.json`.
Pierwotna lokalizacja to
`C:/Users/tuszy/Documents/game_predictor_traning_set/<gra>/manual-image-selection-output-v1.json`.
Gra i ID w tabeli jednoznacznie rozwijają obie ścieżki; manifest podaje je w całości.

| Katalog kopii / ID | Gra | Bajty | Usunięcie | SHA-256 źródła i kopii |
| --- | --- | ---: | --- | --- |
| `$R1YFEW0` | blazing | 2882 | 2026-09-27 08:46:51 | `a2b213277159a4d117440590e110d775edf9816d2dd3b4bbcdbf7a978dabd822` |
| `$R2STL4J` | reels | 8799 | 2026-09-27 09:37:52 | `0a043ecda053ca8feacc26e9f8ab37848c23e746388d0ad20dd08f99582c8416` |
| `$RGTN4OD` | blazing | 370 | 2026-09-27 08:44:06 | `734d352364501c95fce8c64c3b5b1f7f2092af52ec02260865f533adcab184b4` |
| `$RI7UFEF` | gang | 5313 | 2026-09-27 09:00:14 | `7a616999e35d4a8763bb02438af0c5821e68e99eb13bdc5db83495417b119f7f` |
| `$RMXYGMP` | blazing | 5297 | 2026-09-27 08:43:09 | `3c44504836b3b4d1cad0741c886e2cca82a35e60283b5d1205e7bb03f194e8d1` |
| `$RQJTR82` | blazing | 370 | 2026-09-27 08:46:00 | `1141d40c5529e4e778d1d91de0cbdd79bd2f4f7d573c2ffa82adccae7c58fcd7` |
| `$RR02T5G` | gang | 4969 | 2026-09-27 08:56:36 | `84bb0aed18a37fcb6ef8195509c905f46629210348479d4584ce883e33e455c9` |
| `$RTPGMOE` | reels | 6741 | 2026-09-27 10:10:21 | `da4ff9cdd65a06b1519119fed99c3567021b45e05a0e2178bf163e93001ffed3` |
| `$RSDYTF7-477054-453753` | 777 | 702264 | 2026-09-25 09:13:04 | `409f448b12a54ddfbf07527ee25c9a3655aaa71f8bebc8dc06ba3c9ff983d4fd` |

Dziewiąte źródło:
`D:/$RECYCLE.BIN/$RSDYTF7/477054- 453753/manual-image-selection-output-v1.json`.
Pierwotna lokalizacja:
`D:/777/477054- 453753/manual-image-selection-output-v1.json`.
Data usunięcia pochodzi z nadrzędnego usuniętego katalogu `777`.

## Zawartość i pokrycie

Wszystkie pliki mają schemaVersion 2. Siedem zawiera pozycje, dwa są poprawnymi
pustymi eksportami Blazing. Osiem eksportów ma selectionComplete=false; tylko
777 ma true. Flaga nie stanowi weryfikacji filmu ani poprawności geometrii.

| ID | sourceDirectoryName | Pozycje | Zakres metadanych | Dopasowania do nowych JPG |
| --- | --- | ---: | --- | ---: |
| `$R1YFEW0` | `blazing 311400` | 9 | 310969–311049 | 9 |
| `$R2STL4J` | `reels 57500` | 31 | 57088–57366 | 31 |
| `$RGTN4OD` | `blazing 311400` | 0 | brak | 0 |
| `$RI7UFEF` | `GANG476500` | 18 | 476002–476163 | 18 |
| `$RMXYGMP` | `blazing 77600` | 18 | 77626–77787 | 18 |
| `$RQJTR82` | `blazing 311400` | 0 | brak | 0 |
| `$RR02T5G` | `GANG 27500` | 17 | 26785–26937 | 17 |
| `$RTPGMOE` | `reels 359400` | 23 | 359686–359892 | 23 |
| `$RSDYTF7-477054-453753` | `477054 - 453753` | 2590 | 453745–477054 | 5 |

Łącznie odzyskane JSON pasują nazwami outputName do **121 unikalnych z 473 JPG**,
bez duplikowania pokrycia. **0/121** ma imageChecksum identyczny z bieżącym JPG.
Zgodność nazw jest przesłanką pochodzenia, nie zgodnością pikseli. Różnica SHA
jest zgodna z deklarowanym późniejszym przycięciem, lecz sama nie dowodzi tej
transformacji. Nie przeniesiono geometrii ani zgód na nowe piksele.

| Gra | Nowe JPG | Nazwy pokryte odzyskiem | Niepokryte odzyskiem | SHA zgodne |
| --- | ---: | ---: | ---: | ---: |
| 777 | 32 | 5 | 27 | 0 |
| Blazing | 27 | 27 | 0 | 0 |
| Gang | 35 | 35 | 0 | 0 |
| Mumie | 225 | 0 | 225 | 0 |
| Reels | 54 | 54 | 0 | 0 |
| Treasure | 100 | 0 | 100 | 0 |

777: pięć trafień to seq_453745–453789, mapowane do klatek
`477200_021207.jpg`, `_021203.jpg`, `_021200.jpg`, `_021194.jpg`, `_021188.jpg`.
Pozostałe sześć bloków 777 (93853–93888, 149626–149670, 248176–248202,
302239–302283, 379243–379287, 412597–412641) pozostaje bez odzyskanego mapowania.

Treasure ma już wcześniej zachowany, nieodzyskiwany w T03i JSON dla 36 nazw
23590–23913 (`tresure23600`); opisuje go `artifacts/vision-lab/t03-source-map-readonly-report.md`.
Łączne znane pokrycie nazw z tamtym dowodem wynosi 157/473; pozostałe 316 nazw
to 27 zdjęć 777, 225 Mumii i 64 Treasure 429661–430236. Wcześniejszy Treasure
również nie miał zgodnych SHA aktualnych cropów. Nie ponawiamy pytania o
ustalone konserwatywne grupowanie zakresu 23590–23913 z dawnym tresure23600.

Odzysk dowodzi istnienia eksportów i konkretnych powiązań nazw z sourceDirectoryName,
ale nie potwierdza, czy różne foldery są niezależnymi filmami. Nowe metadane
uszczegóławiają wcześniejsze kandydatury Blazing/Gang/Reels; relacje do starych
źródeł oraz wspólne nagrania wymagają osobnego ustalenia. Nie nadano verified=true.
Dotychczasowe 180 siatek pozostaje zachowane; odzysk nie wymaga ich rysowania od nowa.

## Weryfikacja i ograniczenia

Helper operacyjny: `artifacts/vision-lab/t03i-recover-metadata.ps1`.
Wszystkie trzy ukryte procesy miały limit 60 s, exit 0, pusty stderr i czas około 5 s:
preview PID 3484, copy PID 20600, niezależny nowy proces verify PID 26720.
Logi: `artifacts/vision-lab/t03i-{preview,copy,verify}-run1.stdout.json` i
odpowiadające `.stderr.log`. Nie wystąpił timeout. Skrypt pozostawia źródła w Koszu.

Stan laboratorium przed/po każdej fazie: rewizja 260, SHA-256
`ad7c3d8248d303696e701819d705e949be9df094c3e1c2e74e317e7ef8456f17` pliku
`C:/Users/tuszy/Documents/game_predictor_vision_data/annotations/0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2/state.json`.

Nie wykonano restore, odzysku zdjęć/filmów, szerokiego skanu dodatkowych danych,
zmian snapshotów/anotacji/kwalifikacji/rodzin/splitu, treningu, usług lub restartu
OS. Testy aplikacji/lint/typecheck nie dotyczą operacji; kod produkcyjny bez zmian.
Kryteria kopii, nowego procesu, zachowania źródeł i jawnego rozróżnienia dowodów
spełnione. Niezależny audyt potwierdził dziewięć kopii, manifest, pokrycie nazw,
brak zgodnych SHA obrazów, dziewięć oryginalnych ścieżek/dat z plików $I oraz
oba niezmienione magazyny anotacji. Wszystkie dziewięć dat zgadza się z UTC;
opis surowych wartości Shell nie udaje czasu lokalnego. Osobny commit
i pełny hash zapisuje Outcome T03i w TASK-0668. T03 pozostaje
blocked na pozostałych bramkach danych, a rodziny nie zostały automatycznie zatwierdzone.
