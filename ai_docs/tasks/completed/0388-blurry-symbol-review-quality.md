---
title: TASK-0388 Blurry symbol review quality
status: done
last_updated: 2026-09-02
---

# TASK-0388 — Niewyraźny symbol w Weryfikacji symboli

## Goal

Dodać osobną akcję jakości `Niewyraźny`: symbol pozostaje rozpoznany i
logicznie zatwierdzony, ale jego bieżący crop nie może wejść do treningu.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Scope

- domenowa akcja `mark_blurry` i jakość `blurry`;
- migracja addytywna constraintów komórek, eventów i operacji masowych;
- bezpośrednie i masowe mutacje API;
- przycisk `Niewyraźny` po lewej stronie `Nieczytelny`;
- skrócenie etykiety `Nieczytelny symbol` do `Nieczytelny`;
- wspólny, jednoliniowy kontener akcji `Niewyraźny / Nieczytelny / Zła siatka`;
- badge oraz test wykluczenia z treningu.

## Invariants

- `blurry` wymaga aktywnego, rozpoznanego symbolu i stanu `approved`;
- przypisanie symbolu nie jest usuwane ani zmieniane;
- `blurry` nie trafia do kolejki nieczytelnych ani korekty siatki;
- każdy `quality_issue != NULL`, w tym `blurry`, wyklucza crop z treningu;
- ponowne jawne zatwierdzenie lub zmiana symbolu usuwa `blurry` zgodnie z
  istniejącą semantyką naprawy problemu jakości.

## Definition of Done

- akcja działa dla jednego i wielu zaznaczonych cropów;
- nieznany albo nieaktywny symbol jest odrzucany fail-closed;
- API, OpenAPI i klient Admina mają wspólny kontrakt;
- trzy akcje jakości są w jednej linii i we wskazanej kolejności;
- testy domeny, API, migracji i Admina przechodzą.

## Outcome

- Dodano niezależną jakość `blurry` i akcję `mark_blurry` dla mutacji
  bezpośrednich oraz masowych.
- Niewyraźny crop zachowuje zatwierdzony, aktywny symbol, lecz istniejący
  predykat `trainingEligible` wyklucza go z kohort uczenia.
- Admin pokazuje akcje `Niewyraźny`, `Nieczytelny`, `Zła siatka` w jednej
  linii, a karta niewyraźnego cropa otrzymuje osobny badge.
- Migracja `0089` rozszerza constrainty przez `NOT VALID`, bez pełnego skanu
  dużej tabeli podczas upgrade'u; downgrade jest fail-closed przy istniejących
  danych `blurry`.
- Testy domeny, API, migracji i Admina, OpenAPI, lint, typecheck oraz build
  produkcyjny przeszły pomyślnie.
