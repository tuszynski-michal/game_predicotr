---
title: Przegląd rewizji 5 planu doszkalania siatek V3 przez Claude Code
status: active
last_updated: 2026-10-14
---

# Przegląd rewizji 5 planu „Doszkalanie siatek V3”

Audytor: Claude Code, claude-fable-5-1 / medium.
Przedmiot: rewizja 5 przekazana jako materiał z rozmowy Codex
(`uploads/.../52ddc430-codex-plan-...md`, 466 linii). Plik planu na dysku
(`ai_docs/delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md`) zawiera
nadal rewizję 2 i nie jest przedmiotem tej oceny. Punkt odniesienia kodu
potwierdzony: `D:\game_predicotr` main `efb4cdf5` / `v1.7.359`.
Przegląd statyczny; bez zmian w kodzie, danych i usługach. Wcześniejsze
rundy: `..._20261014.md` (rew. 1, REVISE), `..._round2.md` (rew. 2, REVISE).

**Werdykt: REVISE.** Treść merytoryczna rewizji 5 jest poprawna i zamyka
wszystkie uwagi z rund 1–2 oraz trzy własne P1 Codexa, które potwierdziłem
w kodzie. Blokują dwie sprawy procesowe, nie merytoryczne: plan istnieje
tylko w rozmowie i nie ma zadania, które utrwala go w repozytorium wraz z
worktree i protokołem wznowienia (wymaganie operatora z 2026-10-14), a
opis tasków cofnął się z pełnych sekcji TASK_TEMPLATE do jednowierszowej
tabeli, czego PLAN_STANDARD nie dopuszcza. Po dodaniu zadania startowego i
przywróceniu sekcji tasków plan nadaje się do akceptacji bez kolejnej rundy.

## Fakty sprawdzone w kodzie (rewizja 5)

| Twierdzenie rewizji 5 | Wynik |
| --- | --- |
| `NeuralGridSnapshot` dopuszcza tylko wersje statycznych profili | Potwierdzone: `domain/neural_grid_proposal.py:95-123`, `__post_init__` i `from_payload` wymagają `neural_import_profile` i `version in profile.versions`. TASK-1012 jest konieczny. |
| `grid_issue` jest chronioną decyzją człowieka | Potwierdzone: `storage/image_review_repository.py:1926-1934`, komórki z `quality_issue == "grid_issue"` liczone jako chronione (D-462 R9). TASK-1013 z propozycją do zatwierdzenia jest właściwą ścieżką. |
| `materialize=False` przenosi synchronizację projekcji na wywołującego | Potwierdzone: `storage/image_geometry_completeness_state_repository.py:154-166`. TASK-1008 musi odświeżać projekcje w tej samej transakcji. |
| Numery TASK-0993–1014 wolne | Potwierdzone: najwyższy istniejący plik to 0992. |
| Punkt odniesienia `efb4cdf5` / `v1.7.359` | Potwierdzone na `main` checkoutu D. Worktree `multi-game-share` na gałęzi `v1.1-vision-lab-hybrid-geometry` jest na `c6510f19` (v1.7.357). |
| „Klasyczny komunikat gotowości” | Istnieje: `features/games/game-catalog.tsx:864` („Geometria: …” z `shapeGeometryReadiness`). |

Dane z poprzednich raportów (liczniki 777a2/Mumie, `automatic` 341 564/341 564,
odroczone 373/1 153, checkpoint 106 729 511 B) nie były ponownie mierzone.
Liczba „około 8000 brakujących plansz Mumii” pochodzi z rewizji 5 i nie
została przeze mnie zweryfikowana; plan sam oznacza ją jako niepotwierdzoną.

## Zamknięcie uwag z rund 1–2

Wszystkie P1-1…P1-6 i P2-1…P2-10 mają odzwierciedlenie w rewizji 5:
P1-6 przez sekcję 4 (akceptacja silnika, podgląd i backfill za zgodą,
TASK-1007/1008) i sekcję 3 (rozdzielone liczniki, TASK-1010); P2-6 przez
jawne zdanie „TASK-1000 nie zależy od uzyskania dobrego wspólnego modelu”;
P2-8 przez rozróżnienie korekty i zatwierdzenia bez zmiany z wagą 4:1;
P2-10 przez bramkę grid-only („poprawa geometrii lub komórek przy zachowaniu
wyniku całych zdjęć”). Decyzja operatora o „Złej siatce” (propozycja, nie
automatyczne zamknięcie) jest spójna z D-462 i D-543.

## Uwagi P1

**P1-7 — Brak zadania startowego: worktree, plan na dysku, protokół
wznowienia między modelami.** Rewizja 5 sama stwierdza, że plik planu
zawiera rewizję 2, a obowiązująca treść istnieje tylko w rozmowie. Praca ma
być wykonywana przez Codex i audytowana przez Claude Code w osobnych
sesjach, więc każda sesja musi odnaleźć aktualny plan, stan tasków i
gałąź z repozytorium, nie z historii czatu. Reguły repozytorium wymagają
pracy w dedykowanym worktree (sesje agentów nie piszą w głównym checkoucie
D), a checkout D ma dziś niezacommitowane pliki rewizji 2 i trzy raporty
audytu, które nie należą do żadnego taska.

Korekta: dodać **pierwszy task etapu A, przed TASK-1010**, o zakresie:

1. Utworzyć worktree `worktrees/v3-grid-fine-tuning` na gałęzi
   `feat/v3-grid-fine-tuning` od jawnie wskazanego czubka. Plan musi
   rozstrzygnąć bazę: `main` checkoutu D (`efb4cdf5`, v1.7.359) czy
   `v1.1-vision-lab-hybrid-geometry` (c6510f19, v1.7.357), bo
   `CURRENT_STATE.md` nazywa gałęzią domyślną tę drugą, a API operatora
   działa z `main` D. Zalecam `main` D jako bazę i zapis tej decyzji w
   planie; numeracja `vX.Y.N` od v1.7.360.
2. Przenieść do worktree i zacommitować dokumentację planu: plik planu w
   `ai_docs/delivery/` z pełną rewizją 5 (status `accepted` dopiero po
   zgodzie operatora, do tej chwili `proposed`), raporty audytu i odpowiedź
   Codexa w `ai_docs/quality/`, wpisy w `README.md`, `CURRENT_STATE.md`
   (sekcja planu i „Aktywne taski”), `APP_V3_FUNCTIONAL_INVENTORY.md`,
   warunek w `tasks/0957-*.md`. Główny checkout D zostaje czysty.
3. Utworzyć 22 pliki tasków w `ai_docs/tasks/` według `TASK_TEMPLATE.md`
   (Status, Goal, Context, Dependencies, Recommended execution, Relevant
   docs, Scope, Out of scope, Acceptance criteria, Technical notes,
   Expected files, Test cases, Verification, Risks, Outcome).
4. Zapisać w planie sekcję **„Wznowienie pracy w nowej sesji”**: ścieżka
   worktree i gałąź; kolejność czytania (`AGENTS.md`, `CURRENT_STATE.md`,
   plan, plik aktywnego taska); gdzie jest stan (status taska, `Outcome`,
   hash ostatniego commita w `CURRENT_STATE.md`); jak wykonawca kończy task
   (commit `vX.Y.N`, aktualizacja stanu, prośba o audyt z listą plików),
   jak audytor zapisuje raport (`quality/TASK-NNNN_AUDIT_claude-fable-5-1.md`)
   i jak następna sesja rozpoznaje, że task czeka na poprawki po audycie
   (status `blocked` z odwołaniem do raportu). Sekcja ma działać dla obu
   rodzin modeli bez dostępu do czatu.
5. Zapisać proponowane decyzje jako wpisy `proposed` w `DECISION_LOG.md`
   (rozszerzenie D-480 o ręczne korekty w TRAIN i etykiety
   `approved_unchanged`, rozszerzenie D-527 o wspólną geometrię, akceptacja
   silnika jako doprecyzowanie D-484 i zmiana zakresu D-541, propozycja dla
   „Złej siatki” jako doprecyzowanie D-462/D-543). Numery nadać przy zapisie.
6. Kryterium zakończenia: `npm run docs:check` i `git diff --cached --check`
   zaliczone w worktree; jeden commit; główny checkout D bez zmian planu.
   Task nie zmienia kodu aplikacji.

**P1-8 — Opis tasków cofnął się do tabeli.** Rewizja 2 miała dla każdego
taska sekcje Goal, Dependencies, Recommended execution, Relevant docs,
Scope, Expected files, Acceptance, Verification. Rewizja 5 ma tabelę
„Etap / task | Zakres | Zależności” i tabelę modeli. PLAN_STANDARD wymaga
opisu tasków według TASK_TEMPLATE, wskazania istniejących plików i symboli
oraz kryteriów akceptacji per task; wykonawca nie ma odgadywać zakresu.
Dotyczy to zwłaszcza nowych tasków 1007–1014, które nie miały wcześniej
pełnego opisu.

Korekta: w pliku planu przywrócić sekcje tasków (można skrócić do pól
istotnych, ale z `Expected files` i `Acceptance criteria` dla każdego),
a pliki tasków z P1-7 wypełnić z nich. Przykłady brakujących ustaleń:
TASK-1010 nie nazywa modułu liczników (`image_geometry_completeness_repository.py`,
`grid-reviews counts=correction`), TASK-1011 nie wymienia trzech usuwanych
miejsc (`model-quality-workspace.tsx:878-906`, `game-catalog.tsx:864`,
opcje `grid_profile_*` w `game-catalog-state.ts:92-93`), TASK-1013 nie
wskazuje tabeli propozycji ani istniejącej ścieżki ręcznej korekty
(`application/image_grid_reviews.py`).

## Uwagi P2

**P2-11 — Zależność TASK-0999 od TASK-0997.** Ponowne rozpoznanie
odroczonych slotów i propozycje dla „Złej siatki” czekają przez to na
cały pion treningu i oceny. Uzasadnione, gdy ma działać nowy kandydat.
Plan powinien powiedzieć wprost, czy przebieg z aktualną wersją bazową
(bez treningu) jest dopuszczalny dla odroczonych slotów; jeśli tak,
0999 zależy od 1007 i 1012, a od 0997 tylko dla kandydatów.

**P2-12 — Zasada 11 zaostrza D-480.** D-480 dopuszczała automatyczne
geometrie po filtrze zgodności symboli (poziom B) jako targety treningu.
Rewizja 5 wyklucza akceptację silnika z etykiet. To zaostrzenie jest
rozsądne dla doszkalania z korekt, ale ma być zapisane jako decyzja
(doprecyzowanie D-480), nie tylko jako zasada planu.

**P2-13 — Niepotwierdzone „8000 brakujących plansz Mumii”.** Liczba
pojawia się w sekcji 3 bez źródła. Z poprzednich odczytów: 54 914 rewizji
źródła i 492 215 plansz, czyli przy 9 planszach na zdjęcie brak około
2 000, nie 8 000; część zdjęć może oczekiwać mniej plansz. TASK-1010 ma to
zmierzyć po unikalnych numerach sekwencji, więc liczbę w planie należy
usunąć albo oznaczyć jako hipotezę.

**P2-14 — Baza gałęzi i renumeracja.** Dwie równoległe linie (`main` D na
v1.7.359 i `v1.1-vision-lab-hybrid-geometry` na v1.7.357) grożą kolizją
numerów `vX.Y.N` i D-. Plan ma wskazać jedną bazę (patrz P1-7) i regułę
sprawdzania czubka przed każdym numerem.

**P2-15 — Tabela modeli a dostępność.** Tabela deklaruje
`claude-fable-5-1` z zastrzeżeniem „dostępność trzeba potwierdzić”.
Potwierdzam: ta sesja działa na `claude-fable-5-1` w Claude Code desktop i
może audytować w trybie tylko do odczytu. Zastrzeżenie można zastąpić
odwołaniem do tego raportu.

## Proponowane testy dodatkowe

- Wznowienie: nowa sesja bez historii czatu odnajduje z `CURRENT_STATE.md`
  worktree, gałąź, aktywny task i jego status; próba pracy poza worktree
  jest wykryta przez istniejący hook.
- `docs:check` wykrywa task bez sekcji `Outcome` lub bez wpisu w stanie.
- TASK-1012: snapshot wersji z trzeciej rodziny przechodzi preflight i
  wznowienie; stary snapshot dwóch profili czyta się bez zmian.
- TASK-1008: przerwanie po zmianie statusu, przed odświeżeniem projekcji,
  jest cofane w całości.
- TASK-1013: przyjęcie nieaktualnej propozycji (zmieniona rewizja planszy)
  zwraca konflikt i nie zapisuje geometrii.

Przegląd statyczny, bez zmian w planie i kodzie. Jedyny zapis to ten raport.
