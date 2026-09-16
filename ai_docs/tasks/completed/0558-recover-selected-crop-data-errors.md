---
title: Przywrócenie błędnych wyników przycinania wybranych zdjęć
status: done
last_updated: 2026-09-15
---

# TASK-0558 — Przywrócenie błędnych wyników przycinania wybranych zdjęć

## Status

`done`

## Goal

Przeliczyć wszystkie utrwalone automatyczne ostrzeżenia i brakujące wyniki
historycznej sesji `222913 - 248184 cut` aktywnym silnikiem v12, bez zmiany
oryginalnego katalogu `cut`, oraz dodać wznowieniowy runner dla brakujących
wyników po błędzie workera.

## Context

Odczyt sesji wykazał 2808 pozycji inwentarza, 2795 wyników, 301
nierozstrzygniętych automatycznych ostrzeżeń i 13 trwałych failures bez wyniku.
Sesja wskazuje historyczną politykę `selected-image-board-band-v14-vertical-lattice-guarded`,
której implementacji nie ma w obecnym repozytorium; aktywną, wydaną polityką
jest v12. Zamiast zastępować nieznane wyniki starszym kodem, istniejący runner
preview zapisuje ponownie obliczone JPEG-i do osobnego katalogu. Brakujące
failure nie były dotąd jego wejściem.

## Dependencies / entry conditions

- Wymagane są sąsiednie katalogi `D:\777\222913 - 248184` i
  `D:\777\222913 - 248184 cut`; inwentarz źródeł i stan v2 są zgodne co do
  2808 nazw.
- Trwający preview automatycznych ostrzeżeń jest właścicielem wyłącznie katalogu
  `222913 - 248184 cut v12 board-buffer preview` i musi zakończyć się przed
  weryfikacją wyniku.
- Oryginalny `cut`, `.manual-image-crop-state`, ręczne wybory i historyczne
  JPEG-i pozostają tylko do odczytu.

## Recommended execution

`gpt-6-astra` z reasoning `high`: zadanie łączy checksummowany, wznawialny
zapis plików z rozróżnieniem automatycznych ostrzeżeń i brakujących failures.
Niezależny review `gpt-6-astra high` jest wymagany przed uruchomieniem na
danych użytkownika, jeśli zmiana miałaby zapisać w oryginalnym katalogu `cut`
albo zmienić manifest v2.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `scripts/preview_selected_crop_corrections.mjs`
- `scripts/test/selected-crop-correction-preview.test.mjs`

## Scope

- Dodać do niedestrukcyjnego preview jawny tryb odzyskania wpisów z
  `session-v2.json.failures`, które nie mają wyniku w shardach.
- Walidować nazwę względem inwentarza, brak istniejącego wyniku, checksumę
  źródła gdy historyczny wynik istnieje oraz stabilność całego wejściowego
  stanu przed finalizacją.
- Uruchomić v12 dla 301 ostrzeżeń i 13 brakujących wyników do dwóch osobnych,
  wznowieniowych katalogów preview oraz sprawdzić raporty i nienaruszalność
  wejściowego stanu.

## Out of scope

- Zastępowanie lub usuwanie JPEG-ów w `222913 - 248184 cut`.
- Migracja historycznej polityki v14, wpisanie jej jako aktywnej albo
  udawanie, że v12 jest jej implementacją.
- Zmiana ręcznych `correctionFileNames`, decyzji review, kolejki aplikacji lub
  pełne przeliczenie 2808 gotowych pozycji.

## Acceptance criteria

- [x] Preview automatycznych ostrzeżeń przetwarza dokładnie trwałą listę
      nierozstrzygniętych wyników, bez dopisywania lub usuwania wpisów review.
- [x] Preview failures przetwarza tylko wpisy `failures` bez wyniku, w
      kolejności inwentarza, i odrzuca nazwę obcą, duplikat albo wynik już
      istniejący.
- [x] Oba przebiegi są idempotentne po przerwaniu i kontrolują SHA-256 źródła
      i własnego wyjścia.
- [x] Zmiana wejściowego stanu podczas pracy kończy się błędem bez deklarowania
      sukcesu; katalog `cut` i jego stan pozostają niezmienione.
- [x] Skoncentrowane testy, kontrola składni i formatowanie zmienionego runnera
      przechodzą; TypeScript i ESLint nie mają konfiguracji obejmującej skrypty
      `scripts/*.mjs`.

## Technical notes

`runSelectedCropCorrectionPreview` zachowuje dotychczasowy kontrakt dla
automatycznych ostrzeżeń. Wspólna ścieżka preview przyjmuje drugi, jawny zestaw
kandydatów `missing_failures`: unikalne nazwy z failures, które są w inwentarzu
i nie występują w wynikach shardów. Ten zestaw nie ma historycznej checksumy
wyniku, więc sprawdza checksumę źródła względem inwentarza i zapisuje nową
proweniencję v12; dla ostrzeżeń zachowuje obecne porównanie z historycznym
wynikiem. Osobny katalog i własne metadane trybu zabezpieczają przed przypadkowym
wznowieniem inną listą.

## Expected files

- Istniejące: `scripts/preview_selected_crop_corrections.mjs` — drugi,
  kontrolowany tryb kandydatów i raport.
- Istniejące: `scripts/test/selected-crop-correction-preview.test.mjs` —
  regresja failure bez historycznego wyniku i wznowienie.
- Istniejące: wymagania, architektura, `CURRENT_STATE.md`, `DECISION_LOG.md`.

## Test cases

- Snapshot z automatycznym ostrzeżeniem → dotychczasowy preview nadal tworzy
  wyłącznie ten JPEG i daje się wznowić.
- Snapshot z failure, istniejącym źródłem i brakiem sharda → tryb failures
  tworzy osobny JPEG i raportuje ukończone odzyskanie.
- Failure obcy, powtórzony lub mający wynik w shardzie → stabilny błąd przed
  zapisem.
- Zmiana źródła albo stanu wejściowego podczas przebiegu → fail-closed bez
  podania fałszywego sukcesu.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr, timeout pojedynczego kroku <= 120 s
node --experimental-strip-types --test scripts/test/selected-crop-correction-preview.test.mjs
node_modules\.bin\prettier --check scripts/preview_selected_crop_corrections.mjs scripts/test/selected-crop-correction-preview.test.mjs
```

## Risks / open questions

- Historyczna etykieta v14 jest zapisana w danych, ale jej implementacja nie
  występuje w żadnym obecnym refie repozytorium. Preview nie interpretuje jej
  jako uprawnienia do modyfikacji oryginalnej sesji.
- Rzeczywisty obrót 314 JPEG-ów wymaga miejsca i czasu; każdy preview może być
  wznowiony wyłącznie przy niezmienionym wejściu i tej samej liście kandydatów.

## Implementation plan

1. Uogólnić niedestrukcyjny preview o jawny tryb brakujących failures oraz
   dopisać jego walidację i test wznowienia.
2. Uruchomić skoncentrowane kontrole kodu.
3. Zakończyć rozpoczęty preview 301 ostrzeżeń, uruchomić preview 13 failures i
   potwierdzić raporty oraz checksumę wejściowego stanu.

### Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0558 — Przywrócenie błędnych wyników przycinania wybranych zdjęć | gpt-6-astra | high | Trzeba zachować niezależność danych wejściowych i odporność na przerwanie podczas odzyskania 314 rzeczywistych plików. | Tak — gpt-6-astra/high, tylko gdy zakres miałby objąć oryginalny katalog `cut` lub manifest v2. |

## Outcome

### Zmieniono

- Runner preview ma jawny tryb `--missing-failures`. Bierze wyłącznie brakujące
  wyniki z trwałego `session-v2.json.failures`, w kolejności inwentarza, i
  odrzuca obcą, powtórzoną albo już gotową nazwę.
- Przed obliczeniem weryfikuje niezmienność rozmiaru i czasu źródła z
  inwentarza, a po zapisie kontroluje checksumę źródła oraz JPEG-a. Osobne
  metadane trybu uniemożliwiają wznowienie katalogu inną listą kandydatów.
- Na rzeczywistych danych utworzono dwa niedestrukcyjne preview v12:
  301 ostrzeżeń (`242` bez ręcznej korekty, `59` do ręcznego review) oraz
  13 brakujących failures (`8` bez ręcznej korekty, `5` do ręcznego review).
  Oba raportują `0` błędów.

### Weryfikacja

- `node --experimental-strip-types --test
  scripts/test/selected-crop-correction-preview.test.mjs` — 3/3.
- `node --check scripts/preview_selected_crop_corrections.mjs` — powodzenie.
- Prettier dla zmienionych skryptów i dokumentacji — powodzenie.
- Po obu rzeczywistych przebiegach checksum wejściowego
  `.manual-image-crop-state` pozostał
  `4f30856e5e7221adf71c680b7f58e9f24e00f017cc65c7d07326b2817cffa7a5`.

### Niewykonane celowo / ryzyko

- Nie zmieniono oryginalnego `222913 - 248184 cut`, jego manifestu v2,
  historycznych JPEG-ów ani ręcznych decyzji. Historyczna polityka v14 nie ma
  implementacji w obecnym repozytorium, dlatego nie została udawana przez v12.
- Przed przyjęciem wyników do dalszego importu pozostaje operatorowi obejrzenie
  64 pozycji oznaczonych do ręcznego review w obu katalogach preview.
