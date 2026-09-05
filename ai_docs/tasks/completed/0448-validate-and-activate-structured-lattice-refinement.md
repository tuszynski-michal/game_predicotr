---
title: Validate and activate structured lattice refinement
status: in_progress
last_updated: 2026-09-04
---

# TASK-0448 — Odbiór i bezpieczna aktywacja

## Status

`done`

## Goal

Zweryfikować refiner v3 na rzeczywistych, source-disjoint ręcznych korektach i
udostępnić go dla nowych runów wyłącznie po przejściu wszystkich bramek jakości.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0445-separate-board-frame-and-symbol-lattice.md`
- `ai_docs/tasks/completed/0446-refine-structured-symbol-lattices.md`
- `ai_docs/tasks/completed/0447-shadow-structured-lattice-refinement.md`

## Scope

- deterministyczny odbiór na 450 bieżących ręcznych siatkach 3×5;
- golden regressions dla zakresów `19999–20007` i `20026–20034`;
- raport pokrycia, błędu narożników, content safety i niezmienników;
- jawnie wersjonowana aktywacja v3 wyłącznie dla nowych runów;
- zachowanie replayu v1/v2 oraz brak zmian istniejących cropów i decyzji;
- dokumentacja jakości, wymagań, architektury i obsługi operatora.

## Out of scope

- automatyczne przeliczanie istniejących importów;
- zmiana ręcznie zatwierdzonych geometrii;
- nowy model ML lub inna topologia niż 3×5;
- operacje na danych gry bez jawnej decyzji operatora.

## Acceptance criteria

- [x] co najmniej 98% plansz otrzymuje bezpieczną siatkę;
- [x] mediana błędu narożników nie przekracza 3,0 px, a board-level p90 4,5 px;
- [x] zaakceptowane wyniki mają zero przecięć chronionej zawartości;
- [x] zero naruszeń row-major, overlapu i source support;
- [x] spadek pokrycia względem stabilnego baseline'u nie przekracza 0,5 pp;
- [x] niepewne wyniki pozostają fail-closed bez fallbacku do ramki;
- [x] golden regressions są częścią automatycznego testu;
- [x] operator może jawnie wybrać v3 dla nowych runów dopiero po poprawnym raporcie;
- [x] historyczne snapshoty i retry v1/v2 pozostają niezmienne.

## Verification

Skoncentrowane testy domeny, API, workera i Admina; bounded pomiar na 450
rzeczywistych planszach; Ruff, mypy zmienionych modułów, lint, typecheck,
OpenAPI oraz build zmienionych aplikacji.

## Outcome

### Result

- Raport `structured-lattice-v3-real-manual-acceptance-v1` objął dokładnie 450
  bieżących ręcznych geometrii z 50 source-disjoint zdjęć i dwóch gier.
- V3 oszacował 443/450 plansz (`98,4444%`), przy baseline 445/450; spadek
  wyniósł `0,4445 pp`. Pozostałe siedem plansz zostało bezpiecznie odroczonych:
  pięć z niewystarczającym pokryciem inlierów i dwie z konfliktem granicy
  zawartości.
- Mediana wszystkich błędów narożników wyniosła `2,4608 px`; p90 średniego
  błędu czterech narożników planszy wyniosło `3,735 px`. Diagnostyczne p90
  pojedynczych narożników wyniosło `4,7004 px` i nie jest metryką aktywacyjnego
  board-level gate.
- Nie wykryto naruszeń row-major, overlapu, source support ani zaakceptowanego
  przecięcia chronionego komponentu. Oba golden cases `19999–20007` i
  `20026–20034` przeszły zgodnie z zapisanym oczekiwaniem.
- Raport ma SHA-256
  `6aeffdc182f04183fd0ae0f96721248531787169ff146aedfe5f2c29ee81a34c`;
  ta wartość jest częścią accepted-primary configu i snapshotu nowych jobów.

### Implementation

- Dodano jawną politykę gry `structured_lattice_v3`, snapshot rollout schema v3
  oraz fail-closed kontrolę driftu konfiguracji i raportu.
- Worker używa `symbolGridQuad` jako jedynego źródła wirtualnych cropów. Brak
  dowodu zachowuje `finalQuad = null`; zewnętrzna ramka nie jest fallbackiem.
- Admin pozwala jawnie wybrać v3 dla nowych runów i rozróżnia stabilny v2.
  Istniejące joby, cropy, ręczne decyzje i replay snapshotów v1/v2 nie zostały
  zmienione.
- Dodano migrację `0095_structured_lattice_v3_rollout`; nie uruchomiono jej na
  bazie użytkownika.

### Verification

- `pytest` skoncentrowany na API, workerze, snapshotach, migracji i produkcyjnym
  renderze: `120 passed`.
- pełny zestaw Admina: `396 passed`.
- Ruff dla zmienionych modułów: passed.
- Admin ESLint, TypeScript, OpenAPI check, generated-client check i produkcyjny
  build: passed.
- Pełny mypy repozytorium ujawnił trzy wcześniejsze błędy poza zakresem w
  `schemas/image_reviews.py`, `storage/virtual_grid_geometry_repository.py` i
  istniejącym `Literal[0.98]` w `schemas/jobs.py`; zmienione moduły v3 nie
  dodały nowego błędu.
- Globalny Prettier nadal zgłasza pięć wcześniejszych plików poza zakresem:
  `next-env.d.ts`, cleanup control, manual repair workspace, symbol review
  workspace i jego test stylu. Pliki zmienione w tym tasku są sformatowane.

### Operational note

Przed wyborem v3 operator musi wykonać `npm run db:migrate` i zrestartować API,
workera oraz Admina. Sam commit nie zmienia polityki żadnej gry i nie uruchamia
reprocessu istniejących importów.
