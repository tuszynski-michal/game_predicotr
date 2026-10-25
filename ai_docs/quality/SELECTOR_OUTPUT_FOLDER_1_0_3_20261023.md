# Selektor Windows 1.0.3 — nazwa wyniku, TASK-1089

Nowa partia tworzy sąsiedni folder `<gra> <aktualizacja> <pierwsza>-<ostatnia>`, np. `777 a2 1-500`. Brak ostatniej planszy daje 500000. Podgląd formularza i native używają wspólnego buildera. JPEG-i i manifest operator-local pozostają zgodne z wcześniejszym wydaniem. Stare projekty i późniejsza edycja numeracji zachowują zapisany outputRoot.

## Kontrole

- 21/21 testów output-folder i start-resume: przykład operatora, domyślny koniec, znaki ścieżki Windows, limit 255, błędny zakres, wznowienie nowego folderu w nowym procesie bez historii, wybór przez folder projektu i wynik, zachowanie JPEG i ścieżki po zmianie numeracji, starszy projekt, kolizja bez nadpisania.
- Lint i typecheck: PASS.
- Wydanie 1.0.3: build, SHA-256, rozpakowanie ZIP i zawartość app.asar PASS.
- Smoke games: PASS. Sprawdza dokładny podgląd i folder `777 a2 1-500`, zapis `seq_1-9.jpg`, katalog gier, walidację aktualizacji, historię i wznowienie po restarcie.
- Smoke workflow: PASS. Kompaktowy wspólny styl, granica 500000, zmiana kierunku, pełny ekran, następny folder i wznowienie.
- docs:check po zamknięciu i code-map:check: PASS.

## Artefakty

Końcowy ZIP: `artifacts/selector-releases/1.0.3/Selektor zdjec-win32-x64-1.0.3.zip` (149415606 B), obok `.sha256` i `.release.json`.

SHA-256: `ae7e099b5e6d2a29806accf9e805e0ad6a94ab9e532d3716dd274724fcb50aca`.

Źródło: v1.7.469 / `54c33f1ae3fbbf1c44aa1632f96fa8065e7f6db1`; `applicationSourceDirty=false`. Globalne dirty=true wynika z pozostawionych wcześniejszych zmian operatora poza aplikacją. Kopia w artifacts ma identyczny SHA-256. Końcowy ZIP ponownie przeszedł smoke games z restartami i sprawdzeniem dokładnego folderu.

Dowody UI: `games-update-form.png`, `games-update-history.png`, `selection.png`.

## Ograniczenia

Nazwa opisuje początkową konfigurację formularza, niezależnie od kierunku. Nie przenoszono folderów operatora ani nie zmieniano nazw istniejących projektów. Nie wykonano fizycznego restartu Windows lub testu na drugim komputerze; trwałość sprawdzono w nowych procesach. API i Admin nie były uruchamiane. Audyt nie był wymagany przez zaakceptowany zakres. Bez merge/push do main.

## Kontrole integracji z main — 2026-10-25

Operator zatwierdził scalenie całej gałęzi, push do origin, usunięcie gałęzi oraz udostępnienie gotowej paczki 1.0.3. Baza integracji: main `2857968d2513ee2431674442e0c5a67e4f12c46d`; zakres: TASK-1088, TASK-1089 i TASK-1090. Konflikty dotyczyły wyłącznie dokumentacji procesu; zachowano pełne sekcje obu torów, okno 10 tasków oraz indeks 30 decyzji. Historyczne wersje v1.7.467–472 mają różne hashe na obu gałęziach; nie przepisano historii.

- Testy zmienionych części: 32/32 selektora oraz 2/2 interakcji udostępniania PASS.
- Pełny zestaw selektora zapisał końcowy wynik 276/276, 0 błędów i 0 pominięć (170 s). Zewnętrzny runner przekroczył 120 s (kod 124) i pozostawił proces potomny, który zakończył zestaw. Kontrola procesu potwierdziła jego zakończenie; nie uruchamiano drugiego zestawu. Nie traktujemy kodu runnera jako PASS.
- Lint i typecheck selektora oraz zmienionych plików / typecheck Admina PASS; build selektora PASS. Docs i mapa kodu po scaleniu PASS.
- Gotowy oryginalny ZIP 1.0.3: rozmiar, SHA-256, rozpakowanie, app.asar i zawartość PASS. Testy paczki games oraz workflow PASS, w tym nowe procesy i wznowienie.
- Źródło ZIP pozostaje `54c33f1ae3fbbf1c44aa1632f96fa8065e7f6db1`; paczka nie została podmieniona ani ponownie wydana.
- Dowody kontroli: `artifacts/selector-integration-20261025/`. Oryginalne dwa usunięcia artefaktów operatora i pozostałe worktree pozostają poza zakresem commita.
- Brak migracji i restartów usług w tym zakresie. Fizyczny restart Windows i drugi komputer pozostają nieweryfikowane.
