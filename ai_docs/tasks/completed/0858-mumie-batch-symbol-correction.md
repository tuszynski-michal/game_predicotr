# TASK-0858 — Edycja symboli z partii Mumii

## Status

done

## Goal

Operator wybiera właściwy symbol dla dowolnego z 18 dokładnych wycinków
i zapisuje trwałą korektę bez zmiany poprawnej siatki.

## Context

Dotychczasowa galeria otwierała wyłącznie całe zdjęcie. Te źródła nie są
zarejestrowane w starym katalogu; nie wolno udawać zatwierdzenia całej geometrii.

## Dependencies / entry conditions

TASK-0857 v1.7.203 / 5f5ade74222981f7beab0a3ef34d1bb2a0b336f4.
Istniejące 18 cases, partia V2 oraz zatwierdzony słownik D-498.
Zgoda na samodzielną naprawę i uruchomienie narzędzia; brak pytań blokujących.

## Recommended execution

gpt-6.1-sol, high. Jeden wykonawca i własny audyt; bez delegowania.
Drift danych lub brak zatwierdzonego słownika zatrzymuje publikację referencji.

## Relevant docs

- AGENTS.md; ai_docs/README.md; ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md; ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md; ai_docs/process/DECISION_LOG.md (D-501)
- ai_docs/requirements/VISION_LAB.md; ai_docs/architecture/VISION_LAB.md
- ai_docs/delivery/VISION_LAB_SYMBOL_LABELS_CONTRACT.md
- ai_docs/delivery/MUMIE_BATCH_SYMBOL_CORRECTION_20261005.md

## Scope

Pakiet referencji, oddzielne decyzje crop-review, addytywne istniejące API,
generowany klient, edytor i trwały launcher; kontrolowany restart lab.

## Out of scope

DB, migracje, stare etykiety/geometrie, sekwencje, supersymbol, nowe klasy,
trening, kwalifikacja nowych danych, aktywacja, merge/push/produkcja.

## Acceptance criteria

- [x] Kliknięcie wycinka wybiera go; paleta i jawny zapis działają od otwarcia.
- [x] Wyświetlane PNG odpowiadają dokładnym RGB96 pikselom partii.
- [x] Decyzja wiąże referencję i wycinek; istniejące klasy zachowują ID.
- [x] CAS, identyczny retry, historia i restart działają na izolowanych danych.
- [x] Drift i błędna klasa/binding blokują zapis; stary store pozostaje bez zmian.
- [x] API/OpenAPI/klient/wrapper/test są zgodne; domyślne zachowanie bez zmian.
- [x] UI zachowuje PNG po zapisie, pokazuje potwierdzenie i chroni pending.
- [x] Realny edytor udostępnia 18 przypadków bez etykiet stworzonych przez agenta.
- [x] Dokumentacja, audyt, osobny commit, Outcome i CURRENT_STATE są uzupełnione.

## Technical notes

Szczegółowy przepływ, walidacja i granice: zaakceptowany plan wskazany wyżej.
Pochodzenie batch_crop_review nie jest akceptacją całej planszy. Zawsze
trainable=false. Źródła są sprawdzane przed odczytem pikseli.

## Expected files

Istniejące: symbol_contracts.py, symbol_store.py, symbol_api.py, api.py,
__main__.py; generowany klient i wrapper; vision_lab_symbol_review.ps1.
Proponowane: symbol_batch_labels.py, jego testy, komponent i strona
/symbols/batch, test workflow; dokumentacja i raport jakości TASK-0858.

## Test cases

Kliknięcie i wybór nie zapisują automatycznie. Zapis dokładnego bindingu;
restart i utracona odpowiedź zwracają jeden receipt, konflikt nie publikuje
drugiej decyzji. Zmiana źródła/PNG/słownika oraz błędna klasa blokują.
Oryginalny store i stare payloady pozostają zgodne.

## Verification

Komendy przez istniejący artifacts/grid-v3-deployment-20261004/run_step.py,
timeout 120 s dla testów/lint/typecheck; kontrolowany build osobno do 300 s.
Python .venv/Scripts/python.exe -m pytest services/worker/tests/test_vision_lab_symbol_batch_labels.py
oraz istniejące testy API/store. Node npm-cli run test/lint/typecheck/build
--workspace @game-predictor/vision-lab; klient generate/check:generated/test/typecheck.
Każda komenda osobno. Wyniki są planowane, nie wykonane.

## Risks / open questions

Nowe etykiety nie są jeszcze próbkami do treningu. Prawdziwe klasy wybiera
operator. Utrata odpowiedzi zachowuje exact retry; nie ma automatycznej zgody.

## Outcome

### Changed

- Exact RGB96 immutable reference and separate batch_crop_review decisions.
- Additive existing API/OpenAPI/client, real editor, palette, shortcuts,
  receipt-confirmed frozen PNGs, mobile/desktop layout and persistent launcher.
- Diagnostic gallery now links exact editable cases; original page retained.
- Commit: `v1.7.204`.

### Verification results

- Backend 56, UI 62, client 15 tests passed. Strict targeted mypy, Ruff,
  generated/OpenAPI drift, lint/typecheck and final build passed.
- Fresh subprocess, lost response, CAS, invalid inputs and atomic-write fault
  verified on isolated fixtures. No human labels written to real cases.
- Live API/proxy verified all 18 PNG byte/pixel SHAs in 0.203/0.172 seconds.
- Owned API/UI restarted from saved config; original stores SHA unchanged.
- Browser click selects the crop, palette enables save, explicit reread clears
  the unsaved choice. Mobile 390×844 has no overflow and 44px buttons.
- Every acceptance criterion and scoped plan point audited; report:
  ai_docs/quality/MUMIE_BATCH_SYMBOL_CORRECTION_20261005.md.

### Not completed

- Real symbol assignments require the operator. New crop reviews remain
  trainable=false. No DB, migration, training, model activation, merge/push
  or production deployment performed.

### Documentation updates

- D-501, requirements, architecture, symbol contract, scoped plan,
  quality report and CURRENT_STATE updated; completed task archived.

### Recommended next task

- Operator labels the 18 crops in http://127.0.0.1:3102/symbols/batch.
  Then qualify/evaluate the new review evidence in a separate scoped task.
