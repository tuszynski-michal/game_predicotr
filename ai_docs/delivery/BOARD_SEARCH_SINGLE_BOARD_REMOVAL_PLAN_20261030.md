---
title: Usunięcie wyszukiwania wielu układów
status: accepted
last_updated: 2026-10-30
---

# Powrót do wyszukiwania jednej planszy

## Stan i cel

Użytkownik polecił usunąć dodawanie kolejnych układów i wyszukiwanie ich razem.
Ma pozostać wyszukiwanie jednej planszy oraz przeglądanie sąsiednich plansz.
Operator zaakceptował plan i koszt 1–2 godzin oraz zlecił TASK-1113
2026-10-30. Bez zgody na restarty, migracje, merge i push.

Plan przygotowano w TASK-1112 na bazie `main` v1.7.505 / `8b5bb2b7`.
Ograniczona diagnoza kodu potwierdziła:

- `useBoardSearchSequence.search` już wysyła jeden wzór przez
  `searchGameBoards` (GET). Dopiero 2–4 wzory korzystają z POST i osobnego
  rankingu. Nie ustalono pomiarem źródła wszystkich zgłoszonych timeoutów.
- `storage/board_search_sequence.py::_sequence_statement` oblicza dowody
  osobno dla wzorów, łączy pozycje i szereguje całą populację przed LIMIT.
  To zapytanie wykonywane w żądaniu, nie osobny job workera.
- `useBoardSearchSequence` przy otwarciu strony może automatycznie odtworzyć
  i wykonać `lastSubmitted` z localStorage. Historia Admina także odtwarza
  wielowzorowe wpisy v2. Ukrycie przycisku nie usuwa tych dróg wykonania.
- `BoardSearchPhotoNavigation` pobiera sąsiednie zdjęcie pojedynczo po
  kliknięciu. Obsługuje ±15, również dla pojedynczego wyniku. Włączenie tego
  komponentu w `BoardSearchWorkspace` jest dziś związane z `sequenceEnabled`.
- Wyszukiwanie jest wspólne dla Admina, linku jednej gry i panelu wielu gier.
  Panel zarządzania ma odrębny, istniejący przepływ pojedynczej planszy.

## Zakres i rozstrzygnięcia do akceptacji

1. Całkowicie usunąć wykonanie wyszukiwania wielu układów: przycisk „Dodaj
   układ”, zakładki wzorów, wielowzorowy stan wykonawczy, POST, ranking SQL,
   klienta i cache odpowiedzi ciągów. Nie optymalizować ani nie pozostawiać
   ukrytej przełączanej wersji tej funkcji.
2. Zachować GET jednej planszy, obecne reguły dopasowania (w tym D-570 dla
   777a2), domyślne 40 wyników, walidację, korekty, wykres i kalkulator.
   Zachować poprawki obsługi limitu, oczekujących obliczeń i spóźnionych
   odpowiedzi. Nie cofać całych historycznych commitów.
3. Zachować „Poprzedni układ” i „Następny układ”: do 15 numerów przed
   znalezioną planszą i 15 po niej, bez zawijania i pomijania luk. Dwa
   kliknięcia przechodzą o dwie plansze. Dolna granica to numer 1.
   Zmiana zdjęcia nie zmienia wyniku rankingu ani kotwicy wygranych.
   „Pokaż planszę” i korekta dotyczą aktualnie oglądanego numeru.
4. Nowy zapis stanu przeglądarki opisuje jeden wzór (`cells`), bez listy
   wzorów. Poprawny dawny zapis z dokładnie jednym wzorem i co najwyżej
   jednym wzorem w `lastSubmitted` można odtworzyć jako pojedyncze szukanie.
   Wielowzorowy lub mieszany zapis nie uruchamia żadnego zapytania: pusty
   edytor i komunikat „Wyszukiwanie wielu układów zostało usunięte. Wpisz
   jedną planszę.” Oryginalny zapis pozostaje pod starym kluczem, nowy stan
   korzysta z nowej wersji/klucza; bez globalnego czyszczenia localStorage.
   Brak dostępu do storage nie blokuje ręcznego szukania.
5. Historia v2 i snapshoty korekt pozostają czytelne. Odtworzenie wpisu z
   więcej niż jednym wzorem kończy się komunikatem o usuniętej funkcji,
   bez żądania wyszukiwania i bez cichego wyboru pierwszego lub ostatniego
   wzoru. Dotyczy też odtworzenia wygranej lub detalu powiązanego z takim
   wyszukiwaniem. Historia pojedynczego wzoru nadal działa, także v2/1.
6. Usunąć trasy POST z OpenAPI oraz metody klienta. Dawny klient wysyłający
   POST do istniejącej ścieżki GET otrzyma 405; proxy odrzuci metodę przed
   przekazaniem do API. Test ma potwierdzić brak uruchomienia usługi
   wyszukiwania. GET, uprawnienia, cookie, Origin i ochrona innych mutacji
   pozostają bez zmian. To jawna zmiana niezgodna ze starym klientem
   wielowzorowym; po wdrożeniu należy odświeżyć otwarte strony.
7. Nie usuwać plansz, zdjęć, logów ani korekt. Zachować migrację 0169,
   aktualną głowę Alembic, limit historycznych wpisów i manifest v19.
   Nie wykonywać downgrade ani migracji danych. Parsery używane do
   odczytu historycznego nie są silnikiem wyszukiwania i pozostają.

## Wykonanie — jeden etap, jeden task

**TASK-1113 — Usunięcie wyszukiwania wielu układów.** Pełna karta:
[1113-remove-multi-board-search.md](../tasks/completed/1113-remove-multi-board-search.md).

Wykonano TASK-1113; wyniki i ograniczenia w jego Outcome.

Jeden spójny commit implementacyjny obejmuje UI, backend, OpenAPI,
wygenerowanego klienta, regresje i dokumentację. Kolejność pracy:

1. Ponowny odczyt taska i planu, kontrola aktualnego stanu gałęzi i cudzych
   zmian. Zapis decyzji zastępującej wielowzorowy zakres D-573, bez zmiany
   zachowanej nawigacji; numer decyzji ustalić z aktualnych indeksów.
2. Usunięcie tras POST oraz wykonawczych elementów ciągu z aplikacji,
   repozytorium, domeny i dedykowanego middleware. Zachowanie parserów
   historii i korekt. Aktualizacja proxy, OpenAPI i klienta w tym samym pionie.
3. Uproszczenie wspólnego edytora do jednego wzoru, usunięcie cache ciągów,
   zabezpieczenie odtwarzania i uniezależnienie nawigacji od starej
   capability `searchGameBoardSequence`. Zachowanie obecnych zabezpieczeń
   pojedynczego wyszukiwania, bez przywracania całego starego trybu legacy.
4. Testy zmienionego pionu, lint i typy, kontrola generacji oraz kompilacja
   obu hostów. Aktualizacja wymagań, kontraktu, mapy kodu, Outcome i zamknięcie
   taska skillem `task-close`. Zatrzymanie po raporcie; bez merge i push.

## Odbiór i testy

| Wymaganie / TASK-1113 | Dowód wymagany przed zamknięciem |
|---|---|
| Jeden wzór w Adminie, linku i panelu | Test interakcji: brak dodawania i zakładek, jedno GET, poprawne wyniki; puste/wyłącznie `?` nie wysyłają żądania. |
| Nie ma wykonania wielu wzorów | Testy HTTP i proxy: stary POST odrzucony bez wywołania wyszukiwarki; OpenAPI bez tych operacji; brak produkcyjnych odwołań do rankingu ciągów. |
| Nawigacja zachowana | Wynik #100: #99, #98, powrót do #100, #101, #102; granice ±15 i #1, bez zmiany rankingu/kotwicy. |
| Błędy zdjęć i późne odpowiedzi | Brak lub stale zachowuje poprzedni obraz, ponowienie dotyczy tego samego numeru; spóźniona odpowiedź nie podmienia nowego wyniku. |
| Korekty i kalkulator | Detal oraz korekta sąsiedniej planszy używają jej numeru; odświeżenie po korekcie, limit i oczekujące obliczenia zachowują dotychczasowe reguły dla jednego wzoru. |
| Stan po ponownym otwarciu | Nowy mount z dawnym storage 2–4 wzorów: komunikat i zero zapytań. Jeden wzór: poprawne odtworzenie. Osobne testy StrictMode, uszkodzonego storage i spóźnionych odpowiedzi. |
| Historyczne wpisy | V2/2–4 i powiązane zdarzenia nie wykonują szukania; log i korekty nadal widoczne. Legacy oraz v2/1 nadal odtwarzane. |
| Wspólny komponent | Regresje panelu zarządzania i istniejącego zapisu wyboru, bez zmiany domyślnego workflow. |
| Kontrakt i jakość | Test żądania GET wrappera, generacja OpenAPI/klienta bez driftu, lint/typecheck zmienionych modułów, build Admina i Reviewera, `docs:check`, `code-map:check`. |

Scenariusze są planowane, nie wykonane. Nie ma wymogu benchmarku ani testu na
danych operatora. Wąskie testy używają istniejących fixture'ów i atrap;
nie uruchamiają API/Admin/Reviewera jako usług. Test dotykowy responsywnego
widoku ma sprawdzić dostępność obu przycisków; fizyczny Android pozostaje
odbiorem operatora, jeśli urządzenie nie jest dostępne.

## Koszt, ograniczenia i kontrola jakości planu

Szacunek implementacji wraz z testami i dokumentacją: 1–2 godziny pracy,
bez wiarygodnego przeliczenia na procent pakietu. Koszt bierze się z trzech
hostów, kontraktu API i zgodności zapisów, nie z nowego algorytmu. Uruchomienie
TASK-1113 wymaga wyraźnego zatwierdzenia zakresu i tego szacunku. Istotny
wzrost kosztu lub zakresu wymaga zatrzymania i ponownej zgody według AGENTS.md.

Bez otwartych decyzji blokujących napisanie kodu po akceptacji powyższych
reguł. Nie udowodniono przyczyny wszystkich zawieszeń; pozostałe timeouty
będą osobnym zadaniem, jeśli wystąpią po wdrożeniu. Ta zmiana usuwa koszt
rankingu wielu wzorów i jego automatycznych wznowień, nie daje gwarancji czasu
zwykłego wyszukiwania.

Kontrola planu: każdy wymóg ma wiersz odbioru, ścieżki/symbole sprawdzono
w repozytorium, chroniony jest panel zarządzania, historia i migracje.
Istniejące testy wielu wzorów należy świadomie zastąpić testami usunięcia
kontraktu; przypadki dotyczące zachowanej nawigacji i pojedynczego wzoru
przenieść, nie skasować. Nie ma optymalizacji SQL, przebudowy indeksów,
nowych usług, migracji, pomiarów obciążenia ani automatycznej integracji.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1113 — Usunięcie wyszukiwania wielu układów | `gpt-6.1-sol` | `high` | Dostępny w bieżącym środowisku. Jeden wykonawca utrzyma spójność UI, kontraktu i stanu odtwarzania. Przy nieprzewidzianej zmianie uprawnień lub danych zatrzymać zadanie i zrewidować plan. | Nie jest wymagany osobny audyt; obowiązują testy kontraktu, regresje i przegląd diffu. Sama tabela nie upoważnia do delegacji. |
