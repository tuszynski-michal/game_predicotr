---
title: Laboratorium geometrii i symboli — wymagania
status: accepted
last_updated: 2026-09-27
---

# Laboratorium wizji

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
