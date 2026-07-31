---
title: Verification workbench scale and usability acceptance
status: done
last_updated: 2026-07-31
completed_at: 2026-07-31
---

# TASK-0111 — Verification workbench scale and usability acceptance

## Status

`done`

## Goal

Domknąć lokalną bramkę G6.5 przez odbiór wydajności, bounded queue,
dostępności i ergonomii stanowiska weryfikacji plansz oraz zebrać uczciwe
metryki pozwalające oszacować ręczną pracę dla kolejnych 1000 i 3000 plansz.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_06_5_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- dodać powtarzalny profil kolejki co najmniej 3000 syntetycznych plansz,
- potwierdzić bounded cursor i brak pobierania całej kolejki do klienta,
- potwierdzić jedną kolejkę wszystkich plansz: zapis nie usuwa planszy z
  nawigacji, lewo wraca do zatwierdzonej, a `Enter` zapisuje i przechodzi dalej,
- zmierzyć p95 lokalnego odczytu sąsiada i zapisu bez recropowania,
- zweryfikować scenariusz keyboard-only, korektę symbolu, geometrii i ponowną
  edycję kompletnej planszy,
- zweryfikować kwadratowe cropy w zwartej siatce oraz wycięty obraz jednej
  bieżącej planszy pokazany obok,
- zweryfikować konflikt dwóch kart oraz exact retry po niejednoznacznym
  przerwaniu odpowiedzi,
- potwierdzić wznowienie po restarcie bez utraty decyzji i pozycji,
- wykonać odbiór dostępności i układu 1366 × 768 bez poziomego overflow,
- utworzyć raport operatorski z backlogiem, zgodnością model–człowiek,
  odsetkiem skorygowanych komórek/geometrii, przepustowością oraz szacunkami
  pracy dla 1000 i 3000 plansz.

## Out of scope

- zdalny link, kod dostępu, binding poza loopback i hosting — M8.7,
- ponowne trenowanie lub automatyczna promocja modelu,
- automatyczne włączenie `massImportAllowed`,
- pełny masowy import zdjęć,
- ponowne cropowanie w mierzonym hot path.

## Acceptance criteria

- [x] profil zawiera co najmniej 3000 plansz, a pojedyncza odpowiedź UI nadal
  zawiera najwyżej jedną planszę,
- [x] p95 lokalnego odczytu i zapisu bez recropowania nie przekracza 500 ms,
- [x] bounded cursor zachowuje deterministyczne poprzednia/następna na początku,
  w środku i na końcu kolejki,
- [x] decyzja i pozycja są możliwe do wznowienia po restarcie,
- [x] aktywna sesja nawiguje po wszystkich planszach z `limit = 1`; po zapisie
  strzałka w lewo wraca do zatwierdzonej planszy,
- [x] `Enter` zapisuje najwyżej jedną rewizję i po sukcesie przechodzi do
  następnej planszy pełnej kolejności,
- [x] wejście/reload zaczyna od pierwszej pending, a przy braku pending od
  pierwszej planszy importu,
- [x] konflikt stale revision i exact retry są rozróżnione i nie tworzą
  podwójnej rewizji,
- [x] keyboard-only, korekta symbolu, korekta geometrii i ponowna edycja
  kompletnej planszy przechodzą,
- [x] pełna siatka 5 × 3 mieści się przy 1366 × 768 bez poziomego overflow,
- [x] podstawowe nazwy dostępności, role, fokus dialogu i kolejność klawiatury
  przechodzą odbiór,
- [x] raport nie przedstawia pracy ręcznej jako automatyzacji i podaje
  oszacowania dla kolejnych 1000/3000 plansz,
- [x] accepted/corrected pozostają chronione przed późniejszą inferencją,
  a automatyczny masowy import nadal wymaga osobnej decyzji jakości,
- [x] właściwe testy, lint, typecheck i build przechodzą.

## Technical notes

- Profil wydajności ma osobno deterministyczną sekcję semantyczną i pomiary
  czasu ściennego. Nie zapisuje obrazów ani nie uruchamia recropowania.
- Pamięć klienta jest ograniczona kontraktem `limit: 1`; licznik 3000 nie może
  oznaczać tablicy 3000 obiektów po stronie React.
- „Wszystkie plansze” oznacza semantykę kolejki, nie eager loading. Każdy krok
  nawigacji nadal pobiera najwyżej jedną planszę.
- Pomiar operatorski wykonany bez pełnego realnego przejrzenia 3000 plansz
  jest prognozą na podstawie jawnie zapisanej próby. Raport musi podać rozmiar
  próby i nie może nazwać prognozy pomiarem produkcyjnym.
- Każda potencjalnie ciężka komenda ma timeout nie większy niż 120 sekund.

## Expected files

- `services/api/tests/test_operational_image_review_scale.py`
- `apps/reviewer/test/operational-review-*.test.mjs`
- `scripts/run_m65_workbench_acceptance.py`
- `ai_docs/quality/m65-workbench-acceptance-report.json`
- dokumentacja procesu i planu M6.5.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_operational_image_review_scale.py -q
.\.venv\Scripts\python.exe scripts/run_m65_workbench_acceptance.py
node --test --experimental-strip-types apps/reviewer/test/operational-review-*.test.mjs
```

## Risks / open questions

- Wynik czasu zależy od lokalnego sprzętu; bramka zapisuje środowisko i p95,
  ale deterministyczne kryteria semantyczne pozostają niezależne od czasu.
- Realna liczba plansz na godzinę zależy od jakości nowego corpus; obecny raport
  może podać wyłącznie uczciwą prognozę z jawnie oznaczonej próby operatorskiej.

## Outcome

### Changed

- Dodano fizyczny, ograniczony do 120 sekund profil PostgreSQL dla 3000 plansz
  i 45 000 komórek oraz kanoniczny raport odbiorczy.
- Profil mierzy 40 odczytów sąsiada i 30 pełnych zapisów, sprawdza początek,
  środek i koniec kursora, exact retry, stale revision dwóch kart oraz
  wznowienie w nowej sesji.
- Klient nadal wysyła `limit: 1`; test obejmuje licznik 3000 bez utworzenia
  tablicy 3000 elementów w stanie React.
- Dialog zatwierdzenia przejmuje fokus i po anulowaniu oddaje go przyciskowi
  `Zatwierdź`. Dodano zwarty profil wysokości dla desktopu 1366 × 768.
- Raport operatorski wykorzystuje 84 kompletne ręcznie sprawdzone plansze,
  1260 komórek, 31 korekt etykiet oraz 14/387 korekt geometrii. Czas jest jawnie
  oznaczoną prognozą do zastąpienia próbą minimum 10 plansz.
- Po pierwszym odbiorze osobnej aplikacji Reviewer zmniejszono główny widok:
  każda komórka symbolu jest kwadratowa, zwarta siatka nie zajmuje całej
  szerokości, a obok znajduje się asset `board` jednej bieżącej planszy.
  Pełne zdjęcie źródłowe z dziewięcioma planszami pozostaje tylko w edytorze
  geometrii.

### Verification results

- fizyczny PostgreSQL: 3000/45 000, p95 read `49.896 ms`, p95 write
  `96.368 ms`, raport SHA-256
  `98eee87c31b97f49151ced65a31c0fa012d0fa5fda9331f3864cba5141318891`,
- `198 passed, 16 skipped` w pełnym zestawie Admin API; w tym `13 passed`
  dla operational review/cohort/scale,
- `92 passed` w pełnym zestawie panelu; w tym `15 passed` dla stanowiska
  operacyjnego,
- Ruff, mypy (`235 source files`), ESLint, Prettier i TypeScript strict
  przeszły,
- produkcyjny build Next.js przeszedł.
- korekta widoku porównawczego: `15 passed`, TypeScript strict, ukierunkowany
  ESLint, Prettier, produkcyjny build Reviewera i browser smoke przeszły.

### Manual acceptance

- TASK-0112 dostarczył osobną aplikację Reviewer i poprawny lokalny przepływ
  panel admina → link i kod → gate → stanowisko ograniczone do gry/importu.
- Właściciel zatwierdził i ponownie przejrzał układy do `#55`, potwierdzając
  poprawne działanie zatwierdzania, korekt i nawigacji.
- Rzeczywista próba operatorska obejmuje 11 nowych decyzji z zakresu
  `#28–#42` w 198 sekund: 10 zaakceptowanych, jedną poprawioną planszę i jedną
  zmienioną komórkę.
- Odbiór 1366 × 768 potwierdził 15 kwadratowych komórek w viewport, brak
  poziomego overflow, widoczny główny przycisk i wyrównanie obrazu planszy
  porównawczej z siatką symboli.
- Pierwszy test operatorski potwierdził pojedynczy zapis przez `Enter`, ale
  ujawnił błąd nawigacji: po zapisie filtrowanie pending usuwało item i
  uniemożliwiało powrót strzałką w lewo. Zaakceptowana korekta wymaga jednej
  kolejki `all`, automatycznego przejścia dalej po zapisie oraz startu od
  pierwszej pending po wejściu/reloadzie.
- Podczas wznowienia testów wykryto, że CSP Reviewera blokuje inline bootstrap
  Next.js i pozostawia gate w stanie loading. Politykę skorygowano bez
  dopuszczania zewnętrznych originów; test konfiguracji, build produkcyjny oraz
  browser smoke `kod → Weryfikacja plansz` przeszły.
- Kolejny test wykrył wejście po zapisie na planszę kompletną, rozdzielającą
  oczekujące pozycje. `Enter` i przycisk pokazują teraz `Dalej` oraz przechodzą
  bez pustej rewizji; strzałki nadal nawigują po wszystkich statusach.
  Nagłówek planszy porównawczej usunięto, aby obraz był wyrównany z górą siatki
  symboli. Zmiana przeszła 19 testów Reviewera, lint, formatowanie, TypeScript
  strict i build produkcyjny.
- Właściciel zatwierdził i przejrzał układy do `#55`, potwierdzając poprawne
  działanie stanowiska. Zgodnie z informacją zwrotną `ArrowRight` i przycisk
  `→` zostały zrównane z akcją `Enter`; lewa strzałka pozostaje nawigacją
  wstecz. Regresja przeszła 19 testów, ukierunkowany lint, formatowanie,
  TypeScript strict i build produkcyjny.
- Końcowy odbiór właściciela potwierdził obie akcje `ArrowRight`/`→`. TASK-0111
  oraz lokalna bramka G6.5 są zamknięte; wynik nie zmienia osobnej blokady
  `massImportAllowed`.
