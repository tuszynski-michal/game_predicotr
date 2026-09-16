---
title: Recovery starego workera przycinania zdjęć
status: done
last_updated: 2026-09-15
---

# TASK-0544 — recovery starego workera przycinania zdjęć

## Status

`done`

## Goal

Sekcja `Przytnij wybrane zdjęcia` rozpoznaje wynik workera z nieaktualnego
builda i bez zapisywania fałszywego błędu ponawia przygotowanie aktualnym kodem
strony.

## Context

Sesje `387693 - 379711 cut` i `348256 - 371007 cut` zapisały odpowiednio 787
i 431 błędów `SELECTED_IMAGE_CROP_PROPOSAL_INVALID`, podczas gdy sesje v10 w
świeżym profilu działały. Odtworzenie pierwszego błędnego JPEG-a z obu sesji na
aktualnym v12 dało poprawną propozycję przechodzącą walidację. Fingerprint v12
został rozszerzony 14.09.2026, a klient workera nie miał wersji protokołu ani
kontroli, czy odpowiedź pochodzi z tego samego builda co walidator strony.

## Dependencies / entry conditions

- Źródła i istniejące cropy pozostają nienaruszone.
- Brakujące wyniki z trwałym failure są już objęte akcją `Ponów błędne` i
  zwykłym wznowieniem sesji.
- Główny wątek ma funkcjonalny fallback tego samego algorytmu.

## Recommended execution

`gpt-6-astra` z poziomem `high`. Zmiana dotyczy granicy procesów, zgodności
wersji oraz trwałych failure, więc wymaga testu starej odpowiedzi i zachowania
fallbacku. Dodatkowy review jest wymagany tylko przy zmianie algorytmu cięcia
lub formatu danych na dysku.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Scope

- Wersjonować odpowiedź browserowego workera przycinania.
- Sprawdzać protokół, żądaną politykę i dokładny fingerprint przed użyciem
  wyniku.
- Przy niezgodności zakończyć starego workera, wyłączyć go dla bieżącego builda
  karty i zwrócić kontrolowany fallback do aktualnego kodu strony.
- Zachować dotychczasowy retry brakujących/błędnych plików.
- Dodać regresje starego fingerprintu, braku wersji protokołu i zgodnego v12.

## Out of scope

- Zmiana detektora v12, progów, fingerprintu lub współrzędnych cropa.
- Automatyczne usuwanie albo przepisywanie istniejących JPEG-ów i decyzji.
- Modyfikacja IndexedDB lub formatu shardów/session journalu.

## Acceptance criteria

- [x] Odpowiedź starego workera bez bieżącej wersji protokołu jest odrzucana
      przed zapisem.
- [x] Odpowiedź v12 ze starym fingerprintem jest odrzucana przed zapisem.
- [x] Zgodna odpowiedź workera nadal używa renderu poza głównym wątkiem.
- [x] Niezgodność przełącza pozostałe pliki bieżącej karty na istniejący
      fallback i nie tworzy `SELECTED_IMAGE_CROP_PROPOSAL_INVALID`.
- [x] Ponowienie istniejących failure może użyć poprawionego przepływu bez
      resetowania sesji lub usuwania katalogu.

## Technical notes

Worker zwraca jawne `workerProtocolVersion`. Klient porównuje je wraz z
`policyVersion` i fingerprintem v11/v12. Niezgodność nie jest błędem obrazu:
worker jest kończony, a funkcja zwraca `null`, co w istniejącym storage uruchamia
`proposeSelectedImageCrop` z kodu aktualnie załadowanej strony. Flaga fallbacku
obowiązuje do przeładowania modułu, aby każdy kolejny plik nie uruchamiał tej
samej starej odpowiedzi.

## Expected files

- Nowy: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-worker-contract.ts`.
- Istniejący: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-worker.ts`.
- Istniejący: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-worker-client.ts`.
- Nowy: `apps/admin/test/selected-image-crop-worker-client.test.mjs`.
- Istniejący: `apps/admin/test/selected-image-crop-storage-contract.test.mjs`.
- Istniejący: `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`.
- Istniejący: `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`.
- Istniejący: `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Brak wersji protokołu + v12 → wynik niezgodny.
- Bieżący protokół + stary fingerprint v12 → wynik niezgodny.
- Bieżący protokół + poprawna polityka i fingerprint v12 → wynik zgodny.
- Bieżący protokół + polityka inna niż żądana → wynik niezgodny.
- Symulowany stary worker → klient zwraca `null`, kończy workera i kolejne
  wywołanie nie tworzy następnego workera w tej karcie.

## Verification

```powershell
node --experimental-strip-types --test --test-isolation=none apps/admin/test/selected-image-crop-worker-client.test.mjs apps/admin/test/selected-image-crop-storage-contract.test.mjs
npm --workspace @game-predictor/admin run typecheck
npm --workspace @game-predictor/admin run lint
```

Kryterium zaliczenia: testy regresji, typecheck i lint są zielone, a aktualny
v12 nadal odtwarza jako poprawne pierwsze błędne źródło z obu zgłoszonych
sesji.

## Risks / open questions

- Fallback działa w głównym wątku i może być wolniejszy do chwili przeładowania
  karty; chroni jednak trwały stan i po świeżym załadowaniu bieżący worker znów
  przejmuje obliczenia.

## Outcome

Dodano wersję protokołu do każdej odpowiedzi workera oraz kontrolę zgodności
protokołu, polityki i fingerprintu przed użyciem propozycji. Nieaktualna
instancja jest kończona, a karta przechodzi na istniejący fallback bieżącego
modułu; wynik nie trafia do trwałych failures. Regresja symuluje starego
workera, potwierdza jego jednokrotne zakończenie i brak kolejnych prób użycia w
tej samej karcie. Testy kontraktu i zachowania, typecheck oraz lint Admina są
zielone. Dane użytkownika nie zostały zmienione.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0544 | gpt-6-astra | high | Granica worker–główny wątek wymaga zgodności wersji, fail-safe fallbacku i regresji długiej sesji. | Nie; `gpt-6-astra` z `xhigh` tylko przy zmianie algorytmu lub trwałego formatu danych. |
