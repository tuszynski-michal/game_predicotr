---
title: Selector source-first start and resume
status: accepted
last_updated: 2026-10-12
---

# Lokalny selektor — prosty start i historia

Operator zatwierdził zakres i dodatkowe 1–2 godziny2026-10-12.
Obecne foldery są automatyczne, lecz ponowny wybór źródła próbuje tworzyć
projekt zamiast wznowić. Historia nie ma etykiety gry.

## Zakres i rozstrzygnięcia

TASK-0983 obejmuje jeden spójny przepływ od wyboru źródła do wznowienia
oraz ZIP0.1.2. Źródło D:\Mumie\123 daje D:\Mumie\123 selekcja i
D:\Mumie\123 wybrane. Nazwa gry jest etykietą, nigdy fragmentem ścieżki.
Pierwsze otwarcie pyta o grę, pierwszą planszę, opcjonalną górną granicę
oraz kierunek. Potwierdzenie lokalnego miejsca pozostaje wymagane.
Ponowne otwarcie nie pyta o konfigurację i niczego nie resetuje.

Native picker zwraca rendererowi jednorazowy identyfikator konfiguracji,
nie uprawnienie do dowolnej ścieżki. Native szuka projektu w domyślnym
folderze i pomocniczej historii. Źródło oraz ewentualny projectId sprawdza
pod blokadą przed recovery. Konflikt, obcy/uszkodzony folder lub kilka
projektów blokują automatyczne otwarcie; użytkownik może wybrać projekt
z historii. Brak cache nie blokuje wznowienia domyślnego projektu.

ProjectState schema1 otrzymuje opcjonalną gameName (1–80 znaków bez
znaków sterujących), zachowaną przez journal i backup. Stare projekty bez
tego pola pozostają zgodne i mają etykietę źródła. Manifest operator-local
pozostaje bez zmian. Historia maksymalnie10 pozycji jest cache native-only;
projekt pozostaje źródłem prawdy. Kierunek numeracji nie odwraca zdjęć.

## Weryfikacja i odbiór

Sprawdzone moduły: ProjectController.create/open, ProjectStore.create/open,
RecentProjects.list/remember i renderer App. Nowy test kontrolera obejmie
obie numeracje, ponowny proces/instancję, utratę cache, anulowanie, obcy
folder, niedopasowane źródło i ponowienie tokenu. Packaged smoke sprawdzi
rzeczywisty formularz, dropdown i wznowienie po nowym procesie.
Komendy z timeoutami w TASK-0983. Testy są planowane, nie zaliczone.

Najpierw commit źródeł po testach, następnie czysty ZIP z tego commita;
dowody wydania i pełny hash trafiają do końcowego commita dokumentacyjnego.
Stare paczki pozostają zachowane. Nie wykonujemy odbioru na komputerze
odbiorcy ani niezależnego audytu zamiast operatora. Audyt końcowy pozostaje
po stronie operatora zgodnie z jego wcześniejszym poleceniem dla selektora
(D-545); własny przegląd i testy nie są takim audytem. Bez API, usług,
transferu, benchmarku, push/merge i zmian danych użytkownika.

## Wynik wykonania

TASK-0983 done2026-10-12.122 unikalne testy i sześć scenariuszy rzeczywistego
ZIP0.1.2 PASS. Kod: v1.7.328 /9ade6a8596cd316d214cf25339eae40e8789be9f
oraz v1.7.329 /c4181f7ddc8fca2518c2d9abc363ce3bcd307d5f.
Historia jest odświeżana także po relink źródła; regresja obejmuje ponowny
wybór przeniesionych zdjęć po nowym procesie. [Dowody](../quality/OFFLINE_PHOTO_SELECTOR_START_VERIFICATION_20261012.md)
zawierają sumy i pochodzenie paczki. Audyt i fizyczny odbiór pozostają osobne.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0983 | `gpt-6.1-sol` | medium | Typowany przepływ startu, zgodność projektu i testy wydania. | Końcowy audyt operatora; Claude, konfiguracja do potwierdzenia przez operatora, bez niejawnego zastępstwa. |
