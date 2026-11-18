# TASK-1231 — Stabilny podgląd i napis zakresu w Selektorze Windows

## Status

blocked

## Goal

Usunąć puste klatki i skoki przy zmianie JPEG-a oraz umożliwić ustawienie napisu bieżącego zakresu na zdjęciu.

## Context

Operator zgłosił czarne mignięcie po dłuższej selekcji oraz potrzebę odczytu zakresu bez patrzenia na nagłówek. Polecenie 2026-11-16 obejmuje implementację obu zmian.

## Dependencies / entry conditions

- Brak aktywnego taska tego obszaru; bieżąca wersja Selektora 1.0.5.
- Istniejące zmiany TASK-1230 i pozostałe zmiany operatora pozostają chronione.
- Utworzenie roboczego worktree odmówione przez uprawnienia `.git` (cannot lock ref). Zmiany w plikach aplikacji są dozwolone; commit i izolacja Git pozostają blokadą środowiska.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md`
- `ai_docs/delivery/SELECTOR_SMOOTH_NAVIGATION_20261103.md`
- `ai_docs/guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md`
- `ai_docs/quality/SELECTOR_1_0_6_20261116.md`

## Scope

- Rewalidacja decode obrazu z cache przed prezentacją; podmiana JPEG-a, wymiarów i przewijania w klatce renderowania, bez kotwiczenia przewijania przez przeglądarkę.
- Checkbox „Zakres na zdjęciu”, biały napis z przezroczystym tłem, przesuwanie myszą i uchwyt narożnika zmieniający wielkość liter.
- Napis pochodzi z tego samego zakresu co nagłówek, również po pominięciu, cofnięciu i zakończeniu numeracji; działa także w fullscreen.
- Ustawienia per projekt przez istniejący cache widoku i IPC, bez zmian API ani manifestów wynikowych. Wyłączenie zachowuje pozycję i rozmiar; reset przywraca ustawienia domyślne, zachowując włączenie.

## Technical notes / assumptions

- Napis jest wyłącznie nakładką podglądu; nie jest dopisywany do JPEG-ów.
- Pozycja jest względna do miejsca dostępnego na zdjęciu, z ograniczeniem do jego krawędzi; rozmiar liter 12–160 px. Domyślnie wyłączony, 32 px, 5% dostępnego miejsca od lewej i góry.
- Stare preferencje bez nakładki pozostają zgodne; uszkodzona konfiguracja nakładki nie kasuje zoomu i scrolla.
- Brak wymaganego dodatkowego audytu: lokalny UI i testy rzeczywistego Electrona; bez delegowania.

## Expected files

- `apps/selector-desktop/src/renderer/{App.tsx,image-viewer.tsx,style.css}`.
- `apps/selector-desktop/src/{contracts.ts,range-overlay-preferences.ts}` (ostatni plik nowy).
- `apps/selector-desktop/src/renderer/range-overlay.tsx` (nowy).
- `apps/selector-desktop/src/native/view-preferences.ts`.
- Testy preferencji i smoke Electrona, dokumenty wymagań/architektury/instrukcji i mapa kodu.

## Acceptance criteria

- [x] Poprzedni obraz pozostaje do gotowości i podmiany nowego; błędy i stare callbacki nie zmieniają celu wyboru (test renderera i istniejące regresje intencji).
- [x] Nawigacja zachowuje przewijanie i nie ma pustego hosta między obrazami (Chromium, 300%, opóźniony decode).
- [x] Checkbox, przesuwanie, skalowanie za narożnik, transparentne tło i biały napis działają.
- [x] Wyłączenie/włączenie, nowy proces i reset zachowują właściwe ustawienia; stare preferencje działają (nowy proces przeglądarki z fixture IPC, niezależnie rzeczywisty zapis/odczyt ViewPreferencesStore).
- [x] Zakres aktualizuje się zgodnie z numeracją, także fullscreen; pliki wynikowe pozostają oryginalne (zmiana tylko w podglądzie).
- [ ] Testy Selektora, lint, typecheck, build i docs:check przechodzą; przygotowana paczka Windows ma zweryfikowany smoke.

## Verification

Z katalogu repo: skrypty `test`, `lint`, `typecheck`, `build` workspace `@game-predictor/selector-desktop`; `npm run docs:check`. Test smoke przez Playwright/Electron wyłącznie na własnym katalogu tymczasowym. Komendy z timeoutem 120 s; znany build ZIP może wymagać dłuższego limitu po informacji operatora.

## Outcome

### Cross-task operational coordination (TASK-1230, 2026-11-16)

The live general lane was replaced by `task1231-oneshot` (worker-v10-general)
at 03:07:49 Europe/Warsaw, stopping the persistent worker and pausing the active
grid-learning parent. Do not register a global WorkerLaneHeartbeat for one-shot
helpers against the operator database. Root worker CLI now registers a lane only
with --poll; use isolated test databases or that updated one-shot CLI. Old
worktree/custom helpers must not overwrite the live lane registration. No selector
source changes belong to TASK-1230; preserve its existing work and commit scope.

### Changed

- Renderer rewaliduje bitmapę przed podmianą w requestAnimationFrame; zachowuje poprzedni obraz, wymiary i scroll. Kotwiczenie scrolla wyłączone, miejsce na scrollbar stałe.
- Dodano biały napis zakresu, checkbox, pointer capture dla przesuwania i narożnika, ograniczenia pozycji/rozmiaru oraz reset. Wspólny rangeText dla nagłówka i napisu.
- Opcjonalne preferencje zapisuje istniejący magazyn widoku; stary format działa, wadliwa nakładka przy odczycie nie zeruje zoomu i przewijania.
- Przygotowano osobny ZIP 1.0.6, bez podmiany działającego programu i projektów. Szczegóły i SHA-256 w raporcie jakości.

### Verification results

- 35/35 testów renderer-contracts, preview-cache i selection-intents PASS.
- Lint, typecheck, build PASS dla workspace Selektora.
- docs:check i code-map:check PASS; odczyt startowy 44988 B.
- Chromium: checkbox, kolor/tło, przeciąganie, narożnik, ukrycie/przywrócenie, układ fullscreen, zmiana zakresu, reset, nowy proces z fixture IPC PASS. Opóźniony ciepły decode przy 300%: zero pustych klatek DOM i skoków scrolla.
- ZIP SHA-256, zawartość siedmiu plików ASAR, metadane oraz zgodność integralności ASAR z zasobem EXE PASS.
- Pełny zestaw testów zatrzymuje NATIVE_CHECK_FAILED: odczyt Win32_Process przez CIM zwraca brak dostępu. Te same niezmienione kontrole Windows nie działają także poza testem.
- Smoke Electron nie uruchamia procesu zarówno dla nowej paczki, jak i wcześniejszej aplikacji z out; brak PASS pełnego smoke. Devel Electron nie jest zainstalowany; próba automatycznego pobrania kończy się fetch failed.

### Not completed

- Brak potwierdzenia fizycznej długiej sesji Windows, rzeczywistych pikseli podczas migania i natywnego fullscreen. Chromium i klatki DOM nie zastępują odbioru Electrona.
- Worktree i commit zablokowane: zapis `.git/refs/heads/codex/selector-overlay-smooth.lock` odmówiony. Zmiany są niezacommitowane, task nie jest zamknięty przez task-close. Bez push/merge.

### Documentation updates

- Wymagania, architektura, instrukcja, raport jakości, mapy kodu i wskaźnik CURRENT_STATE. Skrócono powtarzający opis okna bez zmiany jego reguł, aby zachować budżet obowiązkowego odczytu.

### Recommended next task

- Odbiór przygotowanej paczki w rzeczywistej sesji operatora; po odblokowaniu zapisu Git selektywne domknięcie taska i commit, bez cudzych zmian.
