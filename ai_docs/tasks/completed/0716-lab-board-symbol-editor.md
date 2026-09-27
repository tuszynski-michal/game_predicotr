---
title: TASK-0716 — Etykietowanie całej planszy w laboratorium
status: done
last_updated: 2026-09-28
---

# TASK-0716 — Etykietowanie całej planszy w laboratorium

## Status

`done` — implementacja, testy, build, odbiór UI i audyt Sol medium PASS.

## Goal

Zastąpić wybór pojedynczej komórki widokiem całej planszy z siatką oraz
kompaktowymi wyborami symboli dla wszystkich 15 pól i jednym atomowym zapisem.

## Context

Operator chce etykietować 15 cropów jednocześnie, nie otwierać każdego osobno.
Obecny panel T06a ma tylko LabCropRequest i LabelDecide. Polecenie dotyczy
narzędzi; nie upoważnia do zatwierdzania danych przez agenta ani treningu.

## Dependencies / entry conditions

HEAD v1.7.33 / 5e415acc9a56ae450fb440357eb60d3074245693; słownik przyjmuje
już same nazwy. Zastane zmiany dokumentacji/next-env zachować poza commitem.
Root zapowiedział operatorowi zgodne rozszerzenie obecnego API. Bez zmiany
roli 777, holdoutów, symbolowego splitu ani reguł aktualności etykiet.

## Recommended execution

Wykonawca `gpt-6-sol`, reasoning `medium`; niezależny audyt przed kodem i po
kodzie `gpt-6-sol`, reasoning `medium`. Atomowość całej planszy, dokładne
bindingi cropów i ochrona danych wymagają sprawdzenia backendu i UI razem.
Nierozwiązane P0–P2 po dwóch cyklach poprawek zatrzymują zakres.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`, `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/tasks/0671-vision-lab-symbol-labels.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T06)
- `ai_docs/delivery/VISION_LAB_SYMBOL_LABELS_CONTRACT.md` (całość)
- `ai_docs/process/DECISION_LOG.md` (D-458, D-459)

## Scope

Pełny pion: zgodne warianty istniejących tras, atomowy symbol store,
podgląd całej planszy i dokładnych cropów, wygenerowany klient, UI, testy i docs.

## Out of scope

Trening, automatyczne etykiety, import starych etykiet DB, produkcyjna baza,
zmiany geometrii, mapowanie klas, mobilna aplikacja, push/merge i aktywacja.

## Acceptance criteria

- [x] Cała wybrana plansza z siatką i numerami; pod nią układ 5 × 3 z dokładnymi cropami i małymi selectami.
- [x] Selecty zawierają klasy słownika oraz jawne Nieznany/Nieczytelne/Błąd siatki, bez automatycznej klasy.
- [x] Aktualne zapisane etykiety są wczytane; nieaktualne nie stają się domyślną zgodą.
- [x] Jeden przycisk zapisuje komplet 15 decyzji; dla istniejącej topologii 3 × 3 komplet 9, bez fikcyjnych pól.
- [x] Błąd dowolnego pola, drift, konflikt lub awaria nie publikuje części decyzji.
- [x] Identical retry i nowy proces zachowują cały zapis; pojedyncze stare requesty nadal działają.
- [x] Holdout/role sprawdzane przed każdym odczytem pikseli, także zdjęcia całej planszy.
- [x] Backend/OpenAPI/generated/wrapper/request test są zgodne; scoped testy, lint, typy, build i audyt PASS.

## Technical notes

### Odczyt i podgląd

Istniejący POST /symbol-crops dostaje kind=lab_board z source_id, board_index,
expected_geometry_revision (bez cell_index). Dotychczasowe lab_cell/db_approved
są niezmienione. LabBoardPreview zawiera kind, revision symbolstore, aktywny
słownik lub null, topology, board_png_base64, width/height i nodes w układzie
podglądu oraz cells w kolejności row-major. Każdy element cells zawiera binding,
png_base64 dokładnego cropa i bieżący lokalny SymbolRow lub null.

W jednym locked() sprawdzić guard_pixels i geometry_for, dopiero potem source
SHA/decode. Czytać obraz raz na podgląd planszy, użyć wspólnej implementacji
cropów tak, aby single-cell PNG/binding pozostały identyczne. Obraz planszy jest
ograniczonym do max960 px na dłuższym boku bounding boxem wszystkich węzłów
z niewielkim marginesem, w perspektywie zdjęcia. Węzły dokładnie przeliczone
do tego kadru; nie zgadywać regularnej siatki z samych narożników. To obraz
kontekstowy, nie osobny target treningowy. Dokładne cropy 96 × 96 widać poniżej.
Maksymalnie 15 cropów, dotychczasowy limit 256 KiB per crop i 4 MiB PNG planszy.

### Zapis

Istniejący POST /symbols dostaje op=label_board_decide: wspólne request_id,
expected_revision, actor, dictionary_version/digest oraz cells (9 albo15)
z binding, action approve|unknown|unreadable|grid_issue i symbol_id|null.
Puste pole jest brakiem wyboru, nie unknown; UI blokuje zapis do uzupełnienia.
Walidować dokładnie wszystkie indeksy 0..N-1 w row-major, brak duplikatów,
jeden source/game/board/topology/geometry i bieżący słownik. Wszystkie bindingi
porównać z ponownie wyliczonymi pod obiema blokadami, przed pierwszą publikacją.
Wspólna implementacja single/batch, bez zagnieżdżonego mutate/lock i 15 HTTP zapisów.

Publikacja immutable cropów preceduje jeden write_atomic(state); dopiero wtedy
wszystkie decyzje stają się widoczne. Jeden przyrost rewizji, jeden event/receipt;
oddzielne stabilne decision_id per komórka wyprowadzone z batch fingerprint i
cell_index. Nowy batch receipt przechowuje decision_ids do odtworzenia wyniku;
nie dziedziczyć grupy przez późniejsze withdraw. Retry po withdraw nadal
zwraca pierwotne ID, przy aktualnie wyliczanej ważności decyzji.
SymbolResult rozszerzony zgodnie o decision_ids (domyślnie pusta lista dla
starych operacji); batch label_valid jest true tylko dla wszystkich ważnych
approve, reasons/blockers agregowane bez ukrywania niepoprawnej komórki.
trainable zawsze false. Retry sprawdza receipt przed CAS, zwraca te same ID;
odczyt może ujawnić późniejszy drift zgodnie z T06a. Nie przepisywać starych
receiptów/decyzji. Backup/restore obsługuje nowe decyzje tym samym mechanizmem.
Awaria po cropach może zostawić nieużyte pliki, ale nigdy częściowe approval;
brak GC. Ograniczenia rozmiaru stanu i 10000 bieżących komórek pozostają.

### UI

Nowa sekcja „Symbole całej planszy” zastępuje pojedynczy wybór komórki.
Wybór zdjęcia i zapisanej pełnej planszy; nie wymagaj ręcznego wpisywania
komórki. Plansza do około 640 px szerokości, selektory w pięciu kolumnach
zgodnie z polami (3 dla 3 × 3), numery 1–15 zgodne z backendowym row-major.
Select font 13–14 px i wysokość 32–36 px desktop, dotyk minimum 44 px; brak globalnego
powiększenia komponentów. Na małym ekranie zachowaj czytelne powiązanie pól
i brak przepełnienia strony. Nie prezentuj 15 osobnych dużych formularzy.

Wczytaj zapisane etykiety tylko gdy odpowiadają aktualnemu bindingowi i
słownikowi; unknown/unreadable/grid_issue można odtworzyć jako jawne stany
przy zgodnym bindingu/słowniku, ale nie jako approve. Withdraw/stale puste.
Zmiana źródła/gry/planszy kasuje stary preview i lokalne wybory bez autosave
i modalnego alertu; odpowiedź starego żądania nie może zastąpić nowej planszy.
Loading i błąd obrazu blokują zapis do wczytania wszystkich pokazywanych PNG.
Podczas pending zapisu blokować nawigację/edycję, zachować dokładny request
do retry; toast zgodny z obecnym panelem. Po sukcesie odtworzyć tę samą planszę
z trwałego zapisu, bez niezamówionego przejścia dalej. Słownik name-only i
read-only DB preview pozostają zgodne; brak pobierania niechronionego assetUrl.

## Expected files

- Istniejące vision_lab/symbol_contracts.py, symbol_crops.py, symbol_store.py, symbol_api.py.
- packages/vision-lab-api-client: OpenAPI, generated, src/index.ts i test żądania.
- apps/vision-lab/src/components/symbol-label-editor.tsx, src/app/style.css, testy workflow.
- Nowy proponowany komponent symbol-board-editor.tsx i helper symbol-board-workflow.ts, jeśli potrzebne do ograniczenia wielkości modułów.
- Nowe testy test_vision_lab_symbol_board.py; istniejące testy symboli/kontraktu.
- Dokumenty właścicielskie wymagań/architektury, kontrakt T06a, przewodnik, ten task i CURRENT_STATE.

## Test cases

Parity single/batch pixels i bindingi; overlay zgodny z węzłami; 5×3/3×3;
9/15 decyzji z jedną rewizją; zły ostatni binding/klasa bez częściowego stanu;
duplikaty/mieszane plansze/niepełne indeksy; drift geometrii/słownika/źródła;
holdout/comparison_only przed decode; utrata odpowiedzi/exact retry, CAS,
restart i backup/restore; stare requesty; UI15 selectów, row-major, aktualne
i nieaktualne etykiety, brak autosave, busy, spóźniony odczyt, błąd PNG.

## Verification

Każda komenda skończona ma timeout<=120s, osobno. Najpierw pytest zmienionych
testów symboli oraz npm test vision-lab i vision-lab-api-client. Potem Ruff,
Mypy zmienionych modułów, lint/TypeScript UI i klienta, check:generated.
OpenAPI eksportować istniejącym mechanizmem projektu, nie pisać ręcznie.
Build tylko przy zatrzymanym zweryfikowanym lokalnym UI; restart API/UI po
audytach, bez zmiany argumentów danych. QA osobna karta, brak zapisów operatora.

## Risks / open questions

Nie odświeżać karty operatora ani nie zatwierdzać symboli podczas QA.
Przy braku zgody holdout lub słownika pokazać istniejący jawny brak, nie omijać.
To ograniczony pion UI/API, nie kwalifikacja danych T06b.

## Outcome

Wdrożono pełny pion zgodnie z planem: podgląd planszy z rzeczywistymi węzłami,
dokładne cropy, 9/15 kompaktowych wyborów i atomowy zapis kompletu. Zachowano
stare API, role/holdouty, słownik name-only oraz podgląd DB tylko do odczytu.

Pre-code i końcowy niezależny `gpt-6-sol/medium`: PASS bez otwartych P0–P2.
Zamknięto P2 dotyczący nieaktualnego podglądu po zmianie photo review/holdoutu
lub utracie pełnej geometrii. Regresja obejmuje jawny reload, zmianę rewizji
anotacji i spóźnione zdarzenia obrazu. Retry po withdraw zachowuje pierwotne
decision_ids; jawne stany niezatwierdzające są odtwarzane tylko przy zgodnych
bindingach i słowniku.

Weryfikacja wykonawcy: 61 testów backendu, 47 UI, 10 klienta PASS. Audytor
niezależnie: 48 testów backendu, 47 UI, 10 klienta PASS. Ruff check/format,
ESLint, TypeScript UI/klienta, eksport OpenAPI i check:generated PASS.
Mypy czterech zmienionych modułów z --follow-imports=silent PASS; pełne
śledzenie importów ujawniło wcześniejsze błędy poza tym pionem, pozostawione
bez zmian. Logi kontroli w work/0716-*.log.

Build Next PASS. API i UI uruchomione ponownie z tymi samymi katalogami danych.
Odbiór przeglądarkowy na zapisanej planszy Blazing: dokładnie 15 selectów,
16 poprawnie załadowanych obrazów, wysokość selecta 34 px desktop / 44 px
przy viewport 390 px; brak poziomego przepełnienia. Brak słownika poprawnie
blokuje wybór symboli, bez tworzenia danych za operatora. QA wykrył zbyt duże
numery SVG w małym źródle; korekta skaluje je względem podglądu. Końcowe
47 testów UI, lint, typy, ponowny build i dodatkowy review korekty PASS.
Końcowy screenshot: artifacts/vision-lab/t0716-board.png. API launcher PID
24616, UI PID 11488; gotowość obu usług potwierdzona z ograniczonym pollingiem.

Definition of Done sprawdzono punkt po punkcie: funkcjonalność, izolacja danych,
zgodny kontrakt, testy i dokumentacja spełnione w zakresie taska. Nie ma zmian
schematu DB. Ograniczenia urządzeń i pełnego Mypy opisano jawnie poniżej.

Nie wykonywano zapisów etykiet operatora, treningu, aktywacji, push ani merge.
Trwałość stanu i retry sprawdzono w nowym procesie oraz backup/restore;
nie wykonano restartu całego Windows ani testu na fizycznym Androidzie.
Następny krok operatora: zatwierdzić słownik gry, wybrać zdjęcie/planszę,
uzupełnić komplet symboli i jawnie zapisać. T06b pozostaje osobnym zakresem.
Commit: do uzupełnienia po końcowej kontroli indeksu.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0716 — pełna plansza i atomowe etykiety | `gpt-6-sol` | `medium` | Spójny pion UI/API z atomowością i ochroną bindingów. | `gpt-6-sol`, `medium`, przed kodem i po kodzie |
