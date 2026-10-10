Przegląd statyczny trwa. Kończę ocenę zamkniętych P1 i przygotowuję raport.

# Audyt TASK-0941 — Kompaktowe punkty i maszyny z nawigacją w głąb

Werdykt: PASS
Audytor: claude-opus-5-5, medium
Wykonawca: gpt-6-sol, medium
Zakres: 0625512d...0625512d4a37072f1d6d44f3f85ef225e7db1835 oraz zmiany niezacommitowane (snapshot `artifacts/audits/TASK-0941_STAGE/audit-source` po ograniczonej rundzie poprawek), data 2026-10-09
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Runda 2 sprawdza tylko poprawki P1-1–P1-4 z rundy 1 oraz związane z nimi P2. Przegląd nie obejmuje zmian TASK-0942. Wszystkie cztery P1 zostały usunięte:

- Modal trzyma rewizję z chwili otwarcia i sygnalizuje konflikt.
- Zewnętrzny guard Admina dostaje łączny stan szkicu.
- Odzyskiwanie zakresu działa raz na operację i namespace, z guardem.
- Dodano wymagane regresje. Geometrię potwierdził pomiar w prawdziwym Chromium, przekazany przez leada jako dowód.

Zostają drobne ryzyka P2. Główne z nich to utrata stylu pól modala po przeniesieniu selektorów CSS na `.management-content`.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `packages/board-search-ui/src/management/management-structure-modal.tsx:155-162` — ryzyko z rundy 1 (ciche ponowne dołączenie legacy `attached=false`) jest teraz jawnie opisane w modalu. Kontrakt backendu się nie zmienił. Propozycja: zaakceptować ryzyko. Ewentualną zmianę kontraktu zrobić w osobnym tasku z wpisem decyzji.
- [P2-6] `packages/board-search-ui/src/management/management.css:236-251` w połączeniu z `management-workspace.tsx` (modal renderowany obok `.management-content`) i `management.css:60-62` — dawny selektor `.management-workspace > form > label > input` obejmował formularz modala. Nowy `.management-content > form > label > input` już go nie obejmuje. Z reguł dla `.management-workspace input` (`:182-189`) pole nazwy zachowuje `width: 100%` i `min-height: 44px`. Traci jednak padding, obramowanie, zaokrąglenie i tło `--panel-soft`. Efekt jest tylko wizualny, bez wpływu na funkcję. Propozycja: dodać `.management-modal > label > input:not([type='checkbox'])` do reguły z `:242-251` i sprawdzić to w odbiorze TASK-0943.
- [P2-7] `packages/board-search-ui/src/management/management-workspace.tsx:390-391,415` — `restoredScopeKey` jest zapisywany przed sprawdzeniem `navigationAllowed()`. Jeśli operator odmówi utraty szkicu, zakres oczekującej operacji nie zostanie już odtworzony. Przycisk „Ponów ten sam zapis” nadal działa. To zgodne z regułą „restore nie zastępuje wyboru bez guardu”. Propozycja: zaakceptować ryzyko albo przenieść zapis klucza za guard.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Tile nie rozciąga się; 4/3/2/1 kolumn; brak przewijania w poziomie przy 390 px | spełnione | `management.css:146-165,177-181`; zgłoszony pomiar Chromium: 10/10 przypadków, kontenery 1000/750/500/320 dają 4/3/2/1 kolumny, max 320 px, brak overflow (dowód leada, nie powtarzany) |
| Home i Cofnij działają, zaznaczenie maszyny/stawki, ikony nie wybierają kafelka | spełnione | `management-workspace.tsx:248-280`; jednorazowe odzyskiwanie `:386-391`; test `apps/admin/test-interactions/management.test.mjs` „pending operation restores once per namespace and focus does not reopen after Home” |
| Modal zapisuje name+games jednym żądaniem; błąd/CAS zachowuje szkic i wymaga świeżego preview | spełnione | `management-workspace.tsx:538-545,562,577` (`baseRevision`), wykrycie konfliktu `:181-202`, komunikat `management-structure-modal.tsx:77-83`; test „focus detects concurrent point edit…” (`expectedRevision` 1, szkic zostaje) |
| Reload/URL/popstate odtwarzają najbliższy poprawny poziom, mpStake nie otwiera edytora, parametry rodzica zachowane | spełnione | `management-workspace.tsx:203-215,309-320,404-413`; testy „structural recovery preserves a valid game and stake…”, „mpStake URL selects its tile without opening a draft editor” (`management-cards.test.mjs`) |
| Pending scope i stara sesja nie przechodzą na innego aktora; recovery bez autoretry | spełnione | `management-workspace.tsx:151-163,179,379`; testy „pending operation from a different namespace…” i „changing the public session namespace drops the previous modal draft” |
| Focus/back/zapis/notfound/conflict odświeżają snapshot; usunięcie w innym oknie nie zostawia aktywnego celu | spełnione | `management-workspace.tsx:240-246,203-215`; test „focus replaces a deleted machine and point URL with the nearest existing ancestor” |
| Dirty draft chroniony na Home/back/popstate/game/zamknięcie modala; legacy archived usuwalne, archiwizacja niewidoczna | spełnione | `management-workspace.tsx:108-139` (łączny stan do `onDirtyChange`), `:281-313`; `apps/admin/src/features/catalog/catalog-workspace.tsx:161-197`; test „outer Admin navigation prompts once and retains a dirty structure modal” |
| Admin i Reviewer używają tego samego UI; link controls tylko lokalnie | spełnione | Bez zmian względem rundy 1; zgłoszone Reviewer geometry 41/41 PASS |

## Listy zamknięte i otwarte

Zamknięte:

- P1-1: `management-workspace.tsx:61,538-545,562,577`. Rewizja jest zamrożona przy otwarciu, a odświeżenie ustawia tylko `editorConflict` (`:181-202`), bez podmiany rekordu.
- P1-2: `management-workspace.tsx:108-114,127-139`. `onDirtyChange(draftDirty || modalDirty)` trafia do `catalog-workspace.tsx:161-164,182,211,272`.
- P1-3: `management-workspace.tsx:378-428`. Odzyskiwanie działa jednorazowo na klucz `namespace:typ:operationId`, po guardzie `:415`, i zachowuje grę/stawkę tej samej maszyny `:405-413`. Usunięto drugi, konkurujący efekt.
- P1-4: nowe testy w `apps/admin/test-interactions/management.test.mjs` (konflikt CAS, jednorazowe odzyskiwanie, zachowanie gry/stawki, izolacja namespace, zmiana sesji, usunięcie w drugim oknie) i `management-cards.test.mjs` (zewnętrzna nawigacja, mpStake). Geometrię 1/4/40 i 4/3/2/1 pokrywa pomiar Chromium, co plan dopuszcza w TASK-0943.
- P2-2: `management-structure-modal.tsx:126-138`. Aktywna gra odłączona występuje raz, z etykietą.
- P2-3: `management-workspace.tsx:282-287,309-313`. Znacznik wygasa w mikrotasku, a panel ignoruje popstate spoza `workspace=management`. Wynik jest poprawny przy obu kolejnościach listenerów, bo katalog przywraca URL przez `replaceState` przed dispatch.
- P2-4: formatowanie `🗑` poprawione w diffie; zgłoszony Prettier i lint PASS.
- P2-5: `management.css:161-165,177-189`. `container-type` jest teraz na wrapperze `.management-content`, modal jest jego rodzeństwem, a limit 320 px dotyczy tylko kafelków. Pomiar potwierdził wyśrodkowanie modala.

Otwarte: P2-1 (akceptacja ryzyka), P2-6, P2-7.

## Proponowane testy

- Statyczna lub przeglądarkowa asercja stylu pola nazwy w `.management-modal` (padding i obramowanie jak w pozostałych polach), w bramce przeglądarkowej TASK-0943 (`scripts/verify_management_panel_browser.mjs`).
- Odzyskiwanie przy brudnym szkicu stawki i odmowie w `confirm`: lokalizacja zostaje, a przycisk ponowienia jest dostępny (`apps/admin/test-interactions/management.test.mjs`, `npm run test:geometry --workspace @game-predictor/admin`).

## Zakres przeglądu i ograniczenia

Przeczytano ze snapshotu `audit-source`:

- `management-workspace.tsx:55-623`;
- `management-structure-modal.tsx:62-171`;
- `management.css:46-62,140-251`;
- fragment `apps/admin/src/features/catalog/catalog-workspace.tsx:155-219,569-574`;
- diff poprawek wraz z nowymi testami Admin z briefu.

Nie uruchamiano testów, lintu, typechecku, Prettiera ani przeglądarki. Wyniki 39/39 Admin, 41/41 Reviewer i pomiar Chromium 10/10 przyjęto jako zgłoszone dowody. Nie oceniano zmian TASK-0942, w tym nowego błędu testu anulowania. Nie czytano pełnych `CURRENT_STATE.md` ani `DECISION_LOG.md`. Nie sprawdzono statycznie, jak listenery `popstate` są uporządkowane w natywnej przeglądarce. Analiza pokazuje, że wynik nie zależy od tej kolejności.
