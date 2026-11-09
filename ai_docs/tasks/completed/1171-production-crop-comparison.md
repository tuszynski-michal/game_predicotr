---
title: TASK-1171 — Porównanie produkcyjnych wycinków 8% i 0%
status: done
last_updated: 2026-11-09
---

# TASK-1171 — Porównanie produkcyjnych wycinków 8% i 0%

## Status

`done`

## Goal

Deterministyczna ocena zawartości i klasyfikacji bez zmiany aktywnego modelu.

## Context

Operator zaakceptował cały plan i koszt 6–10 h; audyty tylko terminalowe.
Zatwierdzenie kosztu nie obejmuje operatorowego treningu, wdrożenia ani merge.

## Dependencies / entry conditions

TASK-1170 zamknięty. Przed kodem ponownie odczytać przypisaną sekcję zaakceptowanego planu.

## Recommended execution

gpt-6-astra/high. Uzasadnienie: Deterministyczna ocena zawartości i klasyfikacji bez zmiany aktywnego modelu. Nierozwiązane P0/P1 blokują commit;
nie zmieniać modelu niejawnie. Review Claude Code claude-opus-5-5/high.

## Relevant docs

- `ai_docs/delivery/GRID_SYMBOL_CROP_PREVIEW_PLAN_20261109.md` — T2 i kryteria wspólne.
- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`.
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`.
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-593--izolowane-etykietowanie-i-dowodowy-eksport-html`.
- D-590/D-591/D-592 w tym samym pliku, przez wyszukanie odpowiednich sekcji.
- `ai_docs/process/CROSS_AUDIT.md`, `ai_docs/process/DEFINITION_OF_DONE.md`.

## Scope

Sekcja T2 planu i niezbędne testy regresji. Rzeczywisty renderer; manual potem model; te same instancje; 0.08 vs 0.0 tylko margines; lab RGB osobny kontrakt; bez labels wynik unavailable; bramka per-game bez kompensacji.

## Out of scope

Aktywacja modelu/marginesu, operatorowy GPU/trening/import691, mutacje etykiet,
restarty usług, migracja operatora, merge/push oraz klasyfikator nowej architektury.

## Acceptance criteria

- [x] Każdy punkt T2 planu ma implementację lub jawny warunek zależny od danych.
- [x] Rzeczywisty renderer; manual potem model; te same instancje; 0.08 vs 0.0 tylko margines; lab RGB osobny kontrakt; bez labels wynik unavailable; bramka per-game bez kompensacji.
- [x] Istniejące historyczne kontrakty i ręczne korekty są zachowane.
- [x] Właściwe testy, lint, typy i docs/map; niezależny Opus audit i receipt.

## Technical notes

Decyzja T2: D-595 w logu decyzji (diagnostyka, nie kwalifikacja/publikacja).

Źródłem prawdy są rewizje zapisanych adnotacji, frozen snapshot i pinned render.
Nie zamieniać pudełka podglądu w GT. Nie wyświetlać podpowiedzi w blind; chronić
całe źródła użyte w pomiarze. Brak danych jest jawnym stanem, nie PASS.
Analiza read-only wykonawcy potwierdziła asymetrię istniejącego renderera:
padding=0 używa cell.source_quad (dokładne wewnętrzne węzły), dodatni padding
projektuje inset przez homografię całej planszy. Zachować oba zachowania,
zmieniać wyłącznie parametr marginesu i jawnie opisać ten skutek, z regresją
nieregularnych węzłów. Nie poprawiać legacy warpu w tym tasku.
Klasyfikacja wymaga current human class/crop identity, nie samego confidence.
Runtime jest osobnym zwalidowanym current-diagnostic-runtime envelope, nie fikcyjną
historyczną polityką. Known manual/disabled to zero decyzji z konfiguracji, nie
kwalifikacja jakości; producer musi rzeczywiście dostarczać ten pin.
LocalSymbolOnnxAdapter i aktualny confidence contract są źródłem predykcji;
brak progu/modelu/ręcznej klasy daje unavailable. Lab RGB jest osobnym kontraktem.

Wykonywalny producent korzysta z istniejącej kohorty i ograniczonego odczytu
READ ONLY bieżących dowodów. Nowy diagnostic capture nie zmienia frozen
snapshotu. Przed pikselami sprawdza role, blind, kopie i aktualność źródła.
Human class wymaga current crop/owner oraz zgodnego zdarzenia approve/reassign
lub board_synchronized z current board_decision i dowodem aktualnej ludzkiej decyzji planszy;
confidence policy pochodzi wyłącznie z przypiętego raportu kalibracji modelu.
Raport production-crop-comparison-v1 jest dowodem diagnostycznym, nie raportem
publikacji modelu. Zachowuje wszystkie wybrane źródła i instancje, także braki.
CLI wytwarza capture i rastry bez ręcznego składania JSON; replay weryfikuje piny.

A internal scoring wiąże WSZYSTKIE latest/current pass2 refs z jednym właściwym
frozen raportem u/δ. Inna porzucona pass1 nie unieważnia tych referencji; TRAIN
i auxiliary galerie pozostają chronione przez wszystkie zapisane sesje/aliasy.
A nie eksportuje PNG ani wizualnych hintów. Wewnętrzny sealed JSON zachowuje
geometrię/klasy do replay i metryk; zaakceptowane ryzyko lokalnych metadanych nie
uprawnia do użycia ich w HTML. T4 konsumuje tylko TRAIN i visualExportAllowed=true.
Actual input witness działa bez contentGT:
SHA odtworzonego wybranego BASE/rescue musi odpowiadać rzeczywistemu tensorowi
wykonanego runnera. Bez dodatkowej inferencji ani ręcznych model nodes.

Artykuły pomocnicze są w root artifacts/full-symbol-training-20261109; nie nadpisywać
ich ani bazy. Odczyt operatorski tylko read-only; wyniki do artifacts tego worktree.

## Expected files

Runda R1: te same moduły oraz nowy
`services/api/tests/integration/test_production_crop_capture_postgres.py` i
`ai_docs/quality/TASK-1171_FIXES_R1.md`. Producent przypina zwalidowany current
diagnostic runtime envelope osobno od historycznego importu/modelu. Testy
producer→consumer używają rzeczywistego autora candidate_gate. Pozostałe poprawki:
board_synchronized human GT, bramka damage/missing, świadek screen, referencyjne
sumy LAB oraz uczciwa granica internal A JSON / brak wizualnego eksportu A.

- Zmiana: services/worker/src/game_predictor_worker/images/production_cell_evaluation.py
  (opcjonalna konfiguracja/raster sink, bez zmiany defaultu).
- Nowe: services/api/src/game_predictor_api/storage/production_crop_capture.py;
  services/worker/src/game_predictor_worker/images/production_crop_comparison.py,
  production_crop_classification.py, production_crop_artifacts.py, production_crop_inputs.py;
  scripts/compare_production_symbol_crops.py.
- Testy: services/worker/tests/test_production_crop_comparison.py (także producent
  READ ONLY, ochrona aliasów i current A measurement); istniejący
  test_production_cell_observations.py uruchomiony bez zmian.
- Wymagania/architektura VISION_LAB i raport TASK-1171_VERIFICATION.
- Bez zmiany VirtualCellRenderer, symbol_onnx i LAB_RGB runtime. Root prowadzi
  decyzję, CURRENT_STATE, mapę kodu, audyt i zamknięcie/commit.

## Test cases

Kryteria planu: ghost quad, wspólne granice/perspektywa, J/10/obramowania/ciemne
symbole, sąsiad, brak pikseli/rzędu, blind isolation, CAS/currentness i restart/replay.
Testy specyficzne dla taska doprecyzować przed implementacją w raporcie weryfikacji.

## Verification

Z katalogu worktree: właściwe testy pytest przez D:/game_predicotr/.venv/Scripts/python.exe
z PYTHONPATH własnego services/api/src i services/worker/src; testy Admin
`npm run test:geometry --workspace @game-predictor/admin`, scoped lint/typecheck,
`npm run docs:check`, `npm run code-map:check`. Każda komenda ma timeout.
Szerszy build dopiero po testach pionu. Audyt według CROSS_AUDIT do 1800 s.

## Risks / open questions

Brak GT i rodowodu może blokować wynik jakości, nie implementację narzędzia.
Nie deklarować poprawy wytrenowanego modelu bez rzeczywistego eksperymentu.

## Outcome

Commit: v1.7.583 (hash dopisuje kolejny commit).

Po Opus R1 wykonano jedną rundę poprawek; implementacja zamrożona do focused R2,
formalny status pozostaje in_progress. Mapa ID→zmiana/test:
`ai_docs/quality/TASK-1171_FIXES_R1.md`.
Wykonywalny CLI daje immutable capture, prawdziwe rastry, model outputs i input
witness oraz per-game/role rekomendację diagnostyczną bez qualification/publish.
Zachowany VirtualCellRenderer, istniejący classifier/LAB runtime i defaulty.

Testy: 47 passed (18.58 s) oraz1PostgreSQL passed (25.34 s), Ruff format/check
dziewięciu plików PASS; scoped mypy siedmiu modułów/CLI PASS. PG wykonuje
produkcyjne save_resolution, odczytuje15klas i current frozen A/protection
READ ONLY we własnej jednorazowej bazie. Rzeczywisty READ ONLY/CPU pilot na
jednym ponownie sprawdzonym TRAIN w `D:/game_predicotr/artifacts/t1171-r1-final`:
9 plansz /135 instancji, 540 cropów, screen i9 board inputs available. Cold
replay w nowym procesie: exit0, identyczny report SHA. Szczegóły, polecenie,
SHA modeli/raportu, granice i punktowe kryteria w
`ai_docs/quality/TASK-1171_VERIFICATION.md`.

Domknięcie R1: rzeczywisty producent current diagnostic runtime pin i obsługa
autentycznego candidate_gate v2/M6 v1; test producer→consumer osiąga candidate
przy znanym manual/disabled, bez kwalifikacji automatu. Current owner i human
board_synchronized są związane z aktualnym cropem/rewizją i human resolution.
Każdy licznik damage oraz nowa missing instance blokują rekomendację bez
kompensacji. Screen/rescue witness wpływa na partial. LAB ma osobne absolutne
sumy per game/role; internal A JSON może zawierać metadane do replay, ale nie
wolno go używać w wizualnej galerii. Brak runtime nadal unavailable.

Operatorowa jakość not_evaluable: brak contentGT/uδ/current class GT oraz
historyczny unclassified snapshot klasyfikatora; brak LAB iteration.
Nie dopisywano operatorskich GT, sesji, predykcji ani progów. Nie uruchamiano treningu/GPU,
usług, Admin build ani zmian operatora. Brak zmian API/schematu. Root prowadzi
mapę/docs:check, niezależny Opus audit/receipt, task-close i commit; wykonawca
nie stage'uje ani nie commit'uje. Następny task po akceptacji audytu: TASK-1172.

Root po freeze: regeneracja mapy, docs:check i code-map:check PASS; logi artifacts/t1171-{code-map,docs-check,code-map-check}.log. Niezależny audyt przed commitem pozostaje następny.

Domknięcie root: Opus R2 **PASS**, 0P0/0P1, terminal, rzeczywisty główny model
claude-opus-5-5; high żądane. Receipt zweryfikowany SHA raportu/pakietu
3a0be39256e817d77693cdb4ec11511c0a2354948c27da285164475998e5f2a1.
Regeneracja mapy, docs:check i code-map:check po poprawkach PASS
(logi artifacts/t1171-r2-*). Testy Admina niepowtarzane w tym tasku bez zmian
Admina; pełny build i przekrojowy odbiór pozostają TASK-1173.

Otwarte P2 przyjęte jako jawne ograniczenia (nie są PASS jakości operatora):
P2-5 autentyczny LAB calibration-only-temperature nie ma obecnie rozpoznanej
polityki, więc LAB daje not_evaluable przy zachowanych surowych licznikach;
P2-6 blacklist aktorów nie wyklucza wszystkich narzędziowych aktorów (np.
m6-acceptance-runner/benchmark:local-admin); takich decyzji nie wolno traktować
jako ludzkiego GT. P2-7 zachowane assignment_source=human po kolejnej decyzji
planszy może dać zachowawcze unavailable. P2-8 TRAIN wymaga jednego jednoznacznego
kwalifikowanego raportu u/δ, wieloznaczny wybór oznacza brak dowodu. P2-9 usable
predictionIndex rastrów i original found predictionIndex wejść/modelPredictions
mają różne przestrzenie: TASK-1173 nie łączy ich po samej nazwie; wejścia NN
pokaże per zdjęcie/stage z kontrolą tożsamości. Surowe A JSON są wewnętrzne,
nie trafiają do HTML. T1 P2 i przyszły plik TASK-1173 pozostają poza tym commitem.
