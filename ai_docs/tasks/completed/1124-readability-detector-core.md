---
title: Rdzeń detektora nałożenia i nieczytelności
status: done
last_updated: 2026-11-02
---

# TASK-1124 — Rdzeń detektora nałożenia i nieczytelności

## Status

`done`

## Goal

Dostarczyć odtwarzalny, fail-closed rdzeń dwóch headów jakości wraz z kontrolą splitów, artefaktem i bramką pilota.

## Context

Operator zatwierdził cały plan i koszt oraz kandydata nr 5 jako zamrożoną bazę bez aktywacji. Pewna klasyfikacja symbolu nie wyklucza nałożenia dwóch różnych symboli.

## Dependencies / entry conditions

Plan zaakceptowany. A1 dostarcza narzędzia i testy; etykiety operatora powstaną w A2. Bez etykiet nie wykonujemy pilota, treningu ani skanu danych operatora. Istniejący checkpoint produkcyjny nie zapisuje architectureVersion/inputSize; strict state SpatialSymbolCnn i jawny kontrakt preprocessingu w deskryptorze chronią tę granicę.

## Recommended execution

gpt-6.1-sol / high. Niezależny eksperyment, proweniencja i brak leakage wymagają kontroli numerycznej. Review claude-opus-5-5 / high przed commitem. Sprzeczność wymagań lub niedostępny model zatrzymują zależny zakres.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md`
- D-578: `ai_docs/process/decisions/DECISION_LOG_2026.md#d-578--niezależny-detektor-jakości-777-a2-na-zamrożonym-kandydacie-nr-5`

## Scope

- Read-only preflight checkpointu, pełnego członkostwa bazowych splitów i checksum datasetu.
- Frozen features 64x4x4 oraz statystyki natywnego RGB; dwa niezależne liniowe heady L2.
- Rodziny źródeł/reimportów/nagrań/exactRGB, brak leakage, niepewne etykiety osobno dla każdego headu.
- Standaryzacja tylko TRAIN, selekcja lambda/progu tylko VAL, metryki TEST z Wilson95 i bramka pilota.
- Checksum-bound artefakt, walidacja, scoring/ranking i testy regresji.

## Out of scope

API/UI, baza, aktywacja, operator training/scan/pilot, syntetyczne nałożenia i pseudoetykiety.

## Acceptance criteria

- [x] Preflight odrzuca brak/drift checkpointu, assetów, preprocessingu i pełnego splitu.
- [x] Ekstrakcja nie zmienia wag/BN; cechy nie zawierają top1/top2.
- [x] Dwa heady realizują dokładny solver i selekcję planu, niepewne etykiety nie trafiają do odpowiedniego fitu.
- [x] Rodziny nie przeciekają pomiędzy splitami ani bazowym TRAIN/VAL i head TEST.
- [x] Niepełne liczności/proweniencja pilota kończą się STOP, brak pewnych nałożeń nie daje PASS.
- [x] Artefakt przypina wszystkie wejścia i odtwarza scoring po nowym odczycie.
- [x] Testy pionu, ruff, mypy, mapa kodu, docs:check oraz wymagany audyt rozliczone.

## Technical notes

Nowe moduły w symbols są niezależne od HTTP/ORM i nie zmieniają rozpoznawania symboli. Dane przechowują wyłącznie identity/metadane/ścieżki, bez bitmap w JSON. Kandydat nr 5 jest bazą jakości, nie aktywacją modelu symboli. Historyczne unreadable są wyłącznie warstwą doboru, nigdy etykietą overlap. Wynik sigmoid jest score, bez deklaracji kalibracji. Niepewne etykiety mają wartość null. Split docelowo 60/20/20 po rodzinach; priorytet ma ochrona bazowych splitów i minima pilota. Dodatkowy naturalny audit200 nie służy fitowi ani selekcji progów.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/symbols/readability_features.py` — preflight i frozen feature extractor.
- Nowe: `services/worker/src/game_predictor_worker/symbols/readability_cohort.py` — identity, split i minima pilota.
- Nowe: `services/worker/src/game_predictor_worker/symbols/readability_detector.py` — solver, artefakt, scoring i metryki.
- Nowe: `services/worker/tests/test_readability_detector.py` — regresje pionu.
- Istniejące: dokumenty wymagań/architektury, DOC_INDEX, CURRENT_STATE, DECISION_LOG i wygenerowane CODE_MAP.

## Test cases

- Drift checksum/preprocessingu/rodziny/splitu i missing asset powoduje błąd przed ekstrakcją.
- Eval/inference_mode i niezmienne parametry oraz bufory BN po ekstrakcji.
- Zmiana TEST nie zmienia scaler/head/progu; null wyłącza wyłącznie swój head.
- ExactRGB, nagranie i sourceSHA łączą reimporty przechodnio; baza TRAIN/VAL wykluczona z head TEST.
- Brak wymaganej grupy lub audit200 blokuje pełny skan; pełne liczności i recall mogą przejść bramkę.
- Zapis/odczyt JSON odtwarza identyczny fingerprint/ranking; drift zostaje odrzucony.

## Verification

Z katalogu worktree, Python `D:/game_predicotr/.venv/Scripts/python.exe`, każda komenda ograniczona do 120 s (audyt 480 s): pytest wskazanego pliku, ruff check/format --check, mypy nowych modułów, generate_code_map.py i --check, npm run docs:check. Testy planowane nie są wynikiem.

## Risks / open questions

- P2-2: checkpoint nie zawiera samodzielnego odtwarzalnego deskryptora datasetu; para jest autoryzowana kandydatem nr 5 i oboma SHA w zaakceptowanym planie. Dowolna podmiana pary pozostaje niedozwolona.
- P2-3: audit200 dotyczy wyłącznie dotąd nieoznaczonych pól z rodzin poza pilotem i bazowym TRAIN/VAL; raport nie jest estymacją szumu całej gry. Receipt przed etykietami/fitem, limit 800=600+200; brak puli oznacza STOP.

- Empiryczna skuteczność jest niezmierzona do czasu etykiet A2 i jawnego pilota. Nie jest kryterium ukończenia narzędzi A1.
- Brak proweniencji lub spełnienia minimów w limicie 600 wymaga STOP, bez automatycznego zwiększania danych.

## Outcome

Commit: v1.7.517 (hash dopisuje kolejny commit).

### Changed

- Jedna runda korekt audytu: pełna kontrola RGB64x64 bazy, stabilne kody malformed input, limit 800 oraz rozszerzone testy exact errorcodes i bramki.

- Read-only preflight pełnego manifestu i assetów bazowego datasetu, strict SpatialSymbolCnn bestState i katalog klas. Frozen features oraz osiem statystyk natywnych; maksymalnie 128 cropów w ekstrakcji.
- Dwa niezależne L2 heady, deterministyczny LBFGS i kontrola konwergencji; najwyższy dopuszczalny próg VAL, precision i mocniejsza lambda rozstrzygają wybór. Strict score > threshold.
- Rodziny łączone przechodnio, ochrona ekspozycji bazowych splitów, minima pilota, niezależne niepewne etykiety, JSON artifact/fingerprint, ranking i Wilson95, natural audit200 oraz osobny odbiór operatora.
- Parametry, BN i aktywacja modelu bazowego pozostają niezmienione. Scaler i fit nie używają TEST/audit; top1 służy wyłącznie ocenie.

### Verification results

- Po jednej rundzie poprawek audytu: **37/37 testów PASS (17,24 s)**. P1-1 pokryty oddzielnymi przypadkami exact errorcodes; P2-1/4/5 poprawione i przetestowane. P2-2 jawnie zaakceptowane ograniczenie przypiętej pary SHA; P2-3 doprecyzowany niezależny audit200 i limit 800 bez deklaracji szumu całej gry. Oryginalny REVISE zachowany; reconciliation leada na końcu `ai_docs/quality/TASK-1124_AUDIT_claude-opus-5-5.md` zamyka wszystkie P0/P1. Ponownego audytu nie wykonywano: P1 zmienił tylko testy, korekty zachowania dotyczą P2.
- P2-1: każdy bazowy asset musi mieć RGB64x64; P2-4: stabilne błędy malformed dataset/artifact, NaN i legacy checksum default; P2-5: STOP dla recall<90 i chronione defaultsplit. Full fit/reload pozostają zielone.
- Po korektach mypy `--follow-imports=silent` osiągnął limit60s bez wyniku; proces zakończono, brak osieroconych procesów Python. Jedyna alternatywna próba ze strict config w `artifacts/mypy-1124-focused.ini` pomijała wyłącznie importy projektu `game_predictor_api.*` i `game_predictor_worker.images.*`, zachowując normalne numpy/torch/stuby oraz strict wszystkich 3 nowych modułów. Mypy 1.17.1 zakończył się wewnętrznym błędem `NotImplementedError: Cannot serialize TypeGuardedType instance` w write_cache, kod 1. **Kontrola typów po korektach jest partial, nie PASS**; nie ponawiano ani nie osłabiano typowania. WcześniejszyPASS, ruff i37 testów pozostają dowodami o opisanym zakresie. Lead zaakceptował zamknięcie z tym jawnym ograniczeniem narzędzia.

- 12/12 testów przed audytem `services/worker/tests/test_readability_detector.py` PASS (15,23 s), w tym pełny fit dwóch headów na małej fixture, wznowienie przez odczyt artefaktu w nowym procesie, neutralność BN, leakage, brak grup, null labels i nonconvergence.
- Ruff check/format PASS; mapa wygenerowana, `generate_code_map.py --check` PASS.
- Przed audytem mypy trzech modułów z `--follow-imports=silent` PASS; pełne śledzenie importów ujawniło dwa wcześniejsze błędy `schemas/source_lattice_geometry.py` i przekroczyło 120 s. Próba `--follow-imports=skip` nie jest miarodajna dla aliasów numpy i nie jest zaliczoną kontrolą; nie zmieniano zależności dla zieleni.
- Pierwszy asset rzeczywistego frozen datasetu sprawdzony wyłącznie read-only: RGB64x64. Produkcyjny INTER_AREA i treningowy bilinear są wtedy resize no-op; regresja dopuszcza tylko różnicę arytmetyki float skali 2e-7.
- `npm run docs:check` nie znajduje lokalnego `.venv` w izolowanym worktree; te same cztery kontrole uruchamiane bezpośrednio Pythonem głównego checkoutu. Kontrole linków, okna i lustrzanych skilli PASS; budżet poprawiono usunięciem redundantnego punktu ograniczeń (informacja pozostaje w planie i wskaźniku taska).
- Cztery kontrole docs PASS, każdy kod 0: decyzje, okno, budżety (11/11; 43 610 B odczytu startowego) i mirror skilli.
- Pierwszą próbę wymaganego audytu claude-opus-5-5/high wykonał skill `.codex/skills/claude-audit/SKILL.md`, przed commitem. Próba CLI code1 bez werdyktu; pojedyncza diagnostyka ujawniła `You've hit your session limit — resets 8:10pm (Europe/Warsaw)`. Reset 2026-11-02 20:10 Warszawa. Po resecie operator jawnie wznowił audyt; ten sam audytor wykonał przegląd read-only (kod0). Szczegóły historycznej blokady: `ai_docs/quality/TASK-1124_AUDIT_BLOCKER_20261102.md` (raport blokera, nie audyt).

Dodatkowa celowana kontrola po wskazaniu przez leada przyczyny serializacji cache: ten sam scoped strict config z `--cache-dir=nul` (specjalna ścieżka os.devnull obsługiwana przez mypy) nie zwrócił wyniku przez 60 s i został zatrzymany zgodnie z regułą ciszy. Nie wykonano kolejnych prób. Nie osłabiano typów numpy/torch ani nowych modułów; końcowy status kontroli typów po korektach pozostaje partial.

### Not completed

- Końcowa kontrola typów po korektach pozostaje partial przez opisane błędy/limity narzędzia; nie raportujemy jej jako PASS.

- Nie wykonano empirycznego pilota, treningu, skanu ani oznaczeń operatora. Jakość modelu pozostaje niezmierzona do A2 i osobnego pilota. Nie aktywowano kandydata nr 5.
- Bez API/UI, zmian bazy, usług, migracji, merge i push.
- A2 nie rozpoczęto; odbiera go lead po zakończeniu A1.

### Documentation updates

- D-578 opisuje frozen kandydata, niezależne heady i świadomy produkcyjny preprocessing; wymagania/architektura, plan/DOC_INDEX, CURRENT_STATE i mapa kodu uzupełnione.

### Recommended next task

- TASK-1125 / A2: trwałe zebranie etykiet PRZED gotowością modelu i pion skanu/przeglądu wykorzystujący interfejsy A1. Etykiety operatora są warunkiem empirycznego fitu; implementacja UI nie oznacza zgody na taki fit.
