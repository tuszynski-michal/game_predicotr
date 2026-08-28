---
title: Odbiór walidacji geometrii i jakości symboli 0.9
status: accepted
last_updated: 2026-08-28
---

# Odbiór wersji 0.9

## Zakres

Raport zamyka TASK-0304 po cutoverze topologii, walidacji geometrii,
nieczytelnych symboli, unknown w wyszukiwaniu/datasetach/payoutach oraz
bezpiecznej proweniencji cropów treningowych. Nie obejmuje zastępczego zdjęcia
jednej planszy; ten zakres znajduje się w TASK-0305.

## Migracje i rzeczywiste dane

- Alembic: `0075_remove_obsolete_board_search_storage (head)`.
- Gra: `80f3c7ec-6110-4e20-a263-2675ee5b15d6`.
- Przypięta topologia: `3 × 5`, rules version
  `68fa8e06-9b23-4dec-a258-c8638b59d1c3`.
- Plansze objęte backfillem: `397 976`.
- Komórki w projekcji: `3 572 295`.
- Brak topologii: `0`.
- Brak zatwierdzonej geometrii zakończonej planszy: `0`.
- Niespójna jakość: `0`.
- Brak proweniencji zatwierdzonego cropa: `0`.
- Podwójny właściciel `game + sequence_number` w fast documents: `0`.

Backfill był ograniczony do 200 plansz na transakcję, zapisywał checkpoint i
został pomyślnie wznowiony po kontrolowanym przerwaniu. Nie przetwarzał ponownie
obrazów i nie tworzył nowych binariów.

## Storage

| Stan | Monitorowane relacje |
|---|---:|
| przed migracją | 6 968 860 672 B |
| po migracji i backfillu | 6 210 854 912 B |
| różnica | −758 005 760 B |

Stara tabela `image_board_search_documents` nie istnieje. Nie wykonano
`VACUUM FULL`; obrazy źródłowe, cropy, obserwacje i audyt pozostały bez zmian.

## Kontrole automatyczne

- domena i API 0.9: `61 passed`;
- geometria, payout i readiness workera: `41 passed`;
- Admin: `296 passed`;
- lokalny workflow geometrii Reviewera: `7 passed`;
- Ruff i formatowanie zmienionych plików: pass;
- lint i typecheck Admina/Reviewera: pass;
- produkcyjne buildy Admina/Reviewera: pass;
- OpenAPI i generowany klient: pass.

Celowany mypy API zatrzymuje się na istniejącym braku markerów `py.typed`
pakietu workera. Nie dotyczy kodu zmienionego w TASK 13 i pozostaje znanym
ograniczeniem repozytorium.

## Decyzja odbiorcza

Wersja 0.9 jest przyjęta. Lokalny Reviewer używa obowiązkowego workflowu
walidacji geometrii; zdalny Reviewer zachowuje swój ograniczony kontrakt.
Fallback lokalnego widoku został usunięty. Następnym niezależnym zakresem może
być TASK-0305, ale nie jest automatycznie rozpoczynany.
