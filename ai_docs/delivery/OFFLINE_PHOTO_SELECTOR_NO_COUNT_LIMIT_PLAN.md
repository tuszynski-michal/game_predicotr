---
title: Selektor Windows bez limitu liczby zdjęć
status: accepted
last_updated: 2026-10-13
---

# Selektor Windows bez limitu liczby zdjęć

Operator polecił usunąć limit 15 000, ponieważ rzeczywiste foldery zawierają
20–30 tysięcy zdjęć. TASK-0988 usuwa limit przy skanowaniu źródła i walidacji
projektu, a także limit liczby wpisów katalogowych. Nie zastępuje ich większą
stałą ani przełącznikiem wymagającym konfiguracji. Sprawdzanie ścieżek,
checksum, własności i trwałości pozostaje bez zmian. Nie zmienia formatów danych.

Wykonanie: zmiana dwóch modułów, regresje indeksu i zapisanego projektu dla
30 000 pozycji, aktualizacja wymagań/architektury/instrukcji, testy desktopu,
lint/typecheck i nowy ZIP0.1.4. Test indeksu używa kontrolowanych metadanych
systemu plików; nie tworzymy wielotysięcznych zbiorów JPEG-ów ani benchmarku.
Dotychczasowy pomiar15 000 pozostaje historycznym pomiarem, a nie limitem.
Nie deklarujemy zmierzonych czasów dla20–30 tysięcy rzeczywistych zdjęć.
Aktualizacja instrukcji Word pozostaje osobnym zadaniem na polecenie operatora. TASK-0988 done; odbiór wydania1.0.0 zatwierdzony D-547.

Audyt operatora na końcu zgodnie z D-545/D-546; ta mała zmiana nie uruchamia
nowej rundy audytu. Nie zmieniamy API/Admin/Reviewera ani danych użytkownika.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0988 | gpt-6.1-sol | medium | Usunięcie dwóch warunków i licznikowego ograniczenia skanu, regresje istniejącego kontraktu oraz pakowanie. | Audyt operatora na końcu według D-545/D-546; bez nowego audytu przed commitem. |
