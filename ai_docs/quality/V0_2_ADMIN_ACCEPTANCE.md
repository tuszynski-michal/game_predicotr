---
title: Version 0.2 Admin acceptance
status: awaiting_owner_acceptance
last_updated: 2026-08-01
---

# Version 0.2 Admin acceptance

## Wynik techniczny

Automatyczna i przeglądarkowa bramka techniczna Admina 0.2 przeszła
`2026-08-01`. Test nie używał danych właściciela: każdy scenariusz PostgreSQL
tworzył osobną bazę, wykonywał migracje do `head` i usuwał bazę po teście.

Powtarzalna komenda:

```powershell
npm.cmd run v02:admin:acceptance
```

Każdy proces potomny ma limit 120 sekund. Raport maszynowy jest zapisywany w
ignorowanym katalogu
`artifacts/v02-admin-acceptance/acceptance-report.json` i nie zawiera sekretów
ani ścieżek wejściowych użytkownika.

## Evidence automatyczne

| Kontrola | Wynik | Zakres |
| --- | --- | --- |
| PostgreSQL integration | passed, 4 testy | publiczny przepływ M2, release i anulowanie, dwa scenariusze cleanup |
| Admin tests | passed, 126 testów | trzy workspace'y, URL, loading/error/empty, akcje, joby, release i cleanup |
| Admin typecheck | passed | TypeScript bez błędów |
| Admin lint | passed | ESLint |
| OpenAPI contract | passed | artefakt i generowany klient są aktualne |
| Admin production build | passed | statyczny build Next.js |

W trakcie pierwszego przebiegu bramka wykryła dwie rozbieżności fixture'ów po
wprowadzeniu `expectedLayoutCount`. Publiczny scenariusz M2 deklaruje teraz cel
1000 layoutów, a fixture release cel 2 layoutów. Skrócono również katalog
tymczasowy pytest, aby najdłuższa ścieżka artefaktu snapshotu nie przekraczała
praktycznego limitu Windows.

## Evidence przeglądarkowe

Na produkcyjnym buildzie i pustej lokalnej bazie sprawdzono viewport
1366 × 768:

- widoczne są dokładnie trzy workspace'y: `Zarządzanie grami`, `Wersje Android`
  i `Joby`,
- `?workspace=releases` i `?workspace=jobs` odtwarzają właściwy ekran po
  odświeżeniu,
- stan pusty gier, wydań i kolejki jobów jest jawny,
- `documentElement.scrollWidth` i `body.scrollWidth` wyniosły 1351 px przy
  `innerWidth = 1366 px`, więc nie wystąpił poziomy overflow,
- konsola nie zawierała błędów ani ostrzeżeń,
- nawigacja używa natywnych przycisków, a globalny styl `:focus-visible` obejmuje
  przyciski, linki, inputy i selecty.

Przed testem zatrzymano pozostawiony od 31 lipca stary proces Admina na porcie
3000. Po odbiorze procesy uruchomione przez test zostały zatrzymane, a porty
3000 i 8000 zwolnione.

## Odbiór właściciela

Ostatnia bramka produktowa pozostaje do wykonania przez właściciela. Na małym
kontrolowanym zestawie należy potwierdzić:

1. utworzenie i wybór gry,
2. import folderu, symbole i bieżące reguły,
3. przejście do Reviewera i powrót do Admina,
4. obserwację joba z filtrem statusu,
5. utworzenie jednego testowego wydania,
6. nawigację `Tab`, aktywację `Enter` i widoczność fokusu,
7. preview cleanup bez wykonywania resetu, chyba że dane są świadomie
   przeznaczone do usunięcia.

Wersja 0.2 nie jest zamknięta produktowo, dopóki właściciel nie potwierdzi tego
krótkiego odbioru i nie zostaną zaadresowane znalezione przez niego regresje.
