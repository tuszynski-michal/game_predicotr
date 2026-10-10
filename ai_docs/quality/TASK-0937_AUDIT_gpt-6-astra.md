# Audyt TASK-0937 - Pilot wykrywania złotej ramki super symbolu

Werdykt: REVISE
Audytor: Codex, etykieta briefu: gpt-6-astra / medium
Wykonawca: claude-sonnet-5-5 / medium (według zadania)
Zakres: HEAD...8629be40e01d49a230ec703d27b89057d37d6d73 oraz zmiany niezacommitowane w czterech plikach wskazanych w briefie, data 2026-10-09
Runda: 1

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano skrypt, sześć testów syntetycznych, szkic raportu oraz zgodność z zadaniem i właściwymi fragmentami planu. Odczyt bazy jest zabezpieczony transakcją tylko do odczytu, ale pomiar nie spełnia pierwszego kryterium akceptacji. Dodatkowo wspólna etykieta dwóch wycinków nie pozwala jednoznacznie ustalić widoczności ramki w V3, a ponowne przygotowanie tego samego przebiegu nadpisuje ręczne etykiety.

## Znaleziska

### P0

- [P0-1] `ai_docs/quality/MUMIE_GOLD_FRAME_PILOT_20261009.md:15` — Raport zawiera 50 komórek, lecz zero etykiet, zero komórek z serii oraz brak końcowej decyzji. Nie spełnia wymogu co najmniej 30 ręcznie oznaczonych komórek i raportu z liczbami oraz decyzją „dalej / nie”. Należy uzyskać wymaganą próbę po spełnieniu warunku pięciu serii, zebrać etykiety operatora i uzupełnić wynik. Do tego czasu zadanie pozostaje nieukończone.

- [P0-2] `scripts/m8_gold_frame_pilot.py:454` — Arkusz pokazuje wycinek `tight` i `margin`, lecz udostępnia jeden zestaw przycisków i jedną etykietę `frame_label`. Pytanie w linii 479 nie określa, którego obrazu dotyczy odpowiedź. Gdy ramka jest widoczna wyłącznie w wariancie z marginesem, zapis „tak” nie mówi, czy obejmuje ją V3. Raport stosuje tę samą etykietę do obu wariantów, więc nie odpowiada jednoznacznie na główne pytanie pilota. Należy rozdzielić ocenę obecności ramki od jej widoczności w poszczególnych wycinkach i odpowiednio raportować wyniki.

- [P0-3] `scripts/m8_gold_frame_pilot.py:593` — Ponowne `--prepare` z tą samą wartością `--run` otwiera istniejący `labels.csv` w trybie zapisu i zastępuje ręczne etykiety pustymi wartościami. Nie ma zabezpieczenia istniejącego przebiegu; wcześniej nadpisywane są również obrazy. Może to utracić pracę operatora albo rozłączyć etykiety z ocenianymi obrazami. Należy odrzucać istniejący katalog przebiegu przed pierwszym zapisem lub tworzyć nowy, jednoznacznie nazwany przebieg.

### P1

- [P1-1] `ai_docs/tasks/0937-gold-frame-detection-pilot.md:127` — Outcome jawnie pomija aktualizację `CURRENT_STATE.md`, mimo wykonania narzędzia i ujawnienia blokady pomiaru. Brak decyzji domenowej nie zwalnia z aktualizacji stanu prac wymaganej przez AGENTS.md i Definition of Done. Należy zapisać wykonany zakres, wyniki kontroli i oczekiwanie na właściwą próbę oraz etykiety; status taska powinien odzwierciedlać rozpoczętą, zablokowaną pracę.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Co najmniej 30 komórek z ręcznymi etykietami oraz raport z liczbami i decyzją „dalej / nie” | niespełnione | `ai_docs/quality/MUMIE_GOLD_FRAME_PILOT_20261009.md:15` — zero etykiet; rekomendacja pozostaje pusta |
| Skrypt uruchamialny ponownie bez zapisu do bazy | spełnione | `scripts/m8_gold_frame_pilot.py:326` — `REPEATABLE READ` i `postgresql_readonly=True`; ocena statyczna. Utrata lokalnych etykiet jest osobnym problemem P0-3 |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P0-1, P0-2, P0-3, P1-1.

## Proponowane testy

W `services/worker/tests/test_m8_gold_frame_pilot.py` należy dodać:

- Przypadek ramki widocznej tylko w wycinku z marginesem, sprawdzający niezależne etykiety i wynik raportu.
- Ponowne przygotowanie istniejącego przebiegu z ręcznymi etykietami, sprawdzające odmowę zapisu i zachowanie plików.
- Test przepływu arkusz → eksport CSV → ewaluacja; obecny test tworzy CSV bezpośrednio w Pythonie.

Komenda po dodaniu testów: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_m8_gold_frame_pilot.py`, z limitem 120 sekund.

Pomiar akceptacyjny wymaga osobno rzeczywistych etykiet operatora na poprawnej próbie; testy syntetyczne go nie zastępują.

## Zakres przeglądu i ograniczenia

Przeczytano brief, cztery pliki objęte audytem, indeks dokumentacji, właściwe fragmenty bieżącego stanu i planów oraz Definition of Done. Sprawdzono również powiązane fragmenty implementacji serii i renderowania.

Nie uruchamiano testów, skryptu pomiarowego, usług ani zapytań do bazy. Wyniki sześciu testów, lintowania i kontroli typów są deklaracjami wykonawcy z Outcome, nie wynikami odtworzonymi podczas audytu. Nie oceniano wizualnie rzeczywistych wycinków ani jakości przyszłych etykiet operatora.

## Nota leada po rundzie 1 (2026-10-09)

P0-2, P0-3 i grupa kontrolna spoza serii naprawione (osobne etykiety dla wycinku ciasnego i z marginesem, odmowa nadpisania istniejącego przebiegu, trzy grupy próby; 8 testów PASS). P0-1 jest blokadą zewnętrzną: pomiar wymaga etykiet operatora, więc task pozostaje `blocked`, narzędzie zacommitowane. P1-1: sekcja w `CURRENT_STATE.md` dodana po zamknięciu TASK-0938, który w tym czasie przebudowuje ten plik.
