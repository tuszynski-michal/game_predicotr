---
title: Przegląd planu doszkalania siatek V3 przez Claude Code
status: active
last_updated: 2026-10-14
---

# Przegląd planu „Doszkalanie siatek V3 z korekt w aplikacji”

Audytor: Claude Code, claude-fable-5-1 / medium.
Zakres: `ai_docs/delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md`
(wersja niezacommitowana z 2026-10-14 08:55 w checkoucie `D:\game_predicotr`,
main `v1.7.356`), towarzyszące zmiany `README.md`, `CURRENT_STATE.md`
i `APP_V3_FUNCTIONAL_INVENTORY.md` oraz wskazane w planie pliki kodu.
Przegląd statyczny planu; dodatkowo odczyt bazy operatora tylko do odczytu
(zliczenia, rola aplikacyjna, transakcje cofnięte). Nie zmieniałem kodu,
danych ani usług.

**Werdykt: REVISE.** Plan jest technicznie rzetelny: wskazane pliki i symbole
istnieją, wnioski o stanie kodu są trafne, reguły edytora, danych, treningu
i ponownego rozpoznania są spójne z D-462, D-480, D-483, D-484, D-527,
D-543 i D-544. Brakuje jednak pokrycia jednego wymagania operatora
(ścieżka dla nowych gier) i kilku faktów o danych, które decydują o
wykonalności i kolejności etapów. Pięć uwag P1 to luki planu, nie błędy
w jego treści.

## Potwierdzone twierdzenia planu

- Stary blok „Ulepszanie geometrii / Cięcie siatki” jest dokładnie w
  `apps/admin/src/features/model-quality/model-quality-workspace.tsx:878-906`
  i montuje `GridQualityPanel` klasycznej kalibracji.
- Rejestr `domain/grid_engine_profiles.py` ma dwa zamrożone profile
  (`777 v2`, `Mumie`) ze stałym `current_version`; resolver
  `storage/grid_profile_snapshot_resolver.py::resolve_neural_grid_proposal`
  zawsze przypina `profile.current`. Brak dynamicznego przypisania per gra,
  zgodnie z opisem planu.
- `vision_lab/neural_grid_training.py::compute_losses` wymaga pełnej
  anotacji ekranu (heat/offsets) i węzłów; `train_run` odrzuca preset
  fine-tune (`NEURAL_GRID_FINETUNE_REQUIRES_ITERATION`), więc doszkalanie
  istnieje wyłącznie w ścieżce Mumii `neural_grid_finetune.py`.
- `scripts/vision_lab_geometry_export.py` filtruje
  `geometry_completeness_status = 'geometry_complete'` (linie 69, 86, 214);
  `_exact_lattice` czyta 24 węzły z rewizji z kontrolą checksum renderu.
- Edytor Reviewera ma akcję „Zamień na szkic z czterech narożników”
  (`deferred-board-cell-geometry-editor.tsx:1282`), która zastępuje dokładną
  siatkę szkicem; teza o utracie węzłów jest prawdziwa.
- Ostatnia migracja to `0154_geometry_correction_revert`; numery TASK-0993–1001
  są wolne (najwyższy istniejący plik: 0992); ostatnia decyzja to D-547.
- Sekcje `Recommended execution` każdego taska zgadzają się z końcową tabelą.
- Wymagana przez PLAN_STANDARD mapa wymaganie → task → dowód jest obecna.

## Uwagi P1 (do poprawy przed akceptacją)

**P1-1 — Ścieżka dla nowych gier (Gang, Treasure) nie ma taska.**
Operator wymaga wyboru modelu przy tworzeniu gry innej niż 777/Mumie.
Dziś profil silnika jest wartością zamkniętego enumu
`GameShapeGeometryConfiguration` (`domain/catalog.py:41-44`), używanego w
`schemas/catalog.py:51` i w formularzu `apps/admin/src/features/games/game-catalog.tsx`.
Plan poświęca temu jedno zdanie („Wybór wersji dla nowej gry korzysta z tego
samego rejestru”), ale żaden z tasków 0993–1001 nie zmienia kontraktu
tworzenia gry, enumu ani formularza, a MODEL-10 pozostaje niewdrożone.
Brakuje też operacji „nowa rodzina z wersji bazowej”: gra Gang startuje bez
korekt, więc jej pierwszy model musi pochodzić z istniejącej opublikowanej
wersji (model 777 v2 ma holdouty Reels 29/30 i Treasure 30/30 w rejestrze),
a dopiero korekty tej gry tworzą jej własną rodzinę albo zasilają rodzinę
zgodną. D-527 mówi, że nazwa gry nie ustala zgodności, więc wybór rodziny
jest jawną decyzją operatora przy tworzeniu gry.

Korekta: dodać task (między 0994 i 0998) „Przypisanie modelu siatek przy
tworzeniu gry”: nowe pole przypisania w `game_grid_model_assignments`
zasilane przy `POST /admin/games` z listy opublikowanych wersji; migracja
wypełnia przypisania istniejących gier z enumu; `shape_geometry_configuration`
przestaje wybierać model (zostaje opisem formatu strony); formularz gry
pokazuje katalog wersji z rodziną, metrykami i zgodnością topologii; nowa
rodzina powstaje operacją „utwórz rodzinę z wersji bazowej”. Dopisać MODEL-10
do mapy pokrycia i uzupełnić `requirements/ADMIN_APP.md`.

**P1-2 — Plan nie podaje zmierzonego stanu danych; kohorta 777a2 jest dziś pusta.**
Odczyt bazy operatora 2026-10-14 (tylko do odczytu):

| Gra | Plansze | Zatwierdzone ręcznie | Rewizje > 0 | Zdjęcia `geometry_complete` | Zdjęcia `geometry_incomplete` |
| --- | --- | --- | --- | --- | --- |
| 777a2 | 341 564 | 0 | 0 | 0 | 37 990 (z 37 993) |
| Mumie | 492 215 | 44 (`reviewer-operator`) | 44 | 4 | 54 790 |

Dla 777a2 nie ma dziś ani jednej etykiety treningowej ani jednego zdjęcia
z kompletem plansz. Etap B dla tej gry nie może wystartować bez fazy korekt
operatora, której plan nie wycenia („bez czasu przygotowania danych”), a
która jest faktyczną ścieżką krytyczną. Pierwsza wersja będzie grid-only
(etap węzłów), bo etap ekranu nie ma ani jednej pełnej anotacji; plan mówi
to w regułach danych, ale nie w przebiegu operatora ani w bramkach.

Korekta: (a) wpisać powyższe liczby do sekcji „Stan obecny”; (b) ustalić
minimalną kohortę pierwszego runu (liczba plansz TRAIN, liczba niezależnych
grup VALIDATION i REGRESSION) i pokazywać ją w preview TASK-0995 jako
`GRID_TRAINING_COVERAGE_INSUFFICIENT` z brakującymi liczbami; (c) w
przebiegu operatora dodać krok 0 „Popraw co najmniej N plansz z co najmniej
K nagrań” z jawną informacją, że bez pełnych anotacji zdjęć model nie
nauczy się odzyskiwać niewykrytych plansz; (d) oddzielić szacunek pracy
implementacyjnej od czasu etykietowania.

**P1-3 — „Niepewna siatka” nie jest zdefiniowana, a zakres TASK-0999 jest przez to nieoszacowany.**
W 777a2 37 990 z 37 993 zdjęć ma status `geometry_incomplete`, choć wszystkie
341 564 plansze mają `completeness_status = complete`, a kolejka korekty
(`image_board_geometry_pending`) liczy 373 wiersze. Domena D-484 rozróżnia
stany pozycji `ok / uncertain / partial / missing / deferred`
(`domain/image_geometry_completeness.py`), lecz plan nie mówi, który z nich
jest „pozostałą niepewną siatką”, ani dlaczego prawie wszystkie zdjęcia są
niekompletne przy pustej kolejce. Domyślny zakres planu („wszystkie
automatyczne siatki bez ręcznej geometrii, również kompletne”) oznacza w
praktyce inferencję 38 tys. zdjęć i potencjalny recrop 341 tys. plansz z
ponowną weryfikacją symboli (D-462), równolegle z trwającym TASK-0991.

Korekta: (a) przed zamrożeniem zakresu dodać do TASK-0999 odczyt rozkładu
stanów pozycji dla gry (ile `uncertain`, `missing`, `partial`, `deferred`)
i pokazywać go w preview; (b) domyślny preview ogranicza zakres do pozycji
`uncertain` i `deferred`, a „wszystkie automatyczne” jest jawnym opt-in z
liczbą plansz i komórek, których crop może się zmienić; (c) opisać
współbieżność z jobami symboli (TASK-0991) jako warunek startu, nie tylko
jako wzmiankę w bramkach.

**P1-4 — Checkpoint bazowy 777 v2 istnieje wyłącznie na dysku C, a plan nie ma kroku jego przeniesienia.**
`vision_lab/neural_grid_runs.py:51-58` domyślnie czyta
`VISION_LAB_DATA_ROOT = ~/Documents/game_predictor_vision_data`, czyli
`C:\Users\tuszy\Documents\game_predictor_vision_data`. Checkpoint
`2cd19738….pt` runu `43933ac8…` (zgodny z `checkpoint_sha256` w rejestrze)
leży w `neural-grid-runs/43933ac8…/attempt-1/`; katalog runów ma 3,5 GB,
snapshoty produkcyjne kolejne 3,5 GB. TASK-0957 (sprzątanie C) wymienia ten
katalog jako otwartą decyzję. Plan słusznie przewiduje
`GRID_BASE_CHECKPOINT_UNAVAILABLE`, ale bez kroku kopiowania pierwszy run
na D zakończy się tym błędem, a sprzątanie C może usunąć jedyne źródło.

Korekta: do zakresu TASK-0994 dodać rejestrację checkpointów bazowych:
kopia `.pt` i manifestu eksportu do zarządzanego katalogu modeli na D
(np. `<ARTIFACT_ROOT>/models/grid-engine/<profile>/<version>/checkpoint/`),
weryfikacja `checkpoint_sha256` z rejestru, zapis ścieżki w
`grid_model_versions`. Oznaczyć w TASK-0957, że katalog
`game_predictor_vision_data` nie może być usunięty przed tym krokiem.
Wskazać, że `VISION_LAB_DATA_ROOT` nie jest konfiguracją aplikacji
produkcyjnej; trener produkcyjny czyta tylko ścieżki z rejestru.

**P1-5 — Bramka audytu krzyżowego jest rozwiązywalna w repozytorium; plan zatrzymuje start niepotrzebnie.**
Tabela przypisuje wykonawcę `gpt-6.1-sol` i recenzenta `gpt-6-astra` (ta
sama rodzina) i warunkuje start od „zapewnienia Claude CLI”. Ustalona w
`AGENTS.md:371` i skillu `audit-task` praktyka repozytorium jest odwrotna:
wykonawcą jest sesja Claude Code, a audytorem Codex (`gpt-6-astra` medium,
`high` dla migracji i danych dowodowych; przy braku mocy `gpt-6.1-sol`).
Brak `claude` w PATH jest cechą środowiska Codex, nie projektu.

Korekta: przepisać tabelę na wykonawcę Claude Code (`claude-fable-5-1`,
`high` dla 0994–0999, `medium` dla 0993, 1000, 1001) z audytem Codex według
`AGENTS.md`, albo pozostawić wykonawcę Codex i wskazać audyt Claude z sesji
desktopowej. Usunąć warunek „start kodowania zatrzymany” i zamienić go na
wybór operatora przy akceptacji. PLAN_STANDARD wymaga modeli dostępnych w
bieżącym środowisku; po wyborze tabela ma być jednoznaczna.

## Uwagi P2

**P2-1 — Granulacja tasków i szacunek.** TASK-0995 łączy grupy nagrań, role,
preview kohorty, niezmienny snapshot z kopiami obrazów i builder zbioru;
TASK-0999 łączy preview/freeze/run/resume, recrop, raport i UI podglądu.
To po dwie–trzy spójne zmiany na task. Proponuję podział 0995 na „nagrania i
role” oraz „kohorta i snapshot”, a 0999 na „operacja backendu” i „preview/raport
UI”. Szacunek 3–6 dni roboczych jest optymistyczny dla ośmiu nowych tabel,
dwóch nowych handlerów workera, pionu HTTP z około dwunastu operacji i
nowej sekcji Admina; realistycznie dwa–trzy razy więcej, niezależnie od
etykietowania.

**P2-2 — Dzierżawa GPU to nowa infrastruktura spoza zakresu.** W
`training_core/` nie ma dzierżawy; `symbols/training_job.py` nie wyklucza
równoległego treningu. Zdanie „jedna trwała dzierżawa GPU wyklucza
równoległy trening siatek i symboli” wymaga zmiany handlera symboli, który
plan wyłącza z zakresu. Wybrać: objąć symbolowy handler dzierżawą w 0996
(jawnie w zakresie) albo ograniczyć regułę do treningu siatek i zapisać,
że operator nie uruchamia obu treningów równocześnie.

**P2-3 — Usunięcie klasycznego panelu zostawia historyczną 777 bez widoku
aktywnego profilu.** `GridQualityPanel` pokazuje też status i aktywację
klasycznego `GridCalibrationProfile` gry `7` (V1.1). Plan zachowuje
endpointy, ale usuwa cały UI. Zalecam w stanie archiwalnym sekcji zostawić
wiersz tylko do odczytu „aktywny profil klasyczny: …”, aby operator widział,
czym importowano zakończone dane.

**P2-4 — Decyzje do zapisania przy akceptacji.** Rozszerzenie D-480 (ręczne
korekty G w TRAIN) i zastąpienie budżetu D-481 nowym presetem wymagają
nowych wpisów (najbliższy wolny numer D-548; sprawdzić przy zapisie).
Preset „20 epok / 5000 kroków / 30 min” nie ma uzasadnienia w danych;
raporty iteracji Mumii (`finetune-D/ledger.json`) pokazują, po ilu krokach
wybrano kandydata. TASK-0996 powinien wyprowadzić limit z tych raportów
i zapisać go w presecie.

**P2-5 — Niezweryfikowane odwołanie.** Nie potwierdzałem istnienia
`GAME_SECTIONS` w `catalog-workspace.tsx`; pozostałe ścieżki i symbole z
tabeli „Stan obecny” potwierdzono.

## Ocena kierunku „laboratorium w aplikacji”

Plan przenosi do aplikacji właściwą część laboratorium: dane z korekt,
trening jako job workera, porównanie, rejestr wersji, aktywację i ponowne
rozpoznanie, a lab zostaje konsumentem tych samych funkcji. Narzędzia
anotacyjne labu (porty 8103–8108) nie są potrzebne, bo Reviewer jest już
narzędziem korekty. To jest zgodne z MODEL-05/MODEL-06/MODEL-09 i D-526/D-527.
Brakującym elementem jest wyłącznie ścieżka nowej gry (P1-1); po jej dodaniu
plan pokrywa oba wymagania operatora: poprawę niepewnych siatek 777a2 i
model dla nowych gier.

## Proponowane testy dodatkowe

- Utworzenie gry Gang z wersją bazową rodziny 777: import używa wskazanej
  wersji; korekty Gang nie trafiają do kohorty 777a2 (izolacja rodzin).
- Preview kohorty przy zerze korekt zwraca
  `GRID_TRAINING_COVERAGE_INSUFFICIENT` z liczbami brakujących plansz i grup.
- Preview ponownego rozpoznania pokazuje rozkład stanów pozycji i liczbę
  komórek, których crop może się zmienić; domyślny zakres nie obejmuje
  pozycji `ok`.
- Rejestracja wersji bazowej bez checkpointu na D zwraca
  `GRID_BASE_CHECKPOINT_UNAVAILABLE`; z checkpointem o niezgodnym SHA
  również.

Przegląd statyczny, bez zmian w plikach planu i kodu. Jedyny zapis to ten
raport.
