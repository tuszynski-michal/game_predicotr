# TASK-1172 — jedna runda poprawek po Opus R1

Data: 2026-11-09. Podstawa: `TASK-1172_AUDIT_claude-opus-5-5_R1.md`,
REVISE, 0 P0 / 4 P1. Raportu i receipt R1 nie zmieniano. Poniżej odpowiedź
wykonawcy, nie niezależny audyt. Kod zamrożony do focused R2 prowadzonego przez root.

## P1

| ID | Poprawka i dowód |
|---|---|
| P1-1 | `capture_production_reference` dla v2 wiąże measurement tylko z A, oznaczonym istniejącym `blindGeometry`. TRAIN/B/REG zachowują niezależną etykietę, również z sesji v1/innego kontraktu, i `measurement:null`. Brak importu pozostaje sealed `unavailable` z oryginalnym powodem oraz wybranym kontraktem; nie tworzy fikcyjnego available context. A nadal odrzuca brak importu. SQL test `test_old_blind_labels_outside_a_survive_v2_capture` sprawdza 3 role × available/unavailable, pin i brak mutacji label. |
| P1-2 | `require_render_preflight` stosuje nowe kontrole całej kohorty wyłącznie przy opt-in `evaluationContract`. Legacy v1 zachowuje wczesne sprawdzenie A, bez nowych ograniczeń TRAIN/B. Test rzeczywistego frozen readera potwierdza mieszane B i TRAIN unavailable oraz retry. V2 nadal sprawdza dokładny kontrakt wszystkich obecnych pinów; jawne unavailable poza A pozostaje brakiem dowodu, a nie utratą etykiety. |
| P1-3 | Globalny `_measurement` najpierw wybiera unikalny ready. Dopiero gdy go nie ma, rozważa poprawny diagnostycznie blocked; kilka ready nadal daje brak wyboru. Jawna sesja jest filtrowana przed wyborem. SQL test `test_global_measurement_prefers_unique_ready_but_exact_scope_stays_blocked` pokrywa global ready+blocked, każdy scoped identyfikator i odrzucenie dwóch scoped IDs. |
| P1-4 | Nowy `test_grid_render_selection.py` wykonuje rzeczywiste SQL: blank obok v2, current pass1, v1/v2, dwie sesje, różne poprawne kontrakty, not-ready oraz poprawne A obok starej pustej v1. Osobne testy sprawdzają content_pin z innym kontraktem i strict expectedNone vs v2. |

Dodatkowy edge z prereview root: wyłącznie zamknięty tryb diagnostyczny może przy
expectedNone użyć kontraktu aktualnej sesji A. `content_pin` sprawdza wtedy
document/report oraz Row.oracle SHA, adnotację, render i fingerprint klasyfikatora.
Strict None odrzuca v2. SQL test odczytuje v2 A, dokładny pomiar T2 i historyczny
import8, zachowując osobny measurement0; wrong document/oracle są odrzucane.
Nie zmieniono API ani wyboru aktywnego modelu.

## P2

| ID | Rozstrzygnięcie |
|---|---|
| P2-1 | Pozostaje jawne ryzyko wydajności: resolver/currentness działa per-board. Bezpieczny cache wymaga ograniczenia do transakcji/gry i zachowania currentness przy zmianie aktywnego modelu; nie dodano go w tej rundzie. Nie deklarujemy pomiaru kosztu ONNX na dużej kohorcie. |
| P2-2 | Naprawione. Każdy cel A v2 wymaga measurement, a istniejący czytnik sprawdza jego oracle. Test ma poprawną bazę z dwiema planszami A, a usunięcie measurement albo oracle wyłącznie z drugiej daje odpowiedni błąd. |
| P2-3 | Naprawione. Techniczny receipt oracle bez konfiguracji daje `CONTENT_ORACLE_RENDER_UNAVAILABLE` z rzeczywistym reasonCode; nie jest udawanym drift ani konfiguracją dopisaną do nieudanego renderu. Test przechodzi przez `advance` z trwałym SQL receipt i sprawdza kod oraz brak sfałszowanej konfiguracji. Sesja pozostaje niezdatna do kwalifikacji. |
| P2-4 | Zachowano zaakceptowane ograniczenie: brak pełnego PASS istniejącego treningowego workflow R0–R3. Nie powtarzano1200 kroków, nie osłabiano testu. Różne objawy timeoutu T3/main nie dowodzą wspólnej przyczyny. Wcześniejszy PG pin/freeze/child proof i scoped recovery/preflight pozostają dowodami swojej warstwy. |
| P2-5 | Zachowano konserwatywny wyjątek D597: pełna widoczność jest wymagana przez czytnik blocked; occluded/out_of_frame blokują użycie całego pomiaru w tym wyjątku. Ryzyko użyteczności do jawnego odbioru T4, bez nowej decyzji domenowej w poprawkach. |
| P2-6 | Naprawione/testowane. Nowy ograniczony owned PostgreSQL test zapisuje rzeczywiste oracle30 jako JSONB, wykonuje rzeczywiste `advance` pass1→pass2→frozen oraz odtwarza raport w nowej sesji SQL. Nie przepisuje raportu. PASS1/29.87s. Jawna granica fixture: źródła/cohort admission zastąpione stałą projekcją, bo pełny source/parent pipeline ma wcześniejszy osobny PG proof; nie zastąpiono advance, locks, ORM/JSONB, oracle ani rekonstrukcji. |

## Weryfikacja

- `artifacts/t1172-r1-preflight-final.log`:29 PASS10.04s — SQL selector, strict/diag
  pin, zachowanie etykiet i frozen preflight.
- `artifacts/t1172-r1-regression.log`:73 PASS40.09s — API content, reference/replay,
  D597, zamrożony pipeline i porównania crop. Jedno istniejące ostrzeżenie Torch
  FutureWarning; brak błędów.
- `artifacts/t1172-r1-pg.log`:1 PASS29.87s, disposable PG; nowoprocesowe
  `artifacts/t1172-r1-pg-cleanup.json` potwierdza0 DB/0 runtimeRoles/0 capabilityRoles.
- `artifacts/t1172-r1-mypy.log`:19 plików PASS.
- `artifacts/t1172-r1-final-lint-check.log`:Ruff PASS;
  `t1172-r1-final-format-check.log`:28 plików format PASS.
- API/OpenAPI/SDK/Admin nie zmieniano w R1; wcześniejsze kontrole pionu zachowują
  ważność. Root odpowiada za mapy, docs check i focused R2.

Nie wykonywano odczytów ani zapisów operatorowej bazy w tej rundzie, GPU,
aktywacji/default/margin, reimportu, migracji operatora, usług, deploy, stage,
commita ani własnego audytu. Jedna runda poprawek; P2-1/P2-4/P2-5 są świadomymi,
jawnymi ograniczeniami, pozostałe wskazane pozycje mają poprawkę i dowód.
