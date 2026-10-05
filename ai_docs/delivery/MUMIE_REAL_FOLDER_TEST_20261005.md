---
title: Mumie — pierwszy test rzeczywistego folderu
status: accepted
last_updated: 2026-10-05
---

# Mumie — pierwszy test rzeczywistego folderu

## Stan, zgoda i cel

Operator wskazał folder `C:\Users\tuszy\Documents\mumie wybrane\1 - 23175 cut`
i pozwolił wykonawcy wybrać część albo całość. Folder ma 2580 JPEG-ów.
Lab ma 31 kompletnych zdjęć, z czego 11 nie uczestniczyło w dotychczasowych
iteracjach. Dwa dostępne eksporty ONNX pochodzą z iteracji 2 i 3.
Test laboratoryjny nie uruchamia V3-D ani zapisu do produkcyjnej bazy.

## TASK-0845 — pomiar i podgląd

1. Zinwentaryzować bajty oraz zakresy `seq_*`, zachować kolejność liczbową.
   Przypiąć manifest do SHA-256 źródeł, anotacji oraz obu bundle.json.
   Wykryć duplikaty i źródła użyte wcześniej w treningu lub ocenie. Kontrola
   folderu wykazała sześć nazw z sufiksem ` — kopia`; zachować ich zakresy,
   a deduplikować wyłącznie po identycznym SHA, preferując oryginalną nazwę.
2. Założenie wykonawcze w ramach zgody na dobór: do pierwszego testu wybrać
   200 unikalnych zdjęć równomiernie po całym zakresie, wykluczając dokładne
   SHA wszystkich 31 aktualnie kompletnych źródeł. Nie twierdzić, że zdjęcia
   z tego samego nagrania są niezależnymi rodzinami.
3. Osobno porównać oba modele na nowych 11 aktualnie kompletnych zdjęciach.
   Są niewidziane przez te checkpointy; nie rozpoczynać ich uczenia przed testem.
   Użyć istniejących metryk D-483 i jawnie podać małą oraz powiązaną próbę.
   Odbiór wykazał, że wszystkie 99 nowych referencji to niezmienione propozycje
   iteracji 3 zatwierdzone przez operatora. Ujawnić pochodzenie w osobnym audycie
   i podglądzie; nie przedstawiać niemal zerowego błędu iteracji 3 jako dowodu
   niezależnej przewagi. Zatwierdzenia pozostają ważne i nie są wycofywane.
4. Użyć istniejącego `onnx_engine` i `evaluate_photo`; nie zmieniać dekodowania,
   progów, treningu ani modelu produkcyjnego. Dane folderu mają unknown jakość.
   Liczba plansz zgodna z nazwą jest diagnostyką, nie wynikiem skuteczności.
5. Przetwarzać w ograniczonych krokach do 120 s, z postępem i create-only
   wynikami per zdjęcie. Wznowienie w nowym procesie ma odzyskać zgodne wyniki.
   Zmiana źródła, modelu lub anotacji blokuje zależny krok, bez nadpisywania.
6. Przygotować pełne nakładki obu modeli i podgląd do wizualnego przeglądu.
   Zapisać rzeczywiste wyniki, ograniczenia, rekomendację następnego zakresu,
   testy, Outcome i CURRENT_STATE; osobny commit.

## Błędy, odbiór i wyłączenia

Nieprawidłowy zakres lub symlink blokuje manifest. Brak obrazu albo drift SHA
blokuje daną operację; błąd inferencji nie jest zerem poprawnych plansz.
Niekompletne lub nieaktualne zatwierdzenie nie daje etykiet ewaluacyjnych.
Brak etykiet folderu wyklucza procent poprawności; należy obejrzeć wynik.
Wznowienie, integralność i końcowe podsumowanie sprawdzić z nowego procesu.
Testy obejmują wybór liczbowy, równomierny dobór, wykluczenie znanych źródeł,
zmianę wejścia i recover wyników. Weryfikacja typów i lint dla nowego narzędzia.

Poza zakresem: trening, przywrócenie/aktywacja modelu, symbole i ramka Super,
migracje, import produkcyjny, zmiana zatwierdzeń, V3-D, push i wdrożenie.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0845 — test rzeczywistego folderu i porównanie modeli | gpt-6.1-sol | high | Integralność źródeł, rozdzielenie treningu i oceny oraz uczciwe metryki | Testy regresji, nowy proces i wizualny przegląd; bez delegowania |
