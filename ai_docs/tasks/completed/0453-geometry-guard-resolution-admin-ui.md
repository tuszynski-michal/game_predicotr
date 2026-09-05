---
title: Geometry guard resolution Admin workspace
status: done
version: v0.10.164
---

# Cel

Udostępnić operatorowi kompletny workspace rozliczenia plansz odroczonych przez
bramkę dużego importu oraz bezpiecznie przypiąć zamknięty manifest decyzji do
nowego browser-importu schema v7.

# Zakres

- audytowa rekonstrukcja raportu v1→v2 uruchamiana jawnie z karty importu,
- widok całego źródła z dziewięcioma numerowanymi slotami i wyróżnieniem
  wyłącznie pozycji wymagających decyzji,
- edytor pełnej siatki oraz częściowej siatki z maską niedostępnych komórek,
- dokładny podgląd 15 cropów bez utrwalania artefaktów przed importem,
- atomowe odrzucanie jednej lub wielu plansz z tego samego źródła,
- zamknięcie kompletnego manifestu oraz przekazanie jego ID i checksumy do
  nowego importu schema v7,
- blokada automatycznego retry, automatycznych decyzji i automatycznego startu.

# Poza zakresem

- rozliczenie ośmiu plansz za operatora,
- wznowienie albo mutowanie joba `86128f3c…`,
- zmiana progu 98%, algorytmu structured v3 albo danych gry,
- rozpoczęcie importu kolejnego katalogu.

# Relevant docs

- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md` (D-339, D-341)
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0450-pre-import-geometry-guard-decisions.md`
- `ai_docs/tasks/completed/0451-schema-v7-geometry-guard-resolution-import.md`
- `ai_docs/tasks/completed/0452-legacy-geometry-guard-report-reconstruction.md`

# Definition of Done

- operator widzi wszystkie dziewięć slotów źródła i dokładnie te pozycje,
  które wymagają rozliczenia,
- pełna i częściowa korekta pokazują końcowy podgląd cropów, a pola częściowe
  są zapisywane jako `source_unavailable`, nie jako sztuczne cropy,
- zbiorcze odrzucenie działa atomowo tylko w obrębie jednego źródła,
- manifest można zamknąć dopiero po rozliczeniu całej kolejki,
- nowy import przekazuje ID i checksumę zamkniętego manifestu schema v7,
- failed job pozostaje niezmieniony i żaden import nie startuje automatycznie,
- skoncentrowane testy API i Admina, Ruff, OpenAPI oraz typecheck są zielone,
- dokumentacja i `CURRENT_STATE.md` opisują dostarczone zachowanie.

# Outcome

- Kolejka zwraca pełny kontekst slotów źródła, a Admin wyróżnia wyłącznie cele
  `deferred`. Historyczny raport v1 można jawnie odtworzyć i obserwować jako
  osobny job bez retry źródłowego importu.
- Dodano edytor quada siatki 3×5, maskę pojedynczych pól/rzędów/kolumn dla
  planszy częściowej, atomowe odrzucanie wielu slotów jednego źródła oraz
  przejściowy podgląd 15 cropów A/B. Podgląd weryfikuje JPEG przez rozmiar i
  SHA-256, renderuje w pamięci i nie zapisuje artefaktów.
- Zamknięcie manifestu jest możliwe tylko przy zerze nierozliczonych pozycji.
  Panel przekazuje jego ID i checksumę do jawnego startu schema v7; zapis nowej
  rewizji unieważnia wybrany manifest w stanie UI.
- Weryfikacja: 10 skoncentrowanych testów API, 12 testów workera bramki i
  manifestu, 50 testów produkcyjnego workflow oraz pełne 402 testy Admina są
  zielone. Ruff, ESLint, typecheck klienta/Admina, OpenAPI check i produkcyjny
  build Admina zakończyły się sukcesem. Skoncentrowany mypy domeny/aplikacji
  przeszedł; pełniejszy mypy nadal raportuje istniejące braki `py.typed` i
  wcześniejsze błędy w niezmienionych modułach.
- Nie uruchomiono rekonstrukcji, nie zapisano decyzji dla ośmiu plansz, nie
  zamknięto manifestu i nie utworzono nowego importu na danych użytkownika.
