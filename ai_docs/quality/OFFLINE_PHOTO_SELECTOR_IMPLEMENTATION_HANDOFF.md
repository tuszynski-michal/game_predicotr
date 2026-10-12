---
title: Lokalny selektor Windows — przekazanie implementacji do audytu operatora
status: changes_requested
last_updated: 2026-10-12
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
|0978 stara sesja|v1.7.322 /abe8e645ad9afe0444a4cf4ddd4c521b3ea7ff17|done|

Przygotowanie dokumentacji: v1.7.317 /e91b365cd02bf50ff914b1c4cda0b732432f8f3a.
Każdy task ma osobny commit. Pełne wyniki i ograniczenia są w jego Outcome oraz
CURRENT_STATE. Finalna paczka po0978 jest wskazana w rejestrze odbioru.
Historyczny ZIP0979 zachowano w out/releases/task-0979; nie mylić obu buildów.

## Finalna paczka i wyniki

Końcowa paczka wszystkich pięciu tasków:
`apps/selector-desktop/out/releases/pilot-0.1.0-abe8e645/Selektor zdjec-win32-x64-0.1.0.zip`.
Wersja0.1.0,149397136 bajtów, SHA-256
`2dcfe275cd7af44519c126272ad7df0e3354faed74366663ad7126480da21bea`.
app.asar SHA-256
`e2c60792e7affd24f473da939996f1ef2a511cd9c7d384fbdcef63b0526d1bab`.
Source commit `abe8e645ad9afe0444a4cf4ddd4c521b3ea7ff17` (v1.7.322),
dirty=true wyłącznie od dokumentacji, applicationSourceDirty=false.
BuiltAt2026-10-11T22:43:28.319Z, releasedAt2026-10-11T22:43:54.088Z.
Sąsiadujące .sha256/.release.json i ZIP zachowano bajtowo; sumy kopii zgodne
z artefaktami make. Release oraz pełny/source-relink/legacy smoke EXE
rozpakowanego z tego samego ZIP-a PASS, każdy krok z limitem do120 s.
Wersja0.1.0 pozostaje pierwszym nieprzekazanym pilotem. Nie jest podpisana.

Testy0978:107 unikalnych PASS (legacy25, recovery29, projekt43, foundation7,
UI3); lint/typecheck/format/build/package również PASS. Wcześniej rdzeń110/110
i Reviewer264/264 PASS; nie udajemy ich ponownego wykonania bez zmian tych modułów.
Docs:check i code-map:check PASS. Pełne grupy, komendy i ograniczenia zapisano
w Outcome tasków. Końcowy smoke sprawdził nowy proces, backup/relink,
relokację tej samej wersji programu oraz legacy preview/anulowanie/import.

## Wynik audytu operatora

[Raport Claude2026-10-12](OFFLINE_PHOTO_SELECTOR_IMPLEMENTATION_AUDIT_CLAUDE_20261012.md):
REVISE. Testy109/109, lint/typecheck/docs/mapy i sumy paczki potwierdzone
przez operatora. Otwarty P1-1 blokuje przekazanie pilotażu. Znaleziska i
oryginalny raport pozostają niezmienione. Poprawki0980/0981 są w commitach
v1.7.324 i v1.7.325, ich testy PASS opisują [dowody rundy](OFFLINE_PHOTO_SELECTOR_AUDIT_REMEDIATION_20261012.md).
Paczka0.1.1 i test zmiany wersji są w toku0982; ponowny audyt operatora pending.

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
