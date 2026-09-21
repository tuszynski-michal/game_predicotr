---
title: TASK-0605 — Walidacja T05 i adopcje profilu geometrii V7
status: done
---

# TASK-0605 — Walidacja T05 i adopcje profilu geometrii V7

## Status

`done`

## Goal

Dostarczyć trwały, fail-closed kontrakt raportu T05 oraz read-only/adoption
registry, który może dopuścić konkretny profil geometrii wyłącznie dla gry z
przeszłą, niezależną walidacją poza holdoutem, bez aktywacji V7.

## Context

TASK-0604 dostarczył obserwator związany z profilem, ale profil 777 nadal
wymaga rzeczywistych anotacji T0603. Istnieją już czyste modele metryk T05 i
`V7GeometryAdoption`, jednak raport jest wyłącznie artefaktem skryptu, a API
zwraca pustą listę adopcji. Ten task przenosi kontrolę tożsamości raportu,
profilu, gry i zbioru walidacyjnego do trwałego server-owned registry. Nie
wykonuje żadnego skanu ani nie interpretuje pustych metryk jako sukcesu.

## Dependencies / entry conditions

- TASK-0599–0604 są ukończone, a T0603 pozostaje `blocked` na ręcznych
  punktach. Implementacja użyje fixture'ów `passed`; żadna rzeczywista adopcja
  nie powstanie bez późniejszego profilu T0603 i własnego raportu T05.
- Zatwierdzony plan `.tmp/V7_LABEL_GEOMETRY_CALIBRATION_UI_PLAN.md` określa
  T0605 jako non-holdout validation, quality i adoption. `reels_test` oraz
  dowolny split `holdout` pozostają wyłącznie dla T0606/T12.
- Przyjęta wartość: raport T05 jest canonical, immutable JSON utworzony po
  pełnej walidacji server-owned tożsamości źródeł. Adopcja nie przyjmuje
  dowolnego fingerprintu raportu od klienta — wybiera wyłącznie zapisany,
  przechodzący raport o tym samym profilu, rodzinie, grze i manifeście.

## Recommended execution

`gpt-5.6-terra`, reasoning `xhigh`. Zmiana obejmuje trwały format artefaktu,
walidację bezpiecznych splitów, API oraz content-addressed registry. Po
self-audycie wymagany jest niezależny review `gpt-6-astra`, reasoning `medium`.
Wykryte P0–P2 poprawić przed commitem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-404, D-411–D-416)
- `ai_docs/requirements/IMAGE_SELECTION.md` (T05/T12 i aktywacja V7)
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `.tmp/V7_LABEL_GEOMETRY_CALIBRATION_UI_PLAN.md` — TASK-0605
- `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_calibration.py`
- `scripts/evaluate_v7_calibration.py`
- `services/api/src/game_predictor_api/application/v7_label_geometry_calibration.py`
- `services/api/src/game_predictor_api/api/v7_label_geometry_calibration.py`

## Scope

- Utrwalić canonical report T05 zawierający dokładny fingerprint profilu,
  rodziny, `sourceGameRef`, manifestu i zamrożonego inwentarza oraz oddzielne
  metryki: recovery zakresów, reprezentantów, top/bottom warningów, błędne
  automatyczne zakresy, false positives i manual review.
- Przyjąć tylko `development`, `calibration` lub `validation`, odrzucić
  `holdout`/`reference_only`, drift inwentarza, profil niepassed, niezgodną
  rodzinę, grę, checksumę źródła, puste mianowniki i niezaliczony raport.
- Utworzyć content-addressed registry raportów i adopcji pod runtime root;
  ponowienie identycznego zapisu jest idempotentne, inna zawartość pod tym
  samym identity jest konfliktem. Lista adopcji API pokazuje wyłącznie trwałe,
  zweryfikowane rekordy.
- Udostępnić zgodne rozszerzenie API/OpenAPI do zapisania zatwierdzonego
  raportu i utworzenia adopcji. Żądania nie przenoszą ścieżek, bitmap ani
  arbitralnych outcome'ów OCR; przyjmują tylko dokument truth/raw prediction
  i server resolves profile oraz corpus.
- Zachować brak aktywacji V7, outputu, writerów, obsługi holdoutu i UI
  selekcji. Ocena jakości obserwatora pozostaje `unknown`; raport z takim
  wynikiem może zostać zapisany jako failed/not_evaluable, nigdy adoptowany.

## Out of scope

- Ręczne wprowadzanie danych truth przez nowy ekran, rzeczywista kalibracja
  777, skanowanie OCR, tuning progów, geometria plansz/symboli/payoutów,
  aktywacja T0607, T12/T0606 i zapis JPEG do `cut`.
- Zmiana kryteriów `>=95%`, `zero` błędnych zakresów i `100%` recallu albo
  wielokrotne dostrajanie na tych samych danych.

## Acceptance criteria

- [x] Raport T05 wiąże profil, rodzinę, grę, manifest i inwentarz oraz nie
  może mieszać source identity, splitów, checksum ani wyników ręcznych z
  automatycznymi.
- [x] Puste mianowniki mają status `not_evaluable`; raport passed wymaga
  95% recovery, 95% reprezentantów, zero błędnych zakresów i 100% top/bottom
  recallu. Późniejsza ręczna korekta nie poprawia wyniku automatu.
- [x] Adopcja jest możliwa tylko z utrwalonego raportu passed, dokładnie dla
  jego profilu, rodziny i `sourceGameRef`; raport fail/not-evaluable,
  `holdout`, inna gra albo brak profilu kończą się fail-closed.
- [x] Restart, utracona odpowiedź, drugi identyczny request i konflikt innej
  treści mają deterministyczne zachowanie, a API/OAS nie ujawnia ścieżek.
- [x] `reels_test`, bramka startu V7 i historyczne endpointy pozostają bez
  zmiany zachowania.

## Technical notes

Nowy report registry nie ufa klientowi w kwestii identity źródeł. Dla każdego
case'u usługa pobiera manifest, zamraża inwentarz przed i po walidacji,
rozwiązuje źródła wyłącznie po stronie serwera oraz porównuje `sourceId`, SHA,
case, split, rodzinę i grę. Widoczne są tylko obiekty Pydantic; ścieżka JPEG
nigdy nie opuszcza backendu.

`V7AcceptanceTruth` pozostaje manualnym, niezależnym opisem sprawdzonych
przypadków. Predykcja zawiera surową decyzję automatu i wybrany, checksummowany
source. Usługa sama wyprowadza correct/incorrect oraz metryki przez istniejący
kontrakt domenowy, a caller-supplied snapshot oznacza jako `unknown` quality.
Tylko przyszły, server-owned wynik `acceptable` będzie mógł zaliczyć
reprezentanta; `unknown` obecnego obserwatora nie może tworzyć adopcji.
`manualReview` jest raportowany, nie jest poprawką wyniku.

Zapis raportu ma operację UUID. Serwer porównuje canonical fingerprint requestu
przed kontrolą rewizji, a wynikowy plik publikuje atomowo. Adopcja ma własny
UUID i wymaga istniejącego raportu; ponowienie z tym samym payloadem zwraca ten
sam record. Record nie może być nadpisany przez późniejszy raport lub profil.

## Expected files

- Istniejące: `v7_calibration.py` — rozszerzenie własności raportu T05, bez
  zmiany kontraktu T12.
- Nowe: `v7_label_geometry_validation.py` — canonical parsing, server-side identity
  validation oraz atomowy, content-addressed registry raportów i adopcji.
- Istniejące: `v7_label_geometry_calibration.py` — facade service, profil i
  manifest jako źródła prawdy.
- Istniejące: router oraz schematy V7 label geometry — addytywne endpointy,
  OpenAPI i odpowiedzi adopcji.
- Nowe: testy report registry oraz rozszerzenia API.
- Istniejące: dokumenty wymagań, architektury, decision log i current state.

## Test cases

- Pełny fixture registry z niezależnymi source SHA, split `validation`,
  profilem passed i server-owned jakością na granicy progów → trwały report i
  adopcja gry 777; publiczny endpoint nie może sam utworzyć takiej adopcji.
- Jeden zły automatyczny zakres, brak top/bottom warningu, pusty mianownik lub
  source bez własnego dowodu → report failed/not_evaluable, brak adopcji.
- Holdout/reels, reference-only, inna rodzina, inny `sourceGameRef`, drift
  manifeście/inwentarza albo selected source z innym SHA → reason-coded error.
- Zapis reportu → restart service → identyczny request oraz adopcja → ten sam
  record; inna treść tego samego operation ID/report fingerprintu → conflict.
- OpenAPI pokazuje wyłącznie dozwolone pola; domyślne `GET adoptions` nadal
  zwraca pustą listę na pustym registry.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr; timeout <= 120 s
.venv\Scripts\python.exe -m pytest services\worker\tests\test_v7_calibration.py services\api\tests\test_v7_label_geometry_calibration_api.py -q
.venv\Scripts\python.exe -m ruff check services\worker\src\game_predictor_worker\semi_automatic_selection\v7_calibration.py services\api\src\game_predictor_api\application\v7_label_geometry_calibration.py services\api\src\game_predictor_api\api\v7_label_geometry_calibration.py services\api\src\game_predictor_api\schemas\v7_label_geometry_calibration.py
```

Task kończy się po testach, self-audycie, review Astra Medium, poprawie błędów
i osobnym commicie. Rzeczywisty raport/adopcja oraz T12 nadal wymagają
niezależnych danych operatora; implementacja nie może ich symulować.

## Risks / open questions

- Brak rzeczywistego profilu i truthu oznacza, że po tym tasku registry może
  być prawidłowo pusty. To oczekiwany stan fail-closed, nie błąd metryki.
- Obecny obserwator nie mierzy jeszcze jakości plansz; może więc wystawić tylko
  raport failed/not-evaluable. Nie wolno obniżać kryteriów, aby uzyskać adopcję.

## Outcome

### Zmieniono

- Dodano immutable, canonical registry raportów T05 i adopcji. Report i
  adoption są publikowane przez `temp → fsync → hard-link`; odczyt odrzuca
  niekanoniczną lub podmienioną zawartość. Wspólna blokada procesu i pliku
  serializuje zapis obiektu z receiptem, a osierocony obiekt jest niewidoczny
  do czasu dokładnego replayu operacji.
- Serwis API sam rozwiązuje profil, corpus case'y, source identity i inventory,
  a z truthu oraz raw snapshotu wyprowadza metryki. Nie przyjmuje
  `rangeOutcome` ani `representativeOutcome`.
- Dodano typowaną mutację raportu/adopcji w OpenAPI i kliencie Admina.
  Odpowiedzi nie zawierają filesystem paths ani bitmap.
- Publiczny snapshot nie przyjmuje `qualityStatus`; backend przypisuje
  niezweryfikowaną jakość `unknown`, więc report z obecnego obserwatora nie
  może utworzyć adopcji.
- Fingerprint inwentarza raportu obejmuje również bezpiecznie rozwiązany
  fizyczny root korpusu. Registry wyprowadza ponownie klucz adopcji i sprawdza
  jej powiązanie z utrwalonym raportem `passed` także przy odczycie.
- Poprawiono recovery receiptów: ich replay jest obsłużony przed każdą nową
  walidacją zmiennego korpusu, natomiast inna treść tego samego UUID pozostaje
  konfliktem.

### Weryfikacja

- `.venv\Scripts\python.exe -m pytest services\worker\tests\test_v7_calibration.py` oraz
  testy API w krótkich partiach — łącznie 25 testów przeszło, w tym zmiana
  korzenia przy identycznym inventory, osierocone report/adoption po awarii,
  konflikt współbieżnych operacji, client-supplied quality oraz pół-zakres.
- Ruff i Mypy zmienionych modułów Python przeszły.
- `npm run check:generated --workspace @game-predictor/admin-api-client`,
  `npm run typecheck --workspace @game-predictor/admin-api-client` oraz
  `npm run test --workspace @game-predictor/admin-api-client` — przeszły;
  58 testów klienta Admina jest zielonych.
- Końcowy review `gpt-6-astra`, reasoning `medium` — brak uwag P0–P2 po
  sprawdzeniu provenance jakości, recovery registry, blokady publikacji,
  weryfikacji linked reportu, identity fizycznego rootu oraz kontraktu OpenAPI.

### Niewykonane celowo

- Nie utworzono realnego reportu, adopcji ani pliku JPEG. T0603 nadal wymaga
  ręcznie oznaczonych punktów dla profilu 777.
- Nie uruchomiono OCR, nie zmieniono bramki aktywacji V7, handlera jobów,
  workera selekcji, writera ani niezależnego holdoutu `reels_test`.

### Kolejny krok

Wznowić T0603 po dostarczeniu przez operatora wymaganych anotacji. Dopiero
profil `passed`, raw snapshot obserwatora i niezależny truth pozwolą przygotować
rzeczywisty report T05; T0606/T12 nadal wymagają osobnego, niezależnego holdoutu.
