---
title: TASK-0238 image selection v10.8 layout-anchored recovery
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0238 — Image selection v10.8 layout-anchored recovery

## Goal

Przywrócić szybkie i bezpieczne rozpoznawanie zakresu na rzeczywistych zdjęciach,
na których użytkownik widzi cztery kolejne etykiety, oraz usunąć zbędne elementy
review powstające z fragmentacji przejść między kolejnymi ekranami.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/tasks/0178-image-selection-v10-accuracy-first-selection.md`

## Scope

- [x] bezpiecznie anulować niezaakceptowany run v10.7 bez usuwania stagingu,
- [x] zakotwiczyć OCR w pozycyjnej siatce dziewięciu layoutów,
- [x] zaakceptować jeden spójny ciąg czterech etykiet mimo błędów OCR poza nim,
- [x] odrzucać większościowo mocno rozmazane layouty,
- [x] zachować próbkę pięciu zdjęć ze środka oraz po trzy z obu brzegów,
- [x] ograniczyć ogólny fallback OCR do poziomów `9 -> 18`,
- [x] odrzucać fragmenty przejściowe między bezpośrednio kolejnymi zakresami,
- [x] scalać rozproszone fragmenty jednej dokładnej luki dziewięciu layoutów,
- [x] dodać fingerprintowany kontrakt odbioru i regresje,
- [x] wykonać profile diagnostyczne bez publikacji outputu.

## Outcome

Domyślnym selektorem jest `fast-image-selector-v10.8` o fingerprintcie
`eb5006f3b6ed5e63b668074bf2e81d8b162d5794d542fd00457ee6a860682769`.
Historyczne manifesty, w tym v10.7, zachowują swoje fingerprinty i zachowanie.

Run v10.7 `45c80055-5beb-43bc-bc35-8c84b3e2b19c` został anulowany przez
kontrolowane API na checkpointcie 10 176 / 42 403. Zakończył się wynikiem 648
grup: 34 automatyczne, 603 `range_required` i 11 duplikatów. Staging i katalog
wynikowy nie zostały usunięte.

Rzeczywisty przypadek `19999–20007`, który wcześniej kończył się bez zakresu,
odczytuje teraz poprawny ciąg `20003–20006` z pozycji 4–7. Błędne wyniki OCR
`9999`, `20502` i `2000` poza tym oknem nie unieważniają lokalnego dowodu.
Profil tych samych 20 zdjęć skrócił się z 50,72 s i trzech nieznanych grup do
7,98 s i trzech poprawnych zakresów.

Końcowy profil pierwszych 1000 zdjęć trwał 335,63 s zamiast 528,49 s po usunięciu
bezowocnego poziomu 36; liczba cropów OCR spadła z 9486 do 5130. Profil 400
zdjęć, obejmujący najgorszy pierwszy blok fragmentacji, trwał 151,68 s i po
końcowym scaleniu zawierał 15 wyborów automatycznych, 11 duplikatów, 27
odrzuconych fragmentów przejścia oraz zero elementów review.

Nie wykonano profilu 5000 z ręcznym odbiorem właściciela ani nowego runu 42 403.
Te bramki pozostają w TASK-0197 i są wymagane przed uznaniem v10.8 za
zaakceptowane na całym corpusie.

## Verification

- pełny zestaw workera, wykonany partiami z limitem 120 s: 658 passed,
- pełny zestaw API, wykonany partiami: 327 passed, 23 skipped; pominięcia
  wymagają PostgreSQL albo niedostępnych na tym koncie dowiązań Windows,
- Admin: 194 passed, ESLint i TypeScript typecheck passed,
- OpenAPI oraz wygenerowany klient Admin API: current,
- Ruff dla wszystkich plików zmienionych w commicie: passed,
- mypy dla rdzenia selektora i profilera: passed (5 plików),
- regresje ujawnione przez pełne testy: wymagany `firstSequenceNumber` w fixture
  importu oraz nieaktualny oczekiwany head Alembic zostały poprawione.

Pełny Ruff pozostaje czerwony na sześciu wcześniejszych przekroczeniach E501 w
niezmienionej migracji `0035_symbol_model_training_jobs.py`. Pełne mypy pozostaje
czerwone na dziesięciu wcześniejszych błędach w `candidate_gate.py`,
`production_workflow.py` i `workbench_acceptance.py`; żaden z nich nie leży w
zmienionym obszarze v10.8.
