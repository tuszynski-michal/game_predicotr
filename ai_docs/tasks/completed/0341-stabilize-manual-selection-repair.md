---
title: TASK-0341 Stabilize manual selection repair
status: done
version: 0.10
last_updated: 2026-08-30
---

# TASK-0341 — Stabilizacja korekty ręcznej selekcji

## Goal

Przywrócić pamięć pozycji obrazu we wszystkich lokalnych viewerach i usunąć
pełny rescan katalogu z gorącej ścieżki usuwania pojedynczej sekwencji.

## Scope

- wspólny viewer zwykłej selekcji, fill oraz delete;
- ochrona ostatniej pozycji przed przejściowym loading scroll event;
- inkrementalny snapshot po fill/delete/undo/restore;
- pojedyncza weryfikacja pełnego katalogu przy jego otwarciu;
- czytelna diagnostyka driftu checksummy output manifestu.

## Out of scope

- automatyczne przyjmowanie zmienionych JPEG-ów jako zaufanych;
- usunięcie jednopoziomowego przywracania;
- API, worker, OpenAPI i PostgreSQL.

## Outcome

- Pozycja viewportu nie jest już nadpisywana zerem w czasie wymiany Object URL
  i jest odtwarzana po załadowaniu kolejnego zdjęcia.
- Mutacja jednego pliku nie uruchamia `inspectRepairDirectory` dla całego
  katalogu. Checksuma celu, pending operation i oba manifesty pozostają
  obowiązkowe.
- Otwarcie katalogu wykonuje każdy pełny hash najwyżej raz zamiast dwukrotnie.
- Niezgodny historyczny plik pozostaje zablokowany do jawnej decyzji operatora.
