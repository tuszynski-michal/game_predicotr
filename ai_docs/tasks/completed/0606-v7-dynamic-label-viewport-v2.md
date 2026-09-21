---
id: TASK-0606
title: Dynamiczny viewport etykiet V7 V2
status: done
owner: Codex
---

# TASK-0606 — Dynamiczny viewport etykiet V7 V2

## Goal

Zastąpić dla nowej rodziny V2 stałe współrzędne liczbowych etykiet V7 lokalnym wykryciem siatki 3 × 3 i normalizacją punktów względem tej siatki. To ma umożliwić późniejszą adopcję przez inną grę bez dzielenia symboli, payoutów ani danych per-gra.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/delivery/V7_DYNAMIC_LABEL_VIEWPORT_V2_EXECUTION_PLAN.md`
- `ai_docs/delivery/GLOBAL_GEOMETRY_LIBRARY_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- Wersjonowany `standard_3x3_numeric_labels_v2` przy zachowaniu V1.
- Kalibracja w układzie lokalnej 3 × 3 siatki z co najmniej pięcioma pełnymi punktami obejmującymi dwa wiersze i dwie kolumny.
- Deterministyczny, niezależny od koloru ramki detector komponentów tekstu i siatki; cropy OCR są tworzone tylko po jego jednoznacznym sukcesie.
- Runtime observer akceptuje V1 i V2, ale nie zmienia proofów ani outputów.
- Aktualizacja dokumentacji, decyzji, testów i bieżącego stanu.

## Out of scope

- Biblioteka geometrii komórek planszy G00–G07, symbole, payouty, Treasure, aktywacja V7, handler produkcyjny, writer, katalog `cut` i UI ergonomii.

## Expected files

- `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_label_locator.py`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_calibration.py`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_profile_bound_observer.py`
- odpowiednie serializery API profilu V7, jeśli kontrakt to wymaga
- `services/worker/tests/test_v7_label_locator.py`
- `services/worker/tests/test_v7_calibration.py`
- `services/worker/tests/test_v7_profile_bound_observer.py`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/CURRENT_STATE.md`

## Acceptance criteria

- [ ] Profile V1 zachowują istniejący fingerprint i wynik lokalizatora.
- [ ] V2 normalizuje poprawnie pełne, przesunięte, skalowane i perspektywiczne obrazy syntetyczne oraz nie korzysta z expected range, sekwencji ani koloru.
- [ ] Niejednoznaczna, zdegenerowana lub zbyt uboga siatka zwraca brak cropów.
- [ ] P95 V2 opisuje odchylenie względem lokalnej siatki; 5 SHA, 2 grupy, `contained` i limit `0,04` pozostają bramkami.
- [ ] Observer V2 tworzy dowód tylko z własnych cropów; V1 nadal działa.
- [ ] Nie ma profilu, aktywacji ani outputu bez późniejszego niezależnego odbioru.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services\worker\tests\test_v7_label_locator.py services\worker\tests\test_v7_calibration.py services\worker\tests\test_v7_profile_bound_observer.py -q
.venv\Scripts\python.exe -m ruff check services\worker\src\game_predictor_worker\semi_automatic_selection\v7_label_locator.py services\worker\src\game_predictor_worker\semi_automatic_selection\v7_calibration.py services\worker\src\game_predictor_worker\semi_automatic_selection\v7_profile_bound_observer.py
```

## Risks / open questions

- V2 jest wspólnym silnikiem lokalizacji etykiet, nie gotową globalną biblioteką komórek planszy. Kolejna gra wymaga osobnej, jawnej adopcji i własnego korpusu testowego.
- Rzeczywiste 777 mogą ujawnić, że detector wymaga następnego taska strojenia; wtedy profil nie może być utworzony przez obniżenie progu.

## Outcome

### Wykonane

- Dodano wersjonowaną rodzinę `standard_3x3_numeric_labels_v2` obok
  niezmienionej V1. V2 wykrywa komponenty tekstowe w obu polaryzacjach,
  dopasowuje pełną lokalną siatkę 3 × 3 i po fitcie projektowym tworzy cropy
  tylko wtedy, gdy siatka jest jednoznaczna.
- Kalibracja V2 liczy residual każdego oznaczenia względem projektowej siatki
  tego samego źródła, z zachowaniem pięciu SHA, dwóch grup, `contained` i p95
  `<= 0,04`. Kontrakt odrzuca również konfigurację lokalizatora niezgodną z
  rodziną.
- Observer oraz odczyt immutable profilu przez API obsługują oba jawne warianty;
  fingerprint nadal zawiera pełny config lokalizatora. Nie zmieniono proofów,
  trackera, gate’u, handlera ani writera.
- Zapisano plan V2 i osobne TASK-0607 zawierające wszystkie komentarze operatora
  o responsywności panelu, doborze materiałów i benchmarku 100/300/500.

### Kontrola

- Self-audyt wykrył i Astra Medium potwierdziła trzy błędy P2: konkurencyjna siatka mogła zostać ukryta przez duplikat hipotezy, jedyny słaby fit nie miał twardej bramki residualu, a odwrócona siatka operatora mogła przejść kalibrację. Poprawiono wszystkie trzy przypadki i dodano regresje; końcowy re-audyt Astra nie wskazał P0–P2.

- Przeszło 28 testów V2/V1 kalibracji, lokalizatora i observera, Ruff oraz Mypy
  zmienionych modułów.
- Próba na pierwszych 30 prawdziwych kadrach 777 znalazła pełną lokalną siatkę
  w 21/30; w pozostałych 9 zwróciła pusty wynik, bez proofu. To jest pomiar
  diagnostyczny, nie odbiór skuteczności ani podstawa aktywacji.
- Pełny test API uruchomiony w sandboxie nie mógł otworzyć/przygotować katalogu
  tymczasowego Windows. Zmiana parsera API jest objęta bezpośrednim testem
  odtworzenia payloadu V2 w pakiecie 28 testów; wcześniejsze API tests nie
  dotarły do wykonania z przyczyny środowiskowej.

### Ograniczenia

- Mumie używają znacznie mniejszych, pojedynczych etykiet niż 777. Wspólny
  silnik V2 nie miesza danych gier, lecz ich adopcja wymaga własnego profilu
  kandydatów i realnego korpusu testowego. Nie poszerzono filtra 777 kosztem
  obecnej skuteczności.
- V7 pozostaje zablokowane. Do aktywacji nadal potrzebne są kalibracja V2,
  niezależna walidacja/adopcja i osobny pion produkcyjnego handlera.