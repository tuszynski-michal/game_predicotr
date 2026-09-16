# TASK-0536 — aktywacja v12 jako głównego silnika cropów

## Status

`done`

## Goal

Ustawić odebrany przez operatora silnik v12 jako domyślną, trwałą politykę
wszystkich nowych sesji `Przytnij wybrane zdjęcia`, bez niejawnego przeliczania
sesji już rozpoczętych.

## Context

TASK-0534 i TASK-0535 uruchomiły v12 niedestrukcyjnie na dwóch rzeczywistych
seriach. Operator obejrzał wyniki i 14.09.2026 podjął jawną decyzję, aby ustawić
nowy silnik jako główny. Kod nadal przypina nowym sesjom v10, a flaga wydania
v12 pozostaje wyłączona.

## Dependencies / entry conditions

- Zaimplementowany i przetestowany fingerprint v12 wraz z regułą
  `complete_layout_board_buffer`.
- Rzeczywiste podglądy: 177/177 automatów w `248176 - 272016` oraz 63 automaty
  i 4 bezpieczne pełne obrazy do ręcznej oceny w `149626 - 177561`.
- Jawna decyzja operatora o aktywacji jest warunkiem wejścia i została wydana.

## Recommended execution

`gpt-6-astra`, reasoning `high`. Zmiana dotyka źródła prawdy polityki, trwałego
snapshotu sesji, workera, CLI i dokumentacji decyzji. Dodatkowy review jest
wymagany tylko przy zmianie fingerprintu lub bramek obrazu; ten task nie może
ich zmieniać.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/quality/SELECTED_CROP_V11_REGRESSIONS.md`

## Scope

- Dodać jedno jawne źródło prawdy aktywnej polityki przygotowania cropów i
  wskazać w nim v12.
- Przypinać v12 nowym sesjom aplikacji oraz używać go jako wartości domyślnej
  w przeglądarkowym workerze, fallbacku i skrypcie katalogowym.
- Zachować policy snapshot istniejących sesji v10/v11/v12 i wymaganie jawnego
  przeliczenia nierozstrzygniętych wyników.
- Włączyć bramkę wydania v12, pozostawiając v11 wyłączony.
- Dodać testy regresyjne aktywnej polityki i trwałości istniejącej sesji.
- Zaktualizować wymagania, architekturę, Decision Log i bieżący stan.

## Out of scope

- Zmiana fingerprintu, progów, detekcji, rejestracji lub reguły bufora.
- Przeliczanie albo nadpisywanie istniejących katalogów `cut`.
- Automatyczna akceptacja czterech wyników pozostawionych do ręcznej oceny.

## Acceptance criteria

- [x] Jedna eksportowana stała wskazuje v12 jako aktywną politykę, a release
      v12 jest włączony.
- [x] Nowa sesja utrwala v12 przed przygotowaniem pierwszego pliku.
- [x] Wznowiona sesja utrzymuje własną v10/v11/v12 i nie zmienia wyników.
- [x] Domyślna ścieżka UI, worker i CLI wybierają aktywną politykę.
- [x] Testy core i Admina potwierdzają aktywację oraz ochronę wznowienia.
- [x] Dokumentacja odróżnia świadomą aktywację operatora od formalnej,
      niezależnej bramki jakości, której nie należy przedstawiać jako zaliczonej.

## Technical notes

`crop-preparation.ts` jest właścicielem obsługiwanych wariantów i flag wydania,
więc otrzyma `ACTIVE_SELECTED_IMAGE_CROP_POLICY = CROP_V12_POLICY`. Nowa sesja
zapisze tę wartość w `session-v2.json`; wszystkie dalsze operacje korzystają z
przypiętego snapshotu. Odczyt starego snapshotu nie może zastępować jego wersji
aktywną stałą. Brak lub nieobsługiwana historyczna wersja nadal wymaga jawnej
akcji przeliczenia.

## Expected files

- Istniejący: `packages/manual-image-selection-core/src/crop-preparation.ts` —
  źródło aktywnej polityki i flaga wydania.
- Istniejące: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-{storage,worker,worker-client,workspace}.ts*`
  — domyślne wejścia i snapshot nowej sesji.
- Istniejący: `scripts/run_selected_image_crop_directories.mjs` — domyślna
  polityka CLI.
- Istniejące testy core i Admina — regresje aktywacji.
- Dokumentacja wskazana w `Relevant docs` oraz `CURRENT_STATE.md`.

## Test cases

- Import źródła polityki → aktywna wersja i release wskazują v12, v11 pozostaje
  wyłączony.
- Nowa sesja bez wyników → `preparationPolicyVersion === CROP_V12_POLICY`.
- Istniejąca sesja v10 → odczyt i wznowienie zachowują v10.
- Domyślne wywołanie workera/fallbacku/CLI → używa aktywnej stałej, bez kopii
  identyfikatora v12.
- Nierozpoznana stara polityka → nadal blokada i jawne przeliczenie.

## Verification

```powershell
npm test --workspace @game-predictor/manual-image-selection-core
npm test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/manual-image-selection-core
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run build --workspace @game-predictor/admin
```

Zaliczenie wymaga zielonych testów zmienionego pionu, typechecku i builda.
Wcześniejsze błędy pełnego lint poza zmienionym pionem należy oddzielić od
wyniku taska zgodnie z AGENTS.md.

## Risks / open questions

- Formalna niezależna bramka dokładności v12 nie została zaliczona; aktywacja
  jest świadomą decyzją operatora po ocenie rzeczywistych podglądów. Mechanizm
  fail-closed i ręczna kolejka pozostają bez zmian.
- Brak pytań blokujących: operator jawnie polecił ustawienie v12 jako głównego.

## Outcome

### Changed

- Dodano jedno źródło aktywnej polityki i ustawiono je na v12; flaga wydania
  v12 jest włączona, a v11 pozostaje wyłączony.
- Nowe sesje, browserowy worker, fallback i runner katalogowy domyślnie używają
  v12. Odczyt istniejącego `session-v2.json` zachowuje jego przypiętą wersję.
- Nie zmieniono fingerprintu, detekcji, rejestracji ani danych operatora.

### Verification results

- 95/95 testów core, 458/458 testów Admina i 8/8 testów trwałego runnera
  przeszło.
- Typecheck core i Admina, pełny lint Admina oraz produkcyjny build Admina
  przeszły.
- Pierwsze uruchomienia wieloprocesowych testów i builda w sandboxie zatrzymał
  systemowy `spawn EPERM`; te same komendy zakończyły się poprawnie po
  uruchomieniu poza tym ograniczeniem.

### Not completed

- Nie przeliczono istniejących katalogów ani rozpoczętych sesji.
- Nie przedstawiono formalnej niezależnej bramki jakości v12 jako zaliczonej.

### Documentation updates

- Zaktualizowano wymagania, architekturę, raport jakości, Decision Log i
  `CURRENT_STATE.md`.

### Recommended next task

- Brak wymaganego zadania wdrożeniowego. Kolejne nowe sesje mogą korzystać z
  v12; rozpoczęte sesje przechodzą na niego przez istniejącą jawną akcję
  przeliczenia.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0536 — aktywacja v12 jako głównego silnika cropów | gpt-6-astra | high | Zmiana domyślnej polityki musi zachować trwałe snapshoty rozpoczętych sesji, spójność UI/worker/CLI i jawny audyt decyzji. | Nie; o ile fingerprint i bramki obrazu pozostają bez zmian. |
