# T03 — mapa dowodów rodzin i dry-run podziału, 2026-09-27

Uwaga chronologiczna: analiza i dry-run poniżej opisują rewizję 260.
Późniejszy autoryzowany zapis siedmiu rodzin unresolved opisuje końcowa sekcja
„Operacja: utrwalenie siedmiu rodzin unresolved”; bieżąca rewizja po niej to 267.

Wykonawca gpt-6-sol / medium; wynik do niezależnego audytu gpt-6-astra / medium.
Bez rzeczywistego apply rodzin, freeze, treningu, zmian kodu produkcyjnego lub usług.

## Wynik i artefakty

Opracowano mapę wszystkich 1466 źródeł (993 stare + 473 nowe) oraz rzeczywistej
kohorty 63 zaakceptowanych zdjęć / 180 pełnych ręcznych siatek. Odczytano
365 JSON: 345 dla 777 (344 w wskazanym usuniętym katalogu i 1 odzyskana kopia),
11 Mumii, 4 Blazing, 2 Gang, 2 Reels, 1 Treasure. Analiza dotyczy JSON i katalogu
laboratorium, bez hashowania obrazów/filmów w Koszu i bez ponownego szerokiego
szukania eksportu Treasure. `Catalog` zweryfikował zarządzane obrazy snapshotu.

Trzy rodzaje ustaleń pozostają odrębne: przypisanie do katalogu/zakresu,
zgodność bajtów obrazu i niezależność nagrań. Zapisane deklaracje operatora
rozstrzygają katalogi Treasure. Brak drugiego JSON nie unieważnia tej deklaracji.
Żadnego kandydata z nazwy nie awansowano do `provenance=verified`.

Artefakty pod `C:/Users/tuszy/Documents/game_predicotr/artifacts/vision-lab/`:

- `t03-family-evidence-run2.stdout.json` — pełna mapa każdego source_id/filename/SHA,
  status kohorty, grupa proponowana, uzasadnienie i wszystkie pasujące dowody
  (ścieżka metadanych, nazwa, checksum, action, imagePath i zakres); SHA/rozmiar
  każdego JSON, 121 ogólnych propozycji unresolved oraz oba przebiegi dry-run.
- `t03-partial-family-requests-proposed.json` — siedem konkretnych requestów
  do audytu i ewentualnego późniejszego apply, zawsze `unresolved`; CAS 260–266,
  bez zapisu. Po zmianie stanu wymagają ponownego preview, nie ręcznego obchodzenia CAS.
- `t03-split-dryrun-requests.json` — dokładne żądania diagnostyczne podziału,
  nie zatwierdzony protokół badania i nie komenda do wykonania na realnym store.
- `t03-family-evidence-dryrun.py` — helper odczytowy. Używa istniejących
  FamilyRequest/StoredFamily/SplitRequest, build_components i freeze_splits.
  Kopia AnnotationState jest wyłącznie w pamięci; nie otwiera AnnotationStore.

## Pokrycie dowodów

| Gra | Wszystkie źródła | Nowe | Akceptowane | Nowe nazwy w JSON | Nowe SHA zgodne z rekordem JSON |
| --- | ---: | ---: | ---: | ---: | ---: |
| 777 | 272 | 32 | 11 | 7 | 0 |
| Blazing | 126 | 27 | 10 | 27 | 0 |
| Gang | 195 | 35 | 11 | 35 | 0 |
| Mumie | 350 | 225 | 11 | 32 | 0 |
| Reels | 280 | 54 | 10 | 54 | 0 |
| Treasure | 243 | 100 | 10 | 36 | 0 |

Zero SHA w tabeli dotyczy pól checksum pasującego rekordu metadanych, a nie
wszystkich istniejących kopii na dysku. Nie jest dowodem różnych nagrań.
Operator przycinał obrazy; nazwa i imagePath mogą być dowodem pochodzenia,
ale bez transformacji/crop-output SHA nie dowodzą identyczności aktualnych pikseli.
Metadane napraw i historyczne decyzje mogą opisywać różne wersje. Każdy rekord
ma w pełnej mapie własne action i źródło; nie utożsamiamy go z bieżącą zgodą labu.

### Treasure — oba zakresy mają deklarację

- 36 nowych seq_23590–23913: operator wskazał `D:/tresure zd/tresure23600`.
  JSON selekcji wzmacnia mapowanie nazw. Konserwatywnie razem z 9 dawnymi
  źródłami tresure23600 (2 zaakceptowane), łącznie 45 źródeł.
- 64 nowe seq_429661–430236: operator wskazał `D:/tresure zd/tresure427100`.
  `439` było jawnie skorygowaną literówką; zakres ma 38 nazw 429 i 26 nazw 430.
  Konserwatywnie razem z 10 dawnymi źródłami tresure427100, łącznie 74.
  Żadne z tych 74 zdjęć nie należy do obecnej zaakceptowanej kohorty.

Oba katalogi istnieją według kontroli koordynatora. Nazwy starych wpisów są
pochodzeniem importu, nie samodzielnym dowodem niezależnego filmu. Zapis
unresolved uczciwie utrwala deklarację i powiązania, pozostawiając bramkę
niezależności otwartą. Nie trzeba ponownie żądać JSON ani wskazania tych katalogów.

### Mumie — deklarowany katalog i konkretne zakresy

Operator wskazał `C:/Users/tuszy/Documents/mumie wybrane`. Odczyt 11 JSON
potwierdził format v1 `decisions` (w tym action=accepted, outputName,
imageChecksumSha256, imagePath), zamiast zakładanego v2 `items`.
Nowe 32 nazwy z JSON: 5 w `1 - 23175` (sourceDirectoryName `mumie od1`),
7 w `76555 - 103221` (`mumie 76500`), 20 w `156538 - 182853` (`mumie 156200`).

Wcześniejszy kontrolowany odczyt koordynatora źródeł wykazał 182/225 nazw
w 7 katalogach i 12 identycznych plików: 5 w `1 - 23175 cut` oraz 7 w
`76555 - 103221 cut`. To wynik porównania plików, odrębny od zerowego wyniku
porównania checksum metadanych powyżej; nie powtarzano skanu 60811 JPG.
43 nazwy seq_379666–380052 nie zostały znalezione w tamtym odczycie.
Mapowanie tych 43 do zakresu 379549–391419 jest słabszą przesłanką zakresową,
nie potwierdzoną kopią pliku. Wspólne traktowanie obu nowych bloków
379549–380052 i 380404–381573 jest konserwatywne; przerwa nie tworzy niezależnych filmów.

Stare zaakceptowane Mumie rozkładają się na: 6 w zakresie 1–23175,
2 w 76555–103221 oraz 3 w 129718–156537 (145936–145971). Ostatni zakres
ma istniejący katalog i cut, ale nie pasujący JSON w tym odczycie; pozostaje
kandydatem unresolved. Nie jest częścią siedmiu ograniczonych requestów.

### Pozostałe gry i 777

Odzyskane metadane konkretyzują wszystkie nowe Blazing (`blazing 77600`,
`blazing 311400`), Gang (`GANG 27500`, `GANG476500`) i Reels (`reels 57500`,
`reels 359400`). Konserwatywne powiązania z odpowiadającymi starymi kandydatami
są w pełnej mapie. Różne nazwy katalogów nadal nie dowodzą niezależności filmów.

JSON 777 (crop-output, repair, filled-gaps i ich zapisane części) rozszerzył
dokładne trafienia nowych nazw z 5 do 7: pięć seq_453745–453789 mapuje się
do `477054 - 453753`; seq_93853–93861 do `70363 - 93861`,
seq_412597–412605 do `412605 - 387693`. Rekord cropu 93853 ma result=null,
więc samo jego istnienie nie dowodzi zakończonego cropu. Pozostałych 25 nowych
nazw nie potwierdziły odczytane metadane. Są jawnie unresolved w pełnej mapie.
W szczególności nie rozszerzamy pojedynczej granicznej pozycji automatycznie
na resztę sąsiedniego bloku. Stare nazwy/cuty nie stają się verified przez normalizację.

## Siedem bezpiecznie ograniczonych propozycji zapisu dowodów

Wszystkie są `provenance=unresolved`, `checksum_reviewed=true`,
`similarity_reviewed=false`. Kontrola checksum dotyczy pełnego zweryfikowanego
katalogu i grafu exact duplicates, nie oceny podobieństwa ani niezależności.
Evidence/declaration oddzielają deklarację operatora od wniosku zakresowego.
Następujące liczności uwzględniają stare wpisy i wszystkie nowe wystąpienia:

| family_id | Wszystkie | Nowe | Stare | Akceptowane |
| --- | ---: | ---: | ---: | ---: |
| mumie:123175 | 66 | 5 | 61 | 6 |
| mumie:76555103221 | 38 | 7 | 31 | 2 |
| mumie:156538182853 | 20 | 20 | 0 | 0 |
| mumie:321832346680 | 7 | 7 | 0 | 0 |
| mumie:379549391419 | 186 | 186 | 0 | 0 |
| treasure:tresure23600 | 45 | 36 | 9 | 2 |
| treasure:tresure427100 | 74 | 64 | 10 | 0 |

Razem 436 źródeł, w tym 325 nowych i 111 starych, 10 zaakceptowanych.
Requesty zachowują wszystkie wystąpienia i nie kopiują zatwierdzeń. Same
grupy nie stanowią zgody na trening. Apply wymaga osobnego audytu konkretnego
pliku i świeżej kontroli stanu; w tej pracy nie wykonano żadnego zapisu rodzin.
121 szerszych propozycji w pełnej mapie służy diagnostyce, nie zbiorczemu apply.

## Rzeczywisty dry-run istniejącego backendu

`freeze_splits` wywołano na oryginalnym stanie oraz kopii w pamięci z
konserwatywnymi, wyłącznie unresolved linkami. Kohorta dokładnie 63 source_id,
pełny graf wszystkich 1466 źródeł, exact SHA także poza kohortą. Po linkach
powstają 144 komponenty. Żadnych źródeł nie usunięto z grafu.

Wejścia diagnostyczne: purpose=geometry, conditional unseen `gang zd`, seed=0.
Gang pozostaje wcześniejszym kandydatem, nie nową zaakceptowaną decyzją.
Wariant A ma pusty measurement; wariant B jednego rzeczywistego zaakceptowanego
Blazing. Oba warianty na obu stanach zwróciły rzeczywisty backend error
`VERIFIED_MEASUREMENT_SOURCES_REQUIRED`. Nie zapisano sztucznych trudności.

Analiza bramek przed tym błędem:

- Oryginalny stan: wszystkie 63 zdjęcia wykluczone jako
  `FAMILY_PROVENANCE_UNRESOLVED`, 0 eligible.
- Po pamięciowych linkach: 52 jako `FAMILY_PROVENANCE_UNRESOLVED`,
  11 jako `COMPARISON_OR_777_PROVENANCE_UNRESOLVED`, 0 eligible.
- Błąd z niepustym wariantem B dowodzi, że samo dodanie ID measurement nie
  usuwa blokady; wskazane źródło nadal nie spełnia bramki verified rodziny.

### Konkretna blokada 777 obecnego kontraktu

| Grupa kandydująca | Wszystkie źródła | Wybrane i kwalifikowane | Pozostałe bez kwalifikacji |
| --- | ---: | ---: | ---: |
| 1–19809 cut | 10 | 4 | 6 |
| 117829–128268 cut | 10 | 3 | 7 |
| 128269–149634 cut | 10 | 4 | 6 |

Są 3 grupy, 30 źródeł, 11 kwalifikowanych targetów i 19 niekwalifikowanych
członków. Bieżący kod sprawdza rolę/kwalifikację na całym komponencie,
więc nawet przyszłe verified rodziny nie wystarczą. Ograniczenie kohorty
nie usuwa pozostałych członków z grafu. Nie można nadać kwalifikacji 19 aliasom
bez ich wymaganych pełnych geometrii i akceptacji. Nie skopiowano na nie zgód.
Zmiana tej polityki wymaga osobnej decyzji/kontraktu i audytu; ta praca jej nie robi.

### Pozostałe minimalne bramki podziału

Po rozstrzygnięciu powyższych kwestii backend wymaga niepustego measurement
z kwalifikowanej kohorty, poza unseen; jednej gry i jawnej trudności na całym
komponencie oraz co najmniej dwóch niezależnych grup w każdym stratum gra/trudność.
Ponadto musi pozostać grupa unseen i co najmniej 3 grupy development, z których
dwie przechodzą do validation/final_test, oraz pokrycie topologii unseen w treningu.
To wymagania kodu; nie twierdzimy, że późniejsze błędy zostały wywołane po obejściu
wcześniejszych bramek. Przypisanie gry niewidzianej, konkretnych grup pomiarowych
i trudności wymaga zamkniętej mapy nagrań, nie kolejnego ogólnego pytania o JSON.

## Integralność, weryfikacja i granice

Nowy store pozostał w rewizji 260, bez rodzin i splitu. SHA przed i po:
`ad7c3d8248d303696e701819d705e949be9df094c3e1c2e74e317e7ef8456f17`.
Ścieżka:
`C:/Users/tuszy/Documents/game_predictor_vision_data/annotations/0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2/state.json`.
Helper zweryfikował pełny Catalog, odczyt checksummed payloadu, 1466/63/180
i brak zmiany SHA na końcu. Przebiegi run1 PID31396 i finalny run2 PID17668
exit0, stderr0, ukryte okna, limity60s. Finalny przebieg około9s.
Pierwsza komenda inspekcji PowerShell miała błąd składni i nie uruchomiła odczytu;
poprawiona ograniczona inspekcja zakończyła się poprawnie, bez mutacji.

Nie wykonano apply, backupu/restore, usuwania obrazów, nowych akceptacji,
freeze/treningu, nowych kosztów, startu usług, zmiany produkcji, commitów ani push.
Weryfikacja aplikacji i build nie dotyczą odczytowej analizy. Odczyt z nowego
procesu potwierdził stan, restart OS nie był testem tego zadania.
Następny konkretny krok dla koordynatora: audyt siedmiu ograniczonych requestów
i ewentualny jawny zapis dowodów unresolved; osobne rozstrzygnięcie polityki 777
i protokołu measurement przed freeze. Rodziny nie są tu automatycznie verified.

## Konkretne odblokowanie po osobnej korekcie T03j

Ta sekcja jest analizą wariantów, nie zmianą protokołu ani decyzją o podziale.
Root przekazał akceptację wąskiej korekty 777 T03j; wynik dry-run powyżej
odnosi się do wcześniejszego kodu. T03j nie rozstrzyga provenance lub measurement.

Obecna kohorta ma 28 kandydujących grup zawierających akceptacje:

| Gra | Konkretne kandydatury grup (zaakceptowane zdjęcia) |
| --- | --- |
| 777 | 1–19809 (4), 117829–128268 (3), 128269–149634 (4) |
| Blazing | BLAZING425200 (5), BLAZING451200 (3), BLAZING476100 (2) |
| Gang | GANG157300 (3), GANG183500 (4), GANG209500 (3), GANG325700 (1) |
| Mumie | 1–23175 (6), 76555–103221 (2), 129718–156537 (3) |
| Reels | reels_145600 (2), reels_218400 (1), reels_245200 (1), reels_27600 (1), REELS450100 (1), REELS451200 (2), REELS471200 (2) |
| Treasure | tresure121900 (1), tresure147100 (1), tresure171100 (2), tresure183100 (1), tresure210100 (1), tresure23600 (2), tresure237400 (1), tresure319200 (1) |

Dla dotychczasowego protokołu potrzeba konkretnie: potwierdzenia, które
z tych kandydatur są tym samym nagraniem (scalić), a które stanowią odrębne
nagrania (uzasadnione verified wszystkich członków całych komponentów);
ostatecznego wyboru unseen; wskazania grup measurement i ich trudności.
Przykładową parą do oceny pomiarowej są dwa całe komponenty BLAZING425200
i BLAZING451200, ale nie przypisano im jednakowej trudności ani niezależności.
Difficulty musi obejmować także ich członków poza kohortą. To przykład
konkretnego brakującego rozstrzygnięcia, nie zapisane żądanie badania.
Jeśli pomiar ma obejmować wszystkie pięć gier poza unseen, potrzeba co najmniej
10 niezależnych grup pomiarowych (po dwie per gra i wybrana trudność),
niezależnie od trzech grup pozostawionych na development/validation/final_test.
Backend dopuszcza węższy zakres measurement, lecz nie wolno po cichu redukować
uzgodnionego pomiaru do jednej gry. Nominalne 28 kandydatów nie oznacza 28
potwierdzonych niezależnych grup; bieżące deklaracje nie wystarczają do takiego twierdzenia.

### Wariant do jednej odrębnej decyzji: pilot z całymi grami

Praktycznym wariantem, jeśli operator nie ma pełnej mapy niezależnych nagrań,
jest jawny **pilot geometrii 5 × 3 z podziałem całymi grami, bez pomiaru czasu**.
Nie wymaga udawania niezależności folderów w obrębie gry: wszystkie znane
i potencjalnie powiązane zdjęcia danej gry pozostają w jednym zbiorze.
Wszystkie istniejące powiązania i exact SHA nadal uczestniczą w kontroli;
wykryte powiązanie pomiędzy grami musi zatrzymać podział lub wymusić wspólny zbiór.
Brak wspólnego SHA sam w sobie nie dowodzi niezależności nagrań.

Nowy odczyt potwierdził dokładnie po 30 pełnych human targetów 5 × 3 na każdą
z sześciu gier. Nie ma targetów 3 × 3 ani exact SHA wspólnych między grami
w pełnym katalogu 1466 źródeł. Liczności możliwego wariantu, bez wyboru nazw:

| Rola | Liczba całych gier | Pełne siatki 5 × 3 |
| --- | ---: | ---: |
| Development/train | 3 | 90 |
| Validation | 1 | 30 |
| Final test | 1 | 30 |
| Unseen game | 1 | 30 |

Zdjęć jest 63: 777 11, Blazing 10, Gang 11, Mumie 11, Reels 10, Treasure 10;
liczba zdjęć na rolę zależy od późniejszego jawnego wyboru gier, liczba siatek
90/30/30/30 pozostaje stała. Żadnej gry nie wybrano tu do roli.
Validation/test/unseen to w tym wariancie trzy odrębne gry, więc wynik mierzy
mały pilot przenoszenia geometrii między grami, nie skuteczność na niezależnych
nagraniach tej samej gry. Nie ocenia oszczędności czasu i nie uzasadnia celu 30%.
90 siatek treningowych to mały zbiór; wynik ma być pilotażowy, bez obietnicy
jakości produkcyjnej i bez oceny 3 × 3.

Wariant wymaga jednej jawnej decyzji zmieniającej protokół, nowej wersjonowanej
polityki splitu i testów zamiast oznaczania obecnych rodzin jako verified.
Aktualny freeze wymaga measurement i zweryfikowanych rodzin, więc nie da się
go uruchomić tym wariantem bez uzgodnionej zmiany kontraktu. Nie wdrożono tego
wariantu, nie zastąpiono nim aktualnego planu i nie wybrano podziału za użytkownika.

Dowód odczytu liczności: `artifacts/vision-lab/t03-whole-game-pilot-counts.stdout.json`,
PID33356, exit0, stderr0, limit60s, około7s; rev260/SHA bez zmian.

## Operacja: utrwalenie siedmiu rodzin unresolved

Po końcowym audycie siedmiu requestów PASS bez P0–P2 i sygnale koordynatora
o zamrożeniu kodu T03j wykonano dokładnie
`artifacts/vision-lab/t03-partial-family-requests-proposed.json`.
Nie zmieniono typed payloadów, aktora, request_id, source_ids lub statusów.
Fresh preview: rewizja260, przypięty SHA ad7c3d82…, zero rodzin, split null.
Kontrola systemowa: port8102 bez listenera i zero pasujących writerów.

Istniejący `AnnotationStore.backup` zapisał zweryfikowaną kopię:
`C:/Users/tuszy/Documents/game_predictor_vision_data/annotations/0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2/backups/f7748d2aca79fe4a1f39fe8241a897f417e7cf357d64a940eb562195f9c7d9b1.json`.
Jej SHA-256 jest identyczny ze stanem wejściowym:
`ad7c3d8248d303696e701819d705e949be9df094c3e1c2e74e317e7ef8456f17`.
Backup ID/payload digest:
`f7748d2aca79fe4a1f39fe8241a897f417e7cf357d64a940eb562195f9c7d9b1`.

Wykonano **siedem osobnych atomowych mutacji**, CAS260–266, kolejne rewizje
261–267; nie jest to jeden atomowy batch. Każdy krok potwierdzono odczytem
i sprawdzeniem dokładnego prefiksu requestów, eventów, receipts i całego payloadu.
Wznowienie helpera dopuszcza wyłącznie taki zgodny prefiks i ten sam backup;
obcy zapis lub inny request zatrzymuje operację. Nie generuje nowych request_id.
Nie wystąpiło przerwanie ani częściowy błąd podczas tej operacji.

Stan końcowy: rewizja267, 436 wpisów mapy families wskazujących siedem family_id,
wszystkie `provenance=unresolved`; history267 i receipts267 (dokładnie +7).
Cały pozostały payload jest identyczny z backupem: 180 anotacji, 63 photo reviews,
11 kwalifikacji geometrii, 196 timingów, wcześniejsza historia i receipts.
Nie zmieniono splitu, split_stale, ról źródeł ani żadnych akceptacji.

Nowy proces replay przesłał dokładnie te same siedem requestów; każda odpowiedź
zwróciła rewizję267, a SHA całego pliku pozostał identyczny. Kolejny osobny proces
read-only ponownie sprawdził Catalog/read_checked, backup i dokładny payload.
Stary store nadal ma SHA22f452d0e976a9997909ece2cf9bede0073f1241574f5880fa7b3ebdbb0e0586.

SHA-256 końcowego `state.json`:
`f4fabe1790b6922ce297ab61e118371aa3eb91a509606c478d67a7a2b75726ae`.
Payload digest:
`9a24d4d49398759467c7447d9c44226afd1e3f1435335a205ecae4bbe9b46220`.
Helper operacyjny: `artifacts/vision-lab/t03-apply-partial-families.py`.

### Trwałe kopie mapy i żądań

Trzy pliki zapisano create-only (bez overwrite) pod
`C:/Users/tuszy/Documents/game_predictor_vision_data/reports/t03-source-mapping-20260927`.
Nowy proces potwierdził JSON, rozmiary i identyczne SHA kopii oraz plików źródłowych:

| Plik | Bajty | SHA-256 |
| --- | ---: | --- |
| t03-partial-family-requests-proposed.json | 39941 | `cd132445e6c9cb1a84e6aabfdee28e17d352ef6a391b687622a829da277bd2fb` |
| t03-family-evidence-run2.stdout.json | 1741287 | `e12748c8a2971f905f727f72447ba3067fdf3022c5652b5b105e743c5896cd52` |
| t03-split-dryrun-requests.json | 10120 | `cc788fb0853c86cb355de34419bfb2ae5769e2968017e9e80f4fdfdaf83ca9db` |

Nazwy historycznych plików i zapis statusu proposed wewnątrz requestów zachowano
bajtowo; dowodem ich późniejszego wykonania są receipts/eventy i ta sekcja.
Pełna mapa jest historycznym dowodem rewizji260, nie aktualnym eksportem stanu267.

### Logi i zakres

Osobne logi pod `artifacts/vision-lab/`, wszystkie exit0, stderr0, limit60s,
ukryte procesy bez timeoutu:

| Krok | PID | Prefiks logów stdout.json / stderr.log |
| --- | ---: | --- |
| Fresh preview | 25468 | t03-partial-families-preview-run1 |
| Backup, metadata copies, siedem apply | 29928 | t03-partial-families-apply-run1 |
| Nowy proces identycznego replay | 31880 | t03-partial-families-replay-run1 |
| Nowy proces read-only verify | 32128 | t03-partial-families-verify-run1 |

Bez dalszego freeze, treningu, usług, verified provenance, symbol approvals,
zmian kodu produkcyjnego, cleanupu lub commitów wykonawcy. Operacja utrwala
dotychczasowe dowody i deklaracje; nie rozstrzyga niezależności nagrań ani
podziału badawczego. Końcowy audyt operacji Astra medium PASS bez P0–P2:
niezależna rekonstrukcja całego payloadu z backupu i siedmiu exact requestów,
kontrola obu store, receipts, replay oraz trzech trwałych kopii metadanych.
Commit prowadzi koordynator.

## Aktualny dry-run T03j v2 na rewizji267

Po zapisie rodzin wykonano nowy proces odczytowy PID17844, exit0, limit60s.
`freeze_splits` wywołano na kopii aktualnego AnnotationState z jawnym
`geometry_policy='lab-geometry-cohort-777-targets-v2'`, purpose geometry
i dokładnie tą samą kohortą 63 zaakceptowanych zdjęć. Zachowano rzeczywiste
436 wpisów rodzin, wszystkie unresolved; niczego nie podmieniono na verified.

Dwa wcześniejsze warianty diagnostyczne (pusty measurement oraz pojedynczy
zaakceptowany kandydat Blazing) ponownie zwróciły rzeczywisty backend error
`VERIFIED_MEASUREMENT_SOURCES_REQUIRED`. Żądania mają expected_revision267;
Gang/seed0 pozostają diagnostycznym wejściem, nie zatwierdzeniem nowego protokołu.
Pełne żądania i wyniki: `artifacts/vision-lab/t03-v2-rev267-dryrun.stdout.json`;
odpowiadający stderr pusty.

Aktualny pełny graf ma 1017 komponentów. Różnica wobec wcześniejszych 144
jest oczekiwana: tamta symulacja zawierała 121 hipotetycznych rodzin unresolved,
a realnie zapisano tylko siedem odebranych grup. Wszystkie 63 targetowe źródła
nadal leżą w komponentach z brakującym albo unresolved provenance; liczba
eligible przy rzeczywistych decyzjach pozostaje 0. Korekta polityki 777
nie rozstrzyga tej odrębnej bramki ani wyboru grup pomiarowych i trudności.

Payload odczytany przed i po jest identyczny; SHA-256 stanu przed/po:
`f4fabe1790b6922ce297ab61e118371aa3eb91a509606c478d67a7a2b75726ae`.
Rewizja pozostała267, split null. Bez realnego mutate, freeze, training lub
wyboru nowego protokołu. Historyczny dry-run260 pozostawiono jako zapis wcześniejszej analizy.
