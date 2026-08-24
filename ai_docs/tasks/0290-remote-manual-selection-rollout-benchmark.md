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

### v0.7.43 — lokalna podbramka etapu 2 i bezpieczne ponowienie transferu

- Etap 2 ma zakres 100–500 operacji i osobną bramkę środowiskową. Lokalny
  harness przetwarza 100 JPEG-ów przez produkcyjny control plane, streaming,
  materializację, finalizację i rzeczywisty tymczasowy filesystem.
- Fault injection obejmuje exact retry operacji, przerwany transfer hosta,
  rekonstrukcję usługi po pięćdziesiątej decyzji oraz revoke. Wynik zachowuje
  status `blocked`, ponieważ nie wykonano jeszcze rzeczywistego UI, dwóch
  profili, LAN, restartu API ani zmiany URL tunelu.
- Harness wykrył błąd finalizacji po udanym ponowieniu przerwanego transferu.
  Udana zweryfikowana próba anuluje teraz starsze nieudane próby tego samego
  pliku i generacji, nie usuwając ich audytowego wpisu ani nie osłabiając
  rewizyjnej bariery finalizacji.
- Lokalna podbramka zakończyła 100 operacji, 100 materializacji i zgodność
  100 plików z output/trace bez utraty, duplikatu i błędu checksummy. Raport:
  `artifacts/remote-manual-selection-rollout/stage-2-local.json` (lokalny,
  ignorowany przez Git).

### v0.7.44 — poprawka pickera źródła ujawniona przez próbę UI

- Rzeczywista próba operatorska wykryła, że identyfikator przekazany do
  `showDirectoryPicker()` przekraczał limit 32 znaków Chromium i blokował wybór
  folderu przed indeksowaniem.
- Reviewer używa teraz krótkiego, stabilnego identyfikatora
  `gp-remote-source-v1`, dzięki czemu zachowuje pamięć ostatniego folderu i nie
  narusza limitu API.
- Test regresyjny sprawdza długość, stabilną wartość i dozwolony alfabet. Pełne
  testy Reviewera, lint oraz typecheck pozostają zielone; istniejące ostrzeżenie
  `no-img-element` nie dotyczy tej zmiany.

### v0.7.45 — poprawne wywołanie natywnego fetch w Chromium

- Próba po wybraniu źródła wykryła `Illegal invocation`: natywny
  `window.fetch` był przechowywany w klasie transportu i wywoływany z instancją
  transportu jako odbiorcą zamiast z globalnym obiektem przeglądarki.
- Zarówno control plane tworzenia kolekcji/partii, jak i transport wybranych
  JPEG-ów wiążą teraz wywołanie z `globalThis`.
- Osobne testy regresyjne wymuszają właściwy receiver dla obu transportów.
  Pełne 109 testów Reviewera, typecheck i lint przechodzą; wcześniejsze
  ostrzeżenie `no-img-element` pozostaje poza zakresem tej poprawki.

### v0.7.46 — parytet widoku i trwały pionowy scroll

- Zdalny workspace wykorzystuje teraz klasy nagłówka, toolbara, nawigacji,
  płótna zdjęcia i akcji lokalnej ręcznej selekcji zamiast osobnego zestawu
  natywnie wyglądających kontrolek.
- Viewport ukrywa poziomy overflow i centruje powiększone zdjęcie. Pionowy scroll
  jest zapamiętywany przed zmianą indeksu i odtwarzany przez animation frame
  dopiero po załadowaniu obrazu oraz obliczeniu nowego rozmiaru.
- Usunięto natywny suwak zoomu; przyciski `−/+`, select skoku, fullscreen i
  przyciski decyzji używają tego samego systemu co Admin. Dwa testy kontraktu UI
  pilnują parytetu klas, braku poziomego scrolla i kolejności restore.
- Pełne 111 testów Reviewera, typecheck, lint i formatowanie przechodzą;
  wcześniejsze ostrzeżenie `no-img-element` pozostaje poza zakresem.

## Open checkpoint before a public pilot

Architektura w sekcji 21 opisuje feature flag jako domyślnie nieaktywną do
odbioru, ale obecne `API_CONTRACT.md`, `LOCAL_OPERATION_GUIDE.md` i konfiguracja
procesów opisują/wdrażają domyślnie włączoną flagę. TASK-0290 nie zmienia tej
wcześniejszej decyzji operacyjnej. Przed etapem z Quick Tunnel właściciel musi
jednoznacznie rozstrzygnąć domyślną politykę flagi oraz potwierdzić ją w nowym
procesie API i Reviewera.

## Outcome

Do uzupełnienia po zamknięciu wszystkich etapów i checkpointu rolloutowego.
