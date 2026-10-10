---
title: T04 — izolowany rdzeń treningu, odbiór 2026-09-27
status: active
last_updated: 2026-09-27
---

# T04 — dowody odbioru

## Zakres

Implementacja TASK-0669 po odebranym T03k/D-456. Wykonawca: gpt-6-sol/high;
niezależny audyt: gpt-6-astra/medium. Ten raport nie jest wynikiem treningu.
Kontrakt checkpointów, manifestu i runów jest zapisany w TASK-0669.

Neutralny rdzeń nie przepina produkcyjnego training_job.py. Adapter udostępnia
wyłącznie development/validation. Trwały RunManager ma start/list/detail/
cancel/retry, idempotencję, tożsamość procesu, fencing, atomowe artefakty,
niezwracany budżet i watchdog. Backend, proxy i wygenerowany klient stanowią
jeden pion. Rejestr modeli pozostaje pusty do implementacji T05.

## Kontrole wykonawcy

- Backend: końcowo 46/46 PASS, w tym 25 nowych testów i 21 istniejących testów API.
  Weryfikowano wznowienie checkpointu, v1, granice importów, integralność
  manifestu, brak dekodowania holdoutów, procesowy restart/cancel/crash,
  fencing, utratę odpowiedzi, budżet i równoczesne odświeżanie/zapis.
- Watchdog uruchomiony w rzeczywistym procesie testowym: checkpoint epoki 0,
  limit 3 s, exit 124, zachowany checkpoint i konserwatywne rozliczenie czasu.
  Fixture nie trenuje modelu ani nie korzysta z danych operatora.
- UI laboratorium: 35/35 PASS; klient API: 9/9 PASS.
- Ruff, mypy (28 plików), ESLint, TypeScript laboratorium i klienta,
  OpenAPI/generated check, składnia PowerShell i git diff --check: PASS.
- Ostrzeżenia istniejących zależności Starlette/AnyIO oraz Node dotyczące
  typu modułu nie zmieniły wyników. Nie poprawiano ich poza zakresem.

Logi lokalne: artifacts/vision-lab/t04-complete-tests.stdout.log,
t04-final-web.stdout.log, t04-final-ruff.stdout.log,
t04-final-mypy.stdout.log. Są artefaktami lokalnymi, nie częścią commita.

## Izolacja GPU i rzeczywiste dane

- Świeży proces .venv-vision-lab: torch2.12.1+cu130,
  torchvision0.27.1+cu130, CUDA13.0, NVIDIA GeForce RTX4050 Laptop GPU.
  Krótkie obliczenie GPU zwróciło 13.0. Pakiety DB/Paddle nieobecne.
- Świeży proces głównej .venv nadal raportuje torch2.12.1+cpu,
  torchvision0.27.1+cpu i cuda=null. Produkcyjny handler niezmieniony.
- Instalacja ma pięć odrębnych, ograniczonych kroków PowerShell. Pierwszy
  krok CUDA przekroczył 120 s po pobraniu pakietu; procesy po timeout
  sprawdzono. Ponowienie z cache zakończyło się poprawnie. Constraints
  przypinają również zainstalowane zależności przechodnie.
- Rzeczywisty manifest
  1e7cc3a70a583320a1f051ef6598c35595aeefb3b94a60631d311c1da0b25bb0
  przeszedł adapter: 90 targetów development, 30 validation, rewizja268.
  Payload anotacji pozostał identyczny; decoded_images=0, started_runs=0.

Dowody: t04-gpu.stdout.log, t04-main-environment.stdout.log,
t04-manifest-real.stdout.log, t04-cli.stdout.log,
t04-runtime-packages.txt w artifacts/vision-lab. Skrypty i instrukcja
operatorska są trwałe; restart całego systemu Windows nie był wykonywany.

## Niezależny audyt

Cykl 1 (Astra medium): jedna P1. RunManager.checkpoint nie sprawdzał
ponownie aktualności danych przed publikacją checkpointu. Niezależne repro:
po zapisaniu epoki0 validator zgłasza RUN_DATA_DRIFT, lecz epoka1 zastępuje
poprzedni poprawny wskaźnik. Wymagana walidacja przed publikacją i regresja
zachowania checkpointu0. Wykonawca otrzymał pełną listę do poprawy.

Pozostały zakres bez P0–P2. Niezależnie 24 testy backendu, 9 klienta i 35 UI
PASS; audytor odczytał dowody GPU, izolacji i rzeczywistego manifestu.
Po poprawce fresh walidacji przed publikacją i regresji: końcowy PASS Astra
medium bez P0–P2. Niezależnie trzy testy checkpointów PASS; regresja sprawdza
odrzucenie epoki1, brak nowego artefaktu i zachowanie epoki0 po nowej instancji
managera oraz zapisie terminalnego failed. Dodatkowo dziewięć wariantów
ochrony katalogów (równość/nadrzędność/podkatalog względem snapshotu,
anotacji i manifestów) odrzucono przed jakimkolwiek zapisem.
Wykonawca ponowił 46 testów backendu, Ruff, format-check i mypy zmiany: PASS.
Dowody poprawki: artifacts/vision-lab/t04-audit1-*.stdout.log.

T04 spełnia kryteria zadania i planu. Osobny commit `v1.7.29` /
`c8ae5bb711128d1eed5286ed029a7e9dbc35f40a`. Staged check/stat/list oraz
show/stat/status PASS, cudze zmiany zachowane; bez push.

## Niewykonane i granice

Nie uruchomiono rzeczywistego runu, treningu hybrydy, usług, migracji,
aktywacji modelu, push ani merge. Nie wykonywano pełnego quality/build
całego repozytorium. T05 wymaga odebranego i osobno zacommitowanego T04.
Final_test Reels i unseen Treasure nie zostały podane do modelu.
