# TASK-0618 — Bramka importu V1.2 i cięcie po siatce symboli

## Status

`done`

## Goal

Ukończony, zgodny preflight V1.2 bez nierozstrzygniętych źródeł uruchamia istniejący import, który wycina pola według przypiętych `symbolGridQuads`.

## Dependencies / entry conditions

TASK-0616 i TASK-0617 ukończone. V1.2 pozostaje jawnym wyborem, V1.1 domyślnym.

## Recommended execution

`gpt-5.6-terra`, `high`; spójność API, manifestu i workera wymaga kontroli całego pionu. Bez dodatkowego review zgodnie z zatwierdzonym planem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`

## Scope

- Import przeglądarkowy V1.2 po ukończonym preflighcie; jawna kontrola zgodności manifestu, wariantu i źródeł.
- Worker używa siatki symboli jako geometrii wycinka i ramki tylko jako dowodu lokalizacji/kontroli.
- Koncentrowane testy bramki, częściowej ostatniej strony, retry i regresji V1.1.

## Out of scope

- V2.0/V2.1, klasyfikacja symboli, historyczne joby i wizualny odbiór dokładności.

## Acceptance criteria

- [x] Brak geometrii lub nierozstrzygnięte zdjęcie blokuje start importu V1.2.
- [x] Nowy kompletny preflight pozwala uruchomić import, a preflight nie tworzy wycinków.
- [x] Import tnie po `symbolGridQuads`, z zachowaniem ostatniej strony i kwalifikacji pól.
- [x] Ponowienie tego samego startu jest deterministyczne; V1.1 pozostaje bez zmian.

## Test cases

- Preflight z `review_required` → konflikt; po korekcie i nowym preflighcie → import.
- Manifest V1.2 z błędną parą ramka/siatka, brakującym źródłem lub innym wariantem → odmowa.
- Siatka różna od ramki → geometria 15 pól pochodzi z siatki.
- Ostatnia strona z mniej niż 9 plansz; retry i regresja V1.1.

## Outcome

### Changed

- API sprawdza ukończony preflight, zgodny manifest i wszystkie pary geometrii V1.2 przed startem; odpowiedź joba ujawnia przypięty wariant.
- Worker waliduje źródłowe wymiary, ramkę i siatkę, a 3 × 5 pól wyprowadza z wewnętrznej siatki. Nie używa czerwonego pokrycia ani fallbacku V1.1.
- Admin odblokowuje istniejący Import dopiero dla gotowego raportu. OpenAPI i klient wygenerowano z backendu.

### Verification results

- Testy API: 4 skoncentrowane (V1.2, idempotentny start i regresja historyczna) przeszły; test uszkodzonego lub nierozstrzygniętego manifestu odrzuca import.
- Testy workera: 9 skoncentrowanych przeszło; pełna i ostatnia strona dały odpowiednio 9/5 plansz oraz po 15 pól z `symbolGridQuads`.
- Ruff, format, typecheck Admina i klienta, zgodność OpenAPI i generatora oraz lint zmienionego panelu przeszły. Lint panelu pozostawia istniejące ostrzeżenie o `<img>`.
- Audyt własny wykrył i naprawił błędną idempotencję drugiego startu oraz brak porównania wymiarów i ścieżki źródła.

### Not completed

- Dokładny odbiór na czterech zdjęciach Mumii należy do TASK-0619. Managed reprocess V1.2 nie jest częścią przeglądarkowego przebiegu i pozostaje zamknięty.

### Documentation updates

- `IMAGE_INGESTION.md`, `ITERATIVE_IMAGE_IMPORT.md` i `CURRENT_STATE.md`.

### Recommended next task

- TASK-0619 — skoncentrowany odbiór techniczny na Mumii, audyt i decyzja operatorska o dokładności.
