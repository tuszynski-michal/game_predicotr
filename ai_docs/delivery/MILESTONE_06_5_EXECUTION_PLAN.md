---
title: Milestone 06.5 execution plan
status: accepted
last_updated: 2026-07-29
---

# Plan wykonania Milestone 06.5 — Supervised verification workbench

## Cel

Udostępnić lokalne, minimalistyczne stanowisko do szybkiego zatwierdzania
pełnych plansz 5 × 3 z sugestiami modelu, korektą symboli i geometrii oraz
niezmiennym audytem decyzji człowieka. Zweryfikowane plansze mają zasilać
kontrolowane wersje danych i kolejne treningi bez nadpisywania wcześniejszych
decyzji.

M6.5 jest pomostem pomiędzy jakością modelu M6 a publikacją M7.5. Nie wymaga
perfekcyjnego auto-accept, ale też nie zmienia ręcznej akceptacji w ukrytą
automatyzację.

## Relevant docs

- `requirements/ADMIN_APP.md`
- `requirements/IMAGE_INGESTION.md`
- `architecture/SYSTEM_ARCHITECTURE.md`
- `architecture/DATA_MODEL.md`
- `architecture/API_CONTRACT.md`
- `quality/TEST_STRATEGY.md`
- `process/DECISION_LOG.md` — D-076, D-080, D-081, D-084, D-086 i D-087
- `delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `delivery/MILESTONE_07_EXECUTION_PLAN.md`

## Warunki wejścia

- TASK-0104 wskazuje dokładnie jeden przestrzenny checkpoint do
  productionization.
- Operacyjne `image_review_items`, ich rewizje i staging pozostają źródłem
  prawdy dla importu M7.
- Obrazy nadal są przechowywane jako pliki z checksumą, a nie jako binaria w
  PostgreSQL.
- Lokalny panel i API domyślnie pozostają dostępne wyłącznie przez loopback.

## Zasady realizacji

- decyzja człowieka ma pierwszeństwo przed późniejszą predykcją modelu,
- accepted/corrected zapisuje całą planszę atomowo i append-only,
- ponowne otwarcie planszy nie usuwa wcześniejszej rewizji,
- zmiana geometrii tworzy nową wersję cropów i wymaga ponownego zatwierdzenia,
- model pokazuje sugestie, ale nie zmienia zaakceptowanych etykiet,
- lista tysięcy plansz używa kursorowej paginacji i nie jest ładowana w całości,
- trening pozostaje jawną operacją batchową uruchamianą po zamrożeniu kohorty,
- zdalne udostępnienie nie należy do lokalnej bramki M6.5.

## M6.5.1 — Productionization wybranego modelu

### Zadanie

- `TASK-0105 — Productionize selected spatial symbol model`

### Zakres

- wersjonowany loader checkpointu `spatial-symbol-cnn-v1`,
- eksport ONNX i test parytetu,
- kalibracja confidence na zamrożonym validation,
- maksymalnie cztery uporządkowane alternatywy symbolu,
- dynamiczny vertical slice na aktualnym korpusie,
- nowa checksum-bound decyzja o `massImportAllowed`.

### Bramka G6.5.1

- checkpoint, ONNX, kolejność klas i kalibracja są jednym manifestem,
- PyTorch i ONNX nie mają top-one mismatch poza zaakceptowaną tolerancją,
- test nie uczestniczy w doborze temperatury ani progów,
- panel może otrzymać stabilną predykcję i maksymalnie cztery alternatywy.

Status: `completed`. Manifest
`m6-spatial-symbol-model-release-manifest.json` ma SHA-256
`9f0dd6f7f67105c9c3b479e9b30cb5f9d58d341e6c5b041564be14963a3db8d0`.
Symbol confidence gate przeszedł przy progu `0.88850097`; globalne
`massImportAllowed` pozostaje `false` z powodu `manual_review_only` OCR.

## M6.5.2 — Operacyjna kolejka review

Status: `completed` w TASK-0106. Testy ręczne całego stanowiska pozostają
odroczone do odbioru po TASK-0111; kontrakt API ma testy automatyczne.

### Zadanie

- `TASK-0106 — Operational image review API and cursor queue`

### Zakres

- wybór gry i import joba,
- widoki `Do weryfikacji` oraz `Plansze kompletne`,
- lista i licznik statusów bez ładowania całej kolejki,
- kursorowa nawigacja poprzednia/następna oraz skok do `sequence_number`,
- detail pełnej planszy, 15 komórek, oryginału i bieżącej rewizji,
- atomowe accepted/corrected/rejected dla `image_review_items`,
- generowany klient TypeScript bez ręcznych typów odpowiedzi.

### Bramka G6.5.2

- gra i job ograniczają każdy odczyt oraz zapis,
- kolejność jest deterministyczna i zachowuje `sequence_number`,
- accepted/corrected materializuje dokładnie jeden staging row,
- stale revision i konflikt idempotency key kończą się kontrolowanym `409`,
- zaakceptowany element można ponownie otworzyć i zapisać jako nową rewizję.

## M6.5.3 — Minimalistyczne stanowisko desktop

Status: `completed` w TASK-0107. Ręczna kontrola widoku 1366 × 768 i pełne
testy operatorskie pozostają odroczone do wspólnego odbioru po TASK-0111.

### Zadanie

- `TASK-0107 — Minimal single-board verification workspace`

### Zakres

- kompaktowy header: gra, sequence, pozycja, status, wybór widoku i mały
  przycisk zatwierdzenia,
- przełącznik `Widok planszy` / `Plansze kompletne`,
- pełna siatka 5 × 3 z cropami i podpisanymi symbolami bez przewijania przy
  wspieranym widoku desktopowym co najmniej 1366 × 768,
- wybrana komórka i jej aktualna etykieta widoczne bez otwierania osobnego
  formularza,
- oryginalne, niepocięte zdjęcie poniżej głównej siatki,
- skróty klawiaturowe opisane pod materiałem,
- loading, empty, error, brak obrazu i konflikt rewizji jako jawne stany.

### Bramka G6.5.3

- siatka, etykiety, nagłówek i akcja zatwierdzenia mieszczą się nad foldem,
- oryginał może znajdować się poniżej i nie zmniejsza czytelności siatki,
- plansze kompletne pozostają edytowalne,
- UI nie przekazuje statusu ani niepewności wyłącznie kolorem.

## M6.5.4 — Sterowanie klawiaturą i szybka korekta

Status: `completed` w TASK-0108. Automatyczne testy potwierdzają mapowanie
klawiszy, dwustopniowy zapis, ochronę przed key repeat i konfliktem rewizji.
Ręczny odbiór operatorski pozostaje odroczony do testów po TASK-0111.

### Zadanie

- `TASK-0108 — Keyboard-first review and safe confirmation`

### Zakres

- strzałki lewo/prawo nawigują między planszami,
- kliknięcie komórki ustawia bieżący wybór,
- skróty symboli wynikają ze stabilnej kolejności katalogu gry:
  `1`–`9`, `0` dla dziesiątego symbolu, następnie `QWERTY...`,
- widoczna legenda pokazuje faktyczne mapowanie dla wybranej gry,
- przy wybranej komórce mały tooltip pokazuje 3–4 najbardziej prawdopodobne
  symbole i pozwala je wybrać,
- pierwsze `Enter` otwiera potwierdzenie całej planszy, drugie `Enter` zapisuje;
  `Escape` anuluje,
- skróty są wyłączone podczas pisania w polu, pracy dialogu innego typu albo
  trwającego zapisu.

### Bramka G6.5.4

- pojedyncze przypadkowe `Enter` nie zapisuje danych,
- przytrzymany klawisz i podwójny event nie tworzą dwóch rewizji,
- zmiana symbolu wskazuje konkretną komórkę i jest widoczna przed zapisem,
- cały poprawny layout można zatwierdzić bez użycia myszy,
- skróty mają etykiety dostępności i nie przechwytują pól formularza.

## M6.5.5 — Korekta geometrii i ponowne cropy

### Zadanie

- `TASK-0109 — Review geometry correction and immutable recrop`

### Zakres

- mały przycisk `Edytuj siatkę` w prawym górnym rogu stanowiska,
- edycja czterech narożników na oryginalnym obrazie,
- podgląd ukośnej siatki 5 × 3, wyprostowanej planszy i nowych cropów,
- zapis nowej wersji geometrii oraz plików cropów z checksumami,
- ponowne otwarcie decyzji symboli po zmianie `cropSampleId`,
- zachowanie starej geometrii, cropów i decyzji w audycie,
- osobny eksport zaakceptowanych korekt geometrii do późniejszej analizy
  profili; brak automatycznego zastosowania do innych plansz.

### Bramka G6.5.5

- edycja jednego layoutu nie zmienia geometrii innego,
- etykieta starego cropu nie jest po cichu przenoszona na nowy crop,
- anulowanie nie zapisuje plików ani rewizji,
- po zapisie użytkownik widzi dokładnie te cropy, które będzie zatwierdzał.

## M6.5.6 — Zweryfikowana kohorta i kontrolowany retraining

### Zadanie

- `TASK-0110 — Freeze verified layouts and protect human labels`

### Zakres

- licznik zweryfikowanych plansz per gra i import,
- jawne zamrożenie wybranej kohorty po poleceniu właściciela, np. po 1000 lub
  3000 planszach, bez automatycznego progu uruchamiającego trening,
- niezmienny eksport symboli, geometrii, numerów, źródeł i rewizji,
- trening nowej wersji modelu wyłącznie z zamrożonego eksportu,
- nowa inferencja tylko dla nierozwiązanych plansz,
- zakaz zmiany accepted/corrected przez model lub migrację predykcji,
- kontrolowana publikacja całkowicie ręcznie zweryfikowanego, ciągłego zakresu
  przez staging niezależnie od flagi automatycznego masowego importu.

### Bramka G6.5.6

- ponowienie zamrożenia tego samego stanu daje ten sam checksum,
- nowa rewizja tworzy nową wersję eksportu,
- trening nie mutuje źródłowych decyzji ani wcześniejszego modelu,
- do datasetu trafiają wyłącznie kompletne 15/15 accepted/corrected,
- luki, duplikaty numerów i nierozwiązana geometria nadal blokują publikację,
- `massImportAllowed = false` nadal blokuje automatyczną ścieżkę bez pełnego
  nadzoru człowieka.

## M6.5.7 — Odbiór ergonomii i skali

### Zadanie

- `TASK-0111 — Verification workbench scale and usability acceptance`

### Zakres

- syntetyczna kolejka co najmniej 3000 plansz bez wczytania jej do pamięci UI,
- scenariusz wyłącznie klawiaturą dla poprawnych plansz,
- korekty symbolu, geometrii i wcześniej zaakceptowanej planszy,
- konflikt dwóch kart przeglądarki i exact retry po przerwanym połączeniu,
- pomiar czasu nawigacji, zapisu i manualnej obsługi planszy,
- raport operatorski: plansze/godzinę, zgodność model–człowiek, odsetek
  skorygowanych komórek, odsetek korekt geometrii i wielkość backlogu,
- brak poziomego overflow i widoczność pełnej siatki na 1366 × 768.

### Bramka G6.5

- odczyt sąsiedniej planszy i zapis pozostają bounded dla 3000 elementów,
- p95 lokalnego odczytu/zapisu, bez ponownego cropowania, nie przekracza
  500 ms w profilu odbiorczym,
- jeden operator może wznowić pracę po restarcie bez utraty pozycji i decyzji,
- raport pozwala oszacować czas przeglądu kolejnych 1000/3000 plansz bez
  ukrywania pracy ręcznej jako automatyzacji,
- accepted/corrected nigdy nie są nadpisywane przez późniejszy model,
- ręcznie zweryfikowany, ciągły podzbiór może przejść do walidacji i publikacji,
- automatyczny masowy import nadal wymaga osobnej pozytywnej decyzji jakości.

### Stan wykonania TASK-0111

Fizyczny profil PostgreSQL z 3000 planszami i 45 000 komórek przeszedł
2026-07-29. Odpowiedź klienta pozostała ograniczona do jednej planszy, p95
odczytu sąsiada wyniósł 49,896 ms, a p95 zapisu pełnej decyzji 96,368 ms.
Exact retry nie utworzył drugiej rewizji, konflikt dwóch kart zwrócił
`IMAGE_REVIEW_REVISION_CONFLICT`, a nowa sesja wznowiła kolejkę od pierwszej
nierozwiązanej planszy.

Raport `quality/m65-workbench-acceptance-report.json` zapisuje również
checksum-bound dowody jakości oraz jawną prognozę 328,27 planszy/h. Jest to
prognoza oparta na opisanych założeniach, nie pomiar 3000 ręcznych decyzji.
Krótki odbiór operatora i rzeczywisty pomiar co najmniej 10 plansz pozostają do
wykonania według `quality/M65_WORKBENCH_MANUAL_ACCEPTANCE.md`; do tego potrzebny
jest realny import job `image_directory`.

## Zdalne review — odłożony zakres M8.7

Zdalny link nie jest częścią G6.5. Samo uruchomienie panelu na domowym Wi-Fi
nie udostępnia go osobie w innym mieście. Nie wolno też otwierać surowego portu
routera bez warstwy TLS, autoryzacji, ograniczenia prób i audytu.

Po odbiorze wersji lokalnej M8.7 może zrealizować:

- `TASK-0112 — Remote reviewer threat model and access-session contract`,
- `TASK-0113 — Revocable game-scoped review link and code gate`,
- `TASK-0114 — Secure ingress runbook and remote end-to-end acceptance`.

Docelowo administrator wybiera grę, tworzy ograniczoną czasowo sesję review i
otrzymuje link oraz osobno przekazywany kod. Kod nie jest przechowywany jawnie,
sesję można unieważnić, a użytkownik zdalny ma wyłącznie uprawnienia do
przeglądu i decyzji wskazanej gry. Transport używa HTTPS przez jawnie wybrany
tunel lub VPN; domyślny tryb loopback pozostaje bez zmian.

## Mapa zadań

| Podetap | Zadanie | Zależność |
|---|---|---|
| M6.5.1 Model produkcyjny | TASK-0105 | TASK-0104 |
| M6.5.2 Kolejka operacyjna | TASK-0106 | M7.2 |
| M6.5.3 Minimalistyczny UI | TASK-0107 | TASK-0106 |
| M6.5.4 Klawiatura i sugestie | TASK-0108 | TASK-0105, TASK-0107 |
| M6.5.5 Geometria | TASK-0109 | TASK-0107 |
| M6.5.6 Kohorta i retraining | TASK-0110 | TASK-0108, TASK-0109 |
| M6.5.7 Odbiór | TASK-0111 | TASK-0110 |
| M8.7 Zdalne review | TASK-0112–0114 | G6.5, G8.1 |

## Następny krok

Rozpocząć TASK-0111 i wykonać odbiór ergonomii, dostępności oraz skali lokalnego
stanowiska wraz z odroczonymi scenariuszami ręcznymi TASK-0107–0110. Nie
zaczynać zdalnego dostępu przed lokalnym G6.5 i modelem bezpieczeństwa M8.1.
