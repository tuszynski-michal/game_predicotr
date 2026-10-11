---
title: Lokalny selektor Windows — projekt instrukcji operatora
status: proposed
last_updated: 2026-10-11
---

# Lokalny selektor Windows — instrukcja projektowana

Gotowe są fundament0975 i natywna trwałość0976. Pełny interfejs selekcji
powstaje w0977; wcześniejsza paczka fundamentu go nie zawiera. Dalsze sekcje
opisują docelowy workflow, który zostanie sprawdzony przy wydaniu0979.

## Budowanie i kontrola fundamentu

Z katalogu głównego worktree, w PowerShell, po instalacji zależności Node:

```powershell
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run test --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 45 npm run lint --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 45 npm run typecheck --workspace @game-predictor/selector-desktop
node apps/selector-desktop/scripts/run-bounded.mjs 120 npm run selector:make
node apps/selector-desktop/scripts/run-bounded.mjs 60 npm run smoke:packaged --workspace @game-predictor/selector-desktop
```

Wrapper uruchamia npm przez jego plik JS obok Node.js, bez zależności od
semantyki shima `.cmd`. Wymagane npm11 zgodne z root `engines`. Instalacja
workspace'ów pobiera też narzędzia desktopu, a pakowanie runtime Electrona.
Root dopuszcza tylko dodatkowy skrypt `esbuild@0.25.12`; istniejące ostrzeżenia
innych wersji esbuild/sharp nie są automatycznie dopuszczane. Bez custom mirror.

ZIP znajduje się w `apps/selector-desktop/out/make/zip/win32/x64/`.
Lokalny packaged smoke nie zastępuje odbioru na komputerze odbiorcy.

## Projektowane uruchomienie

1. Odbiorca otrzymuje ZIP, numer wersji i sumę SHA-256.
2. Rozpakowuje cały folder; nie kopiuje pojedynczego EXE bez zasobów.
3. Uruchamia program na Windows 11 x64. Internet i komputer właściciela
   projektu nie są potrzebne do selekcji.
4. Wybiera Nowy projekt, źródło, lokalny folder projektu i wynik.
5. Po ponownym uruchomieniu wybiera Kontynuuj albo Otwórz projekt.

Pilotaż jest bez podpisu. Windows może ostrzec albo zablokować uruchomienie.
Przy blokadzie należy zachować komunikat i wstrzymać odbiór; instrukcja
nie zaleca wyłączania ochrony ani gwarantuje obejścia blokady.

## Dane i wyniki

Źródłowe zdjęcia nie są modyfikowane. Domyślne katalogi obok źródła:
`<źródło> selekcja` zawiera projekt, a `<źródło> wybrane` JPEG-i
`seq_<start>-<end>.jpg` i manifest operator-local schema v2.

Folder projektu musi być na lokalnym dysku poza Proton Drive i inną
synchronizacją oraz udziałami sieciowymi. Gotowy wynik można ręcznie
przesłać przez Proton Drive. Program nie generuje linków i nic nie uploaduje.
W pierwszym wydaniu zaczyna się nowe partie; bieżące kończy się w Reviewerze.

Brak źródła lub wyniku wymaga ponownego wskazania lokalizacji, bez resetu.
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

Kopia projektu/wyników powstaje po zamknięciu writera; źródło jest potrzebne
do kontynuacji. Nie kopiować tylko EXE jako kopii postępu. Backup/restore
na osobnym katalogu testowym musi przejść odbiór 0979 przed udokumentowaniem
konkretnego gwarantowanego workflowu. Logi mają rotację, bez treści obrazów.

## Warunki odbioru

TASK-0979 wymaga rzeczywistego drugiego komputera, dostarczenia ZIP faktycznym
kanałem, offline selekcji, restartu Windows, aktualizacji, relink źródła
i odczytu wyników. Agent nie może wpisać PASS tych kontroli bez dowodów
operatora. Brak takiego odbioru pozostaje jawnym ograniczeniem wydania.
