---
title: Przekazanie przebiegu RGB v2 (stan 2026-10-06 ~09:00 UTC)
status: active
last_updated: 2026-10-06
---

# Przekazanie przebiegu RGB v2 (stan 2026-10-06 ~09:00 UTC)

Notatka dla kolejnego wykonawcy (Codex). Najpierw przeczytać:
`ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md` (plan, zaakceptowany),
D-520 w `ai_docs/process/DECISION_LOG.md` (z dwiema poprawkami),
`ai_docs/guides/SYMBOL_RGB_V2_BAND_RUNBOOK.md` (polecenia) i
`ai_docs/tasks/0878-symbol-rgb-v2-band-99-100.md` (bieżące zadanie).

## Gdzie jest praca

- Worktree: `C:\Users\tuszy\Documents\game_predicotr\worktrees\symbol-reference-library`,
  gałąź `feat/symbol-reference-library-port`; scalona do
  `v1.1-vision-lab-hybrid-geometry` commitem merge v1.7.222 (2026-10-06, za
  zgodą operatora) i wypchnięta. Sterowniki w tle nadal używają kodu z worktree.
- Artefakty przebiegów (poza Gitem): `<worktree>\artifacts\symbol-rgb-v2\`
  — `index\` (indeks pasm), `runs\<pasmo>\<SYMBOL>-NN-of-MM\` (scope, rows,
  report, preview.html, manifest, pokwitowania, `apply-verify.json`),
  logi `band-<pasmo>-driver.log` (UTC).
- Zamrożony checkpoint i biblioteka: `C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-audit-symbols-20261005\`
  (`library.json`, `library.npz`; SHA checkpointu `1731869d…`).

## Co jest zrobione

| Task | Zakres | Wynik |
| --- | --- | --- |
| 0870 | decyzja RGB v2, indeks pasm, podgląd, manifest | 7 412 524 komórek w indeksie; zgodność z `approved-v2` 5788/5788 |
| 0872 | filtr Admina „RGB v2”, „RGB v2 — do przeglądu” | API + OpenAPI + klient + Admin |
| 0871 | writer `symbol-rgb-v2` (0,99 pewna / 0,50 do przeglądu, wpis `rgbV2`), `apply`/`verify`/`revert` | test PostgreSQL PASS |
| 0873 | sterownik pasm `scripts/run_symbol_rgb_bands.ps1` + runbook | |
| 0874 | pasmo < 60% | 336 komórek / 324 plansze, 0 błędów |
| 0875 | pasmo 60–80% | 599 / 553, 1 plansza `stale` (flaga jakości) |
| 0876 | pasmo 80–90% | 590 / 563 |
| 0877 | pasmo 90–99% | 3 279 / 2 985 |

Razem w bazie 4 804 komórek z rewizją `symbol-rgb-v2`, wszystkie nadal `pending`.

Reguły zapisu (ważne przy ocenie wyników):
1. Zapis tylko gdy zmienia się symbol albo status pewna (≥ 0,99) / do przeglądu.
2. `library_keeps_current` (bramka 0874): niepewna propozycja CNN nie nadpisuje
   symbolu, który jednogłośna biblioteka (7/7) potwierdza — CNN myliła się
   systematycznie przy dominancie barwnej (gwiazdy, plastry arbuza).
3. Pasmo 99–100%: **tylko zmiany symbolu** (decyzja operatora 2026-10-06;
   inaczej ~1 mln obniżeń do przeglądu przy poprawnym symbolu, głównie cytryny).
Zmiana reguł = zmiana `WRITE_RULES_VERSION` (klucz wierszy) → podglądy liczą się od nowa.

## Co trwa teraz (TASK-0878, pasmo 99–100%)

- Dwa sterowniki **tylko podglądu** w tle (PowerShell, ukryte okna), start
  2026-10-06 05:59 UTC: symbole `ARBUZ,CYTRYNA,GWIAZDA,POMARANCZ` i
  `SIEDEM,SLIWKA,WINOGRON,WISNIA`, 120 części po ≤ 60 000 komórek, opcja
  `-DropCropCache` (cache wycinków części kasowany po podglądzie; na C: było
  27 GB wolnego). Do 08:50 UTC gotowe 16 części (~5 części/h razem).
  **Szacowany koniec podglądu: ~2026-10-07 05:00 UTC.**
- Log: `<worktree>\artifacts\symbol-rgb-v2\band-99-100-driver.log`. Każdy
  sterownik kończy się wpisem `GATE band=99-100` (dwa wpisy po starcie 05:59);
  `STOP` = błąd do zbadania. Próbka z 8 części: ~25 zmian symbolu na część.
- Sprawdzenie, czy działa:
  ```powershell
  Get-Content C:\Users\tuszy\Documents\game_predicotr\worktrees\symbol-reference-library\artifacts\symbol-rgb-v2\band-99-100-driver.log -Tail 5
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'symbol_rgb_v2' } | Select-Object ProcessId
  ```

## Co zrobić po podglądzie (zapis pasma 99–100%)

Operator już zatwierdził zakres (tylko zmiany symbolu). Przed zapisem obejrzeć
próbki zmian (`preview.html` w kilku częściach albo arkusze kategorii) —
zmiany potwierdzone (CNN = biblioteka) były dotąd poprawne. Zapis (jeden
proces naraz, nie równolegle):

```powershell
$wt = 'C:\Users\tuszy\Documents\game_predicotr\worktrees\symbol-reference-library'
$main = 'C:\Users\tuszy\Documents\game_predicotr'
$env:PYTHONPATH = "$wt\services\api\src;$wt\services\worker\src;$wt"
powershell -NoProfile -ExecutionPolicy Bypass -File "$wt\scripts\run_symbol_rgb_bands.ps1" -Band 99-100 -Phase apply -Python "$main\.venv\Scripts\python.exe" -ArtifactRoot "$main\artifacts" -ArtifactsDir "$wt\artifacts\symbol-rgb-v2" -LibraryDir "$main\artifacts\grid-audit-symbols-20261005"
```

`PYTHONPATH` jest konieczny: kod RGB v2 jest tylko w worktree, a `.venv`
głównego checkoutu importuje pakiety z głównego checkoutu. Uruchamiać jako
proces w tle (Start-Process), bo zapis trwa długo; wznowienie = to samo
polecenie (części z `apply-verify.json` są pomijane). Potem: Outcome
TASK-0878 (tabela części z `apply-verify.json`), przeniesienie do
`completed/`, `CURRENT_STATE.md`, commit `vX.Y.N`.

Nie weryfikować w Adminie symbolu, którego zapis właśnie trwa (zakleszczenia).

## Otwarte decyzje i sprawy (wymagają zgody operatora)

1. Merge wykonany (v1.7.222). Numeracja: `db99654f` niesie v1.7.198 jak
   `bc75c99c` z integracji (duplikat zostawiony, opisany w merge); kolejne
   commity gałęzi v1.7.210–221. Zadania tego planu: TASK-0870–0878, D-520.
2. **Restart API** (decyzja operatora) — dopiero wtedy filtr „RGB v2” działa
   w Adminie; Admin (Next.js dev) przeładuje się sam.
   Do tego czasu komórki RGB v2 widać filtrem „Data zmiany komórki” od
   2026-10-05 23:44 UTC albo w przedziale pewności < 60% (0,50 = do przeglądu).
3. **Miejsce na dysku** (C: ~27 GB wolnego). Cache do ewentualnego usunięcia
   (tylko za zgodą, wszystkie odtwarzalne):
   - `<worktree>\artifacts\symbol-reference-library\` — 32 GB, w tym 28 GB
     plików `preview-crops.npz` / `preview-context.npz` / `crop-cache.npz`
     starych przebiegów biblioteki (B1–B3, Winogron/Śliwka ≥ 99%); manifesty i
     pokwitowania warto zachować (cofanie D-466).
   - `<worktree>\artifacts\symbol-rgb-v2\runs\{lt60,60-80,80-90,90-99}\*\preview-crops.npz`
     — ~4,9 GB (pasma już zapisane).
   - Tymczasowy worktree `scratchpad\wt0858` (git worktree, detached) z
     katalogu tymczasowego sesji Claude — usunąć `git worktree remove`.
4. TASK-0832 (Śliwka ≥ 99%, stara biblioteka) i TASK-0833 (Arbuz) — zamknąć
   jako zastąpione przez D-520 (bez wznawiania starych manifestów).
5. Propozycje osobnych zadań: test `test_list_endpoint_uses_keyset_cursors_without_duplicates`
   (oczekuje 5 000 ms, kod 20 000 ms — pada na integracji); wolny odczyt
   specyfikacji renderu (~75 s na rundę, od TASK-0792).

## Pułapki środowiska

- Windows PowerShell 5.1: `$PSScriptRoot` jest pusty w bloku `param`;
  `-Symbols A,B` przez `-File` przychodzi jako jeden napis (sterownik dzieli po
  przecinku); `Start-Process` gubi `ExitCode`, jeśli nie odczyta się `.Handle`.
- Każdy proces Pythona ma limit (sterownik: 600 s); kod 3 = ponów.
- Host ma 31 GB RAM, WSL/Docker 8 GB; nie więcej niż dwa podglądy naraz.
