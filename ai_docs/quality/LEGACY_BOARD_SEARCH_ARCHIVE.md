---
title: Legacy board search archive acceptance
status: ready_cleanup_not_authorized
last_updated: 2026-09-07
---

# Odbiór niezależnego archiwum wyszukiwania

## Wynik

Zamrożone archiwum gry `777 v0.1` jest gotowe:

- gra: `80f3c7ec-6110-4e20-a263-2675ee5b15d6`;
- zakres: `45163–499995`;
- dokumenty: 369 554;
- fingerprint preview TASK-0502:
  `2250d49f71cd937218222dae3dd62f108ffd7cc5992f3eb4a315a69ad19d19e4`;
- fingerprint dokumentów źródłowych i archiwalnych:
  `7053d7ac8db72583fd930d66289a8951b2bdfba96f62be5e2ef5f8431e7f15ff`.

Każdy dokument przechowuje zwarty dowód symboli, status oraz bezpośrednią
ścieżkę i SHA-256 obrazu całej planszy. Nie ma relacji do review, recognized
board, importu lub joba. Istniejące, zweryfikowane pliki nie zostały skopiowane
ani przekodowane; archiwum przejmuje ich trwałą referencję i nie zwiększa
zajętości obrazów o kolejne 24,2 GiB.

## Sprawdzenie runtime

- wyszukiwanie starej gry zwróciło wynik `45170` w trybie `legacy_archive`, z
  trzema operacyjnymi UUID ustawionymi na `null`;
- checksum-bound asset `45170` zwrócił 66 769 B obrazu PNG;
- kontrolne wyszukiwanie nowej gry zwróciło `operational_review` wraz z
  bieżącym `reviewItemId`.

## Granica bezpieczeństwa

Nie wykonano żadnego cleanupu. Gotowe archiwum usuwa blokadę architektoniczną,
ale nie jest zgodą na usunięcie danych. Następny etap musi wygenerować nowy
preview, uzyskać jawne potwierdzenie użytkownika i wykluczyć wszystkie ścieżki
`legacy_board_search_archive_documents` z kwarantanny plików.
