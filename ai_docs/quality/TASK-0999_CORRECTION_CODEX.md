# TASK-0999 — odpowiedź wykonawcy na R1

Data: 2026-10-15. Wykonawca: gpt-6.1-sol/high. Jedna autoryzowana runda korekt.
Baza: v1.7.378 / `d078938b18abdff5d6e1f99795f9d4aca09716b1`.
[R1 Claude](TASK-0999_AUDIT_claude-fable-5-1_R1.md) pozostaje niezmieniony
(SHA256 `d8a255be05953ffd53f80e814249f2af6b1a4b6a28858effedd2b54f4d862250`).
To odpowiedź implementacyjna, nie niezależny audyt. Zamknięcie P1 potwierdza lead
w wymaganym R2 Claude high/do1200s. Wykonawca nie uruchamia audytu ani commita.

## Dyspozycje wszystkich ośmiu uwag

| Uwaga | Realizacja i dowód | Stan do oceny R2 |
|---|---|---|
| P1-1 | Handler potwierdza cancel przez istniejący `context.checkpoint` na granicach capture, stron prepare, źródeł infer, przed transakcją zapisu oraz przez callback kontrolowanego runnera. `finally` zamyka runner. PG `cancel_prepare` i `cancel_between_sources` sprawdzają CANCELLED, zachowanie ukończonych receipts/cursora/modelu, brak dalszego zapisu oraz resume od tego samego miejsca. Test workerowy sprawdza checkpoint i close podczas runner heartbeat. | Naprawiono; proponowane zamknięcie. |
| P1-2 | Enqueue/API start/retry/resume nadal sprawdzają CREATED+PROCESSING. Worker sprawdza PROCESSING innych ID, z nieblokującym admission przed row lock i SKIP LOCKED. Maksymalnie 100 uporządkowanych ID, osobna krótka Session/transakcja per kandydat i RLS gry. Ponowny CAS statusu/expiry/slotu oraz istniejący unique slot chronią race. Diagnostyka podaje reason code. PG dowodzi dwóch dawnych CREATED tej samej gry, blokady pierwszego wiersza i postępu innej gry; recovery expired i cancellation priority; trwale wyłącza 101 nieautoryzowanych kandydatów i dociera do poprawnego joba w następnym bounded wywołaniu. | Naprawiono zgodnie z doprecyzowaniem D-551 zapisanym przed kodem. |
| P1-3 | Nowe `test_grid_reinference_models_and_cursor.py` wywołuje rzeczywiste produkcyjne `model()` bez override tej metody: code7 przed config, non-V3, historyczny current unpublished, jawna inna unpublished/ineligible oraz pozytywna per-game eligibility, assignment revision/version CAS przed startem, zachowanie pina po starcie/resume. Rzeczywisty SQL kursora izoluje grę/operację/SHA, odrzuca ujemny ordinal i sprawdza strony bez duplikatów. PG `late_source` dowodzi niezmiennego membership po capture. | Naprawiono; 15 testów nowego pliku PASS. |
| P2-1 | Nie rozszerzono starego reset graph, nie dodano xfail ani osłabienia testu. `_GAME_RESET_STATEMENTS` pozostaje semantycznie identyczny z HEAD; wcześniejszy pełny `cleanup_reset` nadal ma jawny FAIL przez FK komórek symboli. Detach w istniejącej transakcji i rollback były sprawdzone. | Otwarte ograniczenie niezależnego błędu; decyzję o osobnym zakresie prowadzi lead. |
| P2-2 | `target_fence` używa jawnych domenowych pól pending/owner; pomija operational timestamps/counters. Test wykazuje identyczny fingerprint przy zmianie updated_at/created_at/liczników i konflikt po zmianie expected_geometry_revision. | Naprawiono. |
| P2-3 | Bounded odczyt obcych żywych pending/accepted/corrected pozycji tej sekwencji zasila `foreignOwner`. `target_protection` chroni deferred przed mutacją, także bez canonical. PG dowodzi protected, nie failed, braku nowego review/board i zachowania istniejącego pending. | Naprawiono. |
| P2-4 | Nowe wspólne guardy, obsługa workera, owner docs i testy używają neutralnego `GAME_JOB_ADMISSION_CONFLICT`. Historycznych raportów i decyzji nie przepisano. | Naprawiono według decyzji leada zapisanej przed kodem. |
| P2-5 | Automat odrzuca cancel stanu failed jako `GRID_REINFERENCE_PHASE_CONFLICT` przed zapisem receipt. Test sprawdza kod i niezmienność dokumentu. | Naprawiono. |

## Kwarantanna i granice uprawnień

D-551/plan zostały doprecyzowane przez leada przed zmianami; dowód zapisu:
`artifacts/audits/TASK-0999_QUARANTINE_CONTRACT.json`.
Wyłącznie nowy `grid-reinference-v1` z udowodnionym START_REQUIRED może przejść
z CREATED albo rzeczywiście wygasłego PROCESSING do FAILED/executionQuarantine.
Czyste przejście domenowe używa rzeczywistej walidacji expiry przez
`recover_expired_job`; nie wywołuje `fail_job` z wygasłym tokenem ani cofniętym
czasem. Cancel ma pierwszeństwo i kończy CANCELLED. Frozen SHA/model/payload/
receipts pozostają identyczne, lease/slot zostają zwolnione. Flaga blokuje generic
retry oraz jawny resume również prepare; naprawa wymaga nowej operacji pełne
freeze/start. Zwykły admission/row lock nie kwalifikuje do kwarantanny. Test
jednostkowy odrzuca aktywny lease i stary kontrakt pending_grid_only.

## Weryfikacja i logi

- Focused API/worker/runtime: **48 PASS**, 14.77s, w tym 15 nowych testów realnego
  resolvera/kursora. `artifacts/audits/TASK-0999_R1_FOCUSED_FINAL.txt`.
- PG: **7 PASS / 1 FAIL**, 68.38s w `TASK-0999_R1_PG_FINAL.txt`; jedyny FAIL był
  błędem dodanej fixture (`create_job` bez schema_version), poprawionym bez zmian
  produkcji. Powtórzono tylko ten przypadek: **1 PASS**, 32.30s,
  `TASK-0999_R1_PG_ADMISSION_FINAL.txt`. Osiem docelowych regresji PASS.
- Wcześniejsze próby fixture są oddzielne od wyników końcowych:
  `TASK-0999_R1_PG_QUEUE.txt` zachowuje **1 FAIL / 2 PASS** (44.18s), przyczyną
  była próba mutacji dwóch game stores w jednej transakcji seed. Seed rozdzielono
  na transakcje per gra. Pierwszy zestaw cancellation/ownership miał osobne
  **4 PASS**, 51.21s (`TASK-0999_R1_PG_CANCEL_OWNERSHIP.txt`).
- Każda zakończona fixture PG sprawdziła owner i brak aktywnych PID; usunięto
  wyłącznie własną DB/rolę. Ostatni receipt `TASK-0999_PG_RECEIPT.json` ma
  `phase=cleaned`, `pidsBeforeCleanup=[]`, `databaseRemaining=0`, `roleRemaining=0`.
- Ruff/format **48 plików PASS**. Mypy `--follow-imports=silent`: **33 moduły
  PASS**, 57.849s, 2961 przeanalizowanych modułów zależności, 0 errors;
  `TASK-0999_R1_TYPES_PROGRESS.txt`. Dwie wcześniejsze próby miały hardtimeout55s,
  bez osieroconych procesów. Próba `follow-imports=skip` generowała błędy Any
  importów i nie jest uznawana za walidację. Nie zmieniono reguł typecheck.
- Końcowe docs/map/diff i pełne `openapi:check` z UTF8 **PASS**. Wygenerowane
  klienty Admin i Vision Lab są aktualne. Pozostałe sekcje CURRENT_STATE są
  bajtowo identyczne z R1; cały plik ma 99165 B. Manifest aktualnych SHA:
  `TASK-0999_IMPLEMENTATION_EVIDENCE.json`.
- Focused TestClient ponowiono w uzgodnionym scoped require_escalated po omyłkowym
  sandbox timeout55s; odczyt procesów potwierdził brak osieroconego PID. Bez usług.
- Zachowano wcześniejsze dowody niezmienionych części: regresje wspólnego writera
  102 PASS, registry/resolver 38 PASS, PG 11 PASS + osobne2 PASS, OpenAPI/check,
  client build/transport2 PASS oraz Admin typecheck/cleanup labels4 PASS.
  Nie powtarzano tych zestawów bez związku z korektą.

## Ograniczenia i przekazanie

Wcześniejszy pełny reset pozostaje FAIL, nie PASS/xfail. Nie wykonywano operatorDB,
usług, migracji operatora, rzeczywistego inference/training/GPU, benchmarku30s,
backupu/snapshotu, aktywacji, integracji, push ani audytu własnej pracy. Nie ma
nowej polityki produktu ani rozszerzenia resetu. Manifest i weryfikacje do R2:
`artifacts/audits/TASK-0999_IMPLEMENTATION_EVIDENCE.json` oraz
`artifacts/audits/TASK-0999_PATHS.txt`.
