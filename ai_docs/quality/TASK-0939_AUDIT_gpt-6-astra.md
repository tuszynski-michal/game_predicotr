# Audyt TASK-0939 - Narzędzia oszczędzania tokenów z pomiarem

Werdykt: REVISE
Audytor: Codex, etykieta briefu `gpt-6-astra`; reasoning niepotwierdzony
Wykonawca: `claude-sonnet-5-5` / `high` według taska
Zakres: HEAD...f150b06cc35cfb434dacc9935474cfc7bd58a257 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-09
Runda: 1

Przegląd statyczny, bez zmian w plikach.

## Streszczenie

Zbadano generator mapy, hook odczytu, konfigurację Serena, kolektor zużycia, testy i dokumentację pilota. Implementacja zawiera testy podstawowych scenariuszy, ale wymagany pomiar pozostaje niewykonany, a część narzędzi już obowiązuje w instrukcjach repozytorium. Protokół wymaga również poprawienia przygotowania niezależnych worktree przed rozpoczęciem pomiarów.

## Znaleziska

### P0

- [P0-1] `ai_docs/tasks/0939-token-tooling-pilot.md:189` — Brakuje przebiegów i raportu z liczbami oraz decyzjami „zostaje / wypada”, wymaganych przez kryterium akceptacji. Protokół i skrypt zbierający nie zastępują wyników. Należy wykonać pomiar po wymaganej zgodzie na koszt albo uzyskać jawną zmianę zakresu zadania; do tego czasu nie można uznać TASK-0939 za ukończony.

- [P0-2] `AGENTS.md:23` oraz `AGENTS.md:112` — Mapa i reguły oszczędzania kontekstu zostały wprowadzone jako obowiązkowy workflow przed uzyskaniem werdyktu „zostaje”. Warunek pomiaru dotyczy wszystkich wariantów, nie tylko Serena i Graphify. Należy ograniczyć te instrukcje do sesji pilota do czasu pomiaru; stałe włączenie uzależnić od jego wyniku.

### P1

- [P1-1] `ai_docs/quality/TOKEN_TOOLING_PILOT_PROTOCOL.md:60` — Przygotowanie pomiaru wymaga `<PILOT>` zdefiniowanego jako commit **zamykający** TASK-0939, choć zamknięcie wymaga wcześniejszego pomiaru. Powstaje zależność kołowa. Należy wskazać dostępny snapshot przygotowania narzędzi, niezależny od zamknięcia taska, i utrwalić jego identyfikator w raporcie.

- [P1-2] `ai_docs/quality/TOKEN_TOOLING_PILOT_PROTOCOL.md:67` — Wariant Serena nakłada konfigurację i launcher, ale nie przygotowuje `.tooling/venv-tokens` w nowym worktree. Launcher szuka executable względem własnego worktree (`scripts/start_serena_mcp.ps1:17`) i przy jego braku kończy się kodem 2. Protokół opisuje jedynie dowiązanie `.venv`; analogicznie polecenie Graphify odwołuje się do lokalnego `.tooling`. Należy dodać jawne przygotowanie izolowanych narzędzi dla każdego worktree i kontrolę ich dostępności przed sesją.

### P2

- [P2-1] `scripts/generate_code_map.py:589` — Indeks przeznaczony do wyszukiwania przez `rg` korzysta z `format_symbols`, które zachowuje tylko osiem pierwszych symboli. Pozostałe zastępuje liczbą, więc wyszukiwanie ich nazw nie znajdzie modułu, a zmiana nazwy dalszego symbolu może nie zmienić wyniku `--check`. Zalecane pozostawienie limitu w przeglądzie obszarów i zapis wszystkich obsługiwanych symboli w indeksie.

- [P2-2] `ai_docs/guides/TOKEN_TOOLING.md:88` — Instalacja nie przypina wersji, mimo że dokumentacja podaje konkretne wersje pilota. Odtworzenie środowiska może pobrać inne wydania i zmienić zachowanie lub koszt narzędzi między przebiegami. Zalecane przypięcie wersji oraz zapis rzeczywiście zainstalowanych wersji dla każdego środowiska pomiarowego.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Deterministyczna mapa i link w AGENTS.md | spełnione | Generator sortuje ścieżki i zapisuje LF; test stabilności w `services/api/tests/test_token_tooling_scripts.py:29`; link w `AGENTS.md:23`. Ocena statyczna. |
| Hook blokuje duży odczyt bez zakresu i dopuszcza zakres | spełnione | `scripts/hooks/block_large_read.py:47`, `scripts/hooks/block_large_read.py:63`; testy blokowania i zakresu. Ocena statyczna dla plików tekstowych. |
| Raport liczbowy, decyzje i wdrożenie dopiero po „zostaje” | niespełnione | `ai_docs/tasks/0939-token-tooling-pilot.md:189`; P0-1 i P0-2. |
| Instalacje nie dotykają `.venv` projektu ani `package.json` | niezweryfikowane | Instrukcja instaluje do `.tooling` (`ai_docs/guides/TOKEN_TOOLING.md:87`). Diff `package.json` zmienia wyłącznie `docs:check`, bez zależności narzędzi. Historycznego przebiegu instalacji nie potwierdzono niezależnie. |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P0-1, P0-2, P1-1, P1-2, P2-1, P2-2.

## Proponowane testy

- W `services/api/tests/test_token_tooling_scripts.py` dodać przypadek modułu z ponad ośmioma symbolami: dalszy symbol powinien być wyszukiwalny, a zmiana jego nazwy wykrywana przez `--check`.
- Po poprawieniu protokołu sprawdzić przygotowanie Serena i Graphify w świeżym worktree, wyłącznie według zapisanych instrukcji, bez korzystania z nieopisanych katalogów głównego checkoutu.
- Testy skryptów uruchomić poleceniem: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_block_large_read_hook.py services/api/tests/test_token_tooling_scripts.py`.
- Pomiar wykonać zgodnie z poprawionym protokołem po uzyskaniu wymaganej zgody na koszt.

## Zakres przeglądu i ograniczenia

Przeczytano brief, task, fragment etapu T zaakceptowanego planu, zmiany instrukcji repozytorium, skrypty, konfigurację, testy oraz dokumentację instalacji i pomiaru. Brief nie zawierał fragmentu planu; odpowiedni fragment odczytano z pliku wskazanego przez task.

Nie uruchamiano testów, instalacji, serwerów, indeksowania ani sesji pomiarowych. Wyniki testów i testów dymnych zapisane w `Outcome` pozostają deklaracjami wykonawcy. Nie modyfikowano żadnych plików.