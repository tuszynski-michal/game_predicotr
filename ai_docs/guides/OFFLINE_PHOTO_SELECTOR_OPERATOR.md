---
title: Lokalny selektor Windows — instrukcja operatora
status: accepted
last_updated: 2026-10-12
---

# Lokalny selektor Windows — instrukcja operatora

Gotowe są wszystkie pięć części implementacyjnych, w tym przejęcie0978.
ZIP0.1.0 po0978 przeszedł pełny lokalny test po rozpakowaniu. Audyt operatora
2026-10-12 ma werdykt REVISE. Poprawki0980–0982 i paczka0.1.1 przeszły
lokalne kontrole; ponowny audyt operatora pozostaje pending. Do tego audytu
użyć najnowszej paczki pilot-0.1.2-c4181f7d (TASK-0983). Rejestr odbioru
identyfikuje każdą paczkę i jej ograniczenia. Fizyczny odbiór nadal jest pending.

## Budowanie i kontrola programu

Z katalogu głównego worktree, w PowerShell, po instalacji zależności Node.
TASK-0983 dodatkowo sprawdził aktualizację0.1.0→0.1.2 oraz nowy start
i wznowienie w obu kierunkach po restarcie procesu.
Grupy testów mają osobne limity120 s; nie oznacza to pominięcia testów projektu:

```powershell
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

Poniższy przepływ przeszedł testy0983 i realny smoke ZIP0.1.2. Paczka i dowody testów są w
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
Obsługiwany jest lokalny dysk stały; nośniki wymienne i udziały sieciowe
nie należą do tego pilotażu.

Nie nadpisywać ręcznie plików seq_* w aktywnym projekcie. Obcy lub zmieniony
plik blokuje zapis/cofnięcie. Restart wymaga preview i świadomego potwierdzenia.

## Brak zdjęcia wynikowego

`OUTPUT_MISSING_FILE` oznacza brak JPEG-a należącego do potwierdzonej decyzji.
Program zatrzymuje nowe decyzje. Nie używać restartu, pustego folderu wyniku
ani ręcznej edycji projektu lub manifestu do obejścia błędu.

1. Zamknąć program i zachować kopię folderu projektu oraz obecnego wyniku.
2. Odszukać kopię zapasową dokładnie brakującego `seq_<start>-<end>.jpg`
   z tej samej decyzji. Przywrócić ją pod pierwotną nazwą do folderu wyniku,
   wyłącznie gdy plik nadal jest nieobecny. Nie zastępować istniejącego pliku.
3. Otworzyć projekt i użyć `Wznów po naprawie`, jeśli zapis nadal jest
   zatrzymany. Program sprawdza SHA-256; niezgodna kopia nie odblokuje pracy.
4. Jeżeli brak zgodnej kopii, zachować dane i logi do diagnostyki operatora.
   W tym wydaniu nie ma automatycznego odtworzenia ze źródła.

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
ani nie usuwa cudzej blokady. Widok jest zapisywany po250 ms ciszy i przed
zamknięciem lub zmianą projektu. Decyzje i kursor nie korzystają z debounce.

Idempotencja warstwy natywnej dotyczy ponowienia tego samego operationId.
Nowe kliknięcie w interfejsie tworzy nowy identyfikator i nie jest ponowieniem
utraconej odpowiedzi. Projekt zachowuje historię receiptów, także nawigacji;
rozmiar stanu i koszt jego zapisu rosną z inwentarzem i historią operacji.
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

## Warunki odbioru

TASK-0979 wymaga rzeczywistego drugiego komputera, dostarczenia ZIP faktycznym
kanałem, offline selekcji, restartu Windows, aktualizacji, relink źródła
i odczytu wyników. Agent nie może wpisać PASS tych kontroli bez dowodów
operatora. Brak takiego odbioru pozostaje jawnym ograniczeniem wydania.
