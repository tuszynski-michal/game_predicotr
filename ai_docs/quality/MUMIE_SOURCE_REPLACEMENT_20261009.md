# Mumia — zatwierdzony manifest wymiany zdjęć (2026-10-09)

**Status operacji: częściowo wykonana — 55 zdjęć usunięto, 220 pozostało. Dalsze usuwanie wstrzymane po błędzie API drugiej partii.**

Gra: `Mumie` (`mumie`), ID `fea55cc1-ebf4-4cee-b3ab-a520017ed1be`.

Operator zatwierdził zakres po podglądzie: „Tak, ale zapisz które zdjęcia z zakresami usuwamy”. Zgoda dotyczy poniższych 275 zdjęć i wszystkich ich danych pochodnych, także poprawnych plansz oraz dwóch zatwierdzonych decyzji symboli. Nie jest zgodą na usuwanie kolejnych źródeł ani zatrzymywanie usług.

Pierwsza lista: 2026-10-09 16:48 UTC. Świeży podgląd: 2026-10-09T19:44:24.308551+00:00. Aktywne joby zakończone; wszystkie pięć podglądów bez blokad i ostrzeżeń.

## Przypięty zakres

- 275 unikalnych zdjęć i 275 rekordów źródłowych.
- 2475 numerów sekwencji w pełnych zakresach po dziewięć plansz.
- 2198 istniejących rozpoznanych plansz, 2198 pozycji review i 2198 manifestów renderowania.
- 32970 komórek symboli: 32968 pending i 2 approved.
- 281 rewizji geometrii źródeł.
- Bez zależnych kohort treningowych, modeli symboli, eksportów kohort ani wydań mobilnych.
- Oryginalne foldery użytkownika i staging uploadu nie są usuwane przez mechanizm czyszczenia.

260 zdjęć pochodzi z kolejki korekty siatki (277 pozycji), a 16 z oznaczenia częściowej widoczności. Jedno zdjęcie, `seq_69004-69012.jpg`, występuje na obu listach. `incomplete_lattice` nie dowodzi fizycznego ucięcia każdego zdjęcia; operator zdecydował przygotować poprawioną paczkę całego wskazanego zakresu.

Pełne identyfikatory źródeł, jobów i stare checksumy: [MUMIE_SOURCE_REPLACEMENT_20261009.csv](MUMIE_SOURCE_REPLACEMENT_20261009.csv). Zachować manifest po usunięciu starych danych.

## Wykonanie i odtworzenie

Usuwać wyłącznie przez istniejący workflow `board-source-cleanup-preview` / `board-sources`, z lokalną intencją administratora, świeżym tokenem i dokładnym potwierdzeniem. Pięć partii po 55 zdjęć (495 numerów) wynika z limitu API 500 numerów. Nie obchodzić blokad ani RLS. Zmiana zakresu lub pojawienie się zależności poza zatwierdzonym podglądem wymaga zatrzymania operacji.

Nowa paczka: dokładnie poniższe nazwy `seq_PIERWSZA-OSTATNIA.jpg`, bez zmiany numerów sekwencji; każde zdjęcie obejmuje wszystkie dziewięć całkowicie widocznych plansz. Usunięcie obejmuje również poprawne plansze ze źródła, więc muszą zostać odtworzone z nowej paczki. Import poprawionych zdjęć jest osobną operacją po ich przygotowaniu przez operatora.

## Lista zdjęć i zakresów

| Lp. | Zakres plansz | Nazwa zdjęcia | Folder źródłowy | Powód | Status |
|---:|---|---|---|---|---|
| 1 | 29593–29601 | `seq_29593-29601.jpg` | `24517 - 50112 cut` | częściowo widoczne symbole | usunięte — partia 1 |
| 2 | 29602–29610 | `seq_29602-29610.jpg` | `24517 - 50112 cut` | częściowo widoczne symbole | usunięte — partia 1 |
| 3 | 29611–29619 | `seq_29611-29619.jpg` | `24517 - 50112 cut` | częściowo widoczne symbole | usunięte — partia 1 |
| 4 | 29620–29628 | `seq_29620-29628.jpg` | `24517 - 50112 cut` | częściowo widoczne symbole | usunięte — partia 1 |
| 5 | 29629–29637 | `seq_29629-29637.jpg` | `24517 - 50112 cut` | częściowo widoczne symbole | usunięte — partia 1 |
| 6 | 50338–50346 | `seq_50338-50346.jpg` | `50320 - 76554 cut` | częściowo widoczne symbole | usunięte — partia 1 |
| 7 | 69004–69012 | `seq_69004-69012.jpg` | `50320 - 76554 cut` | korekta siatki, częściowo widoczne symbole | usunięte — partia 1 |
| 8 | 69013–69021 | `seq_69013-69021.jpg` | `50320 - 76554 cut` | korekta siatki | usunięte — partia 1 |
| 9 | 69022–69030 | `seq_69022-69030.jpg` | `50320 - 76554 cut` | korekta siatki | usunięte — partia 1 |
| 10 | 69031–69039 | `seq_69031-69039.jpg` | `50320 - 76554 cut` | korekta siatki | usunięte — partia 1 |
| 11 | 69040–69048 | `seq_69040-69048.jpg` | `50320 - 76554 cut` | korekta siatki | usunięte — partia 1 |
| 12 | 69049–69057 | `seq_69049-69057.jpg` | `50320 - 76554 cut` | korekta siatki | usunięte — partia 1 |
| 13 | 69058–69066 | `seq_69058-69066.jpg` | `50320 - 76554 cut` | korekta siatki | usunięte — partia 1 |
| 14 | 69067–69075 | `seq_69067-69075.jpg` | `50320 - 76554 cut` | korekta siatki | usunięte — partia 1 |
| 15 | 87787–87795 | `seq_87787-87795.jpg` | `76555 - 103221 cut` | korekta siatki | usunięte — partia 1 |
| 16 | 105220–105228 | `seq_105220-105228.jpg` | `103222 - 108252 cut` | korekta siatki | usunięte — partia 1 |
| 17 | 261487–261495 | `seq_261487-261495.jpg` | `249886 - 269460 cut` | korekta siatki | usunięte — partia 1 |
| 18 | 261496–261504 | `seq_261496-261504.jpg` | `249886 - 269460 cut` | korekta siatki | usunięte — partia 1 |
| 19 | 261541–261549 | `seq_261541-261549.jpg` | `249886 - 269460 cut` | korekta siatki | usunięte — partia 1 |
| 20 | 326791–326799 | `seq_326791-326799.jpg` | `321832- 346680 cut` | korekta siatki | usunięte — partia 1 |
| 21 | 326800–326808 | `seq_326800-326808.jpg` | `321832- 346680 cut` | korekta siatki | usunięte — partia 1 |
| 22 | 419932–419940 | `seq_419932-419940.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 23 | 419941–419949 | `seq_419941-419949.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 24 | 419950–419958 | `seq_419950-419958.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 25 | 419959–419967 | `seq_419959-419967.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 26 | 419968–419976 | `seq_419968-419976.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 27 | 419977–419985 | `seq_419977-419985.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 28 | 421102–421110 | `seq_421102-421110.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 29 | 421111–421119 | `seq_421111-421119.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 30 | 421120–421128 | `seq_421120-421128.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 31 | 421129–421137 | `seq_421129-421137.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 32 | 421165–421173 | `seq_421165-421173.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 33 | 421174–421182 | `seq_421174-421182.jpg` | `417664- 444276 cut` | częściowo widoczne symbole | usunięte — partia 1 |
| 34 | 421300–421308 | `seq_421300-421308.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 35 | 421381–421389 | `seq_421381-421389.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 36 | 421390–421398 | `seq_421390-421398.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 37 | 421399–421407 | `seq_421399-421407.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 38 | 421408–421416 | `seq_421408-421416.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 39 | 421417–421425 | `seq_421417-421425.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 40 | 422776–422784 | `seq_422776-422784.jpg` | `417664- 444276 cut` | częściowo widoczne symbole | usunięte — partia 1 |
| 41 | 422785–422793 | `seq_422785-422793.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 42 | 422794–422802 | `seq_422794-422802.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 43 | 422803–422811 | `seq_422803-422811.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 44 | 422812–422820 | `seq_422812-422820.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 45 | 422821–422829 | `seq_422821-422829.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 46 | 422830–422838 | `seq_422830-422838.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 47 | 422902–422910 | `seq_422902-422910.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 48 | 423352–423360 | `seq_423352-423360.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 49 | 423361–423369 | `seq_423361-423369.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 50 | 423370–423378 | `seq_423370-423378.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 51 | 424774–424782 | `seq_424774-424782.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 52 | 424783–424791 | `seq_424783-424791.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 53 | 424792–424800 | `seq_424792-424800.jpg` | `417664- 444276 cut` | częściowo widoczne symbole | usunięte — partia 1 |
| 54 | 428347–428355 | `seq_428347-428355.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 55 | 428356–428364 | `seq_428356-428364.jpg` | `417664- 444276 cut` | korekta siatki | usunięte — partia 1 |
| 56 | 428365–428373 | `seq_428365-428373.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 57 | 428374–428382 | `seq_428374-428382.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 58 | 428383–428391 | `seq_428383-428391.jpg` | `417664- 444276 cut` | częściowo widoczne symbole | pozostało |
| 59 | 428446–428454 | `seq_428446-428454.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 60 | 438868–438876 | `seq_438868-438876.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 61 | 438877–438885 | `seq_438877-438885.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 62 | 438886–438894 | `seq_438886-438894.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 63 | 438895–438903 | `seq_438895-438903.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 64 | 439012–439020 | `seq_439012-439020.jpg` | `417664- 444276 cut` | częściowo widoczne symbole | pozostało |
| 65 | 439021–439029 | `seq_439021-439029.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 66 | 439309–439317 | `seq_439309-439317.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 67 | 439984–439992 | `seq_439984-439992.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 68 | 439993–440001 | `seq_439993-440001.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 69 | 440002–440010 | `seq_440002-440010.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 70 | 440011–440019 | `seq_440011-440019.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 71 | 440020–440028 | `seq_440020-440028.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 72 | 440029–440037 | `seq_440029-440037.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 73 | 440038–440046 | `seq_440038-440046.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 74 | 440047–440055 | `seq_440047-440055.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 75 | 440056–440064 | `seq_440056-440064.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 76 | 440065–440073 | `seq_440065-440073.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 77 | 440074–440082 | `seq_440074-440082.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 78 | 440083–440091 | `seq_440083-440091.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 79 | 440092–440100 | `seq_440092-440100.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 80 | 440101–440109 | `seq_440101-440109.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 81 | 440110–440118 | `seq_440110-440118.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 82 | 440119–440127 | `seq_440119-440127.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 83 | 440128–440136 | `seq_440128-440136.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 84 | 440137–440145 | `seq_440137-440145.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 85 | 440146–440154 | `seq_440146-440154.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 86 | 440155–440163 | `seq_440155-440163.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 87 | 440164–440172 | `seq_440164-440172.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 88 | 440173–440181 | `seq_440173-440181.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 89 | 440182–440190 | `seq_440182-440190.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 90 | 440191–440199 | `seq_440191-440199.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 91 | 440200–440208 | `seq_440200-440208.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 92 | 440209–440217 | `seq_440209-440217.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 93 | 440218–440226 | `seq_440218-440226.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 94 | 440227–440235 | `seq_440227-440235.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 95 | 440236–440244 | `seq_440236-440244.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 96 | 440245–440253 | `seq_440245-440253.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 97 | 440254–440262 | `seq_440254-440262.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 98 | 440263–440271 | `seq_440263-440271.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 99 | 440272–440280 | `seq_440272-440280.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 100 | 440281–440289 | `seq_440281-440289.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 101 | 440290–440298 | `seq_440290-440298.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 102 | 440299–440307 | `seq_440299-440307.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 103 | 440308–440316 | `seq_440308-440316.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 104 | 440317–440325 | `seq_440317-440325.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 105 | 440326–440334 | `seq_440326-440334.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 106 | 440335–440343 | `seq_440335-440343.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 107 | 440344–440352 | `seq_440344-440352.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 108 | 440353–440361 | `seq_440353-440361.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 109 | 440362–440370 | `seq_440362-440370.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 110 | 440371–440379 | `seq_440371-440379.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 111 | 440380–440388 | `seq_440380-440388.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 112 | 440389–440397 | `seq_440389-440397.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 113 | 440398–440406 | `seq_440398-440406.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 114 | 440407–440415 | `seq_440407-440415.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 115 | 440416–440424 | `seq_440416-440424.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 116 | 440425–440433 | `seq_440425-440433.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 117 | 440434–440442 | `seq_440434-440442.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 118 | 440470–440478 | `seq_440470-440478.jpg` | `417664- 444276 cut` | częściowo widoczne symbole | pozostało |
| 119 | 440560–440568 | `seq_440560-440568.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 120 | 440569–440577 | `seq_440569-440577.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 121 | 440578–440586 | `seq_440578-440586.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 122 | 440587–440595 | `seq_440587-440595.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 123 | 440596–440604 | `seq_440596-440604.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 124 | 440605–440613 | `seq_440605-440613.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 125 | 440614–440622 | `seq_440614-440622.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 126 | 440623–440631 | `seq_440623-440631.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 127 | 440632–440640 | `seq_440632-440640.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 128 | 440641–440649 | `seq_440641-440649.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 129 | 440650–440658 | `seq_440650-440658.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 130 | 440659–440667 | `seq_440659-440667.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 131 | 440668–440676 | `seq_440668-440676.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 132 | 440677–440685 | `seq_440677-440685.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 133 | 440686–440694 | `seq_440686-440694.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 134 | 440695–440703 | `seq_440695-440703.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 135 | 440704–440712 | `seq_440704-440712.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 136 | 440713–440721 | `seq_440713-440721.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 137 | 440722–440730 | `seq_440722-440730.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 138 | 440731–440739 | `seq_440731-440739.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 139 | 440740–440748 | `seq_440740-440748.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 140 | 440749–440757 | `seq_440749-440757.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 141 | 440758–440766 | `seq_440758-440766.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 142 | 440767–440775 | `seq_440767-440775.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 143 | 440776–440784 | `seq_440776-440784.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 144 | 440785–440793 | `seq_440785-440793.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 145 | 440794–440802 | `seq_440794-440802.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 146 | 440803–440811 | `seq_440803-440811.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 147 | 440812–440820 | `seq_440812-440820.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 148 | 440821–440829 | `seq_440821-440829.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 149 | 440830–440838 | `seq_440830-440838.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 150 | 440839–440847 | `seq_440839-440847.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 151 | 440848–440856 | `seq_440848-440856.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 152 | 440857–440865 | `seq_440857-440865.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 153 | 440866–440874 | `seq_440866-440874.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 154 | 440875–440883 | `seq_440875-440883.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 155 | 440884–440892 | `seq_440884-440892.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 156 | 441406–441414 | `seq_441406-441414.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 157 | 441415–441423 | `seq_441415-441423.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 158 | 441424–441432 | `seq_441424-441432.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 159 | 441433–441441 | `seq_441433-441441.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 160 | 441442–441450 | `seq_441442-441450.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 161 | 441451–441459 | `seq_441451-441459.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 162 | 441460–441468 | `seq_441460-441468.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 163 | 441469–441477 | `seq_441469-441477.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 164 | 441478–441486 | `seq_441478-441486.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 165 | 441487–441495 | `seq_441487-441495.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 166 | 441523–441531 | `seq_441523-441531.jpg` | `417664- 444276 cut` | częściowo widoczne symbole | pozostało |
| 167 | 441532–441540 | `seq_441532-441540.jpg` | `417664- 444276 cut` | częściowo widoczne symbole | pozostało |
| 168 | 441820–441828 | `seq_441820-441828.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 169 | 441829–441837 | `seq_441829-441837.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 170 | 441838–441846 | `seq_441838-441846.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 171 | 441847–441855 | `seq_441847-441855.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 172 | 441856–441864 | `seq_441856-441864.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 173 | 441865–441873 | `seq_441865-441873.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 174 | 441874–441882 | `seq_441874-441882.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 175 | 441883–441891 | `seq_441883-441891.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 176 | 442189–442197 | `seq_442189-442197.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 177 | 442198–442206 | `seq_442198-442206.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 178 | 442207–442215 | `seq_442207-442215.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 179 | 442216–442224 | `seq_442216-442224.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 180 | 442225–442233 | `seq_442225-442233.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 181 | 442234–442242 | `seq_442234-442242.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 182 | 442243–442251 | `seq_442243-442251.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 183 | 442252–442260 | `seq_442252-442260.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 184 | 442261–442269 | `seq_442261-442269.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 185 | 442270–442278 | `seq_442270-442278.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 186 | 442279–442287 | `seq_442279-442287.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 187 | 442288–442296 | `seq_442288-442296.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 188 | 442297–442305 | `seq_442297-442305.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 189 | 442306–442314 | `seq_442306-442314.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 190 | 442315–442323 | `seq_442315-442323.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 191 | 442324–442332 | `seq_442324-442332.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 192 | 442333–442341 | `seq_442333-442341.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 193 | 442342–442350 | `seq_442342-442350.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 194 | 442351–442359 | `seq_442351-442359.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 195 | 442360–442368 | `seq_442360-442368.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 196 | 442369–442377 | `seq_442369-442377.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 197 | 442378–442386 | `seq_442378-442386.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 198 | 442387–442395 | `seq_442387-442395.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 199 | 442396–442404 | `seq_442396-442404.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 200 | 442405–442413 | `seq_442405-442413.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 201 | 442414–442422 | `seq_442414-442422.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 202 | 442423–442431 | `seq_442423-442431.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 203 | 442432–442440 | `seq_442432-442440.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 204 | 442441–442449 | `seq_442441-442449.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 205 | 442450–442458 | `seq_442450-442458.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 206 | 442459–442467 | `seq_442459-442467.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 207 | 442468–442476 | `seq_442468-442476.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 208 | 442477–442485 | `seq_442477-442485.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 209 | 442486–442494 | `seq_442486-442494.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 210 | 442495–442503 | `seq_442495-442503.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 211 | 442504–442512 | `seq_442504-442512.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 212 | 442513–442521 | `seq_442513-442521.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 213 | 442522–442530 | `seq_442522-442530.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 214 | 442531–442539 | `seq_442531-442539.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 215 | 442540–442548 | `seq_442540-442548.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 216 | 442549–442557 | `seq_442549-442557.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 217 | 442558–442566 | `seq_442558-442566.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 218 | 442567–442575 | `seq_442567-442575.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 219 | 442576–442584 | `seq_442576-442584.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 220 | 442585–442593 | `seq_442585-442593.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 221 | 442594–442602 | `seq_442594-442602.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 222 | 442603–442611 | `seq_442603-442611.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 223 | 442612–442620 | `seq_442612-442620.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 224 | 443881–443889 | `seq_443881-443889.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 225 | 443890–443898 | `seq_443890-443898.jpg` | `417664- 444276 cut` | korekta siatki | pozostało |
| 226 | 444421–444429 | `seq_444421-444429.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 227 | 444430–444438 | `seq_444430-444438.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 228 | 444448–444456 | `seq_444448-444456.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 229 | 444457–444465 | `seq_444457-444465.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 230 | 445393–445401 | `seq_445393-445401.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 231 | 445402–445410 | `seq_445402-445410.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 232 | 445411–445419 | `seq_445411-445419.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 233 | 445420–445428 | `seq_445420-445428.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 234 | 445429–445437 | `seq_445429-445437.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 235 | 456868–456876 | `seq_456868-456876.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 236 | 456877–456885 | `seq_456877-456885.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 237 | 466813–466821 | `seq_466813-466821.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 238 | 466822–466830 | `seq_466822-466830.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 239 | 466831–466839 | `seq_466831-466839.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 240 | 466840–466848 | `seq_466840-466848.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 241 | 466849–466857 | `seq_466849-466857.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 242 | 466858–466866 | `seq_466858-466866.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 243 | 466867–466875 | `seq_466867-466875.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 244 | 466876–466884 | `seq_466876-466884.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 245 | 466885–466893 | `seq_466885-466893.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 246 | 466894–466902 | `seq_466894-466902.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 247 | 466903–466911 | `seq_466903-466911.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 248 | 466912–466920 | `seq_466912-466920.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 249 | 466921–466929 | `seq_466921-466929.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 250 | 466930–466938 | `seq_466930-466938.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 251 | 466939–466947 | `seq_466939-466947.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 252 | 466948–466956 | `seq_466948-466956.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 253 | 466957–466965 | `seq_466957-466965.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 254 | 466966–466974 | `seq_466966-466974.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 255 | 466975–466983 | `seq_466975-466983.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 256 | 466984–466992 | `seq_466984-466992.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 257 | 466993–467001 | `seq_466993-467001.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 258 | 467065–467073 | `seq_467065-467073.jpg` | `444277 - 469989 cut` | częściowo widoczne symbole | pozostało |
| 259 | 467119–467127 | `seq_467119-467127.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 260 | 467128–467136 | `seq_467128-467136.jpg` | `444277 - 469989 cut` | korekta siatki | pozostało |
| 261 | 470053–470061 | `seq_470053-470061.jpg` | `469900 - 481536 cut` | korekta siatki | pozostało |
| 262 | 470062–470070 | `seq_470062-470070.jpg` | `469900 - 481536 cut` | korekta siatki | pozostało |
| 263 | 470071–470079 | `seq_470071-470079.jpg` | `469900 - 481536 cut` | korekta siatki | pozostało |
| 264 | 470530–470538 | `seq_470530-470538.jpg` | `469900 - 481536 cut` | korekta siatki | pozostało |
| 265 | 470539–470547 | `seq_470539-470547.jpg` | `469900 - 481536 cut` | korekta siatki | pozostało |
| 266 | 470548–470556 | `seq_470548-470556.jpg` | `469900 - 481536 cut` | korekta siatki | pozostało |
| 267 | 470557–470565 | `seq_470557-470565.jpg` | `469900 - 481536 cut` | korekta siatki | pozostało |
| 268 | 470566–470574 | `seq_470566-470574.jpg` | `469900 - 481536 cut` | korekta siatki | pozostało |
| 269 | 474013–474021 | `seq_474013-474021.jpg` | `469900 - 481536 cut` | korekta siatki | pozostało |
| 270 | 474022–474030 | `seq_474022-474030.jpg` | `469900 - 481536 cut` | korekta siatki | pozostało |
| 271 | 476155–476163 | `seq_476155-476163.jpg` | `469900 - 481536 cut` | korekta siatki | pozostało |
| 272 | 476164–476172 | `seq_476164-476172.jpg` | `469900 - 481536 cut` | korekta siatki | pozostało |
| 273 | 476713–476721 | `seq_476713-476721.jpg` | `469900 - 481536 cut` | korekta siatki | pozostało |
| 274 | 476722–476730 | `seq_476722-476730.jpg` | `469900 - 481536 cut` | korekta siatki | pozostało |
| 275 | 485704–485712 | `seq_485704-485712.jpg` | `481537- 500000 cut` | korekta siatki | pozostało |

## Wynik operacji

- Partia 1: potwierdzone usunięcie 55 źródeł, 443 rozpoznanych plansz i 6645 komórek symboli; 55 zarządzanych artefaktów. Zakres obejmuje 495 numerów plansz.
- Receipt / preview token: `232a575d23654d2377daae71474ba6065552e068e00e61178334a197e06f7302`.
- Czas zakończenia pierwszej partii (UTC): `2026-10-09T19:46:54.988320+00:00`.
- Partia 2: HTTP 500 (`Internal Server Error`). Brak potwierdzonego receiptu. Nie ponawiano DELETE po błędzie.
- Odczyt po błędzie: 220 rekordów źródłowych i 1755 rozpoznanych plansz nadal istnieje. Jedyny receipt odpowiada pierwszej partii. Wynik drugiej partii nie został zatwierdzony w bazie.
- Partie 3–5: niewykonane. Nie obchodzono blokad, triggerów ani uprawnień. Usług nie restartowano.
- Każda pozycja listy i CSV zawiera status `removed` / `remaining`. Pełna lista 275 zdjęć pozostaje listą docelowej nowej paczki.
- Przyczyna błędu API pozostaje nieustalona: odpowiedź nie zawiera tracebacku, a bieżący terminal API nie jest dostępny w tej rozmowie. Przed kontynuacją należy zdiagnozować ten błąd, sprawdzić rollback artefaktów i wykonać świeży podgląd pozostałego zakresu. Zgoda operatora na pierwotny zakres pozostaje odnotowana.
