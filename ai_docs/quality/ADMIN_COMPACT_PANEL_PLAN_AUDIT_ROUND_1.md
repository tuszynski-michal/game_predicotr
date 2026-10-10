# Audyt planu „Minimalistyczny Panel Administracyjny” (Claude, 2026-10-08)

Werdykt: **REVISE**. Kierunek jest dobry i zgodny z ustaleniami, ale plan nie spełnia
`PLAN_STANDARD.md` i zostawia wykonawcy kilka decyzji bezpieczeństwa i danych,
których planista ma nie delegować. Poniżej uwagi w kolejności ważności. Fakty
z kodu oznaczam „sprawdzone”.

## P0 — blokują akceptację

1. **Kasowanie online przez odbiorcę linku nie jest rozstrzygnięte.** D-533 daje
   odbiorcy „pełne zarządzanie modułem”, a T1 każe zaktualizować „publiczny adapter
   i allowlistę proxy jako jeden pion”, co sugeruje `DELETE` przez
   `/management-api`. Skompromitowany lub pomylony link oznacza wtedy nieodwracalne
   skasowanie wszystkich punktów (migracje 0148/0149 nie mają downgrade, jedyne
   odtworzenie to backup binarny). Zapisz jawną decyzję w D-536: rekomenduję
   `delete-preview`/`DELETE` wyłącznie w lokalnym `/api/v1/admin/management/...`,
   bez odpowiedników w `management_public_structure.py` i bez wpisu w
   `apps/reviewer/src/security/management-proxy.ts`. Jeżeli odpinanie gry przez
   `PUT .../machines/{id}` ma kasować dane, to ta sama decyzja dotyczy publicznego
   `updatePublicManagementMachine` i `updatePublicManagementAssignments`.

2. **„Zamknięte procedury” to hasło, nie projekt.** Sprawdzone: trigger
   `management_history_immutable()` (0148) blokuje `UPDATE` i `DELETE` na
   `management_operations`, `management_journal`, a 0149/0150 dokładają
   `management_result_versions`, `management_search_contexts`,
   `management_session_audit`. Rola aplikacyjna z `scripts/provision_database_roles.py`
   ma tylko DML. Plan musi wskazać mechanizm: funkcja `SECURITY DEFINER` należąca do
   ownera, nadana `EXECUTE` roli aplikacyjnej, która ustawia transakcyjny
   `set_config('management.allow_history_delete', ..., true)` sprawdzany przez
   zmodyfikowaną funkcję triggera; bez `ALTER TABLE ... DISABLE TRIGGER`. Dodaj
   wymóg aktualizacji `storage/management_manifest.py` (wersja
   `management-control-plane-v2`, lista tabel) oraz `provision_database_roles.py --check`,
   bo nowe obiekty muszą przejść istniejące kontrole własności.

3. **Kolejność i zakres kasowania nie są opisane na realnym schemacie.** Sprawdzone:
   `management_journal.point_id` jest `NOT NULL` z FK `RESTRICT`; `machine_id`,
   `game_id`, `before_result_id`, `after_result_id` też `RESTRICT`.
   `management_stake_slots` ma PK `(machine_id, game_id, stake_grosze)` i FK na
   `management_assignments (machine_id, game_id)` `RESTRICT`.
   `management_result_versions` ma `UNIQUE (game_id, content_sha256)`, więc wersja
   jest współdzielona między maszynami tej samej gry, a referencje do niej trzymają
   zarówno `stake_slots.result_version_id`, jak i `journal.before/after_result_id`
   innych maszyn. Plan musi podać kolejność: journal usuwanego zakresu → sloty →
   search_contexts → wersje wyniku bez żadnej pozostałej referencji (sloty i journal
   wszystkich maszyn) → assignments → machines → point, wszystko w jednej
   transakcji po blokadzie UUID operacji i blokadach punkt/maszyna.

4. **Receipty: „usunąć dawne payloady” wymaga `UPDATE` na tabeli immutable.**
   Sprawdzone: `management_operations` ma `operation_id, actor, request_checksum,
   response JSON, created_at`; exact retry zwraca `response` przed walidacją rewizji.
   Plan musi określić: (a) procedura nadpisuje `response` zredagowanym
   potwierdzeniem, (b) retry starej operacji po kasowaniu zwraca jawny kod
   (np. `409 MANAGEMENT_TARGET_DELETED`), nie odtwarza encji i nie zwraca starego
   payloadu, (c) test „stary zapis po usunięciu” obejmuje retry
   create/update/save/clear dla skasowanej maszyny.

5. **Korekty symboli są globalne, a ich ślad w journalu ma `point_id NOT NULL`.**
   Usunięcie maszyny usuwa wpisy `before/after` korekt, które zmieniły wspólne dane
   gry (T1 obiecuje „nie usuwać globalnych korekt symboli”, ale audyt tych korekt
   zniknie). Rozstrzygnij: zachować wpisy korekt z `point_id/machine_id = NULL`
   (zmiana `NOT NULL` w migracji) albo jawnie zaakceptować utratę śladu w D-536.

## P1 — do poprawienia przed implementacją

6. **Niezgodność z `PLAN_STANDARD.md` i `TASK_TEMPLATE.md`.** Brak numerów TASK
   (wolne od TASK-0940; 0933–0939 zajmuje plan Mumii), brak plików tasków, sekcji
   „stan obecny” z potwierdzonymi ścieżkami i symbolami, `Expected files`,
   `Verification` z komendami i limitami czasu, `Risks`, listy `Out of scope` oraz
   mapy wymaganie → task → test (tabela testów nie mapuje punktów z „Docelowy wygląd”).
7. **Tabela modeli łamie zasadę kolumny `Dodatkowy review` i AGENTS.md „Audyt
   krzyżowy”.** Pracę Codex audytuje Claude przed commitem, raport w
   `ai_docs/quality/TASK-NNNN_AUDIT_<model>.md`. Zdanie „plan nie ustanawia
   obowiązkowego audytu modelowego” jest sprzeczne z AGENTS.md. Wpisz w każdym
   wierszu model i poziom, np. T1 i T3: `claude-fable-5-1 / high`, T2 i T4:
   `claude-opus-5-5 / medium`. Odbiór operatora zostaje dodatkowo.
8. **Kolizje z równoległym planem Mumii.** Głowa migracji to `0151_super_game_roles`
   i strażnik schematu startowego wymaga 0151; TASK-0933 planuje tabelę
   partycjonowaną, więc numer 0152 może być zajęty. TASK-0935 zmienia wspólne
   komponenty board-search. Plan musi ustalić kolejność z planem Mumii (numer
   migracji, numery D-, wersje commitów, kolejność merge) i podnieść strażnik.
9. **Decyzja D-536 musi zmienić konkretne dokumenty**, nie „zastąpić archiwizację
   w tym panelu”: `requirements/MANAGEMENT_PANEL.md` („No hard deletion UI”,
   „Detach/archive retains saves/history”), `architecture/MANAGEMENT_PANEL.md`
   („Saved history has no GC or destructive downgrade”, T7: „No new deletion
   mechanism is added”), wpis D-533 („no historical deletion UI”),
   `process/MANAGEMENT_PANEL_OPERATIONS.md` (backup przed kasowaniem),
   `project/TRACEABILITY.md`.
10. **`gameIds` na komendzie maszyny.** Sprawdzone: dziś `ManagementMachineCommand`
    ma `name, archived`, a przypisania idą osobno przez
    `PUT /machines/{id}/assignments` (`ManagementAssignmentCommand.game_ids`).
    Ustal: czy stary endpoint zostaje (kompatybilność testów i klienta), jedna czy
    dwie pozycje w journalu, kolejność blokad (UUID → punkt → maszyna → gry),
    oraz że `PUT` odpinający grę bez ważnego `previewToken` kończy się
    `409 MANAGEMENT_PREVIEW_REQUIRED`. Pole `archived` zostaje w kontrakcie bez
    UI, czy znika w migracji? Co z grami, które przestały być `active`, a są
    przypięte (dziś zostają do jawnego odpięcia)?
11. **`previewToken` bez definicji.** Zapisz: treść (hash posortowanych ID usuwanych
    maszyn/przypisań/slotów + rewizje), stateless HMAC czy zapis w DB, TTL, oraz
    że zmiana rewizji slotu przez refresh wyniku unieważnia token.
12. **Stan nawigacji i reload.** Zapisz, czy widok żyje w URL search params
    (`point`, `machine`, `game`) czy tylko w pamięci. Rekomenduję URL, bo
    odtworzenie po reload, per-tab recovery operacji (sessionStorage, klucz
    `pendingKey`) i „usunięcie w drugim oknie” tego wymagają. Snapshot
    `getManagementSnapshot` jest pobierany raz; określ, kiedy jest odświeżany
    (powrót na listę, 404/409 z mutacji).
13. **Panel linków i wrappery nie są wymienione.** Sprawdzone: UI lokalne to cienki
    wrapper `apps/admin/src/features/management/management-workspace.tsx` plus
    `management-share-panel.tsx` (tylko lokalnie), Reviewer montuje
    `apps/reviewer/src/features/management/management-gate.tsx`, a reszta plików w
    `apps/admin/src/features/management/` to wrappery kompatybilności. Plan musi
    wskazać miejsce panelu linków w nowej nawigacji i że wrappery zostają.
14. **Źródło danych wierszy wyniku.** Sprawdzone: summary slotu ma `chartPoints`
    (≤256), `pinned_spin_positions` i `pinned_points` z wartościami; pełne wiersze są
    paginowane po 50. T3 każe liczyć wiersze „z pełnego wyniku”, co dla spinu 4000
    oznacza wiele stron. Wybierz jedno źródło prawdy (rekomendacja: `pinned_points`
    z summary dla kafelka i widoku, pełny wynik tylko dla rozwiniętej tabeli) i opisz
    stan „punkt niedostępny”.
15. **Miniatura symboli na kafelku stawki.** Jeżeli summary nie zawiera symboli
    planszy startowej, to jest zmiana kontraktu API i musi być w T1 (jedyny task
    kontraktowy), nie w T3. Zweryfikuj `summary` w `management_result_versions`.
16. **Pięć etykiet zapisu bez maszyny stanów.** „Zapisz układ”, „Zapisz zmiany”,
    „Nowy układ”, „Zastąp układ”, „Usuń zapisany układ” trafiają na ten sam
    `PUT .../stakes/{stake}` z `expectedRevision` oraz `POST .../clear`. Dodaj
    tabelę: (brak zapisu / zapis) × (szkic czysty / brudny / nowy start) →
    widoczne przyciski, endpoint, potwierdzenie.
17. **Kafelki wyników „całą powierzchnią”** dotyczą wspólnego `BoardSearchWorkspace`,
    używanego przez zwykłą wyszukiwarkę i udostępnianie jednej gry. Doprecyzuj, że
    usunięcie przycisków następuje tylko w wariancie kompaktowym, a domyślny
    wariant i jego testy regresyjne pozostają.

## P2 — doprecyzowania

18. Ikony Edytuj/Usuń nie mogą być potomkami klikalnego kafelka (`button` w
    `button` jest niepoprawnym HTML, psuje klawiaturę). Zapisz: ikony jako
    rodzeństwo pozycjonowane absolutnie nad kafelkiem.
19. Pamięć „ostatniej gry maszyny”: gdzie (localStorage per maszyna, osobno
    Admin i Reviewer), bez backendu.
20. Test „rollback” w wierszu „Trwałość” znaczy rollback transakcji; migracje
    panelu nie mają downgrade. Napisz to wprost.
21. Wymień komendy weryfikacji z repo: pytest `services/api/tests/test_management*.py`
    i `integration/test_management*_postgres.py` (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`),
    `npm run test:interactions --workspace @game-predictor/board-search-ui`,
    `npm run test --workspace @game-predictor/reviewer` (`management-proxy.test.mjs`),
    `npm run test:geometry --workspace @game-predictor/reviewer`
    (`management-panel.test.mjs`), `npm run openapi:check`,
    `npm run reviewer:management:browser`, każda z limitem czasu.
22. Potwierdzone symbole, które plan może cytować jako sprawdzone:
    `approximateWinPointAtSpin` (`board-search-approximate-win-state.ts:237`),
    `approximateWinStakeToPoint` (:523), `approximateWinMachineCashAtPoint` (:544),
    `managementSavedSelection` (`management/management-slot-state.ts:41`),
    `ManagementMiniChart` (`management-cards.tsx:44`), prop `compact` wykresu
    (`board-search-approximate-win.tsx:876`).
23. Zapisz skalę: 40 punktów, ile maszyn na punkt, limit `game_ids` 200 już
    istnieje w walidatorze.
24. Nazwy modeli (`gpt-6.1-sol`, `gpt-6-sol`) nie są dla mnie weryfikowalne;
    poprzednie plany używały `gpt-6.1-sol` i `gpt-6-astra`. Potwierdź dostępność
    `gpt-6-sol` albo oznacz warunkowo.

## Co jest w porządku

Modal zamiast formularza, atomowy zapis nazwy i gier, szkic chroniony przy
konflikcie, limit dwóch odświeżeń, ochrona domyślnych konsumentów wspólnego
wyszukiwania, brak automatycznego wyboru innej planszy, rozdzielenie resetu szkicu
od usunięcia zapisu, migracja i kasowanie danych operatora poza implementacją.