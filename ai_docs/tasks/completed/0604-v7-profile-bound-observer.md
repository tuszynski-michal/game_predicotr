---
title: TASK-0604 — Obserwator V7 związany z profilem geometrii
status: done
---

# TASK-0604 — Obserwator V7 związany z profilem geometrii

## Status

`done`

## Goal

Dostarczyć recognition-only obserwator V7, który używa wyłącznie niezmiennego
profilu geometrii i własnych pikseli JPEG-a do utworzenia bezpiecznej obserwacji
źródła, bez odblokowania startu V7 ani publikowania wyników.

## Context

TASK-0598 ma trwały runtime z fabryką obserwatora, ale domyślnie odmawia pracy
przed otwarciem JPEG-a. TASK-0603 przygotował realną kalibrację, lecz nie może
tworzyć profilu bez świadomych danych operatora. Ten task implementuje adapter
i checkpointowalny kontrakt trackera wystąpień na profilach testowych; nie zastępuje brakującej
kalibracji 777 ani nie zmienia blokady API.

## Dependencies / entry conditions

- TASK-0599–0602 są ukończone; TASK-0603 jest `blocked` na rzeczywistej
  anotacji, ale sam adapter można zweryfikować na izolowanych fixture'ach
  profilu `passed`.
- V7 pozostaje `blocked` po stronie API. Nie wolno podłączać fabryki jako
  domyślnego runtime'u joba ani tworzyć lokalnego profilu z odgadniętych danych.
- Ustalone wartości: pięć zgodnych, wiarygodnych własnych etykiet daje mocny
  dowód; dokładnie trzy są słabą hipotezą; tylko 3+3 z innego klastra wizualnego
  w tym samym wystąpieniu może dać dowód wieloklatkowy. 3+2, konflikt szóstej
  wiarygodnej etykiety, obca klatka i brak profilu pozostają `none` albo
  reason-coded failure.

## Recommended execution

`gpt-5.6-terra`, reasoning `xhigh`. Zmiana łączy profil, EXIF-canonical decode,
OCR, dowód, checkpoint i runtime, więc po self-audycie wymagany jest niezależny
review `gpt-6-astra`, reasoning `medium`. Wykryte P0–P2 poprawić przed commitem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-411–D-416)
- `ai_docs/requirements/IMAGE_SELECTION.md` (kontrakt V7 i blokada startu)
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `.tmp/V7_LABEL_GEOMETRY_CALIBRATION_UI_PLAN.md` — TASK-0604
- `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_calibration.py`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_label_locator.py`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_range_proof.py`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_worker_runtime.py`

## Scope

- Związać `V7GeometryProfile(status=passed)` z dokładnym fingerprintem
  kalibracji i lokalizatora w `V7WorkerConfiguration` przed dekodowaniem źródła.
- Dekodować tylko bajty uprzednio zweryfikowane SHA, stosować EXIF transpose
  raz, wycinać wyłącznie dziewięć numerycznych cropów konfiguracji profilu i
  wywoływać recognition-only backend.
- Wykonać source-local proof 5 etykiet i przekazać jedynie jednoznaczną słabą
  hipotezę 3 etykiet. Stan potrzebny do 3+3 ma należeć wyłącznie do
  checkpointowanego trackera wystąpień razem z prefiksem runtime'u, aby restart
  nie zgubił albo nie sfałszował potwierdzenia.
- Zwrócić kompletne `V7ScanObservation`: decoded frame otrzymuje jawną jakość
  `unknown`, a błąd dekodowania source-local `SOURCE_DECODE_ERROR`; adapter nie
  wywołuje geometrii plansz, symboli, payoutów ani writera.

## Out of scope

- Ręczna anotacja, tworzenie realnego profilu, adopcje gier, truth/holdout,
  ocena jakości plansz, aktywacja API, UI, output `cut` i dowolne automatyczne
  zaznaczanie punktów.
- Zmiana progów dowodu, kalibracji p95 albo zastąpienie historycznych OCR.

## Acceptance criteria

- [x] Fabryka odrzuca brakujący, niepassed albo niezgodny profil zanim odczyta
  JPEG i nie zastępuje `UnavailableV7SourceObserverFactory` jako default.
- [x] Obserwator używa dokładnie profilu, zweryfikowanych bajtów źródła i
  canonical EXIF RGB; nie przyjmuje oczekiwanego zakresu jako wejścia OCR.
- [x] 5, 3+2, 3+3, re-encode/wizualny duplikat, konflikt szóstej etykiety,
  uszkodzony JPEG i restart między obiema klatkami mają deterministyczne,
  reason-coded wyniki.
- [x] Checkpoint trackera wystąpień zawiera małą, własną słabą hipotezę; obcy,
  uszkodzony albo brakujący stan oczekujący dla wznowionego skanu jest
  fail-closed. Obserwator pozostaje bezstanowy.
- [x] Nie ma aktywacji V7, outputu ani wywołania kodu symboli/plansz.

## Technical notes

Nowa fabryka przyjmuje profil i backend przez jawne zależności. Konfiguracja
runtime'u musi zawierać fingerprint tego samego profilu oraz fingerprint
lokalizatora wyprowadzony z jego canonical payloadu. Brak zgodności to
`V7_CALIBRATION_FINGERPRINT_MISMATCH` przed `read_bytes`.

V7WorkerRuntime przekazuje obserwatorowi tylko bajty, których SHA jest równe
przypiętemu źródłu; nie przekazuje ścieżki do ponownego odczytu. Stan 3+3
zapisuje atomowo checkpoint istniejącego trackera wystąpień razem ze stanem
skanu. Obserwator nie ma checkpointu, dlatego nie może dublować granic
wystąpienia ani po restarcie sfałszować drugiego dowodu.

Słaba hipoteza przechowuje najwyżej małe metadane dowodowe, 64-bitowy hash
wizualny i 64-bajtową, trzybitową sygnaturę średnich obrazu, nie bitmapę.
Zmiana jedynej aktywnej hipotezy zakresu otwiera nowe wystąpienie; brak dowodu
nie cofa kursora. Dwa źródła są niezależne tylko, gdy mają inne ID, to samo
wystąpienie i różne klastry wizualne; zgodna sygnatura lub dostatecznie bliski
hash oznacza duplikat, także po rekompresji JPEG-a. Ostateczne granice
wystąpienia i ranking nadal należą do `V7OccurrenceTracker` / EOF runtime'u.

## Expected files

- Istniejące: `v7_range_proof.py` — publiczny odczyt jednoznacznej słabej
  hipotezy bez zmiany progów.
- Istniejące: v7_occurrences.py i v7_run_state.py — trwała słaba hipoteza
  należy do trackera wystąpień i jest przekazywana wyłącznie dla przypiętego
  źródła.
- Istniejące: v7_worker_runtime.py — canonical source bytes i wersjonowanie
  runtime'u dla tego bezpiecznego kontraktu.
- Nowe: v7_profile_bound_observer.py — profilowa fabryka, EXIF decode,
  lokalizator, OCR i wyłącznie source-local evidence.
- Nowe: `services/worker/tests/test_v7_profile_bound_observer.py`.
- Istniejące: services/worker/tests/test_v7_occurrences.py — restart z
  checkpointem oczekującego dowodu 3+3.
- Istniejące: `CURRENT_STATE.md` i wymaganie V7 po ustaleniu runtime contract.

## Test cases

- Profil `passed` z pasującymi fingerprintami + pięć etykiet → mocny dowód z
  własnym `sourceId`; do OCR trafiają wyłącznie cropy profilu.
- Trzy + dwa → `none`; trzy + trzy z różnymi cechami wizualnymi i wspólnym
  aktywnym wystąpieniem → `multi_frame_three_plus_three`; identyczna
  sygnatura po rekompresji JPEG-a → `none` także po restarcie trackera.
- Pięć zgodnych + szósta wiarygodna sprzeczna → `CONFLICTING_RELIABLE_LABEL`.
- Restart po pierwszej słabej klatce → tracker może użyć wyłącznie odtworzonego,
  zgodnego stanu; usunięty/obcy stan kończy się fail-closed.
- Uszkodzony JPEG → pojedynczy `SOURCE_DECODE_ERROR`, bez dowodu i bez jakości
  udającej pomiar; niezgodny profil → odrzucenie przed odczytem bajtów.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr; timeout <= 120 s
.venv\Scripts\python.exe -m pytest services\worker\tests\test_v7_range_proof.py services\worker\tests\test_v7_profile_bound_observer.py services\worker\tests\test_v7_occurrences.py services\worker\tests\test_v7_run_state.py services\worker\tests\test_v7_worker_runtime.py services\worker\tests\test_semi_automatic_selection_job.py -q
.venv\Scripts\python.exe -m ruff check services\worker\src\game_predictor_worker\semi_automatic_selection\v7_range_proof.py services\worker\src\game_predictor_worker\semi_automatic_selection\v7_profile_bound_observer.py services\worker\src\game_predictor_worker\semi_automatic_selection\v7_worker_runtime.py
```

Task kończy się po testach, self-audycie, review Astra Medium, poprawie błędów
i osobnym commicie. Brak rzeczywistego profilu nadal blokuje następny pomiar i
aktywny V7, lecz nie unieważnia testowalnego kontraktu adaptera.

## Risks / open questions

- Pierwszy profil 777 nadal wymaga danych operatora; fixture testowy nie jest
  profilem produkcyjnym ani nie może przejść do adopcji.
- Metryka visual hash jest wyłącznie konserwatywną bramką niezależności
  dowodów. Jej skuteczność na rzeczywistym korpusie zostanie zmierzona w T0605;
  nie będzie strojenia na `reels_test`.

## Outcome

Zaimplementowano profilowy, stateless obserwator V7 oraz checkpointowaną
obsługę dokładnego dowodu 3+3 po stronie trackera wystąpień. Runtime v2 wiąże
checkpoint z fingerprintami kalibracji i lokalizatora, a obserwator dostaje
wyłącznie uprzednio zweryfikowane bajty JPEG-a. Cechy wizualne nie utrwalają
bitmap: 64-bajtowa sygnatura blokuje potwierdzenie rekompresji tej samej
tekstury także po restarcie. 70 testów skoncentrowanych, Ruff i formatowanie
przeszły; mypy zatrzymało wyłącznie wcześniejsze 13 błędów poza zakresem w
`images/structured_geometry`. Self-audyt oraz końcowy Astra Medium nie
stwierdziły błędów P0–P2. API, writer i rzeczywista aktywacja V7 pozostają
zablokowane.
