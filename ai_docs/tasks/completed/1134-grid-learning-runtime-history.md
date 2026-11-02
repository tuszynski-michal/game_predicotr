---
title: Gotowość GPU i czytelne przebiegi uczenia
status: done
last_updated: 2026-11-02
---

# TASK-1134 — Gotowość GPU i czytelne przebiegi uczenia

## Status

`done`

## Goal

Usunąć fałszywe odrzucenie uczenia z korekt z powodu braku konfiguracji CUDA
w workerze general oraz poprawić wysokość, kolor i odstępy listy przebiegów.

## Context

Dwie istniejące próby Mumie a2: GRID_RUN_GPU_UNAVAILABLE, bez kohorty i dziecka
treningu. Odtworzony probe fabryki CLI przy nieustawionej zmiennej zwraca
python=None i GRID_TRAINING_PYTHON_UNSET. Skrypt lane ustawia interpreter CUDA
tylko dla grid-training; parent uczenia wykonuje się w general. Środowisko
repozytorium .venv-vision-lab istnieje i wcześniejszy odczyt CUDA był poprawny.

## Dependencies / entry conditions

Kontynuacja roboczej gałęzi codex/model-quality-button-styles po TASK-1133
(v1.7.523/524), bez zgody na merge/push i restart usług w tym tasku.
Numery 1124–1132 należą do równoległego planu; 1134 wolny.

## Recommended execution

gpt-6.1-sol/high; ograniczona fabryka konfiguracji i prezentacja listy.
Niezależny audyt Claude Code claude-opus-5-5/high przed commitem, bez delegowania.

## Relevant docs

- AGENTS.md, ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md, TASK_TEMPLATE.md, DEFINITION_OF_DONE.md
- ai_docs/requirements/VISION_LAB.md (correction learning)
- ai_docs/requirements/ADMIN_APP.md (uczenie z korekt)
- ai_docs/architecture/VISION_LAB.md (Durable application grid training)
- ai_docs/architecture/CODE_MAP.md i CODE_MAP_SYMBOLS.md
- scripts/manage_worker_lanes.ps1 (Resolve-GridTrainingPython)
- packages/ui/src/buttons.css (primary, --button-height)

## Scope

CLI obu konsumentów korzysta z jednej fabryki: jawne
GAME_PREDICTOR_GRID_TRAINING_PYTHON ma pierwszeństwo; przy jego braku można
odnaleźć istniejący interpreter w .venv-vision-lab właściwego checkoutu.
Nie wybierać środowiska głównego CPU i nie maskować błędnej jawnej ścieżki.
Lista przebiegów ma dedykowaną klasę, primary, 38 px wysokości na desktopie,
wyraźny gap i bez punktorów; dla wskaźnika dotykowego zachować 44 px.

## Out of scope

Trening/wznowienie operatora, model/default, migracje, restart usług, merge/push,
nowe API i instalowanie pakietów. Odczyt rzeczywistego probe CUDA jest dozwolony.

## Acceptance criteria

- [x] Brak env przy istniejącym lokalnym CUDA daje poprawny probe fabryki w nowym procesie.
- [x] Jawna ścieżka ma pierwszeństwo; błędna jawna konfiguracja nie uruchamia fallbacku.
- [x] Brak obu konfiguracji nadal bezpiecznie blokuje start, bez wybierania CPU.
- [x] Parent general i właściwy trener korzystają z tej samej polityki rozwiązywania.
- [x] Lista przebiegów jest niższa, zielona, ma odstępy i mieści się na mobile.
- [x] Regresje workera, interakcje UI, scoped lint/typecheck, docs/map i Opus PASS.
- [x] Outcome, task-close, osobny commit i record-hash.

## Technical notes

Naprawa w kodzie wyboru środowiska, bez jednorazowego ustawiania PATH/env.
Zachować interpretację historycznych jobów, guardy budżetu oraz oddzielny krok
zastosowania. Błędy istniejących prób pozostają w historii. Nie ponawiać ich
podczas weryfikacji bez odrębnego zlecenia rzeczywistego treningu.

## Expected files

services/worker/src/game_predictor_worker/cli.py, nowe ograniczone regresje
fabryki w services/worker/tests; grid-correction-learning-panel.tsx i .css;
ADMIN_APP.md i VISION_LAB.md architektura. Mapa tylko gdy wymaga regeneracji.

## Test cases / Verification

Odtworzenie unset probe przed zmianą; regresje fabryki: env/default/missing oraz
rzeczywiste podpięcie probe rodzica. Istniejące testy parenta i treningu.
Read-only CUDA probe w nowym procesie bez zmiennej i bez połączeń DB.
Interakcje UI, oględziny desktop/mobile bez wykonywania akcji. Timeout komend
<=110 s, audyt 480/570 s. Bez pełnego mypy Torch; scoped strict z jawną granicą.

## Risks / open questions

Działający worker wczytał stary kod. Poprawka będzie wymagać restartu general
po zatwierdzeniu wyniku; zgoda z wcześniejszego wdrożenia nie przechodzi.

## Outcome

Commit: v1.7.525 / `550378ab6d432ab102368fabb7d71c19d4fc3268`.

### Assumptions recorded before coding

Praca w tym samym roboczym checkoutcie; main nie jest przesuwany. Poprawa
listy trafia od razu przez istniejący HMR, backend wymaga osobnego restartu.
Domyślne repo CUDA jest istniejącym kontraktem skryptu lane, nie nowym silnikiem.

### Changed

Wspólna fabryka CLI wybiera jawną konfigurację, a przy jej braku istniejący
interpreter .venv-vision-lab z checkoutu (Windows/POSIX). Parent w general oraz
supervisor treningu używają tej samej funkcji. Jawna błędna ścieżka nadal
kończy probe błędem, bez wyboru innego interpretera lub CPU.
Lista ma własną klasę i zielone primary, bez punktorów, gap 12 px i wysokość
38 px (44 px przy pointer:coarse). Nie zmieniono wyboru/odczytu przebiegu.


### Verification results

Przed zmianą: rzeczywisty probe CLI w nowym procesie bez zmiennej wskazuje
python=None, cuda_available=false, probe_error=GRID_TRAINING_PYTHON_UNSET.
Obie próby API zakończone przed kohortą/treningiem; odczyty bez mutacji.

Test regresyjny przed poprawką: 3 failed / 3 passed dokładnie z brakującego
fallbacku oraz rzeczywistego podpięcia parenta. Pierwszy setup zatrzymał się
na zewnętrznym katalogu TMP; zachowany osobno, nie jest dowodem czerwonej
regresji. Właściwe testy używają krótkiego --basetemp wewnątrz artifacts.
Po zmianie: 34/34 worker PASS (13.39 s), w tym fabryka, parent, trener i CLI;
29/29 UI PASS (6.12 s). Ruff, scoped strict mypy CLI, ESLint i pełny frontend
tsc PASS. Mypy ma pełny config repo z wyłącznie tymczasowym skip wnętrza
Torch/Torch.*, follow-imports=silent; globalny config bez zmian.

Rzeczywisty nowy proces, bez zmiennej: domyślny interpreter D:/game_predicotr/
.venv-vision-lab/Scripts/python.exe; cuda_available=true, torch 2.12.1+cu130,
torchvision 0.27.1+cu130, RTX 4050 Laptop, probe_error=null. evaluate_admission
zwraca admitted=true i reasons=[] dla tego samego presetu co parent. Purpose
smoke jest wyłącznie obiektem decyzji w pamięci: reserved_steps=0, used_seconds=0;
nie uruchomiono smoke/trenera, nie zapisywano budżetu ani dzierżawy i nie użyto DB.
Dowody: artifacts/task1134-before-probe.json oraz task1134-after-probe.json.

Przeglądarka: obie rzeczywiste pozycje mają primary rgb(112,225,180), wysokość
38 px oraz dokładnie 12 px między granicami; bez punktorów. Przy 390 px szerokości
prawa granica 237.3 px, brak przepełnienia i błędów konsoli. Pointer pozostaje
fine w tym podglądzie; reguła coarse=44 px jest w CSS, bez fizycznego testu telefonu.
Rozmiar podglądu przywrócono. Żadnych kliknięć treningu/wznowienia.

### Cross audit and remaining limits

[Claude Code Opus 5.5/high](../../quality/TASK-1134_AUDIT_claude-opus-5-5.md): PASS,
runda 1, bez P0/P1. P2-1 świadomie przyjęte dla niestandardowych ustawień skryptu
lane: -GridTrainingPython/User-only oraz błędna zmienna mogą rozdzielić konfigurację
procesów. Nie zmieniano skryptu ani jego polityki. Domyślna rzeczywista konfiguracja
operatora jest sprawdzona, a dokument zawęża gwarancję do fabryki CLI. Pozostały
zakres wymaga osobnego ujednolicenia launchera, bez maskowania błędów.

P2-2: przyjęto ryzyko braku automatycznej asercji samych klas/reguł CSS (instrukcja
wykonawcza zabrania testów odwzorowujących implementację). Są rzeczywiste oględziny
renderowania i istniejące interakcje. W jednej rundzie poprawek dodano lokalne
min-width/max-width/overflow-wrap przycisku, aby układ nie zależał od otoczenia
workspace. Wariant pointer:coarse pozostaje sprawdzony statycznie, nie fizycznie.
Nie wymagano ponownego audytu dla samych P2. Raport audytora zachowano bez zmian.

### Not completed

Operacje na modelach, restart i integracja operatora poza zakresem.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1134 | gpt-6.1-sol | high | Ograniczona naprawa wyboru runtime i lista przebiegów | Claude Code claude-opus-5-5/high przed commitem |
