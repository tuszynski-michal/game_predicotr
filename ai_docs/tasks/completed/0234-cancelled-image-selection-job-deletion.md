---
title: TASK-0234 cancelled image-selection job deletion
status: done
release: "0.5"
last_updated: 2026-08-11
---

# TASK-0234 — Usuwanie anulowanego joba selekcji zdjęć

## Goal

Pozwolić właścicielowi trwale usunąć niepotrzebny, anulowany job selekcji
zdjęć z zakładki `Joby`, bez naruszenia wynikowego folderu użytkownika,
współdzielonego stagingu albo danych przekazanych do importu.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`

## Outcome

Dodano mocno potwierdzane `DELETE /api/v1/admin/jobs/{jobId}` dostępne wyłącznie
dla anulowanego `image_selection`. API blokuje run przekazany dalej albo z
opublikowanym manifestem, zachowuje staging współdzielony z innym runem i nigdy
nie usuwa zewnętrznego katalogu wynikowego. Zarządzane katalogi są przenoszone
do kwarantanny przed zmianą bazy, przy błędzie transakcji przywracane, a po
commicie usuwane fizycznie. Panel wymaga przepisania ośmiu znaków identyfikatora
joba i po sukcesie usuwa go z listy.

Weryfikacja objęła Ruff, 35 skupionych testów API/domeny/security, OpenAPI,
typecheck klienta i Admina, 35 testów klienta oraz 192 testy Admina.
