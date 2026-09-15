---
title: Kompaktowy stan luk i natychmiastowa zmiana podglądu po usunięciu
status: done
---

# TASK-0554 — Kompaktowy stan luk i natychmiastowa zmiana podglądu po usunięciu

## Status

`done`

## Goal

Usunięcie sekwencji F natychmiast pokazuje następne zdjęcie z zachowanego cache, nie oferuje przywracania, a trwały stan katalogu zachowuje wyłącznie aktualne luki, aktywne pliki, dane uzupełnień i pojedynczą operację recovery.

## Context

Aktualne usunięcie trzyma w pamięci pełny `File` dla przywrócenia, dopisuje rosnący dziennik napraw oraz po zmianie snapshotu unieważnia Object URL-e wszystkich zdjęć. W rezultacie użytkownik widzi kilka sekund oczekiwania, mimo że następne zdjęcie było już w read-ahead cache.

## Dependencies / entry conditions

- TASK-0553 jest zakończony na branchu `version-0.10` w commicie `v0.10.286`.
- Nie istnieje aktywne zadanie bezpośrednio w `ai_docs/tasks/`.
- Użytkownik zaakceptował usunięcie cofania usuniętej sekwencji oraz kontrolowaną kolejkę trwałego zapisu w tle.

## Recommended execution

`gpt-6-astra`, reasoning `high`. Zmiana obejmuje trwały kontrakt lokalnego manifestu, recovery po restarcie i optymistyczny UI, więc wymaga dokładnej analizy kolejności zapisu. Eskalacja do niezależnego review jest wymagana, jeżeli test recovery ujawni niejednoznaczność stanu po przerwaniu usunięcia.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Scope

- Usunąć przywracanie ostatnio usuniętej sekwencji, jego skrót, komunikat i referencję `File` w pamięci.
- Zastąpić historyczny manifest napraw stanem bieżącym: aktywne pliki, zakresy luk po usunięciu, aktywne uzupełnienia z ich proweniencją, minimalne potwierdzenia usunięć wymagane przez weryfikację zakresu i pojedyncza oczekująca operacja recovery.
- Przenieść dotychczasowe manifesty v1 do odczytywalnego, deterministycznego stanu kompaktowego bez zmiany JPEG-ów ani katalogów użytkownika.
- Zachować manifest wyjściowy i pochodny handoff aktywnych uzupełnień, ponieważ są wejściem dalszego cięcia oraz importu.
- Zrezygnować z zapisu dziennika interakcji repairu i zapisywać trwałe mutacje w jednej kolejce, po uprzednim natychmiastowym przełączeniu UI na następne zdjęcie.
- Utrzymać cache `Object URL` według trwałej ścieżki zdjęcia w obrębie repairu, aby usunięcie jednego pliku nie dekodowało ponownie całego okna podglądu.
- Błąd kolejki zapisu pokazać jako trwały błąd workspace'u i zablokować kolejne mutacje do czasu ponownego odczytu katalogu.

## Out of scope

- Usuwanie historycznych plików dziennika z istniejących katalogów użytkownika.
- Zmiana formatu manifestu wynikowego, silnika cięcia albo importu plansz.
- Cofanie wypełnienia luki, które nie korzysta z kopii usuniętego pliku.

## Acceptance criteria

- [ ] W trybie usuwania nie ma przycisku, skrótu ani pamięciowego przywracania ostatniej sekwencji.
- [ ] Po F UI przełącza się na następny aktywny obraz bez czekania na zapis manifestu, a jego zachowany Object URL nie jest ponownie dekodowany.
- [ ] Trwałe mutacje są wykonywane w kolejności; błąd jednej mutacji nie jest maskowany i blokuje kolejne operacje do odczytu katalogu.
- [ ] Bieżący manifest nie ma rosnącej historii operacji ani repair trace; przechowuje wyłącznie aktualny stan konieczny dla luk, uzupełnień, weryfikacji oraz recovery.
- [ ] Manifesty v1 są odtwarzane deterministycznie do stanu kompaktowego; istniejące JPEG-i i handoff aktywnych uzupełnień są zachowane.
- [ ] Weryfikacja nazw nadal rozpoznaje źródło wcześniej usuniętej sekwencji.

## Technical notes

Źródłem prawdy pozostaje katalog z `manual-image-selection-output-v1.json` oraz manifestem naprawy. Nowy stan kompaktowy nie ma append-only `operations`: aktywne wypełnienia są zapisywane jako aktualne wpisy handoffu, a usunięcia mają po jednym potwierdzeniu per aktywnie brakujący plik. Jedyna transakcyjna historia to `pendingOperation`, potrzebna do fail-closed recovery po przerwaniu między zmianą pliku i manifestu.

Kolejka UI najpierw tworzy lokalny snapshot bez usuniętej sekwencji i zmienia kursor. Następnie uruchamia dokładnie jedną trwałą operację. Przy powodzeniu jej wynik zostaje potwierdzony; przy błędzie repair przechodzi do błędu wymagającego ponownego odczytu, bez potajemnego dalszego zapisu. Cache viewer'a jest kluczowany ścieżką względną oraz tożsamością katalogu, nie ordinalem tablicy; url-e nieobecne w nowym oknie są zwalniane.

## Expected files

- Istniejące: `packages/manual-image-selection-core/src/repair.ts` — kompaktowy kontrakt i migracja odczytu v1.
- Istniejące: `packages/manual-image-selection-core/test/manual-selection-repair.test.mjs` — kontrakt stanu, recovery i migracja.
- Istniejące: `apps/admin/src/features/manual-image-selection/manual-selection-repair-storage.ts` — zapis i recovery stanu kompaktowego bez trace.
- Istniejące: `apps/admin/src/features/manual-image-selection/manual-selection-repair-workspace.tsx` — natychmiastowe przełączenie i kontrolowana kolejka.
- Istniejące: `apps/admin/src/features/manual-image-selection/manual-image-viewer.tsx` — cache stabilny po usunięciu.
- Istniejące: `apps/admin/src/features/manual-image-selection/manual-selection-range-verification-workspace.tsx` — odczyt kompaktowego potwierdzenia usunięcia.
- Istniejące: `apps/admin/test/manual-selection-repair.test.mjs` — testy storage/UI-kontraktu.
- Istniejące: `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`, `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`, `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Usunięcie bieżącej sekwencji → lokalny snapshot wskazuje sąsiada przed zakończeniem kontrolowanego zapisu, a po powodzeniu katalog i output manifest nie zawierają pliku.
- Następny obraz jest w poprzednim oknie podglądu → zachowuje Object URL i nie wywołuje nowego odczytu/decode.
- Błąd zapisu po optymistycznej zmianie → komunikat błędu, blokada kolejnej mutacji, ponowny odczyt odbudowuje stan z katalogu.
- Historyczny manifest v1 z fill/undo_fill/delete/restore → kompaktowy stan wyprowadza tylko aktywne uzupełnienia oraz aktywnie brakujące potwierdzenia usunięć.
- Weryfikacja nazwy źródła po usunięciu → rozpoznaje kompaktowe potwierdzenie bez skanowania historii.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr, timeout pojedynczej komendy: 120 s
pnpm --filter @game-predictor/manual-image-selection-core test
pnpm --filter @game-predictor/manual-image-selection-core typecheck
pnpm --filter @game-predictor/admin test -- manual-selection-repair.test.mjs
pnpm --filter @game-predictor/admin typecheck
pnpm --filter @game-predictor/admin lint
pnpm --filter @game-predictor/admin build
```

## Risks / open questions

- Stare pliki trace pozostają niezmienione dla bezpieczeństwa danych, lecz nowa wersja ich nie czyta ani nie rozbudowuje.
- Zachowanie po błędzie zapisu wymaga jawnego odczytu katalogu, aby nie kontynuować na lokalnym snapshotcie niepotwierdzonym przez system plików.

## Outcome

### Changed

- Wprowadzono kompaktowy manifest repair v2, który utrzymuje bieżące luki,
  aktywne fill, potwierdzenia delete i pojedynczy pending recovery zamiast
  rosnącej historii operacji oraz repair trace. Reader v1 tworzy v2 bez
  naruszania historycznego pliku ani JPEG-ów.
- Usunięto przywracanie delete, jego skróty i pamięciową kopię `File`.
  Weryfikacja zakresów korzysta z trwałego potwierdzenia delete.
- Usunięcie najpierw aktualizuje lokalny snapshot i kursor, po czym w jednej
  kolejce zapisuje katalog oraz manifesty. Błąd blokuje mutacje do ponownego
  otwarcia katalogu. Viewer zachowuje cache Object URL po `relativePath` i
  repair scope, więc następny obraz z okna podglądu jest dostępny natychmiast.
- Recovery odtwarza output manifest, gdy delete został już sfinalizowany, ale
  zapis outputu nie doszedł do skutku.

### Verification results

- `node --experimental-strip-types --test packages/manual-image-selection-core/test/manual-selection-repair.test.mjs` — 9/9.
- `node --experimental-strip-types --test apps/admin/test/manual-selection-repair.test.mjs` — 16/16.
- Pełny core: 104/104; pełny Admin zakończył się poprawnie w reporterze dot.
- Core i Admin typecheck, formatowanie oraz skoncentrowany lint są zielone.
- Produkcyjny build Admina przeszedł po kompilacji, typechecku i generacji stron.

### Not completed

- Historyczne pliki v1 oraz trace nie są usuwane z katalogów użytkownika; nowy
  workflow ich nie odczytuje ani nie rozszerza.

### Documentation updates

- Zaktualizowano wymagania i architekturę lokalnej korekty, `CURRENT_STATE`
  oraz decyzję D-388.

### Recommended next task

- Brak; task jest zakończony.

## Plan realizacji

1. Wprowadzić zwalidowany, kompaktowy stan repairu i deterministyczne przejście z v1, zachowując wyjściowy manifest oraz handoff aktywnych uzupełnień.
2. Przełączyć storage i weryfikację zakresu na bieżące wpisy stanu, usunąć trace oraz historyczne zależności operacji.
3. Usunąć delete-undo z workspace'u, wprowadzić optymistyczną zmianę snapshotu i seryjną kolejkę zapisu z fail-closed błędem.
4. Ustabilizować cache viewer'a względem ścieżki i katalogu repairu, a następnie uruchomić testy, typecheck, lint oraz build.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0554 — Kompaktowy stan luk i natychmiastowa zmiana podglądu po usunięciu | gpt-6-astra | high | Trwały lokalny kontrakt, recovery i kolejność UI–system plików wymagają precyzyjnej analizy regresji. | Wymagany tylko, gdy test recovery ujawni niejednoznaczny stan; gpt-6-astra, high. |
