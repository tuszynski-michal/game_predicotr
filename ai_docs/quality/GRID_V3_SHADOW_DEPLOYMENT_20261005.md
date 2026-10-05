---
title: V3-D — kontrolowana integracja i migracja
status: accepted
last_updated: 2026-10-05
---

# Odbiór wdrożenia TASK-0848

Operator zatwierdził scalenie po zakończeniu przypisywania symboli, następnie
migrację oraz kontakt z równoległym wykonawcą TASK-0847. Wdrożenie wykonano
z `C:\Users\tuszy\Documents\game_predicotr` na
`v1.1-vision-lab-hybrid-geometry`. Przełącznik shadow pozostaje wyłączony.

## Zakres i commity przygotowania

- V3-D: v1.7.191 / `1f43e0137b52e5c3c2beb1afffd2dc96568ff02e`.
- Wspólny head migracji: v1.7.192 / `a5119244c0af32ef2cf3132550ba115f1f5c960d`.
- Równoległa poprawka propozycji symboli RGB: v1.7.192 /
  `8a42380bc9b6d13d125c5eab2873c8c58076134f`.
- Końcowy kandydat: v1.7.193 / `6fb6b8f2ed026d17418e4dfc3d9dcce8cf7c9b90`.
- Główny commit wdrożenia: v1.7.194; pełny hash w Outcome TASK-0848
  i CURRENT_STATE po utworzeniu commita.

Obie gałęzie miały niezależne migracje od 0140. No-op
`0143_merge_share_grid_shadow` łączy `0141_share_symbol_corrections`
i `0142_grid_geometry_shadow_results`. Guard API/workera oczekuje jedynego
head 0143. Zachowano decyzje D-493 i D-494 z main; shadow otrzymał D-495
z jawnym śladem poprzednich identyfikatorów.

## Wyniki kontroli

| Obszar | Faktyczny wynik |
|---|---|
| Pierwszy wspólny kandydat | 43 testy API/guardu/graphu, 74 klienta i 21 Reviewera PASS; lint, typy i scoped strict Mypy PASS. |
| Kandydat z TASK-0847 | 34 testy API/guardu/graphu/propozycji PASS; cały klient 82 PASS; typy Admin/Reviewer/board-search-ui/klienta i Ruff PASS. |
| Kontrakt | OpenAPI i klient ponownie wygenerowane z połączonego backendu; żywe OpenAPI zawiera oba piony. |
| Zależności | `npm install --offline --ignore-scripts --no-audit --no-fund`: aktualne, 7,25 s; bez semantycznej zmiany lockfile. |
| Build Admin | PASS, 21,25 s, z głównego checkoutu. |
| Build Reviewer | PASS, 14,11 s, z głównego checkoutu. |
| Migracja i role | `db:migrate` PASS, 8,05 s; osobny odczyt ról compliant, bez superuser/BYPASSRLS/CREATE ROLE/CREATE DB. |
| API/UI | Health ok; Admin i Reviewer HTTP 200; aktualny build i trwała tożsamość Reviewera potwierdzone w nowym procesie. |
| Odczyt historii przez API | GET grid-shadow-results dla istniejącej gry zwrócił pustą listę przez rolę aplikacji. Nie utworzono joba. |
| Worker | Jedna instancja general, budżet 7 wątków; trwały stan odczytany przez nowy proces. |
| Procesy | Poprzednie drzewa API/UI zakończone; brak drugiej instancji workera. Galerie 8105/8107 zachowały wcześniejsze PID. |

Dowody pojedynczych kroków i odczytowe snapshoty znajdują się w
`C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-v3-deployment-20261004`.
Każdy krok miał osobny timeout; nie powtarzano benchmarków ani testów
PostgreSQL tworzących dodatkowe bazy.

## Stan bazy po migracji

Jedyny revision: `0143_merge_share_grid_shadow`. Dwie wcześniejsze gry
pozostały aktywne. Ich manifest zmienił się z v4 na v5, a rewizje magazynów
odpowiednio 3 → 4 i 1 → 2, zgodnie z migracją. Nie przepisano zdjęć,
produkcyjnej geometrii ani przypisanych symboli.

Nowa tabela historii shadow i dwie partycje są puste. Parent oraz direct
children mają ENABLE i FORCE RLS, politykę `game_scope_v1` z USING/WITH CHECK.
Oba indeksy unikalności pionów są obecne. Odczyt ownera z `row_security=off`
potwierdził rzeczywisty brak historii, a nie jej ukrycie przez RLS.
Brak aktywnych jobów i niedokończonych operacji lifecycle w kontroli po DDL.

## Zdarzenia kontrolne i ograniczenia

- Pierwszy pomocnik konfliktów kandydata miał zbyt szeroki regex. Odtworzono
  pliki z indeksu Git; początkowe 35 testów nie jest dowodem odbioru.
  Końcowe 43 testy wykonywano na pełnych plikach.
- Pierwszy start API przekroczył 10-sekundowy limit pojedynczego sprawdzenia.
  Proces pozostał identyfikowalny w zapisanym stanie. Odczyt logów i health
  potwierdził zakończony startup, bez uruchamiania drugiej kopii.
  Nie ustanawia to gwarancji zimnego startu w 10 sekund.
- Własny pomocnik publikacji istniejącego stanu Reviewera wymagał
  `[NullString]::Value` przy File.Replace w Windows PowerShell 5.1.
  Poprawiono zapis w pomocniku wdrożenia, opublikowano stan działającego
  procesu i potwierdzono jego odczyt w nowym procesie, bez ponownego startu.
- Nieprawidłowy dodatkowy URL odczytu gier zwrócił 404; usunięto ten
  nieistniejący probe. Właściwy odczyt historii i żywy kontrakt przeszły.
- Windows ponownie użył PID jednego zakończonego conhost. Końcowa kontrola
  porównuje również czas utworzenia; nie zakończono obcego procesu.

Nie wykonano treningu, inferencji shadow na danych operatora, aktywacji
domyślnego modelu, importu/materializacji stagingu Mumii, downgrade,
usuwania danych ani push. Kod shadow jest wdrożony, lecz jego odbiór na
danych i decyzja o aktywacji pozostają odrębnym zakresem.

## Kryteria TASK-0848 / Definition of Done

1. Wspólny head i zgodny guard: potwierdzone testami graphu oraz świeżym
   odczytem rzeczywistej bazy; oba piony API są w działającym kontrakcie.
2. Main zawiera V3-D oraz zakończony TASK-0847; wcześniejsze funkcje
   zachowano, a lokalne metadane odtworzono poza własnym commitem.
3. Schemat, manifest, istniejące gry, partycje, RLS i pusta historia:
   potwierdzone odczytem ownera w nowym procesie oraz odczytem API.
4. Usługi po restarcie i trwały stan: health/UI/build identity, stan workera
   oraz brak poprzednich procesów potwierdzone oddzielnym odczytem.
5. Zastane zmiany odzyskiwalne: zachowane stashe i kopie; żadnego cleanupu.
   Galerie labu bez restartu, shadow false.
6. Testy, buildy, dokumentacja, Outcome i CURRENT_STATE uzupełnione;
   task zakończony osobnym commitem integracji. Brak nowej zmiany UI poza
   już odebranym TASK-0805; jego audyt i mobilny smoke pozostają dowodem.

Następny zakres: jawnie zlecony, ograniczony przebieg shadow na
zmaterializowanych źródłach i ocena operatora, z zachowaniem limitu 20.
