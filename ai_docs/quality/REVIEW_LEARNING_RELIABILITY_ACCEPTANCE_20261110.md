---
title: Odbiór napraw weryfikacji i gotowości uczenia
status: active
last_updated: 2026-11-10
---

# Odbiór TASK-1177–1178

Cały zatwierdzony zakres implementacji jest gotowy do akceptacji i scalenia.
Oba taski mają terminalowy audyt Claude Code Opus5.5, High requested, PASS,
bez otwartych P0/P1. Raporty statyczne nie zastępują testów:
[T1](TASK-1177_VERIFICATION.md), [T2](TASK-1178_VERIFICATION.md).

| Zgłoszenie | Wynik i dowód |
|---|---|
| Wolne zatwierdzanie/blokady | Mniej SQL i agregacji; cleanup jednej gry; poświadczenie plików poza długą blokadą.45 komórek:413→376 SQL; stare zapytanie odczytowe >12s, nowe3.292s w tym samym snapshotcie. Transakcja planszy i replay zachowane. Szybkość dużej partii operatora wymaga odbioru po wdrożeniu. |
| Zamrażanie/PREVIEW_STALE | Rewizja sprawdzana pod krótką blokadą. Zajęty zapis ma czytelny kod. Rzeczywista zmiana nadal odrzuca stary manifest; nowy podgląd wymaga nowej zgody. PG: równoczesny writer, RR, NOWAIT, ręczna geometria i cold replay. |
| Disabled uczenia/korekty | Historyczny zakres oddzielony od bieżących etykiet. Nowa iteracja i jej ocena działają bez aktualności starych etykiet bieżącej gry; reuse i publikacja nadal wymagają aktualnych dowodów. |
| Cel uczenia | Opt-in rekomendacja backendu. Częściowe TRAIN zachowują punkty; detektor wymaga pełnych danych i zgodnego preflightu. Manualny wybór zaawansowany, odświeżenie go zachowuje. Wyjaśnione warunki startu. |

Świeży proces nowego serwisu, tylko odczyt na Mumie A2: canStart=true,
362 zatwierdzone plansze/195 zdjęć; TRAIN276, w tym75 nowych; VALIDATION53,
REGRESSION21,12 oznaczonych plansz w buforach.150 częściowych zdjęć TRAIN
uzasadnia punkty. Role i bufory bez zmian, brak fikcyjnych zatwierdzeń.

Weryfikacja T1:56 Python+14 PG+12 UI PASS. T2:64 Python+2 PG+56 UI+164 SDK
PASS. Ruff/Prettier, scoped ESLint/mypy, Admin/SDK typecheck/build,
OpenAPI/generator/docs/map PASS. Pełny projektowy quality/mypy nie ma
deklaracji PASS.6 zastanych błędów fixture'ów adaptera odtworzone na HEAD,
bez naprawiania ich dla zielonego wyniku.

Jawne ograniczenia: odczyt gotowości56.938s jest blisko budżetu60s; pełny
dobór może wymagać dwóch podglądów. Uzasadnienie nie drukuje osobno150
częściowych TRAIN, a180 w sekcji detektora dotyczy wszystkich ról.
T1 zachowuje ryzyko pokrycia wszystkich pisarzy fence'u oraz identyfikowania
wiszącego jobu; szczegóły P2 w raportach. Lepsza geometria nowego modelu
wymaga osobnego treningu i testu, którego tutaj nie uruchamiano.

Brak migracji schematu. Nie wykonano merge/push, restartów usług, importu,
treningu lub zastosowania modelu. Operator zatwierdza wynik i scalenie osobno.
Po wdrożeniu API i główny worker muszą wczytać nowy kod. W osobnych terminalach
po zatrzymaniu ich dotychczasowych instancji, z D:/game_predicotr:
`npm run api:dev`, `npm run worker:poll`; Admin: `npm run admin:dev`.
Agent nie wykonuje restartów bez osobnego polecenia dla tego zadania.

Katalog roboczy ma junctiony node_modules,.venv i lokalny klient Admina
apps/admin/node_modules/@game-predictor/admin-api-client. Przed cleanup
odpiąć same junctiony; nie usuwać rekurencyjnie ich celów.
