---
title: Audyt krzyżowy TASK-1124
status: active
last_updated: 2026-11-02
---

# Audyt TASK-1124 — Rdzeń detektora nałożenia i nieczytelności

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...c65823fd7b37bb34e73a0269b18114b87b3e3ff2 oraz zmiany niezacommitowane, data 2026-11-02
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Przejrzałem trzy nowe moduły workera (`readability_features.py`, `readability_cohort.py`, `readability_detector.py`), plik testów i fragmenty dokumentacji wymagań oraz architektury objęte zakresem. Porównałem je z planem A1 i z kodem, od którego zależą: `preprocess_rgb_batch`, `SpatialSymbolCnn`, format checkpointu w `training_job.py` i manifest w `training_dataset.py`. Implementacja jest zgodna z planem w zakresie solvera (LBFGS strong_wolfe, zero-init, L2 bez kary na bias), selekcji progu i lambdy wyłącznie na VAL, standaryzacji wyłącznie na TRAIN, łączenia rodzin, minimów pilota, bramki recall ≥ 90%, audit200 i fingerprintu artefaktu. Główne ryzyko leży w testach. Wymagany przypadek testowy „drift checksum/preprocessingu/rodziny/splitu i missing asset” jest pokryty tylko częściowo: kryterium preflightu jest odhaczone, ale gałęzie dla checkpointu, checksumy datasetu i dryfu rodzin nie mają testu.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/worker/tests/test_readability_detector.py:197` — Test nazwany `test_preflight_missing_checkpoint_and_preprocessing` przekazuje nieistniejące pliki razem z błędnym słownikiem preprocessingu. Preflight odrzuca więc wywołanie już na `services/worker/src/game_predictor_worker/symbols/readability_features.py:106`. Gałąź brakującego checkpointu i datasetu (`readability_features.py:59-63`) nigdy się nie wykonuje, mimo że nazwa testu sugeruje coś innego. W `test_preflight_complete_manifest_and_drift` (`test_readability_detector.py:136-194`) brakuje testów dla następujących ścieżek:
  - dryf SHA datasetu i checkpointu (`readability_features.py:64-65`, `:184`);
  - niezgodność `sourceAssignments` z rodzinami oraz rodzina lub piksel przechodzący między splitami (`:127`, `:150-154`, `:166-172`);
  - niezgodny katalog klas checkpointu (`:186-187`);
  - rzeczywisty brak pliku assetu.

  Zapis `b"changed"` trafia w `UnidentifiedImageError`, czyli w kod `READABILITY_INPUT_MISSING`. Ścieżka `READABILITY_INPUT_DRIFT` dla poprawnego obrazu o innych pikselach (`:148-149`) zostaje nieprzetestowana. Kryterium akceptacji „Preflight odrzuca brak/drift checkpointu, assetów, preprocessingu i pełnego splitu” jest odhaczone bez dowodu testowego dla tych gałęzi, a test case nr 1 z taska nie jest spełniony.

  Skutek: regresja w którejkolwiek z tych kontroli fail-closed przejdzie niezauważona.

  Poprawka: w istniejącej fixture `run()` dodać asercje kodów błędów dla:
  - złego `checkpoint_sha256` i `dataset_sha256` (`READABILITY_INPUT_DRIFT`);
  - usuniętego pliku checkpointu przy poprawnym preprocessingu (`READABILITY_INPUT_MISSING`);
  - zmiany `sourceAssignments` oraz duplikatu piksela w dwóch splitach (`READABILITY_DATASET_INVALID` lub `READABILITY_BASE_LEAKAGE`);
  - poprawnego PNG o innych pikselach (`READABILITY_INPUT_DRIFT`);
  - usuniętego pliku assetu;
  - `classCodes` checkpointu różnych od katalogu.

  Nazwę testu z linii 197 trzeba poprawić albo rozdzielić go na przypadek preprocessingu i przypadek brakującego checkpointu.

### P2

- [P2-1] `services/worker/src/game_predictor_worker/symbols/readability_features.py:106` — Kontrola preprocessingu porównuje tylko słownik przekazany przez wywołującego ze stałą modułu, więc praktycznie niczego nie sprawdza. Preflight dekoduje każdy asset (`:139-142`), ale nie weryfikuje, że ma on rozmiar 64x64. Twierdzenie Outcome, że resize treningowy (bilinear) i produkcyjny (INTER_AREA) jest no-opem, opiera się na ręcznym sprawdzeniu jednego assetu. Skutek: jeśli część bazowego datasetu nie ma 64x64, zgodność z preprocessingiem checkpointu nie jest zagwarantowana. Poprawka: dodać tanią kontrolę `rgb.shape[:2] == (64, 64)` w pętli preflightu z kodem `READABILITY_PREPROCESSING_DRIFT`. Alternatywą jest jawne zaakceptowanie ryzyka w D-578.

- [P2-2] `services/worker/src/game_predictor_worker/symbols/readability_features.py:184-187` — Preflight nie wiąże checkpointu z datasetem przez dane zapisane w samym checkpoincie (`inputFingerprint`, zob. `training_job.py:551`, `:600`). Para checkpoint–dataset jest chroniona wyłącznie przez dwa SHA podane przez wywołującego. Przy przyszłym ponownym użyciu z innym kandydatem łatwo podać niepasującą parę. Poprawka: jeśli `inputFingerprint` da się odtworzyć z manifestu, porównać go. W przeciwnym razie odnotować, że wiązanie zapewniają stałe z zaakceptowanego planu.

- [P2-3] `services/worker/src/game_predictor_worker/symbols/readability_cohort.py:157-165` — Próbki `audit` muszą tworzyć rodziny rozłączne z TRAIN/VAL/TEST pilota i nie mogą stykać się z bazowym TRAIN/VAL. Losowe 200 „dotąd nieoznaczonych pól” z całej gry z dużym prawdopodobieństwem trafi w źródła z bazowego TRAIN albo w źródła pilota, bo jedno zdjęcie zawiera wiele plansz. Skutek: cały cohort zostanie odrzucony (`READABILITY_SPLIT_LEAKAGE`). Żeby tego uniknąć, A2 musiałoby losować tylko z ograniczonej puli, a wtedy audyt przestaje mierzyć naturalny szum. Postępowanie jest fail-closed, ale grozi trwałym brakiem `fullScanAllowed`. Poprawka lub akceptacja: przed A2 jawnie określić w planie lub D-578 pulę losowania audit200 i regułę rozłączności dla audytu.

- [P2-4] `services/worker/src/game_predictor_worker/symbols/readability_features.py:108-116` — Niepoprawne dane wejściowe kończą się wyjątkami spoza `ReadabilityError` (`KeyError`, `TypeError`, `JSONDecodeError`), więc znikają stabilne kody błędów:
  - manifest bez wymaganych pól (`configuration`, `samples`, `splits`, `assetChecksumKind` w `:146`);
  - nieczytelny lub niepoprawny JSON artefaktu w `services/worker/src/game_predictor_worker/symbols/readability_detector.py:244`, w tym NaN, które wybucha dopiero w `fingerprint`.

  Dodatkowo trening przyjmuje brak `assetChecksumKind` z domyślną wartością `sha256-bytes` (`training_job.py:659`), a preflight w takim przypadku rzuca `KeyError`. Działanie pozostaje fail-closed. Poprawka: owinąć parsowanie w `try` z kodami `READABILITY_DATASET_INVALID` i `READABILITY_ARTIFACT_INVALID`, a domyślną wartość `assetChecksumKind` ujednolicić z treningiem.

- [P2-5] `services/worker/src/game_predictor_worker/symbols/readability_detector.py:378-381` — Bramka recall < 90% (`*_recall_below_90` → STOP) i domyślna propozycja splitu 60/20/20 (`readability_cohort.py:140-151`) nie mają testów. Fixture `artifact()` przewiduje wszystko jako kandydatów, a `test_full_fit_and_reload_in_new_process` nie sprawdza `status`. Skutek: regresja progu bramki albo propozycji chronionych rodzin nie zostanie wykryta. Poprawka: test z artefaktem o ujemnym biasie (recall 0 → STOP z oboma kodami) oraz test domyślnego `assign_families` z bazą, w której jest rodzina `test`/`regression`. Ta rodzina powinna trafić do head TEST, a rodzina bazowego TRAIN nie powinna.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Preflight odrzuca brak/drift checkpointu, assetów, preprocessingu i pełnego splitu | niezweryfikowane | Kod: `readability_features.py:59-66`, `:106-187`. Test obejmuje tylko preprocessing, podsumowanie splitu i uszkodzony asset (`test_readability_detector.py:186-207`); zob. P1-1 |
| Ekstrakcja nie zmienia wag/BN; cechy nie zawierają top1/top2 | spełnione | `readability_features.py:235-251` (eval, `requires_grad_(False)`, `inference_mode`, tylko `model.features`); `test_readability_detector.py:106-121` |
| Dwa heady realizują dokładny solver i selekcję planu, niepewne etykiety nie trafiają do odpowiedniego fitu | spełnione | `readability_detector.py:65-155`, `:211-232`; `test_readability_detector.py:248-288`, `:378-382` |
| Rodziny nie przeciekają pomiędzy splitami ani bazowym TRAIN/VAL i head TEST | spełnione | `readability_cohort.py:92-165`; `test_readability_detector.py:210-236` |
| Niepełne liczności/proweniencja pilota kończą się STOP, brak pewnych nałożeń nie daje PASS | spełnione | `readability_cohort.py:169-220`; `readability_detector.py:203-205`, `:377-399`, `:425-429`; `test_readability_detector.py:239-245`, `:314-337` (ścieżka recall < 90% bez testu, P2-5) |
| Artefakt przypina wszystkie wejścia i odtwarza scoring po nowym odczycie | spełnione | `readability_detector.py:167-181`, `:243-278`; `test_readability_detector.py:291-311`, `:340-375` |
| Testy pionu, ruff, mypy, mapa kodu, docs:check oraz wymagany audyt rozliczone | niespełnione | Kryterium nieodhaczone w tasku. Mypy uruchomiono tylko z `--follow-imports=silent`, a `npm run docs:check` zastąpiono bezpośrednim uruchomieniem kontroli (Outcome); ten audyt kończy się werdyktem REVISE |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P1-1, P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- `services/worker/tests/test_readability_detector.py`: rozszerzyć `test_preflight_complete_manifest_and_drift` o złe SHA checkpointu i datasetu, usunięty checkpoint, usunięty asset, PNG o innych pikselach, niezgodne `sourceAssignments`, piksel w dwóch splitach i niezgodne `classCodes`. Każdy przypadek powinien sprawdzać `error.value.code`. Komenda: `D:/game_predicotr/.venv/Scripts/python.exe -m pytest services/worker/tests/test_readability_detector.py -k preflight`.
- Ten sam plik: dodać test `evaluate_pilot` z artefaktem o ujemnym biasie, oczekujący `STOP` z `overlap_unreadable_recall_below_90` i `all_unreadable_recall_below_90`.
- Ten sam plik: dodać test domyślnej propozycji `assign_families(samples, base)` z rodziną bazowego `test`/`regression` (oczekiwane head TEST) i rodziną bazowego `train` (oczekiwane TRAIN lub VAL).
- Opcjonalnie, jeśli przyjęta zostanie poprawka P2-1: test preflightu odrzucającego asset inny niż 64x64.

## Zakres przeglądu i ograniczenia

Przeczytałem w całości trzy nowe moduły, plik testów, brief z treścią taska i planu oraz diff dokumentów wymagań i architektury. Dla kontekstu przeczytałem fragmenty `symbol_onnx.preprocess_rgb_batch`, `SpatialSymbolCnn`, zapisu checkpointu w `training_job.py`, budowy manifestu w `training_dataset.py` oraz sekcję audytu w `AGENTS.md`.

Nie uruchamiałem testów, ruff, mypy, generatora mapy kodu ani `docs:check`. Wyniki tych kontroli opisane w Outcome przyjmuję jako deklarację wykonawcy, nie jako dowód. Nie sprawdzałem rzeczywistego checkpointu ani manifestu kandydata nr 5. Nie przeglądałem plików spoza wskazanego zakresu (`DECISION_LOG`, `CODE_MAP`, `CURRENT_STATE`, `DOC_INDEX`). Analizę zbieżności LBFGS (`state["n_iter"]`, `state["prev_loss"]`) oparłem na znanej implementacji `torch.optim.LBFGS`, bez jej uruchamiania.

## Rozliczenie jednej rundy poprawek przez wykonawcę i leada

To rozliczenie dopisano po audycie; nie jest drugą rundą niezależnego audytu.
Oryginalny werdykt audytora REVISE i jego znaleziska powyżej pozostają bez zmian.
Lead zatwierdził jedną rundę poprawek i sposób operacjonalizacji P2-2/P2-3.

- **P1-1 zamknięte**: parametryczny `test_preflight_complete_manifest_and_drift`
  ma osobne przypadki i asercje dokładnego kodu dla złego SHA datasetu/checkpointu,
  missing dataset/checkpoint/asset, uszkodzonego assetu, poprawnego PNG o innych
  pikselach, niezgodnych sourceAssignments, rodziny między splitami, duplikatu
  RGB między splitami i obcego katalogu checkpointu. Nazwa testu preprocessingu
  została poprawiona. Nie zmieniono zachowania produkcyjnego objętego P1.
- **P2-1 zamknięte**: base preflight sprawdza RGB64x64 każdego assetu;
  osobny przypadek `native_size` sprawdza READABILITY_PREPROCESSING_DRIFT.
- **P2-2 jawnie zaakceptowane ograniczenie**: powiązanie dataset–checkpoint
  zapewnia zatwierdzony kandydat nr 5 i oba SHA z planu, nie samo ogólne API
  preflightu. Zapisano w D-578, planie i Outcome; brak zgody na dowolną podmianę.
- **P2-3 rozstrzygnięte operacyjnie przez leada**: audit200 jest jednostajnym
  losowaniem dotąd nieoznaczonych pól z rodzin poza pilotem i bazowym TRAIN/VAL;
  receipt przed etykietami/fitem. Raport dotyczy tylko tej puli, nie całej gry.
  Izolacji nie osłabiono. Łączny limit 800 (600+200) ma osobny test odmowy dla 801 pól.
  Brak wystarczającej puli pozostaje STOP. Zapis w D-578/planie/Outcome.
- **P2-4 zamknięte**: malformed manifest/JSON i artifact mają stabilne kody;
  loader odrzuca także NaN, brak pliku i nieobiektowy JSON. Brak
  assetChecksumKind stosuje historyczne sha256-bytes zgodnie z trenerem.
  Przypadki te są przetestowane.
- **P2-5 zamknięte**: osobne testy dla recall 0 → STOP z oboma kodami nawet przy
  odbiorze operatora oraz domyślnego splitu 60/20/20 z ochroną bazowych TEST/REG/TRAIN.

Wynik po jednej rundzie: **37 passed in 17.24s** w
`services/worker/tests/test_readability_detector.py`, ruff PASS. Mypy trzech
modułów, mapa i kontrole dokumentacji rozliczone w końcowym Outcome taska.
Otwarte P0/P1 po rozliczeniu leada: **brak**. Nie wykonywano ponownego audytu,
ponieważ poprawka P1 obejmowała wyłącznie testy; korekty zachowania dotyczą P2.
Nie wykonano pilota ani operacji na danych operatora.

Końcowa kontrola typów po korektach jest **partial**, nie PASS: standardowy
mypy silent osiągnął 60 s; pojedynczy scopedconfig strict na 3 moduły (bez importów
API i istniejących worker.images, ale z normalnymi numpy/torch/stubami)
zakończył się wewnętrznym błędem mypy 1.17.1 `Cannot serialize TypeGuardedType
instance` przy write_cache, kod 1. Nie ponawiano ani nie osłabiono kontroli.
Przed audytem mypy 3 modułów był PASS. Lead dopuścił zamknięcie z jawnym
ograniczeniem narzędzia; 37 testów oraz ruff po korektach są zielone.

Dodatkowa celowana kontrola po wskazaniu przez leada przyczyny serializacji cache: ten sam scoped strict config z `--cache-dir=nul` (specjalna ścieżka os.devnull obsługiwana przez mypy) nie zwrócił wyniku przez 60 s i został zatrzymany zgodnie z regułą ciszy. Nie wykonano kolejnych prób. Nie osłabiano typów numpy/torch ani nowych modułów; końcowy status kontroli typów po korektach pozostaje partial.
