---
title: Lokalny selektor Windows — projekt instrukcji operatora
status: proposed
last_updated: 2026-10-11
---

# Lokalny selektor Windows — instrukcja projektowana

Program nie jest jeszcze zaimplementowany i paczka nie jest dostępna.
Ten dokument opisuje zaakceptowany sposób pracy, nie potwierdzone działanie.
Komendy build/release i rzeczywiste dowody zostaną uzupełnione w 0975/0979.

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
