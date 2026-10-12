---
title: Kontrolowany pomiar selektora na 15000 JPEG
status: completed
last_updated: 2026-10-12
---

# TASK-0987 — pomiar 15000 JPEG przed i po optymalizacji

## Wynik i zakres

PASS pomiaru lokalnego. Ciepłe NAV ma p50 **95,08 ms**, p95 **106,66 ms**;
baseline miał odpowiednio **918,79 ms** i **979,36 ms**. Cel inżynierski
p50 poniżej500 ms został spełniony na tym fixture i sprzęcie. Nie jest to
gwarancja czasu dla dowolnego dysku ani zdjęć.

Pomiar objął dokładnie100 unikalnych operacji na każdą wersję:20 NAV,
20 accept i20 undo,20 skip i20 undo. Każda kategoria miała osobny proces
Node oraz oddzielnie mierzony open. Po100 operacjach następny proces
potwierdził100 zachowanych receiptów, rewizję100, zero decyzji po undo oraz
ponowienie `measure_nav_000` bez nowej rewizji. Oba ledgery nowego formatu
mają identyczne bajty; finalny ledger zachował wszystkie24 zmierzone
prefixy przed i po fazach. Wszystkie cztery niezmienne pliki inventory/baseline
zachowały SHA-256, rozmiar i mtime podczas kategorii operacji.

Każdy proces używał produkcyjnego singletonu WindowsCheckWorker. We wszystkich
trzech ciepłych kategoriach każdej wersji licznik spawnCount wynosił1 przed
i1 po: **zero dodatkowych spawnów**. Procesy były zamykane przez
ProjectStore.close i disposeNativeChecks. Nie używano fałszywego ProcessInspector.

## Proweniencja i warunki

- Baseline: pełne `apps/selector-desktop/src` z
  `c4181f7ddc8fca2518c2d9abc363ce3bcd307d5f`, źródło ZIP0.1.2.
- Finalny runtime pomiaru: pełne src z
  `c43434c28d49597407072f9636c7c07d1c3622b8`, po TASK-0985/0986.
  Pomiar używa src z Git, bez testowania opakowania ZIP. Finalny runtime
  paczki0.1.3 z `0b1ab3302df2119efb2519661e2f82b8bdf545df` ma identyczne
  src i rdzeń: pusty `git diff c43434c2 0b1ab330 -- apps/selector-desktop/src packages/manual-image-selection-core`.
- Kopie src zostały wyprowadzone z Git blobów, bez zgadywania źródeł starego
  builda. configuration.json zapisuje SHA każdego pliku i zbiorczy SHA drzewa.
  Potwierdzono brak diffu współdzielonego manual-image-selection-core pomiędzy
  tymi commitami. Obie wersje korzystały z tego samego zainstalowanego rdzenia.
- Windows11 Home,10.0.26300; AMD Ryzen7 170 with Radeon Graphics;
  16 procesorów logicznych, RAM33630056448 B; Node v24.21.0.
- Źródło, dwa niezależne projekty i wyniki są w kontrolowanym `.tmp` worktree
  na lokalnym dysku stałym `D:\`. Produkcyjne driveInfo musiało potwierdzić
  type3 i ready=true. Nie mierzono modelu dysku ani jego maksymalnej przepustowości.
- Jedno wspólne źródło:15000 poprawnych JPEG RGB8×8 po639 B, razem9585000 B,
  `photo1.jpg`–`photo15000.jpg`, stałe mtime. Naturalny porządek sprawdzono
  w obu inventory. Pillow rzeczywiście zdekodował fixture jako JPEG8×8 RGB.
  Zdjęcia są syntetyczne i identyczne; nie reprezentują kamer ani dużych JPEG.
- Przed i po przebiegu przeczytano wszystkie15000 oryginałów. Odrębny końcowy
  proces potwierdził identyczne SHA-256, rozmiary i dokładne mtimeMs.
  Nie użyto danych operatora i nie uruchamiano API/Admin.
- Baseline i current były wykonywane kolejno, bez równoległego builda/smoke.
  Cache systemu plików nie był czyszczony. „Cold” oznacza nowy proces Node
  i nowy worker, nie fizycznie zimny dysk.

## Czas operacji

Wartości w ms, percentyle nearest-rank. Undo po accept i po skip są oddzielne
zbiory20 próbek. Pomiar operacji obejmuje execute, trwały zapis i produkcyjne
kontrole; nie obejmuje kontrolera/IPC ani renderowania.

| Operacja | n na wersję | Baseline p50 / p95 | Current p50 / p95 |
|---|---:|---:|---:|
| NAV |20|918,79 /979,36|95,08 /106,66|
| Accept |20|976,16 /1024,35|124,49 /143,81|
| Undo po accept |20|948,67 /1039,96|104,10 /115,07|
| Skip |20|924,19 /1022,63|94,12 /100,81|
| Undo po skip |20|938,09 /1036,43|94,40 /102,24|

Tworzenie projektu było pojedynczym pomiarem: baseline10788,89 ms,
current21277,22 ms. Nowy create obejmuje także migrację inicjalnego stanu
do kompaktowego formatu; jego czas wzrósł. Pięć kolejnych cold open na wersję
miało p50/p95: baseline10591,47/11441,41 ms,
current10523,05/10637,15 ms. Końcowy retry starego receipt trwał
1,68 ms baseline i1,89 ms current. Koszt pełnego skanu/open pozostał widoczny.

## Etapy zapisu

Wartości p50/p95 w ms pomiędzy istniejącymi checkpointami `:before`/`:after`.
Nie sumują się do całego execute: walidacja, kontrole i inne prace leżą też
poza tymi parami. Callback pomiaru dodaje jedno stat journalu po prepare.
Etap state nowego formatu obejmuje dopisanie/fsync ledgerów i publikację head.

| Etap | NAV baseline / current | Accept+undo baseline / current | Skip+undo baseline / current |
|---|---|---|---|
| Prepare |124,18/145,22 →7,09/8,02|131,26/148,61 →6,88/8,13|128,80/157,67 →6,69/8,13|
| JPEG/removal |0,009/0,012 →0,007/0,108|4,64/25,45 →4,71/26,51|0,009/0,020 →0,007/0,010|
| State |83,31/100,00 →20,65/22,22|84,67/96,04 →20,14/24,02|82,41/102,26 →21,11/24,21|
| Manifest |12,00/13,49 →11,76/13,67|11,28/13,08 →11,08/14,03|10,83/13,96 →11,27/13,71|
| Backup |63,33/77,91 →6,01/6,78|67,66/81,17 →6,02/6,78|67,87/77,83 →6,20/7,16|
| Finalize |5,08/6,18 →4,74/5,69|5,16/6,77 →4,63/5,36|5,24/9,43 →4,64/5,39|

## Projekcja, preview i retencja

Poniższe czasy po100 operacjach mają20 próbek. Pełna projekcja kontrolera
używa rzeczywistego ProjectController.snapshot i zweryfikowanego SourceRegistry;
harness przyłącza wcześniej otwarty własny store przez prywatne pola native.
Nie uruchamia dialogów ani lifecycle aplikacji. Serializacja JSON jest osobnym
przybliżeniem kosztu danych, nie pomiarem transportu Electron IPC.

| Odczyt/projekcja | Baseline p50 / p95 ms | Current p50 / p95 ms |
|---|---:|---:|
| Projekcja store dla UI (baseline pełny snapshot) |14,95 /19,28|0,028 /0,041|
| Publiczny pełny snapshot |15,48 /21,50|13,84 /18,59|
| Rzeczywisty ProjectController.snapshot |16,37 /22,73|1,40 /4,34|
| JSON.stringify workspace |7,63 /10,97|8,91 /14,07|
| Zwykły readFile JPEG639 B |1,06 /1,30|1,09 /1,73|

Workspace JSON obu wersji ma3593323 B dla15000 metadanych. Preview oznacza
zwykły odczyt jednego małego JPEG; nie obejmuje protokołu aplikacji, kontroli
ścieżki, dekodowania ani renderowania UI. Publiczny snapshot nadal klonuje
pełny stan; jego koszt nie został wyeliminowany.

| Pliki projektu po100 operacjach | Baseline | Current |
|---|---:|---:|
| Primary oraz backup, każdy |1935386 B (pełny stan)|1132 B (head2)|
| Inventory, każda z dwóch kopii |w pełnym stanie|1912962 B|
| Baseline, każda z dwóch kopii |w pełnym stanie|624 B|
| Ledger, każda z dwóch kopii |brak osobnego ledgeru|119518 B|
| Łączne trwałe metadane |3870772 B|4068472 B|
| Największy przygotowany journal NAV |3835586 B|3394 B|
| Największy journal accept/undo |3853663 B|3967 B|
| Największy journal skip/undo |3870848 B|3671 B|

Pełna retencja zwiększa całkowity rozmiar metadanych. Optymalizacja dotyczy
bajtów przepisywanych na krok, nie usuwania historii. Pomiary i prefixy ledgeru
potwierdzają zachowanie zapisanej historii; inventory/baseline nie były
przepisywane w ciepłych fazach. RSS na końcu fazy skip wynosił baseline365268992 B,
current247324672 B; to odczyt końcowy, nie pomiar szczytu ani gwarancja pamięci.

Pozostają O(N) metadane źródła w odpowiedzi UI, O(D) pełny manifest oraz
O(N+R+D) pełna walidacja open i retencja w pamięci. Ten fixture ma co najwyżej
jedną bieżącą decyzję przed undo i100 receiptów. Nie mierzy kosztu tysięcy
potwierdzonych decyzji, utraty zasilania, odbioru na komputerze docelowym ani
końcowego audytu krzyżowego.

## Odtworzenie i dowody

Katalog roboczy: `D:\game_predicotr\worktrees\offline-photo-selector`.
Każdą fazę uruchamia się osobno z limitem120 s. Wewnętrzny worker ma limit110 s
z kontrolowanym zakończeniem drzewa procesów przez istniejący run-bounded.
Nowy przebieg wymaga nowej nazwy; prepare odmawia nadpisania istniejącego runRoot.

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 node apps/selector-desktop/scripts/measure-selector.mjs prepare final-20261012
# Każdy wpis poniżej wykonano osobno tą samą komendą, zamiast prepare:
# baseline-create, baseline-nav, baseline-accept, baseline-skip,
# baseline-reopen, baseline-projection,
# current-create, current-nav, current-accept, current-skip,
# current-reopen, current-projection, verify-source, summary
```

Wszystkie wymienione fazy zakończyły się PASS. Pierwszy baseline-create
w ograniczonym sandboxie zakończył się EPERM na realpath źródła, przed utworzeniem
projektu. Powtórzenie i wszystkie fazy produkcyjnych kontroli wykonano z zatwierdzonym
wyjściem poza sandbox; nie zmieniano zabezpieczeń aplikacji. Pierwsze wywołanie
ESLint z root nie znalazło konfiguracji. Poprawne wywołanie z katalogu desktop
przeszło; formatowanie obu nowych skryptów również przeszło.

Surowe wyniki, konfiguracja/SHA źródeł, pełny original-proof i zbiorczy
`summary.json` leżą w ignorowanym
`artifacts/selector-measurements/final-20261012/`. Źródła/fixture/projekty pozostały
w kontrolowanym `.tmp/selector-measurements/final-20261012/` dla weryfikacji;
harness nie wykonuje automatycznego kasowania. Finalny ZIP oraz pozostałe smoke
mają osobne dowody TASK-0987.
