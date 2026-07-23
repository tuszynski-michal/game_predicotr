---
title: TASK-0001 Architecture clarification
status: done
last_updated: 2026-07-24
---

# TASK-0001 — Zamknięcie pytań architektonicznych

## Goal

Uzupełnić decyzje niezbędne do bezpiecznej inicjalizacji Milestone 01.

## Relevant docs

- `AGENTS.md`
- `ai_docs/project/PROJECT_BRIEF.md`
- `ai_docs/project/OPEN_QUESTIONS.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- odpowiedzieć co najmniej na Q-001–Q-014,
- potwierdzić skalę danych,
- zaakceptować lub zmienić D-001–D-010,
- usunąć sprzeczności w wymaganiach,
- zaktualizować Current State.

## Out of scope

- tworzenie kodu,
- inicjalizacja frameworków,
- wybór finalnego modelu OCR/ML,
- masowy import layoutów lub zdjęć.

## Owner answers

Wpisz odpowiedzi poniżej. Można odpowiadać krótko, ale jednoznacznie.

### Q-001 Mobile online/offline

Aplikacja mobilna ma działać całkowicie offline już w Milestone 01. Po instalacji
nie korzysta z Internetu, sieci lokalnej ani połączenia z backendem.

Aplikacja będzie instalowana testowo na maksymalnie 3–5 urządzeniach i nie będzie
publicznie dystrybuowana. Pierwsze urządzenia testowe to Google Pixel 10 Pro XL
oraz Samsung S21 Ultra.

Dane mobilne są dołączane do konkretnej wersji aplikacji. Po zmianie danych w
panelu administracyjnym administrator tworzy nową wersję aplikacji Android, którą
następnie instaluje się na telefonach. Nie przewiduje się synchronizacji danych.
Panel administracyjny powinien zawierać funkcję przygotowania wersjonowanego
wydania na Android; dokładny mechanizm budowania i instalacji zostanie opisany
w architekturze dostarczania.

### Q-002 Skala danych

Przewidywane jest około 12–15 gier, z możliwością dodania kolejnych. Każda gra
może zawierać około `500 000` layoutów, czyli przy 15 grach należy zakładać około
7,5 miliona rekordów.

Liczba `500 000` odnosi się do kanonicznych rekordów layoutów używanych do
sprawdzenia, czy layout wprowadzony ręcznie w aplikacji odpowiada pozycji w
sekwencji. Po jednoznacznym odnalezieniu pozycji docelowa wersja aplikacji
uruchamia algorytm obliczający wyniki prezentowane w sekcji Result/Target;
ostateczna nazwa sekcji pozostaje do ustalenia.

Do wydania mobilnego trafiają wyłącznie rekordy layoutów oraz konfiguracja
potrzebna do obliczeń. Zdjęcia źródłowe i dane robocze importu nie są dołączane
do aplikacji. Rozmiar wydania na poziomie kilku gigabajtów jest akceptowalny;
niedopuszczalny byłby dopiero nieuzasadniony rozmiar rzędu dziesiątek
gigabajtów. Priorytetami są poprawność, niezawodne działanie, wydajność i
prostota utrzymania. Nie należy wprowadzać agresywnej, niestandardowej
kompresji bez potrzeby potwierdzonej pomiarami.

### Q-003 Sequence number

W opublikowanej wersji danych `sequence_number` musi być unikalny i tworzyć
ciągłą sekwencję bez luk w ramach gry. Błędy numeracji wykryte podczas importu
muszą zostać poprawione przed przygotowaniem wydania mobilnego.

Unikalność numeru nie oznacza unikalności zawartości layoutu. Ten sam układ
symboli może rzadko wystąpić pod kilkoma różnymi numerami sekwencji; typowo jest
to około 5–10 przypadków duplikatów na grę. Aplikacja musi wykryć taką sytuację,
pokazać użytkownikowi informację o duplikacie i nie może samodzielnie wybrać
jednego z pasujących numerów.

Procedura użytkownika polega na wyczyszczeniu bieżącego layoutu i wprowadzeniu
kolejnego layoutu widocznego w grze. Oczekiwane jest, że kolejny układ będzie już
jednoznaczny. Szczegóły przechowywania albo nieprzechowywania kontekstu
duplikatu zostaną rozstrzygnięte w Q-014.

### Q-004 Koniec sekwencji

Sekwencja jest cykliczna. Jeżeli punktem startowym jest przedostatni layout,
algorytm analizuje ostatni layout, a następnie przechodzi do layoutu o
`sequence_number = 1` i kontynuuje obliczenia.

Numer analizowanego spinu nadal rośnie niezależnie od zawinięcia numeru
sekwencji. Pełny cykl forecastu obejmuje wszystkie przyszłe layouty aż do
layoutu bezpośrednio poprzedzającego `spin 0`. Layout startowy nie jest ponownie
oceniany na końcu cyklu.

Jeżeli dataset zawiera `N` layoutów, algorytm analizuje `N - 1` spinów. W M1
jest to 999 spinów, a dla docelowej gry zawierającej `500 000` layoutów —
`499 999` spinów. Po przeanalizowaniu tego zakresu algorytm kończy obliczenia.

### Q-005 Typy wzorców

Gra posiada konfigurowalne układy wygrywających linii. Linia jest podawana jako
tablica liczb, w której pozycja elementu odpowiada kolumnie, a wartość wskazuje
wiersz, np. `[2, 3, 2, 1, 1]`.

Dla planszy 3 × 5 linia musi zawierać dokładnie 5 elementów. Panel i backend
muszą blokować tablicę o liczbie elementów innej niż liczba kolumn oraz numer
wiersza spoza istniejącego zakresu. Sposób prezentacji numerów wierszy w UI oraz
ich wewnętrzne indeksowanie muszą zostać opisane jednoznacznie.

Panel administracyjny pozwala skonfigurować wymiary layoutu przy użyciu dwóch
pól liczbowych: liczby kolumn i liczby wierszy. W Milestone 01 obowiązuje layout
o 5 kolumnach i 3 rzędach.

Jedynym wymaganym typem wzorca jest konkretna linia `PAYLINE`. Reguła
`CONSECUTIVE_COLUMNS_ANY_ROW`, która ignoruje pozycję wiersza, nie występuje.

### Q-006 Początek dopasowania

Zwycięski ciąg może rozpocząć się w dowolnej kolumnie payline i musi obejmować
co najmniej 3 kolejne kolumny bez przerwy.

Dla przykładowej linii `[2, 3, 1, 1, 2]` wystąpienie tego samego symbolu na
pozycjach `[x, 3, 1, 1, x]` tworzy ciąg długości 3 i jest wygraną. Układ
`[2, x, 1, 1, x]` nie tworzy ciągu długości 3, ponieważ przerwa rozdziela
wystąpienia.

Wypłata zależy od symbolu oraz długości ciągłego dopasowania, np. 3, 4 albo 5
kolumn. W Milestone 01 mogą zostać użyte wartości testowe, natomiast docelowe
wartości administrator definiuje osobno dla każdego symbolu w panelu.

### Q-007 Najwyższa długość czy wszystkie

Dla tego samego symbolu, tej samej payline i jednego ciągłego dopasowania
naliczana jest wyłącznie wypłata za najdłuższą osiągniętą długość.

Jeżeli symbol ma wypłaty `3 = 100`, `4 = 300`, `5 = 900`, to ciąg długości 5
daje `900` kredytów. Nie sumuje się jednocześnie wypłat za długości 3, 4 i 5.

### Q-008 Wiele symboli w kolumnie

Pierwotne pytanie o wiele wystąpień symbolu w jednej kolumnie nie dotyczy już
reguły `CONSECUTIVE_COLUMNS_ANY_ROW`, ponieważ ten typ wzorca został wykluczony
w Q-005. Każda payline wskazuje dokładnie jedną komórkę w danej kolumnie.

Ta sama komórka może jednak należeć do kilku różnych paylines. Komórka nie jest
„zużywana” przez pierwszą wygraną i może uczestniczyć w każdym niezależnym
dopasowaniu. Przykładowo linie `[1, 2, 1, 1, 1]` i `[3, 2, 3, 1, 2]` przecinają
się w kolumnach 2 i 4. Symbol znajdujący się w komórce wspólnej może zostać
uwzględniony w wygranej na obu liniach, jeżeli każda z nich niezależnie spełnia
warunki dopasowania.

### Q-009 Joker

Joker zastępuje dowolny zwykły symbol, nie ma własnej wypłaty i nie tworzy
samodzielnej wygranej. Nie występuje wygrywający ciąg złożony wyłącznie z
jokerów.

Każda payline jest oceniana niezależnie. Ta sama komórka z jokerem może
zastępować różne symbole na różnych paylines, np. `S1` na jednej linii i `S3` na
drugiej, jeżeli takie interpretacje spełniają reguły odpowiednich linii. Gdy na
jednej payline istnieje kilka poprawnych interpretacji, wybierana jest
interpretacja dająca najwyższą wypłatę.

Wynik obliczenia powinien zawierać informację, jaki symbol joker zastąpił w
każdym naliczonym dopasowaniu.

### Q-010 Sumowanie

Każda payline jest oceniana niezależnie, a wszystkie poprawne wygrane są
sumowane:

- wygrane różnych symboli sumują się,
- ten sam symbol wygrywający na różnych paylines jest liczony osobno dla każdej
  linii,
- wspólne komórki oraz jokery nie blokują naliczenia pozostałych paylines,
- dla jednego symbolu, jednej payline i jednego ciągłego dopasowania obowiązuje
  tylko wypłata za najdłuższy ciąg zgodnie z Q-007.

Przykładowo wygrana `S1 = 300` na pierwszej linii oraz `S3 = 500` na drugiej
linii daje łączną wypłatę `800`.

System nie może pozwolić na zapisanie dwóch identycznych paylines w ramach tej
samej konfiguracji gry.

### Dodatkowe wymagania edytora paylines w panelu admina

- Przycisk, np. `Dodaj wzór`, otwiera modal z planszą odpowiadającą wymiarom
  layoutu danej gry.
- Plansza początkowo zawiera puste kafelki.
- Kliknięcie kafelka zaznacza go w widoczny sposób, np. podświetleniem albo
  symbolem wewnątrz.
- W jednej kolumnie można zaznaczyć najwyżej jedną komórkę.
- Zapis wymaga wybrania dokładnie jednej komórki w każdej kolumnie.
- Panel waliduje, czy identyczny wzorzec nie został już zapisany.
- Administrator ma dostęp do listy istniejących wzorców przedstawionej jako
  tabela, w której jeden wiersz odpowiada jednej payline.
- Dokładne rozmieszczenie przycisków, tabeli i modala zostanie ustalone podczas
  projektowania UI, bez zmiany powyższych reguł domenowych.

### Q-011 Spin 0

Layout wprowadzony przez użytkownika i jednoznacznie odnaleziony w sekwencji jest
punktem startowym `spin 0`. Nie nalicza się za niego kosztu ani wypłaty.

Pierwszy analizowany spin dotyczy następnego layoutu w sekwencji i dopiero dla
niego naliczany jest koszt oraz obliczana wypłata. Jeżeli rozpoznano layout
`100`, spin 1 analizuje layout `101`. Jeżeli rozpoznano ostatni layout, spin 1
analizuje layout `1` zgodnie z cyklicznością ustaloną w Q-004.

### Q-012 Definicja plusa

Wynik netto jest obliczany jako:

```text
net_credits = cumulative_payout - cumulative_cost
```

Rekord jest dodatni wtedy i tylko wtedy, gdy `net_credits > 0`. Wartość `0`
oznacza wyjście na zero i nie jest traktowana jako dodatni wynik.

Każdy payout napotkany po drodze jest dodawany do `cumulative_payout`,
niezależnie od tego, czy w danym momencie wystarcza do uzyskania dodatniego
wyniku. Równoważny zapis iteracyjny:

```text
net_credits[n] = net_credits[n - 1] + payout[n] - spin_cost
```

Przykładowo po 100 spinach o koszcie 10 łączny koszt wynosi 1000. Jeżeli suma
wszystkich payoutów z tych 100 layoutów wynosi 900, wynik netto to `-100` i nie
jest dodatni.

### Q-013 Dodatnie lokalne maksima

Tabela Target nie pokazuje każdego kolejnego dodatniego wyniku ani globalnych
`high-water marks`. Pokazuje dodatnie lokalne szczyty wyniku netto.

Jeżeli wynik netto rośnie przez kolejne spiny, do tabeli trafia tylko jeden
wiersz: spin z najwyższą wartością na końcu tego rosnącego odcinka, przed
spadkiem. Dla ciągu:

```text
5, 10, 15, 25, 20
```

pokazywany jest wyłącznie spin z wynikiem `25`.

Każdy kolejny dodatni lokalny szczyt również trafia do tabeli, nawet jeśli jest
niższy od poprzedniego. Jeżeli pierwszy szczyt to `spin 200 = 25`, a kolejny to
`spin 203 = 18`, tabela zawiera oba wiersze w tej kolejności.

Pierwszy moment przekroczenia zera nie jest osobnym rekordem, jeżeli wynik
rośnie dalej. Pojęcia `high-water mark` oraz `first positive` w obecnej
dokumentacji i API wymagają zastąpienia pojęciem dodatniego lokalnego szczytu.

Jeżeli maksymalny wynik utrzymuje się przez kilka kolejnych spinów, tabela
pokazuje pierwszy spin osiągający tę wartość. Dla ciągu
`10, 25, 25, 25, 20` wskazywany jest pierwszy element o wartości `25`.

### Zakres i przygotowanie obliczeń forecastu

- Forecast analizuje wszystkie przyszłe layouty w jednym cyklu, ale nie ocenia
  ponownie layoutu startowego.
- Analiza zaczyna się od layoutu następującego po `spin 0`, zawija na początek
  sekwencji i kończy na layoucie bezpośrednio poprzedzającym `spin 0`, czyli po
  `layout_count - 1` spinach.
- Podczas przygotowania nowego wydania mobilnego system oblicza i zapisuje
  payout każdego layoutu dla konkretnej wersji reguł.
- Zmiana layoutów albo reguł wymaga ponownego wyliczenia payoutów i utworzenia
  nowego wydania aplikacji.
- Telefon oblicza forecast przez sekwencyjne odczytanie gotowych payoutów,
  naliczanie kosztu i wykrywanie dodatnich lokalnych szczytów.

### Prezentacja tabeli Target

- Tabela znajduje się na dole głównego widoku aplikacji, pod sekcjami
  wprowadzania layoutu i podstawowego wyniku.
- Po wprowadzeniu danych użytkownik przewija ekran w dół, aby przeglądać tabelę.
- Wiersze są uporządkowane rosnąco według numeru spinu.
- Lista musi używać wirtualizowanego renderowania, aby duża liczba wyników nie
  powodowała utworzenia wszystkich elementów UI jednocześnie.

### Q-014 Confirmation chain

Aplikacja nie używa `confirmation chain` i nie zachowuje kandydatów poprzedniego
duplikatu.

Po znalezieniu kilku rekordów o identycznej zawartości:

1. aplikacja informuje użytkownika o duplikacie,
2. nie wybiera żadnego `sequence_number` i nie uruchamia obliczeń,
3. użytkownik czyści planszę,
4. przechodzi w grze do kolejnego layoutu,
5. wprowadza go jako całkowicie nowe wyszukiwanie.

Jeżeli kolejny layout jest jednoznaczny, jego pozycja staje się nowym `spin 0`.
Jeżeli również jest duplikatem, użytkownik powtarza procedurę. Reset usuwa cały
kontekst poprzedniego wyszukiwania.

## Acceptance criteria

- [x] Q-001–Q-014 mają odpowiedzi.
- [x] Każda odpowiedź została odzwierciedlona w wymaganiach.
- [x] D-001–D-010 mają właściwy status.
- [x] Algorithms, Data Model i API Contract opisują ten sam model offline.
- [x] Current State wskazuje zalecany kierunek pierwszego zadania implementacyjnego.

## Outcome

Zamknięto pytania blokujące M1 i zaakceptowano decyzje D-001–D-010.
Dokumentacja została zsynchronizowana z następującym modelem:

- mobile jest całkowicie offline i czyta wersjonowany SQLite dołączony do APK,
- kanoniczne dane administracyjne pozostają w lokalnym PostgreSQL,
- payout każdego layoutu jest obliczany przed wydaniem,
- forecast ocenia `layout_count - 1` spinów, kumuluje wszystkie payouty i koszt
  każdego spinu,
- tabela pokazuje dodatnie lokalne maksima netto,
- duplikat nie jest rozstrzygany łańcuchem; Reset zaczyna nowe wyszukiwanie,
- jedynym typem wzorca jest `PAYLINE`,
- panel docelowo przygotowuje wersjonowany snapshot oraz APK,
- stos image ingestion pozostaje wymienny do benchmarku na większym zbiorze.

Zaktualizowano wymagania, architekturę, model danych, kontrakty, roadmapę,
strategię testów, traceability i Current State. Nie utworzono kodu ani nie
zainicjalizowano frameworków. Weryfikacja zadania obejmowała kontrolę tekstową
spójności dokumentów; testy kodu nie miały zastosowania.

Następne zalecane zadanie zostało po późniejszym przeglądzie wykonawczym
doprecyzowane jako `TASK-0002 — Monorepo and offline SQLite spike`. Aktualny
podział znajduje się w
`delivery/MILESTONE_01_EXECUTION_PLAN.md`, a utworzenie i wykonanie zadania
czeka na osobne polecenie właściciela.
