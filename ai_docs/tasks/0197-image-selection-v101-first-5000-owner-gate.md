---
title: TASK-0197 v10.1 full 32079 real-image owner gate
status: done
release: "0.4"
last_updated: 2026-08-09
---

# TASK-0197 — V10.1 full-32079 real-image owner gate

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/tasks/completed/0196-image-selection-v101-bounded-full-geometry.md`

## Goal

Wykonać kontrolowany profil wszystkich 32 079 rzeczywistych zdjęć po korektach
v10.1, zmierzyć czas i stabilność oraz przygotować wynik do ręcznej oceny
jakości przez właściciela. Właściciel jawnie zastąpił etap pośredni 5000 pełnym
stagingiem po zaliczeniu powtórki TASK-0194.

## Scope

- ten sam niezmienny staging 32 079 zdjęć,
- naturalne indeksy 0–32078,
- cold analysis bez cache lekkiego skanu,
- produkcyjny rerun na istniejącym, niezmiennym stagingu bez ponownego uploadu,
- progresywny eksport każdego rozstrzygniętego reprezentanta do katalogu
  właściciela jako `seq_<od>-<do>.jpg`, bez oczekiwania na koniec joba,
- brak automatycznego przekazania do Importu layoutów,
- trzy scan workers i jeden verifier,
- kontrolowany proces z PID-em, osobnymi logami i limitem 12 godzin.

## Likely files

- `scripts/profile_image_selection_slice.py`
- `scripts/start_image_selection_profile.ps1`
- `artifacts/image-selection-v101-exact-geometry-full-32079-task0197.json`
- `ai_docs/quality/IMAGE_SELECTION_ACCEPTANCE.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

- proces kończy się w limicie i nie pozostawia osieroconego procesu,
- raport zawiera dokładnie 32 079 źródeł, grupy, zakresy, statusy, checksumy
  reprezentantów, błędy skanu, telemetry, czas i peak RSS,
- znany prefiks 0–199 pozostaje zgodny z TASK-0196,
- anomalie zakresów, konflikty oraz `manual_required` są zestawione do oględzin,
- każdy gotowy JPEG pojawia się atomowo w katalogu właściciela podczas pracy
  joba, a kolizja o innej zawartości zatrzymuje monitor zamiast nadpisywać plik,
- wynik nie uruchamia automatycznie profilu 32 000.

## Dependencies

- TASK-0194–0196 ukończone.

## Open questions

Końcowa decyzja `accepted | optimize | rejected` należy do właściciela po
obejrzeniu reprezentantów. Brak niezależnego goldena poza przypiętymi
przypadkami oznacza, że sam procent automatycznych wyników nie jest dowodem
poprawności.

## Outcome

Profil uruchomiono 2026-08-08 jako kontrolowany proces PID `12388`. Dedykowany
worker selekcji został wcześniej zatrzymany, a worker ogólny pozostał aktywny.
Proces używa limitu 5100 s, nie publikuje wyniku i nie zapisuje stanu domenowego.

Stan procesu oraz ścieżki są zapisane w
`.runtime/image-selection-profile.pid.json`. Log postępu zapisuje się do
`.runtime/image-selection-profile-20260808T214647311Z.out.log`, diagnostyka do
odpowiadającego pliku `.error.log`, a atomowy raport końcowy powstanie jako
`artifacts/image-selection-v101-exact-geometry-first-5000-task0197.json`.

Na polecenie właściciela profil zatrzymano 2026-08-08 przed ukończeniem, aby
powtórzyć TASK-0194 bez konkurencji o CPU, pamięć i model OCR. Ostatni zapisany
postęp obejmował około 660/5000 źródeł i 23 grupy. Proces PID `12388` oraz jego
proces wykonawczy zostały zakończone, raport końcowy nie powstał, a staging
32 079 zdjęć pozostał niezmieniony.

TASK-0197 pozostaje `in_progress`. Następna próba ma rozpocząć świeży profil
0–32078; częściowego pomiaru nie wolno traktować jako wyniku odbiorowego.

Po pomyślnej powtórce TASK-0194 właściciel 2026-08-09 jawnie zrezygnował z
ponownego etapu 5000 i polecił uruchomić od razu cały staging 32 079 zdjęć.

Pełny profil uruchomiono 2026-08-09 jako PID `9136` z limitem 21 600 s,
konfiguracją trzech scan workers i jednego verifiera. Stan procesu zapisano w
`.runtime/image-selection-profile.pid.json`, postęp w
`.runtime/image-selection-profile-20260809T063547071Z.out.log`, a diagnostykę w
odpowiadającym pliku `.error.log`. Raport końcowy ma powstać atomowo jako
`artifacts/image-selection-v101-exact-geometry-full-32079-task0197.json`.

Kontrola startowa potwierdziła rzeczywisty postęp powyżej 90/32 079, pierwszą
grupę `1–9` i brak błędu terminalnego. Wynik oraz decyzja właściciela pozostają
do uzupełnienia po ukończeniu procesu.

Próba kontrolna doszła do 180/32 079, lecz jej tempo wskazało około dziewięciu
godzin dla pełnego stagingu. Została zatrzymana bez raportu i bez zmiany źródeł,
ponieważ limit 21 600 s odrzuciłby wynik po ukończeniu. Finalny profil otrzymuje
limit 43 200 s; jest to limit bezpieczeństwa pomiaru, nie cel wydajnościowy.

Finalny profil wystartował 2026-08-09 jako PID `3472`. Jego log postępu to
`.runtime/image-selection-profile-20260809T064054070Z.out.log`, diagnostyka ma
ten sam prefiks i końcówkę `.error.log`. Kontrola startowa potwierdziła aktywny
proces, postęp co najmniej 40/32 079 i brak tracebacku.

Na polecenie właściciela profil read-only PID `3472` przerwano, ponieważ nie
zapisywał reprezentantów podczas pracy. Zamiast niego uruchomiono produkcyjny
rerun istniejącego stagingu bez ponownego ładowania 32 079 plików. Aktualny run
ma identyfikator `8d86fb77-531a-4999-a9c1-d02ed15d0af0`, job
`6b7289da-2312-4b08-8c42-5a6a42aeb3c9`, a monitor PID `18844`.

API bieżącego kodu działa bez auto-reloadu na porcie 8002, a dedykowany worker
selekcji używa fingerprintu
`286b652ea8f19e3afb73017b54f096c0eb5dff828f0020f0b7454e9e42b76f40`.
Stan i logi monitora zapisano w `.runtime/live-image-selection-current.pid.json`,
raport przyrostowy w
`artifacts/image-selection-v101-live-32079-task0197-current.json`, a JPEG-i w
`C:\Users\user\Documents\1 - 19809`. Kontrola przy 128/32 079 potwierdziła
trzy fizyczne pliki: `seq_1-9.jpg`, `seq_10-18.jpg` i `seq_19-27.jpg`.

Właściciel anulował run przy 29 888 / 32 079 po 30 590,702 s. Bramka została
odrzucona z powodu zbyt wolnej końcówki oraz potwierdzonego false merge grupy
2109, który utworzył `seq_18406-18414.jpg` z obrazem layoutów `18415-18423`.
Szczegóły zachowuje
`ai_docs/quality/image-selection-v101-cancelled-run-diagnostic.json`.
