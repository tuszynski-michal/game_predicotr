---
title: Mumie — ocena zamrożonych modeli po oznaczeniu kontrolnych wycinków
status: accepted
last_updated: 2026-10-06
---

# Stan i cel

Operator zakończył26 przypadków z kolejki TASK-0864. Magazyn ma27 decyzji
i26 aktualnych approve. Dwadzieścia dwa wycinki były wyłączone z treningu
eksperymentalnej pary; cztery pozostałe były niejednoznaczne. Obecny wynik
22/22 dotyczy zgodności z AI. Teraz potrzebny jest wynik względem człowieka.
Kontynuacja jest objęta wcześniejszym poleceniem samodzielnej pracy oraz
potwierdzeniem zakończenia wskazanej interakcji. Jeden task, bez nowego treningu.

## TASK-0865 — rzeczywisty human audit

1. Użyć istniejącego `BatchReviewStore` i `symbol_feedback.prepare/verify_pack`
   do create-only pakietu26 ostatnich decyzji. Sprawdzić całą historię27,
   aktualny słownik, źródła, quady, dokładny PNG/pixel SHA i bieżące guardy.
   Operator ma pierwszeństwo nad AI. Nowe pliki wyłącznie w odrębnym
   `artifacts/mumie-human-audit-20261006`, bez mutowania magazynów.
2. Zweryfikować zamrożony manifest/parę/evaluation TASK-0864 i qualified V3.
   Przypiąć actual reports/ONNX oraz wszystkie wejściowe SHA. Sprawdzić,
   że26 rastrów nie należało do development312;22 audit rastry muszą także
   pochodzić ze zdjęć rozłącznych z development. Pozostałe4 otrzymują jawny
   status diagnostyczny, bez obietnicy izolacji całego zdjęcia.
3. Porównać rzeczywiste ONNX V3 i V4 na dokładnych26 PNG, zachowując ich
   dotychczasowy preprocess, słownik, temperature/fusion weight/threshold.
   Porównać predykcje z wcześniejszymi source-bound wynikami tego samego
   pola. Nie dopasowywać modeli, kalibracji ani progów do nowych etykiet.
4. Raportować22 human-referenced audit osobno od4 diagnostic: liczności,
   perclass/pooled wynik RGB/gray/fuzji, błędy, confidence i zgodność z AI.
   Jeden film był częściowo użyty w development, dobór jest kierowany;
   wynik nie jest accuracy całego filmu ani niezależnym filmowym testem.
   Rozbieżność z AI pozostaje dowodem błędu etykiety AI, nie zmianą człowieka.
5. Nowy proces odtwarza identyczny pakiet/raport i kontroluje input SHA,
   model/run/training artifacts oraz wszystkie poprzednie decyzje. Odrębny
   audyt, dokumentacja, Outcome/CURRENT_STATE i własny commit. Jeśli drift
   albo brak decyzji blokuje kwalifikację, raportować konkretną przyczynę.

## Odbiór i granice

Kryteria:26 latest decisions z pełną historią, dokładny podział22/4,
zamrożone modele/kalibracja, actual ONNX oraz wyniki perclass/błędy,
brak mutacji wejść i identyczny retry w nowym procesie. Testy skoncentrowane
na istniejącym feedback pack/metrics oraz negatywna kontrola drift/binding.
Nie dodawać UI/API, schematu, nowego treningu, Super targetów, pseudo-zgód,
zmian geometrii, DB/migracji/usuwania, aktywacji, merge/push/wdrożenia.
Każdy lokalny krok ma istniejący absolutny runner z limitem120s.
Raport kończy etap konkretnym wynikiem i zaleceniem dalszego zbierania danych.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0865 — human audit zamrożonych modeli | gpt-6.1-sol | high | Kontrola historii, braku ekspozycji na nowe targety i rzeczywistych metryk bez dopasowania modeli. | Niezależny audyt danych i wyników: gpt-6.1-sol, high; wcześniejsza jawna zgoda na wewnętrzne AI |
