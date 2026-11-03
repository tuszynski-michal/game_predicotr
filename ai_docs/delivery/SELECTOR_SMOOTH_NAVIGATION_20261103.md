# Selektor — płynna nawigacja 2026-11-03

Status: accepted. Operator zlecił cały plan P1–P3 i zaakceptował koszt 2–4 godzin. Bez dodatkowego audytu zgodnie z tabelą planu. Praca od main, bez merge/push.

## Cel i zadania

- TASK-1142 (P1): atomowa podmiana obrazu bez pustej klatki, poprzedni obraz oznaczony podczas ładowania, prefetch trzech celów w każdą stronę według skoku; 7 wpisów, 128 MiB, ochrona widocznego obrazu i celu podczas przejścia. F przypina cel. Regresje: błędy, zmiany kierunku, zoom/scroll/fullscreen.
- TASK-1143 (P2): indeks inventory raz, wąskie projekcje i podsumowania decyzji, skrócone aktualizacje nawigacji z bazową rewizją i snapshot fallback. Zachowane kontrole rzeczywistego manifestu, SHA i trwały format. Współdzielenie serializacji w transakcji.
- TASK-1144 (P3): baseline i pomiar końcowy, testy, nowy ZIP, dokumentacja. Cel warm p95 <=50 ms. Odbiór dużej istniejącej partii wymaga bezpiecznie dostępnych danych. Bez syntetycznego dużego korpusu i operacji na oryginałach. Niespełnienie celu blokuje potwierdzenie płynności.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1142 | gpt-6.1-sol | high | Synchronizacja obrazu i wyboru. | Nie; regresje Electron. |
| TASK-1143 | gpt-6.1-sol | high | Rewizje IPC i integralność zapisu. | Nie; recovery i kontrakty. |
| TASK-1144 | gpt-6.1-sol | medium | Pomiar i wydanie. | Nie; smoke finalnego ZIP. |
