# TASK-1090 — Domyślna ważność linków 24 h

## Status

`done`

## Goal

Nowy formularz zakładki „Udostępnianie” domyślnie wybiera 24 h.

## Context

Operator polecił zmienić domyślną ważność z 8 h na 24 h. To mała zmiana
formularza, bez osobnego planu i wymaganego audytu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — Udostępnianie wyszukiwania online.
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` — granica zdalnego Reviewera.
- `ai_docs/architecture/API_CONTRACT.md` — Panel wielu gier.

## Scope

- Wartość początkowa `BoardSearchSharingWorkspace`: 1440 minut.
- Aktualizacja wymagań i istniejących testów interakcji.
- Założenie zakresu: istniejący link „24/10” zachowuje termin ważności;
  polecenie dotyczy wartości domyślnej nowych formularzy.

## Out of scope

Istniejące sesje, domyślna wartość pomijanego pola API, dawny modal jednej gry,
migracje, restart usług, scalenie i push.

## Acceptance criteria

- [x] Nowy formularz i ponowne zamontowanie wybierają 24 h.
- [x] Tworzenie bez zmiany wyboru przekazuje 1440 minut.
- [x] Ręczny wybór 72 h nadal przekazuje 4320 minut.
- [x] Kontrole zmienionych plików i dokumentacji przechodzą.

## Expected files

- `apps/admin/src/features/sharing/board-search-sharing-workspace.tsx`
- `apps/admin/test-interactions/board-search-sharing-workspace.test.mjs`
- `ai_docs/requirements/ADMIN_APP.md`
- Ten task oraz okno i archiwum stanu przez `scripts/close_task.py`.

## Verification

Test interakcji wskazanego pliku, ESLint zmienionych plików, typecheck Admina,
Prettier check, generator i kontrola mapy kodu oraz `docs:check`.
Komendy skończone przez subprocess z timeoutem 120 s.

## Risks / open questions

Brak pytań blokujących. API dostaje jawną wartość formularza; jego kontrakt
nie wymaga zmiany.

## Outcome

Commit: v1.7.471 (hash dopisuje kolejny commit).

### Changed

- Formularz wielu gier wybiera 1440 minut zamiast 480. Ręczne opcje zachowane.
- Testy sprawdzają wybór początkowy i ponowne zamontowanie, żądanie domyślne
  1440 minut oraz dotychczasowy ręczny wybór 4320 minut.
- Na dodatkowe polecenie operatora utworzono sesję „24/10 -1” z 777 a1 i Mumie a1,
  ważną do 25.10.2026, 10:52 czasu lokalnego. Sekret nie jest zapisany w repo.

### Verification results

- Testy interakcji: 2/2 PASS w nowym procesie.
- ESLint zmienionych plików, tsc Admina i Prettier check: PASS.
- Generator mapy wykonany; wynik bez zmian. Kontrola mapy i docs:check: PASS.
- Odbiór przeglądarkowy: po odświeżeniu wybrane 24 h; nowa sesja ma aktywny
  status i termin 24 h. Pierwsza sesja „24/10” zachowała poprzedni termin.
- Pierwsze wywołanie ESLint z katalogu głównego nie znalazło konfiguracji;
  poprawne wywołanie z apps/admin zakończyło się sukcesem.

### Not completed

- Bez pełnego builda, ręcznego odbioru Androida, restartów usług, scalenia i pushu.
- Audyt nie był wymagany; task nie ma osobnego planu.

### Documentation updates

- ADMIN_APP.md: domyślne 24 h w zakładce „Udostępnianie”.
- Task, okno stanu i archiwum przez skill task-close.

### Recommended next task

- Odbiór zmiany i osobna zgoda na scalenie.
