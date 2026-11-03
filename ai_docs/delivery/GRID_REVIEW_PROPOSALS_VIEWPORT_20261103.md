# Propozycje do ręcznej korekty i pełny kadr — 2026-11-03

Operator zatwierdził cały zakres i koszt45–90min oraz audyt Opus. TASK-1153 realizuje jeden pion: istniejące propozycje i decyzje człowieka stają się dostępne w głównej Korekcie, a obydwa widoki mają szerszy/pełny kadr. Szczegóły i testy są w tasks/completed/1153-grid-review-proposals-viewport.md.

Źródłem prawdy pozostają istniejące review/geometry/proposal APIs i human approval. Przygotowanie wyniku modelu nigdy nie jest akceptacją ani etykietą. Zmiana kadru UI nie zmienia wejścia modelu15% ani zapisanych punktów. Nie dodajemy API, migracji lub drugiego rejestru danych; nie zmieniamy train/test.

Weryfikacja obejmuje cały opisany przepływ, starszych konsumentów, opóźnione odpowiedzi/utratę odpowiedzi, Reviewer/Admin lint/types/build oraz statyczny HTML. Jeden audyt i jedna runda poprawek; P0/P1 blokują commit. Na końcu task-close/hash i pytanie o merge/push/restart, bez automatycznego wdrożenia lub uruchamiania batcha.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1153 — Propozycje i kadr | gpt-6-astra | high | Integracja istniejących decyzji człowieka i asynchronicznych widoków bez utraty historii | Claude Code claude-opus-5-5/high |
