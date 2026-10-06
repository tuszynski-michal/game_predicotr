---
title: Aplikacja V3 — rejestr ekranów i potrzebnych funkcji
status: draft
last_updated: 2026-10-07
---

# Aplikacja V3 — rejestr przeglądu funkcjonalności

## Cel i sposób prowadzenia

To powierzchowny rejestr do kolejnych rozmów o ekranach. Nie jest planem
wdrożenia wszystkich pozycji. Obecne zachowanie, polecenia użytkownika i
propozycje są rozdzielone. Konkretna zmiana dostanie osobny plan/task i
odnośnik w kolumnie „Realizacja”. Sekcje przenosimy albo usuwamy dopiero
po przejrzeniu danej pozycji. Zachowujemy historię i dane siódemek.

Słownik statusów: **działa** — sprawdzone w kodzie lub odbiorze;
**potrzebne** — wymaganie użytkownika; **propozycja** — do omówienia;
**wycofane** — ukryte w nowych importach, technicznie zachowane do historii.
V3 oznacza tu import Mumii z siecią neural_grid, nie historyczną strukturalną
politykę o technicznej nazwie structured_lattice_v3.

Instrukcja korzystania: [Mumie w głównej aplikacji](../guides/MUMIE_MAIN_APP_OPERATOR_GUIDE_20261006.md).
Źródła reguł: [Admin](ADMIN_APP.md), [import](IMAGE_INGESTION.md),
[uczenie modeli](SUPERVISED_MODEL_IMPROVEMENT.md).

## Import i Zarządzanie planszami

Obszar nazywany przez operatora „Zarządzanie planszami” jest obecnie zbiorem
sekcji wybranej gry w **Zarządzaniu grami**. TASK-0887 zmienił wybór/opis
silnika. TASK-0890 przenosi diagnostykę siatek z importu do korekty zgodnie
z kolejną decyzją operatora; pozostałe pozycje czekają na przegląd.

| ID | Obecna funkcja | Potrzeba w V3 / proponowana zmiana | Status | Realizacja |
| --- | --- | --- | --- | --- |
| IMPORT-01 | Wybór silnika przed folderem | Mumie: V3 widoczny z profilu gry. 777: V1.1 zachowany. V1.0/V1.2 ukryte, oznaczone do usunięcia; historia pozostaje. | działa / wycofane | TASK-0887 |
| IMPORT-02 | Wybierz folder, przesyłanie JPEG, trwały staging | Zachować. Cały wskazany folder, bez sztucznego limitu 100; rozmiar partii wybiera operator. Sekcja „Przesłane foldery” odzyskuje listę po restarcie i pokazuje błąd/ponowienie. | działa / naprawione | D-523, TASK-0889, instrukcja |
| IMPORT-03 | Pokaż raport, Przygotuj geometrię stron | Zachować jawny preflight i start. Docelowo przedstawić jako proste etapy: folder → analiza → import → weryfikacja. | działa / propozycja układu | osobny task po przeglądzie |
| IMPORT-04 | Detekcja wielu plansz i zakres seq_* | Zachować kolejność oraz liczbę z potwierdzonej nazwy; nie dopisywać brakującej planszy ani przesuwać kolejnych numerów. Niepewny zakres/binding do korekty źródła. | działa | D-523 |
| IMPORT-05 | Przygotowanie pełnych siatek 3×5 i cropów | Automatycznie udostępniać pełne, przypisane siatki w weryfikacji symboli; bez ręcznego zatwierdzania każdej planszy. Braki i częściowe do korekty. | działa | D-523 |
| IMPORT-06 | Edytor zdjęcia i numeracji przed importem | V3 pokazuje propozycje sieci, nie obowiązkowe błędy. Pełne siatki idą do importu bez akceptacji każdej planszy. Zachować edytor dla niejednoznacznego przypisania numerów; cięcie pojedynczej planszy poprawiamy po imporcie. | naprawiona prezentacja | D-526, TASK-0891 |
| IMPORT-07 | Dopasowanie geometrii zdjęcia: Standardowe v0.10 / Obszar plansz — testowe | Ukryte dla Mumii V3 na prośbę użytkownika. Zachowane dla klasycznej geometrii V1.1; wybrany wariant nadal trafia do jej preflightu. | wdrożone | TASK-0889 |
| IMPORT-08 | Brakujące plansze, diagnostyka siatek zdjęć | Raport brakujących numerów zostaje w imporcie. Diagnostyka zdjęć przeniesiona do Korekty cięcia siatki; opis uwzględnia D-523. Historyczne liczniki całego zdjęcia nie mierzą dostępności wszystkich cropów V3. | przeniesione; semantyka liczników zachowana | D-525, TASK-0890 |
| IMPORT-09 | Ponowne przetwarzanie z oryginałów, kontynuacja korekty | Zachować wznowienie i ochronę ręcznych decyzji. Ukryto osobne wymuszenie V1.0. Diagnostyka pozostaje w szczegółach. | działa / wycofane V1.0 | TASK-0887 |
| IMPORT-10 | Źródła tej samej sekwencji, ranking, ręczny wybór | Zachować możliwość wyboru lepszego zdjęcia dla tego samego numeru. Propozycja: przesunąć do narzędzi naprawy/diagnostyki. | działa / propozycja układu | do przeglądu |
| IMPORT-11 | Paczki z Selekcji zdjęć i import kolejnych partii | Przejrzeć przy dużych folderach. Nie tworzyć drugiego pipeline V3; sprawdzić obsługę tego samego profilu i checkpointów przed rozszerzeniem. | do przeglądu | osobny task, jeśli potrzebny |
| IMPORT-12 | Usuń plansze, Wyczyść dane plansz gry, Usuń nieużywany staging | Zachować oddzielne preview i zgodę. Propozycja: przenieść operacje destrukcyjne do utrzymania, oddzielnie od zwykłego importu. Bez usuwania dziś. | propozycja układu | do przeglądu |

## Symbole, korekty i uczenie

| ID | Obecna funkcja | Potrzeba w V3 / proponowana zmiana | Status | Realizacja |
| --- | --- | --- | --- | --- |
| MODEL-01 | Katalog symboli gry i obrazy referencyjne | Zachować tożsamość, kolejność i flagi. Rozdzielić flagi zasad gry od bazowej klasy graficznej. | działa / potrzebne | ekran Symbole |
| MODEL-02 | Globalna Weryfikacja symboli z wyborem gry | Główny szybki przepływ: grupy, do 2000 cropów, korekta lub zatwierdzenie wielu naraz. Zapis zamraża stronę do odświeżenia. | działa w Mumii | D-523 |
| MODEL-03 | Zła siatka → Korekta cięcia siatki | Kolejka korekty, odroczone geometrie i diagnostyka zdjęć w jednym miejscu. Zmieniamy cięcie tylko przy błędzie pikseli. Dobrze wycięty zły symbol poprawiamy bez ruszania siatki. | działa / diagnostyka przeniesiona | D-525, TASK-0890, instrukcja |
| MODEL-04 | Weryfikacja symbolu na planszy | Zachować jako wyjątek dla nieczytelnych pojedynczych cropów. To nie obowiązkowe zatwierdzanie wszystkich plansz. | działa | do przeglądu położenia |
| MODEL-05 | Jakość rozpoznawania → Ulepsz rozpoznawanie | Zachować wspólną pulę zatwierdzeń z wielu uploadów, trening kandydata, raport, osobną aktywację i przeliczenie pending. | działa | istniejący pion uczenia |
| MODEL-06 | Ulepsz cięcie siatki | Obecnie kalibracja klasycznego profilu, nie trening sieci V3. Potrzebna osobna czytelna obsługa snapshotu 24 punktów, treningu i oceny sieci z panelu. Nie udawać, że obecny przycisk to wykonuje. | brak funkcji V3 w panelu | przyszły osobny plan/task |
| MODEL-07 | Różne foldery z różnych filmów | Potrzebny trwały identyfikator nagrania i kontrola niezależnego testu. Obecny trening DB dzieli całe zdjęcia; nie gwarantuje podziału po filmach. | potrzebne | przyszły task |
| MODEL-08 | Złota ramka i supergra Mumii | Oddzielić bazowy symbol, flagę złotej ramki i symbol wybrany na serię darmowych gier. Ręczny wybór symbolu serii po ≥3 mumiach jest kierunkiem użytkownika; licznik/retrigger wymagają osobnego dopracowania. | potrzebne, poza dzisiejszym zakresem | osobny plan |
| MODEL-09 | Osobne Laboratorium w głównej aplikacji | Zakładka dla rodzin modeli i przypisanych gier: dane z prawdziwej bazy, uczenie siatek i symboli, raporty, rejestr wersji i aktywacja. Zgodne gry mogą wspólnie dostarczać zatwierdzenia. Udany trening zapisuje kandydata w głównej bazie. | wymaganie użytkownika 2026-10-07; niewdrożone | D-526, D-527; osobny pion integracji |
| MODEL-10 | Wybór profilu Mumie / 777 v2 przy tworzeniu gry | Rozwinąć w katalog ocenionych i jawnie opublikowanych modeli. 777 v3 i 777 v4 mogą używać jednej rodziny i tych samych wag, wspólnie rozwijając kolejne wersje. Dane plansz i reguły gier pozostają osobne. | zaakceptowany kierunek; katalog modeli i wspólne uczenie niewdrożone | D-527, TASK-0892; wymagania i architektura uczenia |

### Laboratorium — zaakceptowany kierunek, jeszcze bez implementacji

Operator wybiera rodzinę modelu oraz **cięcie siatek** albo **rozpoznawanie
symboli**. Rodzina może obsługiwać wiele zgodnych gier, np. 777 v3 i 777 v4.
Dane treningowe pochodzą z zapisanych korekt i zatwierdzeń przypisanych gier;
predykcje nie stają się automatycznie etykietami. Mumie i 777 pozostają
odrębnymi rodzinami. System pokazuje pochodzenie danych per gra, nowe
przykłady, pokrycie klas, niezależny zbiór oceny i postęp trwałego zadania.

Po treningu aplikacja rejestruje wersję kandydującą w **głównej bazie**:
rodzina, gry źródłowe, rodzaj modelu, wersja, kohorta/snapshot, metryki,
status oraz ścieżki i checksumy niezmiennych artefaktów. Wagi pozostają
plikami, nie dużymi blobami w tabelach domenowych. Utracona odpowiedź lub restart nie tworzy
drugiej wersji i nie gubi wyniku. Niekompletny/błędny trening nie staje się
gotowym kandydatem. Po ocenie i jawnej publikacji model pojawia się na liście
przy tworzeniu gry. Nowa gra może użyć istniejącej rodziny i wersji bez
ponownego treningu. Aktywacja dla wskazanych istniejących gier pozostaje
oddzielną decyzją po porównaniu z bieżącą wersją; poprzednia wersja służy do
powrotu. Publikacja nie zmienia rozpoczętych importów ani ręcznych decyzji.

Zgodność wymaga kontraktu klas, jawnego mapowania symboli i zgodnej geometrii,
nie podobnej nazwy gry. Dane plansz, kolejność, payouty i reguły pozostają
osobne. Podział i wyłączenia kontrolne obejmują całą rodzinę, także źródła
powtórzone w innej grze. Szczegóły:
[wymagania](SUPERVISED_MODEL_IMPROVEMENT.md#docelowe-rodziny-modeli-i-katalog-przy-tworzeniu-gry--d-527),
[architektura](../architecture/SUPERVISED_MODEL_IMPROVEMENT.md#docelowy-rejestr-rodzin-współdzielonych--d-527).

Istniejący panel Ulepsz rozpoznawanie i registry symboli są podstawą do
integracji, nie należy tworzyć drugiego pipeline. Obecne plikowe laboratorium
oraz eksport sieci cięcia wymagają adaptacji do głównego cyklu zadań i rejestru.
TASK-0891 i TASK-0892 zapisują ten zakres, ale nie dodają jeszcze zakładki,
katalogu modeli, wspólnego buildera kohort ani migracji.

## Pozostałe sekcje i ekrany — do wspólnego przeglądu

| Ekran | Co jest potrzebne / co przejrzeć | Status |
| --- | --- | --- |
| Zarządzanie grami | Tożsamość gry, profil V3/V1.1, statusy. Karta Mumii nadal pokazuje gotowość klasycznej wspólnej geometrii i tekst o pierwszej ręcznej korekcie; docelowo oddzielić ten stan od gotowości sieci. | zachować; poprawka prezentacji do przeglądu |
| Wyszukaj plansze | Zachować wyszukiwanie po symbolach, sekwencji i wybór źródła; przejrzeć położenie względem weryfikacji. | działa / do przeglądu |
| Reguły | Zachować wymiary, linie wypłat, payouty i wersjonowanie. Oddzielić konfigurację zasad od procesu uczenia. | działa / do przeglądu |
| Joby | Zachować postęp, błąd, wznowienie. Propozycja: czytelny stan w głównym przepływie i techniczne szczegóły tutaj. | do przeglądu układu |
| Selekcja zdjęć, Ręczna selekcja, Semi-auto selekcja | Przejrzeć, czy nadal potrzebne jako osobne zakładki i które procesy przygotowania zdjęć są współdzielone przez gry. | bez usuwania; do przeglądu |
| Kalibracja etykiet V7 | Oddzielny proces siódemek/OCR. Nie uruchamiać ani usuwać przy Mumii. Ocenić przyszłe położenie w narzędziach starszej gry. | zachować do przeglądu |
| Pamięć i czyszczenie | Zachować raport, preview, retencję i zgodę. Oddzielić dane treningowe/model od odtwarzalnych wyników i baz testowych. | potrzebne |
| Wersje Android | Poza bieżącym importem i modelem; przejrzeć po ukończeniu ekranów operatora. | poza tym etapem |
| Laboratorium na 3102 | Środowisko eksperymentów. Docelowo osobna zakładka w głównej aplikacji zgodnie z MODEL-09; zapisane kandydaty i ich raporty należą do głównej bazy. | integracja wymagana; jeszcze niewdrożona |

## Oddzielny panel weryfikacji online — kierunek użytkownika

Panel ma być osobną aplikacją możliwą do udostępniania dla wielu gier.
Potrzebne: wybór gry i przydzielonej kolejki, szybkie symbole, korekta siatki,
widoczny zapis/postęp, wznowienie szkicu i obsługa konfliktów rewizji.
Backend pozostaje właścicielem danych i kontraktu; oba panele powinny
korzystać z tego samego API i wspólnego edytora, bez kopii logiki silnika.

Na późniejszym przeglądzie ustalimy zakres uprawnień, logowanie,
udostępnianie i dostęp do obrazów. Nie wystawiono lokalnego Admina ani jego
API do internetu i nie wdrożono nowego panelu w TASK-0887.

## Retencja i miejsce — podgląd 2026-10-06

Odczyt katalogu PostgreSQL i metadanych plików; żadnego usunięcia ani kopii.
Wartości są w GB dziesiętnych i obejmują indeksy/TOAST, nie tylko rekordy.
Dokładny raport: artifacts/app-v3-review-20261006/storage-inventory.json.

| Obiekt | Zmierzony rozmiar | Decyzja / potrzebny następny krok |
| --- | --- | --- |
| Główna baza game_predictor | 51,73 GB | Chroniona; nie czyścić całości. |
| Partycje gry 777 w głównej bazie | 48,16 GB | Zachować. To istniejące dane siódemek, nie Mumie. |
| Partycje gry Mumie w głównej bazie | 0,071 GB (71 MB) | Zachować źródła, poprawki, symbole, modele i powiązania. |
| Testowa mumie_0884_restore_20261006_155101_test | 46,97 GB | Największy kandydat. Pozostała po zaliczonym odtworzeniu backupu; przy odczycie zero połączeń. Przed usunięciem potwierdzić dokładną nazwę i zakończenie użycia testowej bazy. |
| game_predictor_v7_pilot | 0,117 GB | Aktywna, 3 połączenia; wyłączyć z propozycji czyszczenia Mumii. |
| Trzy bazy testów TASK-0518/0519 | łącznie 0,057 GB | Niewielki zysk; pochodzenie i brak użycia sprawdzić osobno. Nie kwalifikować na podstawie samej nazwy. |
| public.image_pipeline_stage_results | 0,441 GB całej tabeli | To górna wielkość tabeli, nie obietnica odzysku. Istniejący preview kompaktacji kwalifikuje tylko odtwarzalne payloady i chroni referencje. |
| Backup na D: | 13,60 GB | Zachować. Zaliczone odtworzenie i przeniesienie zapisane w receipt; obecny plik ma zgodny rozmiar. Nowej pełnej kopii nie tworzono. |

Największe tabele głównej bazy: rewizje predykcji 17,40 GB, komórki review
13,13 GB, manifesty renderu 7,25 GB. Rozmiar nie oznacza zbędności — zawierają
żywe i historyczne dane. Do osobnej analizy retencji, nie masowego DELETE.

C: ma około 32,16 GiB wolnego, D: około 48,71 GiB. Docker VHDX ma 106,04 GB.
Usunięcie testowej bazy zwolni miejsce wewnątrz Dockera; plik VHDX może
pozostać tej samej wielkości. Rzeczywisty odzysk miejsca Windows wymaga
oddzielnego kontrolowanego kompaktowania i pomiaru. Nie wykonano VACUUM FULL,
kompaktowania ani zatrzymywania bazy.

Reguły wykonania: [utrzymanie bazy](../guides/DATABASE_MAINTENANCE.md).
Osobny preview i konkretne potwierdzenie poprzedzają operację destrukcyjną.

## Dalsze prowadzenie dokumentu

Podczas następnego przeglądu wskazujemy ekran oraz ID pozycji. Zapisujemy
decyzję: zostaje, przenosimy, upraszczamy, ukrywamy lub usuwamy. Po uzgodnieniu
dopisujemy link do osobnego planu/tasku i po wdrożeniu wynik. Nie tworzymy
z góry szczegółowych tasków dla nieomówionych zmian układu.
