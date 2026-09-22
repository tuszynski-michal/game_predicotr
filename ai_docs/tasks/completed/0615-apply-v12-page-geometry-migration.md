---
title: Apply V1.2 page-geometry schema migration
status: done
---

# TASK-0615 — Uzupełnienie schematu bazy dla V1.2 geometrii

## Status

`done`

## Goal

Uzupełnić addytywną migrację V1.2 o magazyn `game_data_v2`, aby lista ręcznej
korekty geometrii mogła odczytywać bieżące override'y bez błędu 500.

## Context

Preflight stagingu `a139379b-fa15-42c5-a3f3-1ae85152723d` jest poprawny: ma
448 zarejestrowanych zdjęć i 2504 pozycje `review_required`. Endpoint listy
zwracał 500, ponieważ model danych oczekuje `board_frame_quads` i
`symbol_grid_quads` w `game_data_v2.image_page_geometry_overrides`.

Migracja `0118_v12_page_frame_grid_pairs` została zastosowana, ale dotknęła
tylko legacy tabeli `public`. Magazyn aktywnej gry jest routowany do
`game_data_v2`, więc potrzebna jest kolejna, addytywna migracja dla
partitioned parent tej samej tabeli. Nie zmieniamy już zastosowanej migracji
0118 ani danych stagingu.

## Dependencies / entry conditions

- Lokalna baza PostgreSQL jest dostępna.
- `alembic current` wskazuje `0118_v12_page_frame_grid_pairs`.
- Endpoint potwierdza brak kolumn w `game_data_v2`, a nie błędny manifest lub
  niepoprawne dane zdjęć.

## Recommended execution

gpt-5.6-terra / high. Zadanie dodaje małą, addytywną migrację dla istniejącej
ścieżki game-data v2 i sprawdza rzeczywisty endpoint. Ograniczenie: nie wolno
modyfikować stagingu ani wykonywać backfillu. Końcowy review: gpt-6-astra /
medium.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`

## Scope

- Dodać następną migrację Alembic, która dodaje nullable kolumny i constraint
  pary wyłącznie do `game_data_v2.image_page_geometry_overrides`.
- Zastosować `alembic upgrade head` dla lokalnej bazy.
- Potwierdzić bieżącą rewizję oraz odpowiedź listy korekt dla stagingu `a139379b`.
- Udokumentować wynik operacyjny.

## Out of scope

- Zmiana obrazów, manifestu, preflightu, importu i jobów.
- Zmiana kodu V1.1/V1.2 lub V2 poza naprawą migracji V1.2.
- Backfill, zmiana obrazów lub rekordów domenowych.

## Acceptance criteria

- [x] Baza wskazuje nową rewizję po `0118_v12_page_frame_grid_pairs`.
- [x] `game_data_v2.image_page_geometry_overrides` zawiera obie kolumny V1.2.
- [x] Endpoint listy korekt stagingu `a139379b` zwraca HTTP 200.
- [x] Liczniki stagingu i manifest nie są zmienione.

## Technical notes

Migracja dodaje tylko nullable kolumny potrzebne do przechowania osobnej ramki
planszy i siatki symboli V1.2 oraz constraint wymagający obu albo żadnej. Musi
jednoznacznie wskazywać schema `game_data_v2`, aby nie polegać na bieżącym
`search_path`. `ALTER TABLE` parenta propaguje kolumny do jego partycji gier.
Jest transakcyjna. Endpoint ma nadal zwracać wszystkie istniejące pozycje
`review_required`; jego powodzenie nie oznacza automatycznej akceptacji ani
przetworzenia żadnego zdjęcia.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

Następnie odczyt właściwego endpointu musi zwrócić HTTP 200 i niezmienione
liczniki 448 zarejestrowanych oraz 2504 wymagających korekty.

## Outcome

Dodano migrację `0119_v12_game_data_v2_page_frame_grid_pairs`. Naprawia ona
zakres wcześniejszej migracji 0118: dodaje nullable `board_frame_quads` i
`symbol_grid_quads` oraz constraint pary do aktywnego, per-game magazynu
`game_data_v2.image_page_geometry_overrides`. Nie zmienia migracji 0118,
stagingu, manifestu, joba, importu ani plików obrazów.

`alembic upgrade head` zastosował 0119, a `alembic current` potwierdza
`0119_v12_game_data_v2_page_frame_grid_pairs (head)`. Odczyt schematu
potwierdził obie kolumny w `game_data_v2`. Rzeczywisty endpoint listy korekt
dla `a139379b` zwraca teraz HTTP 200; manifest pozostaje
`a978227dba82d9df73dff7c6c7cfbabb58dde9e9528ed4ae3fa3b8eb275965ed`, z 448
zarejestrowanymi i 2504 `review_required`.

Przeszły: `pytest services/api/tests/test_migration_baseline.py -q` (66
testów), Ruff check oraz Ruff format check dla migracji i testu. Test
regresji sprawdza oba magazyny V1.2, brak modyfikacji danych podczas upgrade i
ochronę downgrade'u przed utratą par już zapisanych przez V1.2. Astra Medium
znalazła P2 w pierwszej wersji downgrade'u: zapis mógł wejść między kontrolę
danych a usunięcie kolumn. Poprawiono to blokadą `ACCESS EXCLUSIVE` parenta i
partycji przed kontrolą; końcowy re-audyt Astra nie wykazał P0–P3.

Nie wykonywano ręcznej korekty ani automatycznego importu. Liczba 2504 jest
stanem preflightu, który operator może teraz otworzyć; nie jest skutkiem tej
usterki ani sygnałem, że dane zostały zmienione.
