---
title: TASK-1010 — Jednoznaczne liczniki i diagnoza obu gier
status: done
last_updated: 2026-10-14
---

# TASK-1010 — Jednoznaczne liczniki i diagnoza obu gier

## Status

`done`

## Goal

Wyjaśnić różnice liczników przez wspólne jednostki i konkretne przyczyny.

## Context

Task jest częścią zaakceptowanej rewizji 6. Kilka źródeł liczników i różne jednostki. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1015; odczyt bazy we właściwym zakresie gry.
- Brak dostępu blokuje pomiar rzeczywistych liczb, nie testy logiki.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. kilka źródeł prawdy i nakładające się stany.
- Dodatkowy review: `claude-fable-5-1`, reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [IMAGE_INGESTION](../../requirements/IMAGE_INGESTION.md).
- [ADMIN_APP](../../requirements/ADMIN_APP.md).
- [DATA_MODEL](../../architecture/DATA_MODEL.md).
- Zakres odczytu uzupełniający z planu: IMAGE_INGESTION, ADMIN_APP, DATA_MODEL, D-484/D-541/D-543.

- [D-484](../../process/decisions/DECISION_LOG_2026.md#d-484--kompletność-geometrii-zdjęcia-jest-bramką-przed-cięciem-na-symbole) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-541](../../process/decisions/DECISION_LOG_2026.md#d-541--lokalny-reviewer-pracuje-w-zakresie-gry-i-pokazuje-realne-braki-geometrii-zdjęć) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-543](../../process/decisions/DECISION_LOG_2026.md#d-543--odrzucanie-przyciętych-plansz-po-imporcie-i-przejęcie-sekwencji-przez-zdjęcie-zastępcze) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-553](../../process/decisions/DECISION_LOG_2026.md#d-553--diagnostyka-pokrycia-v3-i-izolowany-odczyt-liczników) — przyjęta decyzja o odrzuconych slotach oraz opt-in snapshotcie READ ONLY/RLS.

## Scope

- Rozszerzyć istniejący raport pokrycia i diagnostykę, zachowując unikalność sekwencji.
- Dodać rozkład przyczyn i przecięcia kategorii.
- Raport Mumii/777a2 zawiera czas pomiaru i zakres danych.

## Out of scope

- Nie wnioskować o jakości z liczby niepotwierdzonych zdjęć; nie poprawiać danych podczas diagnozy.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Duplikaty, dane kanoniczne, pending, rejected, deferred i nieznane symbole mają jednoznaczne liczniki.
- [x] Brak symbolu nie udaje braku planszy.
- [x] Wszystkie różnice rzeczywistego raportu mają powód albo kategorię nierozstrzygniętą.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Istniejący GET `board-import-coverage/{game_id}` otrzymuje opcjonalne `includeDiagnostics` (domyślnie false). Pokrycie pozostaje sumą zbiorów kwalifikujących się sekwencji review i kanonicznych; symbole nie uczestniczą w predykacie istnienia planszy. Diagnostyka dotyczy całej gry niezależnie od filtra strony. Endpoint otwiera oddzielną transakcję REPEATABLE READ READ ONLY i przypina RLS gry przed odczytem danych domenowych; wszystkie agregaty i raport kompletności zdjęć pochodzą z jednego obrazu. Limit pojedynczego zapytania wynosi 30 s. Nie tworzymy endpointu ani tabel.

Rozkłady rozdzielają rekordy review i ich statusy, unikalne sekwencje, sloty odroczone, plansze ze zgłoszeniem, geometrię niepotwierdzoną, komórki symboli i zdjęcia. Nadmiar kwalifikujących się rekordów nie jest dodatkową planszą. Przecięcia dotyczą brakujących sekwencji z wieloma sygnałami oraz problemów komórek i geometrii. Zapisane odrzucenie slotu jest przyczyną odrzucenia także bez powstałej planszy. Aktualne komórki odrzuconych/superseded plansz i starej geometrii nie wchodzą do problemów symboli.

Panel Admin pobiera kosztowniejsze agregaty osobnym odczytem dopiero po wyborze „Uzgodnij liczniki gry”. Przechowuje własny czas pomiaru; paginacja, filtry i polling pokrycia nie odczytują diagnostyki ponownie. Zmiana gry remountuje kontrolkę i ignoruje spóźnioną odpowiedź. Wykorzystuje istniejącą klasyfikację kompletności zdjęć. Pasmo niskiej pewności `<0,6` pochodzi z istniejącego `apps/admin/src/features/symbol-reviews/symbol-review-state.ts` (`confidenceQuery`, pasmo poniżej 60%). Nie jest oceną jakości modelu ani warunkiem istnienia planszy. Automatyczne cięcie D-523 i stan akceptacji nie stanowią pomiaru poprawności pikseli. `no_source` oznacza brak znanego numerowanego źródła w bazie, bez wniosku o plikach na dysku.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

## Expected files

- Istniejące: [board_import_coverage_repository.py](../../../services/api/src/game_predictor_api/storage/board_import_coverage_repository.py) — `SqlAlchemyBoardImportCoverageRepository`.
- Istniejące: [image_geometry_completeness_repository.py](../../../services/api/src/game_predictor_api/storage/image_geometry_completeness_repository.py) — raport i klasyfikacja kompletności.
- Istniejące: [image_review_repository.py](../../../services/api/src/game_predictor_api/storage/image_review_repository.py) — ochrona decyzji człowieka, licznik korekt.
- Pozostały zakres wskazany w zaakceptowanym planie: istniejące schematy `image_reviews.py`; nowy proponowany `services/api/src/game_predictor_api/application/grid_diagnostics.py` i panel diagnostyki w Adminie.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_grid_diagnostics_and_counters.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.
- Istniejący test integracyjny rozszerzony w rundzie poprawek: `services/api/tests/integration/test_board_import_coverage_repository.py`; rzeczywisty domyślny GET, rejected/pending priority oraz izolowany snapshot/RLS na testowej roli NOBYPASSRLS.

## Test cases

- Duplikaty, dane kanoniczne, pending, rejected, deferred i nieznane symbole mają jednoznaczne liczniki.
- Brak symbolu nie udaje braku planszy.
- Wszystkie różnice rzeczywistego raportu mają powód albo kategorię nierozstrzygniętą.

## Verification

Zakres: API, ADMIN, DOC; odczyty rzeczywistych danych bez zmian.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_diagnostics_and_counters.py services/api/tests/test_board_import_coverage_api.py services/api/tests/test_board_import_coverage.py services/api/tests/test_image_geometry_completeness_domain.py
# Focused interaction tests use Admin's JSX/React configuration.
Push-Location apps/admin
try {
    node ../../node_modules/tsx/dist/cli.mjs --tsconfig tsconfig.json --test test-interactions/grid-diagnostics-panel.test.mjs
} finally { Pop-Location }
node node_modules/tsx/dist/cli.mjs --test packages/admin-api-client/test/grid-diagnostics-request.test.mjs
# Equivalent wider interaction entry point, not repeated after the focused PASS:
# npm run test:geometry --workspace @game-predictor/admin
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
$env:GAME_PREDICTOR_PG_TEST_ROLE = 'application'
.\.venv\Scripts\python.exe -m pytest -s services/api/tests/integration/test_board_import_coverage_repository.py -k 'rejected_slot or diagnostics_snapshot'
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Nie wnioskować o jakości z liczby niepotwierdzonych zdjęć; nie poprawiać danych podczas diagnozy.

## Outcome

### Execution phase

- Faza: implementacja, pomiary, audyt runda 1 i jedna runda poprawek ukończone; gotowe do osobnego commita; lead zamknął P1 na podstawie finalnych testów. TASK-1015 zakończony; bootstrap v1.7.367 / `b35a9ee7dadf3da485427f81a84149e63f0b8cfc` potwierdzony przez leada.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: przygotowany v1.7.368; numer wybrano po sprawdzeniu lokalnych refs zgodnie ze zgodą operatora. Hash zostanie zapisany po commicie.
- Audit: `claude-fable-5-1`, reasoning `medium`, runda 1: REVISE; [niezależny raport](../../quality/TASK-1010_AUDIT_claude-fable-5-1.md) pozostaje niezmieniony. Wykonano jedną rundę poprawek; rozliczenie znalezisk poniżej. Lead rozliczył P1-1 i P2-1–5; brak otwartych P0/P1. [Odpowiedź](../../quality/TASK-1010_AUDIT_RESPONSE_CODEX.md).
- Następny krok: osobny commit i zapis hasha, następnie TASK-1017. Oryginalny audyt REVISE pozostaje zachowany; nie deklarujemy nowego PASS audytu. Brak zgody na automatyczne scalenie lub push.

### Changed

- Addytywne `includeDiagnostics` istniejącego raportu pokrycia, OpenAPI i wygenerowany klient, wrapper oraz test żądania. Default false zachowuje lekki odczyt pokrycia.
- Agregaty rozdzielają sekwencje, rekordy, zdjęcia, sloty, plansze i komórki. Liczba dodanych pozostaje unią sekwencji z odejmowaniem przecięcia kanonu. Odrzucone sloty bez planszy otrzymują przyczynę odrzucenia.
- Komórki wymagają widocznych pikseli/outside, bieżącej rewizji przez bezpośrednie złączenie z recognized_boards i braku rejected/superseded review item. Test obejmuje starą rewizję z source_available=true, kilka zgłoszeń jednej siatki, nakładanie symboli, obcą grę oraz ponowne otwarcie zapisanej bazy fixture.
- Osobna kontrolka Admin pokazuje polskie etykiety, jednostki, przecięcia, pochodzenie stanu bramki i lokalny czas pomiaru. Diagnostyka jest wyłącznie na przycisk; spóźniona odpowiedź starej gry jest ignorowana.
- [Raport rzeczywisty](../../quality/V3_GRID_DIAGNOSTICS_20261014.md): Mumie 491 969 dodanych, 8 031 brakujących (259 geometria, 7 772 no_source); 777a2 341 537 dodanych, 158 463 brakujących (373 geometria, 158 090 no_source). Pending Mumii 262 = 259 brakujących + 3 już dodane. Zła siatka 0/98 plansz; brak akceptacji geometrii nie jest wynikiem jakości pikseli.

### Verification results

- PASS: 120 testów API/domeny/SQL w 46,54 s (`test_grid_diagnostics_and_counters`, `test_board_import_coverage_api`, `test_board_import_coverage`, `test_image_geometry_completeness_domain`); uruchomiono poza sandboxem po zatrzymaniu zawieszonego TestClient w sandboxie. Każdy proces kontroli miał limit 120 s.
- PASS: test żądania klienta `grid-diagnostics-request.test.mjs`; 2 testy UI `grid-diagnostics-panel.test.mjs` (jednostki i etykiety; jawny odczyt oraz spóźniona odpowiedź po zmianie gry). Test UI używa tsconfig Admina.
- PASS: mypy 7 zmienionych plików produkcyjnych/skryptu poza sandboxem, bez osłabienia sprawdzania typów. Dwie próby w sandboxie przekroczyły 120 s. Próba `follow-imports=skip` wykazała sztuczne Any i nie jest dowodem jakości; wynik właściwej kontroli poza sandboxem jest PASS.
- PASS: Ruff zmienionego pionu; Admin lint bez błędów (5 istniejących ostrzeżeń poza zakresem), typecheck Admina i klienta; finalny skoncentrowany lint i typecheck po rozdzieleniu odczytu diagnostyki. OpenAPI i klient wygenerowane z backendu. PASS: aktualność mapy, docs:check i check:generated klienta; finalny diff --check bez błędów.
- PASS: rzeczywiste odczyty aplikacyjną rolą READ/RLS w REPEATABLE READ READ ONLY: Mumie 18:17:34–18:18:22 UTC (48,610 s), 777a2 18:19:06–18:19:23 UTC (16,516 s). Dwa robocze zapytania z dużymi złączeniami przekroczyły statement timeout 30 s; zostały zastąpione finalnym bezpośrednim złączeniem rewizji. Nie ponawiano danych po zaliczonym finalnym pomiarze.

### Not completed

- Commit przygotowany po końcowej kontroli indeksu; integracja i push nie zostały zlecone. Nie wdrożono API do działającej usługi.
- Nie wykonano migracji bazy operatora, treningu, reinferencji, backfillu, aktywacji, odtworzenia kopii ani nowego snapshotu bazy. Nie uruchomiono ani nie restartowano usług. Alembic `head` wykonano wyłącznie na losowych, izolowanych bazach fixture `_test`, następnie usuniętych.
- Przyczyny konkretnych numerów no_source, wpływ 90 błędów plików bez zakresu Mumii i historia przejść 94 zdjęć między zapisaną bramką a bieżącą klasyfikacją pozostają jawnie nierozstrzygnięte. Nie są traktowane jako zmierzone błędy siatki. Pełny build i szeroka bramka quality nie były potrzebne do tej zmiany odczytu.

### Documentation updates

- Task, CURRENT_STATE, raport rzeczywisty, kontrakt diagnostyki i wygenerowana mapa kodu. Zaległe metadane commita bootstrapu poprawione przez leada są zachowane w zakresie następnego commita.

### Audit correction round 1

- **P1-1 zamknięte przez leada dowodami testów:** rzeczywisty domyślny GET z repozytorium PostgreSQL wykazuje `rejected` dla odrzuconego slotu bez planszy, nie zmienia `added`, a dodatkowy pending slot tego samego numeru daje dominujące `waiting_for_geometry`. Drugi test uruchamia rzeczywisty snapshot i pełne agregaty. Sprawdza odrębną sesję/połączenie, REPEATABLE READ, READ ONLY, limit 30 s, przypięte RLS gry, rolę NOSUPERUSER/NOBYPASSRLS, niewidoczność rekordów obcej gry bez filtra bieżącej gry, union=added i zachowanie READ COMMITTED/zapisu sesji żądania.
- **P2-1 zamknięte:** wspólna backendowa `GRID_DIAGNOSTICS_LOW_CONFIDENCE_THRESHOLD` zasila SQL i odpowiedź. Test obejmuje wartości bezpośrednio poniżej, równe i powyżej progu. Frontendowy istniejący `below_60` pozostaje niezależnym kontraktem; jego przyszły drift jest zaakceptowanym ryzykiem wymagającym aktualizacji obu warstw, bez zmiany kwalifikacji plansz.
- **P2-2 zamknięte przez leada:** D-553 accepted; link w Relevant docs. Nie zmieniano logu decyzji w rundzie wykonawcy.
- **P2-3 zamknięte:** Verification wymienia nowe pytest, skoncentrowany test GUI z właściwym tsconfig, test żądania i dwa testy integracyjne. Nie powtarzano szerszego `test:geometry` po skoncentrowanym PASS.
- **P2-4 zamknięte komentarzem i testem RLS:** przed explicit READ/RLS bind wolno odczytać wyłącznie `public.games`; tabel gry nie wolno dodawać przed bindem. Próbne użycie GameStorageSession wykazało ReadOnlySqlTransaction: globalny guard traktuje tekstowe SELECT/WITH jako WRITE i żąda FOR SHARE. Próbę wycofano bez osłabienia globalnego guarda. Finalny kod zachowuje plain Session i połączenie aplikacyjnej roli; test wymusza rzeczywistą testową rolę również dla plain Session na poziomie początku transakcji silnika.
- **P2-5 rozliczone przez leada:** receipt `artifacts/audits/TASK-1010_GENERATED_DIFF_RECEIPT.json` potwierdza, że treść 14 pozostałych generated plików jest identyczna z HEAD; rzeczywiste zmiany dotyczą wyłącznie generated/index.ts i types.gen.ts. Lead odświeżył indeks dokładnych 14 plików bez zmiany treści; staged zawiera wyłącznie zakres taska. `check:generated` PASS przy zgodnych plikach working/staged; bez dołączania obcych zmian.
- **Kontrole rundy:** PASS 12 skoncentrowanych testów SQL/API (38,23 s), mypy 3 zmienionych modułów produkcyjnych i Ruff zmienionego pionu. Finalne integracyjne PostgreSQL: 2 PASS / 9 deselected / 29,45 s, `GAME_PREDICTOR_PG_TEST_ROLE=application`, cel `127.0.0.1:5432/game_predictor_task1010_5778bfc81619_test`. Fixture sprawdza suffix `_test` i różnicę od bazy operatora przed CREATE; wydruk nie zawiera poświadczeń. Baza i rola `game_predictor_app_test_05b9ca3d04ee` zostały usunięte przez fixture. Receipt: `artifacts/audits/TASK-1010_POSTGRES_REPAIR.log`.
- **Nieudana próba, nie PASS:** pierwsze integracyjne uruchomienie na `game_predictor_task1010_bd5c834f6a56_test` dało 1 PASS / 1 FAIL dla próbnego GameStorageSession; ta baza i rola także zostały posprzątane. Finalny run po wycofaniu zmiany jest dowodem zachowania produkcyjnego. Nie powtarzano pełnych odczytów danych operatora ani zaliczonych kontroli GUI.
- Po uwadze leada urealniono fixture: rejected slot numeru 2 ma pozycję 1 w źródle seq1-3, a pending slot ma pozycję 0 w osobnym źródle seq2-2. Ponowiono wyłącznie dwa testy integracyjne; ich finalny wynik i cel są zapisane powyżej. Wcześniejsze zaliczone uruchomienie (29,23 s) na `game_predictor_task1010_03dc58638cae_test` także usunęło bazę oraz rolę `game_predictor_app_test_fe587e739286`.
- Otwarte P0: brak. Otwarte P1 po poprawkach: brak; lead porównał poprawki z zakresem P1. Otwarte P2 wymagające decyzji: brak; kontrole staged i check:generated zakończone PASS. Nie przepisano niezależnego raportu REVISE.

- Audyt uruchomiono z jawnymi --model claude-fable-5-1 --effort medium, plan mode i tylko Read/Glob/Grep; receipt wywołania zachowany. Ponownego audytu nie wykonywano: finalne P1 dotyczyło dodania testów, bez zmiany zachowania produkcyjnego.

- Lead: docs:check PASS (63 aktywne, 10 done, 96 802 B), git diff --cached --check PASS, staged stat/lista 34 plików sprawdzone, check:generated PASS na zgodnym zestawie working/staged.

### Recommended next task

- TASK-1017
