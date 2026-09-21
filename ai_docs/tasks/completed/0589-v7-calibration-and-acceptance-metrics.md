---
title: TASK-0589 — V7 calibration and acceptance metrics
status: done
last_updated: 2026-09-21
---

# TASK-0589 — Kalibracja i metryki odbioru V7

## Status

`in_progress`

## Goal

Udostępnić wersjonowaną, checksumowaną kalibrację geometrii etykiet oraz
niezależne metryki odbioru V7, które fail-closed blokują aktywację bez danych
oznaczonych przez operatora.

## Context

T02 celowo emituje `position_confidence=0.00`: stałe cropy odczytują cyfry,
ale nie dowodzą ich pozycji w rzeczywistym ujęciu. T04 definiuje klasy jakości,
lecz nie ustala progów. T05 ma rozdzielić pomiary i anotacje od kodu produktu,
wyznaczyć konfigurację tylko z calibration split oraz jasno policzyć bramki
95%/95%/zero błędów/100% ostrzeżeń bez udawania wyniku dla pustego zbioru.

## Dependencies / entry conditions

- T00–T04 są ukończone. Zamrożony manifest/inwentarz T01 jest obowiązkową
  tożsamością korpusu; `wybrane mumie` pozostają `reference_only`.
- Istnieje korpus z małymi/dużymi grupami, zasłonięciami i Treasure. Na start
  nie ma kompletnej, niezależnej ręcznej anotacji V7, więc żaden wynik nie
  może odblokować automatu przez domysł albo przez sama ocenę modelu.
- D-404 wyklucza uprzednio otwartą próbkę z niezależnego holdoutu.

## Recommended execution

`gpt-5.6-terra` z reasoning `xhigh`; wymagany niezależny review
`gpt-6-astra medium` przed commitem. Eskalować, jeśli potrzebne byłoby
oznaczenie przez użytkownika, obniżenie progu albo włączenie produkcyjne —
T05 tworzy narzędzia i bramki, nie może samodzielnie zaakceptować danych.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/quality/v7-corpus-manifest.local.example.json`
- `ai_docs/quality/V7_T02_LABEL_LOCALIZATION_PROBE.md`
- `ai_docs/tasks/completed/0585-v7-corpus-and-configuration-contract.md`
- `ai_docs/tasks/completed/0588-v7-quality-ranking-and-warnings.md`

## Scope

- Czyste kontrakty anotacji geometrii i wyników predykcji, kalibracja po
  splitach, fingerprinty, metryki i fail-closed bramka aktywacji.
- Narzędzie read-only do walidacji anotacji oraz utworzenia raportu; ograniczony
  pomiar bazowy istniejącego OCR na development/calibration.

## Out of scope

- Ręczne oznaczanie pełnego korpusu, tuning na holdoucie, aktywacja API/UI,
  zapis JPEG-a, baza, worker run, trening, klasyfikacja symboli i modyfikacja
  zewnętrznych zdjęć.

## Acceptance criteria

- [ ] Kalibracja geometrii wymaga co najmniej pięciu niezależnych, oznaczonych
  obrazów dla każdej z dziewięciu pozycji, wyłącznie ze splitu `calibration`,
  oraz zapamiętuje residual i fingerprint wejść.
- [ ] Niezależne mianowniki raportują osobno odzysk zakresów, błędne
  przypisania, reprezentanty, warningi góra/dół, fałszywe warningi i manual
  review; zero przypadków jest `not_evaluable`, a nie sukcesem.
- [ ] Bramka przechodzi dopiero przy ≥95% kwalifikowanych zakresów, ≥95%
  kwalifikowanych reprezentantów, zerze błędnych automatycznych przypisań i
  100% recall oznaczonych ucięć góra/dół.
- [ ] Zbiór do konfiguracji, walidacji i holdoutu jest rozłączny; holdout jest
  blokowany do T12 i nie może być wielokrotnie dostrajany.
- [ ] Rzeczywisty, ograniczony probe corpusowy jest read-only, sprawdza
  manifest/inwentarz i nie przedstawia liczbowego OCR jako automatycznej
  akceptacji bez kalibracji geometrii.

## Technical notes

- `v7_calibration.py` będzie przyjmował jawne anotacje z ID źródła, checksumą,
  splitem i pozycjami 3×3. Mediany normalizowanych centrów powstają wyłącznie
  z `calibration`; wymóg to minimum pięć różnych źródeł na pozycję, proponowany
  maksymalny residual p95 `0.04` oraz `position_confidence=0.95`. Są to
  wartości startowe zapisane w artefakcie, nie ukryte stałe automatu.
- Typ wyniku odbioru zawiera niezależny ground truth i predykcję dla każdego
  oznaczonego zakresu. Denominator zakresu to tylko `automatically_recoverable`;
  denominator reprezentanta to `eligible_acceptable_representative`; ręczna
  korekta nie zmienia predykcji automatu. Każdy automatyczny zły zakres blokuje
  bramkę nawet wtedy, gdy skuteczność procentowa przekracza 95%.
- Anotacja góry/dół daje dwa niezależne pola. Recall każdej dodatniej etykiety
  ma wynosić 100%; raport pokazuje również false-positive warnings i odsetek
  manual review. `not_evaluable` dotyczy pustego mianownika.
- Narzędzie wejściowe weryfikuje manifest i jego inwentarz przed odczytem
  JPEG-ów. Domyślne splity do pomiaru to development/calibration; validation
  wymaga jawnego wyboru, holdout jest odrzucony przez T05.
- T05 nie zmienia `DEFAULT_V7_GRID_LABEL_LOCATOR_CONFIG`. Dopiero przypięta,
  pozytywnie oceniona konfiguracja może zostać przekazana do future runu;
  aktywacja produkcji należy wyłącznie do T12.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_calibration.py`.
- Nowe: `services/worker/tests/test_v7_calibration.py`.
- Nowe: `scripts/evaluate_v7_calibration.py`.
- Istniejące: `TEMP PLAN V7.md`, `CURRENT_STATE.md`, `DECISION_LOG.md` i
  outcome taska.

## Test cases

- Pięć źródeł na każdą pozycję → mediana konfiguracji i residual; cztery,
  mieszany split, duplikat source/checksum albo p95 ponad limitem → blokada.
- Pełny raport 95%/95%/zero/100%, jeden błędny automatyczny zakres, brak
  mianownika, false-positive warning i ręczna korekta po automacie.
- Różne fingerprinty anotacji, próba użycia holdoutu oraz drift inwentarza
  kończą się błędem. Probe bez geometrii pozostaje `not_accepted`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_v7_calibration.py services/worker/tests/test_v7_quality.py services/worker/tests/test_v7_configuration.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection/v7_calibration.py services/worker/tests/test_v7_calibration.py scripts/evaluate_v7_calibration.py
.\.venv\Scripts\python.exe -m mypy --follow-imports=skip services/worker/src/game_predictor_worker/semi_automatic_selection/v7_calibration.py
```

## Risks / open questions

- Wartości startowe residualu i pewności są założeniem T05. Bez niezależnych
  ręcznych anotacji narzędzie ma zwrócić `not_evaluable`, a V7 pozostać
  wyłączone; nie wolno wpisać syntetycznych wyników, aby spełnić próg.

## Outcome

Dodano czysty kontrakt kalibracji `v7-calibration-v1` i skrypt
`evaluate_v7_calibration.py`. Anotacja geometrii zawiera źródło, SHA-256, split
i centrum jednej z dziewięciu pozycji. Kalibracja przyjmuje wyłącznie split
`calibration`, wymaga pięciu niezależnych źródeł na pozycję i zapisuje mediany,
residual p95 oraz fingerprint danych. Startowe wartości są jawne: pięć źródeł,
residual p95 `0.04` oraz pewność pozycji `0.95`; pomiar ponad limitem jest
raportowany jako `failed` i nie jest kandydatem do użycia.

Raport odbioru utrzymuje osobne mianowniki dla odzyskania zakresu,
reprezentanta i warningów góra/dół; wszystkie cztery bramki muszą być
ocenialne. Ręczny review nie zmienia zamrożonego wyniku automatu, a poprawka
nie może ukryć błędnego automatycznego zakresu. Jeden zakres w danym przypadku
korpusu może wystąpić tylko raz, a poprawny reprezentant wymaga poprawnego
automatycznego zakresu. Skrypt porównuje manifest, zamrożony inwentarz i SHA
każdego anotowanego źródła; odrzuca aliasy tych samych bajtów jako niezależne
źródła. Anotacja odbioru wskazuje przypadek korpusu, zakres i źródła dowodu,
a predykcja źródło wybranego wyniku, więc deklarowany split nie może zastąpić
rzeczywistej tożsamości pliku. Domyślnie akceptowane są tylko
development/calibration, validation wymaga jawnego parametru, a holdout jest
odrzucony. Każdy raport nadal blokuje aktywację do T12.

Rzeczywisty, read-only probe na zamrożonym korpusie (po jednym JPEG-u z pięciu
przypadków development/calibration) trwał 942 ms po inicjalizacji modelu.
Odczytał odpowiednio 9, 4, 0, 1 i 2 wartości numeryczne, ale zero wiarygodnych
etykiet i zero mocnych consensusów pięciu. Uruchomienie raportu z pustym,
checksumowanym szkieletem anotacji zwróciło `not_evaluable` dla wszystkich
mianowników oraz `productionActivation=blocked`. Nie utworzono anotacji
syntetycznych i nie odblokowano V7.

Self-audyt znalazł dwie korekty przed review: nieudany residual zapisuje teraz
mierzalny `failed`, zamiast gubić wynik przez wyjątek; ręczna korekta nie jest
już typem automatycznej predykcji. Astra Medium znalazła i potwierdziła
naprawę czterech dalszych luk: aliasu SHA, niepowiązanej anotacji odbioru,
sukcesu reprezentanta bez poprawnego zakresu oraz powielonego zakresu pod
różnymi ID. Testy objęły minimalną liczbę źródeł, split, duplikaty, alias SHA,
residual, mianowniki 95%/100%, błędny zakres, manual review, unikalność zakresu,
tożsamość SHA i drift inwentarza. `ruff`, `mypy` oraz 19 testów T02–T05 są
zielone; końcowy review Astra Medium: `APPROVED`. Pełny historyczny test konfiguracji używający systemowego katalogu
tymczasowego nie uruchomił się w sandboxie z powodu ACL katalogu pytest; nie
zmieniano jego kodu, a testy T05 nie zależą od niego.
