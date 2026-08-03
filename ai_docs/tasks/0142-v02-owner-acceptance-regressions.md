---
title: TASK-0142 — Admin 0.2 owner acceptance regressions
status: in_progress
last_updated: 2026-08-02
---

# TASK-0142 — Admin 0.2 owner acceptance regressions

## Status

`in_progress`

## Goal

Usunąć regresje znalezione przez właściciela podczas końcowego odbioru panelu
Admin 0.2 bez rozszerzania produktu poza zaakceptowany workflow i kontrakt API.

## Context

Techniczna bramka 0.2 przeszła, ale ręczny odbiór wykazał problemy z czytelnością
i stanami akcji w sekcji `Import layoutów`. Kolejne uwagi z trwającego odbioru
będą dopisywane do tego zadania i naprawiane pionami funkcjonalnymi.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/quality/V0_2_ADMIN_ACCEPTANCE.md`

## Scope

- rozdzielić stan operacji od zwykłego stanu `disabled` w imporcie obrazów,
- nadać wszystkim akcjom spójne style i responsywny układ,
- dodać dostępną legendę działań w tooltipie pomocy,
- poprawić prezentację kompletności, luk i wyboru źródeł sekwencji,
- rozszerzyć wybór aktywnej gry na cały kafelek z wyłączeniem osobnych akcji,
- usunąć fałszywy błąd edycji gry po skutecznym zapisie oczekiwanej liczby
  layoutów,
- zastąpić zawodny dialog Windows uruchamiany przez backend standardowym
  selektorem folderu przeglądarki i kontrolowanym uploadem JPEG-ów,
- uprościć wejście sekcji `Symbole` i nadać polu liczby symboli spójny styl,
- uporządkować hierarchię tekstu kafelka gry i przenieść destrukcyjne czyszczenie
  na koniec konfiguracji aktywnej gry,
- naprawić checkpoint importu obrazów i zachować czytelny kod błędu dla
  naruszeń domenowego kontraktu joba,
- podłączyć pod `Rozpocznij import` istniejący pełny pipeline obrazu, aby ten sam
  job po managed originals tworzył cropy, obserwacje komórek i pozycje review,
- wykonać OCR numerów wszystkich plansz jednej strony w pojedynczym batchu,
- prezentować dwufazowy postęp importu jako liczbę rzeczywistych zdjęć w fazie,
  bez sugerowania, że source ingestion i pipeline są osobnymi plikami,
- znormalizować odziedziczone środowisko Windows przed uruchamianiem publicznego
  Reviewera, aby kolidujące `Path`/`PATH` nie blokowały procesów z logami,
- pozostawić zimny start Reviewera i Quick Tunnel ograniczony twardym timeoutem,
  ale uwzględnić rzeczywisty czas uruchomienia Next.js oraz odpowiedzi sieci,
- ograniczyć edytor siatki Reviewera do pojedynczego layoutu z marginesem,
  zachowując zapis narożników względem pełnego obrazu źródłowego,
- pokazać dla image importu datę, godzinę i czas zakończonego automatycznego
  workflow również wtedy, gdy cały job ma status `Wymaga review`,
- uniezależnić kontrolę aktualności wygenerowanego klienta OpenAPI od różnic
  końców linii LF/CRLF na Windows, bez ignorowania zmian semantycznych,
- dopuścić w osobnym Reviewerze sesję przypisaną do gry `draft` albo `active`,
  nadal wykluczając grę `archived`,
- naprawić zapis automatycznego bootstrapu symboli, aby opcjonalna rozdzielczość
  `None` była przekazywana do PostgreSQL jako SQL `NULL`, a nie JSON `null`,
- zabezpieczyć naprawę testami oraz zweryfikować ją w przeglądarce.

## Out of scope

- zmiana modeli, polityki confidence lub semantyki etapów pipeline'u niezwiązana
  z brakującym produkcyjnym podłączeniem image importu,
- masowy import 500 000 rzeczywistych layoutów,
- zmiany aplikacji mobilnej 0.3,
- zamknięcie całego odbioru 0.2 przed zakończeniem testów właściciela.

## Acceptance criteria

- [x] `Wybierz folder`, `Rozpocznij import` i `Odśwież status` nie nachodzą na
      siebie i mają spójne style.
- [x] Zablokowana akcja ma kursor `not-allowed`; kursor postępu występuje tylko
      dla faktycznie wykonywanej operacji.
- [x] Tooltip pod ikoną `?` wyjaśnia działanie wszystkich trzech akcji i jest
      dostępny również z klawiatury.
- [x] Liczniki kompletności i pierwsze luki pozostają wewnątrz karty przy
      wąskim i szerokim widoku.
- [x] Pole numeru sekwencji i akcja `Pokaż źródła` mają czytelny, responsywny
      układ oraz spójne style.
- [x] `Wybierz folder` synchronicznie otwiera standardowy dialog przeglądarki;
      nie uruchamia requestu ani procesu PowerShell przed wyborem plików.
- [x] Kolejność akcji to `Rozpocznij import`, `Wybierz folder`, `Odśwież status`.
- [x] Kliknięcie całego dostępnego kafelka wybiera grę, a przyciski `Edytuj` i
      `Archiwizuj` zachowują własne działanie.
- [x] Edycja oczekiwanej liczby layoutów zapisuje się bez fałszywego błędu;
      nietypowa utrata odpowiedzi jest uzgadniana przez odczyt stanu gry.
- [x] Anulowanie dialogu nie pozostawia stanu operacji, a zmiana gry nie
      przenosi tokenu ani postępu uploadu poprzedniej gry.
- [x] UI pokazuje postęp `Przesyłanie X/Y…`; API waliduje JPEG-i i tworzy token
      dopiero po zgodnej finalizacji, a anulowane/wygasłe stagingi są sprzątane.
- [x] Sekcja `Symbole` nie powtarza nagłówka automatycznego katalogu, używa
      etykiety `Liczba symboli` i ma czytelny responsywny input liczbowy.
- [x] Kafelek gry pokazuje mały stabilny kod bezpośrednio pod nazwą, a cel
      layoutów niżej z czytelnym odstępem od dolnej krawędzi.
- [x] `Wyczyść dane layoutów gry` znajduje się pod wszystkimi zwykłymi sekcjami
      konfiguracji aktywnej gry.
- [x] Import folderu zapisuje pierwszy i kolejne checkpointy zgodnie ze wspólnym
      kontraktem jobów; retry wznawia ten sam job i nie wymaga ponownego uploadu.
- [x] Błąd walidacji domenowej joba zachowuje stabilny kod i bezpieczny komunikat
      zamiast ogólnego `JOB_EXECUTION_FAILED`.
- [x] `Rozpocznij import` uruchamia jeden wznawialny job od zapisania managed
      originals aż do utworzenia rzeczywistych cropów, predykcji i pozycji
      `pending_review`; source-only job nie jest raportowany jako sukces importu.
- [x] OCR do dziewięciu numerów sekwencji ze strony wykonuje jedno wywołanie
      modelu, zachowując osobne rezultaty dla plansz.
- [x] Zakładka `Joby` pokazuje dla image importu `Oryginały: X / N zdjęć` albo
      `Pipeline: X / N zdjęć`, a pasek i procent używają tych samych wartości.
- [x] Kliknięcie generowania linku i awaryjne CLI używają jednego helpera,
      który scala `Path`/`PATH` do kanonicznego `Path` przed `Start-Process`.
- [x] API przekazuje kontrolerowi środowisko bez nazw kolidujących wielkością
      liter; test odtwarza poprzedni konflikt słownika.
- [x] Zimny start ma maksymalnie 60 sekund, z limitami 20 sekund dla Reviewera
      i 30 sekund dla URL Quick Tunnel; nie wykonuje builda w request.
- [x] Edytor geometrii pokazuje pojedynczy layout z kontrolowanym marginesem,
      a nie całe zdjęcie zawierające wiele plansz.
- [x] Przeciąganie narożników w lokalnym widoku jest mapowane do współrzędnych
      oryginału; preview i zapis nadal wykonują ponowny crop z oryginalnego
      obrazu, więc można odzyskać wcześniej przycięty fragment symbolu.
- [x] Ręczna korekta naprawia bieżący layout i nie zmienia niejawnie globalnego
      modelu ani profilu geometrii.
- [x] `Wymaga review` pokazuje datę i godzinę zakończenia importu z pipeline'em
      oraz czas automatycznego przetwarzania bez doliczania ręcznego review.
- [x] Rzeczywisty job dochodzi do `waiting_for_review`, po czym `Symbole` nie
      zwracają `SYMBOL_BOOTSTRAP_NO_CROPS`, a wejście do Reviewera jest aktywne.
- [x] Sesja ograniczona do szkicu gry pokazuje jego plansze i symbole; filtr
      nadal usuwa gry zarchiwizowane.
- [x] Automatyczny bootstrap przy zgodnej liczbie ośmiu grup zapisuje run jako
      `applied` i tworzy osiem symboli bez błędu constraintu PostgreSQL.
- [x] Testy, lint, typecheck i kontrola przeglądarkowa zmienionego pionu
      przechodzą.

## Technical notes

- Brak stylów dotyczy klas istniejących wyłącznie w komponencie importu.
- Jeden boolean `busy` myli niedostępność warunkową z rzeczywistym wykonaniem.
  Komponent otrzyma jawny identyfikator aktywnej operacji i `try/finally`, aby
  błąd transportu nie pozostawiał interfejsu w stanie oczekiwania.
- Naprawa pozostaje lokalna dla sekcji importu poza globalną korektą semantyki
  kursora przycisków `disabled`.
- Poprzednie próby wymuszania `SW_SHOWNORMAL`, właściciela `TopMost` i globalnej
  blokady nie usuwały przyczyny. Finalny flow korzysta z gestu użytkownika w
  przeglądarce; backend obsługuje wyłącznie ograniczony upload i finalizację.

## Expected files

- `apps/admin/src/features/imports/image-folder-import-panel.tsx`
- `apps/admin/src/features/imports/image-folder-import-actions.ts`
- `apps/admin/src/features/games/game-catalog.tsx`
- `apps/admin/src/features/games/game-catalog-actions.ts`
- `apps/admin/src/app/globals.css`
- `apps/admin/test/game-catalog-actions.test.mjs`
- `apps/admin/test/game-catalog-contract.test.mjs`
- `apps/admin/test/image-folder-import-panel-contract.test.mjs`
- `services/api/src/game_predictor_api/application/image_imports.py`
- `services/api/src/game_predictor_api/api/image_imports.py`
- `services/api/src/game_predictor_api/main.py`
- `services/api/tests/test_image_imports_api.py`
- `services/worker/src/game_predictor_worker/images/source_ingestion.py`
- `services/worker/src/game_predictor_worker/images/production_workflow.py`
- `services/worker/src/game_predictor_worker/images/geometry.py`
- `services/worker/src/game_predictor_worker/images/sequence_ocr.py`
- `services/worker/src/game_predictor_worker/cli.py`
- `services/worker/src/game_predictor_worker/jobs/runtime.py`
- `services/worker/tests/test_image_source_ingestion.py`
- `services/worker/tests/test_page_board_detection.py`
- `services/worker/tests/test_production_image_workflow.py`
- `services/worker/tests/test_sequence_number_ocr.py`
- `services/worker/tests/test_job_runtime.py`
- `packages/admin-api-client/src/index.ts`
- `packages/admin-api-client/openapi/openapi.json`
- `packages/admin-api-client/scripts/check-generated-client.mjs`
- `packages/admin-api-client/scripts/generated-client-drift.mjs`
- `packages/admin-api-client/test/generated-client-drift.test.mjs`
- `apps/reviewer/src/features/operational-reviews/operational-review-geometry-editor.tsx`
- `apps/reviewer/src/features/operational-reviews/operational-review-actions.ts`
- `apps/reviewer/src/features/operational-reviews/operational-review-workspace.tsx`
- `apps/reviewer/src/features/operational-reviews/operational-review-state.ts`
- `apps/reviewer/test/operational-review-actions.test.mjs`
- `apps/reviewer/test/operational-review-state.test.mjs`
- `apps/reviewer/test/operational-review-workspace-contract.test.mjs`
- `apps/admin/src/features/reviewer-access/reviewer-access-launcher.tsx`
- `apps/admin/src/features/reviewer-access/reviewer-access-state.ts`
- `apps/admin/test/reviewer-access-state.test.mjs`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/api/tests/test_symbol_bootstrap.py`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/quality/V0_2_ADMIN_ACCEPTANCE.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/tasks/0142-v02-owner-acceptance-regressions.md`

## Verification

```powershell
npm.cmd test --workspace @game-predictor/admin
npm.cmd run typecheck --workspace @game-predictor/admin
npm.cmd run lint --workspace @game-predictor/admin
npm.cmd run build --workspace @game-predictor/admin
npm.cmd test --workspace @game-predictor/reviewer
npm.cmd run typecheck --workspace @game-predictor/reviewer
npm.cmd run lint --workspace @game-predictor/reviewer
npm.cmd run build --workspace @game-predictor/reviewer
```

## Risks / open questions

- Kryteria techniczne regresji są spełnione. Zadanie pozostaje aktywne do
  potwierdzenia przez właściciela jednego testowego wydania, obsługi klawiaturą
  w Adminie i preview cleanup bez wykonywania destrukcyjnego resetu.

## Outcome

Wszystkie zidentyfikowane regresje mają naprawy i dowody automatyczne. Zadanie
pozostaje aktywne wyłącznie na trzy końcowe scenariusze odbioru właściciela.

### Changed

- Zastąpiono wspólny boolean `busy` jawnym identyfikatorem aktywnej operacji.
- Dodano `try/finally`, odrębne etykiety postępu i poprawną semantykę kursora.
- Dodano responsywny toolbar, spójne style przycisków i tooltip pomocy.
- Przebudowano kartę kompletności, listę luk, inspektor źródeł i historię
  importów tak, aby zawartość nie dochodziła do krawędzi i nie nachodziła na
  inne kontrolki.
- Zastąpiono dialog Windows uruchamiany przez backend standardowym selektorem
  folderu przeglądarki, dzięki czemu wybór nie blokuje requestu ani procesu.
- Zmieniono kolejność głównych akcji importu zgodnie z odbiorem właściciela.
- Cały kafelek dostępnej gry wybiera teraz jej kontekst; kliknięcia osobnych
  kontrolek akcji nie są przechwytywane przez kafelek.
- Edycja gry uzgadnia stan przez `GET`, gdy odpowiedź mutacji zaginęła lub nie
  zawiera danych, dzięki czemu skuteczny zapis nie kończy się fałszywym błędem.
- Dodano regresję API dla zmiany `expectedLayoutCount` oraz testy zachowania UI i
  uzgadniania zapisu.
- Panel importu jest montowany z kluczem aktywnej gry, więc jego akcje, token i
  komunikaty nie przeciekają między grami.
- Dodano kontrolowany upload pojedynczych JPEG-ów z postępem, walidacją liczby,
  rozmiaru, względnej nazwy i zawartości oraz finalizacją do istniejącego tokenu.
- Anulowanie i wygaśnięcie usuwa staging; CORS jawnie dopuszcza `PUT` i nagłówek
  `X-Image-Relative-Path`.
- Usunięto trzy redundantne teksty wejścia do automatycznego katalogu symboli,
  zmieniono etykietę pola i dodano jego pełne stany wizualne oraz układ mobilny.
- Zmniejszono stabilny kod i ustawiono go bezpośrednio pod nazwą gry; cel
  layoutów ma osobną linię i większy odstęp pionowy.
- Kontrolę czyszczenia danych przeniesiono pod wszystkie sekcje konfiguracji
  gry, zachowując dotychczasowe zabezpieczenia operacji.
- Checkpoint kopiowania oryginałów zawiera teraz wymagane `schema_version: 1`;
  wcześniej błędny klucz `schemaVersion` zatrzymywał pierwszy checkpoint po 25
  plikach.
- Runtime workera zachowuje stabilny kod i bezpieczny komunikat `JobError`, co
  eliminuje nieczytelne `Handler failed with JobError` przy kolejnej regresji
  kontraktu domenowego.
- Job `be771ee2-e124-463e-8552-e5fe28b912a4` wznowiono bez ponownego uploadu:
  zakończył się statusem `completed`, `739/739`, przy drugiej próbie.
- CLI workera używa teraz `ProductionImageImportWorkflow`: source ingestion
  przekazuje immutable manifest do rejestracji i pełnego pipeline'u, zamiast
  kończyć job po skopiowaniu oryginałów.
- Dodano produkcyjne adaptery normalizacji, detekcji, cropów, OCR i lokalnego
  modelu ONNX oraz zapis review-ready projekcji do PostgreSQL.
- OCR numerów plansz jest wykonywany stronami w batchu do dziewięciu cropów;
  rzeczywisty smoke test modelu wykonał etap dla dziewięciu plansz w około
  2,2 sekundy.
- Techniczne `2 × 739` jednostek postępu image importu jest mapowane w Adminie
  na aktualną fazę i rzeczywiste `X / 739 zdjęć`; etykieta, procent i atrybuty
  dostępności paska używają jednej prezentacji.
- Job naprawczy `65d6ca14-dacc-4341-b015-c187f2d7af36` wznowiono z checkpointu
  po przełączeniu workera na pełny workflow; trwa jego kontrolowane
  przetwarzanie w tle bez ponownego uploadu 739 plików.
- Dodano wspólny helper normalizacji środowiska Windows. Scala wszystkie
  warianty `Path`/`PATH`, zachowuje unikalne katalogi i tworzy jeden kanoniczny
  `Path` przed startem procesów z przekierowaniem logów.
- API rekonstruuje case-insensitive środowisko kontrolera, więc naprawa działa
  również wtedy, gdy API odziedziczyło wadliwy blok od innego launchera.
- Konfigurator trwałego środowiska używa tego samego helpera zamiast tworzyć
  procesowy `PATH` obok `Path`; dodano powtarzalny smoke test procesu potomnego.
- Zwiększono nadal ograniczony cold-start ingressu do 60 sekund: lokalny
  Reviewer ma 20 sekund, a Cloudflare 30 sekund na zwrócenie URL.
- Trwały profil użytkownika został zapisany jednym `Path` oraz wymaganymi
  zmiennymi Node/JDK/Android/Gradle; kontrola odczytu HKCU przeszła w nowym
  procesie.
- Rzeczywisty kontroler uruchomił produkcyjnego Reviewera, otrzymał publiczny
  URL `trycloudflare.com`, potwierdził gotowość i następnie zatrzymał tunel.
  Po teście nie pozostał proces cloudflared ani plik aktywnego stanu.
- Edytor geometrii pokazuje teraz wycinek oryginału skupiony na jednej planszy
  z 25% marginesem zamiast całej strony z wieloma layoutami.
- Widoczne narożniki są projekcją współrzędnych źródłowych do lokalnego
  viewportu. Zapis nadal przekazuje źródłowy quad do istniejącego adaptera
  immutable recrop, bez zmiany API i modelu danych.
- Karta image importu w stanie `Wymaga review` pokazuje w podsumowaniu czas
  zakończenia automatyki, a w szczegółach datę i godzinę zakończenia importu z
  pipeline'em oraz obliczony czas automatycznego przetwarzania.
- Terminalne `finishedAt` zachowuje dotychczasową semantykę całego joba;
  prezentacja granicy automatycznej korzysta z `updatedAt` zapisanego przy
  przejściu do `waiting_for_review`, więc ręczne zatwierdzanie nie powiększa
  pokazywanego czasu.
- Kontrola wygenerowanego klienta OpenAPI normalizuje wyłącznie końce linii
  przed porównaniem. Checkout CRLF na Windows nie daje fałszywego driftu, ale
  zmiana semantyczna nadal przerywa bramkę i wskazuje pierwszy różny znak.
- Odczytowy audyt PostgreSQL potwierdził rzeczywisty job
  `65d6ca14-dacc-4341-b015-c187f2d7af36` w stanie `waiting_for_review`: 739
  plików źródłowych, 4050 plansz, 60 750 obserwacji komórek i 4050 pozycji
  review.
- Usunięto filtr `active` z Reviewera i launchera Admina. Sesja może teraz
  otworzyć grę `draft` albo `active`, ale nadal odrzuca `archived`.
- Pole JSONB `resolution` bootstrapu symboli używa `none_as_null=True`.
  Przejściowy run `ready` zapisuje więc SQL `NULL` zgodnie z istniejącym
  constraintem, po czym atomowo przechodzi do `applied`.
- Na rzeczywistym imporcie utworzono osiem symboli: `cherries`, `grapes`,
  `lemon`, `orange`, `plum`, `seven`, `star`, `watermelon`.
- Produkcyjny Reviewer został przebudowany i sprawdzony na sesji szkicu
  `777 v0.2`: pokazał układ #8, wszystkie 4050 plansz oraz osiem aktywnych
  symboli z sugestiami i skrótami.

### Verification results

- `npm.cmd test --workspace @game-predictor/admin` — passed, 138/138.
- `npm.cmd test --workspace @game-predictor/admin-api-client` — passed, 24/24.
- `pytest services/api/tests/test_catalog_api.py` — passed, 2/2.
- `pytest services/api/tests/test_image_imports_api.py` — passed, 7/7.
- `npm.cmd run openapi:check` — passed.
- skupiony `ruff check` — passed.
- `npm.cmd run powershell:check` — passed, 20 skryptów.
- `npm.cmd run typecheck --workspace @game-predictor/admin` — passed.
- `npm.cmd run lint --workspace @game-predictor/admin` — passed.
- `npm.cmd run build --workspace @game-predictor/admin` — passed.
- `pytest test_job_runtime.py test_image_source_ingestion.py` — passed, 9/9.
- skupiony zestaw pełnego pipeline'u workera — passed, 31/31.
- rzeczywisty smoke test adapterów przez `sequence_ocr` — passed, 9 plansz.
- skupiony mypy `sequence_ocr.py` — passed.
- testy Admina po korekcie postępu — passed, 139/139.
- typecheck Admina i skupiony ESLint zmienionych plików — passed.
- skupiony `ruff check` zmienionych plików workera — passed.
- `pytest services/api/tests/test_reviewer_ingress.py` — passed, 5/5.
- `npm.cmd run powershell:check` — passed, 22 skrypty.
- `npm.cmd run windows:environment:smoke` — passed; jeden `Path` i poprawny
  proces z przekierowanym stdout/stderr.
- `npm.cmd run windows:environment:check` — passed w trwałym profilu użytkownika;
  Node `24.14.0`, npm `11.18.0`, JDK `17.0.20`, ADB `1.0.41`.
- rzeczywisty `ReviewerIngressService` start → HTTPS → stop — passed; publiczny
  URL został uzyskany, a po teście stan to `stopped`.
- pełne testy Admina po naprawie — passed, 139/139.
- typecheck Admina po naprawie — passed.
- testy Reviewera po zmianie edytora geometrii — passed, 21/21.
- typecheck i lint Reviewera po zmianie edytora geometrii — passed.
- produkcyjny build Reviewera po zmianie edytora geometrii — passed.
- build uruchomiono lokalnie i potwierdzono HTTP 200 oraz odblokowanie testowej
  sesji; wszystkie lokalne gry mają obecnie status `draft`, dlatego kontrola
  wizualna samego modala geometrii pozostaje częścią odbioru właściciela po
  aktywowaniu właściwej gry.
- pełne testy Admina po dodaniu statystyk automatycznego workflow — passed,
  140/140.
- typecheck, lint i produkcyjny build Admina po zmianie — passed.
- kontrola przeglądarkowa rzeczywistego joba `65d6ca14-dacc-4341-b015-c187f2d7af36`
  — passed; podsumowanie pokazuje `Automatyka zakończona` i datę, a szczegóły
  `Import i pipeline zakończone` oraz `45 min 53 s`.
- `npm.cmd test --workspace @game-predictor/admin-api-client` — passed, 26/26;
  obejmuje regresję LF/CRLF i wykrywanie rzeczywistej zmiany semantycznej.
- `npm.cmd run openapi:check` — passed z checkoutem Windows CRLF.
- `npm.cmd run v02:admin:acceptance` — passed 2026-08-02: PostgreSQL 4/4,
  Admin 140/140, typecheck, lint, OpenAPI i produkcyjny build Next.js.
- odczytowy audyt rzeczywistego PostgreSQL — passed; job image importu jest w
  `waiting_for_review`, a cropy i pozycje review istnieją.
- Pełny `python:typecheck` został przerwany po 60 sekundach bez wyniku; kontrola
  nie pozostawiła osieroconego procesu. Skupiony mypy ujawnił wyłącznie
  istniejące błędy konfiguracji importów i niezwiązane błędy innych modułów.
- `npm.cmd test --workspace @game-predictor/admin` — passed, 141/141.
- `npm.cmd run typecheck --workspace @game-predictor/admin` — passed.
- `npm.cmd run lint --workspace @game-predictor/admin` — passed.
- `npm.cmd test --workspace @game-predictor/reviewer` — passed, 21/21.
- `npm.cmd run lint --workspace @game-predictor/reviewer` — passed.
- `npm.cmd run build --workspace @game-predictor/reviewer` — passed.
- `pytest services/api/tests/test_symbol_bootstrap.py` — passed, 10/10 z
  repozytoryjnym `--basetemp`.
- skupiony Ruff modeli i testu bootstrapu symboli — passed.
- rzeczywisty `POST /symbol-bootstrap` — passed, status `applied`, osiem symboli.
- produkcyjna sesja Reviewera dla draftu i joba `65d6ca14` — passed.

### Not completed

- Utworzenie jednego testowego wydania w bieżącym flow 0.2.
- Kontrola `Tab`, `Enter` i widocznego fokusu w Adminie.
- Preview cleanup bez wykonania resetu danych.

### Documentation updates

- Uzupełniono wymagania Admina 0.2, raport odbioru i `CURRENT_STATE.md`.

### Recommended next task

- Kontynuować TASK-0142 na podstawie kolejnych uwag właściciela.
