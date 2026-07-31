---
title: Version 0.2 execution plan
status: accepted
last_updated: 2026-07-31
---

# Plan wykonania wersji 0.2

## Cel

Przekształcić działające techniczne piony w prosty, prowadzony workflow:
folder zdjęć → layouty → symbole → reguły → zatwierdzanie → wydanie Android.
Następnie domknąć odłożony hardening, backup, recovery, dystrybucję i
automatyczną publikację rzeczywistych danych.

## Warunki rozpoczęcia

- wersja `0.1` przeszła TASK-0118 i TASK-0119,
- pytania Q-022–Q-032 zostały omówione z właścicielem,
- istniejące decyzje o offline mobile, niezmiennych release’ach, ochronie
  człowieka i ograniczonym Reviewerze pozostają obowiązujące.

## V0.2.1 — Nawigacja i jeden kontekst gry

- `TASK-0120 — Admin workspace navigation and collapsible sections`
  — dwa kafelki trybu, accordion, zachowanie scrolla i stan w URL.
- `TASK-0121 — Active game catalog, filters and dependency-safe removal`
  — sekcja `Gry`, podświetlenie, filtry i uzgodniona semantyka `Usuń`.

### Bramka V0.2.1

- bez aktywnej gry wejście pokazuje wyłącznie `Gry`; po wyborze pojawiają się
  zwinięte nagłówki sekcji zależnych,
- zawsze istnieje najwyżej jeden aktywny kontekst gry,
- zmiana sekcji nie resetuje wyboru ani pozycji użytkownika,
- żadna zależna sekcja nie ma drugiego selecta gry.

## V0.2.2 — Folder zdjęć, layouty i katalog symboli

- `TASK-0122 — Local image folder source and resumable layout ingestion`
  — bezpieczny wybór folderu, discovery, manifest i wznowienie.
- `TASK-0123 — 500k completeness, incremental gaps and source quality selection`
  — brakujące zakresy, doładowanie, deduplikacja i wybór czytelniejszego źródła.
- `TASK-0124 — Automatic symbol catalog bootstrap from imported layouts`
  — oczekiwana liczba symboli, propozycje nazw i stabilne kody.
- `TASK-0125 — Representative symbol image picker and catalog refinement`
  — 10 kandydatów, kolejne strony kandydatur i edycja grafiki/nazwy.

### Bramka V0.2.2

- import nie zależy od `examples/imgs` ani Excela,
- ponowienie nie dubluje sekwencji,
- użytkownik widzi dokładny licznik braków do 500 000,
- symbole powstają z rzeczywistych cropów dopiero po imporcie,
- każda automatyczna decyzja zachowuje pochodzenie i metrykę jakości.

## V0.2.3 — Reguły i zatwierdzanie bez technicznego szumu

- `TASK-0126 — Single rules workspace with internal immutable versioning`
  — jeden bieżący widok bez eksponowania pełnej historii.
- `TASK-0127 — Full-layout payout recomputation workflow`
  — jawne przeliczenie, progress, wersja algorytmu i blokada release przy brakach.
- `TASK-0128 — Integrated board approval entry and prerequisite states`
  — jedna sekcja zatwierdzania prowadząca do osobnego Reviewera.
- `TASK-0129 — Remove duplicate Dataset and Manual Review navigation`
  — przeniesienie funkcji bez usuwania encji i audytów backendu.

### Bramka V0.2.3

- zmiana reguł nigdy nie modyfikuje opublikowanej historii,
- 500 000 payoutów można przeliczyć i wznowić,
- zatwierdzanie jest dostępne wyłącznie dla prawidłowego importu,
- nie ma dwóch konkurencyjnych ekranów wykonujących tę samą decyzję review.

## V0.2.4 — Wydania Android, joby i retencja

- `TASK-0130 — Android release workspace and multi-game selection`
  — osobny kafelek, wybór aktywnych gier i jedna orkiestracja.
- `TASK-0131 — Contextual operations instead of the global Jobs section`
  — progress i retry przy imporcie/wydaniu oraz kompaktowa diagnostyka.
- `TASK-0132 — Release, job and artifact retention controls`
  — uzgodnione usuwanie ciężkich artefaktów bez kasowania wymaganej historii.
- `TASK-0133 — Admin 0.2 end-to-end usability and regression acceptance`
  — desktop 1366 × 768, klawiatura, loading/error/empty i pełny workflow.

### Bramka V0.2.4

- użytkownik nie musi odwiedzać globalnego ekranu Jobs, aby przygotować APK,
- każdy etap ma kontekst gry albo wydania,
- cleanup nie narusza aktywnego release, checksum, manifestu ani audytu,
- cały podstawowy workflow jest krótszy i nie wymaga nawigacji po jednej długiej
  stronie.

## V0.2.5 — Rzeczywiste dane i odłożony hardening

- `TASK-0076 — Large image dataset publication and mobile release` po
  spełnieniu `massImportAllowed = true`,
- `TASK-0080–0081` — stabilny podpis i odtwarzalna weryfikacja release,
- `TASK-0082–0083` — backup/restore PostgreSQL i artefaktów,
- `TASK-0084` — recovery uszkodzonego snapshotu,
- `TASK-0085–0087` — macierz urządzeń, offline regression, performance i
  accessibility; zakres urządzeń zostanie ustalony dla `0.2`,
- `TASK-0088–0089` — dystrybucja, rollback, disaster recovery i finalny odbiór.

### Bramka V0.2

- Admin realizuje prowadzony workflow bez duplikowania kontekstu gry,
- rzeczywisty dataset może zostać opublikowany albo jawnie pozostaje wyłączony
  przez niespełnioną bramkę jakości,
- backup został rzeczywiście odtworzony,
- podpis, APK, snapshot i rollback są audytowalne,
- wymagane urządzenia `0.2` przechodzą pełną regresję offline,
- wszystkie krytyczne błędy są zamknięte, a ograniczenia zaakceptowane.

## Poza zakresem bez nowej decyzji

- Google Play i publiczna dystrybucja,
- publiczny Admin API lub PostgreSQL,
- synchronizacja mobile z backendem,
- usunięcie wersjonowania domenowego tylko dlatego, że jest ukryte w UI,
- automatyczne kasowanie decyzji człowieka, audytu lub aktywnego release.
