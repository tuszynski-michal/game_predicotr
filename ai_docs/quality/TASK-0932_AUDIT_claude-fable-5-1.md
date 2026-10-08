---
title: TASK-0932 — audyt niezależny (claude-fable-5-1 / high)
status: accepted
last_updated: 2026-10-08
---

# TASK-0932 — audyt: ewaluator `payout-v4-wild-count`

Audytor: niezależny subagent claude-fable-5-1 / high, świeży kontekst, tylko
odczyt (zamiennik audytu gpt-6.1-sol do czasu dostępności CLI, D-535).
Wykonawca: claude-opus-5-5 / high. Zakres: zmiany niezacommitowane względem
v1.7.269 (dc436a3f) w worktree `mumie-super-game`.

## Werdykt

PASS. Brak P0 i P1. Cztery znaleziska P2, naprawione przez wykonawcę w jednej
rundzie poprawek przed commitem. Cztery odstępstwa zaakceptowane.

## Znaleziska P2 (naprawione)

1. Odrzucanie `rulesVersionId` w publicznym panelu zarządzania sprawdzało
   tylko dokładny klucz. Naprawione: wspólna stała `RULES_VERSION_QUERY_NAMES`
   (`rulesversionid`, `rules_version_id`, bez względu na wielkość liter)
   używana przez obie trasy publiczne; test 6 żądań → 422.
2. Outcome nie wymieniał dwóch istniejących wcześniej błędów testów
   kontraktowych Reviewera i miał nieaktualną notatkę o `test_management.py`.
   Naprawione.
3. Nieużywana stała `APPROXIMATE_WIN_PAYOUT_ALGORITHM_VERSION`. Usunięta.
4. `API_CONTRACT.md` sugerował, że brak rozbicia na sztuki dotyczy tylko
   zamrożonej historii panelu zarządzania; dotyczy całego panelu (format v1).
   Doprecyzowane, zaakceptowane do czasu formatu v2.

## Odstępstwa wykonawcy (zaakceptowane)

1. Brak prekomputacji v4 (job wypłat, `layout_payouts`, snapshot mobilny):
   strażnik `PAYOUT_ALGORITHM_GAME_MISMATCH` odrzuca job v2/v3 dla gry z
   symbolem uruchamiającym; `create_payout_job` nadal przyjmuje tylko v3.
   Dla 777 strażnik nigdy nie działa. Jawny follow-up (mobile poza zakresem).
2. Publiczny szczegół planszy niesie `countMatches` (ta sama klasa danych co
   `matches`; rekordy weryfikacji nadal tylko przez schemat publiczny).
3. `countMatches` w wierszach przybliżonej wygranej opcjonalne (domyślnie
   `[]`), bo zapisane wyniki panelu zarządzania (format v1) nie mają rozbicia;
   skrót treści snapshotów 777 bez zmian (test), wypłata wiersza zawiera sztuki.
4. Nowy ewaluator TS `packages/shared-ts/src/payout.ts` z testem na wszystkich
   złotych przypadkach; semantyka lustrzana z Pythonem; typecheck mobile PASS.

## Sprawdzone bez uwag

- Semantyka: symbole uruchamiające poza liniami; Wild bez zmian; sztuki =
  największa reguła ≤ liczbie sztuk, komórki `0` nigdy nie liczone; suma
  linie + sztuki; wersja per gra (`payout-v3-unknown-prefix-stop` bez
  triggera, wyniki i wersja identyczne jak przed taskiem; `payout-v4-wild-count`
  z triggerem). Walidacja reguł sztuk `2..rows×columns`, ściśle rosnące,
  bez wymogu kompletu; trigger z minimum odrzucony.
- Złote przypadki: 10 nowych przeliczonych ręcznie (w tym przykład z taska:
  10×4 + K×3 + A×4 + 3 sztuki = 70), przypadki 777 nietknięte, oba języki
  iterują po nowej sekcji.
- Pion API: `countMatches` w szczególe planszy i wierszach; `BoardPayoutKind`
  z uwzględnieniem sztuk; `rulesVersionId` tylko dla tej samej gry
  (`draft`/`published`, 404 przy nieznanej); udostępnienie 422, panel
  publiczny 422, proxy Reviewera 403; `openapi:check` aktualne.
- UI: select „Wersja reguł” tylko przy źródle z `listRulesVersions` (Admin);
  sekcja „Sztuki na planszy” z podświetleniem komórek; „w tym sztuki” w
  wierszu; „Wild” zamiast „joker”; dwa testy interakcji.
- Dokumenty ALGORITHMS §B/§D, API_CONTRACT, ADMIN_APP, DATA_MODEL spójne;
  instrukcja operatora testu Wilda na drafcie kompletna.

## Testy uruchomione przez audytora

- Worker (payout, batch, readiness, snapshot): 88 PASS. API (detail,
  approximate win domena i API, share public, management stakes,
  management): 101 PASS. shared-ts 46/46; board-search-ui 80/80 i
  interakcje 51/51; admin-api-client 102/102; `openapi:check` aktualne;
  Admin 679/679 i typecheck; Reviewer typecheck PASS, testy 235/237 (dwa
  błędy kontraktowe sprzed taska); mobile typecheck PASS;
  `fixture:validate` ok; ruff i `mypy --strict` na zmienionych modułach
  czyste poza znanym `main.py:2005`.
- Po rundzie poprawek (wykonawca): 40 PASS w zestawie publicznym, ruff/mypy
  czyste, `openapi:check` aktualne.

Przegląd statyczny, bez zmian plików przez audytora.
