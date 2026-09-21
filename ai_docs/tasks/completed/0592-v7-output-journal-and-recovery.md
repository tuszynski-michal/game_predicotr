---
title: TASK-0592 — V7 first output, journal and recovery
status: done
last_updated: 2026-09-21
---

# TASK-0592 — Pierwszy zapis, journal i recovery V7

## Goal

Zrealizować bezpieczny pierwszy, bajtowo identyczny zapis `seq_<start>-<end>.jpg`
do sąsiedniego katalogu `cut`, z trwałym journalem, generacją decyzji,
wyłącznością katalogu oraz recovery po awarii — bez podmiany istniejącego celu.

## Context

T07 zwraca niezmienne propozycje, lecz nie wolno ich materializować bez
jednoznacznego intentu, kontrolek checksum i odporności na zanik procesu.
Historyczne acknowledgementy nie wystarczają do ochrony lokalnego NTFS przed
wyścigiem ani obcym plikiem.

## Dependencies / entry conditions

- TASK-0584–0591 są ukończone; T07 dostarcza `V7ScanRunState` i przypięty
  manifest. V7 nadal jest zablokowane w API.
- V1 wspiera lokalny NTFS bez junctions, dowiązań i udziałów; brak takiej
  pewności jest błędem fail-closed.

## Recommended execution

`gpt-6-astra`, reasoning `xhigh`: operacja łączy trwały journal, filesystem i
wyścigi. Przed commitem wymagany review `gpt-6-astra`, reasoning `medium`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`

## Scope

- Dodać writer V7 z operacjami `prepared`, `publishing`, `published`,
  `committed`, `cancelled`, `superseded`, `conflict`, idempotency key,
  command fingerprint, generacją i aktualnym właścicielem targetu.
- Dla pierwszego automatycznego zapisu wymagać braku celu; kopia ma zachować
  dokładnie SHA źródła, read-back i atomową publikację bez nadpisania.
- Utrwalić journal atomowo pod wspólnym lockiem katalogu oraz recovery macierzy
  temp/target/journal; stale operation nie może publikować po utracie lease
  lub zmianie generacji.
- Ponownie sprawdzać pełny manifest i źródło w krytycznej sekcji przed publikacją.

## Out of scope

- Ręczna podmiana, ręczny no-OCR, strona 1–8, API/UI, aktywacja V7, OCR,
  optymalizacja równoległa i jakakolwiek mutacja realnego katalogu użytkownika.

## Acceptance criteria

- [ ] Pierwszy output ma nazwę rosnącą, identyczne bajty/SHA i nie nadpisuje
  istniejącego pliku.
- [ ] Idempotency key z innym źródłem, zakresem, generacją lub SHA zwraca
  konflikt zamiast sukcesu.
- [ ] Recovery rozróżnia brak/poprawny/obcy target i temp oraz niepełny journal;
  awaria po publikacji przed commitem kończy się poprawnym commitem po restarcie.
- [ ] Wspólny lock obejmuje odczyt generation/manifest/source aż po publikację
  i commit; code hook testuje ustaloną kolejność zdarzeń.
- [ ] Historyczny committed operation nie wymaga dawnego SHA, gdy późniejszy
  właściciel targetu zastąpi ją w T09.

## Technical notes

1. Target powstaje wyłącznie z canonical range i `source_root.with_name(
   f"{source_root.name} cut")`; ścieżki journal/temp nie przyjmują fragmentu
   od użytkownika.
2. Operacja zapisuje intent → temp + fsync → rewalidacja manifestu/źródła →
   non-clobber publish → read-back SHA → owner/commit. Journal ma pełny stan,
   a nie ostatni indeks.
3. `committed` jest kontrolowane przez aktualnego właściciela targetu. T09
   zachowa O1/H1 jako historię po O2/H2; recovery O1 wtedy nie uzna H2 za
   uszkodzenie. Obcy target bez aktualnego ownera pozostaje konfliktem.
4. Test seam służy wyłącznie testom kontrolowanej awarii/barier; nie pochodzi z
   manifestu ani UI.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_output_writer.py`
- Nowe: `services/worker/tests/test_v7_output_writer.py`
- Istniejące: dokumenty V7, `CURRENT_STATE.md`, `TEMP PLAN V7.md`.

## Test cases

- Pusty `cut` → auto create → dokładny SHA i jeden current owner.
- Istniejący obcy target → konflikt bez zmiany bajtów.
- Crash po prepared/temp/publish → recovery; szczególnie publish bez commit.
- Ponowienie tego samego key zwraca istniejący wynik; ten sam key z innym
  commandem kończy się konfliktem.
- Finalizacja O1, późniejsze historyczne O1 z innym bieżącym ownerem nie
  zgłasza integrity conflict; T09 wykona samą podmianę.
- Bariera między ostatnią walidacją a publish i konkurująca decyzja: stale
  operation nie może przejść przez lock/generation.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_v7_output_writer.py services/worker/tests/test_v7_run_state.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection/v7_output_writer.py services/worker/tests/test_v7_output_writer.py
```

## Risks / open questions

- Zewnętrzny proces filesystemu nie respektuje blokady aplikacji; writer może
  wykryć zmianę przed/po publikacji i nigdy nie nadpisuje obcego targetu, ale
  nie daje blokady współpracującego procesu zewnętrznego.
- T09 doda ręczny replace i ujawni operacje przez API/UI.

## Outcome

- Dodano framework-free `V7OutputWriter` i JSON journal schema v1. Pierwszy
  output jest kanonicznym plikiem `seq_<start>-<end>.jpg` w sąsiednim katalogu
  `cut`, utworzonym jako bajtowo identyczna kopia źródła przez temp + fsync,
  publikację NTFS bez nadpisania i read-back SHA.
- Journal utrwala request, fingerprint, source identity, generację, terminalne
  konflikty oraz current owner. Ten sam operation ID z odmienną komendą,
  obcy target/temp, niespójny owner i zmiana dowolnego wpisu manifestu są
  fail-closed. Wspólny lock obejmuje cały odczyt i commit; seam testowy
  dowodzi blokady starej generacji przed publikacją.
- Recovery rozlicza awarię po `published` do `committed` i rozróżnia awarie
  `prepared`, `publishing` i `published` od niezgodnych SHA. Nie wykonano
  manual replace, ręcznego no-OCR, zakresu 1–8, API/UI ani zapisu w katalogach
  użytkownika — należą do T09/T10.
- Weryfikacja po poprawkach z review: `57 passed` dla T08 oraz regresji
  T03/T04/T07; Ruff i mypy writer'a przeszły.
- Self-audyt naprawił mapowanie driftu manifestu na kontrakt outputu,
  natychmiastowy commit po recovery `published` i walidację ownera. Astra
  Medium zgłosiła i po poprawkach zatwierdziła cztery przypadki: czytelny
  konflikt po uszkodzeniu committed targetu, awarię między linkiem a journalem,
  wymóg local NTFS oraz konkurencyjną decyzję po walidacji generacji.
