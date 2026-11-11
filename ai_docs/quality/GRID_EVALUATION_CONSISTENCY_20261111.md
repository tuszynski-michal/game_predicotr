---
title: Zgodność oceny checkpointu i ONNX — TASK-1182
status: active
last_updated: 2026-11-11
---

# TASK-1182 — Wynik diagnozy i weryfikacji

Audyt R1 ma werdykt **REVISE** (0P0/2P1). Wykonano jedną rundę poprawek
opisaną poniżej; nie stanowi to niezależnego PASS audytu. Koordynator prowadzi
sprawdzenie poprawek i końcową bramkę.

Rozbieżność została dokładnie odtworzona. Przyczyną był domyślny TF32
w splotach cuDNN podczas oceny CUDA, przy eksportowej kontroli FP32 na CPU.
Mały błąd numeryczny przekraczał niezmieniony próg NME0,02 jednej planszy.
Nie znaleziono rozbieżnych etykiet ani oddzielnej implementacji preprocessingu.

## Dowód historyczny

Run `39ddc3a3-0cf1-4116-9d98-b55df7713ed9`, wybrany krok600,
kandydat `1be01f29-abd7-5471-be08-02786e692569`. Oceniono całe zamrożone A:
13zdjęć, 53plansze, 5pełnych i8częściowych zdjęć. Ten sam manifest i te same
kanoniczne piksele/etykiety służyły wszystkim przebiegom. Hash checkpointu
sprawdzono; eksportowe `weights.pt` jest tensorowo identyczne z `modelState`
checkpointu600, choć końcowy plik checkpointu ma globalStep1800 i osobny bestState.

| Runtime | Poprawne plansze | Photo-macro correct-rate | Normalized error |
|---|---:|---:|---:|
| Historyczny CUDA/TF32 | 50/53 | 0,8376068376068376 | 0,010363771398698186 |
| PyTorch CPU FP32 | 51/53 | 0,9145299145299146 | 0,010359770531936714 |
| Historyczny ONNX CPU | 51/53 | 0,9145299145299146 | 0,010359792641582303 |
| CUDA po naprawie FP32 | 51/53 | 0,9145299145299146 | 0,010359795572622373 |

Pierwszy i trzeci wiersz są identyczne z zapisanymi wynikami historycznymi.
We wszystkich przebiegach dopasowano53/53plansze. Jedyna zmiana poprawności:
source `51fe45b2-8014-419c-9d97-059151348158`, label0/prediction2.
NME CUDA/TF32=0,02000688589229439; CPU=0,019981591046695196;
ONNX=0,019981321732448026. Błąd maksymalnego punktu nie przekroczył0,05.
To zdjęcie ma jeden opisany target, więc zmiana wynosi dokładnie1/13
w metryce fotograficznej. Żaden próg nie został zmieniony.

Pierwotne wejście screen ma identyczny SHA w próbie TF32 on/off.
Na tych samych tensorach wejściowych surowe wyjścia TF32 względem CPU
przekroczyły skalowaną tolerancję1e-4: screen heat0,0003666878,
board nodes0,0034077793. Po wyłączeniu cuDNN TF32 oba etapy ją spełniają.
`matmul.allow_tf32` był już false. Różnica screen quad docelowej planszy
CUDA/TF32–ONNX wyniosła maks.0,006744px i zmieniła kolejne wejście cropu;
surowe punkty różniły się maks.0,095154px, punkty po fit0,024612px.
Fit miał17inlierów i ten sam powód `NEURAL_GRID_FIT_OUTLIERS` we wszystkich
trzech historycznie porównanych runtime. Dowodzi to propagacji błędu
numerycznego przez wspólny preprocessing, nie innej reguły preprocessingu.

## Ranking zachowanych checkpointów

Odtworzono modelState wszystkich trzech zachowanych kroków bez treningu.
Dla1200 i1800 wyeksportowano wyłącznie lokalne diagnostyczne grafy.

| Krok | Correct-rate obu runtime | CUDA FP32 error | ONNX error |
|---|---:|---:|---:|
| 600 | 0,9145299145299146 | 0,010359795572622373 | 0,010359792641582303 |
| 1200 | 0,7606837606837608 | 0,011218922136044094 | 0,011218963490422066 |
| 1800 | 0,8376068376068376 | 0,011003775493191028 | 0,011003887514795075 |

Całe A oraz surowe wyjścia rzeczywistych wejść grafów przechodzą kontrolę
dla wszystkich trzech kroków. Ranking w obu runtime:600>1800>1200.
Wybrany krok pozostaje600. Nie jest to dowód alternatywnego przebiegu
optymalizatora ani jakości przyszłego modelu.

## Zmiana i jej granice

Wspólny `evaluation_precision` wyłącza TF32 i autocast na czas inferencji
i przywraca ustawienia także po wyjątku. Treningowe ustawienia pozostają
oddzielne. `CorrectionEvaluator` współdzieli ładowanie A, targety, metryki
i agregację; backendy PyTorch i ONNX pozostają osobne.

Eksport grid-only korekt wymaga pełnego A każdej gry, raw parity1e-4,
zgodnych dopasowań/fit/per-target decyzji, zachowania preferencji wybranego
kroku wobec zapisanej historii i tego samego wyniku warunku non-regression
normalizedError A wobec przypiętej bazy ONNX (istniejące epsilon1e-9).
Dowód z SHA trafia do bundle. Niepowodzenie pozostawia trwały raport i blokuje
publikację katalogu. Recovery kontroluje ponownie proof i tożsamość całego A;
brak/dryf dowodu blokuje reuse bez przerabiania historii.

Kontrola preferencji przyszłego eksportu porównuje nowy wynik wybranego
checkpointu ze zapisaną historią innych kroków. Nie twierdzi, że eksport
odtwarza każdy alternatywny checkpoint. W tej diagnozie wszystkie trzy
zachowane checkpointy zostały odtworzone osobno. Pełny workflow zawartości
otrzymuje własną kontrolę całego A w TASK-1184.

Pomiar istniejącego A po naprawie: walidacja CUDA około4,9–6,4s;
pełna kontrola checkpoint600 wraz z bazą około17,5s. To ograniczony pomiar
tych danych, nie benchmark ani prognoza dla wszystkich gier.

## Weryfikacja

Po audycie R1 dodano testy podłączenia rzeczywistych runnerów `torch_engine`
do kontekstu precyzji (obie głowy, sukces i wyjątek), świeżego `_export`
(utrwalenie proof albo trwały raport bez publikacji i pozostawionego stagingu)
oraz wyboru evaluatora w `_train` dla grid-only i screen. Sprawdzono też
odrzucenie uszkodzonego checksum proof oraz zmienionej tożsamości bazy.
33testy consistency/wiring/metrics/screen zaliczone w nowym procesie,
timeout120s. Nie wykonują optimizer steps ani treningu operatora.
Ruff check/format PASS. Mypy `--follow-imports=silent` wszystkich5modułów T1
PASS w50s z logiem rzeczywistego postępu (limit120s). Dwie wcześniejsze
próby osiągnęły limit60s podczas analizy zewnętrznego Torch; procesy zostały
zakończone i sprawdzone. Log końcowy: `artifacts/task1182-r1-mypy.log`.

P2-1: proof obejmuje SHA bundle i obu grafów bazy; ładowanie otrzymuje te same
bytes i expected bundle SHA, a istniejący loader sprawdza SHA grafów.
Tożsamość trafia także do wiązania recovery. Historyczne bundle pozostają
bez zmian. P2-2:17,5s dotyczy jednej gry/13zdjęć; nie zmierzono kosztu
multi-game. Pełne A, raw parity i ponowne sprawdzenie przy recovery zużywają
istniejący budżet; możliwe wyczerpanie po treningu pozostaje jawnym ryzykiem.
Zarezerwowanie czasu w TASK-1184 zgłoszono koordynatorowi, bez zwiększania
limitów w T1.

Wszystkie procesy testowe uruchomiono z nowego procesu i jawnym timeoutem.
Właściwe środowisko: główna `.venv`, a rzeczywiste CUDA/eksporty diagnozy:
główna `.venv-vision-lab`; PYTHONPATH wskazuje kod worktree.

- `test_grid_correction_consistency.py` + `test_grid_correction_metrics.py`
  + `test_screen_correction_training.py`:23PASS, timeout120s.
- `test_grid_training_child.py`:9PASS, w tym rzeczywisty mały test
  trenera/eksportu ONNX na fixture, timeout120s.
- `test_grid_correction_evaluation_pipeline.py`:6PASS, obejmuje restart,
  kompletne/częściowe role i zachowanie przypiętej bazy, timeout120s.
- Ruff format/check zmienionych modułów T1:PASS, timeout60s.
- Mypy nowych modułów, `--follow-imports=skip`:PASS (2pliki), timeout60s.
- Mypy `--follow-imports=silent` wszystkich5modułów T1:PASS, timeout60s,
  po dopisaniu jawnego typu listy rekordów obserwatora.
- Mapa, docs:check i audyt:
  odbiór koordynatora na czystym worktree; nie są tu deklarowane jako PASS.

Pierwszy pytest trafił na niedostępny katalog Temp; ustawiono własny
`--basetemp`. Następnie długie ścieżki worktree spowodowały6błędów zapisu
w istniejących testach pipeline; z krótkim
`D:/game_predicotr/artifacts/t1182-pipeline` komplet6PASS. Testów nie osłabiono.
Pierwszy szerzej podążający mypy przerwano po braku postępu; sprawdzenie
procesów potwierdziło brak osieroconego procesu. Tryb skip dla istniejących
modułów ujawnił zastępcze Any w pominiętych importach, więc nie był dowodem
ich poprawności. Końcowy `--follow-imports=silent` przeszedł dla wszystkich5.

## Artefakty i rezultat produktu

Zwięzły dowód maszynowy z SHA źródeł:
`quality/GRID_EVALUATION_CONSISTENCY_20261111.json`.
Pełne odtworzenia i skrypty są w worktree `artifacts/t1-diagnosis/`:
`reproduction.json`, `precision.json`, `rank-600.json`, `rank-1200.json`,
`rank-1800.json`; historyczne źródła pozostają w głównym artifacts.

Historyczny werdykt pozostaje **REVISE**. A normalizedError bazy
0,00972416813826611 jest lepszy niż kandydata0,010359792641582303;
zapisany REG również ma regresję błędu i brak wymaganej poprawy.
Naprawa pomiaru nie dowodzi poprawy modelu. Nie wykonano treningu operatora,
nowej oceny REG, aktywacji, wdrożenia, migracji, restartu usług ani zmiany
defaultu. Nie przepisano historycznych raportów, wag ani ręcznych danych.
