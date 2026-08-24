---
title: TASK-0290 — Benchmark i kontrolowany rollout zdalnej ręcznej selekcji
status: in_progress
last_updated: 2026-08-24
---

# TASK-0290 — Benchmark i kontrolowany rollout zdalnej ręcznej selekcji

## Status

`in_progress`

## Goal

Udostępnić audytowalny harness etapów 1–5, który zatrzymuje rollout po każdej
niespełnionej bramce oraz dokumentuje realne wyniki bez sekretów, ścieżek hosta
ani kopiowania JPEG-ów do repozytorium.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`

## Scope

- wersjonowany, content-addressed parser, walidator i agregator raportów,
- deterministyczny lokalny etap 1 z fault injection i zgodnością
  decision/host-files/output-v1/trace-v1,
- jawne checkpointy 10/500/1000/8000/15000 operacji,
- metryki UX/API/transferu/host queue, retry, konflikty i rozkład rozmiarów,
- fail-closed zależność etapów, raporty bez sekretów/absolutnych ścieżek,
- runbook pilotażu, feature flag oraz rollbacku,
- automatyczne testy kontraktu raportu i lokalnego harnessu;
  scenariusze wieloprofilowe, LAN i Quick Tunnel jako jawne kroki operatorskie.

## Out of scope

- automatyczne uruchamianie testów 8 000 lub 15 000 bez osobnej zgody właściciela,
- test publicznym Quick Tunnel podczas implementacji,
- nowy protokół chunkowanego transferu (TASK 19),
- zmiana algorytmu selekcji zdjęć albo osłabienie bramki bezpieczeństwa TASK-0289.

## Acceptance criteria

- [ ] Każdy etap ma kanoniczny, content-addressed raport i zamkniętą walidację.
- [ ] Raport blokuje przejście etapu po utracie, duplikacie, konflikcie, błędzie
  kolejki, niezgodności manifestu/JPEG/JSON lub braku wymaganej metryki.
- [ ] Etap 1 wykonuje select/deselect/undo/retry/restart/finalize na
  deterministycznym fixture bez duplikatów finalnych plików.
- [ ] Etapy 2–5 mają jednoznaczne limity, zgody i checklistę środowiska.
- [ ] Runbook opisuje feature flag, monitoring, rollback, revoke i recovery.
- [ ] Raport nigdy nie zawiera kodu dostępu, tokenu, cookie ani absolutnej ścieżki.
- [ ] Etap 4/5 nie może zostać uruchomiony ani zaliczony przypadkiem.

## Progress

### v0.7.42 — kontrakt raportu, runbook i lokalna bramka etapu 1

- Dodano `remote-manual-selection-rollout-v1`: kanoniczny, checksumowany raport
  z bramką kolejności etapów, metrykami UI/API/transferu/kolejki, czasem,
  throughputem, CPU/pamięcią i fail-closed kontrolą integralności.
- Deterministyczny etap 1 wykonuje select/deselect/undo, exact retry,
  stale-generation, finalizację i recovery bez publicznego endpointu.
- Przeszły: testy kontraktu raportu oraz PowerShellowy etap 1 i jego
  weryfikacja kanoniczności. Nie wykonano etapów 2–5, LAN ani Quick Tunnel.
- Etapy 4 i 5 wymagają jednocześnie jawnej zgody właściciela w obserwacji i
  parametrów `-AllowLarge` oraz `-OwnerApproval`; skrypt nie uruchamia sesji,
  tunelu ani transferu.

## Open checkpoint before a public pilot

Architektura w sekcji 21 opisuje feature flag jako domyślnie nieaktywną do
odbioru, ale obecne `API_CONTRACT.md`, `LOCAL_OPERATION_GUIDE.md` i konfiguracja
procesów opisują/wdrażają domyślnie włączoną flagę. TASK-0290 nie zmienia tej
wcześniejszej decyzji operacyjnej. Przed etapem z Quick Tunnel właściciel musi
jednoznacznie rozstrzygnąć domyślną politykę flagi oraz potwierdzić ją w nowym
procesie API i Reviewera.

## Outcome

Do uzupełnienia po zamknięciu wszystkich etapów i checkpointu rolloutowego.
