# TASK-0470 — Obie granice i obowiązkowa korekta
## Status
done
## Relevant docs
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/quality/SELECTED_CROP_V11_REGRESSIONS.md`
## Dependencies / goal
0469. Pas z całego układu i numerów albo pełny obraz z obowiązkową korektą.
## Scope / expected files
auto-crop-v11-boundaries, kontrakt propozycji, crop-session, storage i workspace.
## DoD / tests
Ekstrema plus bufor 15% i błąd lokalizacji; brak numerów wymaga korekty.
Odznaczenie nie zamyka korekty. Reload zachowuje obowiązek. Ręczny zapis
lub jawna akceptacja zamyka go. Testy core i Admin typecheck.
## Outcome
Dodano ekstrema plansz/numerów, bufor 15% + 2 px analizy, strukturalne pasy
numerów bez OCR, pełny obraz przy niepewności. Obowiązek korekty jest wyprowadzany
z utrwalonego dowodu i decyzji ręcznych, niezależnie od zaznaczeń. UI pokazuje
powód, nie procent; zakończenie review sprawdza także obowiązkową kolejkę.
69 testów core OK, typecheck core/Admin OK. Stary v10 i źródła bez zmian.
Integracja wyboru/przekazania polityki i runnera: 0471.
