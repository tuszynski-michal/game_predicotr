---
title: TASK-0849 — cofnięcie ostatniego zapisu audytu planszy 431508
status: done
last_updated: 2026-10-05
---

# TASK-0849 — cofnięcie ostatniego zapisu audytu planszy 431508

## Status

`done`

## Goal

Przywrócić poprzednią geometrię planszy 431508 i umożliwić jej ponowny przegląd
w audycie, bez usuwania historii i bez cofania innych plansz.

## Context / authorization

Operator polecił: „cofnij mi ostanio zapisaną geometrię bo za szybko zapisałem”.
Odczyt historii wskazuje p00545, board 85445ac4-5d6a-4ebc-bb65-7a16500e96db,
review 937c824b-df21-4b20-aeb3-da41d30966b6, revision 2,
receipt 9b4c8f0f-23cb-4643-9c97-79710bb977a1, 2026-10-05 12:41:39.780470 UTC.
Poprzednia rewizja 1 istnieje. Zapis zmienił cropy i zatwierdził 15 symboli;
przed nim wszystkie 15 pól wymagało przeglądu. Założenie operacyjne: cofnięcie
obejmuje geometrię i zatwierdzenia z tego samego zapisu. Nie ma otwartych
decyzji produktowych; nie dodajemy funkcji undo do UI.

## Recommended execution

gpt-6.1-sol, high, samodzielna ograniczona operacja z kontrolą historii,
idempotencji i odczytem w nowym procesie. Bez delegowania.

## Relevant docs

- requirements/ADMIN_APP.md — audyt i D-488/D-493/D-494
- architecture/API_CONTRACT.md — geometry-revisions oraz niezmienne artefakty audytu
- process/PLAN_STANDARD.md, process/TASK_TEMPLATE.md, process/DEFINITION_OF_DONE.md
- guides/LOCAL_OPERATION_GUIDE.md — lokalny audyt

## Scope / operational choice

1. Zarchiwizować odczyt stanu, sprawdzić ostatni zapis i CAS obu rewizji.
2. Wykonać istniejący POST geometry-revisions z narożnikami rewizji 1,
   bez cellSymbols. Nowa rewizja kompensuje zapis 2; historia pozostaje.
   Wcześniejszy stan 15 pending umożliwia wycofanie zatwierdzeń przez
   standardową invalidację cropów. Nie usuwać rekordów ani plików.
3. Zapisać nową niezmienną wersję artefaktu audytu. Zachować wszystkie 975
   pozycji i ich kolejność, rebase tylko p00545 do rewizji kompensującej.
   Metadane wskazują poprzedni audyt, jego SHA i cofnięty receipt. Pozostałe
   baseline revisions i propozycje siatek pozostają identyczne.
4. Przepiąć artefakty propozycji symboli do nowego audytu bez zmiany ich
   komórek, wag ani biblioteki. Dla p00545 przed publikacją potwierdzić SHA
   PNG podglądu dla nowych oczekiwanych rewizji; brak zgodności zatrzymuje
   publikację. Manifest audytu publikować atomowo na końcu.
5. Sprawdzić nowy proces, p00545 open, 15 pending w bazie, zachowanie pozostałych
   plansz, wszystkie open proposals oraz UI. Zapisać Outcome i osobny commit.

## Expected files

- Proponowane artefakty operacji: .runtime/task0849/ i nowa wersja audytu.
- Dokumenty: ten task i własny fragment CURRENT_STATE.md.
- Kod aplikacji, kontrakt HTTP i schemat bazy pozostają bez zmian.

## Acceptance criteria

- [x] Plansza ma poprzednie narożniki; oryginalny zapis 2 zachowany w historii.
- [x] 15 przypadkowych zatwierdzeń wycofane, p00545 ponownie open z propozycjami.
- [x] Pozostałe baseline, kolejność, symbole i geometrie plansz zachowane.
- [x] Trwała komenda idempotencji, brak usuwania danych, odczyt w nowym procesie.
- [x] UI, Outcome, CURRENT_STATE i osobny commit kompletne.

## Outcome

Read-only snapshot: .runtime/task0847/last-geometry-readonly.json. Pierwsze
zapytania ujawniły routing tekstowego SELECT jako write oraz rozbieżne nazwy
tabel/kolumn; transakcje wycofane bez zapisów. Ostateczny odczyt PASS.

Kompensacja przez istniejący POST: revision 3,
receipt 4c2e9a09-b1af-4b3f-99b9-9d3467ff6ae6,
idempotency f53fb8b5-1760-4ef8-9aa3-c32bd9dbe667. Przywrócono cztery narożniki
rewizji 1. Rewizje 1 i 2 pozostają w bazie. Wszystkie 15 komórek na rewizji 3
ma pending/requires_review i verified_symbol_id_v2=NULL. Stara aprobata
rewizji 2 pozostaje proweniencją historyczną, bez weryfikacji bieżących pikseli.
Początkowa kontrola błędnie oczekiwała usunięcia tej proweniencji; poprawiono
kontrolę do rzeczywistego kontraktu invalidacji, bez zmiany implementacji.

Nowy niezmienny audyt:
silent-grid-777-20261004-undo-p00545-20261005t130216. Tylko p00545 ma baseline 3;
wszystkie 975 pozycji i ich kolejność zachowano. Oryginalny audyt niezmieniony.
Przepięto 917 istniejących artefaktów symboli (obejmują też archiwalne wyniki
zamkniętych plansz); komórki i algorytmy każdego są identyczne z oryginałem.
SHA PNG p00545 zgodny przed i po cofnięciu; zmieniono tylko audyt i oczekiwane
rewizje kontekstu. Manifest nowego audytu opublikowany atomowo na końcu.

Nowy proces: p00545 open, geometria 3, 15 propozycji RGB v2, wszystkie 917
payloads i manifests PASS. Kolejka 482 open / 493 corrected z 975;
p00545 jest pierwsza. Porównanie 974 innych geometrii audytu oraz komórek
ośmiu pozostałych plansz tego źródła PASS. Istniejący zapis normalnie
aktualizuje proweniencję źródła, ale zachowuje ich geometrie i decyzje.
UI pokazuje planszę 431508, 15/15 propozycji, 6 niepewnych; bez Save.
Kontrola 40 testów istniejącego API audytu/propozycji PASS (27,53 s), Ruff
lokalnych pomocników PASS. Kod aplikacji niezmieniony, więc buildy, migracje
i regeneracja klienta nie były potrzebne. Brak usuwania danych, treningu,
aktywacji modelu, restartu usług i push. Warunki DoD i zakres operacji spełnione.

Ograniczenia prób: szeroki odczyt porównawczy przekroczył limit 10 s;
ograniczono go do 975 plansz audytu i 9 plansz źródła. Pierwszy odczyt POST
podglądu bez nagłówka intencji Admin został odrzucony 403, bez zmian danych.
Publikacja początkowo oczekiwała 496 plików (liczba ówczesnych open), lecz
faktycznie archiwum ma 917; przed publikacją zachowano i porównano wszystkie.

Dowody trwałe: artifacts/grid-audit-undo-20261005/p00545/ oraz nowy audyt.
Szczegółowe logi i pomocnik operacyjny: .runtime/task0849/; wywołania
mają limity 20–55 s. Dane operacji odczytano w nowym procesie.
Plan nie obejmuje przycisku Cofnij; kolejna operacja wymaga nowego polecenia.

Commit: v1.7.195; pełny hash zostanie dopisany po zapisie commita.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0849 | gpt-6.1-sol | high | Operacja jednej planszy wymaga ochrony historii, CAS i spójności artefaktów. | Samodzielny odczyt w nowym procesie; bez delegowania. |
