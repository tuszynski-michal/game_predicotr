---
title: TASK-0563 — Selektywna korekta plansz v1.1
status: done
last_updated: 2026-09-16
---

# TASK-0563 — Selektywna korekta plansz v1.1

## Goal

Zachować wszystkie przyjęte wyniki v1.0 i odzyskać odrzucone zdjęcia z siedmioma
lub ośmioma pewnymi planszami, kierując najwyżej dwie robocze propozycje do
Reviewera z czterema uchwytami.

## Context

Zaakceptowany plan „v1.0 i v1.1 — selektywna korekta niepewnych plansz” w
bieżącej rozmowie. Na stagingu 45163–70371 baza v1.0 to 2761 przyjętych i 40
do korekty. Historyczny frame-support spowodował regresję 40→355.

## Recommended execution

`gpt-6-astra high`; niezależny review `gpt-6-astra high` zgodnie z planem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Osobny opt-in wariant i checksumowany snapshot.
- Próba odzysku tylko po odrzuceniu v1.0; wymagane 7–8 pewnych siatek,
  bezpieczna perspektywa i kolejność, bez pionowego ucięcia.
- Zapis roboczego obrysu i dowodów niepewności, brak automatycznych cropów z
  niepewnej planszy, kolejka Reviewer zamiast korekty całego zdjęcia.
- Atomowe zatwierdzenie również niezmienionego świadomie sprawdzonego obrysu.

## Out of scope

- Zmiana progów bazowego v1.0 i uruchamianie jobów na danych użytkownika.
- Usuwanie historycznych manifestów i migracje destrukcyjne.

## Acceptance criteria

- [x] Każdy wpis przyjęty przez zgodny bazowy manifest v1.0 jest ponownie użyty w v1.1.
- [x] Przy 7–8 pewnych siatkach tylko 1–2 słabe trafiają do Reviewer.
- [x] Przy 3 słabych, błędnej perspektywie, pionowym ucięciu lub niejednoznacznej
      kolejności działa dotychczasowa pełna korekta.
- [x] Roboczy obrys jest wstępnie edytowalny czterema uchwytami, lecz nie jest
      automatycznie zatwierdzony ani użyty do cropów lub uczenia.
- [x] Odczytowa kontrola realnych przykładów, testy workera/API/Reviewera,
      OpenAPI, lint, typy i build przechodzą.

## Outcome

Wariant opt-in v1.1 zachowuje bazowy wynik v1.0, przechowuje wyłącznie
niepotwierdzone obrysy 1–2 słabych plansz i otwiera je w Reviewerze. Zapis
używa dotychczasowej atomowej rewizji; świadome zatwierdzenie bez ruchu rogów
jest możliwe. Brak wystarczającego dowodu zachowuje pełną korektę, a faktycznie
niepełne plansze pozostają w osobnej ścieżce v1.0. Na trzech rzeczywistych
zdjęciach próbny wynik to osiem siatek i jeden obrys; pełnego nowego joba nie
uruchomiono. Odczyt manifestu 45163–70371 potwierdził bazę 2761/40, lecz
nowy wariant nie ma jeszcze pomiaru całego stagingu. Pełny mypy repozytorium
pozostaje czerwony przez dwa istniejące błędy w niezmienionym
`semi_automatic_selection/job.py`; typy 17 zmienionych modułów przechodzą.
