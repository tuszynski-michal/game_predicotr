---
title: Laboratorium geometrii i symboli — wymagania
status: accepted
last_updated: 2026-10-05
---

# Laboratorium wizji

## Wersja referencji etykiet po korektach geometrii (D-496)

Jawnie zaakceptowana wersja `lab-symbol-label-reference-v1` pozwala etykietować
przypięte, aktualnie zatwierdzone zdjęcia mimo stale dawnego splitu geometrii.
Nie zastępuje splitu ani zgód. Zachowuje oryginalną historię, receipts, słownik,
role i historyczne użycie, bez ponownego nadania zgody przez narzędzie.
Chronione role i całe komponenty z dawnych oraz aktualnych powiązań pozostają
niedostępne przed odczytem pikseli. Zmiana geometrii, katalogu lub aktywnego
słownika zatrzymuje wersję; operator potrzebuje nowego jawnego preview.
Ta referencja nie kwalifikuje danych do treningu, nie nadaje verified i nie
tworzy podziału symboli. Bez konfiguracji obowiązują dotychczasowe guardy.

## V3-D — shadow w aplikacji (D-495, TASK-0805)

Jawnie uruchomiony etap porównuje na tym samym niezmiennym zdjęciu 5 × 3
obecną geometrię i propozycję sieci. Domyślnie jest wyłączony. Operator
uruchamia ograniczony job dla 1–20 zmaterializowanych źródeł; staging nie
jest materializacją. Historyczna nazwa/wydanie gry ani brak słownika symboli
nie blokują samego porównania.

Propozycje i powody są zapisane oddzielnie z wersją modelu, SHA obrazu i
rewizjami. Każda wymaga ręcznego przeglądu; niekalibrowane Mumie nigdy nie
dziedziczą pewności runu1. Brak siatki nie usuwa aktywnego slotu. Dodatkowe
wykrycie nie zwiększa liczby slotów wynikającej z poświadczonego zakresu.
Rozbieżne metadane mają błąd, bez cichego ograniczenia numerów.

Admin pokazuje pełne węzły i obecną siatkę; aktualny slot można otworzyć w
istniejącej korekcie Reviewera. Jeżeli edytor odtwarza siatkę z narożników,
oznacza ją jako szkic do korekty, nie pełną zaakceptowaną siatkę sieci.
Zmiana SHA/revision oznacza stale i blokuje przekazanie starej propozycji.
Start, odczyt i worker shadow nie zmieniają geometrii ani decyzji symboli.

Migracja, aktywacja, przebieg na danych i odbiór skali pozostają osobne.
Kontrakt: `delivery/GRID_V3_SHADOW_CONTRACT_20261005.md`.

Hybryda D-457 jest jawnym wariantem podglądu, nigdy nowym domyślnym silnikiem.
Poprawia obrazowe propozycje baseline zamrożonym MobileNetV3-Small i uczoną
głowicą narożników. Ręczne węzły służą wyłącznie targetom i ocenie; nie tworzą
cropu wejściowego. Brak anotacji oznacza unknown, nie absent; brak presence-head
i kalibracji oznacza, że każda poprawna propozycja wymaga ręcznego przeglądu.
Nie dopełnia się wyniku do dziewięciu plansz. Nieobsługiwane 3 × 3 pozostaje jawne.

Pilot wykorzystuje wyłącznie development/validation; wybór modelu na zdjęciu
final_test/unseen jest blokowany przed dekodowaniem. Najlepsza ukończona epoka
jest wybierana stałą metryką walidacyjną z karą za brak lub nieważną propozycję,
nie tylko na łatwych dopasowanych planszach. Raport rozróżnia rzeczywiste węzły
baseline od początkowej homografii hybrydy oraz ujawnia brak poprawy.
Jedna próba smoke i jeden niezależny trening zachowują budżety D-457;
walidacja, eksport ONNX, kontrola zgodności i publikacja należą do tego samego limitu.
Sukces i odczyt wymagają zgodnych checksum artefaktów. Galeria pokazuje wybraną
epokę i informację o niekalibrowanej bramce, bez automatycznych zatwierdzeń.

T04 dostarcza trwały backend runów z idempotentnymi start/cancel/retry i historią
prób. Najwyżej jeden run jest aktywny. Restart obserwuje żywy proces, a nie
uruchamia drugiego. Wygasły run po potwierdzonej śmierci procesu wymaga jawnego
retry, które zachowuje budżet oraz checkpoint. T05 dodaje zamknięty rejestr
hybrydy; nieznany wykonawca jest jawnym błędem, nie pozornym sukcesem.

Checkpoint v2 wznawia na granicy ukończonej epoki. Cancel kończy pracę po takim
checkpointcie; twardy limit czasu może przerwać epokę i pozostawia ostatnią
ukończoną. Kroki rezerwuje się przed obliczeniem, a niepotwierdzony czas po
awarii nalicza konserwatywnie. Retry nie zwraca budżetu. Odczyt checkpointów
v1 jest zgodnościowy i jawnie nie gwarantuje identycznego wznowienia.

D-456 dopuszcza osobny pilot geometry-only 5 × 3 z całymi grami przypisanymi
do rozłącznych development/validation/final_test/unseen_game. W tej jawnej
polityce nie wymaga się verified rodzin wewnątrz gry ani pomiaru czasu.
Nie zmienia się pochodzenia rodzin i nie twierdzi, że są niezależne. Pełny
graf wszystkich źródeł musi pozostać wewnątrz przydziałów gier; każde znane
powiązanie przecinające części blokuje cały zapis. Wybrane targety nadal
wymagają aktualnych zgód, ręcznej pełnej geometrii, SHA oraz D-453 dla 777.
Stare polityki i ich wymagania poniżej pozostają bez zmian. Pilot nie mierzy
jakości 3 × 3, symboli, oszczędności czasu ani gotowości produkcyjnej.

Doprecyzowanie użytkownika przy wznowieniu etapu B: zapisane i zaakceptowane
siatki są referencją geometrii plansz, a nie zatwierdzeniem symboli. Część
zdjęć lub ich oznaczeń symboli może być niepoprawna. Brak poprawnej etykiety
symbolu sam w sobie nie wyklucza poprawnej geometrii z jej uczenia; etykiety
symboli nie są targetem etapu B i wymagają osobnego zatwierdzenia w etapie C.
Operator ocenia wybrane geometrie jako poprawne lub w większości poprawne,
nie jako bezbłędny zbiór. Kontrola techniczna nie zastępuje oceny wizualnej;
wykryty błąd geometrii wyłącza daną próbkę do poprawy i ponownej akceptacji,
bez automatycznego poprawiania ani nadpisywania decyzji operatora.

Szybki przegląd pokazuje jedno pełne zdjęcie ze wszystkimi zapisanymi siatkami
(linie i numery) bez galerii, rodzin i edytora. Dwa główne przyciski:
Zatwierdź/Odrzuć, po potwierdzonym zapisie następne. Kolejka stabilna według
katalogu wybranej gry/wszystkich, tylko full/present bez accept/reject/needs_correction.
Odrzucenie całego zdjęcia oznacza Do poprawy bez zmiany geometrii i bez
oznaczania wszystkich plansz. Edycja/mark/withdraw nie usuwa odrzucenia;
kasuje je dopiero jawna akceptacja spełniająca zwykłe warunki. Brak wymogu9.
Decyzja dotyczy wyświetlonych wersji i źródła po załadowaniu zdjęcia; błąd
obrazu blokuje oba przyciski. Pending blokuje wyjście i zachowuje retry.

Przegląd zdjęcia pokazuje numerowane zapisane siatki oraz cropy wybranej planszy.
Przegląd zapisanych plansz na całym zdjęciu jest przy wejściu domyślnie
zwinięty; użytkownik może ręcznie rozwinąć lub zwinąć go nagłówkiem.
Operator może oznaczyć wybrane plansze „Do poprawy” z opcjonalną uwagą lub
wycofać błędne oznaczenie. Zapis poprawki daje „Do ponownego sprawdzenia”, bez
automatycznej akceptacji i bez przejścia do następnej planszy. Po sprawdzeniu
poprawek użytkownik klika „Akceptuj całe zdjęcie”, co domyka ich uwagi.
Ta decyzja obejmuje bieżący niepusty zestaw pełnych obecnych geometrii (nie
wymaga9), nie promuje szkiców ani lokalizacji. Needs_correction i poprawki
zapisane wyłącznie jako szkic/lokalizacja blokują akceptację.
Zmiana/dodanie geometrii unieważnia akceptację tylko tego zdjęcia. Stare dane
pozostają nieprzejrzane. Filtry i badge rozróżniają „Do przeglądu”, „Do poprawy”
i „Zaakceptowane”. Akceptacja jest dodatkową bramką splitu, nie uprawnieniem
do treningu ani zmianą roli777 (D-450).

Aktualizacja folderu zdjęć tworzy nowy niezmienny snapshot. Istniejące decyzje
można przenieść wyłącznie do nowego katalogu i tylko gdy każde źródło użyte
w zapisach, timingach i historii zachowuje id, SHA oraz metadane. Zmiana lub
brak takiego źródła zatrzymuje operację. Historia, autorzy, rewizje i zgody
pozostają identyczne; operacja nie zatwierdza nowych zdjęć. Wersja T03c nie
przenosi zbiorów z rodzinami lub podziałem. Rola 777 nie zmienia się przy imporcie.

Galeria pokazuje osobne liczniki zapisanych obecnych pełnych siatek, lokalizacji
i szkiców. Filtry obejmują całą wybraną grę przed podziałem na strony; „Z pełną
siatką” oznacza co najmniej jedną pełną geometrię, nie ukończenie zdjęcia ani
kwalifikację treningową. Pozycje 1–9 i istniejące dalsze zapisy mają jawne statusy.
Kliknięcie pozycji lub numerowanego obrysu na pełnym zdjęciu wczytuje dokładny
zapis wraz z topologią i cropami; brak zapisu pozwala jawnie utworzyć propozycję.
Nawigacja porzuca niezapisane lokalne zmiany bez modalnego pytania i bez
automatycznego zapisu. Nie ma promptu przy opuszczeniu karty. Busy/pending
blokuje nawigację w aplikacji; jawny przycisk odczytu po konflikcie wystarcza
bez dodatkowego potwierdzenia. Zatwierdzenie pozycji 1–8
otwiera kolejną na tym samym zdjęciu; szkic i pozycja 9 pozostają na miejscu.
Pełne zatwierdzenie jest jawnym kliknięciem bez checkboxa; aktor nowych decyzji
geometrii to stały operator. Powiadomienia są wyłącznie toastami w lewym dolnym
rogu (wszystkie rodzaje 4 s, kliknięcie body zamyka, przycisk Kopiuj kopiuje
wyłącznie wiadomość bez zamykania; sukces kopiowania dopiero po jego wykonaniu,
wstrzymanie przy hover/focus/ukrytej karcie). Raporty i instrukcje pozostają w body.

Edytor pokazuje duże zdjęcie po lewej i zwarte cropy aktualnej siatki po
prawej (na małych ekranach poniżej). Po puszczeniu uchwytu odświeża cropy
i dopasowuje kadr do granic siatki z niewielkim marginesem. Podczas gestu
kadr jest stały. Zdjęcie zachowuje perspektywę i współrzędne źródła;
kontrolka przywraca pełne zdjęcie. Numeracja jest mała i stabilna ekranowo,
z wygodnym obszarem chwytania. Preview nie zatwierdza ani nie zapisuje danych.

Lokalna galeria pokazuje dostarczone zdjęcia, siatki i cropy. Użytkownik może
poprawiać, zatwierdzać, trenować i porównywać modele. Obsługuje 5 × 3 i 3 × 3;
integracja z obecną aplikacją obejmuje wyłącznie 5 × 3. Pełne 3 × 3 wymaga
osobnego planu dla modelu danych, review i wyszukiwania. Model startuje
review/shadow, domyślnie wyłączony; D-261 dotyczy późniejszej aktywacji.

Obecny pilot v3 odpowiada na pytanie, czy podejście w ogóle potrafi znajdować
siatki, ciąć plansze i rozpoznawać symbole. Nie jest odbiorem stuprocentowej
jakości ani skali produkcyjnej. Po ocenie wykonalności wolno przygotować nowy
zbiór i wytrenować modele geometrii oraz symboli od początku; obecne etykiety
i checkpointy nie muszą być promowane. Przed produkcyjną aktywacją lub
masowym przetwarzaniem v3 wymagany jest osobny, udokumentowany odbiór
wydajności i trwałości dla przewidywanej liczby gier, zdjęć, plansz i cropów.
Brak tego dowodu albo wynik przekraczający możliwości magazynu lub workera
blokuje wdrożenie, nawet gdy mały pilot jakościowy wypadnie dobrze.

Istniejąca gra i jej wydanie, np. `777 v1.1`, mogą być ocenione przez nowy
silnik v3 bez zmiany tożsamości gry i bez migracji starych wyników. Operator
może uruchomić na tym samym zdjęciu stary silnik i v3, a następnie porównać
oddzielne wyniki geometrii, cropów i (po ukończeniu etapu symboli) symboli.
Wynik wskazuje silnik i wersję modelu; v3 pozostaje review/shadow i nie
nadpisuje v1.1 ani zatwierdzeń człowieka. Brak mapowania symboli danej gry
ogranicza porównanie symboli, lecz nie może blokować samej geometrii v3.
Historyczna rola źródła danych nie może być używana jako blokada inferencji;
zasady dopuszczenia do treningu i etykietowania pozostają osobne (D-461).

D-453 zastępuje ograniczenie D-447 `comparison_only` wyłącznie dla geometrii
historycznego 777: te zdjęcia mają uczestniczyć w uczeniu modelu, aby obsługiwał
przyszłe podobne zdjęcia. Referencją są nowe ręcznie zatwierdzone siatki
laboratorium, bez używania dawnych geometrii silnika v1.1 jako targetów.
Historyczne pochodzenie pozostaje jawne; nie trzeba zmieniać go na 777 V2.
Kwalifikacja wymaga poprawnej i aktualnie zaakceptowanej geometrii oraz
podziału bez przecieku rodzin. Zgoda na geometrię nie zatwierdza symboli
ani nie zmienia ich dotychczasowych bramek.

Decyzja nie modyfikuje istniejących niezmiennych snapshotów ani zapisanych
ról. Jawna kwalifikacja geometrii T03e zachowuje pochodzenie i ważne zgody
na niezmienione źródła; jej techniczny kontrakt określa architektura labu. Sam import
lub przyjęcie zdjęcia nie wykonuje tej zmiany. 777 V2 nadal wymaga deklaracji
użytkownika dla nagrania/rodziny i kontroli konfliktów checksum oraz
podobieństwa. Brak trafienia podobieństwa nie dowodzi niezależności.

Operator deklaruje, że zdjęcia pozostałych pięciu gier z folderu
`C:\Users\tuszy\Documents\game_predictor_traning_set` pochodzą z innych
zakresów/folderów nagrań niż materiał wskazany do dotychczasowych siatek;
ocenia je jako zdjęcia z odległych brzegów nagrań, oddzielone kilkoma
katalogami. To deklaracja pochodzenia, nie dowód wynikający z nazw plików.
Pozostaje techniczne przypisanie źródeł do rodzin i kontrola konfliktów
z dotychczasowym zbiorem. Brzegi tego samego filmu należą do jednej rodziny;
różne foldery nie oznaczają automatycznie niezależnych filmów.
Nierozstrzygnięte powiązania wykluczają zależne próbki do wyjaśnienia.

Oprócz zatwierdzenia DB dopuszcza się `lab_human_approved`: niezmienną
decyzję człowieka z grą, wersją słownika, obrazem źródłowym i SHA-256,
planszą, komórką, rewizją geometrii, dokładnym cropem i SHA-256, etykietą,
rewizją zatwierdzenia i czasem. Zmiana cropa lub geometrii wymaga ponownego
zatwierdzenia nowych pikseli przed treningiem. Predykcja nie jest decyzją.
Zapis laboratoryjny nie podszywa się pod DB review i nie zmienia istniejących
reguł kohorty bazodanowej. Gra bez DB ma lokalną tożsamość i ręcznie
zatwierdzony słownik; rejestracja kandydata wymaga jawnego mapowania do gry
i symboli aplikacji, bez automatycznego tworzenia rekordów.

Anotacja lokalizacji zatwierdza obecność, topologię i narożniki. Pełna
geometria zatwierdza wszystkie węzły i granice komórek. Anotacja symbolu
zatwierdza dokładny crop i klasę. Interpolowana siatka jest propozycją,
nie pełną referencją. `unknown`, nieczytelność i błąd siatki nie są zwykłymi
klasami. Pilot obejmuje do 40 zdjęć na grę z co najmniej 10 rodzin, jeśli są
dostępne, i 30 pełnych siatek na kombinację gra–topologia. Czas mierzy się
na pierwszych 10 zdjęciach. Braki i rozszerzenie zakresu są jawne.

Rodziny nagrań, duplikaty i pochodne obrazu nie przeciekają między train,
validation i test. Przed pierwszym treningiem geometrii zamraża się grę
niewidzianą; symbole tej gry mają osobny podział per gra. Pomiar oszczędności
czasu używa rozłącznych, losowo przydzielonych zdjęć baseline/hybryda;
referencję ocenia się bez informacji o silniku, a przerwa ponad 30 s kończy
aktywny odcinek. Redukcja o 30% jest celem, nie gwarancją.

Jawna kohorta geometrii T03f wybiera wyłącznie źródła targetów. Nieanotowany
alias poza kohortą nie potrzebuje skopiowanej akceptacji, ale nadal uczestniczy
w pełnym grafie rodzin, duplikatów SHA i pochodnych. Cały powiązany komponent
wymaga zweryfikowanego pochodzenia i dopuszczonej roli lub własnej skutecznej
kwalifikacji D-453, z wyjątkiem jawnej polityki D-455 opisanej poniżej.
Akceptacja i pełny ręczny target są wymagane od każdego
wybranego źródła; błąd jednego wyklucza wybrane źródła całego komponentu.
Niewybrany członek nie omija granic gry niewidzianej ani niezależności pomiaru.
Wybór kohorty nie potwierdza rodzin, nie tworzy zgód i nie odblokowuje treningu
przed pozostałymi bramkami T03. Bez jawnej kohorty obowiązuje poprzedni workflow.

D-455 dodaje opcjonalną politykę `lab-geometry-cohort-777-targets-v2` dla
geometry-only z jawną niepustą kohortą. Niewybrane źródło folderowe o dokładnej
nazwie gry `777`, pierwszym segmencie ścieżki `777` i roli `comparison_only`
nie wymaga własnej kwalifikacji geometrii. Pozostaje wyłącznie kontekstem
pełnego grafu, bez zatwierdzenia, targetu ani przypisania. Każde wybrane 777
nadal wymaga własnej skutecznej D-453, zgodnego SHA i rewizji, akceptacji zdjęcia
oraz pełnej ręcznej geometrii. Wyjątek nie obejmuje DB, V2 ani innych
comparison_only. Verified całego komponentu, unseen, pomiar i pełne fingerprints
pozostają obowiązkowe. Pominięcie nowej polityki i istniejące podziały zachowują
poprzednie reguły; wdrożenie nie zatwierdza rodzin ani nie uruchamia treningu.

D-456 stanowi osobny wariant pilota `lab-geometry-whole-game-pilot-v1`.
Jawna mapa przypisuje wszystkie źródła każdej gry do jednej części;
pełny graf duplikatów, rodzin i pochodnych nie może przecinać tych części,
również poza kohortą. Pilot dopuszcza brak decyzji rodziny lub unresolved,
bez awansu do verified i bez pomiaru czasu. Wymaga targetów w każdej z czterech
części oraz aktualnych akceptacji i pełnych ręcznych geometrii wyłącznie 5 × 3.
Wybrane 777 wymagają własnej kwalifikacji D-453; kontekst zachowuje wąski
wyjątek D-455. Błąd dowolnego wybranego źródła odrzuca cały pilot.
To ograniczony test transferu między grami, bez oceny 3 × 3, symboli ani
oszczędności czasu. Dotychczasowe polityki zachowują swoje bramki.

T06a może rozpocząć pracę z pustymi słownikami i etykietami, aby umożliwić
ich jawne zatwierdzanie w laboratorium (D-458). Nie tworzy zgód za operatora
i nie utożsamia zatwierdzonej geometrii z poprawnością symboli. T06b wymaga
rzeczywistych zatwierdzeń oraz spełnienia bramek pochodzenia i podziału
symboli. Ukończenie narzędzi nie zamyka T06 ani nie odblokowuje treningu.
Unknown, unreadable i grid_issue pozostają stanami review, nie klasami.

W formularzu słownika operator wpisuje wyłącznie nazwę symbolu. Nowy wpis
otrzymuje automatycznie stabilne techniczne ID i kod, niewidoczne jako pola
edycji. Poprawka nazwy zachowuje tożsamość wpisu. Inny rodzaj symbolu należy
dodać jako nową pozycję, nie zmieniać znaczenia istniejącej. Zapis nowej wersji
i jej jawne zatwierdzenie pozostają oddzielnymi akcjami; pusta nazwa blokuje
zapis i jest zgłaszana toastem. Istniejące słowniki nie wymagają migracji.

Etykietowanie symboli pokazuje całą zapisaną planszę z jej rzeczywistą siatką
i numerami pól. Pod nią są dokładne cropy oraz kompaktowe selecty w układzie
5 × 3 (3 × 3 dla tej topologii), w kolejności od lewej do prawej, rzędami.
Operator ustala wszystkie 15 albo 9 wyborów i zapisuje komplet jednym
przyciskiem. Oprócz klas słownika może jawnie wybrać nieznany symbol,
nieczytelność albo błąd siatki; brak wyboru nie staje się żadnym z tych stanów.
Aktualne etykiety są odtwarzane, nieaktualne wymagają ponownego wyboru.
Zapis całej planszy jest atomowy i idempotentny; błąd dowolnego pola nie
publikuje części decyzji. Nie ma autosave ani automatycznego przejścia dalej.
Źródła chronione nie mogą ujawnić pikseli również w pełnym podglądzie planszy.

Poczekalnia symboli pokazuje stronicowane, dokładne cropy z zaakceptowanych
zdjęć i aktualnych pełnych geometrii danej gry, także przed utworzeniem
słownika. Brak decyzji albo jej wycofanie daje „Nieprzypisany”; aktualnie
ocenione `unknown`, nieczytelne i błąd siatki nie są nieprzypisane. Po zmianie
geometrii, renderera lub słownika stary wybór wymaga osobnej ponownej oceny.
Operator wybiera jedną lub kilka widocznych miniatur i jedną istniejącą
klasę słownika, po czym zapisuje tylko zaznaczone cropy atomowo. Brak
zatwierdzonego słownika blokuje zapis, ale nie podgląd. Poczekalnia sama
nie zapisuje etykiety, nie uruchamia treningu i nie ujawnia chronionych źródeł.
„Grupa” symboli jest zwykłym wpisem słownika, nie nowym poziomem danych.
Panel pokazuje do 500 cropów na jednej przewijanej stronie, pobierając je
małymi partiami. To limit widoku, nie jednej transakcji: pojedyncze
przypisanie pozostaje ograniczone do 30 świadomie wybranych cropów.
Pod poczekalnią operator może wybrać symbol aktywnego słownika i obejrzeć
wszystkie jego aktualnie przypisane cropy z nazwą źródła, numerem planszy i
pola. Widok jest tylko do odczytu i stronicowany; decyzje nieaktualne po
zmianie siatki, źródła, renderera lub słownika pozostają w poczekalni do
ponownej oceny, nie na liście aktualnych przypisań.
