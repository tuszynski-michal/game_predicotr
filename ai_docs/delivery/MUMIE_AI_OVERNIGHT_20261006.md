---
title: Mumie — nocny przegląd AI i odrębny eksperyment treningowy
status: accepted
last_updated: 2026-10-06
---

# Cel i zgoda

Operator jawnie zlecił kontynuowanie treningu bez swojej obecności, zaufał
decyzjom wykonawcy i poprosił o wewnętrzne AI do oceny grafik. Ta nowa zgoda
rozszerza granicę poprzedniego etapu D-502/D-504: dopuszcza propozycje AI oraz
jedną odrębną eksperymentalną parę, bez udawania zatwierdzeń człowieka.
Cały poniższy zakres stanowi jeden zlecony etap i jeden spójny task.

## Stan obecny

Qualified V3 ma83/84 human validation,18/18 użytych korekt i9/9 ograniczonej
diagnostyki. Trzeci niezależny film daje8100 pól z60 zdjęć,37 disagreements
i424 niepewnych propozycji.24 dokładne cropy czekają w istniejącym edytorze.
Operator następnie zakończył24 decyzje:19 approve (10=4,Q=4,A=3,Sarkofag=6,
Mumia=1,Sfinks=1) i5 unreadable, revision24. Włączamy19 human targetów z pełną
aktualną historią, priorytetem nad AI. Nieczytelne rastery nie mogą uzyskać AI
targetów.79 blind crops i obie oceny pozostają niezależne od nowych decyzji.

## TASK-0864 — AI review i ograniczony eksperyment

1. Wybrać deterministycznie do100 exact RGB96 rastrów z zakończonego batchu:
   istniejące24 przypadki, pozostałe disagreements i zróżnicowane kontrole klas.
   Dwie niezależne oceny AI widzą raster i zatwierdzone kotwice słownika, bez
   predykcji CNN. Wynik: klasa lub unreadable/grid_issue, pewność high/medium/low,
   krótki powód i osobna obserwacja ramki. Żadnej decyzji w human label store.
2. Kwalifikować tylko zgodne high/high, czytelne i kompletne rastery. Nie używać
   etykiety AI ramki do treningu Super. Zachować wszystkie odrzucone/rozbieżne
   przypadki, pełne oceny i SHA. Przed pikselami sprawdzić pełny base cohort,
   dictionary, batch source exclusions i jednoznaczne przypisanie całego filmu
   do development. Duplicates/alias/source drift blokują.
3. Odrębny format/purpose `symbol_ai_experiment` i generacja4, tylko lokalna.
   Reuse SymbolTrainingInputs i trwałego SymbolRunManager; strict stare adaptery
   odrzucają nowy format. Manifest przypina bazę, batch, oba review, źródła,
   exact render i AI origin. Oryginalne264 human development,84 validation,
   diagnostic9 i18 feedback pozostają bez zmian. AI targets mają wagę1;
   feedback człowieka zachowuje4, w tym nowe19. Walidacja/calibration tylko dawnych84.
4. Wyłączyć z treningu co najmniej20 zaakceptowanych AI przykładów z odrębnych
   zdjęć w tym samym nowym filmie. Indeksy zdjęć modulo3=0 pozostają withheld,
   z wyłączeniem zdjęć zawierających nowe human approvals, które w całości
   trafiają do development. To audit wyglądu w obrębie development,
   nigdy niezależna human accuracy lub niezależny filmowy test. Dobór odbywa się
   przed treningiem, bez znajomości przyszłych wyników. Brak20 przykładów kończy
   eksperyment raportem kwalifikacji bez dopisywania pseudo-zgód.
5. Jedna RGB/gray para od zera,20epok,seed20261005,batch32,lr.001,
   max1800s/10000steps każda, dotychczasowa architektura i augmentacja. Jedna
   aktywna gałąź naraz, trwałe admission/RNG/checkpoint/watchdog/PID. Nie
   powtarzać runów z innym seedem w celu poprawienia liczby.
6. Po finalnym wyborze sprawdzić human84 perclass względem V3, human18/9,
   AI agreement na niewykorzystanych przykładach, nowehuman19 jako training
   regression i exact ONNX parity84. Przed treningiem raportować V3 na tych19,
   wtedy jeszcze bez ekspozycji na etykiety nowego filmu.
   Raport ujawnia AI origin i nie raportuje accuracy nieopisanego filmu.
   Brak human regression jest konieczny do dalszej propozycji, lecz nigdy
   nie aktywuje produkcji. Przy regresji zachować qualified V3.
7. Jeśli wszystkie human gates przejdą, przeliczyć tylko symbole istniejących
   8100 dokładnych pól z60 zdjęć, reuse `reclassify_photo/preprocess/classify_logits`.
   Zamrożona geometria, source/crop SHA i kolejność nie mogą się zmienić.
   Odrębne create-only wyniki eksperymentu, maksymalnie20 zdjęć na krok120s,
   retry/new-process identyczny. Raportować liczbę niepewnych/disagreements,
   accuracy=null i ekspozycję części nagrania na trening. Nie używać generacji4
   jako produkcyjnego batchu ani nadawać human approvals.

## Weryfikacja i odbiór

Testy: consensus/provenance, zła klasa/origin, checksum/source/render drift,
cross-partition duplicates, niezmieniona validation, strict stare adaptery,
generation/purpose i checkpoint sampler replay. Focused pytest, Ruff i scoped
mypy przed realnym uruchomieniem. Nowy proces odtwarza manifest i raport,
identyczny retry nie duplikuje danych/runu. Odrębny audyt kodu i danych przed
commitem, Outcome/CURRENT_STATE oraz porównanie z DoD.

Ryzyka: AI może zgodnie popełnić błąd; wspólny model reviewerów nie zapewnia
statystycznej niezależności. Złota ramka wymaga osobnej referencji; samo CNN
klasy nie rozwiązuje Super. Mała reused walidacja nie dowodzi transferu.
Po etapie człowiek ma konkretne propozycje i zachowaną kolejkę korekt.
Bez DB, migracji/usuwania, aktywacji, merge/push/wdrożenia, nowych płatnych API.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0864 — AI review i odrębny trening | gpt-6.1-sol | high | Trwałe pochodzenie ocen, ochrona human validation i istniejącego run protocol. | Dwa odrębne przeglądy grafik oraz audyt implementacji: gpt-6.1-sol, high; jawna zgoda operatora na wewnętrzne AI |
