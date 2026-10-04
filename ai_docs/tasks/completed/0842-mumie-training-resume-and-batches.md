---
title: TASK-0842 — Mumie, wznowienie uczenia i partie danych
status: done
last_updated: 2026-10-04
---

# TASK-0842 — Mumie, wznowienie uczenia i partie danych

## Status

`done`

## Goal

Zweryfikować import Mumii, wykonać jedną ocenianą iterację F oraz dostarczyć
trwałe partie zdjęć i wycinki z poprawnych siatek do późniejszego uczenia symboli.

## Context

Operator polecił wznowienie niezależnie od własnej pracy. Dotychczasowy stan:
236 zdjęć, 20 kompletnych (16 trening / 4 odłożone), 11 rozpoczętych, iteracja 3.

## Dependencies / entry conditions

Istniejący katalog, magazyn anotacji, run 3 oraz GPU Python. Brak nowych zdjęć
zatwierdzonych od iteracji 3: jawnie przyjmujemy jedną próbę na tych samych
danych (`--allow-same-data`) z nową bramką F. Nie ma innego aktywnego treningu.
Brak etykiet symboli nie blokuje geometrii; blokuje trening klasyfikatora.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`, jak w zaakceptowanym planie wznowienia.
Integralność, budżet albo sprzeczne pochodzenie danych zatrzymują zależne działanie.
Nie delegować bez polecenia operatora.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/HANDOFF_GRID_V3_20261004.md`
- `ai_docs/delivery/MUMIE_TRAINING_RESUME_20261004.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/guides/VISION_LAB_LOCAL.md` — kompletne zdjęcia i run 3
- `ai_docs/process/DECISION_LOG.md` — D-489, D-490
- `ai_docs/tasks/0671-vision-lab-symbol-labels.md` — bramki etykiet

## Scope

Kontrola importu SHA, jedna iteracja istniejącego runu, partie całych zdjęć,
wycinki zatwierdzonych siatek, kontrola danych symboli i złotej ramki, raport.

## Out of scope

Wypłaty, migracje, aktywacja modeli w produkcji, shadow, kasowanie danych,
automatyczne zatwierdzanie geometrii lub klas symboli, stare etykiety 777.

## Acceptance criteria

- [x] Wszystkie znane zdjęcia Mumii rozliczone po SHA; brak cichego duplikowania.
- [x] Iteracja 4 zakończona i oceniona według F; rzeczywisty wynik i budżet zapisane.
- [x] Partie do 50 całych zdjęć stabilne i rozliczone; cropy tylko z kompletnych zdjęć.
- [x] Manifest odróżnia etykiety od propozycji, wiąże źródła i rewizje, przechodzi odczyt w nowym procesie.
- [x] Stan etykiet symboli i przykłady złotej ramki sprawdzone bez pozornego treningu.
- [x] Raport, CURRENT_STATE, Outcome i osobny commit.

## Technical notes

Wykorzystać istniejące Catalog, read_store_state, open_proposals, photo_view,
photo_complete i crop_cell. Zachować kolejność kolejki i pozycji plansz.
Nowy pomocnik tworzy artefakty obok danych, bez połączenia z bazą i bez
AnnotationStore.write. Nie zakładać dziewięciu plansz na zdjęciu.
Klasy symboli oraz cecha Super pozostają unknown do rzeczywistego przeglądu.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/vision_lab/mumie_batches.py`,
  `services/worker/tests/test_vision_lab_mumie_batches.py` i raport jakości.
- Istniejące: CURRENT_STATE, DECISION_LOG (doprecyzowanie D-490).
- Artefakty poza Git: ledger runu, raport iteracji, manifest partii i wycinki.

## Test cases

Stabilna kolejność, brak źródła folderu, niekompletna siatka bez cropów,
integralność SHA, bezpieczne wznowienie identycznego eksportu i odczyt z nowego procesu.

## Verification

Skoncentrowane testy helpera i Ruff z limitem 120 s, rzeczywisty preflight,
manifest i odczyt checksum w osobnym procesie. Trening w odłączonym workerze
z trwałym budżetem; nadzorca z ograniczonym czasem i zapisanym PID.

## Risks / open questions

Mały zbiór ręcznych etykiet ogranicza miarodajność wyniku. Kolejne porcje
uczenia wymagają poprawnych etykiet; predykcje nie są targetem treningu.
Super: dostępność ramek i słownika do sprawdzenia; mechanika wypłat odłożona.

## Outcome

### Changed

Import labu potwierdzony SHA (225/225). Create-only pomocnik przygotował 236
zdjęć w 5 partiach i 2700 nieoznaczonych wycinków z 180 plansz na 20 kompletnych
zdjęciach. Iteracja 4 F wykonana: brak poprawy holdoutu, poprzedni model zachowany.

### Verification results

5 testów PASS, Ruff check/format PASS, Mypy PASS. Integralność w nowym procesie
PASS; ponowienie odzyskało identyczny artefakt. Trening 901 s, 1922 kroki,
3602/14400 s zużycia runu. Wynik porównano ze wszystkimi kryteriami taska i planu.

### Not completed

Trening symboli i Super: brak etykiet nowych kompletnych cropów i ramki.
Nie użyto 244 wcześniejszych decyzji. Bez aktywacji, shadow, migracji,
usuwania ani zapisów do bazy.

### Documentation updates

Raport jakości, plan wznowienia, ostrzeżenie starego planu premium, D-490
i CURRENT_STATE. Commit `v1.7.187` (hash dopisany po commicie).

### Recommended next task

TASK-0843 — dokończenie zleconego wgrywania Mumii do głównej aplikacji.
