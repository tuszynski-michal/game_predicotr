---
title: Naprawa widoczności folderów importu i ustawień V3
status: accepted
last_updated: 2026-10-07
---

# Naprawa folderów importu — TASK-0889

## Stan obecny i cel

Zgłoszenie użytkownika upoważnia do naprawy niewidocznego uploadu i usunięcia
nieużywanego ustawienia V3 z formularza. GET browser-selections zwraca
GAME_NOT_FOUND dla starego stagingu gry 2a46d3a6-bc56-4a13-8f98-dd51c88df0b2.
Nowy staging b770bcc8-0002-4de0-ad01-60efa82d4835 istnieje: „1 - 23175 cut”,
2575 zdjęć, przypisany do aktualnej gry Mumie. Frontend ignoruje błąd listy.
Celem jest dostęp do tego folderu po odświeżeniu i po restarcie API.

## Reguły i rozwiązanie

- Nie usuwać ani przepinać stagingu usuniętej gry. Odczyt opcjonalnego statusu
  retencji zwraca null wyłącznie dla GAME_NOT_FOUND. Inne błędy magazynu
  propagują się. Filtr kontekstu gry pozostaje bez zmian.
- Błąd pobrania listy ma widoczny komunikat i możliwość odświeżenia. Zachować
  ostatnią poprawną listę. Pokazać stan ładowania i pustej listy.
- Po finalizacji uploadu pobrać listę przed przygotowaniem raportu, aby błąd
  raportu nie ukrywał poprawnie przesłanego folderu.
- Ukryć „Dopasowanie geometrii zdjęcia” dla profilu grid_profile_mumie_v1.
  V3 używa własnych propozycji neuronowych; klasyczny wybór nadal działa dla
  V1.1. Nie zmieniać żądań API ani historycznych raportów.
- Odbiór rzeczywistego raportu ujawnił również starą metrykę dopasowania oraz
  klasyczną etykietę przed pierwszym jobem. Ten sam zakres usuwa nieużywaną
  metrykę z raportu V3 i pokazuje konfigurację neuronową z profilu gry, tylko
  gdy brak przypiętej historii. Historyczne klasyczne etykiety pozostają.
- Brak zmian schematu, zapisu danych domenowych, nowego importu, treningu,
  aktywacji modeli lub cleanupu. Restart istniejącego API po testach mieści
  się w wcześniejszej zgodzie na pracę w głównej aplikacji.

## Wykonanie i odbiór

TASK-0889 obejmuje repozytorium retencji, panel importu, testy regresji,
dokumentację oraz weryfikację rzeczywistej listy w głównej aplikacji.
Najpierw test odtwarzający odczyt dwóch stagingów (usunięta i istniejąca gra),
restart usługi i zachowanie innych błędów. Następnie interakcje panelu:
błąd listy, odświeżenie, błąd raportu po uploadzie, ponowne zamontowanie,
ukryty select V3 i zachowany wybór V1.1. Scoped lint/format/typecheck i build
Admin. Odbiór: rzeczywisty folder widoczny po restarcie API oraz reloadzie
strony, z przyciskiem raportu; żadna nowa analiza/import nie uruchomiona.
Komendy i wyniki zapisuje TASK-0889. Jeśli diagnoza wymaga zmiany kontraktu
lub danych, przerwać zależny fragment i zaktualizować zakres.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0889 | gpt-6.1-sol | high | Ograniczona naprawa odczytu i UX; konieczna ochrona innych gier oraz trwałości stagingu. | Własny przegląd diffu i testy regresji; bez delegowania. |
