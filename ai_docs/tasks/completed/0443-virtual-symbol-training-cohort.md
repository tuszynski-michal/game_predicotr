---
title: Virtual-source symbol training cohort
status: done
version: 0.10.152
---

# TASK-0443 — Trening symboli z cropów `virtual_source`

## Problem

Gra `777 v0.2` ma 646 bieżących, zatwierdzonych komórek symboli v0.10, ale
podgląd jakości klasyfikuje wszystkie jako `missingAsset`. Repozytorium źródła
treningowego i builder datasetu obsługują wyłącznie fizyczne pliki cropów,
podczas gdy produkcyjny kontrakt v0.10 przechowuje checksum-bound render spec i
nie materializuje osobnego PNG komórki.

## Scope

- kwalifikować bieżące, zatwierdzone komórki `virtual_source` bez trwałego
  tworzenia duplikatów cropów,
- weryfikować ich pełną proweniencję oraz renderować deskryptor z managed
  original,
- dodać addytywną wersję manifestu kohorty z pełnym kontraktem renderu v0.10,
- odtwarzać dokładne piksele w builderze datasetu i materializować je dopiero w
  content-addressed artefakcie treningowym,
- zachować odtwarzalność historycznych kohort v1–v3 i cropów `legacy_file`,
- po wdrożeniu wykonać wyłącznie read-only kontrolę gotowości gry `777 v0.2`.

## Out of scope

- zamrożenie kohorty, uruchomienie treningu lub aktywacja modelu,
- zmiana etykiet, geometrii, symboli albo danych gry,
- backfill fizycznych plików cropów,
- zmiana publicznego API lub OpenAPI.

## Relevant docs

- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- podgląd kohorty zalicza prawidłowy, aktualny crop `virtual_source` jako próbkę,
- brak źródła, drift checksumy, rewizji lub render spec nadal wyklucza próbkę,
- zamrożony manifest wiąże wszystkie dane wymagane do deterministycznego
  odtworzenia wirtualnego cropa,
- worker odtwarza piksele, sprawdza checksumę pikselową i buduje dataset bez
  trwałego pliku cropa w źródle,
- historyczne manifesty v1–v3 oraz `legacy_file` przechodzą testy regresyjne,
- dokumentacja opisuje obsługę wirtualnych źródeł treningowych.

## Outcome

- Repozytorium źródła treningowego kwalifikuje `virtual_source` przez istniejący
  checksum-bound renderer, zachowuje cache wyłącznie dla read-only preview i
  ponownie weryfikuje piksele podczas zamrożenia.
- Manifest kohorty v4 utrwala tryb assetu, zatwierdzoną proweniencję, source
  geometry revision, checksumy źródła/geometrii/renderu, logical-cell v1/v2,
  render identity v2 oraz pełny render spec.
- Builder datasetu obsługuje v4 legacy i virtual. Wirtualny PNG powstaje dopiero
  w katalogu datasetu; walidacja assetu rozróżnia SHA-256 bajtów legacy od
  checksumy RGB `rgb-pixel-v1`.
- Historyczne manifesty v1–v3 i dotychczasowy trening/ONNX/candidate gate
  pozostają zgodne.
- Read-only podgląd gry `777 v0.2` zwrócił schema v4, 472 wybrane próbki z 5
  źródeł, pokrycie wszystkich 8 symboli, `missingAsset = 0` i `canFreeze = true`.
  Powtórny odczyt z cache trwał około 0,75 s. Nie zamrożono kohorty, nie
  uruchomiono treningu i nie zmieniono danych gry.

### Verification

- `48 passed` — kohorty API, źródło komórek, builder datasetu, klasyfikator i
  pełny job trening → ONNX → candidate gate.
- `8 passed` — istniejący kontrakt renderowania virtual-cell, w tym replay
  utrwalonego render spec.
- Ruff dla całego API, workera i skryptów przeszedł.
- Skoncentrowany mypy dla pięciu zmienionych modułów aplikacji/domeny/repozytorium
  i buildera/jobu przeszedł. Moduł klasyfikatora nadal raportuje dwa wcześniejsze
  błędy stubów PyTorch (`Class cannot subclass Any`), niezwiązane z poprawką.
- `git diff --check` przeszedł; ostrzeżenia dotyczą wyłącznie polityki CRLF na
  Windows.
