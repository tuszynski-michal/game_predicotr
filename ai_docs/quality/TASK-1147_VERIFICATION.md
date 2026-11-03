# TASK-1147 — Weryfikacja integracji kodu

Worktree `D:/game_predicotr/worktrees/grid-correction-growth`; HEAD `7881711b`,
dołączany stabilny ref `60f50c64`. Merge bez commita. Dziewięć konfliktów
rozwiązanych w dokumentacji oraz readiness; indeks nie zawiera konfliktów.

## Ochrona połączonych funkcji

0178 ma rodzica `0177_source_replacement_purge`. Nie zmieniono historycznych
migracji 0172–0177. Samo przepięcie rodzica usuwałoby SQL strażników 0175,
ponieważ 0178 ponownie tworzy photo capability i wrapper. Zatwierdzona poprawka
integracyjna stosuje mały `source_recording_replacement_sql.py`: dokładny guard
0175, ten sam lock i filtr aktualnej populacji, zarówno przy instalacji v6,
jak i odtworzeniu legacy v4/v5 na downgrade do 0177. AST upgrade/downgrade
pozostał identyczny z `7881711b`; zmieniły się importowane, złożone definicje SQL.
Nie zmieniono algorytmu splitu, reguł zwolnienia rezerw ani kontraktu API.

## Wyniki

| Kontrola | Wynik |
|---|---|
| PG guarded migration i replacement fence | 1 PASS, 21,03 s; 0178 → 0177 → 0178; runtime wrapper i private photo odrzucają retired/reserved; current i retencja zachowane |
| PG core correction registry | 1 PASS, 54,91 s; v1/v2, ochrony, rollback, release, nowy interpreter |
| PG replacement guards | 1 PASS, 35,57 s; bootstrap, atomowość, restart, replay i retencja |
| API learning, worker dataset/admission | 104 PASS |
| Evaluator v1/v2, częściowe kontrole i restart | 5 PASS |
| Readiness, domena, adapter, replacement guards i retencja jednostkowa | 74 PASS; dwie zastane porażki retencji opisane poniżej |
| UI interakcje korekt i powiązanych paneli | 74 PASS |
| Requesty klienta: korekty/apply/readability/replacement | 9 PASS |
| Scoped ruff/format | 11 plików PASS |
| Scoped mypy | 8 modułów PASS |
| Admin i klient TypeScript; scoped ESLint | PASS |
| Admin production build | PASS; TypeScript 17,0 s, trzy strony statyczne |
| OpenAPI i SDK | Wygenerowane z połączonego backendu |
| Docs:check | PASS, 44765/45000 B; 30 decyzji, 10 zakończonych tasków |
| Mapa kodu | Zregenerowana |

Logi: `artifacts/task1147-*.log`. Polecenia mają timeout120s i jawny PYTHONPATH
worktree. Build i testy korzystają z lokalnych aliasów dla obu klientów oraz
manual-image-selection-core i podścieżki admin-api-client/types. Pierwsze próby
typecheck/build ujawniły wskazanie współdzielonych node_modules na starszy root;
aliasy rozwiązują to wyłącznie w tymczasowym configu. Oryginalne bajty tsconfig
przywrócono w finally. Nie zmieniono konfiguracji działających usług.

## Końcowa kontrola po audycie — P2-1 i P2-3

Audyt Opus zakończył się PASS bez P0/P1. W jednej rundzie uwag dodano
`services/api/tests/test_source_recording_replacement_sql.py`, bez zmian kodu
produkcyjnego. Test porównuje literal strażnika z migracją 0175 oraz przechwytuje
SQL emitowany przez jej rzeczywiste `upgrade()` bez połączenia z bazą. Wrapper
i odcinek photo przywracane na downgrade muszą być identyczne z tym SQL.
Pozostałe przypadki pilnują pojedynczego strażnika, blokady sequence-ownership
i filtra aktualnej populacji w v6. Ochrona wrappera sprawdza currentness członków;
osobny filtr populacji występuje wyłącznie w funkcji photo.

Po ostatniej edycji testu wykonano wyłącznie kontrole bez autofix, zakończone
2026-11-03 o 11:30 CET. Żadnych późniejszych zmian kodu ani formatowania:

| Kontrola końcowych plików | Wynik i log |
|---|---|
| Nowy test SQL oraz readiness | 29 PASS, 4,78 s; `artifacts/task1147-final-unit.log` |
| PG migracja 0178 → 0177 → 0178 i strażniki | 1 PASS, 23,03 s; `artifacts/task1147-final-migration.log` |
| PG replacement guards | 1 PASS, 19,88 s; `artifacts/task1147-final-replacement-guards.log` |
| PG correction registry z nowym procesem | 1 PASS, 50,33 s; `artifacts/task1147-final-registry.log` |
| Ruff format --check oraz check bez fix | 12 plików PASS; `artifacts/task1147-final-lint.log` |
| Scoped mypy | 8 modułów PASS; `artifacts/task1147-final-types.log` |

Testy PG wykonano sekwencyjnie na jednorazowych bazach, każde polecenie z limitem
120 s i jawnym PYTHONPATH worktree. Mapa została ponownie wygenerowana bez zmiany
jej rozmiarów. Nie powtarzano 104 testów API/worker, testów UI ani buildu.
Opcjonalnego dodatkowego wariantu v2 dla fixture replacement fence nie dodano;
istniejący test registry nadal sprawdza polityki v1/v2 i trwałość po restarcie.
P2-1 oraz P2-3 są zamknięte tymi dowodami. Uwagi dotyczące odbioru bez aliasów,
znanych błędów retencji i rewizji bazy przed wdrożeniem pozostają rozliczane
przez prowadzącego w tasku i planie.

## Zastane porażki

`test_grid_cohort_asset_retention.py` ma dwie porażki także na stabilnym `60f50c64`:

- `test_actual_publisher_hard_crash_residue_enters_guarded_gc_after_retention`:
  mock nie ma nowego `source_replacement_gc_guard`; produkt chroni plik fail-closed.
- `test_completed_game_deletion_requires_catalog_route_and_partition_absence`:
  sztuczna sekwencja wyników nie daje oczekiwanego dowodu usunięcia; stan pozostaje unresolved.

Pierwsza próba zakończyła się 68 PASS/1 FAIL; druga z jawnie pominiętą pierwszą
porażką dała 74 PASS/1 FAIL/1 deselected. Obie odtworzono w świeżym procesie,
ładując `storage_gc` z `git show 60f50c64` i potwierdzając identyczność modułu
retencji, publishera oraz testów z tym refem. Dowód:
`artifacts/task1147-retention-baseline.log` (2 FAIL, jawnie baseline).
Nie zmieniono niezwiązanych testów ani mechanizmu GC. Nie powtarzano znanych
legacy reset_game/stats dla uzyskania zielonego wyniku.

## Zachowanie historii

`artifacts/task1147-preservation.json` potwierdza zachowanie pełnych sekcji
archiwum stanu i decyzji obu rodziców; żadna sekcja nie różni się tekstowo.
Indeksy zawierają obie nowe decyzje D-582/D-583, a nadmiar wierszy pozostaje
w archiwum indeksu. Historyczne audyty TASK-1139/1140/1145 nie były zmieniane.

## Odbiór operacyjny — koordynacja po usunięciu blokady

Koordynator zgłosił `GAME_STORAGE_LIFECYCLE_IN_PROGRESS` przy próbie 0172:
stary running delete gry z 2026-10-20. Przywrócił działającą aplikację na 0171.
Operator następnie osobno zatwierdził dokończenie usuwania pustej 777v2,
konfiguracji i przypisania oraz dalszą migrację i wdrożenie. Koordynator
realizuje ten zakres przed przekazaniem okna dla 0178.
Drugie okno zachowuje kontrolę root/main, usług i bazy; ten wykonawca nie
zmieniał ich. Nie wykonano commita, push, migracji operatora, restartu ani uczenia.
Gotowość kodu do focused audytu nie oznacza zakończenia TASK-1147 ani wdrożenia.

Audyt: `TASK-1147_AUDIT_claude-opus-5-5.md`, R1 PASS bez P0/P1.
P2-1/P2-3 zamknięte kontrolami powyżej; P2-2 pozostaje bramką odbioru
bez aliasów w głównym checkout. P2-4 (dwie zastane porażki retencji)
zaakceptowane jako odłożone przez prowadzącego i zapisane w CURRENT_STATE.
P2-5: ponowny odczyt tożsamości/rewizji bazy przed migracją zapisany w planie.
Nie jest to raport pełnego quality PASS ani zakończonego wdrożenia.
