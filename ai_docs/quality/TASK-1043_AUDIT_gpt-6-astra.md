# Audyt TASK-1043 - Decyzja D-562, dokumentacja i czyste funkcje kadru

Werdykt: REVISE
Audytor: gpt-6-astra, high
Wykonawca: claude-opus-5-5, high
Zakres: HEAD...c0a538df0c5db2071ff8d24f57e6239930a7366d oraz zmiany niezacommitowane TASK-1043, data 2026-10-17
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono moduł domenowy, testy, dokumentację D-562 oraz zgodność z regułami R2, R6 i R7 planu. Planowanie kadru i mapowanie orientacji odpowiadają opisanym przykładom. Przed commitem wymagają poprawy walidacja i kanonizacja atestu, kod błędu weryfikacji oraz brakujący wymagany test.

## Znaleziska

### P0

- [P0-1] `services/api/src/game_predictor_api/domain/source_crop.py:428` — Walidator atestu sprawdza wyrównanie tylko lewej i górnej krawędzi, a następnie samo zawieranie obszaru chronionego, bez deklarowanego marginesu. Na danych fixture `_attestation` zaakceptuje parę `crop_box=PixelBox(47,160,352,464)` i `raw_crop_box=PixelBox(160,248,464,553)`, mimo niewyrównanej dolnej krawędzi raw, która nie jest brzegiem obrazu. Niezależnie zaakceptuje `protected_box=ProtectedBox(49.0,220.0,300.0,410.0)` przy domyślnym cropie zaczynającym się na 48 i `margin_px=50`. Atest może więc poświadczać geometrię sprzeczną z R6. Należy sprawdzać wszystkie krawędzie iMCU z wyjątkiem granic obrazu oraz zawieranie obwiedni powiększonej o zapisany margines.

- [P0-2] `services/api/src/game_predictor_api/domain/source_crop.py:103` — Kanoniczne bajty atestu nie są stabilne przy round-trip dla całkowitych współrzędnych `ProtectedBox`. Konstruktor dopuszcza `ProtectedBox(100,220,300,410)`, a `as_list()` zachowuje liczby całkowite. Dekoder przez `_number()` zamienia je na `float` (`source_crop.py:693`), więc ponowne kodowanie zapisuje `100.0` zamiast `100` i zmienia obie sumy atestu. Należy normalizować reprezentację liczb przed pierwszym kodowaniem i dodać test identyczności bajtów dla współrzędnych całkowitych oraz mieszanych.

- [P0-3] `services/api/src/game_predictor_api/domain/source_crop.py:429` — Operacja modulo następuje przed walidacją rozmiaru iMCU. `imcu_width=0` lub `imcu_height=0` powoduje `ZeroDivisionError`. Dotyczy to również dekodowania dokumentu z poprawną sumą własną; obsługa w `source_crop.py:579` przechwytuje tylko `SourceCropError`. Nieprawidłowy atest nie otrzymuje zatem stabilnego błędu domenowego. Należy sprawdzić dozwolone wartości iMCU przed obliczeniami i przetestować odrzucenie obu zer przez `SOURCE_CROP_ATTESTATION_INVALID`.

### P1

- [P1-1] `services/api/src/game_predictor_api/domain/source_crop.py:343` — Zbyt mała odległość chronionego obszaru od pasa różnic zwraca `SOURCE_CROP_PROTECTED_TOO_CLOSE`. Plan R7 wymaga `SOURCE_CROP_VERIFICATION_FAILED` dla niespełnienia każdego warunku weryfikacji (`ai_docs/delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md:266`). Test w `services/api/tests/test_source_crop.py:213` utrwala rozbieżny kontrakt. Należy zwracać wymagany kod, pozostawiając szczegółowy powód w diagnostyce, i poprawić asercję.

- [P1-2] `services/api/tests/test_source_crop.py:43` — Zestaw testów nie obejmuje JPEG progresywnego, którego plan R6 jawnie wymaga jako przykładu testowego (`ai_docs/delivery/PHOTO_CROP_STORAGE_EXECUTION_PLAN_20261017.md:247`). Obecne testy operują na punktach i tablicach RGB. Należy dodać przypadek progresywnego JPEG, np. przygotowanego w pamięci przez Pillow, sprawdzający planowanie kadru na podstawie jego wymiarów i próbkowania, bez uruchamiania `jpegtran`.

### P2

Brak.

## Pokrycie kryteriów akceptacji

Status „spełnione” oznacza zgodność ustaloną statycznie, bez uruchamiania testów.

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Przykład P1 daje `[32,0,784,480]` | spełnione | `services/api/tests/test_source_crop.py:43`; `services/api/src/game_predictor_api/domain/source_crop.py:233` |
| Orientacje 6 i 3 z offsetem; odrzucenie 2/4/5/7 | spełnione | `services/api/tests/test_source_crop.py:57`; `services/api/tests/test_source_crop.py:105` |
| Kadr zawiera bbox z marginesem albo dochodzi do brzegu | niespełnione | Planowanie realizuje regułę w `services/api/src/game_predictor_api/domain/source_crop.py:250`, lecz walidacja atestu jej nie egzekwuje — P0-1 |
| Różnice tylko w pasie 1 px, przy zachowaniu odległości 8 px | spełnione | `services/api/src/game_predictor_api/domain/source_crop.py:327`; testy od `services/api/tests/test_source_crop.py:151`; rozbieżny kod błędu opisuje P1-1 |
| Round-trip atestu i odrzucanie zmienionej treści lub sumy | niespełnione | Kontrola sumy istnieje w `services/api/src/game_predictor_api/domain/source_crop.py:505`; P0-2 narusza stabilność round-trip, P0-3 obsługę błędnego dokumentu |
| Ruff, strict mypy, focused pytest i docs:check przechodzą | niezweryfikowane | Wyniki deklarowane w `ai_docs/tasks/1043-source-crop-decision-and-region.md:120`; mypy ma opisane wcześniejsze błędy poza zakresem. Audyt nie uruchamiał kontroli |

## Listy zamknięte i otwarte

Zamknięte: Brak. Pierwsza runda audytu.

Otwarte: P0-1, P0-2, P0-3, P1-1, P1-2.

## Proponowane testy

W `services/api/tests/test_source_crop.py` należy dodać:

- Odrzucenie niewyrównanej prawej i dolnej krawędzi atestu oraz akceptację krawędzi dochodzących do granicy obrazu.
- Odrzucenie atestu z niewystarczającym deklarowanym marginesem.
- Identyczność bajtów i sum po round-trip dla całkowitych oraz mieszanych współrzędnych `ProtectedBox`.
- Stabilny błąd dekodowania poprawnie checksummowanego dokumentu z zerowym wymiarem iMCU.
- Wymagany kod błędu przy quadzie zbyt blisko pasa różnic.
- Przypadek JPEG progresywnego wymagany przez R6.

Komenda po poprawkach: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/test_source_crop.py`, z limitem 120 s.

## Zakres przeglądu i ograniczenia

Przeczytano brief, dokumenty startowe, aktywny task, odpowiednie fragmenty planu, wymagania Discovery i Normalizacja, fragmenty architektury i modelu danych, wpis D-562, cały nowy moduł oraz cały plik testów. Sprawdzono także diff indeksu decyzji i obecność modułu w mapie kodu.

Nie uruchamiano testów, narzędzi jakości, `jpegtran`, usług ani operacji na danych. Przykłady błędów wynikają z analizy przepływu kodu; nie wykonywano ich. Wyniki kontroli zapisane w `Outcome` pozostają deklaracją wykonawcy. Loadery, joby, migracje, API i UI pozostają poza zakresem tego audytu.