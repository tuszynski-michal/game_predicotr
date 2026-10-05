---
title: TASK-0846 — wstępnie wybrane propozycje symboli audytu
status: done
last_updated: 2026-10-05
---

# TASK-0846 — wstępnie wybrane propozycje symboli audytu

## Status

`done`

## Goal

Pokazać i wstępnie wybrać najlepszą nową propozycję symbolu na polach audytu,
aby operator zmieniał tylko błędne propozycje przed zapisem planszy.

## Context

Operator 2026-10-05 zlecił pokazanie propozycji również przy braku jednomyślności:
„Jeżeli będzie zła, to ją zmienię”. To zmienia ograniczenie D-491 dotyczące pustych
pól i konieczności osobnego wyboru każdej propozycji. Zapis nadal wymaga kliknięcia
operatora. Przeliczenie i otwarcie planszy nie zmieniają danych domenowych.

## Dependencies / entry conditions

Wdrożony TASK-0844, istniejące sumy i biblioteka 5653 referencji. Odczyt 2026-10-05:
917 opublikowanych wyników, obecnie 610 otwartych i 365 poprawionych plansz audytu.
Kolejka może zmieniać się podczas przeglądu; zamknięte plansze są pomijane.
TASK-0845 i zastane zmiany pozostają poza tym zakresem.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`. Spójna zmiana kontraktu, artefaktów i wspólnego
edytora wymaga regresji zapisu i stale preview. Samodzielny review z testami
integracji; bez delegowania. Zakres nie wykonuje zapisów ani zatwierdzeń operatora.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — TASK-0840/0841, D-491
- `ai_docs/architecture/API_CONTRACT.md` — D-491
- `ai_docs/process/DECISION_LOG.md` — D-465, D-488, D-491 oraz nowe D-493

## Scope

Najlepszy kandydat ze sprawdzonego `hint_candidates(proposal, 1)` dla niepewnych
pól; pewna decyzja 7/7 pozostaje bez zmian. Brak wzorców/pikseli pozostaje pusty.
Jawne `tentativeCellIndices` w istniejącym GET propozycji. Wstępny wybór tylko
w audycie; ręczna zmiana, usunięcie i „Nie wiem” mają pierwszeństwo. Zapis planszy
zatwierdza widoczne wybory dopiero po kliknięciu operatora. Aktualizacja otwartych
artefaktów i lokalny odbiór UI są częścią polecenia „pokaż mi”.

## Out of scope

Trening, zmiana ścisłej reguły pewności biblioteki, zapis do bazy za operatora,
masowe zatwierdzanie, TASK-0845, Śliwka/Arbuz, migracje, push i merge.

## Acceptance criteria

- [x] Każda nadal otwarta plansza ma nowe wyniki polityki najlepszych kandydatów.
- [x] Niepewne kandydatury są opisane w API i rozróżnione tekstowo w UI.
- [x] Wstępny wybór obejmuje propozycje istniejące w katalogu i aktualnym cięciu.
- [x] Ręczny wybór, usunięcie i nieczytelność nie są nadpisywane przy retry podglądu.
- [x] Zmiana cięcia/kwalifikacji ukrywa i wyłącza automatyczne wybory starego cropa.
- [x] Zapis dopiero po akcji operatora, bez zatwierdzeń podczas odczytu.
- [x] Zwykłe korekty zachowują podpowiedzi bez automatycznego wyboru.
- [x] OpenAPI, generowany klient, wrapper i test żądania są zgodne; restart działa.

## Technical notes / plan wykonania

1. API: dodatkowa tablica `tentativeCellIndices` w `GridAuditSymbolSuggestionsResponse`.
   Domyślnie pusta dla wcześniejszych artefaktów. Artefakt per pole zapisuje
   `isTentative`; payload i manifest SHA wiążą dokładne cięcie jak w D-491.
2. CLI: polityka `best-candidate-v1` identyfikuje nowy wynik i cursor. Stare wyniki
   nie są uznawane za gotowe dla nowej polityki. Zamrożona biblioteka/model pozostają
   identyczne. Kandydat pochodzi z sumy wag obu opisów; nie staje się wynikiem 7/7.
3. Edytor: opcjonalny `prefillSymbolSuggestions` w target, ustawiony tylko dla audytu.
   Efektywne wybory są aktualnymi propozycjami połączonymi z ręcznymi nadpisaniami.
   Jawne usunięcie blokuje ponowny prefill. Przy zmianie komendy automatyczne wybory
   znikają; manualne wybory zachowują dotychczasowe zachowanie. Niepewna nazwa ma `?`
   oraz pełny opis dostępności. Zapis czeka na odczyt propozycji, lecz jego błąd pozwala
   kontynuować ręczną korektę. Opóźniony katalog blokuje zapis, lecz nie podgląd;
   błąd katalogu ma komunikat i wymaga odświeżenia. Nie wprowadzamy nowego endpointu
   ani writerów.
4. Testy, lint/format/typecheck, regeneracja kontraktu, ograniczone rundy CLI, build
   i restart lokalnego Reviewera. Odbiór bez zapisu danych w przeglądarce.

## Expected files

Istniejące: `grid_audit_symbol_suggestions.py`, schema `grid_audit_proposals.py`,
`scripts/recognize_grid_audit_symbols.py`, `board-geometry-correction-target.ts`,
`deferred-board-cell-geometry-editor.tsx`, `grid-audit-correction-workspace.tsx`,
OpenAPI, klient generowany/wrapper, testy API/CLI i Reviewera/klienta, wymagania,
kontrakt, dziennik decyzji i CURRENT_STATE. Nowe: niniejszy task.

## Test cases

Silna/słaba/nieobecna propozycja; deterministyczny najlepszy kandydat; API backwards
compatibility; wstępny wybór i zapis; ręczna zmiana/clear/unknown; powtórny podgląd;
nieaktualne cięcie; katalog opóźniony; zwykła korekta; wznowienie po utracie odpowiedzi.

## Verification

Z katalogu repo: `.venv/Scripts/python.exe -m pytest` modułów audytu i biblioteki,
Ruff, scoped strict Mypy, generowanie/kontrola OpenAPI i klienta. Reviewer:
`npm run test --workspace @game-predictor/reviewer`, `test:geometry`, lint, typecheck
i build. Klient: test i typecheck. Skończone kroki mają limit 120 s; CLI rundy 80 s,
twardy limit procesu 115 s. Nowy proces potwierdza pokrycie kolejki bez obliczeń.

## Risks / open questions

Słaba propozycja może być błędna; jawny znacznik i przegląd operatora są wymagane.
Zapis planszy zatwierdzi również niezmienione wstępne wybory, zgodnie z poleceniem.
Nie ma pytań blokujących. Zmiany użytkownika należy zachować i stageować osobno.

## Outcome

Implemented D-493. The audit target preselects fresh candidates of the exact
current preview. Weak candidates use the deterministic existing fused-vote
ranking, keep their original non-unanimous reason and show a textual `?`.
Manual overrides, explicit unknown and explicit clear survive preview retry.
Changed geometry/qualification removes automatic choices from the old crop.
Save waits for the catalog and suggestion read; a catalog failure is explicit
and blocks premature approval. Normal correction targets retain their defaults.

Recognition used the unchanged frozen library of 5653 references and pinned
checkpoint from TASK-0844. Three bounded rounds processed 569 boards that were
open at the first round. The operator continued corrections concurrently.
Read-only acceptance verified all 525 remaining open boards (450 already
corrected of 975), their checksums and new display policy: 6073 unanimous and
1802 tentative candidates, no missing symbols across 7875 cells. A fresh CLI
process then completed with `processed=0`, `coveredOpenBoards=525`.
Library array SHA remained
`5be7ab9f7470ea3174cde032df5c0d4992ba545b41defdfcb69ee7e362a4707f`.

Verification: API/audit/CLI tests 35 PASS, reference-library tests 52 PASS,
Reviewer unit tests 209 PASS, Reviewer interaction tests 22 PASS and client
request tests 79 PASS: 397 total. Focused regressions cover tentative and legacy
artifacts, malformed flags, publication without acknowledgment, cursor recovery,
all preselected fields in the explicit Save, manual override/clear/unknown,
changed qualification, late and failed catalog, and ordinary correction defaults.
Ruff format/check, Prettier, Reviewer lint/TypeScript, client TypeScript,
OpenAPI and generated-client checks PASS. Scoped strict Mypy checked five
modules using the existing TASK-0844 configuration (transitive project/Torch
imports skipped, typed numpy/Pydantic retained). Reviewer production build PASS.

The local Reviewer was rebuilt/restarted and inspected in the in-app browser.
Board p00474 showed all 15 selected candidates; p00475 showed four tentative
names with `?` and matching accessible descriptions. Returned to the first open
board. No live Save was clicked. Runtime evidence:
`.runtime/task0846/read-only-verification.json`,
`recognition-resume.out.log`, `reviewer-proposals.jpg` and check/build logs.
The persistent implementation and artifact recovery were verified in new
processes; a computer reboot and physical Android device were not exercised.

All acceptance criteria and the relevant Definition of Done checks were reviewed
against the plan. No database approvals, migrations, training, push, merge or
TASK-0845 execution. Preexisting user changes remain outside this commit.
Remaining limitation: tentative candidates can be wrong; the operator must
review every board and correct/clear/mark unknown before Save. Next step is this
operator review in the already opened local audit queue.

Commit: prepared `v1.7.190`; the full hash will be recorded after commit.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0846 | gpt-6.1-sol | high | Kontrakt, trwałe wyniki i bezpieczne nadpisania wyborów wspólnego UI. | Samodzielny przegląd z regresjami zapisu i starego cięcia; bez delegowania. |
