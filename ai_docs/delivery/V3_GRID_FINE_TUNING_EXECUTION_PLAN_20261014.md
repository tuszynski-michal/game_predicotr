---
title: Doszkalanie geometrii V3 - rewizja 6
status: accepted
last_updated: 2026-10-15
---

# Doszkalanie geometrii V3 — zaakceptowana rewizja 6

## 1. Status i zmiany po audycie

Plan obejmuje geometrię Mumii, 777a2 i przyszłych gier V3: czytelne liczniki, edytor 4/24 punktów, uczenie na zatwierdzonych korektach, wspólny model geometrii oraz kontrolowane ponowne rozpoznanie. Modele symboli pozostają osobne dla każdej gry.

**Status: accepted; implementation authorized.** Operator 2026-10-14 zaakceptował rewizję 6 i zlecił realizację całego planu, wraz z kosztem orientacyjnym 12–28 dni roboczych. Zgoda obejmuje wykonanie i audyty według tabeli, nie automatyczne scalenie, push, migracje operatora, trening ani masowe operacje danych. TASK-1015 utrwalił pięć propozycji D-548–D-552; D-549/D-550/D-552 przyjęto przed zależnymi taskami na podstawie zaakceptowanej instrukcji operatora. D-548/D-551 pozostają proposed do odpowiedniego etapu, bez domniemania wyników jakości.

Uwzględnione uwagi rundy 3:

| Uwaga                                       | Rozstrzygnięcie                                                                                                                                                                                         |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1-7: brak trwałego startu i wznowienia     | Nowy TASK-1015: worktree, aktualny plan, 23 pliki tasków, decyzje, instrukcja wznowienia i commit dokumentacyjny.                                                                                       |
| P1-8: zbyt skrótowe taski                   | Każdy task ma poniżej zakres, zależności, miejsca zmian, kryteria, testy i sposób weryfikacji.                                                                                                          |
| P2-11: ponowne rozpoznanie czeka na trening | Przebieg aktualną przypisaną bazą jest dozwolony. TASK-0999 nie zależy od zakończenia treningu. Nowy kandydat wymaga osobno zaliczonej bramki.                                                          |
| P2-12: zmiana D-480                         | Osobna proponowana decyzja dla doszkalania z korekt: ręcznie zatwierdzone geometrie mogą tworzyć TRAIN; automatyczna akceptacja nie jest etykietą. Historyczne eksperymenty zachowują pierwotne zasady. |
| P2-13: liczba brakujących plansz Mumii      | Aktualna liczba pozostaje nieustalona do pomiaru po unikalnych sekwencjach. Ani obserwowane około 8000, ani oszacowanie około 2000 nie zastępują tego pomiaru.                                          |
| P2-14: baza i wersjonowanie                 | Operator wybrał `main`, następnie jawnie doprecyzował bazę do v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.                                                                                    |
| P2-15: dostępność audytora                  | Dostępność `claude-fable-5-1` potwierdzono raportem Claude rundy 3.                                                                                                                                     |

W trakcie planowania powstał zewnętrzny commit v1.7.360. Zawiera starszy plan, raporty i powiązane wpisy dokumentacyjne. Dlatego TASK-1015 **aktualizuje istniejącą dokumentację w nowym worktree**; nie przenosi już niezacommitowanych dokumentów z głównego checkoutu.

Historyczny przegląd planowania obejmował odczyty dokumentacji, kodu i historii Git bez zmian plików lub danych. TASK-1015 utrwala obecnie dokumentację w niezależnym worktree. Testy aplikacji opisane poniżej pozostają planowane; wyniki faktycznych kontroli dokumentacji zapisuje Outcome TASK-1015.

Dla Claude Code: kolejny audyt może skupić się na zmianach procesowych, pełnych opisach tasków, zależnościach ponownego rozpoznania oraz zgodności z decyzją o bazie. Poprzednie raporty pozostają dowodami dotyczącymi swoich rewizji, bez przepisywania ich werdyktów.

## 2. Wiążące zachowanie produktu

### 2.1. Zakres i ochrona istniejących danych

- Mumie i 777a2 otrzymują te same możliwości aplikacji, lecz przyczyny błędów i jakość modelu mierzymy osobno.
- Współdzielimy wyłącznie geometrię. Katalogi, etykiety, kohorty, klasyfikatory i aktywacje symboli pozostają per gra.
- Historyczna 777, kod `7`, pozostaje archiwalna. Ten plan nie migruje jej do V3 ani nie przetwarza jej danych.
- Usuwamy zatwierdzone pozostałości klasycznego silnika z ekranów V3 i tworzenia nowych gier. Historyczne kontrakty i raporty potrzebne starej 777 pozostają obsługiwane.
- Nowa gra otrzymuje przypiętą opublikowaną wersję domyślną, jeżeli jest dostępna i zgodna. Bez zatwierdzonego default zwykły formularz może utworzyć draft bez assignment; import pozostaje zablokowany do zgodnego przypisania. Zaawansowany wybór jawnej opublikowanej wersji umożliwia utworzenie przypisanej gry.
- Zwykły formularz nie zawiera wyboru modelu ani `shapeGeometryConfiguration`. Backend zapisuje proponowany neutralny format `GameShapeGeometryConfiguration.NEURAL_GRID_V3 = "neural_grid_v3"`, niezależny od rodziny i przypiętej wersji. Ustawienia zaawansowane umożliwiają zgodny wybór/fork, bez zmiany formatu. Tworzenie gry i dostępnego assignment/forka jest atomowe.
- Nowe klasyczne gry są zablokowane; historyczny odczyt/aktualizacja, wszystkie dotychczasowe wartości formatu i istniejące gry pozostają zachowane. Addytywne rozszerzenie CHECK tabeli `games` nastąpi wyłącznie przez Alembic w TASK-0994; bootstrap nie zmienia kodu ani schematu.
- Zmiana wersji domyślnej nie przełącza istniejących gier ani rozpoczętych zadań.
- Brak zatwierdzonej wersji domyślnej blokuje import V3 z wyjaśnieniem.
- Wspólny model powstaje przez doszkolenie jednej wskazanej bazy na danych obu gier. Nie uśredniamy checkpointów.
- Publikacja, aktywacja, trening, historyczny backfill i masowe przetwarzanie są odrębnymi operacjami.

### 2.2. Liczniki

UI rozdziela pięć obszarów:

| Obszar                    | Jednostka i znaczenie                                                                   |
| ------------------------- | --------------------------------------------------------------------------------------- |
| Brakujące plansze         | Unikalne numery sekwencji bez kwalifikującego się wyniku w oczekiwanym zakresie.        |
| Odroczone pozycje         | Sloty zdjęć, dla których silnik nie zapisał użytecznej planszy.                         |
| Zgłoszone błędne siatki   | Plansze oznaczone przez operatora jako wymagające poprawy geometrii.                    |
| Brak akceptacji geometrii | Stan zatwierdzania zdjęcia lub planszy, niezależny od zmierzonej jakości.               |
| Problemy symboli          | Komórki nierozpoznane, nieczytelne, o niskiej pewności lub oczekujące na zatwierdzenie. |

Kategorie mogą się przecinać. Nie wolno sumować ich jako niezależnych braków.

„Dodane plansze” liczymy po unikalnych sekwencjach, uwzględniając aktualne kwalifikujące się wyniki i dane kanoniczne bez duplikatów. Rozpoznanie wszystkich symboli nie jest warunkiem istnienia planszy.

Dla brakującego numeru wskazujemy dominującą przyczynę: trwający import, oczekiwanie na geometrię, częściowe źródło, błąd przetwarzania, odrzucenie, przyczyna nierozstrzygnięta albo brak źródła. Inne przyczyny pozostają w szczegółach.

TASK-1010 uzgadnia rzeczywiste wyniki obu gier z licznikami importu, Reviewera, geometrii i symboli. Przed tym pomiarem nie deklarujemy liczby brakujących plansz Mumii.

### 2.3. Akceptacja silnika

Automatyczna akceptacja rewizji wymaga rozliczenia oczekiwanych pozycji, zgodnej geometrii, poprawnego przypisania sekwencji i zgodnego pochodzenia modelu. Odroczenia, częściowe pozycje, konflikty i aktualne zgłoszenia błędów blokują akceptację objętego nimi zakresu.

Akceptacja silnika ma własne pochodzenie. Nie ustawia ręcznego zatwierdzenia i nie tworzy etykiety treningowej.

Historyczny backfill otrzymuje podgląd osobno dla każdej gry. Po potwierdzeniu:

- aktualizuje stan akceptacji i zapisuje zdarzenie;
- zachowuje payload geometrii, hashe, wycinki i decyzje człowieka;
- przelicza kompletność oraz synchronizuje istniejące projekcje wyszukiwania w jednej transakcji źródła;
- nie uruchamia modelu ani materializacji nowych komórek;
- pomija niejednoznaczne powiązania rewizji z konkretnym powodem.

Liczba niekompletnych zdjęć nie musi zrównać się z liczbą odroczonych slotów.

### 2.4. Edytor

Domyślnie operator przesuwa cztery zewnętrzne rogi. „Dokładna korekta” pokazuje 24 węzły siatki 5×3.

- Przełączenie trybu zachowuje wszystkie współrzędne.
- Przesunięcie całej siatki przenosi wszystkie węzły.
- Ruch rogu przekształca wszystkie węzły homografią między starym i nowym obrysem.
- Osobna akcja wyznacza regularną siatkę z czterech rogów; ma podgląd i cofnięcie.
- Pusty szkic można zbudować z czterech rogów.
- Zapis wymaga poprawnej orientacji i nieprzecinających się komórek.
- Trwały szkic jest przypięty do źródła i rewizji. Nie nadpisuje nowszego stanu serwera.
- Podgląd i zapis używają wspólnych reguł renderowania.

### 2.5. Ponowne rozpoznanie

Domyślny zakres obejmuje zgłoszone błędne siatki i odroczone sloty. Siatki tylko niepotwierdzone oraz wszystkie automatyczne pozostają osobnymi zakresami.

**Przebieg aktualnym modelem przypisanym do gry jest dostępny bez nowego treningu.** Może nie przynieść poprawy; identyczny wynik nie jest raportowany jako naprawa. Użycie nowego kandydata wymaga publikacji i jawnego wyboru zatwierdzonej wersji.

| Stan celu                                             | Działanie                                                                              |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Zgłoszona „Zła siatka”                                | Trwała propozycja do zatwierdzenia. Aktualne wycinki i zgłoszenie pozostają bez zmian. |
| Chroniona geometria lub decyzje człowieka             | Brak automatycznego nadpisania; raport przyczyny ochrony.                              |
| Odroczony slot bez konfliktu                          | Zapis po bramce i ponownej kontroli aktualnego stanu.                                  |
| Niechroniona automatyczna plansza z wybranego zakresu | Zapis po bramce i sprawdzeniu rewizji oraz właściciela.                                |
| Zmienione źródło, rewizja lub właściciel              | Konflikt; brak zapisu starego wyniku.                                                  |

Jedno zdjęcie jest rozpoznawane raz, a zapis obejmuje wyłącznie wybrane cele. Przed szerszym przetwarzaniem wykonuje się pilot do 100 zdjęć i ocenia raport.

Przyjęcie propozycji korzysta z istniejącej ścieżki ręcznej korekty. Dopiero ta akcja zapisuje zatwierdzenie człowieka i zamyka właściwe zgłoszenie. Odrzucenie propozycji nie zamyka zgłoszenia.

Historia symboli pozostaje zachowana. Zmienione piksele wymagają ponownej oceny zgodnie z D-462. Automatyczne operacje nie zmieniają chronionych etykiet ani właściciela danych kanonicznych.

### 2.6. Dane, trening i ocena

Do nowego doszkalania z korekt kwalifikują się aktualne geometrie zatwierdzone przez człowieka: poprawione albo sprawdzone bez zmiany. Mają różne oznaczenie pochodzenia.

- **Grid-only:** pełna zatwierdzona plansza może pochodzić z niekompletnego zdjęcia. Detektor plansz i jego statystyki pozostają zamrożone.
- **Screen+grid:** wymaga pełnej anotacji zdjęcia. Nieoznaczona plansza nie staje się przykładem negatywnym.
- Pierwszy pilot wyklucza częściowe i wyłącznie ekstrapolowane etykiety.
- Podział odbywa się całymi nagraniami, z aliasami między grami, deduplikacją plików/pikseli i wyłączeniami przodków modelu.
- Chronione zbiory `final_test`, `unseen_game`, Reels/Treasure i pozostałe zapisane holdouty nie trafiają do TRAIN.
- Snapshot danych jest niezmienny. Cofnięte zatwierdzenie oznacza zależnego kandydata jako nieaktualnego, bez przepisywania historii.

Minimum technicznego pilota per oceniana gra:

| Rola              | Minimum                                                                |
| ----------------- | ---------------------------------------------------------------------- |
| TRAIN grid-only   | 30 plansz z co najmniej 10 zdjęć                                       |
| VALIDATION        | Co najmniej 15 plansz i 5 całkowicie opisanych zdjęć, osobne nagranie  |
| REGRESSION        | Co najmniej 15 plansz i 5 całkowicie opisanych zdjęć, kolejne nagranie |
| TRAIN screen+grid | Co najmniej 10 całkowicie opisanych zdjęć treningowych                 |

Przy dziewięciu planszach na zdjęciu kontrolne części wymagają po 45 etykiet, więc minimum grid-only wynosi co najmniej 120 plansz z 20 zdjęć. To próg techniczny, nie gwarancja jakości.

Początkowe ważenie korekt względem zatwierdzeń bez zmian wynosi 4:1 jako wersjonowany parametr pilota. Wspólna kohorta równoważy gry i nagrania.

Preset czasu i liczby kroków wynika z raportów wcześniejszych iteracji oraz ograniczonego pomiaru. Trening zachowuje budżet, optymalizator, RNG, sampler i checkpoint po restarcie.

Ocena zaczyna się od oryginalnego zdjęcia, bez podawania poprawnych rogów. Baza i kandydat otrzymują identyczne źródła kontrolne. Raport obejmuje kompletne poprawne zdjęcia, brakujące i nadmiarowe detekcje, błąd geometrii/P95 oraz poprawność komórek. Brakująca plansza nie znika z mianownika.

Publikacja nowego kandydata wymaga braku pogorszenia wymaganych miar w każdej grze i poprawy miary właściwej dla celu treningu na walidacji. REGRESSION nie służy do wyboru checkpointu. Brak porównywalnych danych nie daje PASS.

Historyczna baza zachowuje historyczny raport i ograniczenia; nie otrzymuje fikcyjnego wyniku nowej bramki.

## 3. Baza, utrwalenie planu i wznowienie pracy

### 3.1. Ustalona baza

- **Istniejąca kopia danych operatora:** `D:\game_predictor_backup`, wskazana przez operatora 2026-10-14 jako wystarczająco aktualna. Nie tworzymy nowego snapshotu ani dodatkowego backupu bazy w ramach tego planu. Potwierdzono dostępność katalogu; nie wykonywano odtwarzania. Niezmienne snapshoty kohort treningowych są odrębnymi artefaktami i pozostają wymagane.

- Repozytorium główne: `D:\game_predicotr`.
- Oryginalna baza: `main`, commit `171e23799ebdbee4ed4590a53376bf870c6741c2`, v1.7.360.
- Operator zatwierdził włączenie upstream main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` 2026-10-14; worktree przewinięto fast-forward do tego HEAD przed commitem bootstrapu. Bootstrap utrwalono jako v1.7.367 / `b35a9ee7dadf3da485427f81a84149e63f0b8cfc`; wcześniejszy przydział v1.7.363 zajęła równoległa praca. Nasza akceptacja silnika została przemianowana TASK-1007 → TASK-1017; historyczny ukończony TASK-1007 wykrywania CLI pozostaje bez zmian.
- Worktree wykonawczy: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`.
- Gałąź robocza: `codex/v3-grid-fine-tuning`.
- Wybór `main` dotyczy bazy tego planu. Nie zmienia automatycznie globalnej polityki integracji ani nie upoważnia do scalenia.
- Przed późniejszym scaleniem trzeba przedstawić także odziedziczone różnice względem domyślnej gałęzi integracyjnej `v1.1-vision-lab-hybrid-geometry`.

Przed utworzeniem worktree sprawdzić, czy wskazana ścieżka i gałąź nie należą już do innej pracy. Nie resetować istniejącego checkoutu.

Stan zastany obejmuje odwołania do dwóch innych worktree zapisane w v1.7.360 i zmianę wewnątrz `worktrees/multi-game-share`. Są poza zakresem. Kryterium startu brzmi: **brak nowych zmian tego planu w głównym checkoucie**, a nie wymuszenie globalnie czystego statusu kosztem cudzej pracy.

### 3.2. Dokumenty utrwalane przez TASK-1015

W nowym worktree:

- pełna rewizja 6 zastępuje starszą treść pliku planu;
- raporty Claude z rund 1–3 pozostają zachowane;
- odpowiedź Codexa otrzymuje rozliczenie uwag i zmian rewizji 6;
- README, CURRENT_STATE, inwentarz V3 i TASK-0957 wskazują aktualny zakres;
- powstają 22 pliki tasków funkcjonalnych oraz TASK-1015;
- powstają wpisy `proposed` w Decision Log.

Nowe decyzje opisują:

1. Doszkalanie z ręcznych korekt jako odrębny zakres D-480: dopuszczenie takich danych do TRAIN i wykluczenie automatycznej akceptacji jako samodzielnej etykiety.
2. Wspólną geometrię, domyślny model i zaawansowany wybór wersji — rozszerzenie D-527.
3. Akceptację silnika, historyczny podgląd i statusowy backfill — doprecyzowanie D-484/D-541 z zachowaniem późniejszych wyjątków V3.
4. Propozycje dla „Złej siatki” i zatwierdzenie przez człowieka — zgodność z ochroną D-462/D-543.
5. Bazę i sposób prowadzenia tego planu.

Numery decyzji wybrać po sprawdzeniu aktualnego indeksu. Nie nadpisywać istniejących decyzji ani przedstawiać propozycji jako przyjętych.

### 3.3. Wznowienie w nowej sesji

Każda nowa sesja Codex lub Claude:

1. Weryfikuje worktree, gałąź, HEAD i zastane zmiany.
2. Czyta AGENTS, README, CURRENT_STATE, indeks decyzji i pięć najnowszych wpisów.
3. Czyta aktualny plan, właściwy task i jego `Relevant docs`.
4. Sprawdza zapisany etap wykonania oraz ostatni raport audytu.
5. Potwierdza, że zakres został zlecony i model odpowiada tabeli.
6. Przygotowuje środowisko worktree przed komendami Verification: własne zależności npm i venv albo jawne, sprawdzone junction `.venv` do `D:\game_predicotr\.venv`, zgodnie z praktyką repo. Zapisuje wynik i ograniczenia w Outcome, nie zakłada dostępności środowiska głównego checkoutu z samego istnienia worktree. Przygotowanie nie uruchamia usług.
7. Przed rozpoczęciem każdego taska rozwija jego `Technical notes` o konkretne walidacje, kolejność zapisów/blokad, granice transakcji, błędy/retry oraz dokładne pliki i symbole. Nie powtarza Scope. Stosuje rozstrzygnięcia sekcji 2/4 planu i istniejące kontrakty; niewskazana decyzja biznesowa lub zmiana architektury wymaga jawnego rozstrzygnięcia, bez ukrytych założeń.

Status taska pozostaje jednym z: `todo`, `in_progress`, `blocked`, `done`.

W `Outcome` zapisujemy dodatkowo:

- `Execution phase`: implementacja, weryfikacja, oczekiwanie na audyt, poprawki audytu, gotowe do commita, oczekiwanie na integrację;
- bazowy commit i listę plików taska;
- wykonane kontrole z wynikiem;
- ścieżkę raportu audytu i otwarte identyfikatory uwag;
- dokładny następny krok;
- wersję i hash commita po jego utworzeniu.

Skrypt w zatwierdzonej bazie przekazuje `Effort` tylko do Codex. Dla Claude lead buduje ten sam ograniczony brief przez `scripts/audit_task.ps1 -DryRun`, następnie uruchamia wykryty CLI z jawnymi `--model claude-fable-5-1 --effort medium` albo `high` według tabeli, `--permission-mode plan` i wyłącznie narzędziami odczytu `Read,Glob,Grep`. Launcher przekazuje prompt jako argument i jawnie zamyka stdin (np. `stdin=subprocess.DEVNULL` w Python), tak jak `Invoke-BoundedProcess` oficjalnego skryptu; nie dziedziczy otwartego wejścia terminala. Limit pozostaje 480 s; nadzorca sprawdza także termin według zegara ściennego w krótkich oczekiwaniach (do 1 s), w tym po wznowieniu komputera. Sam długi Windows process.wait może nie rozliczać czasu zawieszenia. Po przerwaniu sprawdzić własny PID i brak osieroconych procesów; brak raportu opisać bez PASS. Wywołanie zapisuje w `artifacts/audits/TASK-NNNN_AUDIT_INVOCATION.json`, a otrzymany raport w wymaganej ścieżce quality. Nie przypina fizycznej wersji instalacji i nie stosuje fallbacku modelu. Brak obsługi żądanego poziomu wymaga rozstrzygnięcia, nie cichego pominięcia. Ten jawny sposób wywołania działa także z nowego procesu i nie jest zmianą skryptu w TASK-1010.

Wykonawca przed audytem zapisuje wyniki kontroli i ograniczony zakres diffu. Audytor ocenia kod tylko do odczytu i zwraca raport według szablonu. Raport z zewnętrznej sesji zostaje zapisany w worktree bez zmiany ustaleń audytora.

Po `REVISE` task pozostaje `in_progress`, z fazą „poprawki audytu”. Otwarte P0/P1 blokują commit. Brak raportu nie jest PASS. Stosujemy zasady repo dotyczące limitu audytu, jednej rundy poprawek i ponownego audytu tylko w wymaganych przypadkach.

Po commicie wykonawca wpisuje pełny hash do taska i CURRENT_STATE. Zgodnie z AGENTS zapis własnego hasha może wejść do następnego commita; do tego czasu te dwie zmiany dokumentacyjne pozostają jawnie opisane. Nie wykonujemy amend tylko po to, aby próbować zapisać hash commita w nim samym.

### 3.4. Wersjonowanie

Po zatwierdzonym włączeniu upstream v1.7.362 bootstrap utrwalono jako v1.7.367 / `b35a9ee7dadf3da485427f81a84149e63f0b8cfc`. Oryginalna propozycja v1.7.361 została jawnie zastąpiona decyzją operatora; istniejących commitów nie renumerujemy. Przed każdym commitem:

- sprawdzić ostatnią wersję na gałęzi roboczej;
- wyznaczyć następny patch;
- sprawdzić, czy inna linia nie użyła go dla innego commita;
- przy kolizji zastosować zatwierdzony automatyczny przydział kolejnego wolnego numeru i zapisać przyczynę oraz mapowanie; zmian zakresu nie rozstrzygać przez renumerację.

Nie renumerujemy istniejących commitów. Analogiczna kontrola dotyczy tasków i decyzji.

## 4. Kontrakty techniczne i miejsca zmian

### 4.1. Rejestr i snapshoty

Proponowany rejestr przechowuje rodziny, niezmienne wersje, pochodzenie, bazę, możliwości/topologię, manifest artefaktów, przypisania gier i zdarzenia publikacji/aktywacji.

Nowy snapshot zadania przypina wersję, manifest, hashe, preprocessing i politykę dekodowania. Stare snapshoty nadal odczytujemy według ich dotychczasowego kontraktu. Worker nigdy nie pobiera zmiennej „najnowszej wersji” podczas wykonywania zadania.

Dostępność plików, dopuszczenie bazy historycznej, zaliczenie bramki nowego kandydata, publikacja i aktywacja są różnymi stanami.

Proponowane `GameShapeGeometryConfiguration.NEURAL_GRID_V3 = "neural_grid_v3"` identyfikuje format/silnik, nie rodzinę checkpointu. TASK-0994 rozszerza enum i CHECK `games` addytywnie przez Alembic, zachowując wszystkie stare wartości bez przepisywania istniejących gier. GameCreate zachowuje dotychczasowy domyślny status DRAFT. Jawnie wskazany status nie jest po cichu zmieniany; dostępność modelu kontroluje import, bez nowej polityki GameStatus.ACTIVE. TASK-1004 pozwala zwykłemu GameCreate pominąć `shapeGeometryConfiguration`; serwer nadaje neutralne V3 i osobno przypina zgodny opublikowany model. Brak default dopuszcza grę unassigned (domyślnie draft), z blokadą importu do assignment; jawny zaawansowany wybór zgodnej opublikowanej wersji może dostarczyć assignment. Gra, assignment i ewentualny fork powstają atomowo, gdy model jest dostępny. Nowe klasyczne tworzenie jest zablokowane, historyczny odczyt/update starej 777 zachowuje dawny kontrakt. Wszystkie te zmiany są projektowane, niewdrożone przez TASK-1015.

### 4.2. Propozycje korekt

Proponowane tabele w magazynie właściwej gry:

- `grid_geometry_proposals`: identyfikator, operacja, źródło, plansza, wersja modelu, dokładne węzły, kwalifikacja, hashe i oczekiwane rewizje;
- `grid_geometry_proposal_events`: zdarzenia utworzenia, przyjęcia, odrzucenia i utraty aktualności.

Unikalność propozycji obejmuje operację i cel. Ponowienie tego samego polecenia odtwarza wynik. Zmieniona treść pod tym samym kluczem jest konfliktem.

Przyjęcie blokuje właściwe źródło i właściciela, sprawdza rewizje, wywołuje istniejący zapis ręcznej korekty i zapisuje zdarzenie przyjęcia w tej samej transakcji. Nieaktualna propozycja zwraca konflikt bez zmiany geometrii.

### 4.3. Granice API i danych

Rozszerzamy istniejące API, zachowując jeden pion: backend → OpenAPI → wygenerowany klient → wrapper → test żądania.

Nowe możliwości obejmują diagnostykę, katalog, przypisania, nagrania, kohorty, trening, ocenę, akceptację historyczną, ponowne rozpoznanie i propozycje.

Mutacje mają klucz idempotencji, hash polecenia i kontrolę rewizji. Powiązania między grami są jawne i ograniczone uprawnieniami; dane jednej gry nie mogą być dostępne przez identyfikator w zakresie innej.

Duże artefakty pozostają plikami. Migracje wykonujemy przez Alembic. Operacje masowe używają stabilnego kursora, krótkich transakcji i trwałych receiptów. Nie ładujemy całego zbioru zdjęć do pamięci.

### 4.4. Mapa sprawdzonych punktów wejścia

Poniższe oznaczenia służą do jednoznacznego wskazywania plików w opisach tasków.

| Oznaczenie | Istniejący plik i symbol                                                                                                                                                                                                                                                                                                             |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| F1         | [board_import_coverage_repository.py](../../services/api/src/game_predictor_api/storage/board_import_coverage_repository.py) — `SqlAlchemyBoardImportCoverageRepository`                                                                                                                                                             |
| F2         | [image_geometry_completeness_repository.py](../../services/api/src/game_predictor_api/storage/image_geometry_completeness_repository.py) — raport i klasyfikacja kompletności                                                                                                                                                        |
| F3         | [image_geometry_completeness_state_repository.py](../../services/api/src/game_predictor_api/storage/image_geometry_completeness_state_repository.py) — `recompute_source_image_geometry_completeness`                                                                                                                                |
| F4         | [board_search_projection_repository.py](../../services/api/src/game_predictor_api/storage/board_search_projection_repository.py) — `sync_review_items`, `stale_review_item_ids`                                                                                                                                                      |
| F5         | [neural_pending_geometry.py](../../services/worker/src/game_predictor_worker/images/neural_pending_geometry.py) — `neural_pending_payload`; konsument: `images/production_workflow.py`                                                                                                                                               |
| F6         | [virtual_grid_geometry.py](../../services/api/src/game_predictor_api/application/virtual_grid_geometry.py) — `VirtualGridGeometryService.save_review_item`, `save_pending_slot`                                                                                                                                                      |
| F7         | [virtual_grid_geometry_repository.py](../../services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py) — `save_virtual_geometry_revision`                                                                                                                                                                      |
| F8         | [image_review_repository.py](../../services/api/src/game_predictor_api/storage/image_review_repository.py) — ochrona decyzji człowieka, licznik korekt                                                                                                                                                                               |
| F9         | [neural_grid_proposal.py](../../services/api/src/game_predictor_api/domain/neural_grid_proposal.py) — `NeuralGridSnapshot`                                                                                                                                                                                                           |
| F10        | [grid_profile_snapshot_resolver.py](../../services/api/src/game_predictor_api/storage/grid_profile_snapshot_resolver.py) — `resolve_neural_grid_proposal`, routing profilu                                                                                                                                                           |
| F11        | [grid_engine_model_store.py](../../services/api/src/game_predictor_api/storage/grid_engine_model_store.py) — `ManagedGridEngineModelStore`; [instalator](../../scripts/install_grid_engine_models.py) — `install_version`                                                                                                            |
| F12        | [jobs.py](../../services/api/src/game_predictor_api/application/jobs.py) — preflight, snapshoty, admission i start zadań                                                                                                                                                                                                             |
| F13        | [board-lattice-state.ts](../../apps/reviewer/src/features/operational-reviews/board-lattice-state.ts) — `boardLatticePayload`, `translatedBoardLattice`; [edytor](../../apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx) — `BoardGeometryCorrectionEditor`, `DeferredBoardCellGeometryEditor` |
| F14        | [board-lattice-draft-storage.ts](../../apps/reviewer/src/features/operational-reviews/board-lattice-draft-storage.ts) — odczyt i zapis szkiców                                                                                                                                                                                       |
| F15        | [model-quality-workspace.tsx](../../apps/admin/src/features/model-quality/model-quality-workspace.tsx) — `ModelQualityWorkspace`, montowanie klasycznego panelu                                                                                                                                                                      |
| F16        | [game-catalog.tsx](../../apps/admin/src/features/games/game-catalog.tsx) — komunikat klasycznej gotowości i formularz                                                                                                                                                                                                                |
| F17        | [game-catalog-state.ts](../../apps/admin/src/features/games/game-catalog-state.ts) — `SHAPE_GEOMETRY_CONFIGURATION_LABELS`                                                                                                                                                                                                           |
| F18        | [neural_grid_training.py](../../services/worker/src/game_predictor_worker/vision_lab/neural_grid_training.py) — `compute_losses`, `train_run`, `evaluate_network`                                                                                                                                                                    |
| F19        | [neural_grid_finetune.py](../../services/worker/src/game_predictor_worker/vision_lab/neural_grid_finetune.py) — `MixedBatchSampler`, `train_iteration`, wybór kandydata                                                                                                                                                              |
| F20        | [checkpoint.py](../../services/worker/src/game_predictor_worker/training_core/checkpoint.py) — zapis, odczyt i odtworzenie checkpointu                                                                                                                                                                                               |
| F21        | [gate.py](../../services/worker/src/game_predictor_worker/geometry_core/gate.py) — `GateThresholds`, `compare`, `decide`, `gate_photo`                                                                                                                                                                                               |
| F22        | [catalog.py](../../services/api/src/game_predictor_api/application/catalog.py) i [schematy katalogu](../../services/api/src/game_predictor_api/schemas/catalog.py) — tworzenie i aktualizacja gry                                                                                                                                    |
| F23        | [symbol_model_snapshot_resolver.py](../../services/api/src/game_predictor_api/storage/symbol_model_snapshot_resolver.py) — `resolve_unclassified_cold_start`                                                                                                                                                                         |
| F24        | [models.py](../../services/api/src/game_predictor_api/storage/models.py) — encje i relacje magazynu                                                                                                                                                                                                                                  |

Nowe pliki wymienione w taskach są **proponowane**. Ich ścieżki podano względem nowego worktree. To nie są deklaracje istniejącej implementacji.

## 5. Weryfikacja wspólna dla tasków

W TASK-1015 utworzono 23 osobne pliki według `TASK_TEMPLATE.md`. TASK-1015 ma status `done` (kontrole i audyt zakończone, zapis commita prowadzi lead); pozostałe 22 taski mają `todo`. Kolejność wykonania wyznacza tabela modeli i zależności poniżej.

Każdy plik zawiera `Outcome`: Changed, Verification results, Not completed, Documentation updates, Recommended next task oraz dane wznowienia z sekcji 3. Wyników nie wpisujemy przed wykonaniem.

Skróty weryfikacji używane poniżej:

- **DOC:** `npm run docs:check`, kontrola kompletności tasków według szablonu, `git diff --check`; przed commitem również `git diff --cached --check` i kontrola staged listy.
- **API:** skoncentrowane testy `pytest`, Ruff i mypy zmienionych modułów; test HTTP oraz `npm run openapi:check` przy zmianie API.
- **WORKER:** skoncentrowane testy `pytest`, Ruff i mypy modułów workera; test zgodności produkcyjnego i laboratoryjnego adaptera.
- **ADMIN:** `test`, `test:geometry`, `lint`, `typecheck` w workspace `@game-predictor/admin`, dobierane do zmienionego pionu.
- **REVIEWER:** analogiczne polecenia w workspace `@game-predictor/reviewer`.
- **MIG:** upgrade i kontrola schematu na izolowanej bazie testowej; weryfikacja zakresu gry i istniejących rekordów. Bez migracji bazy operatora.
- **MAP:** regeneracja mapy po zmianie modułu/publicznego symbolu i `npm run code-map:check`.

Polecenia uruchamiamy z nowego worktree, z jego skonfigurowanym środowiskiem. Przykładowe sprawdzone formy:

```powershell
npm run docs:check
npm run openapi:check
npm run code-map:check
npm run test --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/reviewer
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_neural_grid_proposal.py
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/domain/neural_grid_proposal.py
git diff --cached --check
```

Każde uruchomienie ma twardy timeout, domyślnie do 120 sekund. Szersze testy dzielimy na właściwe zestawy. Dłuższy znany build wymaga zapowiedzi czasu. Audyt ma limit zgodny z AGENTS. Nie uruchamiamy usług ani pełnych przebiegów produkcyjnych jako części tych kontroli.

`docs:check` sprawdza obecnie linki i okno stanu; nie zastępuje kontroli wszystkich sekcji szablonu taska.

## 6. Pełne opisy zadań

### Etap 0 — trwały start

### TASK-1015 — Utrwalenie planu i przygotowanie wznowienia

- **Status:** `done`.
- **Goal / Context:** Przygotować komplet dokumentów wykonawczych dostępnych bez historii czatu.
- **Dependencies / entry conditions:** Akceptacja rewizji planu i osobne zlecenie tego taska; wybrana baza v1.7.360; wolna ścieżka worktree i gałąź.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; ryzyko dotyczy zachowania dokumentów i poprawnego stanu przekazania. Konflikt własności plików zatrzymuje operację.
- **Relevant docs:** AGENTS, PLAN_STANDARD, TASK_TEMPLATE, raport Claude round3, niniejszy plan.
- **Scope / Technical notes:** Utworzyć worktree z przypiętego commita. Zastąpić starszy plan rewizją 6, zachować raporty, uzupełnić odpowiedź Codexa i indeksy. Utworzyć 23 taski z pełną treścią oraz proponowane decyzje. Zapisać ścieżkę, bazę, kolejność i stan wznowienia.
- **Expected files:** istniejące dokumenty planu i raportów w `ai_docs/delivery` oraz `ai_docs/quality`; README, CURRENT_STATE, DECISION_LOG z pełnymi wpisami, inwentarz V3, TASK-0957; nowe `ai_docs/tasks/0993-…` do `1015-…` z wyłączeniem `1007-…` oraz `1017-…`.
- **Acceptance criteria / Test cases:** Nowa sesja z samych plików identyfikuje worktree, aktywny task i następny krok. Wszystkie taski mają model, zakres, pliki, kryteria, testy i Outcome. Raporty historyczne pozostają zachowane. Jeden commit dokumentacyjny, bez kodu i danych.
- **Verification:** DOC oraz porównanie aktualnego planu z rozliczeniem P1-7/P1-8. Test wznowienia jest odczytem dokumentów, bez uruchamiania implementacji.
- **Risks / Out of scope:** Nie czyścić innych worktree, nie zmieniać gitlinków, nie uruchamiać kolejnego taska bez zleconego zakresu.
- **Outcome:** pełne pola z sekcji 5; po commicie dopisać hash zgodnie z zasadą bez samoodwołania.

### Etap A — diagnoza, akceptacja i korekta

### TASK-1010 — Jednoznaczne liczniki i diagnoza obu gier

- **Status:** `todo`.
- **Goal / Context:** Wyjaśnić różnice liczników przez wspólne jednostki i konkretne przyczyny.
- **Dependencies:** TASK-1015; odczyt bazy we właściwym zakresie gry. Brak dostępu blokuje pomiar rzeczywistych liczb, nie testy logiki.
- **Recommended execution:** `gpt-6.1-sol`, `high`; kilka źródeł prawdy i nakładające się stany.
- **Relevant docs:** IMAGE_INGESTION, ADMIN_APP, DATA_MODEL, D-484/D-541/D-543.
- **Scope / Technical notes:** Rozszerzyć istniejący raport pokrycia i diagnostykę, zachowując unikalność sekwencji. Dodać rozkład przyczyn i przecięcia kategorii. Raport Mumii/777a2 zawiera czas pomiaru i zakres danych.
- **Expected files:** F1, F2, F8; istniejące schematy `image_reviews.py`; nowy proponowany `application/grid_diagnostics.py` i panel diagnostyki w Adminie.
- **Acceptance / Tests:** Duplikaty, dane kanoniczne, pending, rejected, deferred i nieznane symbole mają jednoznaczne liczniki. Brak symbolu nie udaje braku planszy. Wszystkie różnice rzeczywistego raportu mają powód albo kategorię nierozstrzygniętą.
- **Verification:** API, ADMIN, DOC; odczyty rzeczywistych danych bez zmian.
- **Risks / Out of scope:** Nie wnioskować o jakości z liczby niepotwierdzonych zdjęć; nie poprawiać danych podczas diagnozy.
- **Outcome:** wyniki uzgodnienia, ograniczenia odczytu i dalsze przypadki wymagające korekty.

### TASK-1017 — Akceptacja nowych wyników przez silnik V3

- **Status:** `todo`.
- **Goal / Context:** Nowa poprawna rewizja otrzymuje właściwy stan akceptacji silnika.
- **Dependencies:** TASK-1010 i akceptacja decyzji doprecyzowującej D-484/D-541.
- **Recommended execution:** `gpt-6.1-sol`, `high`; zmiana kwalifikacji danych produkcyjnych.
- **Relevant docs:** IMAGE_INGESTION, VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP, D-484/D-523/D-541.
- **Scope / Technical notes:** Zastąpić bezwarunkowe `needs_review` oceną kompletu pozycji i pochodzenia. Zachować odrębność engine/human approval. Aktualizacja statusu i projekcji należy do transakcji istniejącego zapisu.
- **Expected files:** F5 i jego produkcyjny konsument, F3; walidatory payloadu geometrii. Nowa proponowana czysta funkcja kwalifikacji akceptacji V3.
- **Acceptance / Tests:** Komplet zgodnych pozycji może zostać przyjęty; deferred, partial, konflikt lub błąd blokuje akceptację. Żaden przypadek nie ustawia ręcznego zatwierdzenia. Stare snapshoty pozostają czytelne.
- **Verification:** WORKER, API; regresje `test_neural_folder_correction_pipeline.py` i produkcyjnego importu.
- **Risks / Out of scope:** Bez historycznego backfillu i bez poluzowania bramki jakości.
- **Outcome:** wersja polityki, pokryte przyczyny i dowody ochrony zatwierdzeń.

### TASK-1008 — Historyczna akceptacja bez ponownego cięcia

- **Status:** `todo`.
- **Goal / Context:** Uzgodnić historyczne statusy przy zachowaniu istniejącej geometrii.
- **Dependencies:** TASK-1017; wykonanie na danych operatora dopiero po podglądzie i potwierdzeniu.
- **Recommended execution:** `gpt-6.1-sol`, `high`; masowa operacja na stanach i projekcjach.
- **Relevant docs:** D-484/D-485/D-541, DATA_MODEL, zasady operacji danych.
- **Scope / Technical notes:** Podgląd, zamrożony zakres, idempotentne uruchomienie, kursor i raport. Dla źródła jedna transakcja: kontrola rewizji, akceptacja, `materialize=False`, synchronizacja istniejących dokumentów wyszukiwania, receipt.
- **Expected files:** F2–F4; istniejący `scripts/backfill_image_geometry_completeness.py` jako wzorzec wznowienia; nowe proponowane `application/grid_engine_acceptance.py`, repozytorium operacji i UI podglądu.
- **Acceptance / Tests:** Awaria między statusem a projekcją cofa całość. Powtórzenie nie dubluje zdarzeń. Wycinki, approval, payloady i właściciele są identyczni przed/po. Mieszane rewizje nie są akceptowane na skróty.
- **Verification:** API, MIG dla nowych zapisów operacji, ADMIN, DOC.
- **Risks / Out of scope:** Bez modelu, recropu i tworzenia komórek; brak automatycznego wykonania na całej grze.
- **Outcome:** dowody niezmienności, podgląd skutków i ewentualne operacyjne wykonanie opisane oddzielnie.

### TASK-0993 — Edytor czterech rogów i 24 punktów

- **Status:** `todo`.
- **Goal / Context:** Przyspieszyć korekty przesuniętej siatki bez utraty dokładnych węzłów.
- **Dependencies:** TASK-1015.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; istniejący kontrakt i ograniczona geometria.
- **Relevant docs:** ADMIN_APP, API_CONTRACT, reguły edytora w tym planie.
- **Scope / Technical notes:** Oddzielić tryb uchwytów od danych. Dodać transformację wszystkich węzłów, przesunięcie całości, jawny reset, undo i konflikt szkicu.
- **Expected files:** F13–F14; testy interakcji Reviewera; opcjonalne rozszerzenie transportu tylko jeśli obecny kontrakt nie przenosi wymaganych danych.
- **Acceptance / Tests:** Roundtrip 24→4→24 zachowuje liczby. Homografia, translacja, reset/undo, błędny quad, dotyk i reload są sprawdzone. Podgląd i zapis mają zgodne wycinki.
- **Verification:** REVIEWER, API przy zmianie transportu, MAP.
- **Risks / Out of scope:** Bez zmiany topologii, danych operatora i klasyfikacji symboli.
- **Outcome:** interakcje, testy regresji i ograniczenia obsługiwanych geometrii.

### Etap B — artefakty, wersje i nowe gry

### TASK-1014 — Zarządzane checkpointy na D

- **Status:** `todo`.
- **Goal / Context:** Uniezależnić użycie baz od jedynej kopii checkpointu na C.
- **Dependencies:** TASK-1015; odczyt manifestów i dostępność miejsca.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; kontrolowana kopia z hashami.
- **Relevant docs:** TASK-0957, VISION_LAB, zasady przechowywania modeli.
- **Scope / Technical notes:** Rozszerzyć instalator o potrzebne artefakty treningowe i receipt pochodzenia. Staging, weryfikacja, atomowa publikacja; wznowienie nie nadpisuje odmiennego pakietu.
- **Expected files:** F11; nowy proponowany manifest receipt kopii i test instalatora. F20 tylko do sprawdzenia odczytu checkpointu.
- **Acceptance / Tests:** Zgodny hash i rozmiar; przerwana kopia wznawia się; obcy katalog nie jest nadpisywany; nowy proces odczytuje bazę z D.
- **Verification:** API/WORKER dla kontraktu artefaktów, test instalatora, DOC.
- **Risks / Out of scope:** Bez usuwania C, kopiowania całego korpusu i wykonywania treningu.
- **Outcome:** źródło, docelowe ścieżki, hashe i receipt; brak zgody na cleanup odnotowany.

### TASK-0994 — Rejestr rodzin, wersji i przypisań

- **Status:** `todo`.
- **Goal / Context:** Zastąpić statyczny wybór wersji trwałym katalogiem.
- **Dependencies:** TASK-1014; aktualne Alembic heads.
- **Recommended execution:** `gpt-6.1-sol`, `high`; migracja i zgodność istniejących gier.
- **Relevant docs:** DATA_MODEL, API_CONTRACT, D-527/D-544.
- **Scope / Technical notes:** Addytywne encje rodzin, wersji, przypisań i zdarzeń. Zarejestrować bazy historyczne bez fikcyjnych kohort i PASS. Przypisania istniejących V3 odzwierciedlają dotychczasowe wersje.
- **Expected files:** F24, `domain/grid_engine_profiles.py`; nowe proponowane `domain/grid_model_registry.py`, `application/grid_model_registry.py`, `storage/grid_model_registry.py`, schema/router i migracja.
- **Acceptance / Tests:** Migracja zachowuje modele obu gier, stara 777 nie otrzymuje neural assignment. Brak artefaktu blokuje udostępnienie. Powtórna rejestracja jest idempotentna. Gra nie odczytuje cudzych danych przez błędny zakres.
- **Verification:** API, MIG, OpenAPI, MAP, DOC.
- **Risks / Out of scope:** Bez aktywacji nowych modeli i migracji bazy operatora.
- **Outcome:** schemat, mapowanie istniejących profili i wyniki migracji testowej.

### TASK-1012 — Dynamiczne snapshoty i spójny routing V3

- **Status:** `todo`.
- **Goal / Context:** Nowe wersje z katalogu działają bez dopisywania do statycznego rejestru.
- **Dependencies:** TASK-0994.
- **Recommended execution:** `gpt-6.1-sol`, `high`; zgodność rozpoczętych zadań i wielu konsumentów.
- **Relevant docs:** IMAGE_INGESTION, API_CONTRACT, D-544, kontrakt snapshotu tego planu.
- **Scope / Technical notes:** Nowa wersja snapshotu oraz czytnik starej. Jeden resolver możliwości dla preflightu, importu, ponownego użycia, workera i własności sekwencji.
- **Expected files:** F9–F12; `storage/image_sequence_canonical_repository.py::uses_neural_grid_pilot`; konsumenci snapshotów w workerze.
- **Acceptance / Tests:** Trzecia rodzina działa; stary job wznawia się po zmianie aktywacji; stary preflight nie uruchamia innej wersji; brak lub zmiana hashy nie powoduje fallbacku.
- **Verification:** API, WORKER, testy snapshotów/resolvera/importu, MAP.
- **Risks / Out of scope:** Bez przepisywania historycznych payloadów i ukrytych aliasów starego profilu.
- **Outcome:** obsługiwane wersje kontraktu i lista zweryfikowanych konsumentów.

### TASK-0998 — Publikacja, aktywacja, domyślna wersja i rollback

- **Status:** `todo`.
- **Goal / Context:** Jawnie kontrolować wersję używaną przez grę i nowe zadania.
- **Dependencies:** TASK-1012. Kontrakt oceny jest wdrożony teraz; realny PASS nowego kandydata dostarczy TASK-0997.
- **Recommended execution:** `gpt-6.1-sol`, `high`; wyścigi aktywacji i niezmienność zadań.
- **Relevant docs:** D-527/D-544, API_CONTRACT, kontrakt rejestru.
- **Scope / Technical notes:** Odrębne polecenia publish, activate, set-default i rollback. CAS przypisania, idempotencja i historia. Bazy historyczne wymagają jawnego dopuszczenia z istniejącym raportem; nowi kandydaci wymagają nowej bramki.
- **Expected files:** moduły rejestru z TASK-0994, F10, API/schema/klient; testy aktywacji i preflightu.
- **Acceptance / Tests:** Dwie konkurencyjne aktywacje nie nadpisują się; brak PASS blokuje nowego kandydata; rozpoczęty job zachowuje wersję; rollback nie zmienia wycinków.
- **Verification:** API, OpenAPI, DOC.
- **Risks / Out of scope:** Bez żywej aktywacji i bez zmiany domyślnej wersji bez decyzji operatora.
- **Outcome:** historia poleceń i dowody rozdziału bazy historycznej od kandydata.

### TASK-1004 — Tworzenie gry z domyślną geometrią V3

- **Status:** `todo`.
- **Goal / Context:** Nowa gra korzysta z opublikowanej geometrii bez treningu od zera.
- **Dependencies:** TASK-0998.
- **Recommended execution:** `gpt-6.1-sol`, `high`; spójny pion tworzenia i izolacja symboli.
- **Relevant docs:** ADMIN_APP, D-527, wymagania cold-start symboli.
- **Scope / Technical notes:** Backend przypina domyślną wersję. Zaawansowany wybór/fork kontroluje zgodność i dziedziczy wyłączenia. Utworzenie gry i przypisania jest atomowe. Format danych strony nie pełni funkcji identyfikatora checkpointu.
- **Expected files:** F16–F17, F22–F23, `game-catalog-actions.ts`; klient i testy żądań.
- **Acceptance / Tests:** Brak default blokuje import; fork nie kopiuje etykiet ani wag. Nowa gra ma własny katalog i cold-start symboli, bez modelu obcej gry. Retry nie tworzy drugiej gry.
- **Verification:** API, ADMIN, OpenAPI, DOC.
- **Risks / Out of scope:** Bez tworzenia rzeczywistych gier i przełączania istniejących przypisań.
- **Outcome:** ścieżka nowej gry i test izolacji symboli.

### TASK-1011 — Usunięcie zatwierdzonych pozostałości V1.1 z V3

- **Status:** `todo`.
- **Goal / Context:** Ekrany V3 pokazują właściwy model i dostępne działania.
- **Dependencies:** TASK-1004.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; ograniczona zmiana UI z regresją starej gry.
- **Relevant docs:** ADMIN_APP, APP_V3_FUNCTIONAL_INVENTORY, D-541/D-544.
- **Scope / Technical notes:** Usunąć klasyczny panel z F15, klasyczną gotowość z F16 i stare opcje tworzenia z F17. Dokładne stare wartości to `framed_full_page_v2` i `requires_clarification`. Zwykły formularz traci również wybór dwóch profili V3 na rzecz default.
- **Expected files:** F15–F17; testy `model-quality-workspace-contract`, `game-catalog-state`, `game-catalog-contract`.
- **Acceptance / Tests:** V3 nie pokazuje klasycznych działań; pokazuje stan przypisanej wersji. Stara 777 nadal poprawnie odczytuje historyczne wartości i raporty.
- **Verification:** ADMIN, DOC; odbiór obu rodzajów gry.
- **Risks / Out of scope:** Nie usuwać historycznych enumów z odczytu API ani backendu klasycznego. Inne pozostałości wpisać do listy decyzji operatora.
- **Outcome:** trzy usunięte miejsca i lista pozostałych zależności poza zakresem.

### Etap C — ponowne rozpoznanie aktualnym modelem

### TASK-0999 — Backend ponownego rozpoznania wybranego zakresu

- **Status:** `todo`.
- **Goal / Context:** Przeliczyć wskazane cele z trwałym postępem i ochroną danych.
- **Dependencies:** TASK-1017, TASK-1012, TASK-0998; bez zależności od treningu.
- **Recommended execution:** `gpt-6.1-sol`, `high`; zapis geometrii, wycinków i kontrola właściciela.
- **Relevant docs:** IMAGE_INGESTION, D-462/D-523/D-543, VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.
- **Scope / Technical notes:** Preview, zamrożony manifest, jeden inference na zdjęcie, zapis tylko wybranych celów. Dla zgłoszeń wynik pozostaje propozycją przekazywaną do TASK-1013. Admission uwzględnia kolidujące zadania geometrii i symboli.
- **Expected files:** F8, F12, istniejące blokady własności i runtime geometrii; nowe proponowane `application/grid_reinference.py`, `storage/grid_reinference.py`, `images/grid_reinference_handler.py` oraz migracja receipts.
- **Acceptance / Tests:** Aktualna baza działa bez treningu. Chronione decyzje pozostają identyczne. Brak środkowego slotu nie przesuwa sekwencji. Restart nie dubluje zapisu; identyczny wynik nie jest „naprawą”.
- **Verification:** API, WORKER, MIG, renderer parity, OpenAPI, MAP.
- **Risks / Out of scope:** Bez automatycznego przejęcia kanonu i uruchamiania pełnej gry.
- **Outcome:** zakres, konflikty, receipts i rozdzielenie zapisów automatycznych od propozycji.

### TASK-1013 — Trwałe propozycje dla „Złej siatki”

- **Status:** `todo`.
- **Goal / Context:** Model przygotowuje korektę, a operator decyduje o jej zastosowaniu.
- **Dependencies:** TASK-0993, TASK-0999.
- **Recommended execution:** `gpt-6.1-sol`, `high`; ochrona zgłoszenia i atomowy zapis decyzji.
- **Relevant docs:** D-462/D-543, API_CONTRACT, schemat propozycji z sekcji 4.
- **Scope / Technical notes:** Wdrożyć tabele propozycji i zdarzeń. Reviewer pokazuje porównanie, przyjęcie, edycję i odrzucenie. Przyjęcie korzysta z `VirtualGridGeometryService.save_review_item`, a nie z usługi samych liczników.
- **Expected files:** F6–F8, F24; nowe proponowane `application/grid_geometry_proposals.py`, `storage/grid_geometry_proposals.py`, schema/router, migracja oraz komponent propozycji w Reviewerze.
- **Acceptance / Tests:** Utworzenie nie zmienia cropów ani zgłoszenia. Przyjęcie działa raz, zapisuje autora i zamyka właściwy problem. Zmieniona rewizja daje konflikt. Odrzucenie pozostawia zgłoszenie otwarte.
- **Verification:** API, MIG, REVIEWER, OpenAPI; integracja rzeczywistej ścieżki zapisu geometrii.
- **Risks / Out of scope:** Automatyczny wynik nie może zostać oznaczony jako ręczny przed decyzją operatora.
- **Outcome:** tabela stanów, dowody idempotencji i stale-proposal conflict.

### TASK-1003 — Podgląd i raport ponownego rozpoznania

- **Status:** `todo`.
- **Goal / Context:** Operator rozumie zakres, koszt i wynik przebiegu.
- **Dependencies:** TASK-0999, TASK-1013.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; gotowy kontrakt backendu.
- **Relevant docs:** ADMIN_APP, D-541, zakresy z sekcji 2.
- **Scope / Technical notes:** Oddzielne liczby zdjęć, slotów, plansz i komórek; domyślny zakres, pilot do 100, jawny szeroki wybór, postęp i wznowienie. Raport rozróżnia propozycje, automatyczne zapisy, ochronę, brak zmiany i konflikty.
- **Expected files:** nowe proponowane `grid-reinference-preview.tsx`, `grid-reinference-report.tsx`, stan i akcje w Adminie; istniejące linki do jobów.
- **Acceptance / Tests:** Stary preview daje konflikt; utrata odpowiedzi odtwarza tę samą operację; zmiana gry nie miesza stanu; wszystkie automatyczne nie są domyślnie zaznaczone.
- **Verification:** ADMIN, test transportu, DOC.
- **Risks / Out of scope:** Frontend nie wylicza samodzielnie kwalifikacji ani zakresu na podstawie jednego licznika.
- **Outcome:** podglądy i raport dla aktualnej bazy oraz przykłady błędów.

### Etap D — dane i pomiar jakości

### TASK-1002 — Nagrania, aliasy i role kontrolne

- **Status:** `todo`.
- **Goal / Context:** Zapobiec przeciekowi między treningiem i oceną.
- **Dependencies:** TASK-0994.
- **Recommended execution:** `gpt-6.1-sol`, `high`; pochodzenie danych między grami i rodzinami.
- **Relevant docs:** VISION_LAB, D-480/D-527, reguły kohorty tego planu.
- **Scope / Technical notes:** Trwałe grupy nagrań, deklaracje operatora, aliasy, byte/pixel SHA, TRAIN/VALIDATION/REGRESSION i wyłączenia przodków. Folder jest sugestią, nie dowodem niezależności.
- **Expected files:** nowe proponowane `domain/source_recording_groups.py`, warstwa application/storage, migracja, API i `recording-groups-panel.tsx`.
- **Acceptance / Tests:** Alias w innej grze zachowuje rolę. Holdout rodzica nie trafia do TRAIN dziecka. Brak deklaracji nie daje niezależności. Role przeżywają restart.
- **Verification:** API, MIG, ADMIN, OpenAPI, MAP.
- **Risks / Out of scope:** Bez przenoszenia plików źródłowych i zmiany sekwencji.
- **Outcome:** pochodzenie grup, nierozstrzygnięte nagrania i blokady kwalifikacji.

### TASK-1009 — Losowa kontrola Mumii i 777a2

- **Status:** `todo`.
- **Goal / Context:** Zmierzyć rodzaje błędów zamiast opierać decyzję o treningu na liczniku.
- **Dependencies:** TASK-1010, TASK-0993, TASK-1002; kontrola operatora jest warunkiem raportu rzeczywistej jakości.
- **Recommended execution:** `gpt-6.1-sol`, `high`; poprawna populacja, próba i interpretacja.
- **Relevant docs:** VISION_LAB, ADMIN_APP, sekcja pomiaru w tym planie.
- **Scope / Technical notes:** Zamrożona losowa próba do 100 zdjęć per gra, pełna kontrola oczekiwanych pozycji, osobny zbiór trudnych przypadków. Wyniki zapisane z wersją i pochodzeniem.
- **Expected files:** nowe proponowane `application/grid_quality_measurements.py`, repozytorium i manifest pomiaru, schema/router oraz panel kontroli; F6 dla zapisanych korekt.
- **Acceptance / Tests:** Ten sam seed i populacja odtwarzają próbę. Trudne przykłady nie zmieniają częstości z próby losowej. Brak pełnej kontroli zdjęcia jest widoczny. Raport rozdziela detekcję, geometrię, symbole i sekwencję.
- **Verification:** API, ADMIN/REVIEWER, test deterministycznego próbkowania, DOC.
- **Risks / Out of scope:** Nie deklarować niezależności filmów bez dowodów ani jakości całej gry na podstawie celowo trudnych przykładów.
- **Outcome:** wynik pomiaru albo jawny stan oczekiwania na anotacje.

### TASK-0995 — Kwalifikacja korekt i niezmienny snapshot

- **Status:** `todo`.
- **Goal / Context:** Dostarczyć trenerowi odtwarzalny zbiór z czytelną listą braków.
- **Dependencies:** TASK-1002, TASK-1009; przyjęta decyzja rozszerzająca D-480.
- **Recommended execution:** `gpt-6.1-sol`, `high`; aktualność etykiet i dane dowodowe.
- **Relevant docs:** VISION_LAB_EXPORT, VISION_LAB, DATA_MODEL.
- **Scope / Technical notes:** Preview required/eligible/missing per gra i rola. Osobne targety board/screen. Freeze źródeł, rewizji, preprocessing, base, ról i hashy. Cofnięte dowody unieważniają kwalifikację kandydata.
- **Expected files:** istniejący eksporter geometrii jako wzorzec; nowe proponowane `domain/grid_training_cohorts.py`, application/storage, migracja, `training_core/grid_dataset.py`, `grid-cohort-preview.tsx`.
- **Acceptance / Tests:** Pełna plansza z niekompletnego zdjęcia działa w grid-only. Niepełne zdjęcie nie jest screen targetem. Auto-accept nie tworzy etykiety. Drift między preview/freeze blokuje zapis.
- **Verification:** API, WORKER, MIG, ADMIN, OpenAPI, MAP.
- **Risks / Out of scope:** Stary eksporter zachowuje dotychczasową domyślną semantykę; bez treningu.
- **Outcome:** manifest, liczby braków i dowody kwalifikacji.

### Etap E — trening i ocena

### TASK-1005 — Preset i dopuszczenie zasobów

- **Status:** `todo`.
- **Goal / Context:** Ustalić jawny budżet runu na podstawie danych.
- **Dependencies:** TASK-0995; osobna zgoda na ograniczony pomiar GPU.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; parametry wynikają z raportów i mierzalnego testu.
- **Relevant docs:** VISION_LAB i raporty dotychczasowych iteracji Mumii.
- **Scope / Technical notes:** Osobne presety grid-only/screen+grid, koszt kohorty, early stopping i limit czasu/kroków. Smoke kończy się po 50 krokach albo 120 sekundach, zależnie co nastąpi pierwsze. Dzierżawa obejmuje app grid runs.
- **Expected files:** F19, istniejące protokoły runów; nowy proponowany `training_core/grid_training_admission.py`, presety i API podglądu.
- **Acceptance / Tests:** Brak GPU, niezgodny runtime, zajęta dzierżawa lub brak zatwierdzonego presetu blokuje run. Resume nie odnawia budżetu.
- **Verification:** WORKER, API; ograniczony smoke tylko po zgodzie.
- **Risks / Out of scope:** Bez obietnicy kontroli wszystkich zewnętrznych procesów CUDA i bez zmian trenera symboli.
- **Outcome:** uzasadniony preset, wynik pomiaru i ograniczenia.

### TASK-0996 — Trwały trening V3 w aplikacji

- **Status:** `todo`.
- **Goal / Context:** Wykonać odtwarzalny run z checkpointem i wznowieniem.
- **Dependencies:** TASK-0995, TASK-1005, TASK-1012.
- **Recommended execution:** `gpt-6.1-sol`, `high`; stan treningu i maskowanie danych.
- **Relevant docs:** VISION_LAB, architektura workera i kontrakt kohort.
- **Scope / Technical notes:** Wydzielić wspólny rdzeń z istniejącego treningu. Grid-only zamraża detektor i BatchNorm. Obsłużyć lease, postęp, cancel/resume, eksport i trwały budżet.
- **Expected files:** F18–F20, model i data adapter laboratorium; nowe proponowane `training_core/grid_training.py`, `images/grid_training_handler.py`, `application/grid_training_runs.py` i repozytorium runów.
- **Acceptance / Tests:** Restart odtwarza RNG/sampler/optimizer; crash po eksporcie nie dubluje wersji; uszkodzony checkpoint nie daje gotowego kandydata; lab i produkcja używają zgodnej logiki.
- **Verification:** WORKER, API, MIG przy encjach runów, OpenAPI, MAP.
- **Risks / Out of scope:** Bez automatycznego rzeczywistego treningu lub aktywacji.
- **Outcome:** kontrakt checkpointu, testy wznowienia i ewentualny run opisany osobno.

### TASK-0997 — Ocena per gra i bramka kandydata

- **Status:** `todo`.
- **Goal / Context:** Zapobiec publikacji poprawy jednej gry kosztem drugiej.
- **Dependencies:** TASK-0996 i niezależne, kompletne dane kontrolne.
- **Recommended execution:** `gpt-6.1-sol`, `high`; metryki i kwalifikacja publikacji.
- **Relevant docs:** D-483, VISION_LAB, reguły oceny tego planu.
- **Scope / Technical notes:** Identyczne źródła dla bazy i kandydata, pełny inference od zdjęcia, wyniki per gra/nagranie. Wersjonowane definicje metryk. REGRESSION tylko do końcowej kontroli.
- **Expected files:** F18/F21 i istniejące metryki; nowe proponowane `training_core/grid_evaluation.py`, `application/grid_model_evaluation.py`, `grid-model-comparison.tsx`.
- **Acceptance / Tests:** Regresja dowolnej gry blokuje wspólny PASS. Brak detekcji ma koszt. Brak danych, parity lub aktualnych dowodów blokuje publikację. Dobór checkpointu nie używa REGRESSION.
- **Verification:** WORKER, API, ADMIN, OpenAPI.
- **Risks / Out of scope:** Nie zastępować nieznanej jakości zerowym błędem.
- **Outcome:** porównanie, wersja polityki i powody PASS/REVISE/braku możliwości oceny.

### TASK-1006 — Kandydat wspólnej geometrii Mumii i 777a2

- **Status:** `todo`.
- **Goal / Context:** Udostępnić kontrolowany trening geometrii obu gier.
- **Dependencies:** TASK-0997; kohorty obu gier; osobne zlecenie i budżet rzeczywistego runu.
- **Recommended execution:** `gpt-6.1-sol`, `high`; wspólne dane i ryzyko regresji.
- **Relevant docs:** rozszerzenie D-527, VISION_LAB, reguły wspólnej kohorty.
- **Scope / Technical notes:** Wybór jednej bazy na VALIDATION, równoważenie gier/nagrań, dziedziczenie wyłączeń obu linii danych. Jeden jawny eksperyment, bez automatycznej pętli.
- **Expected files:** rejestr, kohorty, trener i ocena poprzednich tasków; nowy proponowany `application/shared_grid_model_candidate.py` i wersjonowana joint policy.
- **Acceptance / Tests:** Duża gra nie dominuje. Alias kontrolny nie trafia do treningu drugiej gry. Regresja blokuje publikację. Wynik nie przełącza gier automatycznie.
- **Verification:** API, WORKER; rzeczywisty run tylko po zgodzie i spełnieniu warunków.
- **Risks / Out of scope:** Brak dobrego wspólnego kandydata nie blokuje panelu i pracy na dotychczasowych wersjach.
- **Outcome:** mechanizm i wynik eksperymentu rozdzielone; brak pomiaru nie jest PASS.

### Etap F — pełny panel i odbiór

### TASK-1000 — Pełna sekcja „Geometria V3”

- **Status:** `todo`.
- **Goal / Context:** Udostępnić cały proces z poziomu gry.
- **Dependencies:** TASK-0995, TASK-0997, TASK-0998, TASK-1003, TASK-1011; bez zależności od pozytywnego wyniku TASK-1006.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; integracja gotowych kontraktów.
- **Relevant docs:** ADMIN_APP, APP_V3_FUNCTIONAL_INVENTORY, D-527/D-541.
- **Scope / Technical notes:** Diagnostyka, próbka, korekty, dane, run, porównanie, wersje i ponowne rozpoznanie. Backend określa dostępność działań. Brak danych pokazuje konkretne wymagania.
- **Expected files:** F15, istniejąca nawigacja; nowe proponowane `grid-model-workspace.tsx`, `grid-model-state.ts`, `grid-model-client.ts`; wcześniejsze panele.
- **Acceptance / Tests:** Proces działa bez skryptów operatora. Wejście na ekran nie uruchamia joba. Zmiana gry/reload zachowuje właściwy stan. Panel działa z dwiema bazami i odrzuconym wspólnym kandydatem.
- **Verification:** ADMIN, testy transportu i interakcji, DOC.
- **Risks / Out of scope:** Bez połączenia treningu symboli z geometrią i bez przebudowy archiwalnej 777.
- **Outcome:** ścieżki operatora i jawne stany blokujące.

### TASK-1001 — Odbiór procesu i instrukcja operatora

- **Status:** `todo`.
- **Goal / Context:** Potwierdzić działanie całego procesu i możliwość dalszej pracy bez historii czatu.
- **Dependencies:** Ukończone piony aplikacji i audyty. Odbiór na rzeczywistych danych wymaga właściwych zgód i anotacji; wynik wspólnego modelu raportowany oddzielnie.
- **Recommended execution:** `gpt-6.1-sol`, `medium`; integracja i dowody trwałości.
- **Relevant docs:** DEFINITION_OF_DONE, AUDIT_REPORT_TEMPLATE, dokumenty właścicielskie tasków.
- **Scope / Technical notes:** E2E na izolowanej bazie: korekta → kohorta → run → ocena → aktywacja → wybrany przebieg → restart. Osobno aktualna baza bez treningu, propozycja i przyjęcie przez człowieka.
- **Expected files:** nowe proponowane `ai_docs/guides/V3_GRID_FINE_TUNING_OPERATOR.md`, `ai_docs/quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md`, testy odbiorowe; wymagania, architektura, mapy i stan.
- **Acceptance / Tests:** Proces działa po restarcie i utracie odpowiedzi; obie gry i nowa gra zachowują izolację symboli. Stara 777 ma regresję. Rzeczywiste liczby i ograniczenia są opisane bez domniemanych wyników.
- **Verification:** API, WORKER, ADMIN, REVIEWER, wymagane buildy, OpenAPI, DOC, MAP.
- **Risks / Out of scope:** Bez automatycznego wdrożenia, push, migracji operatora i masowego przetwarzania.
- **Outcome:** wyniki techniczne, odbiór operatora, zakres niewykonany, gałąź i dokładne commity gotowe do akceptacji.

## 7. Pokrycie wymagań i warunki zakończenia

| Wymaganie                                  | Taski                  | Dowód odbioru                                                                |
| ------------------------------------------ | ---------------------- | ---------------------------------------------------------------------------- |
| Trwały plan i wznowienie między modelami   | 1015                   | Nowa sesja ustala stan z plików i Git.                                       |
| Czytelne różnice liczników obu gier        | 1010                   | Uzgodnione jednostki, przyczyny i przecięcia.                                |
| Akceptacja silnika i historyczne statusy   | 1017, 1008             | Atomowy zapis, zgodne projekcje, brak recropu.                               |
| Edytor 4/24                                | 0993                   | Roundtrip, transformacja, undo, restart.                                     |
| Checkpointy na D                           | 1014                   | Hash, receipt i odczyt z nowego procesu.                                     |
| Dynamiczne wersje i nowe gry               | 0994, 1012, 0998, 1004 | Trzecia rodzina, stare snapshoty, nowa gra bez obcego klasyfikatora symboli. |
| Usunięcie zatwierdzonych pozostałości V1.1 | 1011                   | Trzy miejsca UI, regresja historycznej gry.                                  |
| Ponowne rozpoznanie bez treningu           | 0999, 1013, 1003       | Przebieg aktualną bazą i ręczne przyjęcie propozycji.                        |
| Kontrola jakości i dane do treningu        | 1002, 1009, 0995       | Niezależne role, pomiar i kwalifikacja etykiet.                              |
| Trening i wspólna geometria                | 1005–1006, 0996–0997   | Trwały run, brak przecieku, bramka osobno per gra.                           |
| Całość w aplikacji                         | 1000–1001              | E2E i instrukcja operatora.                                                  |

Niepowodzenie wspólnego modelu jest dopuszczalnym wynikiem eksperymentu, jeżeli zostaje rzetelnie zmierzone. Nie jest podstawą do osłabiania bramki.

Szacunek implementacji pozostaje orientacyjny: 12–28 dni roboczych, bez czasu anotacji i oczekiwania na runy. Operator jawnie potwierdził ten koszt i zlecił realizację całego planu 2026-10-14. Istotny wzrost kosztu wymaga ponownej zgody zgodnie z AGENTS.

Aktualna faza: TASK-1015 done, bootstrap v1.7.367 / `b35a9ee7dadf3da485427f81a84149e63f0b8cfc`. TASK-1010 done po audycie Claude REVISE i jednej rundzie poprawek; brak otwartych P0/P1, bez przepisywania werdyktu. Commit TASK-1010: v1.7.368 / `02f38d6cb731dfc06001a1c6fc819ee4927acba1`. TASK-1017 done; TASK-1008 done; TASK-0993 done; TASK-1014 done; TASK-0994 done (audyt timeout, bez PASS). D-550/D-552 przyjęte przed implementacją TASK-1017. Cały plan jest zlecony; nie wymaga ponownej zgody po każdym tasku. Integracja i operacje danych zachowują osobne bramki.

## 8. Przypisanie modeli do zadań

Audyt każdego taska: Claude Code w oddzielnym kontekście, zgodnie z ograniczonym zakresem diffu i zasadami AGENTS. Historyczna sesja `claude-fable-5-1` jest potwierdzona raportem rundy 3. Pakietowe CLI Claude wykryto pełnym resolverem z nowego main; --version działa, logowanie i wykonanie audytu wymagają osobnego rzeczywistego wyniku; zewnętrzny raport TASK-1015 otrzymano od operatora: PASS, brak P0/P1, cztery P2 do rozliczenia. Raport zapisano bez zmiany znalezisk w `ai_docs/quality/TASK-1015_AUDIT_claude-fable-5-1.md`. Audyt bootstrapu nie jest PASS aplikacji. Niedostępność przypisanej konfiguracji przy wykonaniu wymaga jawnego rozstrzygnięcia, bez ukrytego zamiennika.

| Zadanie   | Model       | Reasoning | Uzasadnienie                                        | Dodatkowy review         |
| --------- | ----------- | --------- | --------------------------------------------------- | ------------------------ |
| TASK-1015 | gpt-6.1-sol | medium    | Dokumentacja, bezpieczny start i przekazanie stanu. | claude-fable-5-1, medium |
| TASK-1010 | gpt-6.1-sol | high      | Kilka źródeł liczników i różne jednostki.           | claude-fable-5-1, medium |
| TASK-1017 | gpt-6.1-sol | high      | Akceptacja silnika i pochodzenie danych.            | claude-fable-5-1, high   |
| TASK-1008 | gpt-6.1-sol | high      | Historyczne statusy i atomowe projekcje.            | claude-fable-5-1, high   |
| TASK-0993 | gpt-6.1-sol | medium    | Geometria edytora i zachowanie węzłów.              | claude-fable-5-1, medium |
| TASK-1014 | gpt-6.1-sol | medium    | Trwałość i integralność artefaktów.                 | claude-fable-5-1, medium |
| TASK-0994 | gpt-6.1-sol | high      | Rejestr i migracja przypisań.                       | claude-fable-5-1, high   |
| TASK-1012 | gpt-6.1-sol | high      | Snapshoty i zgodność całego importu.                | claude-fable-5-1, high   |
| TASK-0998 | gpt-6.1-sol | high      | Aktywacje, CAS i historia wersji.                   | claude-fable-5-1, medium |
| TASK-1004 | gpt-6.1-sol | high      | Nowe gry i izolacja symboli.                        | claude-fable-5-1, high   |
| TASK-1011 | gpt-6.1-sol | medium    | Ograniczone zmiany UI i regresja starej gry.        | claude-fable-5-1, medium |
| TASK-0999 | gpt-6.1-sol | high      | Ponowne zapisy i ochrona sekwencji.                 | claude-fable-5-1, high   |
| TASK-1013 | gpt-6.1-sol | high      | Decyzje człowieka i rewizje propozycji.             | claude-fable-5-1, high   |
| TASK-1003 | gpt-6.1-sol | medium    | Podgląd zakresu i raport operacji.                  | claude-fable-5-1, medium |
| TASK-1002 | gpt-6.1-sol | high      | Pochodzenie i niezależność nagrań.                  | claude-fable-5-1, high   |
| TASK-1009 | gpt-6.1-sol | high      | Dobór próby i interpretacja wyników.                | claude-fable-5-1, medium |
| TASK-0995 | gpt-6.1-sol | high      | Kwalifikacja i niezmienne dane dowodowe.            | claude-fable-5-1, high   |
| TASK-1005 | gpt-6.1-sol | medium    | Pomiar kosztu i wersjonowany preset.                | claude-fable-5-1, medium |
| TASK-0996 | gpt-6.1-sol | high      | Trener, checkpoint i wznowienie.                    | claude-fable-5-1, medium |
| TASK-0997 | gpt-6.1-sol | high      | Metryki i bramka osobno dla gier.                   | claude-fable-5-1, medium |
| TASK-1006 | gpt-6.1-sol | high      | Wspólna kohorta i regresje między grami.            | claude-fable-5-1, high   |
| TASK-1000 | gpt-6.1-sol | medium    | Integracja gotowych funkcji panelu.                 | claude-fable-5-1, medium |
| TASK-1001 | gpt-6.1-sol | medium    | Odbiór procesu i dokumentacja trwałości.            | claude-fable-5-1, medium |
