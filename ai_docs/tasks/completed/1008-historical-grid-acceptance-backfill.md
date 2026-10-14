---
title: TASK-1008 — Historyczna akceptacja bez ponownego cięcia
status: done
last_updated: 2026-10-14
---

# TASK-1008 — Historyczna akceptacja bez ponownego cięcia

## Status

`done`

## Goal

Uzgodnić historyczne statusy przy zachowaniu istniejącej geometrii.

## Context

Task jest częścią zaakceptowanej rewizji 6. Historyczne statusy i atomowe projekcje. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- TASK-1017 done, v1.7.369 / `5451da2ea2df923a7e8788731ceb58c6ba2915b3`; D-550 accepted. Próba niezależnego audytu TASK-1017 przekroczyła480 s, brak PASS jawnie zapisany zgodnie z wyjątkiem AGENTS.md. Wykonanie historycznej akceptacji na danych operatora dopiero po podglądzie i potwierdzeniu.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. D-550/D-552 przyjęte na podstawie wcześniejszych poleceń; D-548/D-549/D-551 pozostają proposed dla własnych zależnych zakresów.

## Recommended execution

- Wykonawca: `gpt-6.1-sol`, reasoning `high`. masowa operacja na stanach i projekcjach.
- Dodatkowy review: `claude-fable-5-1`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [DATA_MODEL](../../architecture/DATA_MODEL.md).
- Zakres odczytu uzupełniający z planu: D-484/D-485/D-541, DATA_MODEL, zasady operacji danych.

- [D-484](../../process/decisions/DECISION_LOG_2026.md#d-484--kompletność-geometrii-zdjęcia-jest-bramką-przed-cięciem-na-symbole) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-485](../../process/decisions/DECISION_LOG_2026.md#d-485--bramka-kompletności-stan-trwały-zdjęcia-dokument-sekwencji-bez-dowodu-symboli-przepinanie-plansz-uzupełnia-d-484) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.
- [D-541](../../process/decisions/DECISION_LOG_2026.md#d-541--lokalny-reviewer-pracuje-w-zakresie-gry-i-pokazuje-realne-braki-geometrii-zdjęć) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Podgląd, zamrożony zakres, idempotentne uruchomienie, kursor i raport.
- Dla źródła jedna transakcja: kontrola rewizji, akceptacja, `materialize=False`, synchronizacja istniejących dokumentów wyszukiwania, receipt.

## Out of scope

- Bez modelu, recropu i tworzenia komórek; brak automatycznego wykonania na całej grze.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [x] Awaria między statusem a projekcją cofa całość.
- [x] Powtórzenie nie dubluje zdarzeń.
- [x] Wycinki, approval, payloady i właściciele są identyczni przed/po.
- [x] Mieszane rewizje nie są akceptowane na skróty.
- [x] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

- Istniejący router `image-review-items` otrzymał pięć operacji pod
  `geometry-completeness/{gameId}/historical-acceptance`: create,
  preview-next, confirm, run-next i raport z paginacją szczegółów. Kontrakt
  `schemas/grid_engine_acceptance.py` jest źródłem OpenAPI; klient generowany,
  wrapper i test żądania realizują ten sam pion. Nowe UI w diagnostyce zostało
  zgłoszone leadowi przed zmianą i potwierdzone jako zakres planu.
- Podgląd tej gry zapisuje kotwicę czasu DB i stabilny kursor UUID. Późniejsze
  źródła są wyłączone przed paginacją. Kwalifikacja utrwala revision id/number,
  status, fingerprint chronionych danych i oryginalnego inputu joba oraz powody.
  Stan `previewed` zamyka zakres. `confirm` wymaga literalnego `confirmed=true`,
  osobnego klucza i zgodnego hash polecenia; dopiero wtedy wolno wykonywać run.
- Kwalifikacja jest historyczną operacją, nie wywołaniem fresh-only finalizatora
  TASK-1017. Wymaga zarejestrowanego oryginalnego snapshotu modelu, zgodnych
  source hash/dimensions/normalization, pełnego proposal/binding i exact neural
  lattice oraz kompletnego zakresu pozycji. Sprawdza aktualne board/cell/render
  revisions, właścicieli review/canonical/search, odroczenia i bieżące grid issue.
  Ręczna geometria, wyjątek operatora, nieznany model, brak dowodu, mieszane lub
  niejednoznaczne rewizje mają jawny skip; nie ma fallbacku do `.current`.
- Blokady przebiegu: klucz/operacja, ownership gry, wiersz gry i operacji,
  rosnące sequence locks, source row. CAS i ponowna kwalifikacja chronią target.
  Status, `recompute_source_image_geometry_completeness(materialize=False)`,
  synchronizacja tylko istniejących projekcji, receipt/zdarzenie, kursor i
  przyrostowe liczniki są jedną transakcją źródła. Błąd cofa całość. Receipt
  odtwarza ten sam klucz; inny command hash albo nowy klucz ze starym kursorem
  zwraca 409. Nie ma nowej materializacji, inferencji, recropu ani zmiany
  geometry payload/checksum, cropów, approval, decyzji czy canonical owners.
- Addytywna migracja `0155_historical_grid_acceptance` została wybrana po
  potwierdzeniu pojedynczego head `0154_geometry_correction_revert`. Tabele
  operacji, targetów i receiptów są partycjonowane per gra pod FORCE RLS;
  bieżący manifest to v8. Zamrożone migracje i manifesty v7 są zachowane,
  fixture historyczne jawnie rozróżniają stare heady. Downgrade odmawia
  utraty istniejącej historii. Migracji operatora nie wykonywano.
- Oryginalny manifest ma wznawialny pomocniczy indeks
  `historical-neural-evidence-index-v1`, opisany w schema ownership. Budowa
  checkpointuje offset bajtowy na granicy wpisu, także UTF-8, w niepublikowanym
  `.building.sqlite`: 1000 wpisów lub 15 s/krok, maksymalnie 2 MiB/wpis.
  Pełna kontrola SHA jest oddzielną fazą z limitem 30 s i dopiero ona pozwala
  atomowo opublikować indeks. Restart wznawia checkpoint, gotowy uszkodzony
  indeks odtwarza preview; run nigdy nie buduje go pod source lock.
- Limit SHA nie jest udowodnioną wydajnością dużych importów. Przekroczenie
  zatrzymuje UI z `HISTORICAL_EVIDENCE_VERIFICATION_TIME_LIMIT`, zachowuje
  przygotowanie i kursor, blokuje confirm; nie tworzy skip/PASS. Do wznowienia
  służy ten sam operationId. Mały odczyt stat plików operatora zlecony przez
  leada objął dwa joby na grę: Mumie 28 898 319–74 772 916 B,
  777a2 277 108 530–329 146 197 B. Nie czytano zawartości tych manifestów,
  nie liczono ich SHA, nie uruchamiano inferencji ani backfillu.

## Expected files

- Istniejące: [image_geometry_completeness_repository.py](../../../services/api/src/game_predictor_api/storage/image_geometry_completeness_repository.py) — raport i klasyfikacja kompletności.
- Istniejące: [image_geometry_completeness_state_repository.py](../../../services/api/src/game_predictor_api/storage/image_geometry_completeness_state_repository.py) — `recompute_source_image_geometry_completeness`.
- Istniejące: [board_search_projection_repository.py](../../../services/api/src/game_predictor_api/storage/board_search_projection_repository.py) — `sync_review_items`, `stale_review_item_ids`.
- Pozostały zakres wskazany w zaakceptowanym planie: istniejący `scripts/backfill_image_geometry_completeness.py` jako wzorzec wznowienia; nowe proponowane `services/api/src/game_predictor_api/application/grid_engine_acceptance.py`, repozytorium operacji i UI podglądu.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_historical_grid_acceptance_backfill.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Awaria między statusem a projekcją cofa całość.
- Powtórzenie nie dubluje zdarzeń.
- Wycinki, approval, payloady i właściciele są identyczni przed/po.
- Mieszane rewizje nie są akceptowane na skróty.

## Verification

Zakres: API, MIG dla nowych zapisów operacji, ADMIN, DOC.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_geometry_completeness_domain.py services/api/tests/test_image_geometry_completeness_api.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez modelu, recropu i tworzenia komórek; brak automatycznego wykonania na całej grze.

## Outcome

### Execution phase

- Faza: implementacja i skoncentrowana weryfikacja zakończone, oczekiwanie na audyt leada; current HEAD v1.7.369 / `5451da2ea2df923a7e8788731ceb58c6ba2915b3`.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: nie utworzono; następny patch ustalić z rzeczywistej historii gałęzi.
- Audit: uruchomiony `claude-fable-5-1`, reasoning `high`, wyłącznie Read/Glob/Grep i stdin zamknięte. Timeout480 s bez końcowego raportu. [Dowód i ograniczenie](../../quality/TASK-1008_AUDIT_TIMEOUT_CODEX.md). Brak PASS; jawny wyjątek AGENTS.md pozwala kontynuować bez ponawiania. Lokalne metadane potwierdziły rzeczywistą pracę modelu aż do limitu.
- Następny krok: lead odczytuje `artifacts/task1008-scope.json`, wykonuje jeden niezależny audyt Claude high z zamkniętym stdin, rozlicza uwagi, ustala wersję z historii i tworzy commit TASK-1008.

### Changed

- Zaimplementowano historyczną operację status-only, zamrożone targety,
  wznawialny podgląd, jawne potwierdzenie, krótki run per źródło i raport.
- Dodano migrację 0155/manifest v8, game-scoped RLS i receipty/zdarzenia.
  Writer i globalne guardy nie zostały poluzowane; historyczne v7 zachowano.
- Zgodny pion API obejmuje backend, OpenAPI, generowany klient, wrapper,
  test żądania i UI w diagnostyce. UI automatyzuje kroki po potwierdzeniu
  i zachowuje operationId/klucze po utracie odpowiedzi lub reload.
- Dowody oryginalnego modelu mają ograniczony, wznawialny indeks pomocniczy;
  brak dowodu i niejednoznaczność są jawne, bez fallbacku/inferencji.
- Zmiany aktualnych fixture manifestu są wyłącznie dostosowaniem do head v8;
  historyczne heady nadal wybierają zamrożony v7.

### Verification results

- Własny PostgreSQL pod rzeczywistą rolą NOBYPASSRLS: 7 testów PASS w 73,44 s;
  następnie 3 nowe/zmienione granice PASS w 77,24 s (6 przypadków deselected).
  Upgrade 0155, no-history downgrade/up i dodanie partycji istniejącej gry v7
  zaliczone. Awaria projekcji cofa status, receipt i kursor. Replay nie dubluje
  zdarzeń; chronione pełne rekordy są identyczne. Mixed cell revision, late
  source, cross-game i legacy7 są wykluczone. Exact DB receipt w
  `artifacts/task1008-postgres-receipt.json`; `cleaned=true`, rola testowa
  usunięta przez conftest. Nie tworzono ani nie sprzątano cudzych baz.
- Testy indeksu/komendy: 3 PASS; cold UTF-8 checkpoint, brak publikacji po
  złym SHA, strict confirmation. Test routera API: 1 PASS poza sandboxem.
- Schema readiness, routing, lifecycle i manifest: 40 PASS w 10,87 s.
- Admin: 733 testy PASS; 12 skoncentrowanych interakcji PASS, a po zmianie
  etykiet dwa nowe przypadki ponownie PASS. Typecheck Admin i klienta PASS.
  Lint Admin: 0 błędów, 5 istniejących ostrzeżeń w innych komponentach.
- Wrapper request test: 1 PASS. Ruff zmienionych plików PASS; mypy 15
  zmienionych modułów źródłowych PASS; mapa kodu zregenerowana.
- Zbiorczy zestaw API + katalog przekroczył 120 s bez pełnego wyniku;
  nie jest PASS. Sandbox blokował localhost 10013 i synchronny ASGI
  TestClient; ograniczone PG/transport były wykonywane poza sandboxem.
  Nie pozostał proces własnego zestawu po timeout.
- Odczyt operatora był wyłącznie read-only SELECT kilku deskryptorów
  (0,312 s) i stat plików (0,015 s). Próba nie dowodzi czasu SHA.
- Końcowe docs:check, git diff --check, OpenAPI --check, check:generated
  klienta i code-map --check: PASS.
- Oba oryginalne profile: dwa przypadki wszystkich zarejestrowanych wersji
  PASS. Checkpoint UTF-8 dodatkowo sprawdzono na 17-bajtowych chunkach: PASS.
- Wymagane stare regresje domknięto w krótszych grupach po timeoutach:
  domain 85 PASS; API report/exception 8 PASS w 46,76 s, list 16 PASS
  w 74,28 s, low-quality 10 PASS w 53,42 s, source-assets 7 PASS w 39,20 s.
  Grupy pokrywają wszystkie 40 przypadków API; geometry_exception jest
  jednocześnie w grupie list i exception, więc wyników nie sumować.
  Wcześniejsze częściowe zestawy nie są PASS. Własne procesy po timeoutach
  zakończone, potwierdzone odczytem stanu; nie kończono cudzych procesów.
- Dokładne polecenia rozdzielonych grup, cwd, timeouty i wyniki zapisano w
  `artifacts/task1008-verification.json`.
- Zakres audytu i wyłączenia metadata leada zapisano w
  `artifacts/task1008-scope.json` (59 plików). Niezależny audyt nie został
  uruchomiony przez wykonawcę; status i commit domyka lead.

### Not completed

- Niezależny audyt został uruchomiony, ale nie zwrócił werdyktu480 s; nie ma PASS. Ograniczenie i reguła kontynuacji są zapisane powyżej. Commit i integracja nie były wykonane przez wykonawcę.
- Nie wykonywano backfillu, migracji ani kontroli usług operatora,
  treningu, aktywacji, backupu bazy, recropu lub masowego odczytu obu gier.
- Nie wykonano pomiaru pełnego SHA dużych oryginalnych manifestów ani
  operacyjnego odbioru UI. Limit 30 s jest jawnym ograniczeniem; po jego
  przekroczeniu przygotowanie pozostaje bezpiecznie nieukończone.

### Documentation updates

- Zaktualizowano task, sekcję TASK-1008 w CURRENT_STATE, owner docs
  DATA_MODEL/API_CONTRACT/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP/ADMIN_APP
  oraz wygenerowane mapy kodu.

### Recommended next task

- TASK-0993
