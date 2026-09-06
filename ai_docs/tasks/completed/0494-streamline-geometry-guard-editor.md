---
title: Streamline geometry guard editor
status: done
version: v0.10.209
---

# Cel

Uprościć workspace `Rozlicz problematyczne plansze`, aby widoczna siatka na
pełnym zdjęciu była wystarczającą podstawą jawnego zapisu korekty.

# Zakres

- usunąć frontendowy obowiązek oraz widok podglądu 15 cropów A/B,
- usunąć boczną listę `Plansze na zdjęciu`; wybór odbywa się na overlayu,
- wykorzystać odzyskaną szerokość dla zdjęcia,
- umieścić małe kontrolki decyzji bezpośrednio pod viewerem,
- umieścić `Zapisz decyzję` obok `Następne zdjęcie`,
- zachować osobne szkice plansz oraz zasadę, że nawigacja nie zapisuje.

# Poza zakresem

- zmiana kontraktu decyzji, manifestu lub workera,
- usunięcie diagnostycznego endpointu preview z API,
- zmiana detektora albo croppera,
- automatyczne uruchomienie importu.

# Relevant docs

- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0493-multi-board-geometry-guard-editing.md`

# Testy

- zapis pełnej i częściowej korekty nie wymaga wywołania preview,
- boczna lista plansz i panel A/B nie są renderowane,
- overlay nadal wybiera każdą planszę i zachowuje szkice,
- decyzja jest pod viewerem, a zapis i następne zdjęcie są obok siebie,
- następne zdjęcie nie wywołuje zapisu.

# Definition of Done

- operator może zapisać widoczną korektę bez komunikatu o podglądzie A/B,
- zdjęcie zajmuje całą dostępną szerokość,
- małe radio buttony znajdują się pod zdjęciem,
- akcje zapisu i przejścia dalej znajdują się obok siebie,
- testy Admina, lint, typecheck, format zmienionych plików i build są zielone,
- dokumentacja opisuje uproszczoną granicę zapisu.

# Outcome

- Usunięto frontendowy obowiązek i galerię podglądu 15 cropów A/B. Widoczny
  quad na pełnym zdjęciu można zapisać bez dodatkowego requestu preview.
- Usunięto boczną listę `Plansze na zdjęciu`; obraz wykorzystuje pełną
  szerokość, a każdy slot nadal wybiera się bezpośrednio na overlayu.
- Minimalistyczne radio buttony decyzji znajdują się pod viewerem. Tryb
  częściowy nadal udostępnia dokładną maskę piętnastu pól.
- `Zapisz decyzję` i `Następne zdjęcie` znajdują się obok siebie. Pierwsza
  akcja zapisuje wszystkie zmienione szkice źródła, druga wyłącznie nawiguje.
- Diagnostyczny endpoint preview pozostaje kompatybilny, ale Admin go nie
  wywołuje w tym workflow.

## Weryfikacja

- skoncentrowane testy kontraktu UI: 16/16,
- pełne testy Admina: 419/419,
- lint Admina: bez błędów,
- typecheck Admina: bez błędów,
- produkcyjny build Admina: zakończony poprawnie,
- Prettier dla zmienionych plików: bez różnic.
