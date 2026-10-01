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

## T2 — ślepa ocena operatora (TASK-0741, bramka PASS)

Operator ocenił 200/200 komórek 2026-09-29 według reguły: rozpoznawalny
symbol, także lekko zasłonięty lub przycięty, dostaje klasę; stany
nieczytelny, zasłonięty i zła siatka tylko wtedy, gdy symbolu nie da się
rozpoznać. Plik ocen SHA
`d7b16c908f827f1f4ae3ff738dfcbf5fb6f8bd29c1ad93478eff00a97ee9e591`,
raport `compare.json` SHA
`60829592508644fadccb850b225fcdecd08b767db5478358c0c70c175c1ba4c2`.

| Miara | Wynik |
|---|---:|
| Komórki z symbolem wg operatora | 195 (1 nieczytelna, 2 zasłonięte, 2 zła siatka) |
| Pewne propozycje biblioteki | 161 (pokrycie 82,6%) |
| Zgodność pewnych propozycji | 99,4% (160/161) |
| Aktywny model na tych samych 195 komórkach | 73,8% |

| Proponowany symbol | Pewne propozycje | Zgodne |
|---|---:|---:|
| Arbuz | 16 | 100% |
| Cytryna | 10 | 100% |
| Gwiazda | 22 | 100% |
| Pomarańcz | 23 | 100% |
| Siedem | 23 | 100% |
| Śliwka | 16 | 100% |
| Winogron | 21 | 100% |
| Wiśnia | 30 | 96,7% |

Bramka: komplet ocen, 99,4% ≥ 98% ogółem, każdy symbol ≥ 95% przy co
najmniej 10 pewnych propozycjach — **PASS**. Żaden symbol nie pozostał
niepotwierdzony, ale Cytryna ma dokładnie minimalne 10 propozycji.

Aktywny model na tej próbce (poprawnie / błędnie): Arbuz 13/11, Śliwka 13/11,
Winogron 12/13, Cytryna 18/6; pozostałe symbole co najwyżej 3 błędy.

Przypadki szczególne (ocena wzrokowa agenta, do potwierdzenia przez
operatora):

- `f083d112` — jedyny „błąd”: operator Cytryna, propozycja Wiśnia. Wycinek
  pokazuje wiśnię częściowo pod przyciskiem nawigacji; możliwa pomyłka
  wyboru na stronie.
- `cf7f29d9` — operator Zasłonięty, propozycja Wiśnia: wiśnia na wycinku
  jest widoczna w całości; możliwa pomyłka wyboru.
- `9d4660f5` — operator Zasłonięty, propozycja Wiśnia: wiśnia pod przyciskiem
  nawigacji. Biblioteka daje pewną propozycję także dla takiej komórki.
- Dwie komórki „zła siatka” (`0373f361` numer sekwencji, `b310be76` pole
  między symbolami) i komórka nieczytelna trafiły do przeglądu.
- 34 komórki do przeglądu według oceny operatora: Cytryna 11, Pomarańcz 9,
  Wiśnia 4, Gwiazda 4, zła siatka 2, pozostałe po 1–2.

Żadna z 200 komórek nie została w międzyczasie zatwierdzona w Adminie
(`laterAdminDecisions.cells = 0`).

### Przygotowanie próbki

Zamrożona próbka: 200 oczekujących komórek, po 25 na przewidziany symbol
z pasma 60–80%, z 24 importów, bez komórek pokazanych wcześniej z propozycją.
`blind-frozen.json` SHA
`0bc381166236d40259f62f61aabfcde101fcfa60444c3d540e2ead1d8d384582`.
Biblioteka daje w niej 163 pewne propozycje i 37 komórek do przeglądu.

Strona oceny (plik lokalny, bez sieci):
`worktrees/symbol-reference-library/artifacts/symbol-reference-library/blind/blind-review.html`.
Strona nie zawiera propozycji ani predykcji. Nie otwieraj
`blind-frozen.json` przed zakończeniem oceny.

Po pobraniu pliku ocen, z katalogu worktree:

```powershell
$env:PYTHONPATH = "services\worker\src;services\api\src"
$py = 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe'
$p = Start-Process -FilePath $py -ArgumentList @(
  'scripts/evaluate_symbol_reference_library.py', 'compare',
  '--frozen', 'artifacts/symbol-reference-library/blind/blind-frozen.json',
  '--ratings', '<ścieżka do pobranego blind-ratings-0bc381166236.json>',
  '--output', 'artifacts/symbol-reference-library/blind/compare.json',
  '--with-database'
) -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'timeout 120 s' }
```

Bramka: komplet 200 ocen, co najmniej 98% zgodności pewnych propozycji
ogółem i co najmniej 95% dla każdego proponowanego symbolu z co najmniej
10 pewnymi propozycjami. Oceny `Nieczytelny`, `Zasłonięty` i `Zła siatka`
nie są błędami propozycji; raport podaje, ile pewnych propozycji padło na
takie komórki.

## A3 — polityka wzorców v2 i podgląd dla predykcji Arbuz (TASK-0742)

D-465 wyłącza z wzorców komórki, których ostatnią decyzją jest masowe
`approve` (48 698 komórek); przeniesienia `reassign` pozostają.

| Pomiar | `all-human-v1` | `no-bulk-approve-v2` |
|---|---:|---:|
| Wzorce | 2 706 | 2 508 |
| T1: pokrycie / zgodność pewnych propozycji | 80,5% / 99,5% | 79,1% / 99,5% |
| Ślepa próbka, oceny oryginalne | 82,6% / 99,4% | 80,5% / 99,4% |
| Ślepa próbka, oceny poprawione | 82,7% / 100% | 80,6% / 100% |

Poprawione oceny: operator potwierdził, że `f083d112` i `cf7f29d9` to
Wiśnia (osobny plik `blind-ratings-corrected.json`, oryginał bez zmian).
Polityka v2 zmienia 6 z 200 propozycji ślepej próbki; bramka etapu A nadal
PASS. Z polityką v2 Cytryna ma 8 pewnych propozycji w próbce, poniżej
minimum 10 — jej wynik jest niepotwierdzony. `rescore-v2.json` SHA
`c4de3a068b4e92cb0e222255b3cce978db5da3b98b0d4b4a615a155908df9b63`.

Podgląd: wszystkie oczekujące komórki z predykcją Arbuz poniżej 80%
(11 864; poza zakresem 16 z `grid_issue` i 11 w trybie `legacy_file`).
Nic nie zapisano w bazie.

| Propozycja biblioteki | Pewność modelu 0–60% | Pewność modelu 60–80% |
|---|---:|---:|
| Arbuz (bez zmiany) | 2 540 (77,1%) | 5 226 (61,0%) |
| Do przeglądu | 493 (15,0%) | 1 200 (14,0%) |
| Wiśnia | 47 | 766 |
| Pomarańcz | 58 | 588 |
| Gwiazda | 54 | 270 |
| Siedem | 34 | 230 |
| Winogron | 12 | 163 |
| Cytryna | 33 | 108 |
| Śliwka | 24 | 18 |
| **Razem** | 3 295 | 8 569 |

`preview.json` SHA
`0ed25966268122088f4c7278ef2ad3aeebb1ff6ba3bc098ab12f5ea88ec616e9`,
identyczny w kolejnych uruchomieniach. Widok lokalny:
`worktrees/symbol-reference-library/artifacts/symbol-reference-library/preview-arbuz/preview.html`
(zestawienie per pasmo i do 40 przykładów na przejście).

Ograniczenia: pasmo 0–60% nie było objęte ślepą oceną; jego wyniki są
niepotwierdzone. Ocena wzrokowa agenta na przykładach: przejścia do Siedem
i Wiśnia pokazują czytelne siódemki i wiśnie (część wiśni pod przyciskiem
nawigacji, zgodnie z D-465); przejścia do Pomarańcz to żółte owoce z
listkiem, które w ślepej ocenie operator potwierdzał jako Pomarańcz.

Polecenie (wznawialne, kod wyjścia 3 = uruchom ponownie):

```powershell
$env:PYTHONPATH = "services\worker\src;services\api\src"
$py = 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe'
$p = Start-Process -FilePath $py -ArgumentList @(
  'scripts/evaluate_symbol_reference_library.py', 'preview',
  '--game-code', '7', '--symbol', 'ARBUZ', '--max-confidence', '0.8', '--band-edge', '0.6',
  '--output-dir', 'artifacts/symbol-reference-library/preview-arbuz',
  '--artifact-root', 'C:\Users\tuszy\Documents\game_predicotr\artifacts',
  '--library-cache', 'artifacts/symbol-reference-library/stage-a/crop-cache.npz',
  '--time-budget-seconds', '60'
) -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'timeout 120 s' }
```

`--library-cache` jest współdzieloną pamięcią podręczną wycinków wzorców
i może być uzupełniany poza katalogiem wyników.

## A4 — podpowiedzi i rozmiar biblioteki (TASK-0743)

Operator wskazał trzy komórki „do przeglądu” z błędną podpowiedzią
(`292172c9` Śliwka, `681eaba5` Arbuz, `aa8e6866` Cytryna). Przyczyny:
zasłonięcie przyciskiem lub dłonią dominuje podobieństwo (najbliższe
wzorce to inne zasłonięte symbole), a podpowiedź brała tylko opis kształtu.

Podpowiedź to teraz dwie klasy o największej sumie wag obu opisów.
Trafność na komórkach przeglądu ślepej próbki (oceny poprawione):

| Podpowiedź | 15 wzorców/grupę (38 komórek) | 40 wzorców/grupę (19 komórek) |
|---|---:|---:|
| Kształt (dotychczas) | 31 | 15 |
| Połączona, 1 kandydat | 33 | 16 |
| Połączona, 2 kandydatów | 38 | 19 |
| Stary model | 28 | 13 |
| Połączona (1) lub stary model | 38 | 19 |

Rozmiar biblioteki (polityka `no-bulk-approve-v2`):

| Pomiar | 15 wzorców/grupę | 40 wzorców/grupę |
|---|---:|---:|
| Wzorce | 2 508 | 5 700 |
| T1: pokrycie / zgodność pewnych | 79,1% / 99,5% (10 błędów) | 87,8% / 99,7% (16 błędów) |
| Ślepa próbka: pokrycie / zgodność | 80,6% / 100% (158) | 90,3% / 100% (177) |

Przy 40 wzorcach każdy symbol ma co najmniej 11 pewnych propozycji w ślepej
próbce (Cytryna 11), więc żaden nie jest niepotwierdzony. Jedna pewna
propozycja padła na komórkę ocenioną jako zasłonięta. Zgodność nie spadła,
więc domyślna wartość to teraz 40 wzorców na grupę. Stara wartość jest
dostępna przez `--references-per-group 15`.

Podgląd Arbuz poniżej 80% przy 40 wzorcach (`preview-arbuz-g40/preview.html`,
`preview.json` SHA
`5b78a43c947e4aa4226c8f55d1bcde3c418caae1b10c25e39021632126b4dd01`; raporty ponownej oceny
ślepej próbki: `rescore-v2-g15.json` SHA `04921555…31f5`, `rescore-v2-g40.json`
SHA `a132d937…f489`):

| Propozycja | 0–60% | 60–80% |
|---|---:|---:|
| Arbuz (bez zmiany) | 2 621 | 5 384 |
| Do przeglądu | 377 | 832 |
| Wiśnia | 60 | 824 |
| Pomarańcz | 61 | 666 |
| Gwiazda | 60 | 295 |
| Siedem | 43 | 271 |
| Winogron | 12 | 163 |
| Cytryna | 35 | 116 |
| Śliwka | 26 | 18 |

Względem 15 wzorców: 0 pewnych propozycji zmieniło symbol, 542 komórki
przeszły z przeglądu do pewnej propozycji, 58 odwrotnie. Trzy wskazane
komórki pozostają do przeglądu; podpowiedź: `681eaba5` Arbuz / Siedem,
`aa8e6866` Pomarańcz / Cytryna, `292172c9` Wiśnia / Winogron (nadal błędna;
zasłonięta śliwka nie ma podobnych wzorców, pomogą poprawki operatora).

## Ograniczenia

- Import jest przybliżeniem nagrania; wyłączenie importu nie dowodzi
  niezależności nagrań.
- Biblioteka pochodzi głównie z komórek poprawionych przez operatora.
  Rzeczywista zgodność na oczekujących komórkach wymaga ślepej oceny T2.
- Zasłonięte wzorce pozostają w bibliotece do rozstrzygnięcia O1.
