---
title: Panel udostępniania wyszukiwarki dla wybranych gier
status: completed
last_updated: 2026-10-16
---

# Panel udostępniania wielu gier

## Zgoda i warunki wejściowe

Operator zatwierdził zakres i budżet 3–5 godzin 2026-10-13.
Najnowsza jawna instrukcja 2026-10-16 pomija audyt i zatwierdza migrację
0155 bazy operatora, scalenie do literalnego main oraz usunięcie gałęzi
v1.1-vision-lab-hybrid-geometry i worktree po zabezpieczeniu dowodów.
Nie wolno uruchamiać Claude Code dla tego taska. Migracja i integracja
są rozliczone w completed/0991-multi-game-board-search-share.md.
Main zawiera v1.7.364 / cb87d269128996eecc0ddd1321bf7ccf8f41fcbb;
gałąź i worktree panelu usunięte po zabezpieczeniu dowodów.

Bazowy commit main: v1.7.350, 6fa5577802738f3614fc21e4abc2873990f8536d.
Izolowany worktree: D:/game_predicotr/worktrees/multi-game-share,
pierwotna gałąź v1.1-vision-lab-hybrid-geometry; końcowa robocza
codex/multi-game-share-main bazuje na aktualnym main. Usług nie uruchamia agent.

## Stan obecny i cel

BoardSearchShareAccessService obsługuje sesję jednej gry, kod i rotowany
token. BoardSearchShareSessionModel ma wymagany game_id i unikalny hash
tokenu. BoardSearchShareGate korzysta ze wspólnego BoardSearchWorkspace.
BoardSearchShareCorrectionRepository sprawdza sesję pod blokadą przed
zapisem, zachowuje idempotencję i historię per gra/sesja. Wspólny Quick
Tunnel jest uruchamiany przez ensure_online_reviewer_ingress; nie ma
stałego adresu po ponownym utworzeniu.

Celem jest zakładka „Udostępnianie” w lokalnym Adminie oraz panel odbiorcy
z wyborem gry. Zawartość wyszukiwarki, wypłaty, wykresy, stawki, linie i
poprawianie symboli pozostają wspólnym, istniejącym workflowem.

## Zakres i reguły

- Operator wybiera niepustą listę aktywnych gier według obecnego katalogu
  Admina (niearchiwalnych; obejmuje gotowe drafty). Każda musi przejść obecną
  bramkę gotowości wyszukiwarki i opublikowanych reguł. Niegotowa gra daje
  czytelny błąd; nie jest po cichu pomijana.
- Jawny limit transportu: do 100 różnych gier w jednym panelu, do 100
  metadanych paneli w odczycie listy i do 128 KiB publicznego kontekstu.
- Lista gier linku jest niezmienna. Nazwy prezentacyjne mogą odzwierciedlać
  bieżący katalog. Kolejność gier jest deterministyczna.
- Link ma długi losowy sekret w fragmencie URL, bez ręcznego kodu. Sekret
  jest wymieniany na osobne HttpOnly/Secure/SameSite cookie panelu przez
  same-origin POST. Nie trafia do logów, zapytań URL ani Referer.
- Każdy posiadacz linku ma uprawnienia wyszukiwania i poprawiania symboli.
  UI informuje o rejestrowaniu zapytań i poprawek.
- Ważność 5..4320 minut; wybory UI jak w obecnym udostępnianiu, domyślnie
  8 godzin. Termin nigdy nie jest przedłużany przez otwarcie albo restart.
- Zatrzymanie działa atomowo dla całego panelu. Historia zostaje.
- Limit pięciu aktywnych linków obejmuje dotychczasowe linki i panele;
  panel liczy się raz niezależnie od liczby jego gier.
- Obecny tunel pozostaje współdzielony. Aktywne gry panelu chronią go przed
  automatycznym zatrzymaniem. Przy nowym adresie operator kopiuje nowy URL
  tej samej sesji i zachowanego sekretu, bez zmiany gier i daty wygaśnięcia.
- Surowy sekret jest zwracany tylko przy tworzeniu i przechowywany lokalnie
  w przeglądarce Admina do wygaśnięcia/revoke. Lista API nie zwraca sekretu.
  Bez tej lokalnej kopii operator zatrzymuje link i tworzy nowy. Utrata
  odpowiedzi tworzenia nie jest powodem zgadywania ani odtwarzania sekretu.
- Poprawki po utracie odpowiedzi/reloadzie używają obecnych receiptów;
  pamięć lokalna i cache są oddzielone dla każdej gry i sesji.
- Zmiana gry czyści wzór jak istniejąca zmiana gry w Adminie. Nie usuwa
  niepotwierdzonej poprawki, którą można sprawdzić po powrocie do tej gry.

## TASK-0991 — Architektura i kontrakt

Proponowana addytywna migracja 0155 dodaje tabelę panelu (UUID, label,
hash sekretu, created_at, expires_at, revoked_at) oraz nullable panel_id
w istniejących sesjach. Dziecko panelu pozostaje sesją dokładnie jednej
gry; logi i korekty nadal wskazują dziecko. Unikalność (panel_id, game_id)
i klucze obce RESTRICT chronią członkostwo i historię.

Tworzenie waliduje komplet gier przed ingress i zapisuje panel oraz dzieci
w jednej transakcji control-plane. Gotowość każdej gry sprawdza osobna
sesja bazy, jak board_search_share_readiness w main.py:790; nie wiąże
wielu magazynów gry w jednej transakcji. Limit korzysta ze wspólnej
istniejącej blokady tworzenia linków.

Dependency transportu kończy transakcję w scope function, przed wysłaniem
linku lub cookie. Błąd commit nie daje odbiorcy nieutrwalonego credentialu.
Migracja wskazuje schema public jawnie; nie zależy od historycznego
search_path wcześniejszych rewizji. Nieprzeznaczone do unlock pola kodu
dzieci zawierają losowe markery; dzieci nie mają używalnego kodu.

Poświadczenie dziecka jest HMAC-SHA256 z sekretu panelu i jednoznacznego
komunikatu zawierającego wersję, UUID panelu i UUID dziecka. Hash trafia do
istniejącego token_hash, a termin odpowiada terminowi panelu. Otwarcia
panelu nie rotują tokenów i pozwalają wielu odbiorcom pracować równolegle.
Legacy unlock jawnie odrzuca dzieci panelu przed zapisem prób/rotacją.

Nowa wąska rodzina API odpowiada jedynie za tworzenie/listę/revoke panelu
oraz publiczne open/context. Nie powstaje kopia endpointów wyszukiwania,
wypłat ani korekt. Reviewer ma osobny proxy i cookie. Dla ścieżki panelu
i dziecka proxy wyprowadza poświadczenie i deleguje do istniejącej
allowlisty board-search-shares. Nie przepuszcza unlock dziecka, arbitralnej
gry, reguł, Admin API ani sekretów w odpowiedzi. Cookie zawiera identyfikator
panelu; żądanie starej karty nie używa ani nie usuwa cookie nowego panelu.

Open/context mają timeout 12 s, żądania danych gry 120 s jak ograniczone
operacje istniejącej wyszukiwarki. Limit kontekstu panelu wynosi 128 KiB;
request open 4 KiB, a ścieżki dzieci zachowują obecne limity odpowiedzi.

Revoke blokuje dzieci w deterministycznej kolejności i atomowo unieważnia
parent oraz ich tokeny. Istniejący zapis korekty nadal serializuje się
z revoke na wierszu dziecka. Dane już odczytane/cache pozostają na urządzeniu
odbiorcy; revoke blokuje nowe odczyty i zapisy.

Admin korzysta z wygenerowanego klienta i wrappera. Dziennik panelu pokazuje
grę i wykorzystuje istniejący BoardSearchShareQueryLog per dziecko, wraz
z obecnym przeglądem poprawek i odtworzeniem wyszukiwania.

## TASK-0991 — pełny pion panelu udostępniania

Plik: ai_docs/tasks/completed/0991-multi-game-board-search-share.md. Jeden task obejmuje
spójny pion backend/OpenAPI/klient/Admin/Reviewer, testy, migrację, dokumentację
oraz osobny commit. Audyt jawnie pominięty przez operatora. Szczegóły i kryteria w pliku taska.

## Weryfikacja, ryzyka i wyłączenia

Testy planowane: backend i HTTP dla tworzenia wielu gier, błędnego członkostwa,
sekretu, wygaśnięcia, revoke, limitu i starego kodowego linku; proxy z próbami
wyjścia poza allowlistę i kolizją kart; realne interakcje Admin/Reviewer dla
wyboru gier, przełączenia bez przenoszenia wzoru, poprawek i reloadu; migracja
i trwałość na izolowanej bazie testowej. Przebiegi mają jawne limity czasu.
Następnie scoped format/lint/typecheck, kontrola generowanego klienta,
docs:check, code-map:check i build Admin/Reviewer. Wyniki wykonanych kontroli zapisuje Outcome TASK-0991; sam plan nie
stanowi dowodu ich zaliczenia.

Nie uruchamiać ani nie restartować usług operatora. Nie tworzyć publicznego
linku na jego danych ani wykonywać push. Migracja 0155, main merge i cleanup
są zatwierdzone jawną instrukcją z 2026-10-16. Stały hostname, domena, nowy dostawca tunelu i gwarancja uptime
przez 72 godziny pozostają poza zakresem. Fizyczny telefon i odbiór w sieci
zewnętrznej pozostają osobną kontrolą po migracji i uruchomieniu przez operatora.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0991 | gpt-6.1-sol | high | Jeden pion ze zmianą autoryzacji, migracji i trwałymi korektami; eskalacja przy sprzeczności albo otwartym P0/P1. | Audyt pominięty jawnym poleceniem operatora 2026-10-16; nie uruchamiać Claude Code. Brak fikcyjnego PASS. |
