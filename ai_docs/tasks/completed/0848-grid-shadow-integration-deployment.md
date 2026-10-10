---
title: TASK-0848 — integracja i migracja V3-D na głównym branchu
status: done
last_updated: 2026-10-05
---

# TASK-0848 — integracja i migracja V3-D na głównym branchu

## Status

`done`

## Goal

Połączyć zaakceptowany TASK-0805 z bieżącym głównym branchem, wykonać
zatwierdzoną migrację i przywrócić działające API/Admin/Reviewer.

## Context / zgody

Operator wcześniej zlecił scalenie po zakończeniu przypisywania symboli,
a 2026-10-05 udzielił zgody na migrację. Zgoda obejmuje niezbędne zatrzymanie
i restart usług. Nie obejmuje treningu, aktywacji domyślnego silnika,
przebiegu shadow na danych, usuwania danych, downgrade ani push.
Operator następnie jawnie upoważnił kontakt z czatem wykonującym TASK-0847.
Wysłano prośbę o zakończenie kontroli i commita bez własnego restartu API
ani migracji. Równoległa poprawka ma wejść do wspólnego wdrożenia.

Główny checkout: `C:\Users\tuszy\Documents\game_predicotr`, branch
`v1.1-vision-lab-hybrid-geometry`, HEAD v1.7.191 / 317a07c9.
Worktree przygotowania: `C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3`,
branch `feat/grid-engine-v3`, HEAD v1.7.191 / 1f43e013 przed integracją.
Baza operatora jest na 0140, ma dwie aktywne gry i manifest v4; brak
processing/created jobs oraz niezakończonych operacji lifecycle.
Main ma commitowaną 0141; feature ma 0142, obie od 0140.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`. Samodzielne wykonanie i review integracji
oraz wyników, bez delegowania. Dotychczasowy niezależny audyt TASK-0805
i testy PostgreSQL pozostają dowodem jego implementacji.

## Relevant docs

- AGENTS.md, README.md, CURRENT_STATE.md, PLAN_STANDARD.md, TASK_TEMPLATE.md
- requirements/VISION_LAB.md, architecture/VISION_LAB.md
- architecture/API_CONTRACT.md — oba addytywne piony API
- delivery/GRID_V3_SHADOW_CONTRACT_20261005.md
- process/HANDOFF_GRID_V3_20261004.md — kontrolowana kolejność wdrożenia
- tasks/completed/0805-grid-geometry-shadow-integration.md
- quality/GRID_V3_SHADOW_IMPLEMENTATION_20261005.md
- Główny tasks/completed/0847-grid-audit-rgb-symbol-proposals.md — wyłącznie
  ochrona równoległych niezacommitowanych zmian, nie wykonanie tego taska.

## Scope / plan wykonania

1. Zachować zastane zmiany jako odzyskiwalne patche/stash, bez ich commita.
   Połączyć commitowany main w worktree. Zachować oba piony API i dokumenty.
   Kolizje decyzji rozwiązać: zachować D-493/D-494 z main, shadow oznaczyć D-495
   z jawnym śladem poprzedniego numeru; treści decyzji nie zmieniać.
2. Dodać proponowaną no-op migrację `0143_merge_share_grid_shadow`, parents
   0141_share_symbol_corrections i 0142_grid_geometry_shadow_results.
   Guard API/workera i test muszą wskazywać jedyny head 0143.
3. Sprawdzić graph migracji, composition/API/regresje shadow i korekt share,
   wygenerować łączny kontrakt; lint/typy. Oba buildy wykonać z main w kroku 5.
   Nie powtarzać
   benchmarków, treningów ani testów PostgreSQL na nowych bazach.
4. Zapisać osobny commit kandydata v1.7.192 (zapisany). Po zakończeniu
   TASK-0847 włączyć jego commit do worktree i sprawdzić wspólny kontrakt.
   Każdy kolejny commit zwiększa patch według rzeczywistej historii brancha.
   Przed zmianą main ponownie
   sprawdzić stan repo/jobów; zachować tylko kolidujące lokalne patche.
   Zatrzymać konkretne procesy API/Admin/Reviewera i worker general;
   pozostawić lab 8105/8107. Nie zmieniać plików main przy działającym reload.
5. Scalić feat do main bez automatycznego commita, zachowując zatwierdzony
   commit TASK-0847 i zastane lokalne zmiany metadanych poza własnym commitem.
   Zainstalować istniejące zależności i zbudować oba UI z main. Wykonać
   `db:migrate` do 0143 oraz check ról. Migracje 0141/0142 są transakcyjne,
   z lock_timeout 5 s i statement_timeout 120 s. 0143 nie zawiera DDL/DML.
6. Restart z głównego checkoutu, readiness każdego procesu do 10 s,
   kontrola schematu/manifestu/partycji/RLS, kontraktu i stron HTTP.
   Przełącznik shadow pozostaje false. Odtworzyć uruchomiony worker z jego
   dotychczasowym budżetem 7 wątków. Brak niezamówionej inferencji.
7. Uzupełnić Outcome/CURRENT_STATE i raport, przenieść task do completed,
   osobny commit scalający z kolejnym patchem względem ostatniego kandydata.
   Przywrócić i zachować zastane zmiany; żadnego push.

## Acceptance criteria

- [x] Jedyny head 0143 i zgodny guard; oba piony API i client działają.
- [x] Main zawiera V3-D i pozostałe wcześniej commitowane funkcje.
- [x] Baza na 0143, dwie dotychczasowe gry aktywne, manifest v5, nowe
      partycje zabezpieczone parent/direct child RLS; shadow historia pusta.
- [x] API 8000, Admin 3000, Reviewer 3001 i wcześniej uruchomiony worker
      gotowe z main. Brak podwójnych procesów i osieroconych dzieci wdrożenia.
- [x] Zastane metadane zachowane poza własnym commitem; zakończony TASK-0847
      zachowany w historii, lab nieprzerwany.
- [x] Weryfikacja, commity, Outcome, CURRENT_STATE i raport kompletne.

## Expected files

Nowe: migracja 0143 i test jej graphu, raport wdrożenia, ten task.
Istniejące: schema_readiness.py i test, oba konflikty dokumentacji,
OpenAPI/generowany klient po wspólnym eksporcie, referencje D-493 shadow.

## Verification / granice

Każdy krok ma osobny limit do 120 s i wynik w
`C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-v3-deployment-20261004`.
Read-only preflight zapisuje wersję i stan magazynów; kontrola po migracji
wykonana w nowym procesie. Wszelkie błędy lock/readiness zatrzymują dalszy
krok; najpierw sprawdzić stan i logi, bez automatycznego downgrade/resetu.
Zmiany danych są ograniczone do zatwierdzonych migracji i grantów ról.
Migracje nie przepisują zdjęć, geometrii ani przypisanych symboli.
Nie twierdzić, że przygotowanie pełnej ścieżki ONNX oznacza jej operacyjny
odbiór: shadow nadal wyłączony i bez wyników na danych operatora.

## Outcome

Read-only preflight: 0140, dwie aktywne gry v4, brak aktywnych jobów/lifecycle.
Pierwsza próba preflight użyła nieistniejącego statusu queued; odczyt został
wycofany bez zmian danych, poprawiony według enum domeny i ponowiony PASS.
Zastane feature metadata zachowano w stash b2501a4e3428c75cd990fcb637eb3a0d110b5ae8.
Scalanie kandydata: konflikty tylko w CURRENT_STATE, Decision Log,
guardzie schematu i jego teście. Początkowy pomocnik konfliktów miał zbyt
szeroki regex, co ucięło wspólne końcówki plików. Lint wykrył błąd;
odtworzono pełne pliki z indeksu Git i ograniczono marker do jednej linii.
Nie zmieniono main ani danych. Początkowe 35 testów nie jest dowodem odbioru;
po odtworzeniu pełnych plików 43 testy API/guardu/migracji PASS (64,55 s).
Klient 74 PASS, regresje Reviewera 21 PASS, typy czterech workspace PASS,
strict Mypy main/router/guard z typowanymi zależnościami PASS, Ruff/format PASS.
Wspólny OpenAPI i klient wygenerowane z połączonego backendu.
Przygotowanie migracji 0143 i guardu zakończone; baza nadal na 0140.

Kandydat integracji: `v1.7.192` / `a5119244c0af32ef2cf3132550ba115f1f5c960d`.
Przed wdrożeniem ponowny status main wykrył aktywne zmiany TASK-0847 w API,
OpenAPI i podpowiedziach symboli. Nie staszowano ani nie scalano tych
niezacommitowanych zmian i nie zatrzymano usług. Operator upoważnił kontakt
z drugim czatem; koordynacja wykonana; TASK-0847 zakończony jako `v1.7.192` /
`8a42380bc9b6d13d125c5eab2873c8c58076134f`, włączony do worktree.
Nowa D-494 main dotyczy RGB; ostateczny identyfikator shadow to D-495.
Zapisano odczytowy snapshot identyfikatorów i rewizji magazynów obu gier
(`task0848-before-catalog.json`) oraz przygotowano kontrolę po migracji
obejmującą manifest, pustą historię shadow, partycje, RLS i indeksy obu pionów.
Snapshot potwierdza nadal 0140, brak aktywnych jobów/lifecycle i shadow false.
Baza i procesy operatora pozostają bez zmian; wdrożenie nie jest zakończone.
Drugi snapshot lokalnych metadanych feature: stash
`6c3cc4aaef184787ba40ea3039ff131cb82d8049`, zachowany do odtworzenia.
Po włączeniu zakończonego TASK-0847: 34 testy API/graph/guard/propozycji
PASS, 82 testy całego klienta PASS, typy czterech workspace PASS,
Ruff połączonych modułów PASS. OpenAPI i klient ponownie wygenerowane.
Dwa konflikty dokumentacji rozwiązano, zachowując D-493, D-494 i D-495.
Przygotowano podgląd konkretnych drzew procesów; żadnej usługi nie zatrzymano.
Końcowy kandydat: `v1.7.193` / `6fb6b8f2ed026d17418e4dfc3d9dcce8cf7c9b90`.


### Wdrożenie i odbiór

Główny checkout scalono przy zatrzymanych API/Admin/Reviewer i workerze,
bez konfliktów. Zastane metadane main zapisano w stash
`ee7797a689f3f371d11acde25251afc6c8641dfb` oraz w kopii z SHA plików.
Odtworzenie odbywa się po staged własnych dokumentów, poza indeksem.
Zależności aktualne; brak semantycznej zmiany package-lock. Build Admin
21,25 s PASS, Reviewer 14,11 s PASS. `db:migrate` 8,05 s PASS do jedynego
head `0143_merge_share_grid_shadow`, role osobno compliant PASS.

Nowy proces ownera potwierdził dwie wcześniejsze aktywne gry, manifest v5,
rewizje magazynów 3→4 i 1→2. Historia shadow ma rzeczywiście zero wierszy;
parent i dwa children mają ENABLE/FORCE RLS oraz USING/WITH CHECK.
Indeksy unikalności obu pionów obecne; aktywnych jobów/lifecycle zero.
Odczyt historii przez API zwraca pustą listę, żywy OpenAPI ma oba piony.
Admin i Reviewer HTTP 200; aktualny build i trwała tożsamość Reviewera PASS.
Worker general wznowiony z 7 wątkami, stan sprawdzony w nowym procesie.
Galerie 8105/8107 zachowały swoje PID; brak poprzednich procesów lub
drugiej instancji workera. Shadow pozostaje false, bez jego jobów/inferencji.

Pierwszy 10-sekundowy probe startupu API wygasł; późniejszy odczyt logów
i health potwierdził gotowość tego samego zapisanego procesu, bez drugiej
kopii. Nie obiecujemy zimnego startu w 10 s. Własny pomocnik publikacji
stanu Reviewera poprawiono dla File.Replace/[NullString] w PowerShell 5.1;
stan odtworzono bez restartu, a jego odczyt w nowym procesie PASS.
Usunięto nieistniejący probe GET /games (404). Końcowa kontrola PID bierze
pod uwagę czas utworzenia, bo Windows ponownie użył PID conhost.
Szczegóły: `ai_docs/quality/GRID_V3_SHADOW_DEPLOYMENT_20261005.md`.

Kryteria taska, siedem kroków planu i właściwe punkty DoD porównane z
wynikami w raporcie. Bez treningu, aktywacji modelu, importu stagingu,
downgrade, cleanupu danych i push. Następny zakres wymaga jawnego zlecenia
przebiegu shadow na zmaterializowanych zdjęciach; limit 20 pozostaje.
Główny commit wdrożenia: `v1.7.194` /
`73ae0b6fe82d397fefed24a3f1656ba805c50d6c` (hash dopisany po commicie).
Zachowany worktree `grid-engine-v3` / `feat/grid-engine-v3` wyrównano
fast-forward do tego samego commita. Wpisy po commicie kandydata zachowano
w stash `89c13dcea4b3465c650c767c34b5e3173180d0a8`; zastane metadane
feature odtworzono z pierwotnego b2501a4 bez stagingu. Oba indeksy puste.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0848 | gpt-6.1-sol | high | Integracja dwóch pionów i kontrolowana operacja schematu wymagają przeglądu graphu migracji, ochrony zastanych zmian oraz kontroli gotowości. | Samodzielny review połączonego kontraktu i wyników; bez delegowania. |
