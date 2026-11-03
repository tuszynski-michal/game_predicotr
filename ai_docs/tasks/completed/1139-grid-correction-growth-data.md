# TASK-1139 — Przyrostowy podział i prawdziwe liczniki

## Status

`done`

## Goal

Nowe korekty bez historycznego użycia zwiększają TRAIN przy zachowaniu kontroli, buforów i weryfikowalności historii.

## Context

Polityka v1 rezerwuje nieopisane ogony. Plan przyrostu zaakceptowany przez operatora 2026-11-03 wraz z kosztem 1–2 godzin.

## Dependencies / entry conditions

TASK-1138 ukończony. Praca w `D:/game_predicotr/worktrees/grid-correction-growth`, gałąź `codex/grid-correction-growth`. Preflight tylko do odczytu; baza operatora pozostaje na 0171.

## Recommended execution

gpt-6-astra / high. Niezależny audyt claude-opus-5-5 / high przed commitem. Sprzeczność ochrony domeny wymaga eskalacji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GRID_CORRECTION_GROWTH_PLAN_20261103.md`
- `ai_docs/requirements/VISION_LAB.md`
- `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md` (sekcja znanej usterki cleanup_reset, linie 101–107)
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-577--podział-korekt-geometrii-z-atestów-i-trwała-ochrona-zdjęć`

## Scope

- Odczyt preflight, nowa jawna polityka, addytywna migracja capability, audytowalne zwolnienia wyłącznie rezerwacji v1 bez ochrony komponentu.
- Liczniki ready/preview, OpenAPI, wygenerowany klient i test żądania.
- Zachowanie historycznych kohort, rzeczywistych użyć, kopii, sesji, holdoutów, ancestry i buforów.

## Out of scope

Migracja operatora, restart, trening, aktywacja, merge/push oraz UI TASK-1140.

## Acceptance criteria

- [x] Stare metadane bez użycia mogą bezpiecznie zwiększyć TRAIN.
- [x] Rzeczywiste kontrole i historia pozostają chronione; nieokreślona ochrona blokuje nowe potwierdzenie dowodu.
- [x] Freeze atomowo zapisuje zwolnienia i przydziały; preview niczego nie zmienia.
- [x] Nowa rezerwa nieopisanych kontroli wynosi najwyżej pięć zdjęć na rolę, bez przepisywania historycznych ochron.
- [x] Minima, atesty, nierozdzielne grupy i bufory dziesięciu zdjęć pozostają obowiązujące.
- [x] Jednostki liczników, deduplikacja i powody wyłączeń są jawne.
- [x] Kontrole zmienionego pionu przechodzą; ograniczenia szerszych testów są jawnie rozliczone jako P2-6.

## Technical notes

Nowa polityka rozdziela rzeczywiste użycie od metadata-only rezerwacji v1. Rezerwy v2 są chronione. Zwolnienia są addytywnymi zdarzeniami istniejącego rejestru, bez modyfikowania zapisanych kohort. Historyczna walidacja kontroluje role faktycznie użytych członków; niewykorzystane historyczne rezerwacje nie mogą unieważniać rzeczywistego dowodu po legalnym zwolnieniu.

## Expected files

- Istniejące: `domain/grid_correction_split.py`, `storage/grid_correction_split.py`, kontrakty i adaptery kohort API/workera, `schemas/grid_correction_learning.py`, `application/grid_correction_learning.py`.
- Proponowane: `domain/grid_correction_incremental_split.py`, `storage/source_recording_sql_v6.py`, `storage/source_recording_permissions_v6.py`, migracja `0172_grid_correction_growth.py`.
- Generowane OpenAPI i klient `packages/admin-api-client`; testy domenowe i integracyjne PostgreSQL.
- Readiness schematu oraz testy guarded downgrade, ochron SQL i metadanych kopii.

## Test cases

Przyrost z nieużytej rezerwacji; zakaz użytej kontroli; alias/sesja/holdout/ancestor; stare dowody po nowym freeze; rollback i restart; dziesięć wszystkich zdjęć bufora; nieznana kolejność; ograniczona rezerwa; minima; izolacja runtime od prywatnych tabel.

## Verification

Bezpośredni pytest zmienionych plików z limitem 120 s na komendę, scoped ruff/mypy, testy request klienta, docs:check i code-map:check. PostgreSQL wyłącznie na disposable test database. Root wykonuje końcowe kontrole i audyt.

## Risks / open questions

Wynik preflight jest potencjałem, nie obietnicą +79 TRAIN. Pełna walidacja etykiet i atestów pozostaje obowiązkowa.

## Outcome

Commit: v1.7.537 (hash dopisuje kolejny commit).

### Changed

- Jawna polityka v2 chronionych wysp zachowuje atesty, kopie/sesje, minima i wcześniejsze bufory; dopuszcza kolejne bloki TRAIN.
- Migracja 0172 rozszerza istniejący prywatny rejestr o niezmienną historię zwolnień i chronione rezerwy v2. Freeze jest atomowy; stare rzeczywiste kontrole pozostają weryfikowalne.
- Tylko aktualne `grid_issue` kwalifikuje nieopisane zdjęcie do ograniczonej rezerwy. Zmiana kolejki po freeze nie wchodzi do historycznego population hash.
- Gotowość i preview mają `progressCounts`; backend, OpenAPI, wygenerowany klient, wrapper oraz test żądania pozostają spójne. Worker przyjmuje v1/v2, w tym częściowe kontrole i wznowienie oceny.
- Po R1: guarded downgrade, readiness 0172, testy zewnętrznych ochron SQL, nieprzezroczyste aliasy i historyczny wyjątek tylko dla zapisanych zwolnień. Rezerwy liczą wyłącznie pending; użycie oznacza zamrożony TRAIN, nie ukończony trening GPU. Zmiana reprezentanta kopii zachowuje tożsamość targetu, a rewizje własnego źródła pozostają ścisłe. Wybór rezerw ma liniowy koszt odległości.

### Verification results

- Audyt Opus 5.5/high: R2 PASS, wszystkie P1 i P2-1–P2-5 zamknięte. Oba raporty zachowane w `ai_docs/quality/TASK-1139_AUDIT_claude-opus-5-5.md` i `_R1.md`. Pierwsza runda miała przerwę po 480 s i została dokończona w tej samej sesji; R2 oceniał dokładny diff względem stanu R1.

Preflight READ ONLY: 788 zdjęć; TRAIN 60/77, VALIDATION 13/17, REGRESSION 13/21; bufory 40 zdjęć (3 zatwierdzone plansze); 662 zdjęcia z nieużytymi rezerwacjami, w tym 44/78 z etykietami. Brak znanych recording_occurrences. Przy odległości ponad dziesięć zdjęć od kontroli: potencjalnie 38 zdjęć/69 plansz, pozostałe 6/9 zbyt blisko.

- Końcowa symulacja domeny na odczytanych metadanych: TRAIN 98/146 (nowe 38/69), VALIDATION 13/17, REGRESSION 13/21, bufory 53 zdjęcia/12 plansz, wykluczenia 9/12; bez bezpiecznych przyszłych rezerw. Nie wykonano freeze ani treningu.
- Domena/adapter/kontrakt: 35 PASS, jeden test baseline odznaczony jawnie.
- API, reader i admission workera: 104 PASS; evaluator v1/v2 z restartem: 5 PASS po użyciu krótkiego katalogu tymczasowego Windows.
- Request klienta: 3 PASS. Scoped mypy: 19 modułów PASS, ruff/format: 28 plików PASS; klient TypeScript PASS.
- PostgreSQL: test migracji, capability, prywatnych uprawnień, rollback, zwolnienia, twardej rezerwy v2 i starych dowodów PASS (52,65 s); świeży interpreter z runtime rolą potwierdził TRAIN oraz dwukrotnie zweryfikował starą i nową kohortę. Ostatni adapter po dopisaniu odmowy sprzecznych ochron: 7 PASS.
- docs:check PASS. Mapa kodu zregenerowana. Szczegóły: `ai_docs/quality/TASK-1139_VERIFICATION.md`.
- Po R1: 54 testy domeny/adaptera/readiness PASS, scoped mypy 20 modułów PASS; guarded migration 1 PASS, istniejący migration lifecycle 5 PASS, crop runs 4 PASS, evaluation bridge 1 PASS. Reinference ma 6 PASS i zastany `cleanup_reset` FK FAIL; stats przerwany przez limit 120 s, bez deklaracji sukcesu. Własne pozostałe zasoby testowe uprzątnięto po kontroli tożsamości. Pełne rozliczenie ograniczeń zawiera verification.
- Końcowy registry lifecycle po korekcie aliasów: PASS (45,83 s), w tym siedem ochron SQL, metadane kopii i nowy interpreter; scoped lint/format 32 plików PASS.

### Not completed

Nie wykonano migracji operatora, restartu usług, uczenia, publikacji, zastosowania, merge/push. Audyt R2 PASS po jednej rundzie poprawek.

P2-6 akceptowane przez prowadzącego jako ograniczenie szerszej weryfikacji: nie ma świeżego porównawczego uruchomienia cleanup_reset na HEAD v536 ani PASS całego stats. Dokładnie ta kolejność DELETE image_review_items przed image_symbol_review_cells i wynik RestrictViolation są jednak udokumentowane w `V3_GRID_FINE_TUNING_ACCEPTANCE.md:101–107` jako FAIL od TASK-0999, identyczny na main. Reset nie zmienia się w tym tasku. Nie naprawiano go dla zielonego wyniku; brak pełnego wyniku stats pozostaje jawny.

P2-7 rozliczone dokumentacją API: ochrona holdout/ancestor/use bez roli blokuje nowe potwierdzenie również zamrożonej kohorty v1. To bezpieczna odmowa, bez zmiany historii. W preflight Mumie A2 brak recording_occurrences, więc ograniczenie nie zmienia policzonego przyrostu.

Zastany test `test_shared_candidate_rejects_correction_policy_before_creating_plan` nadal FAIL. Odtworzenie modułu HEAD i starego identyfikatora polityki w osobnym procesie potwierdziło ten sam `TypeError` przy `session_factory=None`. Nie zmieniono testu ani niezwiązanej logiki dla zielonego wyniku.

### Documentation updates

Decyzja D-582, wymagania i architektura VISION_LAB, API_CONTRACT, preflight oraz końcowy JSON symulacji. CURRENT_STATE i DOC_INDEX utrzymuje prowadzący.

### Recommended next task

TASK-1140.
