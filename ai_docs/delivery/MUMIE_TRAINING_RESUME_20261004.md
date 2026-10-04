---
title: Mumie — wznowienie uczenia siatek i przygotowanie danych symboli
status: accepted
last_updated: 2026-10-04
---

# Mumie — wznowienie uczenia i większe porcje danych

## Zgoda i granice wykonania

Operator 2026-10-04 polecił niezależnie dokończyć wgrywanie Mumii, rozpocząć
uczenie siatek oraz przygotować większe porcje danych do późniejszego uczenia
symboli. Doprecyzował, że złota ramka wskazuje zwykły symbol wybrany do supergry.
To polecenie wznawia tor Mumii zatrzymany po iteracji 3. Nie zatwierdza starego
planu wypłat premium ani aktywacji V3-D.

## TASK-0842 — dane i jedna oceniana iteracja

1. Sprawdzić SHA wszystkich 225 zdjęć znanego folderu Mumii względem katalogu
   laboratorium (236 zdjęć wraz z wcześniejszym materiałem). Zaimportować jedynie
   rzeczywiście brakujące źródła przez istniejący niezmienny snapshot.
2. Wznowić istniejący run 3, iteracja 4, preset F, w dotychczasowym budżecie
   14 400 s. W chwili wznowienia jest 20 kompletnych zdjęć, bez nowych zatwierdzeń.
   Jawne założenie wykonawcze: jedna próba z tymi samymi danymi
   (`--allow-same-data`) sprawdzi nową regułę wyboru F; nie udaje większego zbioru
   etykiet i nie rozpoczyna kolejnych powtórzeń bez nowych danych.
3. Zachować trwały holdout Mumii (16 trening / 4 odłożone), strażnik 777 oraz
   warunek ścisłej poprawy holdoutu przed publikacją nowego modelu. Nie zamieniać
   propozycji modelu na zatwierdzenia człowieka. Nie zmieniać profilu produkcyjnego.
4. Przygotować stabilne partie po najwyżej 50 całych zdjęć do przeglądu geometrii,
   z pełnymi źródłami, nakładkami i wskazaniem kolejki 8105. Przygotować wycinki
   symboli wyłącznie z aktualnie kompletnych zatwierdzonych zdjęć; bez etykiet
   odziedziczonych z 777 i bez automatycznych zatwierdzeń.
5. Osobno sprawdzić istniejący słownik i etykiety Mumii. Brak prawdziwych etykiet
   blokuje trening klasyfikatora symboli, ale nie przygotowanie wycinków.
6. Zapisać raport rzeczywistych liczności, metryk, zużycia czasu, ograniczeń i
   następnego kroku. Zakończyć TASK-0842 osobnym wersjonowanym commitem.

## TASK-0843 — dokończenie wgrywania w głównej aplikacji

Po zamknięciu TASK-0842 utworzyć brakującą grę „Mumie” jako draft z wdrożonym
profilem `grid_profile_mumie_v1`, bez reguł wypłat, aktywacji klasyfikatora i
zgadywania etykiet. Wgrać znany folder 225 zdjęć przez istniejący staging API.
Zachować jawne zakresy `seq_*` z nazw; nie przenumerowywać źródeł na ciągły zbiór.
Wykonać preflight i dostępne przetwarzanie z wirtualnymi komórkami; wymagające
decyzji pozycje pozostawić do przeglądu. Stan i identyfikatory stagingu/jobów
zapisać na dysku przed następnym krokiem. Wznowienie nie może dublować uploadu
ani joba. Polecenie operatora „dokończ wgrywanie” obejmuje te addytywne zapisy
przez istniejące API; nie obejmuje migracji, kasowania ani zatwierdzania za niego.

## Symbol wybrany do supergry

Proponowana krótka etykieta UI: **Super**. Złota ramka jest osobną obserwowalną
cechą obrazu, niezależną od klasy symbolu. Trzy mumie uruchamiają tryb, ale nie
ujawniają tożsamości wybranego symbolu. Rozpoznanie musi wskazać zarówno klasę,
jak i obecność ramki; brak widocznej ramki nie pozwala zgadywać wybranego symbolu.
Uczenie ramki wymaga przykładów dodatnich i ujemnych z osobnymi zatwierdzeniami.
Złota obwódka całej planszy nie jest etykietą komórki. Mechanika rozwijania kolumn
i wypłat zostaje na później; stary plan liczenia premium gdziekolwiek nie jest
aktualną specyfikacją tej mechaniki.

## Odbiór i trwałość

Odczyt liczności i integralności z nowego procesu; ledger treningu i raport iteracji;
manifesty partii wiążące źródła SHA, rewizje siatek, pochodzenie i checksum wycinków.
Ponowne przygotowanie identycznego stanu musi odzyskać ten sam artefakt, nie
nadpisywać go. Nowy stan tworzy nowy artefakt. Nie usuwać danych ani zmieniać
zatwierdzeń operatora. Nie uruchamiać benchmarku, shadow ani final-test nowych gier.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0842 — import, iteracja F i partie Mumii | gpt-6.1-sol | high | Pochodzenie etykiet, trwały budżet i rozdzielenie propozycji od prawdy | Kontrola integralności, testy regresji i samodzielny przegląd; bez delegowania |
| TASK-0843 — gra Mumie i wgranie zdjęć przez API | gpt-6.1-sol | high | Trwałe wznowienie stagingu, kolejność sekwencji i izolacja gry | Kontrola requestów, odczyt z nowego procesu i samodzielny przegląd; bez delegowania |
