# TASK-0972 — D-542, D-543, dokumentacja i odbiór cofania korekt i zamiennika

## Status

`todo`

## Goal

Decyzje D-542 i D-543 oraz dokumenty opisują cofanie korekt, odrzucanie i zamiennik; operator wykonuje migrację `0154` po scaleniu za zgodą, a odbiór potwierdza cofnięcie slotu 69004 i jedno przejęcie sekwencji przez zdjęcie zastępcze, wykonane przez operatora.

## Context

Plan `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`, etap R4.

## Dependencies / entry conditions

- TASK-0966–0971 ukończone; zgoda operatora na scalenie i push.

## Recommended execution

`claude-sonnet-5-5`, reasoning `low`: dokumentacja i odczytowy odbiór. Eskalacja: rozbieżność stanu bazy z oczekiwanym → zatrzymaj i zgłoś. Review: Codex `gpt-6-astra`, `medium`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- D-542 (pełny wpis w `DECISION_LOG_2026.md`, indeks, okno pięciu wpisów): cofanie ostatniej korekty, status `reverted`, fizyczne usuwanie w przypadku B z audytem, reguła `assignment_source`, zmiana D-462 w zakresie „bez usuwania historii” dla wierszy utworzonych przez cofany zapis.
- D-543: odrzucanie slotu/planszy po imporcie (status `rejected` slotu, bramka bez zmian), reguła przejęcia sekwencji przez zdjęcie zastępcze (zmienia D-238), sprzątanie starego zdjęcia.
- `DATA_MODEL.md` (tabela audytu, status, kolumna zdarzeń), `API_CONTRACT.md` (trasy cofania i odrzucania), `IMAGE_INGESTION.md` (reguła przejęcia sekwencji), wymagania Reviewera, `README.md` (link do planu), status planu.
- Instrukcja operatora: stop API/worker/Admin/Reviewer → scalenie → `npm run db:migrate` → start → cofnięcie w Reviewerze.
- Odczytowy pomiar N1: ile korekt importu `092ff7a4-…` jest `revertable` i jakie są powody blokad.
- Odbiór po cofnięciu 69004 przez operatora (odczyt): slot `pending`, brak planszy `378a273f-…`, sąsiedzi 69006–69012 na rewizji źródła 0, rewizja 1 `reverted`, wiersz audytu.
- Odbiór zamiennika po imporcie operatora (odczyt): odrzucony slot `superseded`, nowa plansza właścicielem sekwencji, stare zdjęcie przeliczone, raport importu z „Zastąpione sekwencje”.

## Out of scope

- Wykonywanie cofnięcia lub migracji przez agenta.

## Acceptance criteria

- [ ] `npm run docs:check` zielone; D-542 i D-543 w indeksie i oknie.
- [ ] Odbiór 69004 i zamiennika opisany w `Outcome` z wynikami zapytań odczytowych.

## Verification

```powershell
npm run docs:check
# odczyt stanu bazy operatora: psql SELECT, bez zapisów
```

## Risks / open questions

- Operator może najpierw ponownie poprawić 69004; wtedy cofnięcie dotyczy nowszego zapisu albo jest blokowane — odnotuj w `Outcome`.

## Outcome

Wypełnia agent po pracy.
