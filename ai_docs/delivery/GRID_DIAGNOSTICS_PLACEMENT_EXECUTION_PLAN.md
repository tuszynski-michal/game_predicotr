---
title: Przeniesienie diagnostyki siatek do korekty
status: accepted
last_updated: 2026-10-07
---

# Diagnostyka siatek w Korekcie cięcia siatki

## Stan, cel i zgoda

Operator wskazał, że problemy siatek należą do „Korekty cięcia siatki”,
a „Import plansz” nie powinien zawierać dodatkowego panelu diagnostycznego.
Obecny GeometryCompletenessSection znajduje się pod MissingBoardsSection
w ImageFolderImportPanel. ReviewerAccessLauncher już pobiera joby i pokazuje
istniejącą kolejkę korekty oraz odroczone geometrie.

## Zakres i reguły

TASK-0890 przenosi istniejący komponent do ReviewerAccessLauncher, pod
uruchomienie kolejki korekty. Wykorzystuje joby tej gry do wyboru importu
i zachowuje filtry, podgląd zdjęcia, wyjątki oraz jawne szukanie słabych cropów.
Odświeżenie kolejki pobiera kontekst ponownie i odświeża diagnostykę.
Komponent jest kluczowany gameId: zmiana gry nie zachowuje poprzednich danych.
Import nadal zawiera MissingBoardsSection, foldery i przebieg importu.

Nazwa diagnostyki i opis wyjaśniają przeznaczenie oraz wyjątek V3 D-523:
raport całego zdjęcia nie oznacza braku wszystkich cropów. Stan odrzuconej
siatki pozostaje własnością istniejącego backendu/kolejki; przeniesienie UI
nie zmienia kwalifikacji, sekwencji ani danych.

Istniejące ścieżki: apps/admin/src/features/imports/geometry-completeness-section.tsx
— GeometryCompletenessSection; features/reviewer-access/reviewer-access-launcher.tsx
— ReviewerAccessLauncher; features/catalog/catalog-workspace.tsx — GAME_SECTION_OPTIONS.
Nowy test interakcji: apps/admin/test-interactions/grid-diagnostics-placement.test.mjs.
Szczegóły, pliki i polecenia w TASK-0890.

## Odbiór, ryzyka i wyłączenia

Sprawdzić brak diagnostyki i jej zapytań w imporcie, obecność w korekcie,
zakres gry/importu, odświeżenie, błąd z ponowieniem, ponowne zamontowanie
oraz zmianę gry z opóźnioną odpowiedzią. Uruchomić testy istniejącego
importu/kolejki, formatowanie, lint, typy i build Admina. Odczytać rzeczywiste
ekrany po odświeżeniu bez zapisu danych.
Ryzyko: historyczny raport kompletności nie jest miarą dostępności cropów V3;
opis musi to zachować. Bez zmian API, bazy, migracji, uruchamiania importu,
treningu, aktywacji modelu, cleanupu, push ani merge.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
| --- | --- | --- | --- | --- |
| TASK-0890 — przeniesienie diagnostyki siatek | gpt-6.1-sol | high | Istniejący komponent i kontrakt, mała zmiana UI z ochroną zakresu gry. Ponowna analiza przy konieczności zmiany kwalifikacji backendu. | Przegląd diffu i testy wykonawcy; niezależny agent niewymagany. |
