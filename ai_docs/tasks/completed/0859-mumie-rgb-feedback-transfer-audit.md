---
title: TASK-0859 — audyt przeniesienia poprawki RGB z 777 do Mumii
status: done
last_updated: 2026-10-05
---

# TASK-0859 — audyt przeniesienia poprawki RGB z 777 do Mumii

## Status

`done`

## Goal

Ustalić na istniejącym kodzie, zamrożonych wynikach i dokładnych cropach,
które zasady poprawki 777 już spełniają Mumie, a które wymagają osobnej oceny.

## Context

Operator wskazał handoff RGB/feedback z 2026-10-05 podczas dalszych prac nad
Mumiami. Trwała zgoda na samodzielną diagnostykę i poprawki pozostaje ważna.
Nie oznacza to przeniesienia wag, klas ani zgody na aktywację modelu.

## Dependencies / entry conditions

- TASK-0858 udostępnia dokładne 18 cropów oraz osobny magazyn decyzji.
- Zamrożone raporty RGB/gray V1 i V2 zawierają te same 84 próbki walidacji.
- D-498 potwierdza pochodzenie nagrań; nie pytamy operatora ponownie.
- D-500 i D-501 zachowują granicę treningu oraz trainable=false crop-review.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`; samodzielny odrębny przegląd dowodów.
Zakres jest odczytowy i nie wymaga delegowania. Rozbieżność bindingów lub
zmiana etykiet w trakcie odczytu zatrzymuje analizę zależnych wyników.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-494, D-498, D-500, D-501)
- `C:/Users/tuszy/Documents/game_predicotr/ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md`
- `ai_docs/quality/MUMIE_SYMBOL_MODELS_20261005.md`
- `ai_docs/quality/MUMIE_SYMBOL_ROBUSTNESS_20261005.md`
- `ai_docs/tasks/completed/0858-mumie-batch-symbol-correction.md`

## Scope

- Porównanie oryginalnego RGB, normalizacji, spatial head i mapowania klas.
- Odczyt zweryfikowanych raportów i porównanie RGB, gray oraz istniejącej
  fuzji na identycznej walidacji, także osobno dla każdej klasy.
- Ograniczony odczyt 18 przypadków: propozycje obu gałęzi i rzeczywiste
  bieżące decyzje operatora oraz wyniki per klasa względem ukończonych
  podczas analizy 18 korekt, bez nadawania im kwalifikacji treningowej.
- Weryfikacja parytetu preprocessingu na istniejących dokładnych PNG.
- Zapis raportu i konkretnych zasad dalszej oceny oraz CURRENT_STATE.

## Out of scope

Zmiana domyślnego wyboru klasy, API/UI, wagi/model/słownik z 777, nowe
treningi lub ponowna inferencja 600 zdjęć, DB/migracje, etykiety za człowieka,
aktywacja, scalanie, push i wdrożenie. Nie uruchamiamy CLI audytu 777 na Mumiach.

## Acceptance criteria

- [x] Raport oddziela już zgodne przetwarzanie od różnic decyzyjnych.
- [x] Porównanie wiąże identyczne manifesty, klasy, ID próbek i etykiety;
      pokazuje błędy per klasa oraz ograniczenia małej walidacji.
- [x] Raport wskazuje faktyczną liczbę bieżących decyzji 18 przypadków.
- [x] Dowód nowego procesu potwierdza niezmienność odczytanych wejść i
      parytet preprocessingu; istniejące testy tego pionu przechodzą.
- [x] Raport zapisuje bramkę oceny: mniej błędów ogółem bez regresji klasy,
      na tym samym zbiorze; sama pewność lub zgodność modeli nie wystarcza.
- [x] Osobny commit, Outcome i CURRENT_STATE; brak zmian zachowania aplikacji.

## Technical notes

Używamy istniejących `symbol_models.compare/metrics/probabilities`,
`RunState`, `verify_artifact`, `SymbolTrainingAdapter` i checksumowanych
referencji. Raport diagnostyczny nie zastępuje starych comparison.json ani
manifestów partii, których dokładny replay nadal wymaga oryginalnej fuzji.
RGB-primary to hipoteza do późniejszej kontrolowanej oceny, nie nowy default.

## Expected files

- Nowy raport: `ai_docs/quality/MUMIE_RGB_FEEDBACK_TRANSFER_20261005.md`.
- Bieżący task i `ai_docs/process/CURRENT_STATE.md`.
- Odrębne dowody pod absolutnym
  `C:/Users/tuszy/Documents/game_predicotr/artifacts/mumie-rgb-feedback-20261005`.

## Test cases

Istniejący test exact preprocessing, disagreement/low confidence,
walidacyjna kalibracja, mapowanie słownika i wiązanie identycznych próbek.
Faktyczne 18 PNG pozostają RGB96 z właściwymi byte/pixel SHA.

## Verification

Odczytowy skrypt dowodowy uruchomiony dwukrotnie w nowych procesach oraz
istniejące testy `test_vision_lab_symbol_batch.py` i
`test_vision_lab_symbol_training.py`, z limitem 120 s na krok. Brak benchmarku.
Przed commitem kontrola staged diff/stat/list; po commicie show/status.

## Risks / open questions

Walidacja ma tylko 84 pola z dwóch zdjęć; wybór epoki i kalibracja już jej
używały. Nie jest ślepym testem końcowym. Celowo wybrane 18 trudnych cropów
to diagnostyka, nie estymator jakości całej populacji. Brak etykiet operatora
blokuje liczenie accuracy partii, ale nie audyt preprocessingu i kontraktów.

## Outcome

### Changed

- Read-only comparison of the 777 handoff with Mumie, including exact
  preprocessing, dictionary order, frozen validation and 18 operator labels.
- Per-class improvement gate recorded; RGB-primary fails it. No default change.
- Commit: `v1.7.205`.

### Verification results

- 29 existing batch/training tests passed in the installed test runtime.
  Training runtime lacked pytest; no package installed.
- All 18 approve decisions verified at revision18 with exact RGB96 PNGs.
  RGB/gray preprocessing equals the training transform pixel-for-pixel.
- V1 RGB/gray/fusion:11/10/10 correct out of18; V2:10/13/11.
  All variants83/84 on the reused small validation, with identical class counts.
- Fresh-process exact replay passed, all tracked input SHA unchanged.
  Evidence199f2b585845887455fec2f4e92090e7b733a76fa9c531b649f369e6bff53f84.
- Own separate criterion-by-criterion review found no unresolved P0–P2.

### Not completed

- No training qualification, new training, reference library transfer,
  model activation, API/UI change, DB, restart, merge/push or deployment.
- The targeted18 cases do not establish general accuracy. New operator
  decisions remain trainable=false until explicit derived qualification.

### Documentation updates

- ai_docs/quality/MUMIE_RGB_FEEDBACK_TRANSFER_20261005.md and CURRENT_STATE.
  Existing requirements/architecture/default behavior remain unchanged.

### Recommended next task

Qualify the 18 exact corrected crops in a separate immutable training cohort,
then train a bounded next iteration and evaluate unused sources. Do not
re-request the completed labels or the already confirmed recording provenance.
