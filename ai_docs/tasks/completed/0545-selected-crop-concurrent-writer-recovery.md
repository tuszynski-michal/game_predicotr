---
title: Ochrona przycinania przed równoległym writerem
status: done
last_updated: 2026-09-15
---

# TASK-0545 — ochrona przycinania przed równoległym writerem

## Status

`done`

## Goal

Jedna sesja `cut` ma najwyżej jeden aktywny browserowy writer, a zgodny JPEG
pozostawiony po utracie zapisu journalu jest odzyskiwany bez nadpisania danych.

## Context

Po przeładowaniu kilku kart cztery katalogi rozpoczęły automatyczne wznowienie
w tej samej chwili. `200575 - 222912 cut` zapisał
`seq_215353-215361.jpg`, lecz konkurencyjna karta utraciła pending journal i
zgłosiła `SELECTED_IMAGE_CROP_OUTPUT_FOREIGN`. Plik odpowiada nazwie brakującego
wpisu manifestu, ale nie ma jeszcze checksummy wyniku. Dwa stare przebiegi v12
nadal wykonywały kod sprzed TASK-0544, a nowy klient po pierwszej niezgodności
przechodził na wolniejszy główny wątek dla całej karty.

## Dependencies / entry conditions

- TASK-0544 wersjonuje odpowiedzi workera.
- Źródła, istniejące JPEG-i, shardy i decyzje operatora pozostają bez zmian.
- Dwa różne katalogi muszą nadal móc być przetwarzane równocześnie.

## Recommended execution

`gpt-6-astra` z poziomem `high`. Zmiana dotyczy trwałego journalu i
koordynacji wielu kart. Dodatkowy review jest potrzebny tylko przy rezygnacji z
dokładnego porównania SHA-256 albo przy zmianie formatu istniejących manifestów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Scope

- Utrzymywać wyłączną, browserową blokadę pliku stanu przez cały batch
  przygotowania lub przeliczenia jednego katalogu.
- Zwracać stabilny komunikat drugiej karcie bez pozostawiania jej w stanie
  ładowania.
- Dopuszczać do recovery tylko JPEG o nazwie należącej do inwentarza i bez
  wyniku, a następnie adoptować go wyłącznie, gdy SHA-256 dokładnie odpowiada
  świeżo wyrenderowanej propozycji.
- Po pojedynczej niezgodności starego workera utworzyć świeżą instancję i
  ponowić raz; dopiero druga niezgodność uruchamia fallback głównego wątku.
- Zachować cały zarejestrowany czworokąt plansz, gdy v12 przecina crop
  rejestracji z ciaśniejszym cropem strukturalnym.

## Out of scope

- Usuwanie, przenoszenie albo nadpisywanie istniejących JPEG-ów użytkownika.
- Równoległe zapisy do tego samego katalogu.
- Zmiana detektora, progów, fingerprintów lub formatu manifestu.

## Acceptance criteria

- [x] Drugi writer tego samego katalogu kończy się
      `SELECTED_IMAGE_CROP_PREPARATION_ALREADY_RUNNING` i zwalnia stan UI.
- [x] Różne katalogi mogą nadal pracować równolegle.
- [x] Osierocony JPEG o zgodnej nazwie i dokładnej checksumie jest finalizowany
      bez ponownego zapisu pliku.
- [x] Osierocony JPEG o innej checksumie pozostaje fail-closed jako
      `SELECTED_IMAGE_CROP_OUTPUT_CHANGED`.
- [x] Odpowiedź starego workera powoduje jedno ponowienie na świeżej instancji;
      zgodna odpowiedź zachowuje pracę poza głównym wątkiem.
- [x] Przecięcie cropów v12 nie obcina żadnego punktu zarejestrowanej planszy.
- [x] Nowy fingerprint odrzuca stary worker, a historyczny fingerprint pozostaje
      zgodny przy odczycie rozpoczętej sesji.

## Technical notes

Blokada korzysta z osobnego pliku w `.manual-image-crop-state` i utrzymuje
otwarty `FileSystemWritableFileStream` w trybie `exclusive` przez cały batch.
`abort()` w `finally` zwalnia uchwyt także po anulowaniu albo błędzie; po
awarii procesu przeglądarka zwalnia natywną blokadę bez timeoutu i bez
destrukcyjnego cleanupu. Blokada jest per katalog, ponieważ każdy output ma
własny plik.

Top-level audyt katalogu nadal odrzuca każdą nazwę spoza manifestu. Nazwa
brakującego wpisu manifestu może przejść do przygotowania, ale `save` porównuje
istniejący SHA-256 z nowym renderem. Tylko równość pozwala utworzyć pending i
sfinalizować shard/journal bez `writeBlob`; rozbieżność nie modyfikuje pliku.

## Expected files

- Nowy: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-preparation-lease.ts`.
- Nowy: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-output-recovery.ts`.
- Istniejący: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-storage.ts`.
- Istniejący: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-worker-client.ts`.
- Istniejący: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-workspace.tsx`.
- Istniejący: `packages/manual-image-selection-core/src/crop-preparation.ts`.
- Istniejący: `packages/manual-image-selection-core/src/auto-crop-v12-registration.ts`.
- Istniejący: `packages/manual-image-selection-core/src/crop.ts`.
- Testy w `apps/admin/test/` dla lease, recovery, workera i kontraktu storage.
- Testy core dla przecięcia cropów i wersjonowania fingerprintu.
- Dokumenty wymagań, architektury i `CURRENT_STATE.md`.

## Test cases

- Dwa acquire na jednym fałszywym pliku → drugi stabilny konflikt; po release
  kolejny acquire działa.
- Brak outputu → write; zgodny orphan → reuse; różny orphan → reject.
- Stary worker, potem bieżący worker → dwa utworzenia, jeden wynik workera.
- Dwa kolejne stare workery → kontrolowany fallback i brak dalszych instancji.
- Kontrakt storage potwierdza lease w `finally`, brak zapisu zgodnego orphanu i
  zachowanie ochrony obcych nazw.

## Verification

```powershell
node --experimental-strip-types --test --test-isolation=none apps/admin/test/selected-image-crop-preparation-lease.test.mjs apps/admin/test/selected-image-crop-output-recovery.test.mjs apps/admin/test/selected-image-crop-worker-client.test.mjs apps/admin/test/selected-image-crop-storage-contract.test.mjs apps/admin/test/selected-image-crop-workspace-contract.test.mjs
npm --workspace @game-predictor/manual-image-selection-core test
npm --workspace @game-predictor/manual-image-selection-core run typecheck
npm --workspace @game-predictor/admin run typecheck
npm --workspace @game-predictor/admin run lint
npm --workspace @game-predictor/admin run build
```

Kryterium zaliczenia: testy, typecheck, lint i build są zielone, a diagnoza ani
naprawa nie modyfikują rzeczywistego `seq_215353-215361.jpg`.

## Risks / open questions

- Otwarta karta z kodem sprzed TASK-0545 nie zna blokady; pełne odświeżenie
  takich kart jest jednorazowo wymagane, aby zakończyć stare pętle.

## Outcome

### Changed

- Dodano blokadę `exclusive` per katalog dla odczytu/recovery, batchy,
  przeliczeń i pojedynczych zapisów cropów.
- Zgodny checksumowo orphan jest finalizowany bez ponownego zapisu, a plik o
  innych bajtach pozostaje nietknięty i fail-closed.
- Stary worker jest ponawiany raz na świeżej instancji przed wyborem fallbacku.
- UI kończy loading drugiej karty i wyjaśnia, że katalog pracuje w innym oknie.
- Przecięcie cropa strukturalnego z rejestracją obejmuje cały zarejestrowany
  czworokąt; przypadek `bottomY 1097` i punkt planszy `y 1102` ma regresję.
- Konsensus `registered-band-bounded-intersection-v2` jest fingerprintowany;
  wcześniejsze wyniki v12 pozostają zgodne tylko jako stan trwały.

### Verification results

- 40/40 skoncentrowanych testów przeszło.
- Pełny zestaw core: 97/97.
- Pełny zestaw Admina: 475/475.
- Typecheck core i Admina, lint oraz produkcyjny build Admina przeszły.
- Podczas pierwszej diagnozy rzeczywisty `seq_215353-215361.jpg` istniał;
  odczytano jego SHA-256 bez zmiany pliku i nie wykonano recovery na danych
  użytkownika. Przed końcowym commitem katalog miał już świeżą sesję v12
  `25/2482`, bez błędów i bez tego outputu. Codex nie usuwał ani nie zmieniał
  plików w katalogu; dokładne recovery tego egzemplarza pozostaje niezweryfikowane
  na danych użytkownika i jest pokryte testem regresyjnym.

### Not completed

- Nie zatrzymano zdalnie pętli działających w kartach ze starym JavaScriptem;
  wymagają jednorazowego odświeżenia przez operatora.

### Documentation updates

- Zaktualizowano wymagania, architekturę i `CURRENT_STATE.md`.

### Recommended next task

- Brak. Świeża sesja v12 już przetwarza katalog; po dojściu do pozycji
  `seq_215353-215361.jpg` należy potwierdzić jego zwykłe wygenerowanie.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0545 | gpt-6-astra | high | Trwały journal oraz koordynacja kilku kart wymagają ścisłej kolejności walidacji, blokady i niedestrukcyjnego recovery. | Nie; `gpt-6-astra` z `xhigh` tylko przy zmianie formatu manifestu lub odejściu od SHA-256. |
