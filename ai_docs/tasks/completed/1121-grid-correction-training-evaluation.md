---
title: Trening i ocena częściowych zdjęć
status: done
last_updated: 2026-11-02
---

# TASK-1121 — Trening i ocena częściowych zdjęć

## Status

`done`

## Goal

Wykonać T2 zaakceptowanego planu uczenia wspólnego modelu siatek z zapisanych korekt.

## Context

Operator ma ponad 100 poprawionych plansz Mumie A2 i potrzebuje uczenia bez ręcznej rejestracji nagrań. Liczba jest deklaracją, nie pomiarem kwalifikujących się danych.

## Dependencies / entry conditions

TASK-1120 ukończony z audytem; polityka i dane dostępne.

## Recommended execution

gpt-6-astra/high, według tabeli planu. Obowiązkowy niezależny audyt Claude Code claude-opus-5-5/high przed commitem; P0/P1 blokują commit. Niedostępność przypisanego modelu wymaga jawnej aktualizacji, bez niejawnej zamiany.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- [Plan i pełny zakres T2](../../delivery/GRID_CORRECTIONS_LEARNING_PLAN_20261102.md)
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`, `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/VISION_LAB.md`, `ai_docs/architecture/CODE_MAP.md`
- [D-554](../../process/decisions/DECISION_LOG_2026.md#d-554--nagrania-i-ochrona-danych-kontrolnych-geometrii-v3)
- [D-556](../../process/decisions/DECISION_LOG_2026.md#d-556--niezmienne-kohorty-geometrii-v3-i-aktualność-dowodów)
- [D-559](../../process/decisions/DECISION_LOG_2026.md#d-559--ocena-kandydata-geometrii-v3-per-gra-i-most-aktualności-dowodów)

## Scope

Pełna sekcja T2 planu; zasady i minima z planu są obowiązujące.

## Out of scope

Trening na danych operatora, zmiana defaultu lub przypisań, migracja bazy operatora, restart usług, merge/push; klasyfikator symboli i uczenie detektora całego ekranu.

## Acceptance criteria

- [x] Same częściowe VALIDATION i REGRESSION przechodzą cały pion bez filtrowania; checkpoint deterministic; scoped report v3 i publish gate v2; legacy bez zmian.
- [x] Właściwe testy, lint/typecheck i dokumentacja (zakres i ograniczenie mypy poniżej).
- [x] Audyt Opus 5.5/high bez otwartych P0/P1.
- [x] Outcome, task-close, osobny wersjonowany commit i record-hash.

## Technical notes

Przed kodowaniem ponownie odczytać ten task i sekcję T2 planu. Chronić istniejące polityki/snapshoty/raporty; nowe reguły wersjonowane. API zmieniać jednym pionem. Mutacje operatora wyłącznie z osobną zgodą. Podgląd nie tworzy dowodu faktycznego użycia danych.

## Expected files

Istniejące: worker `images/grid_cohort_dataset.py`, `grid_training_data.py`,
`grid_training_child.py`, `grid_training_handler.py`, `grid_model_evaluation_handler.py`,
`training_core/grid_training.py`, `grid_training_admission.py`; API cohort/run/evaluation/
publication/shared-candidate services, schemas/routes/SQL capability, jobs runtime/store.
Nowe: czyste metryki/report v3, lexicographic checkpoint, parent learning service/store/
handler/API i migracja0171; pełny wygenerowany klient oraz testy pionów.

Założenie techniczne: parent używa istniejącej kolejki PostgreSQL, zapisuje etap,
zwalnia dzierżawę i slot podczas oczekiwania na dziecko. Claim pomija rodzica do
zakończenia przypiętego dziecka; GET nie wykonuje kroków ani nie zapisuje stanu.
Brak znanej sesji pozostaje photo-only. Nowe formaty nie zmieniają legacy.
D-578 opisuje wersjonowane miary, scope i orkiestrację. Bez nowych usług.


## Test cases

Scenariusze T2 i T4 w planie: minima, brak danych, nowe/stare polityki, aliasy, restart, utracona odpowiedź, konflikty rewizji; zakres testów odpowiedni do zmienionego pionu.

## Verification

Polecenia ustalić z package.json/pyproject i istniejących testów. Każda skończona komenda z timeout <=120 s; build po uprzedzeniu, audyt <=600 s zgodnie ze skillem. Nie uruchamiać szerokich benchmarków.

## Risks / open questions

Preflight i rzeczywista kwalifikacja danych mogą zatrzymać implementację przed błędną obietnicą użycia korekt. Wynik pomiaru należy zapisać w Outcome.

## Outcome

Commit: v1.7.518 / `7801ea4711f92f04eeeb58bfed124f9f850e01e0`.

Uzupełnienie przed audytem (dyspozycja root): preview/ready zwracają nullable
`dataAvailability` z photos/boards po deduplikacji przed buforami, minima20/60,
photoDeficit/boardDeficit jako dolne granice sum i splitStatus minima/infeasible/ready.
Strukturalny błąd adaptera przenosi liczby solvera bez parsowania tekstu; sukces
korzysta z istniejących source pins/representatives, bez dodatkowego odczytu i bez
zmiany persisted split/SHA. Wcześniejszy blocker daje null; nie ma fikcyjnych
per-role braków. Backend/OpenAPI/client/wrapper fixtures i request tests zmienione
w jednym pionie; 58 testów solver/adapter/preview/API PASS; Ruff7/scoped mypy4,
TypeScript klienta, dwa testy wrappera, OpenAPI/generated drift i docs:check PASS.
Szczegóły uzupełnienia w Verification. Audyt R1 po resecie: REVISE; poprawki poniżej.

### Audyt R1 i jedna runda poprawek

Po wznowieniu audyt Opus5.5/high dał REVISE (2 P1, 6 P2). P1-1/P1-2 poprawione:
scoped set_default sprawdza aktualną bazę pod registry lock; realne execute testują
publish/currentness, concurrent default, replay/no-op oraz activate inside/outside scope.
P2-1–P2-6 zaadresowane: mypy main/cli PASS, wspólna definicja full geometry,
409 busy/cancellation-pending, kanoniczne exclusions, spójny status. 38 regresji
PG/publikacji/API PASS. Dyspozycje i kontrole w [Verification](../../quality/TASK-1121_VERIFICATION.md).
R1 zachowany w [raporcie](../../quality/TASK-1121_AUDIT_claude-opus-5-5_R1.md);
focused [runda2](../../quality/TASK-1121_AUDIT_claude-opus-5-5.md) dała PASS, bez
otwartych P0/P1. P2-1 R2 zamyka aktualizacja tabeli planów przy task-close; P2-2
(polska etykieta scope-stale) jest jawną częścią T3. Nie ponawiano pełnego przeglądu75plików. Wcześniejsza blokada infrastruktury pozostaje
w [historii](../../quality/TASK-1121_AUDIT_BLOCKED_20261102.md); heartbeat usunięto przy wznowieniu.

Odbiór T2 zakończony audytem PASS; task-close i osobny commit prowadzi lead.
Dodatkowa regresja nowych gier i snapshotów: 41 PASS (16.26 s). Nie zmieniano
bazy operatora ani usług. Pełny project mypy pozostaje ograniczeniem T4.

Nowy preset `grid-corrections-v1`, snapshot v2, częściowe obie kontrole, wersjonowany
lexicographic checkpoint i evidence w checksummowanym bundle. Raport v3 i gate v2
chronią każdą wymaganą grę/rolę oraz pełne zdjęcia; publication zachowuje currentness,
ale scoped report nie wymaga innych niebadanych gier rodziny. Legacy formaty i reguły
pozostają. D-578, wymagania i architektura opisują nowe zachowanie.

Trwały parent ma pełne API ready/preview/start/list/status/cancel/resume/evaluation.
Używa dotychczasowego cohort service, istniejącego shared training/evaluation i
PostgreSQL jobs. Deterministyczne klucze adoptują dzieci po utracie odpowiedzi.
Parent zwalnia general slot, claim omija go do zakończenia dziecka. Cancel/resume
serializuje tworzenie dzieci bez blokowania heartbeat. GET niczego nie uruchamia.
Metadata preview przypina całą wskazaną populację, default i koszt; runtime/GPU
sprawdza worker przed capture, a admission dziecka ponawia kontrolę i nie zmniejsza
danych. Nieznane sesje pozostają jawnie photo-only.

P2-5 audytu T1: `grid_correction_history.py` i konsumenci shared-run/evaluator
dołączają zweryfikowane historyczne kohorty innych gier z ich oryginalnymi bazami,
rolami i snapshotami. Własne wcześniejsze aktualne korekty pochodzą z wybranej
populacji importów; domyślny ready obejmuje wszystkie importy gry. Hashy/baz historii
nie przepisuje się. Brak jawnych game IDs legacy nie tworzy fikcyjnego scope.
P2-7: nowa polityka jest obsługiwana przez rzeczywisty evaluator zamiast starego
full-only adaptera. P2-6/P2-8/P2-9 pozostają odbiorem TASK-1123 zgodnie z dyspozycją.

T3 otrzymuje dodatkowe `POST /grid-model-evaluations/assigned-comparison`: baseline,
rewizję i descriptor wybiera serwer z aktualnego przypisania. Worker wykonuje
osobną inferencję baseline, raport ma osobne ID/format, główny raport publikacji i
baseVersionId kandydata pozostają nietknięte. T3 odpowiada za receipt apply i końcowy
CAS/currentness. OpenAPI, generated SDK, wrapper i testy żądań spójne; istniejący
Admin renderer obsługuje nowe union bez deklaracji full-photo dla partial.

Weryfikacja: 31 testów dataset/core PASS; 66 testów partial pipeline/admission/schema
PASS; 45 composition/history/legacy/shared/run PASS, następnie 8 nowych
handler/history/pipeline PASS i 5 preview/history PASS. Testy czystych metryk/gate
pomocnika PASS (38), assigned report/schema PASS (30). PostgreSQL: binding v3 i
ochrona ról/buforów PASS; osobno HTTP→parent→evaluation service-entry przy parent
processing, restart/replay/CAS, claim/release, resume tych samych dzieci i budżetu,
cancel po ukończonym dziecku oraz kontrakty API: 29 PASS. Poprzedni test uprawnień
ujawnił SELECT r.*; poprawiono na jawne dozwolone kolumny i minimalne granty katalogu.
135 testów klienta + build/typecheck PASS; Admin typecheck, 35 testów renderer/state/
legacy i scoped ESLint PASS. Ruff format/check zmienionych Pythonów PASS.
Dokładne komendy i ograniczenia: [TASK-1121_VERIFICATION](../../quality/TASK-1121_VERIFICATION.md).

Scoped mypy: 38 zmienionych modułów src PASS, strict z `--follow-imports=silent`;
tymczasowy config pomija wyłącznie implementacje `torch`/`torch.*`. Globalny config
niezmieniony; `main.py`/`cli.py` sprawdzone dodatkowo po R1: 2 PASS. Próba bez tego wyjątku przekroczyła
limit podczas analizy zewnętrznego PyTorch; log w artifacts. To nie jest pełny
project gate. Pełny mypy/build i szerszy odbiór wymagane w TASK-1123 przed merge.

Code-map zregenerowany; końcowy OpenAPI drift check, git diff --check i docs:check
PASS (startup 44092/45000 B, CURRENT_STATE 15295 B).
Nie uruchomiono usług, GPU smoke/treningu, migracji operatora, publikacji, zmiany
defaultu/przypisań, merge/push. Testy inference używają kontrolowanych predictorów;
rzeczywista skuteczność modelu wymaga późniejszego osobno zatwierdzonego eksperymentu.
Metadane record-hash T1 zapisane wcześniej przez root zachowano do commita T2.
