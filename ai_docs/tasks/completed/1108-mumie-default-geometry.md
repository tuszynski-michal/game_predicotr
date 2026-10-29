---
title: Wersja Mumii jako domyślna geometria nowych gier
status: done
last_updated: 2026-10-29
---

# TASK-1108 — Wersja Mumii jako domyślna geometria nowych gier

## Status

`done`

## Goal

Udostępnić istniejącą wersję geometrii Mumie a1 jako opublikowaną bazę domyślną dla nowych gier V3.

## Context

Operator poprosił o użycie działającej geometrii Mumie a1. Odczyt lokalnego API potwierdził dwie dostępne historyczne bazy, obie bez publikacji, oraz brak default (revision 0). Mumie a1 ma assignment revision 1 do wersji Mumie v1, UUID `158a740f-1f54-523f-94f3-508477dbea7a`.

## Dependencies / entry conditions

- Istniejąca wersja ma admission `historical_baseline`; publikacja korzysta z istniejącej ścieżki historycznego dopuszczenia, bez fikcyjnego nowego raportu PASS.
- Polecenie operatora z 2026-10-29 obejmuje wykorzystanie tej wersji jako bazy dla nowych gier; nie obejmuje zmiany przypisań istniejących gier.

## Recommended execution

Bieżąca sesja Codex, bez delegowania i bez dodatkowego audytu. To ograniczona operacja istniejącym API, bez implementacji ani planu wykonawczego.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` — Games i Geometria V3.
- `ai_docs/architecture/API_CONTRACT.md` — tworzenie, publikacja i default V3.
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-549--wspólna-geometria-v3-i-domyślna-wersja`.

## Scope

- Potwierdzenie wersji przypisanej Mumie a1 i dostępności jej artefaktów.
- Publikacja tej historycznej wersji i ustawienie globalnego default przez istniejące API.
- Zapis dokładnych poleceń, receiptów i wyniku odczytu w nowym procesie.

## Out of scope

Trening, nowy model lub fork, zmiany kodu i schematu, import zdjęć, tworzenie próbnej gry, zmiana przypisań istniejących gier, restart usług, merge i push.

## Acceptance criteria

- [x] Źródłem jest dokładnie wersja używana przez Mumie a1.
- [x] Wersja jest dostępna, opublikowana i eligible.
- [x] Default wskazuje tę wersję i jest eligible.
- [x] Przypisanie Mumie a1 pozostaje bez zmiany rewizji.
- [x] Niezależny odczyt z nowego procesu potwierdza zapis; dokumentacja przechodzi docs:check.

## Technical notes

Publikacja historycznej bazy nie oznacza nowego pomiaru jakości innych gier. Default jest trwałą konfiguracją w bazie i dotyczy nowych gier. Nowe gry wymagają oceny rzeczywistego cięcia. Polecenia mają osobne UUID i expectedRevision 0; przy utracie odpowiedzi należy ponowić dokładnie zapisane polecenie.

## Expected files

- Nowy: `ai_docs/quality/MUMIE_DEFAULT_GEOMETRY_20261029.json` — stan i polecenia operacyjne.
- Nowy: niniejszy task; po zakończeniu przeniesiony skillem task-close.
- Istniejące: `ai_docs/process/CURRENT_STATE.md` i bieżące archiwum stanu — zapis wyniku przez task-close.

## Test cases

GET katalogu i default z nowego procesu: wybrana wersja published/eligible, default revision 1; GET assignment Mumie a1: ta sama wersja i revision 1.

## Verification

Odczyty i zapisy HTTP mają timeout 20 s na żądanie. Dokumentacja: `npm run docs:check` z limitem 120 s. Kryterium zakończenia: spełnione kryteria akceptacji, bez testowego importu na danych operatora.

## Risks / open questions

Brak nowego testu jakości na innych grach. Historyczny model jest punktem startowym, a nie gwarancją skuteczności na dowolnej nowej grze. Pełny restart usług nie jest potrzebny i nie jest zlecony.

## Outcome

Commit: v1.7.506 / `3d1f55f2f9b51ddcd8b679238111c7025ed9e257`.

### Changed

- Istniejąca historyczna baza Mumie v1 została opublikowana przez `publishGridModelVersion`, następnie ustawiona przez `setGridModelDefault` jako globalny default revision 1. To dokładnie wersja przypisana Mumie a1, z tym samym SHA manifestu.
- Zapisano UUID poleceń, receipty z `evidenceKind=historical_admission` i odczyt kontrolny w `ai_docs/quality/MUMIE_DEFAULT_GEOMETRY_20261029.json`.
- Zmieniono wyłącznie trwałą konfigurację katalogu przez istniejące API; kod i pliki modelu pozostały bez zmian.

### Verification results

- API HTTP: publikacja i set-default zakończone receiptami revision 1. Pierwsze żądanie publikacji bez nagłówka intencji zostało odrzucone `ADMIN_INTENT_REQUIRED`; ponowiono dokładne polecenie z wymaganym nagłówkiem standardowego klienta lokalnego administratora.
- Nowy proces PowerShell, 2026-10-29 20:14:33 UTC: default revision 1, `GRID_MODEL_ELIGIBLE`, model available/published/eligible, UUID i SHA zgodne ze źródłem. Assignment Mumie a1 zachował revision 1 i eventCount 1.
- `npm run docs:check`: PASS — decyzje i kotwice, okno stanu, wszystkie 11 budżetów odczytu i kopie skillów. Odczyt startowy 43 430 B, jeden aktywny task i 10 wpisów done.
- Definition of Done: kryteria operacyjne spełnione; nie zmieniono kodu, kontraktu ani schematu, więc testy kodu, lint i typecheck nie dotyczą tej operacji. Audyt nie jest wymagany przez żaden plan.

### Not completed

- Nie wykonano treningu, testowego importu, nowego pomiaru jakości, restartu usług ani komputera, migracji, merge ani push. Trwałość potwierdza nowy odczyt zapisanej konfiguracji, bez restartu usługi.
- Nowe gry wymagają kontroli rzeczywistych wyników cięcia; historyczne dopuszczenie nie jest nowym PASS dla wszystkich gier.

### Documentation updates

- Task, raport operacyjny i stan projektu; zamknięcie prowadzi `task-close`.
- Wymagania i architektura pozostają zgodne: użyto istniejącej ścieżki historycznej publikacji i default.

### Recommended next task

Ponownie otworzyć formularz nowej gry: powinien pokazać „Domyślna geometria: Mumie · v1”. Po utworzeniu gry skontrolować pierwsze wyniki importu.
