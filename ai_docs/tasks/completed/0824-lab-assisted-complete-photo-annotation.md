---
title: TASK-0824 — wspomagana anotacja kompletnych zdjęć laboratorium (Mumie, Blazing, Gang)
status: done
last_updated: 2026-10-02
---

# TASK-0824 — wspomagana anotacja kompletnych zdjęć laboratorium

## Status

`done` (commit, przeniesienie do `completed/` i `CURRENT_STATE.md` należą do koordynatora)

## Goal

Operator przegląda zdjęcia gier Mumie, Blazing i Gang z propozycjami siatek
sieci `neural_grid` (run 1), poprawia je i akceptuje zdjęcie dopiero z
kompletem siatek wszystkich plansz; wynik jest trwałym zbiorem kompletnych
zdjęć gotowym do snapshotu treningowego runu 3.

## Context

D-490. Sieć uczy się na całym ekranie, więc zdjęcie z częścią siatek uczy
ją, że pozostałe plansze nie istnieją. W labie ręcznie zatwierdzone są 63
zdjęcia i 180 siatek (średnio 3 na zdjęcie). Folder źródłowy
`C:\Users\tuszy\Documents\game_predictor_traning_set`: mumie 225 plików,
blazing 27, gang 35 (także 777: 32, reels: 54, treasure: 100 — Reels i
Treasure są holdoutami i **nie** wchodzą do tego zadania).

## Dependencies / entry conditions

- Eksport ONNX runu 1:
  `neural-grid-runs\43933ac8…e2e6\exports\2cd19738367121e6-round3` (CPU).
- Laboratorium ma katalog zdjęć, magazyn anotacji i edytor siatek z
  przeglądem i akceptacją zdjęcia (`annotations.py`, `photo_review.py`,
  API `127.0.0.1:8102`, UI `apps/vision-lab` `127.0.0.1:3102`, T03d).
- Run 2 treningu może trwać na GPU — to zadanie używa wyłącznie CPU.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Rozszerzenie magazynu anotacji labu z
blokadami i historią o stan kompletności zdjęcia oraz propozycje z sieci;
błąd oznacza utratę pracy operatora albo fałszywe etykiety. Audyt zawieszony
decyzją operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/DECISION_LOG.md` (D-490, D-484, D-450, D-453, D-456, D-447)
- `ai_docs/architecture/VISION_LAB.md`, `ai_docs/requirements/VISION_LAB.md`
- `ai_docs/guides/VISION_LAB_LOCAL.md`
- `ai_docs/tasks/0668-vision-lab-geometry-annotations.md` (T03: magazyn
  anotacji, edytor, akceptacja — czytaj selektywnie, plik jest duży)

## Scope

- Propozycje: uruchomienie `neural_grid` (ONNX CPU) na zdjęciach trzech gier
  i zapis propozycji jako osobnego, niezmiennego artefaktu (nie jako
  anotacji).
- Przepływ operatora: zdjęcie z naniesionymi propozycjami; akceptacja
  planszy bez zmian, korekta narożników/węzłów, dodanie brakującej planszy,
  usunięcie fałszywej; potwierdzenie liczby plansz zdjęcia; stan zdjęcia
  „kompletne” dopiero gdy każda oczekiwana plansza ma zaakceptowaną siatkę.
- Trwały zapis w istniejącym magazynie anotacji (blokada, CAS, historia) —
  bez równoległego magazynu.
- Kolejka: Mumie pierwsze, potem Blazing i Gang; licznik postępu i pomiar
  czasu na zdjęcie.
- Eksport listy kompletnych zdjęć (zdjęcie → plansze → 24 węzły, gra,
  rodzina źródła, SHA) w formacie zgodnym z czytnikiem snapshotu
  produkcyjnego albo z adapterem do niego.
- Testy, wpis w przewodniku.

## Out of scope

- Trening, preset D, pobieranie wag, snapshot treningowy runu 3 (następne
  zadanie), symbole, Reels i Treasure, aplikacja produkcyjna i baza.

## Acceptance criteria

- [x] Propozycja sieci nigdy nie staje się etykietą bez akcji operatora;
      etykieta zapisuje pochodzenie (propozycja zaakceptowana bez zmian /
      poprawiona / narysowana ręcznie).
- [x] Zdjęcie „kompletne” wymaga potwierdzonej liczby plansz i
      zaakceptowanej siatki każdej z nich; cofnięcie akceptacji planszy
      cofa kompletność.
- [x] Istniejące anotacje i akceptacje labu (63 zdjęcia, 180 siatek) są
      zachowane i widoczne jako już zaakceptowane plansze; nic nie jest
      nadpisywane ani usuwane; zamrożony pilot D-456 i jego manifesty
      nietknięte.
- [x] Praca operatora przeżywa restart serwera i przeglądarki.
- [x] Reels i Treasure są niedostępne w tym przepływie (strażnik + test).
- [x] Eksport kompletnych zdjęć z sumami kontrolnymi; test zgodności z
      czytnikiem danych `neural_grid`.
- [x] Operator może zacząć pracę jedną komendą startu i jednym adresem;
      instrukcja z klawiszami w przewodniku.
- [x] Laboratorium nadal nie importuje `storage` ani `psycopg`.
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

Najpierw ustal, czego brakuje istniejącemu edytorowi T03d do tego
przepływu, i rozszerz go minimalnie; nie buduj drugiego edytora, jeżeli
istniejący pozwala poprawiać siatkę 5 × 3 i akceptować zdjęcie. Jeżeli UI
`apps/vision-lab` nie da się uruchomić z worktree (brak zależności) albo
jego rozszerzenie jest nieproporcjonalnie duże, dopuszczalne jest małe
narzędzie serwowane przez API labu (wzorzec `label_review.py`), ale zapis
nadal idzie do istniejącego magazynu anotacji przez jego publiczne funkcje.

Edycja siatki: minimum to przeciąganie czterech narożników planszy (siatka
5 × 3 wyliczana projekcyjnie) z podglądem linii; precyzyjna korekta
pojedynczych węzłów nie jest wymagana. Powiększenie planszy podczas edycji.
Klawiatura: akceptuj planszę, następna/poprzednia plansza, akceptuj zdjęcie,
następne zdjęcie, cofnij.

Zdjęcia, których źródło jest powiązane z istniejącymi rodzinami i podziałem
labu: zachowaj identyfikatory i rodziny z katalogu labu; nie zgaduj rodzin
z nazw plików ponad to, co robi katalog.

Uruchom generowanie propozycji dla trzech gier (CPU, ok. 0,2–0,3 s na
zdjęcie) i sprawdź przepływ end to end na 2 zdjęciach testowych w kopii
magazynu albo z natychmiastowym wycofaniem zmian — operator ma zacząć od
czystego stanu.

## Expected files

- Istniejące: `vision_lab/annotations.py`, `annotation_contracts.py`,
  `photo_review.py`, `api.py`, ewentualnie `apps/vision-lab`.
- Nowe (proponowane): `vision_lab/assisted_annotation.py`, testy,
  wpis w `ai_docs/guides/VISION_LAB_LOCAL.md`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests -q -p no:cacheprovider -k "assisted_annotation or annotation or photo_review or no_production_storage_imports"
.\.venv\Scripts\python.exe -m ruff check services scripts
```

## Risks / open questions

- Sieć uczona na 777 może słabo trafiać w plansze innych gier; wtedy
  operator rysuje więcej ręcznie — pomiar czasu na pierwszych 10 zdjęciach
  rozstrzyga o realnej liczbie zdjęć.

## Outcome

Wykonano 2026-10-02 (implementer, bez commita).

Projekt: osobne małe narzędzie serwowane przez Pythona (wzorzec `label_review.py`,
port 8105) zamiast rozbudowy edytora T03d — edytor T03d edytuje jedną pozycję naraz,
nie zna propozycji sieci, kompletności zdjęcia ani kolejki z pomiarem czasu, a jego UI
wymaga osobnego buildu Next i drugiego procesu. Zapis idzie wyłącznie przez
`AnnotationStore.mutate` (blokada, CAS, potwierdzenia, historia) do istniejącego
magazynu.

### Changed

- `annotation_contracts.py`: `AssistedBoard`, `AssistedPhoto`, `AssistedRequest`;
  `AnnotationState.assisted_photos` (domyślnie puste — magazyny sprzed zadania czytają
  się bez zmian; wzorzec jak `geometry_qualifications`). `GeometryAnnotation` bez zmian,
  więc odciski siatek w zamrożonym podziale się nie zmieniają.
- `annotations.py`: `mutate` przyjmuje `AssistedRequest`; wpis historii zawiera
  `assisted_photo`, zapisaną adnotację i ewentualny `photo_review`.
- Nowy `assisted_annotation.py`: strażnik gier (Mumie/Blazing/Gang; Reels, Treasure i
  777 odrzucone), reguły zapisu (akceptacja planszy z pochodzeniem
  `proposal_unchanged`/`proposal_corrected`/`manual`, cofnięcie akceptacji, usunięcie,
  odrzucenie/przywrócenie propozycji, zatwierdzenie zdjęcia z liczbą plansz i
  akceptacją T03d), kolejka, generator propozycji ONNX CPU (artefakt create-only z sumą
  kontrolną), widoki, eksport create-only z manifestem i adapter
  `write_reader_snapshot` do formatu `production-geometry-snapshot-v1`, strona FastAPI
  i CLI (`proposals`, `serve`, `status`, `export`).
- Nowy `assisted_annotation_page.py` (UI po polsku, klawiatura, przeciąganie narożników
  z siatką projekcyjną, powiększenie planszy, licznik postępu i czasu).
- `rebase_annotations.py`: odmowa `REBASE_ASSISTED_PHOTOS_UNSUPPORTED`.
- Nowy `scripts/vision_lab_assisted_annotation.ps1` (`Start`/`Stop`/`Status`/`Export`).
- OpenAPI labu i wygenerowany klient `packages/vision-lab-api-client` (nowe pole stanu).
- Testy: `services/worker/tests/test_vision_lab_assisted_annotation.py` (7 testów).

### Verification results

- `pytest services/worker/tests -k "assisted_annotation or annotation or photo_review or no_production_storage_imports"`:
  38 passed; z `rebase`: 48 passed; wszystkie testy `-k vision_lab`: 311 passed.
- `ruff check services scripts`: jedyny błąd to istniejący wcześniej E501 w
  niezmienionym `test_page_geometry_preflight.py:345`; zmienione pliki czyste.
  `mypy --strict` dla zmienionych modułów: bez błędów w tych plikach.
- `npm run vision-lab:openapi:check`: OK; testy klienta labu: 14 passed;
  `scripts/check_powershell_syntax.ps1`: OK.
- Propozycje (CPU, 4 wątki, 89 s): zbiór
  `9f8f98b879dc7d8a462c45419b42417c4b169093429f1bb4b8baca29ffbcf326` w
  `<LAB>\assisted-annotation\proposals`; 319 zdjęć: Mumie 236 (225 z folderu + 11
  wcześniej anotowanych), Blazing 37 (27 + 10), Gang 46 (35 + 11). Mumie i Blazing:
  9 propozycji na każdym zdjęciu; Gang: 9 na 32, 8 na 9, 7 na 4, 6 na 1. Brak zdjęć z
  0 plansz. Wizualnie Mumie i Blazing trafiają dobrze; Gang słabiej (342 plansze z
  `NEURAL_GRID_FIT_OUTLIERS`, część siatek za szeroka).
- E2E na kopii magazynu (strona 8105 przez skrypt, przeglądarka): zdjęcie 1 Mumie —
  7 propozycji bez zmian, 1 poprawiona przeciągnięciem, 1 odrzucona i narysowana
  ręcznie, liczba 8 odrzucona (`ASSISTED_BOARD_COUNT_MISMATCH`), 9 zatwierdzone;
  restart serwera i przeładowanie strony zachowały stan. Zdjęcie 226 (wcześniejsza
  praca labu, 3 zablokowane plansze): próba usunięcia zablokowanej odrzucona, 6
  propozycji przyjętych, cofnięcie akceptacji zablokowało zatwierdzenie, ponowna
  akceptacja i zatwierdzenie 9. Czas aktywny 1:39 i 1:26. Eksport z kopii: 2 zdjęcia,
  18 plansz z pochodzeniem; adapter → `load_samples` czyta oba zdjęcia i obrazy.
- Prawdziwy magazyn `annotations\0cdc…72c2` i `manifests`: SHA-256, rozmiar i mtime
  12 plików identyczne przed i po; rewizja 268, 180 siatek, 63 akceptacje,
  `split_stale=false`, `assisted_photos` puste.

### Not completed

- Commit, `CURRENT_STATE.md`, przeniesienie do `completed/` — poza zakresem
  implementera.
- Pierwszy zapis operatora oznaczy zamrożony podział D-456 jako `split_stale`
  (istniejąca reguła magazynu dla każdej zmiany geometrii); runy labu na manifeście
  D-456 zwrócą wtedy `RUN_DATA_DRIFT`. Podział, manifesty i wyniki T05 pozostają bez
  zmian. Wymaga świadomości operatora / wpisu decyzji.
- Numeracja pozycji starych anotacji labu nie zawsze jest rzędowa (np. zdjęcie 227:
  lewa dolna plansza zapisana jako pozycja 8); strona wykrywa kolizję i wymaga
  ręcznego numeru. Eksport niesie niezależną `readingOrder` z geometrii.
- Plansze częściowo poza kadrem nie dadzą się zapisać (`GEOMETRY_OUTSIDE_SOURCE`);
  takie zdjęcia zostają niekompletne do decyzji wyjątku D-484.

### Documentation updates

- `ai_docs/guides/VISION_LAB_LOCAL.md`: sekcja „Kompletne zdjęcia Mumie, Blazing i
  Gang z propozycjami sieci (TASK-0824, D-490)” — start/stop, klawisze, kolory,
  kompletność, trwałość, eksport, skutek `split_stale`.

### Recommended next task

- Snapshot treningowy runu 3 (preset D): eksport `-Action Export`, podział zdjęć
  każdej gry na trening i odłożoną ocenę, `write_reader_snapshot` z rolami
  `training`/`development`. Wcześniej: pomiar czasu na pierwszych 10 zdjęciach Mumie.
