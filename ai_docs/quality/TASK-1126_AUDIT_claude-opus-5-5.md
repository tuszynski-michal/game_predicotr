# Audyt TASK-1126 — Shift i trwały zapis grup jakości

Werdykt: PASS

**Audytor:** claude-opus-5-5 / medium
**Wykonawca:** gpt-6.1-sol / medium
**Runda:** 2 (tylko poprawki do uwag z rundy 1)
**Zakres:** HEAD e4bdfcbf plus zmiany niezacommitowane
**Data:** 2026-11-03

Przegląd był statyczny: 11 odczytów i wyszukań (Read/Grep). Nie zmieniłem żadnego pliku i niczego nie uruchamiałem.

## Streszczenie
Wszystkie uwagi z rundy 1 są poprawione: P1-1 oraz P2-1, P2-2 i P2-3.
- **Porzucenie kolejki:** operator robi to jawnie i musi potwierdzić. Akcja usuwa tylko klucz `readability-label-queue:<gameId>` w localStorage. Nie wysyła żadnych żądań do API i nie cofa zapisów.
- **Uszkodzona kolejka:** ma tę samą ścieżkę porzucenia i nie zgaduje liczników.
- **Blokada w trakcie żądania:** porzucenie jest niedostępne, gdy trwa żądanie.
- **Testy:** nie udają już, że trwały konflikt 409 sam znika.

Mechaniki Shift nie audytowałem ponownie.

## Znaleziska
**P0:** Brak.

**P1:** Brak.

**P2:** Brak blokujących. Dwie drobne uwagi, nie wpływają na werdykt:
- **N-1. Surowy angielski błąd przy uszkodzonym JSON.** `readability-label-queue.ts:21` wywołuje `JSON.parse` bez obsługi błędu. Przy wpisie typu `{broken` alert pokazuje angielski SyntaxError zamiast komunikatu „Nie można odczytać zapisanej kolejki ocen.” (linia 49). Okno potwierdzenia jest poprawne, bo opiera się na `queueUnreadable`. Wystarczy otoczyć parse `try/catch` i rzucić ten sam polski komunikat.
- **N-2. Tekst z liczbami nie jest sprawdzany w teście.** Okno potwierdzenia porzucenia pokazuje „Wykonane X… Pozostałe Y” (`readability-workspace.tsx:535`), ale test UI sprawdza tylko zdanie o niepotwierdzonej porcji (`readability-workspace.test.mjs:341-344`).

## Pokrycie kryteriów poprawek
| Kryterium | Status | Dowód |
|---|---|---|
| Jawny przycisk „Porzuć pozostałe porcje” i potwierdzenie z „Zachowaj kolejkę” albo „Potwierdź porzucenie” | OK | `readability-workspace.tsx:517-551` |
| Porzucenie usuwa tylko klucz kolejki tej gry, bez API i bez cofania zapisów | OK | `readability-label-queue.ts:135-137`; test jednostkowy `:109-119` (inna gra i `readability-command:other` nietknięte); test UI `:350-354` (`received.length === 2`) |
| Niedostępne, gdy trwa żądanie | OK | przycisk ma `disabled={blocked}` (`blocked` obejmuje `busy`, `:226`); `discardQueue` sprawdza `commandBusy` (`:356`); przyciski w oknie mają `disabled={busy}`; otwarte okno blokuje inne komendy (`discardRequested` w `blocked`); test `:383-413` |
| UI wyjaśnia: X potwierdzonych zostaje, Y nie zostanie ponowionych, niepotwierdzona porcja mogła już zostać zapisana | OK | `:533-538` |
| Uszkodzona kolejka: ta sama ścieżka, bez zgadywania liczników | OK | `queueUnreadable` (`:106`, `:121-126`); przycisk widoczny dla `labelQueue !== null \|\| queueUnreadable`; test UI `:362-381` |
| Po porzuceniu odświeżenie, wyczyszczone zaznaczenie i reset anchora; nowe komendy działają | OK | `:358-365`; „Przygotuj pilot” wysyła `start` (test `:355-356`, `:376-377`) |
| Bez rebase i bez automatycznego czyszczenia | OK | `drain` przy błędzie tylko rzuca wyjątek (`:120-123`); klucz znika wyłącznie po pełnym ukończeniu kolejki albo po jawnym porzuceniu |
| P2-1: kodowanie UTF-8 i pełny komunikat w teście | OK | polskie znaki poprawne w `readability-label-queue.ts:49,64,69,122` i w nagłówku taska; test sprawdza pełny komunikat (`:75`) |
| P2-2: trwały 409 przy identycznym ponowieniu dalej wstrzymuje kolejkę | OK | test jednostkowy `:84-100` (porcja identyczna z oryginałem, ogon nie wysłany, `completed` = 1); test UI `:331-335` (dwa ponowienia z identycznym body); utracona odpowiedź osobno: proces Node `:121+` i cold mount w UI `:245-302`, `:482+` |
| P2-3: limit porcji liczony ze stałych | OK | `readability-label-queue.ts:28-29` (`Math.ceil(MAX/BATCH)`) |
| Outcome taska opisuje poprawki | OK | `1126-shift-range-selection.md:61-78` („Audit corrections (runda 1)”) |

## Zamknięte i otwarte
- **Zamknięte:** P1-1, P2-1, P2-2, P2-3.
- **Otwarte (opcjonalne, nieblokujące):** N-1, N-2.
- Sugestia z rundy 1, żeby zapisywać w kolejce ostatni status błędu, nie została wdrożona. Była oznaczona jako „rozważyć”. UI nie odróżnia „ponów” od „konfliktu”, ale ścieżka porzucenia zamyka ślepy zaułek, więc nie jest to warunek.

## Testy
Wyniki podaje wykonawca, ja ich nie uruchamiałem:
- 9/9 testów kolejki i stanu PASS
- 12/12 testów UI readability PASS
- strict TypeScript i lint zmienionych plików PASS

Przeczytane testy odpowiadają opisanym scenariuszom:
- trwały 409 przy dwóch identycznych ponowieniach;
- anulowanie i potwierdzenie porzucenia;
- brak wywołań API po porzuceniu;
- nowy `start` po porzuceniu;
- uszkodzony JSON;
- blokada porzucenia w trakcie żądania;
- utracona odpowiedź w nowym procesie Node i przy cold mount.

## Ograniczenia
- Czytałem tylko wskazane fragmenty: całą kolejkę, fragmenty workspace `:95-139`, `:220-379`, `:495-564`, testy oraz nagłówek i Outcome taska.
- Nie czytałem pełnych diffów, mapy kodu, symbol-review ani backendu.
- Wyników testów nie weryfikowałem.
- Przypadek dwóch kart przeglądarki z tą samą kolejką jest poza zakresem.
- Brak operacji operatora i testu live na Androidzie.

Zgodnie z poleceniem to jedyna runda poprawek: nie zlecam kolejnej.
