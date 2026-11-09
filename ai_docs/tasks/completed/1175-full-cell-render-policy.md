---
title: TASK-1175 — Pełne pola symboli bez marginesu8%
status: done
last_updated: 2026-11-09
---

# TASK-1175 — Pełne pola symboli bez marginesu8%

## Status

`done`

## Goal

Pełne pola symboli bez marginesu8%.

## Context

Operator zaakceptował2–4h na margines0%, testy i Opus, połączył z najnowszym
zgłoszeniem powtarzającej się planszy i wolnego ładowania. Pełny zakres dwóch
tasków jest zlecony; zgoda nie obejmuje wdrożenia ani merge.

## Recommended execution

gpt-6.1-sol/high. Terminalowy niezależny Claude Code claude-opus-5-5/high,
przed commitem; otwarte P0/P1 po jednej rundzie poprawek zatrzymują task.
Bez automatycznej delegacji ani zmiany modelu.

## Relevant docs

- `ai_docs/delivery/FULL_FIELD_CORRECTION_FLOW_PLAN_20261109.md`.
- `ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md`, `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`.
- `ai_docs/requirements/IMAGE_INGESTION.md`, `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`.
- `ai_docs/process/CROSS_AUDIT.md`, `ai_docs/process/DEFINITION_OF_DONE.md`.
- `ai_docs/tasks/completed/1174-geometry-review-navigation.md` — wyłącznie zależność i zapis hasha.
- `ai_docs/process/decisions/DECISION_LOG_2026.md` — konkretne D-462/D-488/D-591/D-596/D-597 przez indeks; nie czytać całości.

## Out of scope

Trening, default geometrii, zapis do bazy operatora, masowe akceptacje, restarty,
merge/push i wdrożenie. Testy PG wyłącznie disposable. Operatorowe odczyty bounded/read-only.

## Scope

T2 planu. Jawny nowy pin0% w nowych snapshotach i dalszej manualnej korekcie obecnych6219; historyczny brak pola pozostaje8% i zachowuje fingerprint. Doprecyzować konkretną ścieżkę przed implementacją po sprawdzeniu manual resolvera.

## Dependencies / entry conditions

TASK-1174 zamknięty, OpusR2 PASS, v1.7.587/1181797c; hash zapisany do tego taska
metadanymi następnego commita. Brak blokującego pytania. D-598 konkretyzuje
zaakceptowany wybór0%, bez zmiany modelu, wag, RGB lub rozmiaru.

## Technical notes

- Zamknięte `cropPolicyVersion=full-cell-v2` w snapshotach i nowych manualnych
  komendach. Brak pola zachowuje dotychczasowy hash i sposób wycinania.
- Nowy resolver aktywnego modelu przypina0. Historyczny parser nie podmienia
  importu. Ręczny podgląd/symbole/zapis używają tego samego jawnego tokenu;
  klient nie podaje surowego paddingu. Token wchodzi do hasha komendy i draftu.
- Zmiana tokenu przy retry z tym samym kluczem daje konflikt, nie zapis innego
  wycinka. Nowe ręczne rewizje utrwalają konfigurację0 oraz efektywny snapshot
  predykcji. Historyczne rewizje/etykiety i pełne piny importów pozostają.
- Kontekst pending nie może pożyczać konfiguracji z dowolnego innego slotu
  lub importu: przy mieszanych starych/nowych rewizjach model i render muszą
  wiązać tę samą konfigurację. Zmiana realnych pikseli unieważnia stary symbol.
  Niekompletny stary pin runtime zachowuje czytnik manifestów; jeśli model jest
  przypięty, jego zweryfikowany padding wygrywa z marginesem sąsiada. Nie daje
  to nowego dowodu jakości. Dwie dawne regresje SQL
  zachowują asercje, a fixture jawnie deklaruje ten brak zamiast ogólnego Mock.
- `manualCropPolicyVersion` jest ofertą serwera dla nowej korekty, nie opisem
  starego wycinka. Brak tej opcjonalnej oferty zachowuje klientów legacy.
  Komendy bez polityki nie dostają nowego null pola w serializowanych dowodach.
- Wspólne komponenty zachowują opcjonalny opt-in; nowe targety korekty oferują0,
  także przy przyjęciu propozycji. Szerszy viewport nie jest tym marginesem.
- Aktualne raporty renderu porównują faktyczny padding;0 nie dziedziczy dowodu8.
  Klasyfikacja nowych wycinków jest propozycją do ludzkiej weryfikacji.

## Acceptance criteria

- [x] Spełnione kryteria przypisanej sekcji planu i regresje dotychczasowych konsumentów.
- [x] Spójny kontrakt API/OpenAPI/SDK/wrapper/test, jeżeli zmieniany.
- [x] Właściwe testy/lint/types/build/docs/map i niezależny Opus z receipt; zastane ograniczenia jawnie w raporcie.
- [x] Outcome, task-close, osobny commit i hash w kolejnym commicie.

## Expected files

domain/symbol_model_snapshots.py i image_reviews.py; storage/symbol_model_snapshot_resolver.py;
application/virtual_grid_geometry.py, board_cell_geometry_pending.py i image_reviews.py;
storage/virtual_grid_geometry_repository.py i grid_geometry_proposals.py; schematy/API,
transport klienta/targetów i testy; worker production_crop_classification.py,
dokumenty/mapa. Istniejący production_workflow już korzysta z property snapshotu,
więc bez ręcznej podmiany stałej w workerze.

## Test cases

Legacy bytes/fingerprint/crops unchanged; new policy0 serialized and hash-bound, invalid policies rejected; preview/symbol/save use identical0; changing crop invalidates old quality proof and changed symbol pixels; cold reload/idempotency/PG; real15rasters8/0.

## Verification

Python z D:/game_predicotr/.venv; PYTHONPATH własnego API/workera. Reviewer
`npm run test:geometry --workspace @game-predictor/reviewer` (najpierw właściwe pliki),
scoped Ruff/mypy/ESLint/TS, potem wymagany build. Skończone komendy timeout≤120s;
znany build/audyt według limitów repo. Nie uruchamiać usług.

## Risks / open questions

Dane operatora nie stanowią testowych fixture; same confidence/regularność nie
kwalifikują pełności. Brak GT nie jest pomiarem poprawy klasyfikacji. Nie tworzyć
fikcyjnego PASS. Wszelkie zmiany kolejności/source identity muszą zachować sequence.

## Outcome

Commit: v1.7.588 / `6a560516a45527c196b266be3b479f1a5187aa64`.

Wdrożono jawny full-cell-v2 w nowych snapshotach oraz nowej korekcie
preview/symbols/save/accept. Stare snapshoty i hashe pozostają bez zmian.
Oferta w kontekście jest oddzielna od historycznego renderu. CAS, idempotencja
i szkic wiążą nowy wariant; zmienione piksele wracają do pending, a historie
renderów, source joba i decyzji człowieka są zachowane. API/OpenAPI/SDK/wrapper
i request są zgodne. Brak migracji oraz ręcznej zmiany stałej w workerze.

Weryfikacja:198 testów API/workera, PG1 z nowym interpreterem, Reviewer44+40,
klient160 oraz TS/build/lint PASS. **Mypy16: jeden zastany błąd w niezmienionym
_current_row, potwierdzony na HEAD; bez pełnego PASS i bez tłumienia błędu.**
Końcowe narzędzia/audyt: `ai_docs/quality/TASK-1175_VERIFICATION.md`.
Nie deklarujemy zmierzonej poprawy klasyfikacji bez GT; nie wykonano treningu,
aktywacji, zapisów operatora, restartów, merge ani push.

Opus R1: REVISE/P0-1 — pominięte pole w publicznym payloadzie joba.
Naprawiono w jedynej rundzie poprawek, z rzeczywistą regresją POST/replay/GET/list
dla legacy/full i bootstrap/LAB. Pełne ponowienie dwóch plików przekroczyło120s,
więc nie ma PASS całej próby; ograniczone testy i kontrole są w raporcie.
Import4 PASS; jobs36 PASS/1 zastany FAIL JobType, odtworzony na main41c784fd;
klient161 PASS i nowy schemat mypy1 PASS. Opus R2 PASS,0 otwartych P0/P1,
zamknięte P0-1/P2-1. Raport i receipt:
ai_docs/quality/TASK-1175_AUDIT_claude-opus-5-5.md oraz .receipt.json;
pakiet db6034a137b87f8aca30883777c2267c3c1e8bfc12988caff007f50eacd01648.
Model główny potwierdzony z CLI, high żądane (nie niezależnie atestowane).
P2-1: reinferencja używa historycznych cropów, nie przelicza ich
według nowego pinu; jawny opis pola/architektury i checksumy manifestów.
P2-2 przyjęte: dawny fallback joba zupełnie bez modelu może korzystać z
sąsiedniego manifestu0. Nowe kompletne piny są od tego niezależne.

DoD/plan: wersjonowany pin i stare fingerprinty; pion API i klienta; ręczny
preview/symbole/zapis/propozycje;15 produkcyjnych wycinków i zachowanie historii;
CAS/lost response/nowy proces; worker i brak dziedziczenia kalibracji; dokumenty,
mapa i osobne Opus/commit/task-close — wykonane. Rzeczywista jakość modelu,
wdrożenie i odbiór działającego ekranu nie są wynikiem tych testów.
