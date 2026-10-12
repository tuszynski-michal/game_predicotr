---
title: Lokalny selektor Windows — odbiór pilotażu
status: blocked
last_updated: 2026-10-12
---

# Odbiór pilotażu lokalnego selektora Windows

To jest rejestr dowodów odbioru TASK-0979, nie raport audytu kodu.
Operator zlecił audyt całego zakresu dopiero po pięciu taskach. Testy agentowe
nie zastępują uruchomienia paczki otrzymanej przez odbiorcę.

## Paczka0.1.2 — TASK-0983, prosty start i historia

Finalna paczka: `apps/selector-desktop/out/releases/pilot-0.1.2-c4181f7d/Selektor zdjec-win32-x64-0.1.2.zip`.
Wersja0.1.2, 149402003 bajtów, ZIP SHA-256 `9426704949dd8ab7d16f9d9743e2254257805a8ed1cc5dce38eecd2c37442e27`,
app.asar SHA-256 `0e2c2bf2894bd519ceea96e957e564dbe02f54d0963f3d381085396815c323c0`.
Source commit v1.7.329 /`c4181f7ddc8fca2518c2d9abc363ce3bcd307d5f`;
dirty=false, applicationSourceDirty=false. BuiltAt2026-10-12T12:13:30.073Z;
releasedAt2026-10-12T12:13:58.018Z. Sąsiadujące .sha256 i .release.json zachowane.

122 testy oraz wszystkie sześć finalnych smoke PASS: source-first start,
full, shortcuts/relink, legacy, UX oraz aktualizacja0.1.0→0.1.2.
Oba kierunki, historia i ponowne wskazanie przeniesionego źródła przeszły
nowy proces. [Dowody0983](OFFLINE_PHOTO_SELECTOR_START_VERIFICATION_20261012.md)
nie zastępują audytu operatora ani odbioru na komputerze odbiorcy; status
rejestru pozostaje blocked. Paczka0.1.2-9ade6a85 jest tylko wcześniejszym
buildem historycznym; nie używać jej jako finalnej.

## Poprawiona paczka 0.1.1

Paczka z commitów0980–0982, przygotowana do ponownego audytu operatora:
`apps/selector-desktop/out/releases/pilot-0.1.1-ede94bdc/Selektor zdjec-win32-x64-0.1.1.zip`.

- Wersja0.1.1;149400221 bajtów.
- ZIP SHA-256: `fa1891d20f0348de2e89e4a66d5b4e849744ba148ae961c29e5997072512b023`.
- app.asar SHA-256: `9c3d0c6bb46ac262106c1cf1e8c5181971045ee4ebafdf0d0bfcb957bd17adc8`.
- Source commit: `ede94bdcb3ad1cac5838f524b604423bec81b69f` (v1.7.326).
- dirty=false, applicationSourceDirty=false.
- BuiltAt2026-10-12T09:43:02.413Z; releasedAt2026-10-12T09:43:25.794Z.

Full, shortcuts/source-relink, legacy i UX smoke oraz aktualizacja
rzeczywistych ZIP-ów0.1.0→0.1.1 na własnej kopii PASS. Sąsiadujące `.sha256` i `.release.json` identyfikują tę paczkę.
Odbiór na komputerze odbiorcy i ponowny audyt operatora pozostają pending.
Starych paczek nie zastępujemy; poniższe dane są historycznym dowodem0.1.0.

## Historyczne paczki i wyniki 0.1.0

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

Historyczna sprawdzona paczka0979 (przed migracją0978):
`apps/selector-desktop/out/releases/task-0979/Selektor zdjec-win32-x64-0.1.0.zip`.
Wersja0.1.0,149393535 bajtów, SHA-256
`0e21b78a2fbaa79f57a9ad6504c5a071b678f933d0e624b7bb2d09adbcc0b108`.
Source commit `0121ce8f1bd3604977e1c60872da43a4110326d7`, dirty=true i
applicationSourceDirty=true (skrypty0979 przed commitem).
Sąsiadujące .sha256/.release.json zachowano bez zmiany. To nie jest paczka
fundamentu0975. Końcowy ZIP po0978 wskazano powyżej; każda przebudowa
ma własną sumę. Odbiorca sprawdza konkretną przekazaną paczkę.

## Kontrole agentowe

| Kontrola | Status | Dowód |
|---|---|---|
| Granice odczytu, sandbox, lokalny JPEG, blokada internetu/okien | PASS0975 | Outcome0975, testy7/7 i packaged smoke |
| Trwałość, awarie, idempotencja, checksumy, nowy proces | PASS0976 | Outcome0976,50 unikalnych testów |
| Pełny interfejs, skróty, numeracja, wznowienie | PASS0977 | Outcome0977, test:ui3/3, pełny i krótki smoke rzeczywistego EXE |
| ZIP0979 i finalny ZIP po0978, SHA-256, rozpakowana kopia | PASS | release2/2 wcześniej; finalny release i trzy smoke tego samego ZIP-a; metadane powyżej |
| Backup/restore oraz relokacja kopii programu | PASS0979 częściowy | smoke:release; symulacja aktualizacji tą samą wersją, bez fizycznego reboot/innej wersji |
| Przejęcie starej sesji bez zmian oryginału | PASS0978 | Kontrakt25 i recovery29, packed EXE preview/import/nowy proces; Outcome0978 |
| Poprawki po audycie i ZIP0.1.1 | PASS0980–0982 lokalny |130 testów, fresh worker/close/skipped/scroll, cztery warianty smoke końcowego ZIP-a |
| Rzeczywista zmiana programu0.1.0→0.1.1 na własnej kopii | PASS0982 lokalny | Decyzje/currentRelativePath/SHA seq1-9 zachowane, nowa decyzja i kolejny proces; oryginalne SHA/size/mtime bez zmian |

Test przeniesionego źródła i natywnego relink w nowym procesie również PASS0979.
Oryginalne dane pozostają nienaruszone. Pierwszy timeout harnessu naprawiono;
nie jest dowodem odbioru, a finalne przebiegi są PASS.

## Odbiór operatora na drugim komputerze

Uzupełnić status i konkretny dowód. Nie wpisywać PASS na podstawie testu agenta.

| Kontrola | Status | Dowód operatora |
|---|---|---|
| Model komputera, Windows11 x64, data, wersja paczki i zgodny SHA-256 | PENDING | — |
| ZIP otrzymany faktycznym kanałem dystrybucji; cały folder rozpakowany | PENDING | — |
| Uruchomienie bez zainstalowanego Node.js/Pythona | PENDING | — |
| Wynik ochrony Windows; przy blokadzie odbiór wstrzymany | PENDING | — |
| Internet wyłączony, host niedostępny; nowa partia ukończona | PENDING | — |
| Restart Windows w trakcie partii; ponowne Kontynuuj zachowuje pracę | PENDING | — |
| Aktualizacja do oddzielnego folderu programu; dotychczasowy projekt otwarty | PENDING | — |
| Przeniesiony source wskazany ponownie, bez zmiany postępu | PENDING | — |
| Kopia zamkniętego projektu i wyniku przywrócona w osobnym lokalnym katalogu | PENDING | — |
| JPEG-i zgodne bajtowo, zwykły folder wynikowy i manifest v2 | PENDING | — |
| Projekt i aktywny wynik poza synchronizacją/udziałem; przekazano tylko gotowy wynik | PENDING | — |

## Audyt implementacji — 2026-10-12

[Audyt operatora Claude](OFFLINE_PHOTO_SELECTOR_IMPLEMENTATION_AUDIT_CLAUDE_20261012.md)
ma werdykt REVISE. Potwierdza109/109 testów i sumy obecnej paczki, ale
P1-1 (opóźnienia interakcji) oczekuje ponownej oceny operatora przed przekazaniem.
P2-1 i P2-3 mają poprawki0980/0981 oraz regresje backendu i ZIP-a.
Instrukcja opisuje odtworzenie brakującego JPEG-a z kopii; pełny SHA open
i rosnąca historia pozostają jawnymi ograniczeniami. Raport operatora pozostaje bez zmian.
Poprawki0980/0981 mają osobne commity i nowe testy. [Dowody rundy](OFFLINE_PHOTO_SELECTOR_AUDIT_REMEDIATION_20261012.md) opisują wykonanie oraz pozostawione ograniczenia. ZIP0.1.1 i rzeczywista aktualizacja0.1.0→0.1.1 na własnej kopii PASS0982. Ponowny audyt operatora jeszcze nie został wykonany.

## Warunek zakończenia

TASK-0979 pozostaje blocked do przedstawienia dowodów fizycznego odbioru.
Przygotowanie kodu i paczki umożliwia wykonanie0978 zgodnie z poleceniem operatora.
Pilotaż nie ma podpisu. Blokada Windows wstrzymuje odbiór; nie wyłączać ochrony.
Po zmianie paczki powtórzyć kontrole odnoszące się do otrzymanej wersji.
