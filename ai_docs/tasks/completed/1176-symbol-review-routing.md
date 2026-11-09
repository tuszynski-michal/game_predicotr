---
title: TASK-1176 — Istniejące siatki do weryfikacji symboli
status: done
last_updated: 2026-11-09
---

# TASK-1176 — Istniejące siatki do weryfikacji symboli

## Status

`done`

## Goal

Spiąć nowe importy i wznowienie zaległej partii z istniejącym rendererem
i klasyfikatorem: symbole pending, bez zatwierdzeń człowieka. Kod podlega
odbiorowi przed osobną integracją i uruchomieniem operacji na danych operatora.

## Context

Operator zlecił domknięcie, wykluczył nowy trener/panel i zbędne prace.
Pierwotny limit15min został wycofany przez operatora: „dokończ w dowolnym
limicie”. Zgoda obejmuje konieczne domknięcie i audyt, bez zbędnego zakresu.
Bez deklaracji ukończenia przed testami.
Main94c5bc6d. Staging691:6219 pending, obecne ręczne korekty chronione.

## Relevant docs

ai_docs/requirements/IMAGE_INGESTION.md (D-484/550/584),
ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md,
ai_docs/process/CROSS_AUDIT.md, ai_docs/process/DEFINITION_OF_DONE.md.

## Scope / decyzja operatora

Wersjonowane dopuszczenie propozycji do ludzkiej weryfikacji symboli jest
odrębne od kwalifikacji automatu. Zachowuje stan niekwalifikowany modelu;
nie tworzy ludzkiej geometrii, nie kwalifikuje treningu i nie zatwierdza klas.
Stare piny/polityki nie zmieniają interpretacji. Kontrole tożsamości,
sekwencji, fizycznych pikseli i poprawności topologii pozostają.
Wykorzystać istniejący zapis automatic=True i istniejący proces reinferencji.
Brak wdrożenia modelu, nowego trenera i obniżania bramek akceptacji automatu.

## Expected files / Technical notes

domain/neural_grid_operation_pin.py: nowy pinv4 dla celu symbol-review;
domain/v3_engine_acceptance.py i neural_crop_policy.py: jawna nowa polityka
przetwarzania propozycji, stare reguły bez zmian. storage kwalifikacji,
job_repository i virtual_grid_geometry_repository: walidacja pinu i tożsamości;
worker neural_pending_geometry: spójne przyjęcie dla tego samego celu.
storage/grid_reinference.prepare wybiera politykę na podstawie wersji pinu;
zakwalifikowany pinv3 zachowuje kalibracjęv4, tylko pinv4 używa review.
API/OpenAPI/SDK zgodne; bez migracji schematu. Szczegółowy raport po testach.

## Acceptance criteria / Verification

- [x] Niekwalifikowany automat dostarcza pending symbole, nie human GT.
- [x] Stare piny i bramki automatu pozostają zgodne.
- [x] Zła topologia/pochodzenie/piksele nie przechodzą.
- [x] Testy zmienionego pionu i Opus PASS przed commitem; zastane błędy z baseline jawne.
- [x] Odczytowo sprawdzono rzeczywistą partię i produkcyjne wycinki. Gotowość
  uruchomionej wersji oraz całej partii potwierdzi dopiero odbiór po scaleniu;
  nie deklarowano ukończonego przetworzenia6219.

## Outcome

Commit: v1.7.591 / `ccedfdbe2c7ffba3844e580c7fdd2fed8a77fd90`.

Implementacja odebrana przed integracją; bez wdrożenia i zapisów operatora.
Nowe pinyv4 oznaczają cel ludzkiej weryfikacji symboli; automat pozostaje
niekwalifikowany. Nowe importy, które nie mają kwalifikacji automatu,
przekazują wykonalne siatki dalej. Reinferencja deferred korzysta z istniejącego
renderera full-cell-v2 i klasyfikatora oryginalnego importu; ręczne pola
approval pozostają puste. Historia, własność, topologia i fizyczne piksele
zachowują kontrole. Nie powstał nowy trener ani panel.

Weryfikacja:117 API/worker PASS;3 PostgreSQL PASS z realnym zapisem,
LocalJobWorker i replay w nowym interpreterze;163 klienta/build PASS,
typecheck klienta PASS. Scoped mypy10 modułów: jeden zastany błąd w _current_row,
ten sam co TASK-1175; bez osłabiania globalnej konfiguracji. Historyczne
44 PASS/2 zastane FAIL potwierdzone baseline, poza zakresem naprawy.
Cały istniejący moduł PG reinferencji:21 PASS/2 zastane FAIL, potwierdzone
baseline. Moduł propozycji:13 zastanych FAIL także na main (fixture tabel).
Opus R1 REVISE P0-1/P1-1: polityka wyznaczana z pinu, mismatch odrzucany;
R2 przez terminal: PASS,0 otwartych P0/P1. P2-5 przyjęte jako obronne ryzyko:
produkcja tworzy review pin wyłącznie dla unqualified automatu, ale sam
konstruktor nie zabrania przyszłemu wywołującemu połączenia v4+qualified.
P2-6 przyjęte: istniejący moduł porównuje politykę do operacji; osobny test
kalibrowanego pinu i testy review zapewniają dodatkowe pokrycie. Bez dalszej
rundy zmian po zaakceptowanym R2. Raport i receipt:
ai_docs/quality/TASK-1176_AUDIT_claude-opus-5-5.md. R1 również zachowany.
Pełny zapis wyników i ograniczeń: ai_docs/quality/TASK-1176_VERIFICATION.md,
odpowiedź na audyt: ai_docs/quality/TASK-1176_AUDIT_FIXES.md.

Odczytowy preview691 zdjęć:6219 strukturalnie renderowalnych propozycji.
Rzeczywisty klasyfikator na jednym zdjęciu:135 predykcji/9 plansz, padding0%,
bez zapisu i bez deklaracji jakości. Zaległe6219 nie są jeszcze przetworzone.
Operator zatwierdził dokończenie całości z audytami i wszystkie pozostałe
operacje tego zadania; wyłączył scalenie do czasu końcowego pytania.
Restart API/general workera oraz przetworzenie zaległej partii są zatwierdzone,
ale zależą od osobnej zgody na merge. Brak migracji. Po scaleniu nowa operacja
obejmie tylko import bf601495, z kontrolą wyników i zachowaniem ręcznych zmian.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1176 — Domknięcie kolejki symboli | gpt-6.1-sol | high | Spójność istniejących zapisów i pochodzenia | Claude Code claude-opus-5-5/high |
