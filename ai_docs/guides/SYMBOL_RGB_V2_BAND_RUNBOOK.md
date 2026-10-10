---
title: Runbook przebiegów RGB v2 po pasmach
status: active
last_updated: 2026-10-05
---

# Runbook przebiegów RGB v2 po pasmach

Dotyczy planu `ai_docs/delivery/SYMBOL_RGB_V2_REPROCESSING_PLAN.md` i decyzji
D-520. Wszystkie polecenia z katalogu repozytorium (główny checkout), Windows
PowerShell. Każdy proces Pythona ma twardy limit 600 s; kod wyjścia 3 znaczy
„uruchom ponownie”.

## 1. Indeks pasm (tylko odczyt, raz)

```powershell
.\.venv\Scripts\python.exe -m scripts.symbol_rgb_v2 index --game-code 7 --output-dir artifacts/symbol-rgb-v2/index --shards 32 --time-budget-seconds 1
```

Powtarzać do kodu 0 (jedna część na proces, ~40–65 s). Wynik:
`artifacts/symbol-rgb-v2/index/<SYMBOL>/shard-NNN-of-032.json` i `summary.json`
(liczby komórek per symbol, pasmo i obecne źródło). Pasmo komórki to jej
pierwotna pewność modelu; dla komórek starej biblioteki — z ostatniej rewizji
modelu planszy.

## 2. Podgląd pasma i bramka operatora

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_symbol_rgb_bands.ps1 -Band lt60 -Phase preview
```

Dla każdego symbolu i części (≤ 60 000 komórek, podział `--shard` po skrócie
identyfikatora) powstaje `artifacts/symbol-rgb-v2/runs/<pasmo>/<SYMBOL>-NN-of-MM/`
z `scope.json`, `rows.json` (decyzje), `report.json` i `preview.html` (próbka
≤ 40 komórek na parę obecny → nowy i status). Na końcu
`artifacts/symbol-rgb-v2/band-<pasmo>-gate.json` i wpis `GATE` w logu.
**Zapis tylko po zgodzie operatora na to pasmo.**

## 3. Zapis zatwierdzonego pasma

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_symbol_rgb_bands.ps1 -Band lt60 -Phase apply
```

Dla każdej części kolejno: `manifest` (wiąże zatwierdzone decyzje z bieżącą
rewizją plansz — po zapisie poprzedniego symbolu wspólne plansze mają nowe
rewizje), `apply` (plansza na transakcję, pokwitowania
`apply-receipts-<sha12>.jsonl`), `verify` (`apply-verify.json`). Plansza z
efektem ubocznym poza celami kończy się jako `stale:SYMBOL_REFERENCE_WRITE_SIDE_EFFECT`
i przebieg idzie dalej. Inny błąd zatrzymuje przebieg (`STOP` w logu).

## 4. Wznowienie

Uruchomić to samo polecenie. Podgląd: części z `report.json` i kompletnymi
wierszami nie są liczone ponownie. Zapis: części z `apply-verify.json` są
pomijane; część z manifestem bez weryfikacji jest wznawiana na tym samym
manifeście (plansza zapisana bez pokwitowania wraca jako `stale`).

## 5. Cofnięcie

```powershell
.\.venv\Scripts\python.exe -m scripts.symbol_rgb_v2 revert --game-code 7 --manifest <katalog części>\apply-manifest.json --expected-sha256 <sha> --board <reviewItemId>
```

`--all` zamiast `--board` cofa całą część. Cofnięcie kopiuje poprzednią
rewizję (suma `sha256("revert:" + suma przebiegu)`); komórki zdecydowane w
międzyczasie przez operatora zachowują decyzję.

## Ograniczenia

- Nie uruchamiać zapisu symbolu, który operator weryfikuje w Adminie
  (zakleszczenia w B3).
- Jeden sterownik naraz; bez równoległych zapisów.
- Odczyt specyfikacji renderu trwa ~75 s na rundę dla 60 000 komórek
  (TASK-0792); budżet podglądu 300 s, zapisu 240 s.
