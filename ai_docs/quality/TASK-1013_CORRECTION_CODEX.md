# TASK-1013 — rozliczenie poprawek po Claude high R1

Wykonawca: gpt-6.1-sol, reasoning high. Jedna runda poprawek zlecona przez
leada 2026-10-15. Dokument jest odpowiedzią wykonawcy, nie niezależnym audytem.
Raport [Claude R1](TASK-1013_AUDIT_claude-fable-5-1_R1.md) pozostaje bez zmian.
R2, końcowy werdykt i commit należą do leada.

## Rozliczenie uwag

| Uwaga | Rozstrzygnięcie wykonawcy | Zmiana i dowód |
|---|---|---|
| P0-1 | Naprawiona; oczekuje oceny R2. | Proposal-specific `save` uzupełnia tylko null/undefined qualification kwalifikacją immutable kandydata. Istniejące wyliczone partial/exclude mają pierwszeństwo. Serwer i domyślny manual target bez zmian. UI dla `item.geometryQualification=null` wysyła complete i24nodes; rzeczywiste ciało przechodzi `ProposalAcceptCommand`, kopia z null jest odrzucana. Osobny wariant partial zachowuje pending_partial, unavailable[0] i exclude=true. |
| P1-1 | Naprawiona; oczekuje oceny R2. | Obie nowe tabele dodano do istniejącego zamkniętego zbioru `_provision_partition`. Realne partycje obu nowo provisionowanych gier mają enabled/forced RLS i dokładnie jedną policy. Po jawnym SELECT grant wyłącznie roli fixture bezpośredni odczyt obcego child daje0, własnego1 dla obu tabel. |
| P2-1 | Naprawiona. | Discovery pomija tylko `ImageReviewNotFoundError` z kodem `GRID_PROPOSAL_RESULT_INVALID` z `_candidate`; inny not-found i RuntimeError propagują się. Realny target23nodes nie ukrywa poprawnego kandydata ani zapisanej propozycji, create wadliwego targetu odmawia. Propagację wyjątków sprawdza czysty unit bez połączenia PG. |
| P2-2 | Naprawiona w opt-in helperze. | Merge filtruje board.status=rejected. Unikalność source/position wyklucza duplikaty. Realna regresja odrzuconego rodzeństwa z historycznym wskaźnikiem do reverted source revision odtwarzała409 przed poprawką. Human accept teraz działa; status, geometria, komórki i brak właściciela odrzuconego rodzeństwa pozostają zgodne ze snapshotem. Zwykły mixed-sibling również PASS. |
| P2-3 | Naprawiona. | Workspace używa istniejącego `gridIssueView === 'needs_grid_fix'`; DTO nie ma per-board open-issue flag, więc nie dodano równoległego predykatu ani API. Realny workspace jsdom ma zero GET kolekcji w all, pobiera tylko w widoku zgłoszeń i po powrocie do all ponownie nie pobiera. Sam unmount nie usuwa draftu/UUID. Wcześniejszy lost-response/remount test zachowany i PASS. |
| P2-4 | Przyjęty dług utrzymania zgodnie ze zleceniem leada. | Nie refaktoryzowano frameworka fixture ani miejsca receipts. Coupling prywatnych helperów pozostaje; ogranicza to utrzymanie testów, bez zmiany kontraktu produktu. Safety guard owner/PID przed drop pozostaje nieosłabiony; artefakty dowodzą exact cleanup. |

## Weryfikacja red/green

- `TASK-1013_R2_ui_red.log`: FAIL odtwarzał null zamiast jawnej complete qualification.
- `TASK-1013_R2_ui_scope_red2.log`: FAIL odtwarzał GET kolekcji w all. Pierwszy scope run miał brak progress w fixture; późniejszy green run ujawnił błędny tekst przycisku oraz zbyt ścisłe oczekiwanie jednego GET przy legalnym remount. Logi zachowano, asercja zero GET poza widokiem pozostała.
- `TASK-1013_R2_pg_red.log`: trzy odtworzone FAIL — rejected sibling409, invalid candidate404, nowe child flags false/false/0.
- `TASK-1013_R2_pg_green.log`:4PASS — dwie wersje mixed-sibling, discovery, dwie gry/RLS/composite/lifecycle.
- `TASK-1013_R2_ui_green3.log`:5PASS — discovery/replay, gate widoku i dwa warianty edycji z rzeczywistym walidatorem backendu.
- `TASK-1013_R2_unit.log`:5PASS — dotychczasowe trzy kontrakty i dwa typy propagowanych wyjątków. Format/lint porządkują następnie wyłącznie zapis kontekstów i importów.
- Mypy zmienionych trzech modułów PASS; Reviewer types i scoped ESLint PASS. ESLint uruchomiony z root zgłosił informacyjny brak katalogu pages; pliki nie mają nowych ostrzeżeń reguł. Końcowe format/lint/map/docs/diff oraz SHA są w `artifacts/audits/TASK-1013_R2_IMPLEMENTATION_EVIDENCE.json`.

## Zachowane ograniczenia i dowody

R1 źródła i78 dowodów zostały zachowane przez leada w oddzielnych archiwach.
Live R1 RUNS dostał jeden dodatkowy wpis read-only przed przełączeniem na
oddzielny runner R2; lead zachował dokładny historyczny prefix zgodny z SHA.
R1 raport i manifest nie zostały zmienione.

Dodatkowy `pg_discovery_final` ma wynik **FAIL**: asercje testu przeszły,
lecz teardown zobaczył własny PID i prawidłowo odmówił drop. Po zakończeniu
procesu recovery sprawdził dokładną bazę, właściciela i zero PID, po czym
usunął wyłącznie jej bazę/rolę. `TASK-1013_R2_PG_DISCOVERY_FAILED_RECEIPT.json`
i `TASK-1013_R2_PG_DISCOVERY_RECOVERY.json` zachowują oba stany; recovery
potwierdza również zero pozostałych baz i ról TASK1013. Nie zabijano połączeń.
Mockowane błędy przeniesiono do czystego unit testu. PG4 green pozostaje
dowodem swojego niezmienionego zakresu; dodatkowego FAIL nie przedstawiamy
jako zaliczonego uruchomienia.

Nie powtarzano szerokich wcześniejszych suite bez zmiany ich zakresu.
API/OpenAPI/SDK bez nowej zmiany schematu; wcześniejsze kontrolne PASS
zachowują ważność. Bez operatorDB, usług, GPU/inferencji, aktywacji,
integracji, push, audytu lub commita wykonawcy. Stary layout-data reset
FAIL oraz brak fizycznego odbioru przeglądarki/Androida pozostają ograniczeniami.

## R2 PASS i końcowe rozliczenie P2

[Claude high R2](TASK-1013_AUDIT_claude-fable-5-1_R2.md) zakończył się PASS;
brak otwartych P0/P1. Uzupełniono komentarz testu o skonfigurowanym Pythonie,
Pydantic i `GAME_PREDICTOR_TEST_PYTHON`. API_CONTRACT opisuje pomijanie
strukturalnie niepoprawnego kandydata w kolekcji i jawną odmowę create,
bez deklarowania numeru HTTP.

Uwaga R2 P2-1 dotycząca asynchronicznego cleanup backendu fixture pozostaje
zaakceptowanym długiem razem z R1 P2-4. Bez zmian wait/retry ani refaktoru
testów po PASS. Guard owner/PID pozostaje bez zmian; dokładne recovery
potwierdzające zero zasobów zachowano. Ta końcowa zmiana dotyczy wyłącznie
dokumentacji; sprawdzono Prettier, docs i diff, bez ponawiania testów.
