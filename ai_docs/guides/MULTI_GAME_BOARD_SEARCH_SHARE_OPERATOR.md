---
title: Panel udostępniania wielu gier — odbiór i uruchomienie
status: active
last_updated: 2026-10-16
---

# Panel udostępniania wielu gier

TASK-0991 jest scalony do literalnego main: v1.7.364 /
cb87d269128996eecc0ddd1321bf7ccf8f41fcbb. Gałąź panelu i worktree usunięto.
Operator
2026-10-16 jawnie pominął audyt i zatwierdził migrację 0155 oraz usunięcie
gałęzi/worktree. Nie uruchamiano Claude Code ani nie nadawano audytu PASS.

Migracja bazy operatora 0154→0155 wykonana. Zachowano wszystkie 24 sesje
(zweryfikowany hash wierszy), nowy parent jest pusty, FK i indeks poprawne.
Backup pełnego schematu i danych zmienianych tabel, historyczny brief oraz
dowody: `artifacts/branch-integration/multi-game-share-20261016-4e7f3eb0/`.
To nie jest pełny backup danych bazy 124 GiB. Wynik integracji i commity:
`ai_docs/tasks/completed/0991-multi-game-board-search-share.md`.

## Uruchomienie po scaleniu

Buildy Admin i Reviewer w main są już przygotowane i zweryfikowane.
Operator uruchamia API, Admin i worker swoimi dotychczasowymi komendami.
Reviewer na porcie 3001 pozostał uruchomiony podczas przejścia; wymaga
ręcznego zatrzymania i ponownego startu po nowym buildzie. Agent nie
uruchamia, nie zatrzymuje ani nie restartuje tych usług.

```powershell
Set-Location D:\game_predicotr
npm run db:current
```

Oczekiwany head: `0155_board_search_panels`. Nie wykonywać downgrade,
usuwania danych ani automatycznej aktywacji gier. Dostawca i konfiguracja
tunelu pozostają obecne. Pierwszy link używa istniejącego ingressu.

## Korzystanie

W Adminie otwórz „Udostępnianie”, zaznacz gry, wybierz ważność do 72 h
i kliknij „Utwórz link”. Niegotowa gra blokuje cały wybór; przygotuj ją
lub odznacz. Skopiuj cały link z fragmentem `#key=...` i przekaż odbiorcy.
Każdy posiadacz linku może wyszukiwać i poprawiać symbole wybranych gier.

Odbiorca otwiera link bez kodu i wybiera grę. Zmiana gry czyści wzór jak
w obecnym Adminie, ale nie usuwa niepotwierdzonej poprawki. Po utracie
odpowiedzi wróć do właściwej gry i skorzystaj z istniejącego sprawdzenia
ostatniego zapisu. Dziennik operatora wybiera grę, pokazuje wyszukiwania
i dotychczasowy przegląd poprawek.

Po zmianie adresu tunelu pamięć niepotwierdzonych poprawek odbiorcy jest
przypisana do starego adresu przeglądarki. Historia serwerowa pozostaje
w bazie; nowy adres nie przenosi lokalnej pamięci automatycznie.

Lista gier jest stała. Zatrzymanie z potwierdzeniem odwołuje cały link.
Po zmianie adresu tunelu kliknij „Odśwież linki” i skopiuj nowy adres tej
samej sesji; ważność i wybór nie zmieniają się. Sekret jest zachowany tylko
w przeglądarce, która utworzyła link. Inna przeglądarka albo wyczyszczona
pamięć wymagają nowego linku. Utracona odpowiedź tworzenia: odśwież listę,
zatrzymaj wpis bez sekretu, dopiero potem utwórz kolejny.

## Odbiór po uruchomieniu

Sprawdź na telefonie przez zewnętrzną sieć: wybór dwóch gier, paletę i
wyszukiwanie każdej, przybliżoną wygraną/wykres/stawkę/linie, jedną jawną
poprawkę, odświeżenie, dziennik właściwej gry i zatrzymanie linku. Otwórz
link równolegle na drugim urządzeniu: pierwszy odbiorca zachowuje dostęp.
Sprawdź także stary kodowy link pojedynczej gry. To kontrola operatorska;
testy lokalne nie stanowią jej fizycznego zaliczenia.

72 h jest terminem ważności, a dostęp wymaga działającego komputera,
lokalnych usług, internetu i tunelu. Obecny Quick Tunnel nie gwarantuje
stałego adresu ani nieprzerwanej dostępności.
