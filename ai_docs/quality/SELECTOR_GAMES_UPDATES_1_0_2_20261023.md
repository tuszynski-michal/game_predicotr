# Selektor Windows 1.0.2 — TASK-1088

Zakres zaakceptowany przez operatora: trwały wybór gry i aktualizacja w historii, bez zmiany nazw eksportu. Gałąź `codex/selector-games-updates`.

## Wynik

- Combobox filtruje zapisane gry; Enter zapisuje nową nazwę bez utworzenia projektu. Przycisk listy korzysta ze wspólnego stylu i wysokości 32 px.
- Katalog w profilu jest niezależny od limitu 10 projektów. Pierwsza pisownia nazwy zostaje zachowana; ponowne dodanie jest idempotentne. Uszkodzony katalog daje jawny błąd i nie jest nadpisywany.
- Nowa partia wymaga aktualizacji `a[0-9]+` albo `z_a[0-9]+`. To tekst, więc zera wiodące są zachowane. Walidują ją UI, IPC i odczyt stanu projektu.
- Historia i aktywna partia pokazują aktualizację obok gry. Starsze projekty bez pola nadal działają. Kolejny folder zachowuje grę i aktualizację.
- Nazwy katalogów, `seq_<początek>-<koniec>.jpg` oraz manifest operator-local v2 są niezmienione.

## Weryfikacja

- 27/27 testów `start-resume`, `game-catalog`, `renderer-contracts`: nowy proces, zapis przerwany podczas przygotowania, historyczny projekt bez nowych pól, przejęcie nazw z historii i usunięcie cache, 13 nazw, duplikaty, uszkodzenie katalogu, walidacja aktualizacji i regresje wznowienia.
- Lint i typecheck selektora: PASS.
- Build wydania, świeżość ZIP, SHA-256, rozpakowanie i zawartość app.asar: PASS.
- Smoke `workflow`: PASS. Wspólny styl, kompaktowe rzędy, granica 500000, edycja kierunku, pełny ekran, anulowanie kolejnego folderu i wznowienie w nowym procesie.
- Smoke `games`: PASS. Dodanie Enterem bez submitu, ponowne uruchomienie przed utworzeniem projektu, lista i filtrowanie, walidacja formularza, zapis `z_a003`, dokładna nazwa JPEG, etykieta historii i wznowienie po kolejnym restarcie.
- W teście smoke doprecyzowano oczekiwanie na zamknięcie otwartej listy oraz zakończenie operacji przed odczytem manifestu. Jedna próba przy równoległych testach zakończyła się `ATTRIBUTE_SCAN_FAILED` natywnej kontroli Windows; samodzielne ponowienie przeszło. Zabezpieczeń nie osłabiono.
- Dokumentacja i mapa kodu: kontrola przed zamknięciem.

## Paczka i ograniczenia

Paczka końcowa i jej SHA-256 zostaną przypisane po commicie implementacji. Dowody wizualne: `artifacts/selector-releases/1.0.2/games-update-form.png`, `games-update-history.png`, `selection.png`.

Nie wykonano fizycznego restartu komputera ani testu na drugim komputerze. Trwałość potwierdzono w nowych procesach z izolowanym profilem. Nie uruchamiano usług API/Admin, nie scalano ani nie publikowano w zewnętrznym serwisie. Dotychczasowych gier spoza dostępnych 10 wpisów starej historii nie da się odtworzyć bez ponownego wpisania.

Audyt krzyżowy nie był wymagany przez zaakceptowany zakres; brak delegacji.
