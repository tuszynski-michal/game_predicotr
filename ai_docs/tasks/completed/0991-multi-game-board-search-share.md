---
title: TASK-0991 — Panel udostępniania wyszukiwarki wielu gier
status: done
---

# TASK-0991 — Panel udostępniania wielu gier

## Status

`done` — implementacja i weryfikacja zakończone. Operator 2026-10-16
jawnie polecił pominąć audyt, wykonać migrację 0155, scalić do main
oraz usunąć gałąź i worktree. Migracja bazy operatora wykonana i sprawdzona;
scalenie do main i usunięcie gałęzi/worktree zakończone (dowody poniżej).

## Goal

Udostępnić pełną obecną wyszukiwarkę i poprawki symboli dla stałej listy
wybranych aktywnych gier przez jeden link bez ręcznego kodu, do 72 godzin.

## Dependencies / entry conditions

Plan MULTI_GAME_BOARD_SEARCH_SHARE_EXECUTION_PLAN_20261013.md.
Bazowy commit v1.7.350 / 6fa5577802738f3614fc21e4abc2873990f8536d.
Pierwotnie audyt miał wykonać operator. Jawna instrukcja z 2026-10-16
uchyla audyt i zatwierdza migrację bazy operatora oraz main merge/cleanup.

## Recommended execution

gpt-6.1-sol, reasoning high. Zmiana poświadczeń i zapisu wielu sesji wymaga
kontroli transakcji, izolacji i regresji. Audyt pominięty jawną decyzją operatora z 2026-10-16; nie nadano mu PASS.

## Relevant docs

- AGENTS.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/DECISION_LOG.md
- ai_docs/requirements/ADMIN_APP.md (wyszukiwanie i udostępnianie)
- ai_docs/architecture/API_CONTRACT.md (sesje i publiczne board-search-shares)
- ai_docs/architecture/SYSTEM_ARCHITECTURE.md (wspólny ingress)
- ai_docs/architecture/CODE_MAP.md
- ai_docs/delivery/MULTI_GAME_BOARD_SEARCH_SHARE_EXECUTION_PLAN_20261013.md
- ai_docs/quality/AUDIT_REPORT_TEMPLATE.md

## Scope

Addytywna migracja, sesja panelu i per-game dzieci istniejących sesji,
API i wygenerowany klient, zakładka Admina, panel odbiorcy i wąski proxy,
pełne wykorzystanie obecnej wyszukiwarki/korekt/logów, testy i dokumentacja.

## Out of scope

Uruchamianie/restart usług, publiczna ekspozycja danych, stały hostname,
nowy tunel, push, fizyczny odbiór sieci zewnętrznej, zmiana gier linku.
Migrację 0155, main merge i usunięcie gałęzi/worktree operator zatwierdził
osobno 2026-10-16; są częścią końcowego przejścia.

## Acceptance criteria

- [x] Zakładka wybiera wyłącznie aktywne gry i pokazuje czytelny błąd gotowości.
- [x] Jeden link działa bez kodu i pokazuje tylko wybrane gry.
- [x] Wyszukiwanie, wypłaty, wykresy, stawki, linie i poprawki są obecnym UI.
- [x] Poprawki/retry/reload/cache są odseparowane per gra i sesja.
- [x] Lista gier jest stała; 72 h to twarda granica czasu; revoke obejmuje całość.
- [x] Secret jest hashowany, poza logami/Referer; cookie jest osobne i HttpOnly.
- [x] Równoległe otwarcia nie rotują credentialów; obca karta nie zmienia autora.
- [x] Dziennik wskazuje grę, przegląd poprawek i odtworzenie działają jak dotąd.
- [x] Legacy linki kodowe zachowują kontrakt; panel liczy się raz do limitu 5.
- [x] Obecny ingress jest współdzielony i chroniony przez aktywne sesje.
- [x] Nowy URL istniejącej sesji można skopiować z zachowanym lokalnie sekretem.
- [x] Migracja i restart/trwałość zweryfikowane na izolowanej bazie testowej.
- [x] OpenAPI i wygenerowany klient/wrapper/test żądania są spójne.
- [x] Focused testy, format/lint/typecheck, docs/mapa/build rozliczone; audyt jawnie pominięty przez operatora.
- [x] Dokumentacja i instrukcja przygotowane; migracja operatora wykonana po osobnej zgodzie.

## Technical notes

Obowiązuje szczegółowa architektura i granice transakcji z planu. Wszystkie
operacje gry pozostają game-scoped. Panel jest control-plane i nie odczytuje
wielu magazynów gry w tej samej transakcji. Sekwencje pozostają domenowe.
Nowa migracja nie trafia na main przed osobno uzgodnionym przejściem operatora.

## Expected files

Istniejące: application/board_search_share_access.py (Record, unlock),
storage/board_search_share_repository.py (count_active_sessions, list_sessions),
storage/models.py (BoardSearchShareSessionModel), main.py (dependencies),
storage/game_data_v2_manifest_v5.py i security/local_admin.py,
Reviewer board-search-share-data-source.ts (opcjonalny base URL),
Admin catalog-workspace.tsx i admin-navigation-state.ts,
packages/admin-api-client (OpenAPI, generated, index wrapper), dokumenty i mapa.
Nowe: application/storage/schemas/api board_search_panels.py,
alembic/versions/0155_board_search_panels.py, Admin features/sharing,
Reviewer features/board-search-panel, proxy i trasy panelu, focused testy.
Wszystkie ścieżki backendu odnoszą się do services/api/src/game_predictor_api/.

## Test cases

Niepusty wybór dwóch gier, gra nieaktywna/niegotowa, duplikaty, brak i obcy
sekret, obce dziecko, próba legacy unlock dziecka, granica 72 h, expiry/revoke
w trakcie korekty, retry po utracie odpowiedzi i nowym procesie, limit 5,
stare single-game linki, kolizja cookies kart, nowy origin bez przedłużenia TTL.

## Verification

Focused pytest przez istniejący runtime .venv; każda grupa max120 s.
Node testy nowych i istniejących board-search share modułów oraz testy
interakcji przez istniejące test/test:geometry workspaces max120 s.
npm run openapi:generate; check:generated; scoped lint/typecheck; docs:check;
python scripts/generate_code_map.py; code-map:check. Build Admin/Reviewer
z wcześniej podanym czasem i jawnym limitem. Audyt z briefem ograniczonym
do plików taska; jedna runda i jedna runda poprawek.

## Risks / open questions

Audyt pominięty decyzją operatora. Nie gwarantować uptime Quick
Tunnel. Utrata lokalnej kopii sekretu wymaga nowego linku; API nie odzyskuje
sekretu. Odbiór fizycznego telefonu/publicznej sieci po wdrożeniu operatora.

## Outcome

### Changed

W izolowanym worktree dodano zakładkę „Udostępnianie”, wybór gotowych
niearchiwalnych gier, ważność do 72 godzin, tworzenie/kopiowanie/zatrzymanie
linku oraz dziennik wybranej gry z istniejącym przeglądem korekt i replay.
Panel odbiorcy otwiera link bez ręcznego kodu, wybiera grę i korzysta
z obecnego BoardSearchWorkspace, wypłat i poprawek.

Addytywna migracja 0155 tworzy parent panelu i relację do istniejących
single-game sesji. HMAC wiąże token dziecka z panelem i sesją; baza
przechowuje wyłącznie hashe. Otwarcie nie rotuje credentialów. Revoke
atomowo blokuje cały panel; limit pięciu linków liczy panel raz.
Legacy unlock/revoke nie pozwalają zmieniać pojedynczych dzieci panelu.
Nowe cookie jest HttpOnly, Secure, SameSite Strict i ma ścieżkę per panel;
wąski proxy deleguje operacje gry do istniejącej allowlisty. CSP i Referer
nie ujawniają sekretu. Gotowość jest walidowana przed ingress/zapisem,
a commit kończy się przed odpowiedzią tworzenia i publicznym cookie.

Obecny kontroler tunelu i ochrona aktywnych sesji pozostają wspólne.
Po zmianie origin można skopiować URL tej samej sesji z lokalną kopią
sekretu, bez przedłużenia czasu. Brak kopii lub utracona odpowiedź tworzenia
wymagają zatrzymania widocznego wpisu i utworzenia nowego linku.

### Verification results

PASS: 84 testy Python w skupionych, ograniczonych czasowo grupach:
17 access, 11 Admin HTTP, 20 public share HTTP, 8 nowych paneli,
19 schema-readiness/manifest, 8 istniejących integracji PostgreSQL
i 1 nowa integracja PostgreSQL. Nowa integracja używa własnej losowo
nazwanej bazy testowej; sprawdza przejście 0154→0155, zachowanie legacy,
rzeczywistą bramkę gotowości przed ingress, autoryzację w nowym interpreterze
i revoke. Stare integracje sprawdzają również pełny łańcuch migracji.
Test HTTP z błędem finalizacji transakcji potwierdza brak linku/cookie
przed udanym commit. Testy proxy sprawdzają podmianę panelu/dziecka,
allowlistę, scope cookies, limit body, sekrety w JSON, expiry i kill-switch.

PASS: 44 testy Node (proxy, adapter, korekty/retry po utracie odpowiedzi,
izolacja gry/sesji, local Admin security i wrapper żądania), 10 testów
interakcji Admin/Reviewer. Po końcowych zmianach timeoutów dodatkowo
powtórzono 8 testów proxy. Focused mypy (6 modułów), Ruff check/format
(16 plików), TypeScript Admin/Reviewer i oba produkcyjne buildy PASS.
ESLint zmienionych części: 0 błędów; zachowano wcześniejsze ostrzeżenie
`_operationId` w istniejącym adapterze Reviewera.

OpenAPI artifact i wygenerowany klient są aktualne; istniejące ścieżki
API zachowują kontrakt. docs:check, code-map:check i git diff --check PASS.
Mapa kodu zregenerowana. Testy i buildy korzystają z jawnych timeoutów;
nie uruchamiano serwerów operatora.

Kontrola przeglądarkowa rzeczywistego AdminShell/CatalogWorkspace na
fixture, bez serwera: desktop 1440 px i ekran 390 px, bez błędów strony
i poziomego overflow. Zrzuty: artifacts/task0991/sharing-desktop.png
i sharing-mobile.png. To kontrola układu, nie fizyczny odbiór publicznej sieci.

W pierwszym pełnym przebiegu integracji migracja trafiła w historyczny
search_path pg_catalog. Poprawiono ją trwałym jawnym schema public dla
wszystkich operacji; cały łańcuch i izolowane integracje następnie PASS.
Pierwsza duża grupa pytest przekroczyła timeout po wypisaniu wyników;
jej własny proces zakończono i rozdzielono grupy z pełnym poprawnym wyjściem.
Build wymagający kanonizacji ścieżek Windows wykonano poza piaskownicą.
Nie zmieniano globalnej konfiguracji ani danych operatora.

### Not completed

Audyt został pominięty na jawne polecenie operatora 2026-10-16.
Nie uruchamiano Claude Code i nie oznaczano audytu jako PASS.
Historyczny brief zachowano w zabezpieczeniu poza usuwanym worktree.

Nie wykonano push, restartu/uruchomienia usług, publicznego linku na danych
operatora, pełnego repo-wide quality ani fizycznego odbioru telefonu.
Quick Tunnel nadal nie gwarantuje nieprzerwanego uptime ani stałego adresu.
Ważność linku jest ograniczona do 72 godzin. Po zmianie origin lokalne
receipts odbiorcy pozostają w pamięci starego origin; historia serwerowa
pozostaje w bazie. Reviewer na 3001 pozostał uruchomiony; API 8000 i Admin
3000 były zatrzymane, a baza przed migracją nie miała innych klientów.

### Documentation updates

Plan i task, wymagania Admina, API_CONTRACT, SYSTEM_ARCHITECTURE,
README, CURRENT_STATE, decyzja D-548 i generowana mapa kodu.
Instrukcja odbioru/migracji: guides/MULTI_GAME_BOARD_SEARCH_SHARE_OPERATOR.md.

### Definition of Done / zgodność z planem

Zakładka/wybór/link bez kodu, stała lista gier, obecne wyszukiwanie i korekty,
72 h/revoke/limit pięciu, izolacja poświadczeń/cache/receiptów, dziennik/replay,
wspólny ingress i odświeżenie URL: zaimplementowane i focused PASS.
Migracja/trwałość/legacy, backend→OpenAPI→klient→wrapper→test żądania,
format/lint/typecheck/build/dokumentacja/mapa: PASS. Zakres bez operator DB
i usług: zachowany do osobno zatwierdzonej migracji. Audyt pominięty
jawną decyzją operatora; implementacja zamknięta, integracja rozliczana poniżej.
Odbiór sieci zewnętrznej/telefonu: kontrola po osobno uzgodnionym wdrożeniu.

### Przeniesienie na wskazaną gałąź (2026-10-13)

Na jawne polecenie operatora zmiany przeniesiono z codex/multi-game-share
na v1.1-vision-lab-hybrid-geometry, w tym samym izolowanym worktree.
Gałąź docelowa była przodkiem bazy implementacji; bezpieczny fast-forward
037a30100d7383a18c76ba5fc7a8a82dad7f20a2 →
6fa5577802738f3614fc21e4abc2873990f8536d zachował trzy nowsze commity
dokumentacyjne. Nie powstał commit taska ani merge commit. Przed aktualizacją
metadanych potwierdzono SHA-256 wszystkich 53 zmienionych plików:
identyczne bajty po przełączeniu. Kod i jego wyniki testów są niezmienione.
Zaktualizowano nazwę gałęzi w planie, stanie i instrukcji oraz brief audytu.
W tamtym momencie commit TASK-0991 czekał na audyt operatora; main,
baza i zdalne gałęzie pozostawały bez zmian. Instrukcja z 2026-10-16
zastąpiła tę bramkę i zatwierdziła opisane poniżej przejście.

### Integracja zatwierdzona 2026-10-16

Operator polecił: „Pomijamy audyt. Wykonaj migrację 0155, zmerguj zmiany
do main, a potem usuń gałąź i worktree.” Ta instrukcja zastępuje starsze
bramki tego taska. Main sprzed integracji: v1.7.363 /
4e171b06773edf0946bdb1551b3c97174e3e5cfc. Kod przeniesiono na aktualną
bazę main na roboczej codex/multi-game-share-main; konflikty tylko README
oraz CURRENT_STATE rozliczono z zachowaniem nowszej dokumentacji main.
Kolizję numeru TASK-0991 z naprawą symboli zachowano; pełna ścieżka
tego taska odróżnia oba zakresy.

Backup zmian, briefu i dowodów: artifacts/branch-integration/
multi-game-share-20261016-4e7f3eb0/changes-and-evidence.zip (73 pliki,
zweryfikowane SHA-256). Backup bazy: podkatalog database-0154;
schema.dump (pełny schemat) oraz affected-tables.dump (dane i definicje
board_search_share_sessions/alembic_version). To nie pełna kopia danych
bazy 124 GiB. Oba archiwa zweryfikowano pg_restore --list i SHA-256.
Migracja 0154→0155 PASS: 24 dotychczasowe sesje identyczne (hash całych
wierszy z pominięciem nowego panel_id), nowa tabela pusta, panel_id NULL,
FK validated i unikalny indeks valid. Wynik: database-0154/migration-result.json.
Po migracji provision_database_roles PASS: app role compliant, bez
brakujących uprawnień tabel/sekwencji i bez superuser/bypassRls.

Na aktualnej bazie main ponowiono focused testy panelu i schematu:
27 PASS; dodatkowo 10 testów kluczy/proxy i 1 test wrappera PASS
(właściwy runner tsx dla wrappera). Porównano 41 plików aplikacji/testów
z zabezpieczoną wersją: identyczna zawartość po normalizacji CRLF. Kod aplikacji main od bazy pierwotnych testów nie zmienił się;
wcześniejsze wyniki 84 Python, 44 Node i 10 interakcji pozostają dowodami
tego samego pionu. Kontrole finalnego drzewa i wynik integracji zapisano poniżej.

### Końcowy wynik integracji

Commit implementacji: **v1.7.364 / cb87d269128996eecc0ddd1321bf7ccf8f41fcbb**.
Scalenie fast-forward do literalnego **main** wykonane; ancestry potwierdza,
że main zawiera cały commit taska. Zachowano wcześniejszą historię main
oraz cudze niezacommitowane worktree. Produkcyjne buildy Admin i Reviewer
w głównym katalogu PASS; nowe trasy /board-search-panel i proxy są w buildzie.
Nowy proces z runtime rolą app: require_alembic_head PASS dla 0155;
provision_database_roles --check compliant (brak luk uprawnień).
OpenAPI artifact, docs:check, wygenerowana mapa i diff checks PASS.

Usunięto D:/game_predicotr/worktrees/multi-game-share oraz lokalne gałęzie
v1.1-vision-lab-hybrid-geometry, codex/multi-game-share-main i pierwotną
pomocniczą codex/multi-game-share. Każdy ich tip był przodkiem main.
Usunięto wyłącznie własny stash bd89be3dc458af7ec1666def16b580281b1b35d4
po zabezpieczeniu. Przed rekursywnym usunięciem odpięto 8 samych reparse
points; .venv i biblioteki głównego repozytorium zachowały swoje SHA-256.
Pozostałe worktree są zachowane. Własny gitlink worktree usunięto z indeksu,
aby main nie wskazywał nieistniejącego checkoutu.

Dowody: artifacts/branch-integration/multi-game-share-20261016-4e7f3eb0/:
cleanup-result.json, database-0154/migration-result.json, admin-build.log,
reviewer-build.log, final-evidence (brief, zrzuty i narzędzia weryfikacji),
ignored-preserved (wszystkie nieregenerowalne ignorowane pliki tego taska).
Kod po przeniesieniu był zgodny w 41 plikach z wcześniejszym backupem.
Audyt pominięty — jawna decyzja operatora, bez audytu PASS. Usług nie
uruchamiano i nie restartowano; brak push. Reviewer 3001 wymaga ręcznego
restartu, API/Admin/worker ręcznego uruchomienia. Odbiór telefonu i sieci
zewnętrznej nadal nie jest deklarowany jako wykonany.

### Recommended next task

Operator uruchamia API/Admin/worker swoimi dotychczasowymi komendami
oraz restartuje Reviewer po nowym buildzie. Odbiór linku na telefonie
w sieci zewnętrznej według instrukcji operatora. Bez automatycznego push.
