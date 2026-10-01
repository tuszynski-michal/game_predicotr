---
title: TASK-0717 — Poczekalnia cropów symboli
status: done
last_updated: 2026-09-28
---

# TASK-0717 — Poczekalnia cropów symboli

## Status

`done` — zlecone przez operatora po TASK-0716. Niezależny pre-code i końcowy
audyt `gpt-6-sol/medium` PASS bez otwartych P0–P2.

## Goal

Pokazać nieprzypisane cropy z zatwierdzonych geometrii w poczekalni gry oraz
umożliwić jawne przypisanie jednego lub kilku do istniejącego symbolu słownika.

## Context

Aktualny edytor pełnej planszy pozwala obejrzeć cropy bez słownika, lecz zapis
wymaga kompletnej planszy i zatwierdzonego słownika. Operator chce ciąć
wcześniej, tworzyć symbole później i przypisywać cropy pojedynczo lub masowo.
„Grupa” oznacza wpis Słownika gry, np. „cytryna”; nie powstaje druga hierarchia.

## Dependencies / entry conditions

Start HEAD `v1.7.34` / `9d22c13b93c195b28732ceb1f7cfab274145bb87`;
równoległy, niezwiązany TASK-0718 przesunął go w czasie pracy na `v1.7.35` /
`1406f0344d4f40464001daf364523fef06b7f64a`. Przed commitem ponownie
potwierdzić najnowszy rzeczywisty commit brancha i następny patch.
Zastane zmiany/hunki CURRENT_STATE oraz pozostałe cudze pliki zachować poza
commitem. T06a i TASK-0716 gotowe. T06b pozostaje zablokowane do decyzji
operatora i zamrożenia podziału symboli. API rozszerzamy zgodnie w istniejących
trasach; operator został poinformowany przed zmianą.

## Recommended execution

`gpt-6-sol`, reasoning `medium` dla pionu backend/API/UI; niezależny review
`gpt-6-sol`, reasoning `medium` przed kodem i po kodzie. Gdy zakres lub
kontrakt różni się istotnie, zaktualizować task przed kodowaniem. P0–P2 po
dwóch cyklach poprawek zatrzymują zadanie.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `TASK_TEMPLATE.md`, `DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/tasks/0671-vision-lab-symbol-labels.md`
- `ai_docs/delivery/VISION_LAB_SYMBOL_LABELS_CONTRACT.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T06)
- `ai_docs/process/DECISION_LOG.md` (D-458, D-459, D-460)

## Scope

Jedna wyliczana poczekalnia per gra, stronicowany chroniony podgląd dokładnych
cropów i jeden atomowy zapis do 30 wybranych komórek jako jedna klasa aktywnego
słownika. Istniejący edytor całej planszy i jego zapis pozostają bez zmian.
Backend, OpenAPI, wygenerowany klient, wrapper, UI, testy, docs i lokalny QA.

## Out of scope

Import nowych plików zdjęć/rebase snapshotu, autoetykiety, grupy nad klasami,
zmiany ról/holdoutów, zapis `unknown` przez poczekalnię, kwalifikacja T06b,
trening, model, DB, aplikacja mobilna, push/merge/aktywacja.

## Acceptance criteria

- [x] Crop bez aktualnej decyzji klasy widoczny jako „Nieprzypisany” przed
  utworzeniem słownika, po restarcie i bez fizycznej kopii PNG w symbolstore.
- [x] „Nieprzypisany” nie jest `unknown`, `unreadable` ani `grid_issue`;
  aktualne jawne stany oceny nie wracają do poczekalni. Cofnięcie decyzji
  wraca jako „Nieprzypisany”, drift jako osobne „Do ponownej oceny”.
- [x] Stronicowanie 1–30 cropów per gra, stabilna kolejność; źródła
  comparison_only i holdout nie ujawniają pikseli ani danych listy.
- [x] Wybór jednej lub wielu miniatur i jednej klasy słownika; jeden atomowy
  zapis tylko zaznaczonych cropów. Pozostałe nie zmieniają się.
- [x] Brak zatwierdzonego słownika nie blokuje podglądu, ale blokuje zapis.
- [x] CAS, identyczny retry po utracie odpowiedzi, restart i backup/restore
  zachowują wynik; błąd ostatniej komórki nie publikuje części decyzji.
- [x] T06a/TASK-0716 single/whole-board/DB zachowane; API, klient, testy,
  lint, typy, build, audyt i QA PASS.

## Technical notes

### Stan i reguły

Poczekalnia to pochodny widok: `AnnotationState` i istniejący immutable
SymbolStore są źródłami prawdy. Nie dodać nowej tabeli ani trwałej flagi
„pending”. Kandydują tylko zdjęcia z `photo_accepted`, zapisane pełne obecne
ludzkie geometrie, dozwolone role/holdout. Porządek: source_id, board_index,
cell_index rosnąco. Brak decyzji i ostatni withdraw dają „Nieprzypisany”.
Stary binding geometrii, renderer lub stara wersja słownika dają osobne
„Do ponownej oceny”, także dla poprzednich unknown/unreadable/grid_issue.
Bieżące approve i jawne stany oceny przy aktualnym bindingu/słowniku nie wchodzą.
Przed ujawnieniem source/cropa sprawdzić rolę i holdout, przed dekodowaniem
obrazu; brak założenia, że geometria dopuszcza trening symboli. Tylko
widoczne 30 elementów renderować, dokładnie tym samym rendererem RGB96.
Kandydaci to podgląd, nie lab_human_approved ani próbki treningowe.
Źródła `HOLDOUT_NOT_RELEASED` są pomijane bez pikseli; globalny
`HOLDOUT_POLICY_UNRESOLVED` jest błędem całego odczytu/zapisu, nigdy pustą
poczekalnią HTTP200. Nie maskować integralności jako braku kandydatów.
Zbudować indeks rewizji i akceptacji geometrii raz oraz wyliczyć uprawnienia
per source/komponent raz na odczyt; nie wołać wielokrotnie photo_accepted,
pilot_is_current ani build_components dla każdego z ~2700 cropów.

### API i transakcja

Proponowane addytywne `kind=lab_queue` w istniejącym `POST /symbol-crops`
z game_id, offset, limit, read_token. Odpowiedź ma `items` (binding, PNG
base64, status `unassigned|requires_review` i reason), total, revision
i stabilny read_token. Nie tworzy równoległego endpointu.
Limit <=30; offset>0 wymaga identycznego tokenu widoku geometrii i symboli.
Token dodatkowo obejmuje render_spec, regułę kolejki, game_id i sortowanie,
aby nie mieszać stron po zmianie wersji renderera. Zwraca wyłącznie dopuszczone
źródła. Brak aktywnego słownika nie blokuje
odczytu. Nie stosować `local_row` do liczenia tysięcy kandydatów, bo ten
odczytuje piksele/artefakty; liczyć z metadanych przy obu blokadach.

Istniejący `POST /symbols` dostaje addytywne `op=label_cells_decide`:
request_id, expected_revision, actor, aktywna dictionary_version/digest,
symbol_id i 1–30 unikalnych `CropBinding` z jednej gry, ułożonych jak lista
kandydatów. Serwer przed publikacją sprawdza kompletność pól, rolę/holdout,
geometrię, źródło, bieżący status kandydata „Nieprzypisany” albo „Do ponownej
oceny”, wersję słownika i każdy
ponownie wyliczony binding. Dopiero po walidacji wszystkich: immutable cropy,
jedno write_atomic(state), jedna rewizja/historia/receipt. Odrębne stabilne
decision_id na crop wyprowadzony z fingerprintu żądania i crop_id (sam
cell_index powtarza się na różnych planszach), dokładny retry przed CAS,
jak TASK-0716. Brak częściowej
zgody w razie błędu; pojedyncze/całoplanszowe requesty bez zmiany.
Dekodować obraz najwyżej raz per źródło w stronie/batchu; nie hashować źródła
ani przeliczać grafu 30 razy przez `result()` dla świeżego batcha. Receipt
przechowuje identyfikatory/rewizję, ale identyczne retry zwraca bieżącą
ważność etykiet po późniejszym withdraw/drift, jak TASK-0716.

### UI

Sekcja „Poczekalnia cropów” na `/symbols`, po słowniku gry. 30 miniatur
z nazwą zdjęcia, numerem planszy i pola. Checkbox przy każdej, „Zaznacz
widoczne”, „Wyczyść wybór”, kompaktowy wybór istniejącego symbolu i
„Przypisz zaznaczone”. Zmiana gry/strony kasuje lokalny wybór. W czasie
pending blokować nawigację/edycję i zachować identyczny payload retry przez
obecny `symbolWriteSession`. Toast błędów, nie inline alert. Po zapisie
odczytać tę samą stronę lub pierwszą, jeśli ostatnia stała się pusta.
Zapis zablokowany do `onLoad` wszystkich pokazywanych PNG; spóźnione
`onLoad/onError` poprzedniej strony nie zmieniają gotowości nowej.
Trwałe `unknown` pozostaje w edytorze planszy, nie jest pustym wyborem.
Nie pobierać 2700 cropów naraz ani nie startować treningu.

## Expected files

- Istniejące `vision_lab/symbol_contracts.py`, `symbol_store.py`, `symbol_api.py`,
  `symbol_crops.py`; nowy helper metadanych tylko jeśli upraszcza moduły.
- `packages/vision-lab-api-client/openapi/openapi.json`, generated, `src/index.ts`, test.
- `apps/vision-lab/src/components/symbol-label-editor.tsx`, `src/app/style.css`;
  nowy proponowany `symbol-candidate-queue.tsx`, helper i testy.
- Nowy proponowany `services/worker/tests/test_vision_lab_symbol_candidates.py`.
- Wymagania, architektura, kontrakt T06a, guide, decyzja D-460, CURRENT_STATE.

## Test cases

Pusta gra/słownik i widoczne cropy, role/holdout przed decode, 30+1 i token
zmiany, kolejność, repeated SHA, unknown vs no decision, withdrawn/stale,
jedna/wiele komórek z różnych plansz, zły ostatni binding/klasa/CAS bez części,
source swap, przejście słownika (także unknown → nowa wersja), recrop po
unknown, batch mieszający oba statusy i niezmienność decyzji przy błędzie,
retry po utracie odpowiedzi i w nowym procesie,
backup/restore, UI brak autosave, select jednego/masowo, pusta kolejka, loading,
błąd obrazka, utrata geometrii, stary odczyt, dotyk 390 px. Testy planowane.

## Verification

Z root repo, każde skończone polecenie z timeout <=120 s: skoncentrowany
pytest nowych i dotychczasowych testów symboli; testy UI/klienta; Ruff,
Mypy zmienionych modułów, ESLint, TypeScript, generated check; build Next po
zatrzymaniu własnego starego UI. Odśwież lokalne API/UI dopiero po audycie,
sprawdź read-only QA bez decyzji za operatora. Nie uruchamiaj benchmarków.

## Risks / open questions

Nowe zdjęcia nie zostaną zaimportowane tą zmianą. Obecny rebase ma blokadę
przy historycznej kwalifikacji/splitach; wymaga osobnego kontraktu wersjonowania.
Poczekalnia sama nie upoważnia do etykiety ani treningu. Nie kasować starych
decyzji, nie zmieniać holdoutów.

## Outcome

Zaimplementowano pochodną poczekalnię cropów, odczyt 30/strona i atomowe
przypisanie 1–30 komórek do istniejącej klasy gry. Brak kopii PNG w kolejce;
rozróżniono `unassigned`, aktualne jawne review i `requires_review` po drift.
Ochrona role/holdout jest przed dekodowaniem, strona dekoduje tylko widoczne
źródła, jeden pełny obraz naraz. Odczyty parent/board/queue są uporządkowane,
preview ma limit 60 s; identyczny retry pokazuje bieżącą ważność etykiety.
Nowe zdjęcia i podział symboli pozostają poza taskiem.

Wykonawca `gpt-6-sol/medium`: backend focused 38 PASS (8 nowych), UI 53 PASS,
klient 12 PASS; Ruff, Mypy scoped, ESLint, TypeScript, OpenAPI/generated PASS.
Root: build Next PASS; runtime API/UI 8102/3102 PASS, Blazing 450 kandydatów,
30 obrazów załadowanych i wybieralnych, odświeżenie oraz obie strony PASS.
390 px: brak poziomego przepełnienia, kontrolki 44 px. Nie zapisano żadnej
decyzji operatora. Pre-code i końcowy niezależny audyt `gpt-6-sol/medium`:
PASS bez otwartych P0–P2. Fizyczny restart Windows i Android nietestowane.
Commit `v1.7.36` / `8fa1e25991cc0af1905034d40dcb0065d5f6a552`.
Staged diff check/stat/list i post-commit show/stat/status PASS; 25 plików,
zastane cudze zmiany pozostały poza commitem.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0717 — poczekalnia i przypisanie 1–30 cropów | `gpt-6-sol` | `medium` | Stronicowanie, atomowość i ochrona danych w pionie API/UI. | `gpt-6-sol`, `medium`, przed i po kodzie |
