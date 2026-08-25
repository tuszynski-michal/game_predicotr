---
title: TASK-0255 reviewer launch and resolution recovery
status: done
release: "0.7"
last_updated: 2026-08-21
---

# TASK-0255 — Odzyskiwanie otwarcia i zapisu Reviewera

## Goal

Lokalny Reviewer opuszcza kartę `about:blank` natychmiast po otrzymaniu
poprawnego adresu, a niejednoznaczna odpowiedź zapisu online nie pozostawia
przycisku `Zatwierdź` bezterminowo wyłączonego.

## Context

- Admin otwiera synchronicznie `about:blank`, ale przed nawigacją czeka na
  dodatkowe odświeżenie overview. Zawieszone odświeżenie pozostawia pustą kartę,
  mimo że API zwróciło już właściwy lokalny URL.
- Reviewer nie ogranicza czasu oczekiwania na POST decyzji. Jeśli zapis dotrze
  do API, lecz odpowiedź zginie w tunelu, `isSaving` pozostaje aktywne bez
  końca.
- Rzeczywisty zapis online z 2026-08-21 14:55:47 UTC został potwierdzony w
  `image_review_resolution_events` i `image_review_items`; problem dotyczy
  odzyskania odpowiedzi klienta, nie utraty decyzji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- nawigować przygotowane okno lokalne przed pomocniczym odświeżeniem overview,
- pokazać kontrolowany fallback, jeśli nawigacja nowego okna się nie powiedzie,
- ograniczyć czas pojedynczej próby zapisu decyzji Reviewera,
- po timeoutcie powtórzyć dokładnie tę samą idempotentną komendę jeden raz,
- po drugim timeoutcie odblokować UI i pokazać informację o możliwym przyjęciu
  zapisu oraz potrzebie ponowienia/odświeżenia,
- dodać regresje Admina i Reviewera oraz zaktualizować dokumentację.

## Out of scope

- zmiana modelu assignmentów, sesji, bazy albo API/OpenAPI,
- automatyczne zatrzymywanie aktywnego udostępnienia,
- zmiana Quick Tunnel, limitu trzech prac albo kolejności review,
- ponowne zapisywanie lub usuwanie istniejącej decyzji użytkownika.

## Acceptance criteria

- [x] Poprawny lokalny URL jest ustawiany w przygotowanym oknie przed
      odświeżeniem overview.
- [x] Błąd nawigacji pozostawia widoczny, ręczny link i komunikat zamiast
      bezczynnej karty `about:blank`.
- [x] Zapis online nie może utrzymywać `isSaving` bez limitu czasu.
- [x] Pierwszy timeout wykonuje jedno ponowienie z tym samym kluczem
      idempotencji i pełną, niezmienioną komendą.
- [x] Sukces retry jest obsługiwany jak zwykły sukces, bez podwójnej rewizji.
- [x] Drugi timeout odblokowuje UI i pokazuje niejednoznaczny stan bez
      twierdzenia, że zapis na pewno nie powstał.
- [x] Istniejący zapis online pozostaje zachowany; brak migracji i mutacji
      operatorskich.
- [x] Testy Admina i Reviewera, lint, typecheck, build oraz formatowanie
      zmienionych aplikacji przechodzą.

## Expected files

- `apps/admin/src/features/reviewer-access/reviewer-access-launcher.tsx`
- `apps/admin/test/reviewer-access-launcher-contract.test.mjs`
- `apps/reviewer/src/features/operational-reviews/operational-review-actions.ts`
- `apps/reviewer/test/operational-review-actions.test.mjs`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/CURRENT_STATE.md`

## Outcome

- Lokalny launcher nawiguje przygotowane okno natychmiast po otrzymaniu URL, a
  odświeżenie overview jest pomocnicze i nieblokujące. Kontrolowany fallback
  pokazuje ręczny link po błędzie nawigacji.
- Reviewer ogranicza każdą próbę zapisu do 12 sekund i wykonuje najwyżej jedno
  automatyczne ponowienie dokładnie tej samej komendy oraz klucza idempotencji.
  Po drugim timeoutcie zwraca stan niejednoznaczny, dzięki czemu workspace
  zwalnia blokadę zapisu.
- Testy regresyjne potwierdzają kolejność nawigacji, identyczność retry, sukces
  idempotentnego odzyskania i kontrolowane zakończenie dwóch timeoutów.
- Przeszły: Admin `222/222`, Reviewer `35/35`, typecheck i produkcyjne buildy
  obu aplikacji, ESLint bez błędów i Prettier. Działające procesy nie zostały
  przerywane podczas implementacji.
