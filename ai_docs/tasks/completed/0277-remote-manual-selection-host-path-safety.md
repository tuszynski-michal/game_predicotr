---
title: TASK-0277 - Host base binding i bezpieczne mapowanie Windows
status: done
owner: Codex
version: 0.7
---

# Cel

Pozwolić lokalnemu hostowi wybrać jedyną bazę zapisu i bezpiecznie utworzyć
mapowanie `collection/batch` bez przyjmowania ścieżki od zdalnego klienta.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md` (sekcja 12 i TASK 5)
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/tasks/completed/0276-remote-manual-selection-persistence.md`

## Zakres

- wspólny, stały picker `select_local_image_folder.ps1` bez komendy ani ścieżki
  sterowanej przez wywołującego;
- krótkotrwała, jednorazowa opaque capability ujawniająca tylko display name;
- centralna walidacja pojedynczych komponentów Windows i normalized key;
- final-path containment, blokada reparse/symlink/junction oraz ograniczenie
  okna TOCTOU przez uchwyty katalogów bez `FILE_SHARE_DELETE`;
- atomowe utworzenie katalogów i content-addressed ownership markera;
- idempotentne wznowienie po restarcie wyłącznie dla zgodnego markera i DB;
- lokalny endpoint Admina otwierający picker bez ujawnienia ścieżki;
- testy nazw, kolizji, restartu, współbieżności i realnego filesystemu Windows.

## Poza zakresem

- publiczna sesja, kod, token, writer lease i zdalna autoryzacja z TASK 6;
- publiczne endpointy collection/batch, upload, materializacja plików,
  output/trace JSON i UI;
- automatyczny suffix, overwrite, usuwanie obcych lub nieoznaczonych danych.

## Invarianty

- request nie zawiera docelowej ani bazowej ścieżki;
- żaden wynik nie wychodzi poza final path host-bound base;
- istniejący reparse point w łańcuchu base/collection/batch blokuje operację;
- obcy, uszkodzony albo brakujący marker istniejącego batcha blokuje wznowienie;
- nazwy są NFC, a kolizje porównywane case-insensitive bez cichego skracania;
- capability jest jednorazowa i wygasa; trwały binding znajduje się wyłącznie
  w sesji PostgreSQL;
- publiczny DTO i błędy nie ujawniają pełnej ścieżki hosta.

## Outcome

- Wydzielono współdzielony `WindowsFolderPicker`; stały skrypt nie przyjmuje
  komendy ani ścieżki, a jeden lock obejmuje import i zdalny host setup.
- Dodano pięciominutową, jednorazową capability i lokalny endpoint Admina bez
  request body i bez ścieżki w odpowiedzi. OpenAPI i klient TypeScript zostały
  wygenerowane; endpoint ma jawny feature flag rollbacku.
- Centralna polityka odrzuca traversal, absolute/UNC, separatory, reserved
  names, kontrolne znaki, trailing dot/space oraz przekroczenie rzeczywistych
  limitów komponentu/final path. Nazwy są NFC i porównywane case-insensitive.
- Adapter Win32 otwiera finalne katalogi z blokadą usunięcia, wykrywa reparse w
  całym istniejącym łańcuchu, weryfikuje containment i tworzy atomowy marker
  `remote-manual-selection-ownership-v1`.
- Zgodny marker i DB pozwalają na restart. Test PostgreSQL potwierdził również
  recovery po crash-window: marker został zapisany, transakcja wycofana, a
  kolejny proces bezpiecznie odtworzył ten sam mapping.
- Testy: 104 celowane unit/API/kontraktu/security i 8 PostgreSQL integration
  przeszły. Realne junction oraz junction podstawiony między mkdir/final-open
  zostały odrzucone. Przeszły Ruff, focused mypy, OpenAPI/client typecheck i
  kontrola składni 35 skryptów PowerShell.
- Pełny mypy repozytorium nie zwrócił wyniku przez ponad 60 sekund, został
  przerwany, a pozostały proces zakończony. Nie dodano publicznej sesji, auth,
  uploadu, materializacji, output/trace ani UI; TASK 6 nie został rozpoczęty.
