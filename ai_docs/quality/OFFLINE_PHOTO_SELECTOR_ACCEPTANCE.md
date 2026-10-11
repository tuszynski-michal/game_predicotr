---
title: Lokalny selektor Windows — odbiór pilotażu
status: blocked
last_updated: 2026-10-11
---

# Odbiór pilotażu lokalnego selektora Windows

To jest rejestr dowodów odbioru TASK-0979, nie raport audytu kodu.
Operator zlecił audyt całego zakresu dopiero po pięciu taskach. Testy agentowe
nie zastępują uruchomienia paczki otrzymanej przez odbiorcę.

## Paczka

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

## Warunek zakończenia

TASK-0979 pozostaje blocked do przedstawienia dowodów fizycznego odbioru.
Przygotowanie kodu i paczki umożliwia wykonanie0978 zgodnie z poleceniem operatora.
Pilotaż nie ma podpisu. Blokada Windows wstrzymuje odbiór; nie wyłączać ochrony.
Po zmianie paczki powtórzyć kontrole odnoszące się do otrzymanej wersji.
