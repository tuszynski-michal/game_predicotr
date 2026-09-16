---
title: Walidacja proporcji i odzyskanie zbyt wysokich cropów
status: done
last_updated: 2026-09-16
---

# TASK-0560 — Walidacja proporcji i odzyskanie zbyt wysokich cropów

## Status

`done`

## Goal

Rozpoznawać automatyczny crop wyższy niż 78% obrazu źródłowego jako błędny
niezależnie od deklaracji detektora oraz przeliczyć aktywnym v12 rzeczywiście
zbyt wysokie JPEG-i z `303319 -326700 cut` do osobnego, wznawialnego preview.

## Context

Odczyt 2598 wyników wykazał 235 zapisanych prostokątów pełnej wysokości, lecz
kontrola rzeczywistych JPEG-ów potwierdziła 225 plików 1080×1920. Pozostałe
10 JPEG-ów ma już zwykłą wysokość 560–675 px, mimo że starszy shard nadal
opisuje pełny obraz. Wszystkie pełne wyniki powstały jako `safe_wide`; sam
zapis JPEG-a nie odróżnił bezpiecznego marginesu od nieudanego cięcia.

## Dependencies / entry conditions

- Katalogi `D:\777\303319 -326700` i `D:\777\303319 -326700 cut` są
  dostępne, a źródło i inventory mają po 2598 nazw.
- Aktywnym, dostępnym silnikiem przycinania jest v12.
- Oryginalny katalog `cut`, jego shardy, review i JPEG-i pozostają tylko do
  odczytu. Wyniki odzyskania powstają w osobnym katalogu preview.

## Recommended execution

`gpt-6-astra` z reasoning `high`. Zadanie łączy trwałą regułę domenową z
kontrolowanym przeliczeniem danych użytkownika; niezależny review jest wymagany
tylko przed zmianą oryginalnego katalogu `cut`, której ten task nie wykonuje.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `scripts/preview_selected_crop_corrections.mjs`

## Scope

- Dodać czystą walidację maksymalnej wysokości cropa równą 78% wysokości
  kanonicznego źródła; dokładnie 78% pozostaje poprawne.
- Nadać przekroczeniu stabilny powód review `crop_too_tall`, sprawdzany przed
  pozytywnym dowodem struktury lub rejestracji i odtwarzany po restarcie.
- Rozszerzyć niedestrukcyjny runner o tryb `excessive_height`, który wybiera
  kandydatów według wymiarów rzeczywistych JPEG-ów w `cut`, zachowując
  kolejność inventory.
- Związać listę kandydatów, próg i wejściowy stan z metadanymi preview oraz
  zachować dotychczasowy journal, shardy, checksumy i wznowienie.
- Uruchomić tryb na 225 rzeczywiście pełnowysokościowych JPEG-ach i sprawdzić
  raport oraz niezmienność stanu wejściowego.

## Out of scope

- Nadpisywanie, usuwanie albo naprawa shardów w oryginalnym katalogu `cut`.
- Zmiana geometrii plansz, progów rejestracji v12 albo fingerprintu detektora.
- Automatyczne dodawanie ostrzeżeń do ręcznego `correctionFileNames`.
- Przeliczanie 10 JPEG-ów, których bieżące wymiary są już prawidłowe mimo
  nieaktualnych współrzędnych w historycznym shardzie.

## Acceptance criteria

- [x] Automatyczna propozycja przekraczająca 78% wysokości źródła otrzymuje
      `crop_too_tall`, również gdy struktura albo rejestracja deklaruje sukces.
- [x] Propozycja równa 78% nie jest odrzucana samą proporcją.
- [x] Tryb odzyskania wybiera 225 rzeczywistych JPEG-ów 1080×1920 i pomija 10
      plików już przyciętych, których stare shardy nadal wskazują pełną wysokość.
- [x] Preview jest wznawialne, checksummowane i nie zmienia oryginalnego
      katalogu `cut` ani jego stanu.
- [x] Testy domenowe i runnera, typecheck, lint/format oraz właściwy build
      przechodzą.

## Technical notes

Źródłem prawdy dla nowych wyników jest `proposal.crop`; funkcja review najpierw
liczy `(bottomY - topY) / height`. Dla historycznego odzyskania nadrzędny jest
rzeczywisty nagłówek JPEG-a, ponieważ 10 plików ma rozbieżny, starszy shard.
Runner porównuje wysokość JPEG-a z wysokością źródła zapisaną w wyniku, wymaga
zgodnej szerokości i odrzuca nieprawidłowe wymiary przed utworzeniem preview.

Tryb `--too-tall` używa aktywnego v12 i najbliższych pełnych kotwic dokładnie
tak jak istniejący preview automatycznych ostrzeżeń. Lista kandydatów jest
checksummowana i zapisana wraz z progiem 0,78. Zmiana wejściowego stanu podczas
przebiegu kończy się błędem bez deklarowania sukcesu.

## Expected files

- Istniejące: `packages/manual-image-selection-core/src/crop-session.ts` —
  reguła wysokości i powód review.
- Istniejące: `scripts/preview_selected_crop_corrections.mjs` — selection
  `excessive_height` i CLI `--too-tall`.
- Istniejące: testy crop session i runnera preview.
- Istniejące: wymagania, architektura, `CURRENT_STATE.md` i `DECISION_LOG.md`.

## Test cases

- Crop 78% źródła → brak ostrzeżenia proporcji; crop 78% + 1 px →
  `crop_too_tall`.
- Rejestracja `registered` z pełną wysokością → obowiązkowe ostrzeżenie.
- Dwa historyczne wyniki z pełnym prostokątem w shardzie, lecz JPEG-i pełny i
  prawidłowo skrócony → preview wybiera wyłącznie faktycznie pełny JPEG.
- Ponowne uruchomienie tego samego preview → weryfikacja i wznowienie bez
  ponownego zapisu gotowego wyniku.

## Verification

```powershell
node --experimental-strip-types --test --test-isolation=none packages/manual-image-selection-core/test/selected-image-crop-session.test.mjs scripts/test/selected-crop-correction-preview.test.mjs
npm run typecheck --workspace @game-predictor/manual-image-selection-core
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run build --workspace @game-predictor/admin
node_modules\.bin\prettier --check packages/manual-image-selection-core/src/crop-session.ts packages/manual-image-selection-core/test/selected-image-crop-session.test.mjs scripts/preview_selected_crop_corrections.mjs scripts/test/selected-crop-correction-preview.test.mjs
```

Warunkiem zakończenia jest także raport rzeczywistego preview dla pełnej listy
oraz identyczna checksuma wejściowego `.manual-image-crop-state` przed i po.

## Risks / open questions

- Część 225 wyników może nadal wymagać ręcznej korekty, jeżeli v12 nie znajdzie
  pełnej struktury ani zgodnej kotwicy. Raport rozdzieli wyniki automatyczne i
  wymagające review; task nie przyjmie ich automatycznie do oryginalnej sesji.
- Nie ma pytania blokującego. Polecenie użytkownika upoważnia do przeliczenia,
  a istniejąca decyzja D-392 wymaga osobnego katalogu preview.

## Implementation plan

1. Dodać współdzieloną regułę wysokości oraz regresje domenowe.
2. Rozszerzyć runner o wybór według rzeczywistych proporcji JPEG-a i test
   rozbieżnego historycznego sharda.
3. Wykonać kontrole kodu, uruchomić 225 kandydatów na danych użytkownika,
   zweryfikować raport i niezmienność wejścia.
4. Zaktualizować dokumentację, Outcome i zamknąć task osobnym commitem.

## Outcome

Zadanie ukończono 2026-09-16 na bieżącym branchu `version-0.10`, bez
modyfikacji oryginalnego katalogu `303319 -326700 cut`.

### Changed

- Dodano niezależną regułę `crop_too_tall` dla wyniku przekraczającego 78%
  wysokości źródła. Ma pierwszeństwo przed pozytywnym statusem struktury lub
  rejestracji i jest odtwarzana z sharda po restarcie.
- Runner preview ma selection `excessive_height` i CLI `--too-tall`. Lista
  korzysta z rzeczywistych wymiarów JPEG-a, jest uporządkowana według inventory
  i checksummowana razem z progiem oraz stanem wejściowym.
- Utworzono `D:\777\303319 -326700 cut v12 aspect-ratio preview` dla dokładnie
  225 pełnowysokościowych JPEG-ów. V12 odzyskał 113 przez rejestrację; 112
  pozostawił jako pełne i oznaczył `crop_too_tall` do review.

### Verification results

- Testy `manual-image-selection-core`: 105/105; testy runnera preview: 4/4;
  skoncentrowane kontrakty Admina: 32/32; pełne testy Admina: 493/493.
- Typecheck core i Admina, lint Admina, build core, produkcyjny build Admina
  oraz Prettier zakończyły się kodem 0. Pierwsza próba builda Admina w
  sandboxie została zablokowana przez `spawn EPERM`; powtórzenie poza tym
  ograniczeniem przeszło w całości.
- Rzeczywisty raport: 225/225, `automatic=113`, `registered=113`, `manual=112`,
  `failures=0`. W wynikach jest 113 cropów nieprzekraczających limitu i 112
  pełnych klatek z `crop_too_tall`; minimalna wysokość odzyskanego JPEG-a to
  542 px.
- Checksum listy kandydatów:
  `981ce0ba63597192ad0d23b5ecb99310d09ffbe9cfde40d65184d53d56dcc210`.
  Checksum 44 plików stanu wejściowego przed i po:
  `6efcd4edbcc4d6f3d8b6e30fd5f42c98a5855becc916f1f3a0eead72d711a616`.

### Not completed

- Nie zastąpiono JPEG-ów, shardów ani review w oryginalnym katalogu `cut`.
  Pozostałe 112 pełnych klatek wymaga świadomej korekty lub akceptacji po
  obejrzeniu osobnego preview.

### Documentation updates

- Zaktualizowano wymagania, architekturę, `CURRENT_STATE.md` oraz decyzję
  D-393 w `DECISION_LOG.md`.

### Recommended next task

- Obejrzeć 112 wpisów oznaczonych `crop_too_tall` w wygenerowanym HTML i w
  osobnym zleceniu zdecydować, czy 113 odzyskanych cropów ma zastąpić stare
  wyniki w kontrolowanym, checksummowanym imporcie.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0560 — Walidacja proporcji i odzyskanie zbyt wysokich cropów | gpt-6-astra | high | Zmiana łączy trwałą klasyfikację jakości z bezpiecznym, wznawialnym przeliczeniem 225 plików użytkownika. | Tak — gpt-6-astra/high tylko przed zapisem do oryginalnego katalogu `cut`; osobne preview nie wymaga dodatkowego review. |
