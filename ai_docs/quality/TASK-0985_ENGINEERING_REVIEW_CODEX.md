---
title: TASK-0985 — wewnętrzny przegląd warstwy zapisu
status: pass
last_updated: 2026-10-12
---

# TASK-0985 — wewnętrzny przegląd inżynierski Codex

Model: `gpt-6-astra`, reasoning `high`, niezależny agent w świeżym kontekście.
Baza: v1.7.334 / `c52518a8ece7c79f88b31224d4d90a84f0779b4c` i zmiany
TASK-0985 przed commitem. Zakres: store/storage/codec/types, SecureFiles,
projekcja kontrolera oraz testy trwałości. Brief zawierał task, fragment
zaakceptowanego planu i diff. Bez pełnych dokumentów procesu.

To wewnętrzny review inżynierski tej samej rodziny modeli. Nie zastępuje
audytu krzyżowego Claude, który operator wykona na końcu zgodnie z D-545.
Autor przeglądu nie uruchamiał testów, buildów ani pomiarów i nie zmieniał
plików. Raport zapisał lead na podstawie zwróconego wyniku.

## Runda1 — REVISE

P0: brak. P1: dwie uwagi. P2: brak.

### P1-1 — idempotencja po relink projektu legacy

`apps/selector-desktop/src/project/project-store.ts:1271` (linie przed poprawką).
Zapis receipt do after.receipts został usunięty również dla storage=null.
Projekt schema1 otwarty z brakującym źródłem pozostaje przed migracją.
Execute(relink) bez pending journal naprawia bindings, ale zapisuje legacy
stan bez receipt i nie uruchamia upgrade. Kolejne operacje również nie
zachowują nowych receiptów; retry może ponownie wykonać potwierdzony skip/undo.

Wymagana poprawka: zachować receipt w gałęzi legacy i zapewnić migrację po
udanym recovery/relink. Regresja: schema1 → przeniesione źródło → frozen open
→ relink → skip → identyczny retry przed i po reopen. Rewizja i liczba decyzji
nie rosną przy retry; zmieniony fingerprint daje konflikt.

### P1-2 — ponowienie upgrade w tym samym procesie

`apps/selector-desktop/src/project/project-store.ts:918` (linie przed poprawką).
UpgradeIntent ustawiany jest przed udanym replace descriptoru. Po ENOSPC
następne resume pomija jego zapis, ponieważ intent istnieje w pamięci.
Awaria procesu po pierwszym sidecarze pozostawia legacy heads i sidecar bez
descriptoru. Nowy open blokuje FOREIGN_CONTENT i nie wznawia migracji.

Wymagana poprawka: przed publikacją sidecarów zawsze zapewnić zgodny trwały
descriptor. Stan pamięci nie zastępuje dowodu zapisu. Regresja: legacy frozen
open → przywrócenie źródła → resume z ENOSPC przed rename descriptoru →
ponowne resume z exit po pierwszym sidecarze → fresh open odzyskuje dokładny
stan.

## Pozostały zakres

Przeczytany kod i testy pokrywają head2, mirrory, ścisły suffix, zatrzymanie
przy dwóch uszkodzonych kopiach, niezmienny record przy pending relink,
zachowanie starych ID, izolację snapshotów i brak pełnego zapisu
inventory/receiptów na zwykły krok. P1-1/P1-2 blokują potwierdzenie pełnego
kryterium retry/migracji i commit zadania do czasu poprawki.

## Ograniczony przegląd poprawek P1 — PASS

Po jednej rundzie poprawek ten sam niezależny reviewer sprawdził wyłącznie
zmienione zachowanie P1-1/P1-2. Werdykt: PASS, obie wcześniejsze uwagi
zamknięte, otwarte P1: brak. Nie wykonano drugiego pełnego audytu.

Legacy relink zachowuje receipt i kończy migrację przed potwierdzeniem.
Retry po ENOSPC również kończy upgrade, zachowuje rewizję i usuwa blokadę
zapisu. Upgrade odczytuje i sprawdza dokładny trwały descriptor przed
publikacją sidecarów. Intent w pamięci nie zastępuje dowodu trwałości.

Przeczytane regresje obejmują oba przypadki, nowy proces, kolejny zapis po
retry oraz przeniesienie katalogów podczas pending upgrade. Wykonawca
zgłosił 4/4 PASS dla tej grupy. Wyniki pełnej kontroli lead zapisuje osobno
w Outcome zadania; reviewer nie uruchamiał testów.

Przegląd statyczny, bez zmian w plikach. Ten wewnętrzny przegląd Codex nie
zastępuje końcowego audytu Claude przez operatora.
