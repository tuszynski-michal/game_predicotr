---
title: Lokalny selektor Windows — przekazanie implementacji do audytu operatora
status: ready_for_review
last_updated: 2026-10-11
---

# Przekazanie implementacji do audytu operatora

Operator polecił wykonać pięć tasków i odłożył audyt do końca.
Ten dokument zestawia wykonanie i dowody testów; nie jest audytem ani jego PASS.

## Zakres kodu

Gałąź `codex/offline-photo-selector`, worktree
`D:\game_predicotr\worktrees\offline-photo-selector`.
Baza porównania: `bb883b5902cb0934b9732d1bc24361d01085051d` (v1.7.316).
Nowy workspace `apps/selector-desktop`, zależności root, mapy oraz dokumentacja.
Komponenty Admina/Reviewera, API, OpenAPI i baza nie były zmieniane.
Nie wykonano push, merge, migracji ani restartu usług operatora.

| Task | Commit implementacji | Stan |
|---|---|---|
|0975 fundament|v1.7.318 /00331d5776c462a3dd91e4d9113b39d0223fe6c4|done|
|0976 trwałość|v1.7.319 /be20ad8e3835cc6aed0078a7b137ea161ea2497b|done|
|0977 interfejs|v1.7.320 /0121ce8f1bd3604977e1c60872da43a4110326d7|done|
|0979 wydanie|v1.7.321 /60449f54d6b4cd08c041b86c294cc498b11efba4|kod i paczka gotowe, fizyczny odbiór blocked|
|0978 stara sesja|v1.7.322, pełny hash po commicie|done|

Przygotowanie dokumentacji: v1.7.317 /e91b365cd02bf50ff914b1c4cda0b732432f8f3a.
Każdy task ma osobny commit. Pełne wyniki i ograniczenia są w jego Outcome oraz
CURRENT_STATE. Finalna paczka po0978 zostanie wskazana w rejestrze odbioru.
Historyczny ZIP0979 zachowano w out/releases/task-0979; nie mylić obu buildów.

## Punkty do sprawdzenia w końcowym audycie

- Granice renderer/native: nadawca IPC, argumenty, opaque imageId/token,
  protokoły, CSP, sandbox, blokada sieci/nawigacji/okien i reparse pointów.
- Trwałe zatwierdzenie, dziennik/backup, retry po utracie odpowiedzi, zamrożenie
  po błędzie, lock i output lease bez przejęcia wyłącznie na podstawie heartbeat.
- Własność JPEG-ów przy undo/restart, checksumy, rozbieżny manifest, brak folderu
  oraz relink bez resetu. Projekt jest źródłem prawdy, manifest projekcją.
- Semantyka Reviewera: Enter/F+1, Tab bez zmiany zdjęcia, skok i kierunek,
  końcowy zakres, brak podwójnego submitu oraz licznik po zakończeniu zapisu.
- Stara sesja: silne dowody źródła/outputu, nowy projekt i nowy wynik,
  preview/anulowanie, wieloplikowy recovery i nietknięty oryginał. Jawne odmowy
  dla brakujących dowodów, sprzecznego v1, duplikatów oraz metadata/MIME mismatch.
- Paczka: osadzone build-info, SHA ZIP/app.asar, prawdziwe provenance/dirty,
  brak źródeł/monorepo w runtime, odtworzenie projektu z kopii i izolacja fixture.

## Granice dowodów

[Rejestr odbioru](OFFLINE_PHOTO_SELECTOR_ACCEPTANCE.md) oddziela testy agentowe
od dowodów operatora. Rzeczywisty drugi komputer, faktyczny kanał dystrybucji,
Windows bez narzędzi deweloperskich, reboot, ochrona Windows i aktualizacja do
innej wersji pozostają pending. Symulacja relokacji tej samej wersji nie jest
odbiorem aktualizacji. Niepodpisany pilot nie ma gwarancji uruchomienia na
każdym komputerze; blokada ochrony wstrzymuje odbiór.

Recovery sprawdzono dla awarii procesu. Nie obiecujemy odporności na zanik
zasilania/uszkodzenie dysku, fsync katalogu na Windows, synchronizację projektu
lub międzykomputerowe przejęcie blokad. Znane sync/network roots są blokowane;
dowolny klient synchronizacji wymaga jawnego potwierdzenia użytkownika.
Limit15000 JPEG jest założeniem wydania, nie wynikiem benchmarku. Benchmarków
ani danych operatora nie używano. Pomocniczy cache widoku nie jest kopią projektu.
