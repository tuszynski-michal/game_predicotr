---
title: Lokalny selektor Windows — projekt instrukcji operatora
status: proposed
last_updated: 2026-10-11
---

# Lokalny selektor Windows — instrukcja projektowana

Gotowe są fundament0975, trwałość0976 i interfejs0977, sprawdzone lokalnie.
Finalna paczka0979 i fizyczny odbiór pozostają do przygotowania; wcześniejszy
ZIP fundamentu nie zawiera pełnej selekcji.

## Budowanie i kontrola programu

Z katalogu głównego worktree, w PowerShell, po instalacji zależności Node:

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:foundation --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:project --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test:ui --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 45 npm run lint --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 45 npm run typecheck --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run selector:make
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run smoke:packaged --workspace @game-predictor/selector-desktop
```

Wrapper uruchamia npm przez jego plik JS obok Node.js, bez zależności od
semantyki shima `.cmd`. Wymagane npm11 zgodne z root `engines`. Instalacja
workspace'ów pobiera też narzędzia desktopu, a pakowanie runtime Electrona.
Root dopuszcza tylko dodatkowy skrypt `esbuild@0.25.12`; istniejące ostrzeżenia
innych wersji esbuild/sharp nie są automatycznie dopuszczane. Bez custom mirror.

ZIP znajduje się w `apps/selector-desktop/out/make/zip/win32/x64/`.
Lokalny packaged smoke nie zastępuje odbioru na komputerze odbiorcy.

## Uruchomienie i nowa partia

Poniższy przepływ przeszedł testy0977. Finalna paczka i dowody testów
zostaną wskazane w raporcie odbioru0979; stary ZIP fundamentu go nie realizuje.

1. Odbiorca otrzymuje ZIP, wersję, SHA-256 i tę instrukcję. Porównuje sumę
   otrzymanego pliku z sumą przekazaną przez operatora.
2. Rozpakowuje cały folder do osobnego lokalnego katalogu programu.
   Nie uruchamia EXE bezpośrednio z ZIP i nie kopiuje samego EXE bez zasobów.
3. Uruchamia `Selektor-zdjec.exe` na Windows11 x64. Internet, host, Node.js
   i Python nie są potrzebne. Wymagany systemowy PowerShell jest częścią Windows.
4. Wybiera `Nowy projekt`, podaje pierwszą planszę, opcjonalną ostatnią
   planszę oraz kierunek numeracji. Lista zdjęć pozostaje naturalna w obu
   kierunkach; kierunek dotyczy wyłącznie kolejnych numerów plansz.
5. Potwierdza, że projekt i aktywny wynik są na lokalnym dysku poza
   synchronizacją i udziałami sieciowymi. Kliknięcie
   `Wybierz zdjęcia i utwórz projekt` otwiera wybór katalogu źródła.
6. Domyślne katalogi projektu/wyniku powstają obok źródła. Opcja
   `Wybiorę osobne katalogi projektu i wyniku` pozwala wskazać inne miejsca.
   Przed utworzeniem natywne potwierdzenie pokazuje wszystkie trzy lokalizacje.
   Istniejące obce dane nie są nadpisywane; anulowanie nie resetuje pracy.
7. Po zamknięciu i ponownym uruchomieniu wybiera `Kontynuuj: <nazwa>` albo
   `Otwórz projekt` i wskazuje folder projektu, nie sam folder wybranych zdjęć.

Pilotaż jest bez podpisu. Windows może ostrzec albo zablokować uruchomienie.
Przy blokadzie należy zachować komunikat i wstrzymać odbiór; instrukcja
nie zaleca wyłączania ochrony ani gwarantuje obejścia blokady.

## Praca ze zdjęciami

Enter lub F zatwierdza zdjęcie i przechodzi do następnego JPEG-a po trwałym
zapisie. Akceptacja przesuwa o jeden, niezależnie od wybranego skoku nawigacji.
Tab pomija zakres numeracji i pozostawia to samo zdjęcie. Strzałki lewo/prawo
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
W pierwszym wydaniu zaczyna się nowe partie; bieżące kończy się w Reviewerze.

Przy `Zapis zatrzymany` zapisać kod błędu. Brak źródła lub wyniku wymaga
`Wskaż ponownie źródło` albo `Wskaż ponownie wynik`, bez resetu. Wskazać zgodny
przeniesiony katalog, nie pusty zamiennik. Po naprawie miejsca/uprawnień użyć
`Wznów po naprawie`. Zmieniona lista lub metadane źródła blokują wznowienie;
program nie zgaduje, że zmieniły się tylko daty plików.
Nie nadpisywać ręcznie plików seq_* w aktywnym projekcie. Obcy lub zmieniony
plik blokuje zapis/cofnięcie. Restart wymaga preview i świadomego potwierdzenia.

## Trwałość projektu

Decyzje i bieżąca względna ścieżka zdjęcia są w wersjonowanym projekcie.
Manifest w wyniku jest jego projekcją. Potwierdzenie decyzji następuje po zapisie
JPEG-a, stanu, manifestu i kopii stanu. Dziennik pozwala dokończyć przerwaną
operację po awarii procesu. Uszkodzenie, brak miejsca lub konflikt zatrzymują
nowe decyzje; nie usuwać ręcznie dziennika ani plików blokad.
Nieznany właściciel blokady wymaga diagnostyki, a sam upływ czasu nie pozwala
przejąć projektu. Folderów projektu i aktywnego wyniku nie synchronizować.
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
