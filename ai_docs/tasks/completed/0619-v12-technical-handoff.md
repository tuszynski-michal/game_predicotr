# TASK-0619 — Odbiór techniczny V1.2 na Mumii

## Status

`done`

## Goal

Sprawdzić gotowość techniczną przebiegu V1.2 i stan czterech rzeczywistych źródeł Mumii, po czym przekazać operatorowi konkretne warunki odbioru wizualnego.

## Dependencies / entry conditions

TASK-0618 ukończony. Cztery źródła `seq_1-9.jpg`, `seq_10-18.jpg`, `seq_19-27.jpg`, `seq_28-36.jpg` znajdują się w lokalnym katalogu Mumii. Nie przypisujemy historycznej pojedynczej geometrii V1.1 do pary ramka/siatka V1.2.

## Recommended execution

`gpt-5.6-luna`, `xhigh`; ograniczony audyt, pomiar dostępnych danych i dokumentacja. Bez Astra Medium według zatwierdzonego planu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/quality/V1_2_MUMIE_GEOMETRY_DIAGNOSIS.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- Zweryfikować checksumy czterech źródeł i ostatniego lokalnego manifestu V1.2.
- Odczytać rzeczywiste decyzje preflightu, dostępność profilu i możliwość pokazania par geometrii/importu.
- Wykonać audyt T01–T03, zapisać techniczny raport oraz decyzję o testowym starcie przeglądarkowego importu V1.2.

## Out of scope

- Samodzielne tworzenie ręcznej prawdy dla Mumii, zapisywanie wynikowych JPEG-ów, aktywacja domyślna V1.2, V2.0/V2.1 i klasyfikacja symboli.

## Acceptance criteria

- [x] Cztery źródła i manifest są przypięte sumami i sprawdzone.
- [x] Raport rozróżnia działające testy techniczne od realnego wyniku geometrii.
- [x] Przypadki wymagające korekty mają jednoznaczną listę i instrukcję dla operatora.
- [x] Dokumentacja i decyzja o testowym imporcie są zgodne z rzeczywistą bramką API.

## Test cases

- Brak zatwierdzonej pary ramka/siatka w profilu → `review_required`, brak wycinków i brak importu.
- Potwierdzona para oraz ponowny preflight → procedura umożliwia import dopiero po wyzerowaniu nierozstrzygniętych importowanych źródeł.
- Regresja V1.1 i techniczne cięcie 9/5 plansz po 15 pól pozostają wynikiem skoncentrowanych testów TASK-0618.

## Outcome

### Changed

- Spisano `ai_docs/quality/V1_2_MUMIE_TECHNICAL_HANDOFF.md`, decyzję D-429
  oraz bieżący stan V1.2. Bez zmian kodu, danych gry i JPEG-ów.

### Verification results

- Ponownie obliczono SHA-256 czterech JPEG-ów i manifestu. Sumy odpowiadają
  raportowi; manifest podaje 0 zarejestrowanych i 24 wymagające korekty źródła.
- Audyt porównał T01–T03 z kryteriami planu i wynikami ich skoncentrowanych
  testów. Nie powtarzano testów kodu bez nowych zmian w kodzie. Kontrola diffu
  i zakresu staged przed commitem nie obejmuje niepowiązanych zmian V2.

### Not completed

- Nakładki oraz rzeczywisty import czterech Mumii są `not_evaluable`: profil
  V1.2 ma zero zatwierdzonych próbek, a bramka poprawnie blokuje import.
  Dokładną ocenę wycinków wykonuje operator po ręcznej korekcie i nowym
  preflighcie.

### Documentation updates

- `CURRENT_STATE.md`, D-429 oraz raport odbioru technicznego.

### Recommended next task

- Operator zatwierdza co najmniej jedną pełną parę ramka/siatka Mumii,
  ponawia preflight i rozlicza pozostałe źródła przed wizualnym odbiorem importu.
