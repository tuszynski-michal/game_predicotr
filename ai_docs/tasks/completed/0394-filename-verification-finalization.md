---
title: TASK-0394 — Domknięcie OCR weryfikacji zakresów bez selekcji
status: done
last_updated: 2026-09-02
---

# TASK-0394 — Domknięcie OCR weryfikacji zakresów bez selekcji

## Goal

Naprawić trwałe wznowienie runu weryfikacji nazw bez ponownego OCR oraz
oddzielić je od automatycznej selekcji reprezentantów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- tryb `filename_verification` po OCR nie wykonuje wyboru zakresów ani outputu;
- monotoniczny progres joba i trwałe retry bez ponownego OCR;
- wspólny, czysty klasyfikator weryfikacji pliku dla workera i API;
- bezpieczne cofnięcie niepotwierdzonego, błędnego wyboru historycznego runu;
- akcja Admina do wznowienia failed runu.

## Out of scope

- automatyczne czyszczenie danych po zakończeniu review (TASK-0395);
- zmiana OCR, proofów, selectorów lub zwykłej półautomatycznej selekcji.

## Definition of done

- weryfikacja nazw nie wybiera reprezentanta ani nie tworzy `seq_*`;
- terminalny licznik review nie może zmaleć po OCR;
- retry wykorzystuje istniejące obserwacje i zachowuje właściwy błąd domenowy;
- failed run da się wznowić z Admina;
- automatyczny cleanup nie jest jeszcze uruchamiany.

## Outcome

- Worker rozdziela `filename_verification` od selekcji: po OCR klasyfikuje
  obserwacje jako `verified`, `unreadable`, `mismatch` lub
  `invalid_filename`, bez `apply_selection` i bez local outputu.
- Terminalny checkpoint publikuje liczbę review tylko raz, a wyjątek
  `JOB_PROGRESS_REGRESSION` nie jest już maskowany jako niepoprawny checkpoint.
- Retry workflowu weryfikacji resetuje wyłącznie postęp joba; obserwacje OCR,
  checksummy i diagnostyka runu pozostają nienaruszone. Błędny historyczny
  wybór jest cofany tylko, gdy nie ma outputu ani potwierdzenia lokalnego.
- Admin otrzymał akcję `Wznów analizę`, która uruchamia polling po requeue i
  komunikuje, że OCR nie będzie wykonany ponownie.
- Uruchomiono skupione testy API, workera oraz Admina, Ruff i mypy. Cleanup po
  terminalnym review pozostaje celowo zakresem TASK-0395.
