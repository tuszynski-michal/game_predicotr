---
title: TASK-0805 — V3-D: porównanie siatek w aplikacji
status: done
last_updated: 2026-10-05
---

# TASK-0805 — V3-D: porównanie siatek w aplikacji

## Status

`done`

## Goal

Udostępnić domyślnie wyłączony, ograniczony pion shadow 5 × 3 na istniejących
zdjęciach aplikacji, z oddzielnym trwałym wynikiem i ręczną korektą propozycji.

## Context

Operator jawnie uruchomił V3-D 2026-10-05 po dwóch testach folderów Mumii.
Obsługa pól częściowych i poza obrazem została potwierdzona jako wystarczająca.
To wykonanie zarezerwowanego TASK-0805, nie aktywacja domyślnego silnika.

## Dependencies / entry conditions

- V3-C zakończony; profile TASK-0830 i korekta TASK-0840/0841 istnieją.
- Model runu 1 ma zamrożone progi; model Mumii nie ma kalibracji. Wszystkie
  wyniki shadow wymagają przeglądu, również gdy bramka potwierdza zgodność.
- Zakres obejmuje zmaterializowane `source_images` i ich jawne sloty.
  225 źródeł Mumii w browser stagingu nadal wymaga wcześniejszego przeglądu
  geometrii i importu plansz. Shadow nie omija tego preflightu.
- Główny checkout zawiera cudzą niecommitowaną migrację `0141`. Tutaj
  powstaje odrębna `0142` od `0140`; przed scaleniem i wdrożeniem potrzebny
  jeden wspólny head Alembic. Nie kopiować ani commitować cudzej migracji.
- Kod/testy są zlecone. Migracja bazy, zapisy wyników na danych operatora,
  scalenie i uruchomienie pozostają do osobnej zgody po odbiorze kodu.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`; niezależny audyt `gpt-6-astra`, reasoning
`high`. Niedostępny Claude z pierwotnego planu zastąpiono jawnie przed
implementacją, wraz z tabelą planu. Delegowanie w ramach jawnie uruchomionego
etapu, osobne zakresy plików; jeden commit całego TASK-0805.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/delivery/GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` (V3-D)
- `ai_docs/delivery/GRID_V3_SHADOW_CONTRACT_20261005.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/requirements/IMAGE_INGESTION.md` (poświadczone zakresy, D-484/485)
- `ai_docs/requirements/ADMIN_APP.md` (D-488, korekta TASK-0840/0841)
- `ai_docs/architecture/API_CONTRACT.md` (korekta i propozycje audytu)
- `ai_docs/process/DECISION_LOG.md` (D-461, D-483–D-485, D-488–D-490)
- `ai_docs/tasks/0676-vision-lab-geometry-integration.md` (T11)

## Scope

- Neutralny rdzeń CPU ONNX, kompatybilne labowe wejścia, zamrożony registry.
- Jawny bounded job VALIDATE i per-source trwałe wyniki z lease fencing.
- Osobna tabela gry, manifest v5, partycje i RLS także na child.
- Backend, OpenAPI, klient, wrapper, porównanie w Adminie i istniejący
  edytor Reviewer do jawnej korekty aktualnego slotu.
- Domyślnie wyłączone API/worker; uruchomienie nie zmienia polityki importu.

## Out of scope

Aktywacja modelu, trening, symbole/Super/wypłaty, masowy przebieg, browser
staging bez materializacji, automatyczne akceptacje, cudze zmiany, push,
scalenie, migracja lub zapisy do bazy operatora.

## Acceptance criteria

- [x] Shadow off odmawia uruchomienia; 3 × 3 odmawia przed zapisem/inferencją.
- [x] Ten sam obraz/SHA ma oddzielne baseline i neural z wersjami; model
  nie czyta starych etykiet, nie zależy od nazwy gry ani słownika symboli.
- [x] Wszystkie jawne aktywne sloty pozostają obecne; brak środkowej planszy
  nie przesuwa numerów. Dodatkowe wykrycie nie tworzy szóstego aktywnego
  slotu przy poprawnym zakresie pięciu plansz.
- [x] SHA źródła/modelu, wersje i rewizje geometrii są zamrożone; drift
  daje jawny stale/konflikt, nigdy dopięcie starej propozycji do nowej siatki.
- [x] Puste, niepełne, częściowe i poza obrazem pola są jawne. Wynik shadow
  sam nie tworzy cropów produkcyjnych ani decyzji symboli.
- [x] Utrata odpowiedzi/restart odzyskuje ten sam job/wynik; lease fencing
  blokuje starego writera. Brak dublowania ukończonych wyników.
- [x] RLS i lifecycle izolują gry oraz bezpośrednie partycje nowej tabeli.
- [x] Admin porównuje wyniki na źródle; aktualna propozycja otwiera zwykłą
  korektę z wyborem symboli. Zapis pozostaje jawną istniejącą operacją.
- [x] Regresje starego importu/labu/korekty, lint, typy, klient i build PASS.
- [x] Audyt niezależny bez nierozwiązanych P0–P2; osobny commit, Outcome,
  CURRENT_STATE i porównanie z tym taskiem/planem.

## Technical notes

Pełny kontrakt w `GRID_V3_SHADOW_CONTRACT_20261005.md`. Nowa migracja jest
wyłącznie przygotowanym kodem. Testy używają izolowanych danych testowych;
nie uruchamiać integracyjnych zapisów w bazie operatora.

## Expected files

Istniejące: `storage/models.py`, trzy konsumery manifestu v4,
`storage/schema_readiness.py`, `schemas/jobs.py`, `main.py`, worker
`imports/validation_dispatch.py`, `cli.py`, moduły inferencji labu,
`packages/admin-api-client/src/index.ts`, generowany klient/OpenAPI,
Reviewera target/entry, wybrane wejście Admina.

Nowe (proponowane): neutralny `geometry_core`, worker handler shadow,
API `domain/application/storage/schemas/api/grid_shadow.py`, manifest v5,
migracja 0142, panel porównania Admina i workspace shadow Reviewera,
testy neutralnego rdzenia, handlera, API/storage/migracji i interakcji UI.

## Verification

Najpierw testy skoncentrowane na nowych modułach i regresjach wskazanych
powyżej, następnie Ruff/Mypy, OpenAPI/generowany klient, interakcje UI,
lint/typecheck i build. Każdy skończony krok z jawnym limitem do 120 s;
znany build może mieć dłuższy ogłoszony limit. Szczegółowe komendy i wyniki
zostaną zapisane w Outcome. Nie uruchamiać benchmarków ani nowych treningów.

## Risks / open questions

- Zgodność węzłów z istniejącym edytorem narożników: nie przedstawiać
  interpolacji czterech narożników jako zachowania pełnych 24 węzłów sieci.
- Bezpieczna integracja rozbieżnych migracji przed przyszłym wdrożeniem.
- Brama skali pozostaje wymagana przed masowym przetwarzaniem.

## Outcome

Implementacja przygotowana, domyślnie wyłączona. Audyt statyczny zamknięty
bez pozostałych uwag P0–P2. Raport z dowodami i granicami odbioru:
`ai_docs/quality/GRID_V3_SHADOW_IMPLEMENTATION_20261005.md`.

Testy backendu 108 PASS, 2 PostgreSQL SKIP; dodatkowe regresje cleanup 14 PASS
i końcowe storage/retention 16 PASS (pakiety częściowo wspólne). Nowe testy
workera 20 PASS, regresje labu 38 PASS, testy klienta 79 PASS; UI, typy,
OpenAPI i build obu aplikacji PASS. Wznowienie w osobnym procesie potwierdzone
na repozytorium plikowym. Rzeczywiste PostgreSQL i współbieżne transakcje
potwierdzono czterema testami po osobnej zgodzie operatora 2026-10-05.

Końcowy opt-in moduł PostgreSQL zawiera cztery testy: nowe gry/RLS, migracja
istniejącej gry i odmowa downgrade, odczyt trwałego wyniku w osobnym procesie
oraz współbieżność dwóch połączeń przy Game FOR KEY SHARE. Kolekcja z
wymuszonym opt-in=0 daje 4 SKIP bez połączenia z bazą. Operator następnie
zezwolił na tworzenie, migracje, zapisy i usunięcie izolowanych baz testowych
oraz tymczasowych ról. Każdy test uruchomiono osobno z limitem 120 s:
recovery 1 PASS (35,29 s), locks 1 PASS (18,75 s), RLS 1 PASS (34,46 s),
migration 1 PASS (19,05 s). Nowy proces kontrolny potwierdził brak pozostałych
baz TASK-0805 i tymczasowych ról. Zgoda nie obejmuje bazy operatora.

Końcowy przegląd Definition of Done wskazał brak stanów loading/empty panelu
oraz dowodu mobilnego dotyku. Dodano jawne stany, regresje opóźnionego GET,
etykiety wyboru 48 px i przyciski panelu 44 px. Końcowe 8 testów interakcji
Admina, typecheck, lint bez ostrzeżeń, formatowanie i build (20,11 s) PASS.
Mobilny smoke Edge Chromium: 360 × 844 i 390 × 844, prawdziwe zdarzenia CDP
touchStart/touchEnd, wybór zdjęcia, start z atrapą API, wybór pola i symbolu.
Brak overflow, 15 cropów, zero zapisów i wyjątków. Nowy proces potwierdził
brak pozostałych procesów Edge z izolowanych profili testowych. Fizycznego
Androida nie testowano. Raport: `artifacts/grid-shadow-mobile-smoke/report.json`.

Końcowy niezależny audyt gpt-6-astra high: brak otwartych P0–P2. Kryteria
akceptacji i zaakceptowany V3-D porównano punkt po punkcie w raporcie jakości.
Techniczne Definition of Done spełnione. Pełny odbiór rzeczywistego
worker + ONNX + PostgreSQL na danych operatora pozostaje przyszłym zakresem.

Trwała poprawka kontroli jakości: exporter OpenAPI wybiera źródła własnego
worktree mimo wspólnego editable venv; mypy_path używa listy dwóch katalogów
zamiast nierozpoznawanego separatora średnikowego. Nowe procesy potwierdzają
aktualny kontrakt oraz typy zmienionych modułów.

Bez operacji na danych operatora, migracji jego bazy, scalenia lub wdrożenia.
Następny krok operacyjny wymaga uzgodnienia migracji 0141/0142 i kontrolowanego
wdrożenia po odrębnej zgodzie. Etap V3-D przygotowania kodu zakończony.
Commit `v1.7.191`; pełny hash zostanie dopisany po commicie.
