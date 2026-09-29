---
title: Symbol reference library — stage A measurement
status: active
last_updated: 2026-09-29
---

# Biblioteka wzorców symboli — pomiar etapu A (TASK-0740)

Plan: `ai_docs/delivery/SYMBOL_REFERENCE_LIBRARY_EXECUTION_PLAN.md`, decyzja
D-464. Pomiar jest odczytowy. Nie zapisano niczego w bazie, nie zmieniono
predykcji, decyzji operatora ani aktywnego modelu.

## Uruchomienie

Z katalogu worktree, z interpreterem głównego checkoutu:

```powershell
$env:PYTHONPATH = "services\worker\src;services\api\src"
$py = 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe'
$p = Start-Process -FilePath $py -ArgumentList @(
  'scripts/evaluate_symbol_reference_library.py', 'evaluate',
  '--game-code', '7',
  '--output-dir', 'artifacts/symbol-reference-library/stage-a',
  '--artifact-root', 'C:\Users\tuszy\Documents\game_predicotr\artifacts',
  '--time-budget-seconds', '95'
) -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'timeout 120 s' }
```

Kod wyjścia `3` oznacza niepełne renderowanie w budżecie czasu; to samo
polecenie wznawia pracę z pamięci podręcznej wycinków. Kod `2` to błąd
kontraktu (np. nieznana gra, brak checkpointu aktywnego modelu).

## Wejście

- Gra `777` (kod `7`), aktywny model: iteracja
  `d5b3e588-f2f2-4d4b-b2fb-9b5a72a6d52b`, checkpoint SHA
  `1731869da3d082c43968c55bbc3fee0e2f58066ebcabf50191fb53164fb35f6c`.
- Stan komórek w jednej transakcji `REPEATABLE READ READ ONLY`
  (`cellStateFingerprint`): 7 500 000 komórek, 73 834 zatwierdzone, suma
  rewizji 2 583 661. Ten sam odcisk we wszystkich uruchomieniach potwierdza
  brak zmian między nimi.
- Pełna widoczność obejmuje też `source_visibility IS NULL` przy
  `source_available = true`: to wartość historyczna, nieuzupełniona przez
  migrację 0126 (2 132 z 2 706 wzorców, 351 z 400 oczekujących). Audyt nie
  znalazł w tych wycinkach czarnych krawędzi spoza zdjęcia.
- Biblioteka: 2 706 komórek zweryfikowanych przez operatora z 25 importów,
  0 wykluczonych przez niezgodność sum pikseli. Aktywny model zgadzał się
  z operatorem w 344 z nich. Liczności: Arbuz 365, Cytryna 269, Gwiazda 375,
  Pomarańcz 380, Siedem 356, Śliwka 223, Winogron 361, Wiśnia 377.
- Próbka oczekujących: po 50 komórek na przewidziany symbol z pasma pewności
  60–80%, równomiernie po importach; 400 komórek, 0 wykluczonych.

## Wynik na komórkach zweryfikowanych

Każda komórka jest oceniana bez wzorców z własnego importu. Próba zawiera
w 87% komórki, w których aktywny model się pomylił, więc jego wynik tutaj
nie jest ogólną jakością modelu.

| Symbol operatora | Komórki | Aktywny model | Głos kształtu | Pokrycie pewnych | Zgodność pewnych | Błędy pewnych |
|---|---:|---:|---:|---:|---:|---:|
| Arbuz | 365 | 8,8% | 95,6% | 82,2% | 99,3% | 2 |
| Cytryna | 269 | 9,7% | 89,6% | 55,0% | 99,3% | 1 |
| Gwiazda | 375 | 8,0% | 97,3% | 86,9% | 99,4% | 2 |
| Pomarańcz | 380 | 7,9% | 95,3% | 73,7% | 98,9% | 3 |
| Siedem | 356 | 8,4% | 98,3% | 84,8% | 99,3% | 2 |
| Śliwka | 223 | 13,5% | 91,5% | 74,0% | 100% | 0 |
| Winogron | 361 | 37,7% | 96,4% | 91,1% | 99,7% | 1 |
| Wiśnia | 377 | 8,0% | 97,9% | 87,3% | 100% | 0 |
| **Razem** | 2 706 | 12,7% | 95,6% | 80,5% | 99,5% | 11 |

Powody skierowania do przeglądu: 405 bez jednomyślności, 122 niezgodność
opisów. Pasmo 60–80% (728 komórek): pokrycie 77,9%, zgodność 99,1%.

Błędy pewnych propozycji (operator → propozycja): Pomarańcz → Cytryna 2,
Siedem → Gwiazda 2, Gwiazda → Siedem 2, Arbuz → Pomarańcz, Arbuz → Cytryna,
Pomarańcz → Arbuz, Cytryna → Pomarańcz, Winogron → Śliwka. Identyfikatory
komórek są w `report.json`.

## Wynik na 400 oczekujących komórkach

| Predykcja modelu | Ten sam symbol | Inny symbol | Do przeglądu |
|---|---:|---:|---:|
| Arbuz | 26 | 14 | 10 |
| Cytryna | 20 | 4 | 26 |
| Gwiazda | 39 | 1 | 10 |
| Pomarańcz | 33 | 3 | 14 |
| Siedem | 39 | 2 | 9 |
| Śliwka | 19 | 21 | 10 |
| Winogron | 17 | 27 | 6 |
| Wiśnia | 37 | 5 | 8 |

Najczęstsze zmiany: Śliwka → Winogron 14, Winogron → Siedem 12,
Winogron → Wiśnia 6, Winogron → Śliwka 6, Śliwka → Cytryna 6.

Ocena wzrokowa agenta na arkuszach (nie jest weryfikacją operatora):

- Propozycje Siedem dla predykcji Winogron pokazują czytelne siódemki.
- Propozycje Śliwka dla predykcji Winogron pokazują niebieskie kółka z
  obwódką, zgodnie z dotychczasowymi poprawkami operatora.
- Wycinki z numerem sekwencji zamiast symbolu (np. `34f6ded3`, `359c8c2e`)
  trafiły do przeglądu.
- Ryzyko: komórki zasłonięte dłonią lub przyciskiem nawigacji dostają
  pewne propozycje (np. Pomarańcz, Wiśnia, Cytryna). Zależy to od pytania O1.
- Cytryna ma najniższe pokrycie; blade cytryny i żółte arbuzy są często
  kierowane do przeglądu.

## Wyniki i powtarzalność

- `report.json` SHA
  `a461e260f2f57b47efd0c5abd9d5e728e85085a7c36f061dcbec3698a8df8f8c`.
- `pending-proposals.json` SHA
  `26317ee63e1687052615f41c78dbd2323fa21c08876677fff0b129e4b9e71036`.
- Cztery uruchomienia wykonawcy (w tym po poprawkach audytu) i dwa
  niezależne uruchomienia audytora na tym samym stanie dały identyczne sumy
  obu plików.

## Testy i audyt

- 20 testów PASS: 14 dla modułu `reference_library` i 6 dla skryptu
  (wykluczenie niezgodnej sumy pikseli, wznowienie z pamięci podręcznej,
  budżet czasu, brak oryginału, niepełny `render_spec`, wyłączenie importu).
- Ruff check/format i mypy `--strict` dla czterech nowych plików PASS.
- Niezależny audyt `claude-opus-5-5`: PASS bez P0–P2. Poprawiono P3:
  niepełny `render_spec` jest błędem kontraktu, niedostępny oryginał nie
  trafia do pamięci podręcznej, błąd OpenCV wyklucza komórkę, usunięto
  pozorną kontrolę stanu wewnątrz jednej transakcji, opisano znaczenie
  `NULL` widoczności. Pozostawione P3: skrypt uznaje za aktywny tylko wpis
  `activate` (po `rollback` zatrzymuje się błędem), budżet czasu nie obejmuje
  liczenia opisów (około 35 s), nazwa arkusza pochodzi z kodu symbolu w bazie.
- Arkusze: `artifacts/symbol-reference-library/stage-a/sheets/pending-<SYMBOL>.png`
  w worktree (katalog ignorowany przez git).

## Ograniczenia

- Import jest przybliżeniem nagrania; wyłączenie importu nie dowodzi
  niezależności nagrań.
- Biblioteka pochodzi głównie z komórek poprawionych przez operatora.
  Rzeczywista zgodność na oczekujących komórkach wymaga ślepej oceny T2.
- Zasłonięte wzorce pozostają w bibliotece do rozstrzygnięcia O1.
