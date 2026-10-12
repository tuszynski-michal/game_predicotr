---
title: Lokalny selektor Windows — instrukcja operatora
status: accepted
last_updated: 2026-10-12
---

# Lokalny selektor Windows — instrukcja operatora

Aktualna paczka to **0.1.3**, przygotowana po pełnej rundzie TASK-0984–0987:
`apps/selector-desktop/out/releases/pilot-0.1.3-0b1ab330/Selektor zdjec-win32-x64-0.1.3.zip`.
ZIP SHA-256: `cfb078b5f86a57cd781d99210ff699849485031a1ac173b6acb1861c1a145761`.
[Dowody finalizacji](../quality/OFFLINE_PHOTO_SELECTOR_FINAL_VERIFICATION_20261012.md)
identyfikują runtime, kontrole i ograniczenia. Wszystkie części implementacji,
w tym przejęcie starej sesji, są dostępne. Dane i wyniki pozostają lokalnie.
Wcześniejszy audyt Claude rundy 2 miał PASS dla paczki 0.1.2; końcowy audyt
nowych zmian i fizyczny odbiór paczki 0.1.3 wykonuje operator.

## Budowanie i kontrola programu

Z katalogu głównego worktree, w PowerShell, po instalacji zależności Node.
Finalne scenariusze sprawdzają nowy start i wznowienie w obu kierunkach,
przejęcie starej sesji, zamykanie i rzeczywiste aktualizacje ze starszych ZIP-ów.
Grupy testów mają osobne limity120 s; nie oznacza to pominięcia testów projektu:

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 node --experimental-strip-types --test apps/selector-desktop/test/start-resume.test.mjs
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:native --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:foundation --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:project --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:ui --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:legacy --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:legacy-recovery --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:legacy-process --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 45 npm run test:release --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 45 npm run lint --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 45 npm run typecheck --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run release --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:start --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:shortcuts --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:legacy --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:release:ux --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:update --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:packaged --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:ux --workspace @game-predictor/selector-desktop
```

Wrapper uruchamia npm przez jego plik JS obok Node.js, bez zależności od
semantyki shima `.cmd`. Wymagane npm11 zgodne z root `engines`. Instalacja
workspace'ów pobiera też narzędzia desktopu, a pakowanie runtime Electrona.
Root dopuszcza tylko dodatkowy skrypt `esbuild@0.25.12`; istniejące ostrzeżenia
innych wersji esbuild/sharp nie są automatycznie dopuszczane. Bez custom mirror.

ZIP znajduje się w `apps/selector-desktop/out/make/zip/win32/x64/`.
Polecenie release tworzy świeży ZIP oraz sąsiadujące pliki `.sha256` i
`.release.json`: wersja, bajty, SHA-256, commit/stan dirty oraz suma app.asar.
Osadzone dane buildu pozwalają sprawdzić pochodzenie rozpakowanego programu.
Powtarzalny workflow nie oznacza identycznych bajtów ZIP przy każdym buildzie;
każdą paczkę identyfikuje jej własna suma. Artefakty są ignorowane przez Git.
Smoke release sprawdza sumy i uruchamia EXE po rozpakowaniu do własnego katalogu.
TASK-0982 sprawdził rzeczywistą zmianę0.1.0→0.1.1 na własnej kopii projektu.
Przeniesienie tej samej wersji pozostaje jedynie symulacją zmiany lokalizacji
programu. Obie kontrole są lokalne; odbiór aktualizacji przez odbiorcę jest osobny.
Lokalny packaged smoke nie zastępuje odbioru na komputerze odbiorcy.

## Uruchomienie i nowa partia

Poniższy przepływ przeszedł testy i rzeczywisty smoke finalnego ZIP-a 0.1.3. Paczka i dowody testów są w
[raporcie odbioru](../quality/OFFLINE_PHOTO_SELECTOR_ACCEPTANCE.md); stary ZIP
fundamentu go nie realizuje.

1. Odbiorca otrzymuje ZIP, wersję, SHA-256 i tę instrukcję. Porównuje sumę
   otrzymanego pliku z sumą przekazaną przez operatora. W PowerShell można użyć
   `Get-FileHash -Algorithm SHA256 -LiteralPath "C:\Paczki\Selektor.zip"`,
   podając rzeczywistą lokalizację otrzymanego ZIP-a. Wynik ma być identyczny
   z plikiem `.sha256` przekazanym dla tej paczki.
2. Rozpakowuje cały folder do osobnego lokalnego katalogu programu.
   Nie uruchamia EXE bezpośrednio z ZIP i nie kopiuje samego EXE bez zasobów.
3. Uruchamia `Selektor-zdjec.exe` na Windows11 x64. Internet, host, Node.js
   i Python nie są potrzebne. Wymagany systemowy PowerShell jest częścią Windows.
4. Wybiera `Wybierz folder zdjęć` i wskazuje katalog źródła.
   Jeżeli katalog należy do zapisanego projektu, aplikacja od razu wznawia
   ostatnią pozycję, numerację i postęp. Nie wpisuje ustawień ponownie.
5. Dla nowej partii wpisuje nazwę gry, np. `Mumie`, pierwszą planszę,
   opcjonalną ostatnią planszę i kierunek numeracji. Nazwa gry jest etykietą
   historii. Kierunek zmienia wyłącznie numerację plansz; zdjęcia pozostają
   w naturalnej kolejności w obu kierunkach.
6. Ekran pokazuje ścieżki: dla `D:\Mumie\123` projekt powstaje jako
   `D:\Mumie\123 selekcja`, wynik jako `D:\Mumie\123 wybrane`.
   Oba foldery są obok źródła; aplikacja tworzy je sama. Potwierdza lokalny
   dysk poza synchronizacją/udziałem sieciowym i klika `Rozpocznij wybieranie`.
   Wybory i postęp zapisują się automatycznie; nie ma ręcznego przycisku zapisu.
7. Po restarcie może ponownie wskazać te same zdjęcia albo wybrać pozycję
   z listy `Ostatnie projekty`, np. `Mumie — 123`, i kliknąć `Kontynuuj`.
   `Otwórz projekt` nadal pozwala wskazać zapisany folder projektu, np. ze
   starszego wydania lub przeniesionej kopii. Projekty bez nazwy gry mają
   etykietę folderu źródła. Historia jest pomocnicza i ma10 ostatnich pozycji.
8. Konflikt, kilka projektów źródła lub brak znanego folderu nie tworzą nowej
   selekcji w miejsce istniejącej. Wybiera właściwy projekt z historii albo
   używa `Otwórz projekt`. Obce dane nie są nadpisywane.
   Gdy znany folder nie istnieje, dialog pokazuje jego ścieżkę. `Anuluj`
   zachowuje pracę i pozwala wskazać przeniesiony projekt przez `Otwórz projekt`.
   `Nowa partia` wymaga świadomego potwierdzenia i zapomina wyłącznie martwy
   wpis historii. Nie usuwa plików. Istniejący niepusty wynik nadal blokuje
   nową partię; aplikacja podaje jego ścieżkę i nie nadpisuje zawartości.

Pilotaż jest bez podpisu. Windows może ostrzec albo zablokować uruchomienie.
Przy blokadzie należy zachować komunikat i wstrzymać odbiór; instrukcja
nie zaleca wyłączania ochrony ani gwarantuje obejścia blokady.

## Praca ze zdjęciami

Enter lub F zatwierdza zdjęcie i przechodzi do następnego JPEG-a po trwałym
zapisie. Akceptacja przesuwa o jeden, niezależnie od wybranego skoku nawigacji.
Tab pomija zakres numeracji i pozostawia to samo zdjęcie. Do pominiętego zakresu
można później wrócić przez korektę początku; zaakceptowany zakres i powtórny
wybór tego samego źródła pozostają chronione. Strzałki lewo/prawo
zmieniają oglądany JPEG bez zatwierdzania. Skoki to1–10,15,20.
A lub Ctrl+Z cofa ostatnią decyzję; plik zostanie usunięty tylko po potwierdzeniu
jego własności i sumy kontrolnej. Skróty nie przejmują wpisywania w polach.
Przytrzymanie Enter/F/Tab/A/Ctrl+Z nie wykonuje kolejnych decyzji. Aby wykonać
następną, należy zwolnić i ponownie nacisnąć klawisz. Przytrzymane strzałki
mogą przechodzić między zdjęciami.

Zakres ma standardowo dziewięć plansz, a na końcu określonej sesji może być
krótszy. Korekta początku zakresu respektuje tę regułę; nie oznacza dowolnej
liczby plansz. Licznik pokazuje wyłącznie zakończone zapisy. Podczas zapisu
kolejna mutacja jest zablokowana. Zoom100–3000%, pełny ekran i przewijanie
zmieniają tylko widok. `Otwórz folder wynikowy` otwiera lokalny wynik.

`Restart partii` pokazuje liczbę decyzji i własnych plików, które zostaną
usunięte. Dopiero `Potwierdź restart partii` wykonuje reset; `Anuluj restart`
zachowuje pracę. Zmieniony lub obcy JPEG blokuje operację. Nie używać restartu
jako sposobu naprawy brakującego katalogu.

## Dane i wyniki

Źródłowe zdjęcia nie są modyfikowane. Domyślne katalogi obok źródła:
`<źródło> selekcja` zawiera projekt, a `<źródło> wybrane` JPEG-i
`seq_<start>-<end>.jpg` i manifest operator-local schema v2.

Folder projektu musi być na lokalnym dysku poza Proton Drive i inną
synchronizacją oraz udziałami sieciowymi. Gotowy wynik można ręcznie
przesłać przez Proton Drive. Program nie generuje linków i nic nie uploaduje.
Nowe partie zaczyna się lokalnie. Zgodną starą sesję można przejąć z jej
manifestu i folderów, według procedury poniżej; niezgodną kończy się w Reviewerze.

Przy `Zapis zatrzymany` zapisać kod błędu. Brak źródła lub wyniku wymaga
`Wskaż ponownie źródło` albo `Wskaż ponownie wynik`, bez resetu. Wskazać zgodny
przeniesiony katalog, nie pusty zamiennik. Po naprawie miejsca/uprawnień użyć
`Wznów po naprawie`. Zmieniona lista lub metadane źródła blokują wznowienie;
program nie zgaduje, że zmieniły się tylko daty plików.
Otwarcie projektu sprawdza inwentarz źródła i SHA-256 wszystkich zapisanych
JPEG-ów. Duży wynik może wymagać dłuższej kontroli przed odblokowaniem pracy.
Przy kontrolowanym pomiarze 15 000 małych JPEG-ów utworzenie projektu trwało
około 21 s, a ponowne otwarcie około 10,5 s. To orientacja z jednego komputera;
duże zdjęcia i wolniejszy dysk mogą wymagać więcej czasu. Ekran „Weryfikacja…”
nie oznacza potrzeby ponownego kliknięcia lub resetu.
Obsługiwany jest lokalny dysk stały; nośniki wymienne i udziały sieciowe
nie należą do tego pilotażu.

Nie nadpisywać ręcznie plików seq_* w aktywnym projekcie. Obcy lub zmieniony
plik blokuje zapis/cofnięcie. Restart wymaga preview i świadomego potwierdzenia.

## Brak zdjęcia wynikowego

`OUTPUT_MISSING_FILE` oznacza brak JPEG-a należącego do potwierdzonej decyzji.
Program zatrzymuje nowe decyzje. Nie używać restartu, pustego folderu wyniku
ani ręcznej edycji projektu lub manifestu do obejścia błędu.

1. Zamknąć program i zachować kopię całego folderu projektu oraz obecnego wyniku.
2. W manifeście `manual-image-selection-output-v1.json` znaleźć zaakceptowaną
   decyzję, której `outputName` odpowiada brakującemu `seq_<start>-<end>.jpg`.
   Odczytać jej `imagePath` oraz `imageChecksumSha256`. `imagePath` jest
   względną ścieżką oryginalnego JPEG-a w źródle; uwzględnić podkatalogi.
3. Użyć zgodnej kopii brakującego wyniku albo dokładnie oryginalnego JPEG-a
   wskazanego przez `decisions[].imagePath`. Przed kopiowaniem porównać jego
   SHA-256 z `imageChecksumSha256`, np. przez `Get-FileHash -Algorithm SHA256`.
   Kopiować tylko przy identycznej sumie, bez ponownego zapisu lub konwersji
   zdjęcia. Nie wystarczy podobny obraz ani zgodna nazwa.
4. Przywrócić te same bajty pod `outputName` do folderu wyniku, wyłącznie
   gdy plik nadal jest nieobecny. Nie zastępować istniejącego pliku i nie
   edytować projektu ani manifestu.
5. Otworzyć projekt i użyć `Wznów po naprawie`, jeśli zapis nadal jest
   zatrzymany. Program ponownie sprawdza SHA-256; niezgodna kopia nie
   odblokuje pracy. Jeśli brak potwierdzonego oryginału/kopii, zachować dane
   i logi do diagnostyki operatora. Automatycznego odtworzenia z UI nie ma.

Gdy przeniesiono cały wynik, wskazać zgodny folder przez `Wskaż ponownie wynik`.
Obce pliki, również `desktop.ini` lub `Thumbs.db`, blokują zapis. Nie usuwać ich
automatycznie; operator ustala ich pochodzenie na kopii danych. Nieznana lub
pusta blokada odzyskiwania wymaga diagnostyki, ponieważ nie dowodzi tożsamości
właściciela. Sam upływ czasu nie uprawnia do jej usunięcia.

## Przejęcie sesji Reviewera

Przepływ0978 przeszedł testy kontraktu, recovery oraz rzeczywistego EXE.
`Przejmij sesję Reviewera` rozpoczyna lokalny odczyt źródła i starego wyniku z
manifestem `manual-image-selection-output-v1.json`. Nie odczytuje IndexedDB
przeglądarki, nie łączy się z hostem i nie zmienia starego wyniku.

Po walidacji pokazuje podgląd postępu. `Utwórz nowy projekt z tej sesji`
pozwala wskazać dwa nowe, puste lokalne foldery: projekt i wynik. Natywne
potwierdzenie pokazuje lokalizacje. Import kopiuje zweryfikowane JPEG-i,
przenosi decyzje i pozycję oraz zapisuje manifest v2 w nowym wyniku.
Anulowanie podglądu nie resetuje ani nie modyfikuje starej sesji.

Przejęcie jest dostępne tylko z dowodowo zgodnego v1/v2. Brak fingerprint
źródła, fileCount lub jednoznacznej konfiguracji, zmieniona lista/metadane,
niezgodne checksumy JPEG i obce pliki blokują import. Historyczny nietypowy
MIME może dawać inny fingerprint; program go nie przerabia ani nie zgaduje
zmiany samych dat. V1 z końcową malejącą stroną i sprzeczną semantyką
zakończenia oraz historia wielokrotnie akceptująca tę samą source path są
nieobsługiwane. Nie poprawiać manifestu ręcznie, aby wymusić import.
Taką sesję zachować i kontynuować dotychczasowym narzędziem.

## Trwałość projektu

Decyzje i bieżąca względna ścieżka zdjęcia są w wersjonowanym projekcie.
Manifest w wyniku jest jego projekcją. Potwierdzenie decyzji następuje po zapisie
JPEG-a, stanu, manifestu i kopii stanu. Dziennik pozwala dokończyć przerwaną
operację po awarii procesu. Uszkodzenie, brak miejsca lub konflikt zatrzymują
nowe decyzje; nie usuwać ręcznie dziennika ani plików blokad.
Nieznany właściciel blokady wymaga diagnostyki, a sam upływ czasu nie pozwala
przejąć projektu. Folderów projektu i aktywnego wyniku nie synchronizować.
Po utracie blokady można zamknąć program; zamknięcie nie przejmuje projektu
ani nie usuwa cudzej blokady. Dotyczy to także blokady o nieznanym właścicielu.
Ponowne uruchomienie podczas zamykania otworzy jedno okno po zakończeniu
poprzedniego procesu. Widok jest zapisywany po250 ms ciszy i przed
zamknięciem lub zmianą projektu. Decyzje i kursor nie korzystają z debounce.

Idempotencja warstwy natywnej dotyczy ponowienia tego samego operationId.
Nowe kliknięcie w interfejsie tworzy nowy identyfikator i nie jest ponowieniem
utraconej odpowiedzi. Projekt zachowuje całą historię potwierdzeń, także nawigacji.
Nowy format dyskowy zapisuje inwentarz raz oraz dopisuje operacje do dwóch
zgodnych dzienników. Nie przepisuje całego inwentarza i historii na każdy krok.
Rozmiar dziennika i pamięć nadal rosną z liczbą operacji; otwarcie sprawdza
całą historię, a manifest wynikowy rośnie z liczbą decyzji.

Otwarcie starszego projektu wykonuje odzyskiwanie i automatyczną migrację
pod jego blokadą. Migracja zachowuje decyzje, kursor, wyniki i dawne
potwierdzenia operacji. Po migracji stara aplikacja odmawia zapisu tego
projektu. Przed aktualizacją zachować cały folder projektu i wyniku; do
kontynuacji używać nowej wersji. Wszystkie pliki folderu projektu są częścią
kopii zapasowej, również pliki inwentarza i dzienników.
Nie obiecujemy odporności na awarię dysku ani zanik zasilania.

## Aktualizacja, kopia i diagnostyka

Zamknąć program po ukończeniu bieżącego zapisu, zachować folder projektu
i źródło, rozpakować nową wersję do oddzielnego folderu programu.
Otworzyć dotychczasowy projekt. Aktualizacja nie zastępuje katalogu projektu.

Kopię wykonywać po zamknięciu programu, na lokalny dysk. Skopiować cały folder
projektu oraz cały wynik. Źródło jest potrzebne do kontynuacji; zachować jego
nazwy, układ katalogów i metadane. Nie kopiować tylko EXE ani samego pliku
manifestu jako kopii postępu. Kopia projektu zachowuje decyzje i kursor;
krok/zoom/scroll są pomocniczym cache'em tego komputera i mogą wrócić do domyślnych.

Przy odtwarzaniu na osobnych kopiach zamknąć oryginalny projekt i wskazać kopię
projektu. Kopia zachowuje stare lokalizacje źródła i wyniku; nie tworzy
automatycznie niezależnej partii. Przed kolejnymi decyzjami rozwinąć `Inne lokalizacje źródła i wyniku`
i wskazać jawnie kopię wyniku oraz zgodne źródło. Jeśli stare katalogi nadal istnieją, samo otwarcie
kopii projektu nie zmienia tych powiązań. Nie edytować ścieżek w plikach projektu
ręcznie. Test kopii agenta i fizyczny odbiór operatora zostaną
zapisane osobno w raporcie0979. Logi mają rotację, bez treści obrazów; przycisk
logów otwiera ich katalog. Nie usuwać ręcznie blokad, aby wymusić otwarcie.

## Diagnostyka startu i testów wydania

Kontrola tożsamości procesu ma ograniczony czas. Po timeout aplikacja może
wykonać jedną świeżą próbę. Timeout nie oznacza, że właściciel projektu nie
żyje; nieznana tożsamość nadal zatrzymuje zapis. W logu pojawiają się numer
próby, jej czas i kod wyniku. Nie usuwać blokady ręcznie i nie wyłączać
zabezpieczeń systemu, aby obejść błąd.

Testy wydania uruchamiane przez operatora zachowują logi po porażce w
`artifacts/selector-smoke-diagnostics/<unikalny-przebieg>` w worktree.
Katalog zawiera selector.log, dostępne rotacje oraz krótki failure.json.
Dowód jest poza tymczasowym katalogiem testu. Gdy kopiowanie logów nie
powiedzie się, test zachowuje cały własny katalog i podaje jego ścieżkę.
Ta procedura dotyczy testów wydania; zwykły użytkownik otwiera lokalne logi
przyciskiem aplikacji.

## Warunki odbioru

TASK-0979 wymaga rzeczywistego drugiego komputera, dostarczenia ZIP faktycznym
kanałem, offline selekcji, restartu Windows, aktualizacji, relink źródła
i odczytu wyników. Agent nie może wpisać PASS tych kontroli bez dowodów
operatora. Brak takiego odbioru pozostaje jawnym ograniczeniem wydania.
