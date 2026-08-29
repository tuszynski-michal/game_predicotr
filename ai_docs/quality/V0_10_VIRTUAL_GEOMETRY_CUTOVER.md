---
title: V0.10 virtual geometry cutover acceptance
status: accepted
last_updated: 2026-08-29
---

# Wynik odbioru

Decyzja TASK-0318: **brak promocji trybu** (`insufficient_evidence`).

Kod Structured OpenCV, wirtualny renderer i bounded walidacja pozostają
dostępne w kontrolowanych trybach per gra. `structured_default` nie staje się
domyślnym silnikiem, ponieważ nie istnieje zaakceptowany raport board-level
spełniający pełny kontrakt próbki.

## Audyt dowodów

| Wymaganie | Stan 2026-08-29 |
|---|---|
| minimum 100 ręcznie sprawdzonych źródeł | brak raportu |
| minimum 500 aktywnych plansz | brak raportu |
| minimum 5 bucketów jakości/kąta | brak raportu |
| wszystkie historyczne false-success i failures | nieudokumentowane w raporcie 0.10 |
| holdout rozłączny od strojenia progów | brak raportu |
| zakończona walidacja proweniencji gry | TASK-0317 nie uruchamiał operacyjnego backfillu |
| board-level automatic correctness | nie można wyliczyć |

Brak wyniku nie jest interpretowany jako `<95%`. TASK-0319 nie zostaje
automatycznie uruchomiony. Można go rozpocząć dopiero, gdy kompletny,
zaakceptowany raport wykaże wynik poniżej 95%.

## Obowiązująca bramka

```text
>= 98%   structured_default + virtual_default
95–98%   structured_review + virtual_shadow
< 95%    legacy + legacy_files; TASK-0319 może zostać uruchomiony
brak lub niepełna próbka   bez zmiany bieżącego trybu
```

Mianownikiem jest każda ręcznie sprawdzona aktywna plansza. Odrzucone źródło
wnosi wszystkie swoje aktywne sloty jako błędy. Confidence symboli, liczba
poprawnych komórek oraz wynik na danych użytych do strojenia nie zastępują tej
metryki.

## Stan kompatybilności

- nie usunięto żadnego legacy cropa ani stage resultu;
- nie usunięto historycznych endpointów/aliasów Reviewera;
- nie zmieniono canonical owner ani decyzji człowieka;
- istniejące joby zachowują przypięte snapshoty;
- endpoint status/start TASK-0317 pozostaje jedyną publiczną operacją
  dotyczącą walidacji rolloutu; nie dodano endpointu promującego tryb;
- jawnie wybrane importy v20/v19 pozostają samowystarczalne i nie odczytują
  równoległego stanu rolloutu 0.10.

## Pełny rollback operacyjny

Jeżeli gra zostanie w przyszłości promowana po zaakceptowanym raporcie:

1. zatrzymać uruchamianie nowych importów tej gry;
2. pozwolić trwającym jobom dojść do checkpointu albo je kontrolowanie
   anulować; ich przypiętych snapshotów nie modyfikować;
3. w jednej transakcji i pod blokadą rekordu gry ustawić następny stan na
   `geometry_mode=legacy`, `cell_asset_mode=legacy_files`, zwiększyć `revision`
   dokładnie raz i zapisać aktora;
4. tworzyć nowe joby wyłącznie po odczycie nowego snapshotu legacy;
5. nie zmieniać `image_sequence_canonical`, verified labels, source geometry,
   prediction revisions ani eventów;
6. pozostawić UI zdolne do odczytu `legacy_file`; w razie regresji ukryć nowe
   akcje virtual, nie usuwać ich danych;
7. uruchomić bounded walidację właścicieli i checksum historycznego retry;
8. po odbiorze wznowić importy.

Po pojawieniu się `virtual_source` rollback pozostaje operacyjny. Downgrade
migracji 0082 ani usuwanie kolumn/tabel nie jest dozwoloną procedurą rollbacku.

## Warunek ponownego rozpatrzenia

Nowy raport musi jawnie podać engine/config fingerprint, źródła i buckety,
liczniki klasyfikacji, oba mianowniki, listę historycznych przypadków oraz
checksumę dowodów. Dopiero taki raport może zostać przekazany do domenowej
polityki `assess_geometry_cutover` i osobno zaakceptowany przez właściciela.
