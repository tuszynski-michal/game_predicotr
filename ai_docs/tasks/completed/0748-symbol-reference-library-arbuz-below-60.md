---
title: TASK-0748 — B1 — zapis biblioteki wzorców dla oczekujących Arbuz poniżej 60%
status: done
last_updated: 2026-09-30
---

# TASK-0748 — B1 — zapis biblioteki wzorców dla oczekujących Arbuz poniżej 60%

## Status

`done`

## Goal

Pierwszy przebieg D-466: pewne propozycje biblioteki wzorców zapisane jako
nowa wersja predykcji dla oczekujących komórek z predykcją modelu Arbuz i
pewnością poniżej 60% w grze `777`.

## Context

Operator 2026-09-30 polecił przeprowadzić cały proces (T3–T5 i B1) bez
swojego udziału, z zatrzymaniem tylko przy krytycznym błędzie. To polecenie
jest zgodą na zapis wymaganą przez D-466.

## Dependencies / entry conditions

- TASK-0744 (narzędzie zapisu) scalone do `v1.1-vision-lab-hybrid-geometry`.
- TASK-0745 i TASK-0746 (filtry) — do przeglądu wyników w Adminie.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo); kontrola po zapisie
odczytem bazy.

## Relevant docs

- `ai_docs/delivery/SYMBOL_REFERENCE_LIBRARY_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-466)
- `ai_docs/tasks/completed/0744-symbol-reference-library-writer.md`

## Scope

- `apply-preview` (manifest), kanarek na 3 planszach, test cofnięcia na 1
  planszy, pełny zapis w porcjach, `apply-verify`, odczyt liczników przez API.

## Out of scope

- Inne symbole i pasma pewności (osobne przebiegi), zatwierdzanie komórek.

## Acceptance criteria

- [x] Manifest z sumą kontrolną; zapis tylko dla tej sumy.
- [x] Kanarek: komórki docelowe `pending`, nowy symbol i nowa wersja
  predykcji; komórki niedocelowe bez zmiany decyzji i przypisania.
- [x] Cofnięcie przywraca predykcję modelu i działa tylko na wskazanej
  planszy.
- [x] Pełny zapis bez błędów; `apply-verify` zgodny z manifestem.

## Technical notes

- Polecenia (z katalogu worktree, `PYTHONPATH=services/worker/src;services/api/src`):
  `scripts/evaluate_symbol_reference_library.py apply-preview --game-code 7
  --symbol ARBUZ --max-confidence 0.6 --library-cache
  artifacts/symbol-reference-library/stage-a/crop-cache.npz --artifact-root
  <repo>/artifacts --output-dir artifacts/symbol-reference-library/apply-arbuz-lt60`,
  potem `apply` / `apply-revert` / `apply-verify` z `--manifest
  …/apply-manifest.json --expected-sha256 <suma>`.

## Test cases

- Odczyt 45 komórek kanarka przed i po zapisie oraz po cofnięciu.

## Outcome

- Manifest `artifacts/symbol-reference-library/apply-arbuz-lt60/apply-manifest.json`
  (w worktree, poza Gitem), sha256
  `1e4be8ce89590a0532a2b7d8483e030c12df6da289a8746a9bd622fdca1ecd61`,
  suma przebiegu (`model_checksum_sha256` wersji)
  `131eec1b8ecb0e0a92569d95bc072d7579786a5618815087b73cf88ecc89481c`:
  2 703 plansze, 2 918 komórek (2 621 potwierdzeń Arbuz; zmiany: Cytryna 35,
  Gwiazda 60, Pomarańcz 61, Siedem 43, Śliwka 26, Winogron 12, Wiśnia 60).
  377 komórek bez pewnej propozycji zostało przy predykcji modelu.
- Kanarek 2026-09-30 00:08 UTC: plansze `000fd4a8…` (2 potwierdzenia),
  `111e66a3…` (Arbuz → Cytryna), `0440c2ef…` (Arbuz → Wiśnia). Wszystkie 45
  komórek pozostały `pending/model`; komórki docelowe dostały nowy symbol,
  pozostałe zachowały symbol; `revision` każdej komórki +1 (zmiana wersji
  predykcji planszy).
- Test cofnięcia: `apply-revert --board 111e66a3…` przywrócił Arbuz z
  wersją `spatial-symbol-cnn-onnx-v1` (nowa wersja, suma revertu). Ta
  plansza zostaje przy predykcji modelu i nie wróci do biblioteki w tym
  zakresie przebiegu.
- Pełny zapis: 5 porcji po ok. 100 s, 00:08–00:27 UTC, 2 703 pokwitowania
  `applied`, 0 błędów, 0 `stale`. `apply-verify`: 2 917 komórek z predykcją
  biblioteki, 1 cofnięta, 0 zmienionych przez operatora w międzyczasie.
  W bazie 2 703 wersje `symbol-reference-library-v1`.
- Liczniki API (filtr „Nowy algorytm”, stan oczekujące): wszystkie symbole
  2 917 — Arbuz 2 621, Cytryna 34, Gwiazda 60, Pomarańcz 61, Siedem 43,
  Śliwka 26, Winogron 12, Wiśnia 60. Arbuz ze starym modelem i pewnością
  < 60%: 382.
- Przegląd w Adminie: `Weryfikacja symboli` → symbol → „Źródło predykcji:
  Nowy algorytm” i opcjonalnie „Data zmiany komórki: Od dziś 00:00”.
- Wycofanie całego przebiegu (tylko na polecenie operatora):
  `apply-revert --all` z tym samym manifestem i sumą.
