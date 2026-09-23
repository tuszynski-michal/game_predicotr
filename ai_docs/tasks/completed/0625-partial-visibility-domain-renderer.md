---
title: TASK-0625 — częściowo widoczne komórki w domenie i rendererze (T1)
status: done
last_updated: 2026-09-23
---

# TASK-0625 — częściowo widoczne komórki w domenie i rendererze (T1)

## Status

`done`

## Goal

Komórka planszy, której quad ma 1–3 (nie 4) rogi poza granicami zdjęcia,
może zostać zmaterializowana jako `VirtualCell` i wyrenderowana (dotychczasowy
renderer, bez zmiany matematyki warpu — brakująca część wychodzi czarna z
istniejącego `BORDER_CONSTANT`), zamiast być całkowicie wykluczona. Komórka
z 4/4 rogami poza kadrem nadal jest wykluczana w 100% tak jak dziś.

## Context

Zgłoszenie użytkownika: przy „niepełnej planszy" z kolumną wychodzącą poza
kadr, komórki w tej kolumnie nigdy nie trafiają do Weryfikacji symboli — ani
jako „pending", ani jako „nierozpoznany ?" — bo `derive_virtual_cells`
(services/api/src/game_predictor_api/domain/image_geometry_v2.py:681)
całkowicie pomija każdy indeks z `unavailable_cell_indices`, a
`VirtualCell.__post_init__` wymaga (`require_within`), by quad mieścił się
w całości w źródle. To celowe, udokumentowane zachowanie z TASK-0505–0509
(„brakujące nie otrzymują sztucznych obrazów", `IMAGE_INGESTION.md`
ok. l. 1765–1801) — użytkownik, po przedstawieniu przyczyny, poprosił o nową
zdolność: dać *sobie* możliwość oceny częściowo widocznego symbolu, zamiast
całkowitego pominięcia.

Zaakceptowany plan (ta sesja, wiadomość z DA-1…DA-4) dzieli pracę na T1
(ten task: domena + renderer), T2 (pipeline workera — wymuszony
„nierozpoznany", wykluczenie z treningu) i T3 (Admin UI). Task startuje po
osobnym poleceniu; to polecenie dotyczy wyłącznie T1.

Potwierdzone decyzje z planu:
- **DA-1:** próg „częściowo widoczna" = 1–3 rogi poza kadrem (nie 4/4).
- **DA-4:** zakres na start — tylko ścieżka `virtual_source` (ten task nią
  właśnie jest; legacy plikowa świadomie pominięta).

## Dependencies / entry conditions

- Brak zależności od T1–T5 z wcześniejszej części sesji (osobny obszar:
  Weryfikacja symboli / geometria komórek, nie geometria stron ani
  paginacja).
- Zaakceptowany plan „częściowo widoczne komórki jako wymuszony
  nierozpoznany" z tej sesji (DA-1…DA-4 potwierdzone).

## Recommended execution

`claude-sonnet-5`, reasoning `high`. Uzasadnienie: dotyka twardego
niezmiennika (`SourceQuad.require_within` wywoływane z
`VirtualCell.__post_init__`) chronionego checksumami tożsamości cropa
(`logical_id_sha256`, `render_id_sha256`) oraz duplikowanego bezpiecznika w
rendererze workera (`_require_full_source_support`, komunikat „An
unavailable logical cell must never be rendered"). Wymaga precyzyjnej, nie
za szerokiej relaksacji obu miejsc jednocześnie, bez zmiany matematyki
warpu ani istniejącego zachowania dla zwykłych/w pełni niedostępnych
komórek. Eskalacja: jeśli zmiana wymagałaby też dotknięcia
`render_image_geometry_guard_preview` (osobne, niezależne narzędzie
podglądu dla operatora — poza zakresem) albo repozytorium
`SqlAlchemyVirtualGridGeometryRepository` w sposób szerszy niż tylko
uruchomienie jego testów regresyjnych.
Dodatkowy review: tak — `claude-opus-5-5` / `high`, review diffu przed
commitem (zgodnie z planem).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md` (sekcja „Kontrakt ręcznej
  kompletności i kwalifikacji", TASK-0505–0509)

## Scope

- `services/api/src/game_predictor_api/domain/image_geometry_v2.py`:
  nowy `SourceQuad.require_not_fully_outside`; refaktor współdzielonego
  liczenia rogów poza kadrem; nowa funkcja
  `fully_unavailable_source_cell_indices`; nowe pole
  `VirtualCell.partially_visible: bool`; zmiana `derive_virtual_cells`
  (pomija tylko w pełni niedostępne) i `VirtualCell.__post_init__`
  (relaksacja dla `partially_visible`).
- `services/worker/src/game_predictor_worker/images/virtual_cell_extraction.py`:
  relaksacja bezpiecznika w `VirtualCellRenderer._prepare` (obie kontrole
  `_require_full_source_support` + wczesny `raise
  IMAGE_VIRTUAL_CELL_UNAVAILABLE`) dla komórek `partially_visible`;
  ewentualna nowa wartość `VIRTUAL_CELL_BORDER_POLICY_VERSION` (dokumentacyjna,
  niewpięta w żaden checksum — potwierdzić przed zmianą).
- Nowe testy w `services/api/tests/test_image_geometry_v2.py` i
  `services/worker/tests/test_virtual_cell_extraction.py`.

## Out of scope

- `production_workflow.py`, tworzenie rekordów recenzji symbolu, wymuszony
  `assignedSymbolId = null`, nowy `quality_issue`/`assignmentSource`,
  wykluczenie z treningu — to T2, osobne polecenie.
- Admin UI (T3).
- `render_image_geometry_guard_preview` /
  `image_import_geometry_guard_preview.py` — osobne narzędzie podglądu dla
  operatora podczas korekty geometrii (transient, nic nie persystuje);
  świadomie pozostaje bez zmian, bo pokazuje operatorowi dokładnie to, co
  zadeklarował jako niedostępne — inny cel niż to, co widzi recenzent
  symboli.
- `GeometryQualification`, `resolve_manual_geometry_qualification`,
  `unavailable_source_cell_indices` (istniejąca funkcja, tylko reużyta w
  refaktorze bez zmiany zwracanych wartości), walidacja przy zapisie
  ręcznego override'u strony — bez zmian. Maska `unavailable_cell_indices`
  na poziomie planszy nadal obejmuje zarówno częściowo, jak i w pełni
  niedostępne komórki (bez zmian kontraktu).
- `VIRTUAL_CELL_RENDER_SPEC_VERSION`, `VIRTUAL_CELL_RENDERER_VERSION` i inne
  wersje wpięte w checksumy identyfikujące crop — bez zmian (matematyka
  warpu dla zwykłych komórek jest identyczna; zmienia się tylko, które
  komórki się kwalifikują).

## Acceptance criteria

- [x] `fully_unavailable_source_cell_indices` zwraca wyłącznie indeksy
      komórek, których wszystkie 4 rogi leżą poza granicami źródła (z tym
      samym epsilonem co dotychczasowe `unavailable_source_cell_indices`).
- [x] `derive_virtual_cells` dla planszy z częściowo przesuniętą kolumną
      (1–3 rogi poza kadrem dla części komórek) zwraca **więcej niż**
      `15 - len(unavailable_cell_indices)` komórek — dokładnie te, które nie
      są w pełni niedostępne — i oznacza je `partially_visible=True`; zwykłe
      komórki mają `partially_visible=False`.
- [x] Komórka w 100% poza kadrem (wszystkie 4 rogi) nadal jest pomijana
      przez `derive_virtual_cells` — zero zmian względem obecnego
      zachowania dla tego przypadku.
- [x] `VirtualCell.__post_init__` nie rzuca dla `partially_visible=True`
      mimo quadu częściowo poza źródłem; rzuca `ImageGeometryContractError`
      (`IMAGE_GEOMETRY_QUAD_ENTIRELY_OUT_OF_BOUNDS`), gdyby ktoś spróbował
      skonstruować `VirtualCell(partially_visible=True)` dla quadu w 100%
      poza kadrem (defense-in-depth, nie powinno się zdarzyć przez
      `derive_virtual_cells`, ale klasa sama się chroni).
- [x] `VirtualCellRenderer.render` dla partii zawierającej komórkę
      `partially_visible=True` nie rzuca `IMAGE_VIRTUAL_CELL_UNAVAILABLE` i
      zwraca realny render (RGB, poprawny checksum) zamiast błędu.
      Renderer nadal odrzuca próbę renderowania komórki, która nie jest
      `partially_visible`, ale ma indeks w `unavailable_cell_indices`
      (niespójność domena↔wywołujący — fail-closed jak dotąd).
- [x] Wszystkie istniejące testy `test_image_geometry_v2.py`,
      `test_image_geometry_v2_persistence.py`,
      `test_virtual_cell_extraction.py`,
      `test_virtual_grid_geometry_repository.py`,
      `test_image_import_geometry_guard_preview.py` pozostają zielone bez
      zmiany istniejących asercji.
- [x] `ruff`, `mypy` czyste (bez nowych błędów) dla zmienionych plików.

## Technical notes

### `image_geometry_v2.py`

Aktualnie `unavailable_source_cell_indices` liczy `any(...)` po rogach
(linia 726). Wydzielić prywatny helper `_out_of_bounds_corner_count(cell,
source) -> int` zwracający liczbę rogów poza granicami (ten sam warunek co
dziś, z `SOURCE_SUPPORT_EPSILON`). `unavailable_source_cell_indices` używa
`count > 0`; nowa `fully_unavailable_source_cell_indices` używa `count ==
4`. Bez zmiany podpisów ani zwracanych wartości istniejącej funkcji.

`SourceQuad.require_not_fully_outside(source) -> None`: analogicznie do
`require_within`, ale odwrotnie — rzuca tylko gdy WSZYSTKIE 4 rogi są poza
granicami (z tym samym epsilonem). Nowy kod błędu
`IMAGE_GEOMETRY_QUAD_ENTIRELY_OUT_OF_BOUNDS`.

`VirtualCell`: dodać pole `partially_visible: bool = False` (musi być na
końcu listy pól ze względu na `slots=True` + wartości domyślne — sprawdzić
kolejność istniejących pól przed dodaniem). W `__post_init__`, zamienić:
```python
self.source_quad.require_within(
    self.geometry.source,
    tolerance=SOURCE_SUPPORT_EPSILON if self.geometry.geometry_qualification is not None else 0.0,
)
```
na rozgałęzienie: gdy `self.partially_visible`, wywołać
`self.source_quad.require_not_fully_outside(self.geometry.source)` zamiast
`require_within`. W przeciwnym razie — bez zmian. Reszta `__post_init__`
(walidacja `cell_quad` zgodności) bez zmian.

`derive_virtual_cells`: obliczyć `fully_unavailable =
set(fully_unavailable_source_cell_indices(geometry.symbol_grid_quad,
source=geometry.source, topology=geometry.topology))` tylko gdy
`geometry.geometry_qualification is not None` (w przeciwnym razie brak
maski, zachowanie jak dziś — pusty zbiór). Pętla pomija `cell_index` tylko
gdy jest w `fully_unavailable` (nie w całym `unavailable_cell_indices`).
`partially_visible` dla wynikowej komórki = `geometry_qualification is not
None and cell_index in geometry_qualification.unavailable_cell_indices`
(prawda dokładnie dla komórek, które nie zostały pominięte, a mimo to są
w masce operatora — obejmuje to zarówno geometryczne częściowe wyjście poza
kadr, jak i ręczne wykluczenie komórki w pełni mieszczącej się w kadrze,
np. przesłoniętej naklejką — w obu przypadkach realne piksele istnieją,
więc oba przypadki mają sens jako „do oceny przez człowieka" w T2).

### `virtual_cell_extraction.py` (worker)

W `VirtualCellRenderer._prepare`, obecny blok (ok. l. 209–230):
```python
if cell.geometry.geometry_qualification is not None:
    if cell.cell_index in cell.geometry.geometry_qualification.unavailable_cell_indices:
        raise VirtualCellExtractionError("IMAGE_VIRTUAL_CELL_UNAVAILABLE", ...)
    _require_full_source_support(cell.source_quad, frame=frame, tolerance=SOURCE_SUPPORT_EPSILON)
...
_require_full_source_support(padded_quad, frame=frame, tolerance=... )
```
Zmienić na: jeśli `cell.partially_visible`, pominąć zarówno wczesny `raise`,
jak i obie kontrole `_require_full_source_support` (raw i padded quad) —
zamiast nich wywołać relaksowaną kontrolę „nie w 100% poza kadrem" na
padded quadzie (ten faktycznie trafia do `cv2.warpPerspective`). Jeśli
`cell.geometry_qualification is not None` i indeks w
`unavailable_cell_indices`, ale `cell.partially_visible` jest `False` —
zachować dotychczasowy `raise IMAGE_VIRTUAL_CELL_UNAVAILABLE` (broni przed
niespójnością między warstwami, np. wywołującym, który ręcznie ustawiłby
złą kombinację pól).

`VIRTUAL_CELL_BORDER_POLICY_VERSION` — potwierdzone przed zmianą (grep), że
nie jest porównywana w żadnym checksumie/identity; można ją zaktualizować
dla śladu dokumentacyjnego, ale to opcjonalne — nie blokuje taska.

### Przykład wejście → wynik

Plansza 3×5, kolumna 0 (indeksy 0, 5, 10) przesunięta częściowo poza lewą
krawędź źródła (np. -30 px przy komórce 60×60, analogicznie do fixture w
`test_image_import_geometry_guard_preview.py`). `unavailable_cell_indices =
(0, 5, 10)` (zadeklarowane i zwalidowane przy zapisie — bez zmian w tym
tasku). Po zmianie: `derive_virtual_cells` zwraca 15 komórek (nie 12), z
`cells[0].partially_visible == cells[5].partially_visible ==
cells[10].partially_visible == True`, pozostałe `False`. Renderer zwraca
realny obraz dla wszystkich 15 — dla komórek 0/5/10 lewa część kadru jest
czarna (`BORDER_CONSTANT`), prawa realna.

## Expected files

- Istniejące:
  `services/api/src/game_predictor_api/domain/image_geometry_v2.py`,
  `services/worker/src/game_predictor_worker/images/virtual_cell_extraction.py`,
  `services/api/tests/test_image_geometry_v2.py`,
  `services/worker/tests/test_virtual_cell_extraction.py`.

## Test cases

- `fully_unavailable_source_cell_indices`: komórka z 1, 2, 3 rogami poza
  kadrem → nie w wyniku; komórka z 4/4 → w wyniku. Komórka w pełni w
  kadrze → nie w wyniku.
- `derive_virtual_cells` z kolumną częściowo poza kadrem: liczba zwróconych
  komórek, `partially_visible` per indeks, quady pozostałych komórek
  niezmienione względem dzisiejszego zachowania (regresja: istniejący test
  `test_virtual_cells_are_projective_row_major_without_rectangle_constraints`
  bez zmian).
- `derive_virtual_cells` z kolumną w 100% poza kadrem (np. przesunięcie
  całej szerokości + margines): te komórki nadal pominięte, `len(cells) ==
  15 - len(fully_unavailable)`.
- `VirtualCell` skonstruowany bezpośrednio (nie przez `derive_virtual_cells`)
  z `partially_visible=True` i quadem w 100% poza kadrem →
  `ImageGeometryContractError` z kodem
  `IMAGE_GEOMETRY_QUAD_ENTIRELY_OUT_OF_BOUNDS`.
- `VirtualCellRenderer.render` z partią zawierającą jedną
  `partially_visible=True` komórkę: brak wyjątku, zwrócony `VirtualCellRender`
  ma spójny checksum, `rgb.shape == (output_height, output_width, 3)`.
- Regresja: `VirtualCellRenderer.render` nadal rzuca
  `IMAGE_VIRTUAL_CELL_UNAVAILABLE`, gdy ktoś poda komórkę z indeksem w
  `unavailable_cell_indices`, ale `partially_visible=False` (niespójne
  wywołanie, obrona głębi).

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_geometry_v2.py services/api/tests/test_image_geometry_v2_persistence.py services/api/tests/test_virtual_grid_geometry_repository.py services/api/tests/test_image_import_geometry_guard_preview.py -q
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_virtual_cell_extraction.py -q
.\.venv\Scripts\python.exe -m ruff check services/api/src/game_predictor_api/domain/image_geometry_v2.py services/worker/src/game_predictor_worker/images/virtual_cell_extraction.py services/api/tests/test_image_geometry_v2.py services/worker/tests/test_virtual_cell_extraction.py
.\.venv\Scripts\python.exe -m mypy services/api/src/game_predictor_api/domain/image_geometry_v2.py services/worker/src/game_predictor_worker/images/virtual_cell_extraction.py
```

Timeout 120 s na każdą komendę.

## Risks / open questions

- Jeśli `test_virtual_cell_previews.py`/`test_symbol_references_repository.py`
  lub inne pliki zależne od `VirtualCell`/`derive_virtual_cells` mają
  literalne asercje na liczbę pól dataclass albo pełny `to_dict`/payload —
  nowe pole `partially_visible` może wymagać dopisania go tam, gdzie test
  porównuje kompletny payload (addytywnie, bez osłabiania istniejących
  asercji, zgodnie z ogólną zasadą repo).
- Padding (`padding_fraction`) dla `partially_visible` komórek nie jest
  wyłączany w tym tasku — akceptowane jako spójne z resztą (padding tylko
  dodaje czarny margines, nie zmienia zasady „brak fabrykowania w środku
  komórki").

## Outcome

### Changed

- `services/api/src/game_predictor_api/domain/image_geometry_v2.py`:
  `SourceQuad.require_not_fully_outside` (nowa, relaksowana kontrola
  granic — odrzuca tylko quad z zerem realnych pikseli);
  `_out_of_bounds_corner_count` (wydzielony helper, reużyty przez
  `unavailable_source_cell_indices` bez zmiany jej sygnatury/wartości
  zwracanych); nowa `fully_unavailable_source_cell_indices`
  (podzbiór — tylko komórki z 4/4 rogami poza kadrem); `VirtualCell` +
  pole `partially_visible: bool = False`, `__post_init__` rozgałęzia
  kontrolę granic wg tego pola; `derive_virtual_cells` pomija tylko w
  pełni niedostępne indeksy, oznacza pozostałe zamaskowane komórki
  `partially_visible=True`.
- `services/worker/src/game_predictor_worker/images/virtual_cell_extraction.py`:
  nowa `_require_partial_source_support` (analogiczna relaksacja
  renderera); `VirtualCellRenderer._prepare` — wczesny `raise
  IMAGE_VIRTUAL_CELL_UNAVAILABLE` i obie kontrole
  `_require_full_source_support` (surowy i padded quad) pomijane dla
  `cell.partially_visible=True`, zastąpione `_require_partial_source_support`
  na padded quadzie (to on faktycznie trafia do `cv2.warpPerspective`).
  `VIRTUAL_CELL_BORDER_POLICY_VERSION` pozostawiona bez zmian (potwierdzone
  grepem: nieużywana w żadnym checksumie/identity — zmiana byłaby czysto
  dokumentacyjna, uznana za niepotrzebną w tym tasku).
- `services/api/tests/test_image_geometry_v2.py`: nowy import
  `GeometryQualification`, `VirtualCell`, `fully_unavailable_source_cell_indices`;
  helper `_rectangular_source`/`_partial_visibility_geometry`; 4 nowe testy.
- `services/worker/tests/test_virtual_cell_extraction.py`: nowy import
  `GeometryQualification`; helper `_partial_visibility_frame_and_cells`;
  2 nowe testy.
- `ai_docs/process/DECISION_LOG.md` (D-434), `ai_docs/requirements/IMAGE_INGESTION.md`
  (sprostowanie TASK-0505–0509), `ai_docs/process/CURRENT_STATE.md`.

### Verification results

- `pytest services/api/tests/test_image_geometry_v2.py
  services/api/tests/test_image_geometry_v2_persistence.py
  services/api/tests/test_virtual_grid_geometry_repository.py
  services/api/tests/test_image_import_geometry_guard_preview.py
  services/worker/tests/test_virtual_cell_extraction.py -q`:
  54 passed (48 istniejących bez zmian w asercjach + 6 nowych).
- `pytest services/worker/tests/test_production_image_workflow.py
  services/api/tests/test_symbol_references_repository.py
  services/api/tests/test_image_symbol_review_virtual_source.py -q`:
  68 passed, bez zmian — potwierdza, że T1 samo w sobie nie zmienia
  zachowania `production_workflow.py` (ma własny, redundantny filtr
  usuwający wszystkie zamaskowane indeksy niezależnie od
  `partially_visible` — patrz „Not completed"/D-434).
- `ruff check` na 4 zmienionych plikach: jeden błąd E501 (linia >100
  znaków) w `image_geometry_v2.py`, naprawiony przez złamanie linii;
  ponowny przebieg czysty.
- `mypy` na obu zmienionych plikach źródłowych: 0 błędów bezpośrednio w
  nich; szerszy przebieg (oba pliki naraz) pokazuje 27 błędów w innych,
  niepowiązanych plikach — potwierdzone `git stash` na dokładnie tych 2
  plikach: baseline też 27, identyczna liczba, zero nowych.

### Not completed

- T2 (pipeline workera: wymuszony `assignedSymbolId = null` niezależnie od
  predykcji modelu, nowy `quality_issue`/`assignmentSource`, trwałe
  wykluczenie z treningu) — świadomie poza zakresem T1, wymaga osobnego
  polecenia. Do czasu T2, `production_workflow.py`'s redundantny filtr
  (`if cell.cell_index not in set(unavailableCellIndices)`) nadal usuwa te
  komórki przed renderowaniem — **zero zmiany zachowania widocznego dla
  użytkownika końcowego** mimo ukończenia T1.
- T3 (Admin UI — oznaczenie takich kart w Weryfikacji symboli) — poza
  zakresem, po T2.
- Nie zmieniono `render_image_geometry_guard_preview` (osobne narzędzie
  podglądu dla operatora podczas korekty geometrii) — świadomie, inny cel
  niż to, co widzi recenzent symboli; potwierdzone czytaniem kodu, że nie
  korzysta z `derive_virtual_cells`/`VirtualCell`.
- Nie zmieniono `VIRTUAL_CELL_RENDER_SPEC_VERSION`/`VIRTUAL_CELL_RENDERER_VERSION`
  ani `VIRTUAL_CELL_BORDER_POLICY_VERSION` — brak potrzeby (matematyka
  warpu niezmieniona; żadna z tych stałych nie jest porównywana w
  checksumie/identity, potwierdzone grepem).

### Documentation updates

- `ai_docs/process/DECISION_LOG.md` (D-434), `ai_docs/requirements/IMAGE_INGESTION.md`,
  `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- T2/TASK-0626 (pipeline workera) — wymaga osobnego polecenia użytkownika.
  Kluczowe decyzje z zaakceptowanego planu do zastosowania: DA-2 (predykcja
  modelu nadal liczona i pokazana jako podpowiedź, ale `assignedSymbolId`
  zawsze `null`), DA-3 (nowa, jawna wartość `quality_issue`/`assignmentSource`
  zamiast reużycia `unreadable`), DA-4 (tylko ścieżka `virtual_source`).
