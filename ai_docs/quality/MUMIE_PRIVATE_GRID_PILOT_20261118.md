# Pilot cięcia siatek Mumii A2

## Stan na 18 listopada 2026

Operator przygotuje świeży folder. Rzeczywista liczba plansz wymagających poprawy, naprawionych, pogorszonych i nowo uciętych symboli pozostaje niezmierzona. Rekomendacja aktywacji czeka na nowego kandydata, wynik istniejących bramek i ślepe oceny człowieka.

Odczyt w transakcji PostgreSQL `READ ONLY` potwierdził wersję gry `6cc10344-1d69-5765-b8c8-423a0313984a`, rewizję 7 i kohortę `8d571c98-bbcc-5d00-9792-4ec77e53c491`. Dwa ostatnie importy obejmują 2778 i 2789 zdjęć. Wszystkie 5567 mają pozycje wyznaczone w manifeście źródeł przed detekcją. Dla żadnego rejestr nie potwierdza pełnego, niezależnego nagrania. Z tego względu nie weszły do sprawdzianu.

### Rozliczenie historycznych korekt

Kwerenda łączy aktualnie zatwierdzoną ręczną rewizję planszy z poprzednią rewizją tej samej strony przez zdarzenia unieważnienia 15 pól. Porównuje ten sam slot, tożsamość obrazu i 24 węzły. Użycie etykiety wymaga zgodności węzłów, numeru rewizji i identyfikatora ręcznej korekty z zapisem zamrożonej kohorty.

| Dowód w kohorcie aktywnego modelu | Przed 11:15:49 UTC | Bieżący odczyt |
|---|---:|---:|
| Użyta dokładna rewizja TRAIN | 589 | 589 |
| Użyta dokładna rewizja VALIDATION | 57 | 57 |
| Użyta dokładna rewizja REGRESSION | 21 | 21 |
| Inna rewizja lub geometria | 5 | 5 |
| Brak zatwierdzenia i niepełne oznaczenie zdjęcia | 3 | 4 |
| Jak wyżej, dodatkowo bufor podziału | 24 | 24 |
| Jak wyżej, dodatkowo chronione sąsiedztwo | 5 | 5 |
| Jak wyżej, dodatkowo bufor i problem siatki lub topologii | 3 | 3 |
| Jak wyżej, dodatkowo problem siatki lub topologii | 1 | 1 |
| **Pełne pary / różne zdjęcia** | **708 / 521** | **709 / 521** |

Poza tabelą pozostają 24 rekordy bez pełnego powiązania 15 pól z jedną poprzednią rewizją. Bieżący odczyt objął 733 rekordy. Kolumna historyczna stosuje jawny górny limit daty korekty `2026-11-18T11:15:49Z`. Najnowszy zapis dla planszy 9 pochodzi z 11:15:49,199007 UTC. Taki podział odtwarza liczność 708/521. Dokładna chwila pierwotnego pomiaru jest nieznana. Rola źródła TRAIN, VALIDATION lub REGRESSION sama nie dowodzi użycia tej rewizji.

### Gdzie przesuwała się ramka Mumii A2

Pomiar z 18 listopada obejmuje 589 par na 461 zdjęciach treningowych wersji `6cc10344`. Sprawdzono zgodność położenia 24 węzłów, ID korekty i jej rewizji z etykietą użytą w zamrożonej kohorcie TRAIN. W 508 parach poprzednia siatka była automatyczna, w 81 już wcześniej poprawiona ręcznie. Jest to zbiór wybranych korekt. Nie wyznacza częstości błędów na wszystkich importach ani jakości najnowszego modelu na nowych zdjęciach.

Każdą parę sprowadzono do płaszczyzny ręcznie skorygowanej planszy o wymiarach 5 × 3 pola. Jednostką jest wysokość lub szerokość jednego pola. Dla obwodu i środka policzono bezwzględne przesunięcie w bardziej zmienionej osi, a dla poszczególnych boków średnie przesunięcie do wnętrza planszy. Drugi pomiar wyrównuje cztery narożniki obu siatek i dopiero wtedy porównuje osiem wewnętrznych węzłów. Próg ćwierci pola służy opisowi wielkości poprawki.

| Zmiana przekraczająca ¼ pola | Wszystkie poprawki (589) | Po automacie (508) |
|---|---:|---:|
| Co najmniej jeden węzeł obwodu | 341 | 323 |
| Środek planszy | 89 | 87 |
| Górna granica średnio za nisko | 276 | 264 |
| Dolna granica średnio za wysoko | 5 | 5 |
| Lewa albo prawa granica średnio za daleko do środka | 0 | 0 |
| Wewnętrzny węzeł po wyrównaniu narożników | 0 | 0 |

Największe przesunięcie obwodu miało medianę 0,278 pola, a 90. percentyl 0,994 pola. Częsty wzór to utrata górnego fragmentu planszy. Współrzędne wewnętrznych węzłów obu zapisanych siatek w tych parach wynikają niemal dokładnie z projekcji narożników. Taka korekta silnie nadzoruje pozycję obrysu. Sam zapis nie rozdziela błędu pierwszego detektora od błędu dopasowania siatki na wycinku i nie daje dowodu o indywidualnym obrysie symbolu. W zbiorze TRAIN tej wersji 10 zdjęć miało etykiety wszystkich dziewięciu plansz, a 493 zdjęcia miały etykiety częściowe (434 z jedną, 56 z dwiema, dwa z trzema i jedno z pięcioma). Do uczenia detektora Mumii szczególnie wartościowe są całe zdjęcia z zatwierdzonymi wszystkimi planszami, również z trudnym górnym rzędem. Liczność dla nowego treningu sprawdza aktualny podgląd gotowości.

### Co trafiło do wycinków

Z czterech różnych historycznych zdjęć TRAIN wycięto po 15 pól przed i po korekcie, łącznie 120 wycinków. Dla każdej pary użyto tego samego oryginału, jego sprawdzonych sum, pozycji i parametrów wycinania z danego importu. Zmierzono, jaka część powierzchni ręcznie wskazanego pola znajduje się w obszarze źródłowym faktycznie pobranym przez renderer. Tabela podaje wynik najgorzej pokrytego z 15 pól.

| Plansza | Historyczne wcięcie na stronę | Przed korektą | Po korekcie |
|---|---:|---:|---:|
| 24580 | 0% | 0,0% | 100,0% |
| 317712 | 8% | 55,6% | 70,6% |
| 197814 | 0% | 71,8% | 100,0% |
| 228343 | 8% | 68,9% | 70,6% |

Na zdjęciu 24580 obrys poprzedniej siatki zaczyna się w drugim rzędzie symboli. Ręczna korekta przywraca górny rząd w końcowych kafelkach. Na 317712 widać skośną górną granicę i cofnięcie poprzedniej siatki do wnętrza. Historyczne wcięcie 8% z każdego boku pozostawia około 70,56% powierzchni prostokątnego pola nawet po idealnym ustawieniu siatki. Liczby opisują powierzchnię pola. Stopień ucięcia grafiki zależy od jej faktycznych granic na zdjęciu. W obu najnowszych importach wskazanych w tym pilocie, również w domyślnym `5fd0aca9`, odczytany parametr wynosi 0%. Odbiór nowego modelu mierzy pełne pole.

Pomiar i podgląd można odtworzyć z katalogu gałęzi roboczej. Wskaż rzeczywisty katalog artefaktów instalacji i nowy katalog wyjściowy. Polecenie bez opcji `--preview` zwraca same pomiary. Z wygenerowanego katalogu otwórz `index.html`. Baza aplikacji jest otwierana tylko do odczytu. Istniejące rezerwacje sprawdzianów wykluczają zdjęcia, kopie i znane powiązania nagrań. Podgląd zapisuje ekspozycję wybranych przypadków w tym samym lokalnym rejestrze pilota.

```powershell
.\.venv\Scripts\python.exe scripts/mumie_grid_pilot.py --artifacts 'D:\game_predicotr\artifacts' training-geometry --version 6cc10344-1d69-5765-b8c8-423a0313984a --preview '.runtime\mumie-a2-geometria'
```

## Przebieg operatorski

Pierwszy trening niezależnego modelu wymaga wdrożenia gałęzi z migracjami 0193 i 0194 oraz włączenia prywatnej rodziny Mumii A2. W panelu „Ulepsz siatki z korekt” sprawdź informację „Pierwszy trening od zera” i liczby pełnych zdjęć w podziale do treningu i walidacji. Jedno pełne zdjęcie ma zatwierdzoną geometrię wszystkich dziewięciu plansz. Zamroź świeży sprawdzian przed pierwszym treningiem. Nowy sprawdzian wymaga kontraktu zapisu pełnego pola (wcięcie 0%) i potwierdzonego niezależnego pochodzenia wag kandydata dla Mumii A2.

Polecenia uruchamia się z katalogu repozytorium. W worktree wskaż faktyczny katalog artefaktów instalacji parametrem globalnym `--artifacts` przed nazwą polecenia. Wszystkie próby powinny korzystać z jednego trwałego katalogu rejestru. Domyślnie jest to `artifacts/mumie-grid-pilot`. SQLite zapisuje manifesty, zarezerwowane tożsamości zdjęć i nagrań, przypisanego kandydata oraz klucz ślepej oceny. Samo uruchomienie CLI nie zapisuje danych w PostgreSQL.

1. **Zamrożenie przed strojeniem.** Przygotuj osobny katalog zawierający całe nowe, wcześniej nieużyte nagranie Mumii A2. Nazwy JPEG deklarują zakres domenowy, np. `seq_101-109.jpg`. Całe nagranie, łącznie z niewylosowanymi klatkami i kopiami, pozostaje poza importami, strojeniem i diagnostyką. Komenda odczytuje oryginalne pliki oraz oblicza tożsamości bajtowe i pikselowe. Potwierdzenie operatora obejmuje pochodzenie zdjęć i kompletność folderu. Samymi pikselami nie da się ustalić, czy nieujawnione ujęcia pochodzą z tego samego nagrania.

   ```powershell
   .\.venv\Scripts\python.exe scripts/mumie_grid_pilot.py freeze --folder 'D:\Pilot\NoweNagranie' --confirm-complete-fresh-recording
   ```

   Zachowaj wypisany identyfikator `study` oraz sumę manifestu. CLI wybiera dokładnie 100 różnych zdjęć i potwierdzonych pozycji, niezależnie od wyniku detekcji. Brak odpowiedniej liczby blokuje zapis. Dla źródeł już zarejestrowanych alternatywą jest `freeze --import-ids <id-importu> ...`. Wówczas działający rejestr musi potwierdzać całe niezależne nagranie, jego ochronę przed treningiem oraz brak wcześniejszej ekspozycji. `inspect` sprawdza te warunki dla dwóch opisanych importów.

2. **Rozpoznanie etapu poprawy.** Wstaw identyfikator `study` do zmiennej. Komenda pokazuje wyłącznie osobne przypadki historyczne z materiału TRAIN. Sprawdza rezerwacje i ekspozycje przed załadowaniem obrazu.

   ```powershell
   $proba = '<identyfikator study>'
   .\.venv\Scripts\python.exe scripts/mumie_grid_pilot.py diagnose $proba
   ```

   Otwórz wygenerowany `diagnoza/index.html`. Dla każdej planszy porównaj oryginał, raster detektora, wejście planszy, obrys detekcji, węzły modelu, ręczną siatkę i 15 pól zapisanych produkcyjnym rendererem. Brak detekcji pozostawia oryginał i dostępne wejście. Wybierz przyczynę i pobierz raport. Obrys detektora wymaga pełnych etykiet zdjęć i istniejącej bramki gotowości. Częściowe korekty nadają się do uczenia węzłów. Zmianę zapisu wycinków trzeba najpierw zmierzyć na tym samym modelu. Przy mieszanej przyczynie sprawdź oba etapy osobno. Trening wymaga odrębnej decyzji.

3. **Ślepe porównanie.** Po osobno zatwierdzonym treningu podaj identyfikator zarejestrowanego kandydata. Program sprawdzi przypiętą bazę i czas rozpoczęcia treningu. Oba modele dostają identyczne oryginały, pozycje i kontrakt zapisu. Kontrakt domyślnie pochodzi z jawnie wskazanego importu Mumii. Zmiana kontraktu jest możliwa wyłącznie przy zamrożeniu nowego sprawdzianu przez `--contract-import`.

   ```powershell
   $kandydat = '<identyfikator wersji kandydującej>'
   .\.venv\Scripts\python.exe scripts/mumie_grid_pilot.py blind $proba $kandydat
   ```

   Oceniający dostaje wyłącznie folder `ocena`. Otwiera w nim `index.html`, ogląda oryginał, wskazaną pozycję i pola A/B. Rozkład stron losowany jest osobno dla każdej pary i pozostaje stały po ponowieniu. Oceniający wskazuje status poszczególnych pól albo przyciskiem oznacza pozostałe jako pełne i poprawne. Niedostępna plansza pozostaje w próbie. Po 100 parach pobiera `oceny.json` przyciskiem i zapisuje go poza folderem `ocena`, którego integralność jest sprawdzana przed podsumowaniem.

4. **Raport.** Wskaż pobrany plik.

   ```powershell
   .\.venv\Scripts\python.exe scripts/mumie_grid_pilot.py score $proba 'D:\Pilot\oceny.json'
   ```

   Raport podaje liczby plansz wymagających korekty dla obu wersji, naprawionych i pogorszonych oraz liczbę nowych ucięć poszczególnych pól. Brak planszy lub choć jedno pole do poprawy obciąża całą planszę. Rekomendacja wymaga zysku netto co najmniej 5/100 i zera nowo uciętych wcześniej pełnych symboli. Pole nierozstrzygalne lub utracony wcześniej pełny symbol nie pozwalają potwierdzić braku nowych ucięć. Konieczny jest także aktualny PASS produkcyjnej kwalifikacji prywatnego kandydata dla tej gry. Program ponownie porównuje wszystkie klatki nagrania z bazą źródeł, rejestrem użycia i zamrożonymi kohortami. Dla zaimportowanej próby sprawdza domknięcie nagrań i kopii. Zmiana przypisania, wykryta ekspozycja, drugi kandydat, pomieszany pakiet lub niepełne oceny blokują odbiór. Kolejna próba po dostrojeniu wymaga świeżego nagrania i nowego manifestu. Publikacja oraz aktywacja pozostają osobnymi decyzjami.

Rozliczenie korekt można powtórzyć przez `history` lub `history --before 2026-11-18T11:15:49Z`.
