# TASK-0937 — Pilot wykrywania złotej ramki super symbolu (pomiar)

## Status

`todo`

## Goal

Raport mierzący, czy obecne wycinki komórek V3 gry Mumie obejmują złotą
ramkę super symbolu i czy prosta heurystyka koloru wykrywa ją z precyzją i
czułością wystarczającą do automatycznego proponowania super symbolu serii.

## Context

Operator rozważa oznaczanie złotej ramki w weryfikacji symboli i
automatyczne rozpoznawanie. D-489 zostawił margines wycinka jako otwarte
pytanie. Plan: etap S-D (warunkowy).

## Dependencies / entry conditions

- Co najmniej 5 serii ze zdefiniowanym super symbolem (TASK-0934) jako prawda
  odniesienia.
- Tylko odczyt danych i plików; żadnych zmian w bazie ani modelach.

## Recommended execution

claude-sonnet-5-5 / medium. Skrypt pomiarowy i raport. Eskalacja
niepotrzebna. Audyt: gpt-6.1-sol / medium.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/delivery/MUMIE_SYMBOLS_PREMIUM_EXECUTION_PLAN.md` (margines 8 %, kontekst)

## Scope

- Skrypt `scripts/m8_gold_frame_pilot.py` (proponowany, tylko odczyt):
  dla 30–50 komórek z plansz serii (symbol X i inne) pobiera wycinek V3 i
  wycinek z marginesem 8 % z obrazu źródłowego; liczy udział „złotych”
  pikseli na obwodzie; raportuje precyzję/czułość względem prawdy
  (komórki X w serii = ramka).
- Raport `ai_docs/quality/MUMIE_GOLD_FRAME_PILOT_<data>.md`: widoczność
  ramki w wycinkach V3 (tak/nie/częściowo), wynik heurystyki, rekomendacja:
  cecha komórki + propozycja automatyczna albo rezygnacja.

## Out of scope

- Zmiany w weryfikacji symboli, modelach, wycinkach.

## Acceptance criteria

- [ ] Raport z liczbami na co najmniej 30 komórkach i decyzją „dalej / nie”.
- [ ] Skrypt uruchamialny ponownie bez zapisu do bazy.

## Expected files

- Nowe: `scripts/m8_gold_frame_pilot.py`, `ai_docs/quality/MUMIE_GOLD_FRAME_PILOT_<data>.md`.

## Verification

```powershell
# katalog worktree, timeout 120 s
.\.venv\Scripts\python.exe scripts/m8_gold_frame_pilot.py --game mumie --limit 50 --out artifacts/gold-frame-pilot
```

## Risks / open questions

- Odblaski i rozmycie mogą ukrywać ramkę; klatki animacji z ramą całej
  planszy mogą zawyżać wynik.

## Outcome

Wypełnia agent po pracy.

### Changed

### Verification results

### Not completed

### Documentation updates

### Recommended next task
