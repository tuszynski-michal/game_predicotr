---
title: Przekazanie pracy — silnik siatek V3, bramka kompletności, audyt 777, Mumie (stan 2026-10-04)
status: active
last_updated: 2026-10-04
---

# Przekazanie pracy: silnik siatek V3 (stan 2026-10-04)

Dokument dla kolejnego agenta (Codex). Najpierw przeczytaj `AGENTS.md`,
`ai_docs/README.md`, początek `ai_docs/process/CURRENT_STATE.md` (sekcja
„Hybrydowy silnik siatek V3”) i ten plik. `CURRENT_STATE.md` i
`DECISION_LOG.md` są bardzo duże — przeszukuj je, nie czytaj w całości.

## 1. Gdzie jest kod i co jest wdrożone

| Rzecz | Stan |
|---|---|
| Gałąź robocza | `feat/grid-engine-v3`, worktree `C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3`, HEAD `v1.7.184` (`cab2eee1`) |
| Gałąź integracyjna | `v1.1-vision-lab-hybrid-geometry` (główny checkout `C:\Users\tuszy\Documents\game_predicotr`), ostatnio scalone ode mnie: `v1.7.179` |
| **Niescalone do integracji** | `v1.7.180`–`v1.7.184`: plan Mumii, TASK-0830 (migracja `0140`), TASK-0831, TASK-0840 |
| Baza deweloperska | PostgreSQL w Dockerze `game-predictor-postgres-1`, baza `game_predictor`, head Alembic **`0139`** |
| Inne okno | Drugi agent pracuje równolegle na gałęzi integracyjnej (korekta siatki z symbolami, wyszukiwarka, biblioteka wzorców). Zajął TASK-0825–0829 i D-486–D-488. Przed nadaniem numeru sprawdzaj gałąź integracyjną. |

**Najważniejsze ostrzeżenie:** nie scalaj `feat/grid-engine-v3` do
`v1.1-vision-lab-hybrid-geometry` przed migracją `0140`. API na porcie 8000
działa z głównego checkoutu z `--reload`; kod z `0140` odmawia startu na
bazie `0139` — API by padło w trakcie pracy operatora.

## 2. Procesy uruchomione na komputerze

| Port | Co | Skąd |
|---|---|---|
| 8000 | Admin API (`--reload`) | główny checkout, `.venv\Scripts\python.exe -m game_predictor_api --reload` |
| 3000 | Admin UI (`npm run admin:dev`) | główny checkout |
| 8105 | Wspomagana anotacja siatek labu (Mumie) | worktree, `scripts\vision_lab_assisted_annotation.ps1 -Action Start/Stop/Status` |
| 8107 | Przegląd audytu cichych błędów (zakończony, można zatrzymać) | worktree, `silent_grid_review serve` |
| tunel | Link do Weryfikacji Plansz dla zewnętrznego użytkownika, ważny do 2026-10-04 22:50 (import `f786fed3…`) | API 8000 |

Docker Desktop: po awarii nie uruchamia się, bo blokują go gniazda.
Procedura bez restartu Windows: zabić `Docker Desktop` i
`com.docker.backend`, `wsl --shutdown`, zmienić nazwy **obu** katalogów
`%LOCALAPPDATA%\Docker\run` i `%LOCALAPPDATA%\docker-secrets-engine`
(dopisek `.stale-<data>`), uruchomić
`%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe`, potem
`docker start game-predictor-postgres-1`. Nigdy „Reset to factory defaults”.

## 3. Decyzje operatora (DECISION_LOG) — skrót

- **D-484** — jednostką geometrii jest zdjęcie: żadna plansza zdjęcia nie
  jest cięta na symbole, dopóki wszystkie oczekiwane plansze nie mają
  poprawnej siatki. (Pierwotnie zapisane jako D-479; numer zajęło inne
  okno, przenumerowane.)
- **D-485** — szczegóły bramki: trwały stan `source_images`
  (`geometry_complete | geometry_incomplete | geometry_exception | NULL`),
  dokument wyszukiwarki wstrzymanej planszy zostaje bez dowodu symboli,
  przepinanie plansz na najnowszą rewizję źródła tylko przy identycznej
  geometrii, plansza częściowa wymaga wyjątku operatora.
- **D-480** — zatwierdzona geometria 777 może być danymi uczącymi
  (poziomy G/S/B). **D-481** — budżet treningu: 3 runy × 4 h GPU.
  **D-482** — etap sieci bez etapu symboli. **D-483** — metryka nadrzędna:
  odsetek zdjęć kompletnych i poprawnych (plansza poprawna: NME ≤ 0,02 i
  maks. błąd węzła ≤ 0,05 przekątnej).
- Wersja planu: obowiązuje plan zaakceptowany w tym torze (bramka w
  pipeline produkcyjnym, dane 777 do treningu). Równoległa „korekta” z
  innego okna („777 poza zakresem”, `v1.7.141`) została **zastąpiona**
  decyzją operatora z 2026-10-02.
- **D-489** — symbole dla V3 wybiera i przypisuje operator **od nowa** po
  pocięciu nową siatką; stare etykiety wolno użyć wyłącznie po fakcie do
  listy rozbieżności (bez wpływu na trening i podpowiedzi). (Pierwotnie
  D-486.)
- **D-490** — run 3 przygotowuje nowe gry: zmiana D-456 (Mumie, Blazing,
  Gang mogą być danymi uczącymi; Reels i Treasure pozostają holdoutami);
  potem zakres zawężony do Mumii (Blazing/Gang później), run 3 =
  iteracyjne doszkalanie w łącznym budżecie 4 h; reguły doszkalania: preset
  D → E (strażnik 777: poziom B, image-macro, wykrycie) → F (stan
  przyjmowany tylko przy poprawie holdoutu). Wymagania premium Mumii
  (niżej). Pierwszy zapis anotacji wspomaganej oznaczył stary podział
  pilota D-456 jako `split_stale` — zamierzone.
- Osobna baza PostgreSQL per gra: **odrzucona** przez operatora (partycje
  `LIST (game_id)` + RLS wystarczają; potwierdzone testem TASK-0809).
- Duplikat importu `7d10ae0a`: **nie usuwać** — 51 plansz żyje tylko tam, a
  historia symboli `f4ef3449` wskazuje jego rewizje; narzędzie TASK-0811
  kwalifikuje 0 zdjęć.

## 4. Co zostało zrobione (w kolejności)

| Zadanie | Wersja | Wynik |
|---|---|---|
| TASK-0806/0808 | `v1.7.136`, `v1.7.141` | Raport kompletności geometrii zdjęć w Adminie (sekcja „Kompletność siatek zdjęć”), stany `superseded`, `import_failed`, podgląd zdjęcia po `source_image_id` |
| TASK-0807 | `v1.7.145`, wdrożone `v1.7.148` | Bramka kompletności w pipeline, migracja `0139`, backfill: 777 = 55 499 kompletnych, 60 niekompletnych (plansze częściowe — czekają na wyjątek operatora w Adminie), 1 253 poza bramką; 449 plansz przepiętych |
| TASK-0809 | `v1.7.146` | Test izolacji per gra (nowa gra = 63 partycje, plany zapytań bez cudzych partycji) |
| TASK-0810 | `v1.7.150` | 19 nieaktualnych testów PG naprawionych |
| TASK-0811 | `v1.7.151` | Narzędzie usuwania zastąpionych zdjęć importu (nie uruchomione — niebezpieczne) |
| TASK-0812 | `v1.7.152` | Rozpoznawanie konfliktu unikalności na partycjach gry |
| TASK-0800 | `v1.7.153` | Eksport geometrii produkcyjnej 777 (499 460 plansz; G 459, S 137 473, B 361 103) |
| TASK-0801, 0813 | `v1.7.155`, `v1.7.157` | Snapshot treningowy v2 (`production-geometry-snapshots\286f2e37…`): trening 6 000 zdjęć, development 600, złoty 102 (rodziny złote częściowo wyłączone z treningu) |
| TASK-0823 (dawniej 0814) | `v1.7.159` | Przegląd etykiet 600 plansz przez operatora: S 0,3% złych / 2,0% z nacięciami, B 0% |
| TASK-0802 | `v1.7.158` | Sieć `neural_grid` (2 stopnie, MobileNetV3-Large od zera). Run 1 (preset A) development 92,3%; run 2 (preset B) 92,2% |
| TASK-0803 | `v1.7.168` | Bramka zgodności `hybrid_v3` (progi dla runu 1) |
| TASK-0824, 0825 | `v1.7.170`, `v1.7.172`–`v1.7.177` | Narzędzie wspomaganej anotacji (port 8105) i iteracyjne doszkalanie na Mumiach: 3 iteracje, 20 zdjęć Mumii; propozycje przyjmowane bez zmian 14% → 79%, 165 s → 67 s na zdjęcie; zużyte 2 461 s z 14 400 s budżetu runu 3 |
| poprawka | `v1.7.175` | Magazyn anotacji labu przekroczył 64 MB (pełna kopia podziału w każdym wpisie historii) — naprawione, plik skompaktowany z kopią zapasową |
| TASK-0804 | `v1.7.178` | Raport V3-C `ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md`: na złotym zbiorze silnik produkcyjny 41,4% plansz poprawnych (wszystkie błędy = brak siatki, 79% w skrajnych kolumnach), sieci 96,5–97,2%; Reels 29/30, Treasure 30/30. Rekomendacja: tryb shadow (TASK-0805) w ograniczonym zakresie |
| TASK-0830 | `v1.7.181` (niewdrożone) | Profile w polu „Format strony”: `grid_profile_777_v2` (model runu 1) i `grid_profile_mumie_v1` (model po doszkoleniu); modele w `artifacts\models\grid-engine\…\v1`; migracja `0140` |
| TASK-0831 | `v1.7.182` | Audyt cichych błędów 777: 975 plansz do poprawy (660 werdyktów operatora + 315 z reguły), 237 z nich ma decyzje symboli (490 komórek). Raport `ai_docs/quality/SILENT_GRID_AUDIT_777_20261004.md` |
| TASK-0840 | `v1.7.183` (niewdrożone) | Kolejka „Poprawki z audytu siatek” w Reviewerze z siatką sieci jako propozycją; lista w `artifacts\grid-audit-proposals\…\silent-grid-777-20261004\` |
| Plan Mumii | `v1.7.180` | `ai_docs/delivery/MUMIE_SYMBOLS_PREMIUM_EXECUTION_PLAN.md`, status `proposed`, TASK-0832–0839 zarezerwowane |

## 5. Najbliższe kroki (w tej kolejności)

### Krok 1 — wdrożenie `0140` + TASK-0840 (czeka na sygnał operatora)

Operator przypisuje teraz symbole przez API/Admin; wdrożenie dopiero, gdy
powie, że skończył. Kolejność:

1. Zatrzymać API 8000 (dwa procesy `python -m game_predictor_api --reload`
   plus osierocone dzieci `multiprocessing.spawn` — sprawdzić
   `netstat -ano | findstr :8000`), Admin 3000, Reviewer 3001 jeśli działa,
   ewentualne workery. Strony labu 8105/8107 nie korzystają z bazy.
2. W głównym checkoucie: `git merge --no-ff feat/grid-engine-v3` (uwaga:
   `git merge` bez `-m` otwiera vim — operatorowi to się już zawiesiło;
   podawać `-m`). Wersja commita: kolejny numer `v1.7.N` po najnowszym na
   gałęzi integracyjnej.
3. `npm install`, `npm run reviewer:build`.
4. `npm run db:migrate` → `npm run db:current` = `0140_grid_engine_profiles`.
5. `.venv\Scripts\python.exe scripts/import_grid_audit_proposals.py --dry-run`
   (pokaże plansze zmienione od audytu jako nieaktualne; ponowny import
   nie jest potrzebny) i `scripts/install_grid_engine_models.py --check`.
6. Start API (`npm run api:dev` albo jak wcześniej z `--reload`), Admin,
   Reviewer.
7. Zaktualizować `CURRENT_STATE.md`, przenieść `0830` i `0840` do
   `ai_docs/tasks/completed/`.

Kolejka dla operatora:
`http://127.0.0.1:3001/?mode=local&gameId=bfc4f949-5c14-4850-b02a-db99610bcfa5&queue=grid-audit`
(najpierw 237 plansz z decyzjami symboli; tylko mysz/przyciski — jeśli
operator poprosi, dodać skróty klawiszowe). Pierwsze zapisy obejrzeć
uważnie (nie testowane na żywej bazie).

### Krok 2 — plan symboli Mumii (czeka na 5 decyzji operatora)

`MUMIE_SYMBOLS_PREMIUM_EXECUTION_PLAN.md`: (1) premium jako cecha komórki,
nie osobny symbol; (2) przełącznik „Gra premium” + zakładka „Wypłaty
premium”; (3) **czy symbol premium liczy się też w liniach** — operator
weryfikuje; (4) przypisywanie przez grupowanie wycinków i nazywanie grup;
(5) margines wycinka 8%. Po akceptacji: status `accepted`, wpis D-…,
etapy M-A…M-D.

Wymagania premium (od operatora): każdy symbol gry może być premium;
premium = złota ramka wokół komórki na danej planszy; wygrana premium
zależy od liczby symboli premium na planszy (2, 3, 4, 5 sztuk → różne
wartości) niezależnie od pozycji; obok liczone 5 linii (777 ma 20);
złota rama wokół całej planszy na części klatek to animacja; tabela
wypłat premium podawana przy konfiguracji gry.

### Krok 3 — V3-D tryb shadow (TASK-0805, wymaga jawnego polecenia)

Rekomendacja z raportu V3-C: sieć liczy siatki równolegle do silnika
produkcyjnego (model wskazany przez profil gry z TASK-0830), wynik w
osobnej tabeli gry (migracja, manifest magazynu), bramka `hybrid_v3`
weryfikuje wynik produkcji, propozycje sieci do przeglądu na zdjęciach
oznaczonych przez produkcję; plansza tylko z sieci nigdy automatycznie;
cięcie symboli tylko z zatwierdzonych siatek. Przed integracją: przy
modelu Mumii przekalibrować bramkę (dziś progi tylko dla runu 1).

### Krok 4 — pozostałe (do decyzji operatora)

- Gang i Blazing w narzędziu 8105 (przełącznik gier), pętla doszkalania z
  presetem F; zostało 3 h 19 min budżetu runu 3.
- 60 zdjęć 777 z planszami częściowymi czeka na wyjątek operatora
  (sekcja „Kompletność siatek zdjęć” w Adminie).
- Braki z raportu V3-C: losowa próba zdjęć zaakceptowanych przez produkcję
  (ciche błędy), przegląd 17 plansz przy tolerancji, pełne siatki
  Reels/Treasure, zgodność symboli po cięciu, czas silnika produkcyjnego.
- Znany niezależny błąd testu:
  `test_openapi_contract.py::test_grid_review_openapi_is_topology_aware_and_checksum_bound`
  (`KeyError: 'minItems'`), także na czystym kodzie.
- Kolizja numeru TASK-0825 (dwa tory) — oba zakończone; nie przenumerowano.

## 6. Dane i artefakty

| Co | Gdzie |
|---|---|
| Dane labu | `C:\Users\tuszy\Documents\game_predictor_vision_data\` |
| Runy sieci | `neural-grid-runs\43933ac8…` (run 1, eksport `2cd19738367121e6-round3`), `ff03b1d7…` (run 2, eksport `d623eebfc876c7f3-round9`), `5bc98156…` (run 3 doszkalanie, eksport `iteration03-f896da7196431be2`), ledger `finetune-D\ledger.json` |
| Snapshot 777 | `production-geometry-snapshots\286f2e370aa84437c63fcffe202f01260d6ca13aee317eb8c11cac2ad0f2df59` (v2) |
| Ocena V3-C | `grid-v3-comparison\` (ledger jednorazowych odczytów holdoutów: `sealed\ledger.json`) |
| Audyt 777 | `silent-grid-audit\777-20261004\` (werdykty `review\decisions.json`, reguły `review\rule-verdicts.json`, lista `review\correction-worklist.csv`) |
| Magazyn anotacji labu | `annotations\0cdc0770…\state.json` (kopia przed kompaktacją w `backups\pre-history-compaction-…`) |
| Modele produkcyjne | `C:\Users\tuszy\Documents\game_predicotr\artifacts\models\grid-engine\` |
| Środowisko GPU | `C:\Users\tuszy\Documents\game_predicotr\.venv-vision-lab` (RTX 4050 6 GB; ONNX Runtime tylko CPU) |

## 7. Zasady pracy, które się sprawdziły

- Praca w worktree, nie w głównym checkoucie; ścieżki zawsze absolutne
  (raz wykonawca przez ścieżkę względną zmienił pliki w głównym
  checkoucie).
- Każde zadanie: plik w `ai_docs/tasks/`, osobny commit `v1.7.N - …`,
  `Outcome`, wpis w `CURRENT_STATE.md`, przeniesienie do `completed/`.
- Baza produkcyjna: odczyt tylko w transakcjach `READ ONLY`; zapisy,
  migracje i usuwanie wyłącznie za wyraźną zgodą operatora.
- Testy PG pojedynczo (VM Dockera ma 8 GB); trening GPU nie równolegle z
  ciężkimi operacjami bazy.
- PowerShell 5.1: pliki z polskimi znakami czytać/zapisywać jawnie w UTF-8
  (`[IO.File]::ReadAllText/WriteAllText` z `UTF8Encoding($false)`);
  `Get-Content`/`Set-Content` bez `-Encoding` psują znaki; polskie
  cudzysłowy w here-stringach łamią parser.
- Ścieżki Windows ≤ 260 znaków (krótkie katalogi wyników).
- Operator komunikuje się po polsku, odpowiedzi zwięzłe; dokumentacja po
  polsku, kod po angielsku.
