---
title: TASK-0093 Bootstrap symbol label review tool
status: done
last_updated: 2026-07-28
---

# TASK-0093 — Bootstrap symbol label review tool

## Status

`done`

## Goal

Odblokować TASK-0059 przez lokalne narzędzie przeglądarkowe, które pokazuje
automatyczne cropy, pozwala przypisać lub odrzucić symbol jednym kliknięciem i
zapisuje wznawialny `reviewed-cell-labels-v1`.

## Context

Inwentarz `symbol-crop-inventory-v1` zawiera 5805 zweryfikowanych cropów, ale
nie istnieją prawdziwe etykiety symboli odpowiadające zdjęciom. TASK-0060 nie
może rozpocząć się przed pierwszym oznaczonym eksportem. Pełny trwały workflow
Admin API i PostgreSQL nadal należy do TASK-0064/TASK-0065; obecne narzędzie
jest lokalnym bootstrapem jednego właściciela.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/tasks/0059-labeled-symbol-dataset-export.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- D-058 w `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- serwer HTTP wyłącznie na `127.0.0.1`,
- odczyt gotowego inwentarza i bezpieczne serwowanie wskazanych cropów,
- konfiguracja kodu gry, recenzenta oraz listy symboli,
- deterministyczne bootstrap ID symbolu wyprowadzone z kodu gry i symbolu,
- decyzje `accepted/rejected`, cofnięcie decyzji i pomijanie,
- opcjonalne zastosowanie etykiety do identycznych bajtów cropu,
- zapis atomowy i wznowienie istniejącego pliku,
- progress, filtry i skróty klawiaturowe,
- eksport dokładnego kontraktu `reviewed-cell-labels-v1`,
- ochrona przed nieznanym sample, konfliktem symbolu, drift checksumy,
  unsafe path, obcym Origin i niepoprawnym JSON.

## Out of scope

- PostgreSQL, migracje i trwałe `review_items`,
- finalny ekran manual review M6.3,
- sugestie modelu albo automatyczne etykietowanie,
- OCR,
- podział train/validation/test,
- trening klasyfikatora,
- publiczny lub sieciowy deployment.

## Acceptance criteria

- [x] Serwer odmawia uruchomienia na adresie innym niż loopback.
- [x] Crop można odczytać wyłącznie przez znany `sampleId`, po ponownej
      kontroli bezpiecznej ścieżki i checksumy.
- [x] Konfiguracja tworzy stabilne ID, a zmiana nie usuwa używanego symbolu.
- [x] Decyzja zapisuje dokładny `reviewed-cell-labels-v1` atomowo.
- [x] Retry tej samej decyzji jest idempotentne, a wznowienie zachowuje postęp.
- [x] UI ma loading, empty, error, postęp, accepted/rejected/pending oraz
      obsługę klawiatury.
- [x] Brak etykiety nie jest automatycznie odrzucany ani zgadywany.
- [x] Testy, format, lint i typecheck przechodzą.
- [x] Narzędzie przechodzi lokalny test przeglądarkowy bez błędu aplikacji.
- [x] Dokumentacja zawiera komendę uruchomienia i ograniczenia bootstrapu.

## Expected files

- `services/worker/src/game_predictor_worker/images/symbol_review.py`
- `services/worker/tests/test_symbol_review.py`
- `scripts/review_m6_symbol_labels.py`
- `scripts/m6_symbol_review/index.html`
- `scripts/m6_symbol_review/app.js`
- `scripts/m6_symbol_review/styles.css`
- `package.json`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_symbol_review.py -q
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images scripts
$env:MYPYPATH = "services\api\src;services\worker\src"
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images scripts
npm run format:check
```

## Risks / assumptions

- Bootstrap ID jest stabilne dla pary `gameCode/symbolCode`, ale przed
  publikacją danych TASK-0060 musi je powiązać z właściwym katalogiem gry.
- Narzędzie działa dla jednego lokalnego właściciela i nie zastępuje
  audytowalnego, wielosesyjnego review z M6.3.
- Oznaczenie około 100 przykładów na symbol nadal wymaga decyzji człowieka;
  narzędzie usuwa ręczne wycinanie i edycję JSON.

## Outcome

Powstało lokalne narzędzie uruchamiane komendą:

```powershell
npm run m6:symbols:review
```

Serwer wiąże się wyłącznie z `127.0.0.1`, używa losowego tokenu zapisu,
odrzuca obcy `Origin` i nie udostępnia dowolnych ścieżek plików. Przed
wysłaniem cropu ponownie sprawdza `sampleId`, ścieżkę, checksumę, tryb RGB
oraz wymiar 90 × 90. Decyzje są zapisywane atomowo w
`artifacts/m6-symbol-review/reviewed-labels.json`.

Interfejs obsługuje konfigurację gry i symboli, postęp, filtry, skróty
klawiaturowe, accepted/rejected/clear/skip oraz opcjonalne oznaczenie wszystkich
identycznych bajtowo cropów. Istniejący plik jest walidowany i wznawiany bez
utraty postępu. Narzędzie nie zgaduje etykiet i nie zastępuje trwałego
manual-review workflow z TASK-0064/TASK-0065.

Weryfikacja objęła 22 testy kontraktów datasetu, stanu review i serwera HTTP,
Ruff, mypy oraz formatowanie. Rzeczywisty smoke w przeglądarce wczytał
5805 cropów, obraz RGB 90 × 90, zapisał jedną etykietę do poprawnego
`reviewed-cell-labels-v1` i po odświeżeniu odtworzył postęp `1/5805`.
Testowy serwer i port zostały następnie zamknięte.
