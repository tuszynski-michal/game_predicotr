# Selektor Windows 1.0.3 — nazwa wyniku, TASK-1089

Nowa partia tworzy sąsiedni folder `<gra> <aktualizacja> <pierwsza>-<ostatnia>`, np. `777 a2 1-500`. Brak ostatniej planszy daje 500000. Podgląd formularza i native używają wspólnego buildera. JPEG-i i manifest operator-local pozostają zgodne z wcześniejszym wydaniem. Stare projekty i późniejsza edycja numeracji zachowują zapisany outputRoot.

## Kontrole

- 21/21 testów output-folder i start-resume: przykład operatora, domyślny koniec, znaki ścieżki Windows, limit 255, błędny zakres, wznowienie nowego folderu w nowym procesie bez historii, wybór przez folder projektu i wynik, zachowanie JPEG i ścieżki po zmianie numeracji, starszy projekt, kolizja bez nadpisania.
- Lint i typecheck: PASS.
- Wydanie 1.0.3: build, SHA-256, rozpakowanie ZIP i zawartość app.asar PASS.
- Smoke games: PASS. Sprawdza dokładny podgląd i folder `777 a2 1-500`, zapis `seq_1-9.jpg`, katalog gier, walidację aktualizacji, historię i wznowienie po restarcie.
- Smoke workflow: PASS. Kompaktowy wspólny styl, granica 500000, zmiana kierunku, pełny ekran, następny folder i wznowienie.
- docs:check i code-map:check przed zamknięciem: PASS.

## Artefakty

Końcowy ZIP z pochodzeniem z commita zostanie skopiowany do `artifacts/selector-releases/1.0.3/` wraz z `.sha256` i `.release.json`. Dowody UI: `games-update-form.png`, `games-update-history.png`, `selection.png`.

## Ograniczenia

Nazwa opisuje początkową konfigurację formularza, niezależnie od kierunku. Nie przenoszono folderów operatora ani nie zmieniano nazw istniejących projektów. Nie wykonano fizycznego restartu Windows lub testu na drugim komputerze; trwałość sprawdzono w nowych procesach. API i Admin nie były uruchamiane. Audyt nie był wymagany przez zaakceptowany zakres. Bez merge/push do main.
