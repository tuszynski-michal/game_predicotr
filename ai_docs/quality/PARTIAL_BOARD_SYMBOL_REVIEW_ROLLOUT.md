# Wdrożenie obsługi niepełnych plansz — TASK-0712

Data:2026-09-27. Osobne zlecenie użytkownika obejmuje wdrożenie oraz krok
danych T4. Wersja kodu:v1.7.16 / a4c38cacefc62edffe116b485f6497f708ba71d2.

## Zakres i ochrona danych

Gra777 `bfc4f949-5c14-4850-b02a-db99610bcfa5`, dokładna lista70 plansz
z zaakceptowanego planu. Nie wykonywano rozpoznawania, treningu ani zmiany
historycznych manifestów. Poza tym zakresem wykonano wyłącznie migracje
rozszerzające, odbudowę projekcji liczników gry oraz odczytowy audyt.

Przed operacją:Alembic0125, brak aktywnych jobów i transakcji aplikacyjnych.
Main API8000, Admin3000 i worker general7 zatrzymane; lab8102/3102 oraz
reviewer3001 pozostawiono. Zgodne usługi przygotowano przed zmianą danych,
a uruchomienie następuje po licznikach, aby nowe zapisy nie unieważniały
kursora. Produkcyjny build Admina PASS.

## Backup i migracje

- Pełny `pg_dump` CUSTOM, kompresja1, exit0; rozmiar22,088,367,628B.
- SHA256:`135915d338a87c5fc5ef26cd280aa457e89e3f8a49ed1b296f166eae8b4617e1`.
- `pg_restore --list`:exit0,4110 pozycji katalogu; potwierdzona czytelność
  archiwum. Nie wykonano pełnego próbnego odtworzenia bazy90.77GB.
- Łączny czas kopii i weryfikacji1534.21s. Na podstawie postępu COPY
  zwiększono limit20→60min, przejmując uchwyt tego samego procesu dumpa;
  kopia nie została przerwana ani uruchomiona ponownie.
- Świeży preflight przed migracją:0jobów/0innych aktywnych transakcji,
  main porty nieaktywne, lab PID4200/12968 bez zmian, wolne83.96GB.
- Niezależny audyt bramki backupu PASS. Alembic0126→0128:exit0/3.17s.

Surowe dowody i archiwum lokalnie w ignorowanym katalogu
`artifacts/partial-board-rollout/20260927-t0712/`; dużych plików nie dołączono
do repozytorium.

## Preview i atomowe uzupełnienie

Świeży preview po migracji ma SHA
`a964291d5517751f0761842d975fef74df4e1c77a8365d26977a6718f8e7e515`.
Jest zgodny z ponownym odczytem przed migracją:70 gotowych plansz,
985 pozycji,65 braków,829full/201partial/20outside. Źródła sprawdzono przez
rzeczywisty odczyt SHA i wymiarów oraz przypiętą bieżącą geometrię.

Wykonano14 partii po5 nowych plansz, każda z własną transakcją obejmującą
wspólny writer i receipt. Wynik:70 receiptów,1050 pozycji,0konfliktów.
Każda plansza ma dokładnie indeksy0–14. Wszystkie985 istniejących ID
zachowane. Odczytowy audyt potwierdził brak zmian ownerów, źródeł, geometrii,
obserwacji, predykcji i kolejki. Pola outside nie mają fikcyjnych zasobów.

| Dostępność | Pozycje |
|---|---:|
| full |829|
| partial |201|
| outside |20|
| Wszystkie |1050|

W pilocie nie było ręcznych decyzji operatora; nie traktujemy tej operacji
jako testu ich zachowania. Ochronę decyzji i późniejszych zmian potwierdziły
wcześniejsze izolowane testy T4. Istniejące193 oznaczenia częściowej
widoczności zachowano,8 kolejnych dotyczy nowo utworzonych pozycji.

Retry w nowym procesie:70/70 replayed,0nowych prób, brak nowych eventów
i zmian danych. Preview po apply i po retry mają identyczny SHA
`4444ff694bcf9ad2b7d0b24820fca1543c527ae2e7565e40c843e121fbfdc0fb`.
Digest1050 komórek:
`916fa29c5171df976196a55cd8bd8a81d7f140c3c4fc6a26a6ccf32863640cba`.

## Liczniki i usługi

Odbudowa zakończona. Użyła niezmienionego `rebuild_counts_batch`, pełnej
walidacji manifestu, osobnej transakcji na najwyżej10000 rekordów i trwałego
kursora. Odczytowy EXPLAIN potwierdził Index Scan po `(game_id,id)`.
Pomiar koniecznej pracy:3 partie w jednym engine7.17s; uniknięto narzutu
uruchamiania osobnego procesu dla każdej komendy. Kontrolowany helper ma
limit800 partii/60min i zatrzymanie pomiędzy partiami; repository ustawia
efektywny timeout zapytania30s.
Nie zwiększono partii ani nie pominięto walidacji.

Po pierwszych16 partiach dalsze735 wywołań (w tym końcowe stwierdzenie
wyczerpania) zakończyło się w412.48s. Początkowy ostrożny szacunek był
dłuższy; odczyt przyspieszył w trakcie. Stan globalny i liczniki:`ready`,
marker`_semantics.version=2`, kursorNULL, rewizja liczników500673.

| Zakres | Wymagające weryfikacji | Zatwierdzone | Suma |
|---|---:|---:|---:|
| Wszystkie grupy |7,498,986|701|7,499,687|
| Nierozpoznany |302,642|0|302,642|
| Poza zdjęciem |20|0|20|
| Osiem grup symboli łącznie |7,196,324|701|7,197,025|

Dziesięć grup szczegółowych sumuje się dokładnie do „Wszystkich”. To wynik
bieżącej projekcji liczników. Historyczne pole postępu starego backfillu
`state.cell_count=7,497,075` pozostało bez zmian i nie jest tym kontraktem
liczników.

Nowe procesy:API launcher35276/listener9860, Admin23576, worker general
launcher40784/worker39752 z budżetem7. Niezależne HTTPhealth/API i Admin
potwierdzone200. Lab8102 PID4200 i3102 PID12968 bez zmian. Pierwszy start
Admina zakończył się błędem względnej ścieżki Next; ponowiono go z
absolutną ścieżką współdzielonego `node_modules/next/dist/bin/next`.
Poprawiony pomiar readiness zapisuje osobny wynik i czas każdego żądania,
również błąd, bez odziedziczenia poprzedniej odpowiedzi.

Niezależny audyt danych, liczników, retry i nowych usług PASS bez P0–P2.
Końcowy odbiór przeglądarkowy na rzeczywistym Admin3000 PASS: wszystkie
osiem symboli oraz „Nierozpoznany”, „Poza zdjęciem” i „Wszystkie” w filtrze;
20 kafelków bez obrazu z numerem planszy, pozycją i badge’em. Po zaznaczeniu
aktywne „Zmień symbol” i „Nieczytelny”; grafika symbolu i „Niewyraźny”
wyłączone z informacją o braku obrazu. Kontekst planszy61882/pole1 poprawnie
wyświetla źródło, siatkę, kolumnę poza zdjęciem i wyróżnienie pola.
Nie wysłano żadnej decyzji zmieniającej dane; zaznaczenie wyczyszczono.

## Odczytowy audyt pozostałych gier

| Gra | Plansze | Istniejące pozycje | Brakujące | Dostępność | Blokery |
|---|---:|---:|---:|---|---:|
| mumie (`cf300bc1…`) |26|390|0|390full|0|
| Mumie test (`2a46d3a6…`) |0|0|0|brak pozycji|0|

Obie strony zwróciły brak dalszego kursora; audyt obejmuje wszystkich
aktywnych właścicieli tych gier. Nie wykonywano ich uzupełnienia ani
odbudowy liczników.

Odrębnie potwierdzono odczytowo znane6 plansz777 poza listą pilota:
225930(12 pozycji),225933(13),225939(12),225942(14),225948(13),225957(13).
Pozostaje tam13 brakujących pozycji. Nie należą do zatwierdzonego apply70
i nie zostały uzupełnione; dalsze uzupełnienie wymaga wskazania zakresu.
