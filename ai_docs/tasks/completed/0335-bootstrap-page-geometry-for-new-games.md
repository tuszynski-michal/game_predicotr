---
title: TASK-0335 bootstrap page geometry for new games
status: done
owner: ai
created: 2026-08-30
---

# Cel

Usunąć pusty cold-start nowych gier, w którym `structured_shadow` omija
preflight geometrii, a stabilny primary v20/v19 odrzuca wszystkie źródła przed
utworzeniem plansz.

# Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`

# Zakres

- każdy browserowy import `seq_*` wymaga niezmiennego manifestu geometrii
  strony, również w `structured_shadow`;
- preflight nowej gry bez aktywnego profilu kończy się kontrolowanym manifestem
  `review_required`, a nie `IMAGE_PAGE_GEOMETRY_PROFILE_EMPTY`;
- ręczna korekta strony jest używana jako przypięta kotwica następnego
  preflightu, aby automatycznie spróbować rozwiązać pozostałe źródła;
- nierozwiązane źródła pozostają odroczone i nie trafiają do cięcia ani
  inferencji;
- istniejące joby i fingerprinty pozostają niezmienne.

# Poza zakresem

- promocja Structured Geometry v2 do primary;
- zmiana progów rejestracji;
- automatyczne zatwierdzanie geometrii bez bramek;
- usuwanie historycznych pustych jobów.

# Kryteria odbioru

- nowa gra `structured_shadow` może utworzyć preflight bez wcześniejszego
  profilu;
- pusty profil daje listę źródeł do korekty, nie techniczny błąd;
- po zapisaniu jednej korekty następny preflight wykorzystuje ją jako kotwicę;
- import bez ukończonego manifestu jest blokowany;
- import z manifestem zachowuje shadow jako pomiar i v20/v19 jako primary;
- testy API, workera i Admina, Ruff, mypy, typecheck oraz build przechodzą.

# Outcome

- Browserowy raport obu presetów wymaga manifestu geometrii; start bez
  ukończonego, checksum-bound preflightu jest blokowany.
- Nowa gra może utworzyć preflight z pustym profilem w obu bezpiecznych
  presetach.
  Źródła otrzymują wtedy kontrolowany stan
  `PAGE_GEOMETRY_BOOTSTRAP_ANCHOR_REQUIRED`, a nie techniczny fail.
- Ręcznie zapisany override kompletnej strony jest dołączany jako niezmienna
  kotwica następnego preflightu. Pozostałe strony przechodzą dotychczasową,
  rygorystyczną rejestrację ORB; nierozwiązane źródła pozostają odroczone.
- Admin prowadzi operatora przez korektę pierwszej strony i nie pozwala
  uruchomić primary v20/v19 bez manifestu.
- Nie zmieniono progów rejestracji, schematu bazy ani autorytetu Geometry v2.
