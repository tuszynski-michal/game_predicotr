---
title: TASK-0368 — exact proof zakresu z trzech numerów środkowego rzędu
status: done
release: "0.10"
last_updated: 2026-09-01
---

# TASK-0368 — exact proof zakresu z trzech numerów środkowego rzędu

## Goal

Zbudować niezależny od runtime joba, Paddle, SQL i pipeline'u plansz komponent
lokalizujący trzy pełne etykiety środkowego rzędu oraz dopuszczający wynik
`exact` wyłącznie po dopasowaniu trzech odczytów do jednego wpisu
`ExpectedRangeTable`.

## Scope

- kanonizacja EXIF wykonywana dokładnie raz;
- `ExpectedRangeTable` dla pełnych i częściowych stron;
- wersjonowany `MiddleRowTripleLocator` i opcjonalny locked prior;
- grupowanie komponentów w pełne etykiety, source-resolution crops oraz
  kompletność cropów;
- konserwatywne metryki lokalnej czytelności;
- jeden wersjonowany profil preprocessing OCR;
- exact/unknown observations, reason codes i fingerprint komponentu v4.1.

## Out of scope

- produkcyjny Paddle adapter i batching;
- orientacja runu po EXIF;
- integracja z jobem, groupingiem, checkpointem i API;
- zmiana bieżącego fingerprintu nowych runów;
- board detection, geometria, symbole, segmentacja i trwałe cropy.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `.runtime/plans/plan_ocr_srodkowy_rzad_v4_1.md`

## Acceptance

- fast path wytwarza maksymalnie trzy cropy OCR na źródło;
- cropy pochodzą bezpośrednio ze skanonizowanego obrazu źródłowego;
- niejednoznaczny lattice, niepełny lub przycięty crop i słaba czytelność dają
  stabilny wynik unknown;
- exact proof nie używa fuzzy matching i pasuje do dokładnie jednego expected
  range;
- częściowa strona bez pełnych trzech slotów środkowego rzędu nie jest exact;
- locator nie zależy od Paddle, a resolver nie zależy od SQL;
- v1–v3 i ich fingerprinty pozostają niezmienione.

## Known input limitation

Plan wymaga 19-klatkowej checksum-bound challenge sequence, ale jej pliki nie
są dostępne w bieżącym środowisku. Brak materiału nie może być zastąpiony
fałszywym wynikiem. Pełny challenge acceptance pozostaje bramką TASK-0370.

## Outcome

- Dodano czysty `ExpectedRangeTable`, exact resolver oraz stabilne wyniki
  `exact | unknown`; trzy odczyty muszą być kolejne, numeryczne, wystarczająco
  pewne i pasować do jednego oczekiwanego zakresu bez fuzzy correction.
- Dodano jednokrotną kanonizację EXIF i wersjonowany locator. Bounded thumbnail,
  grupowanie pełnych etykiet oraz afiniczna siatka 3×3 obsługują pochylenie;
  drugie przejście może rozszerzyć tylko dolną granicę ROI z `0.48` do `0.60`.
- Locator wycina dokładnie trzy cropy bezpośrednio z obrazu źródłowego i przed
  przyszłym OCR sprawdza kompletność, lokalne rozmycie oraz kontrast. Nie zależy
  od Paddle, geometrii plansz ani klasyfikacji symboli.
- Na dostępnym rzeczywistym pliku o SHA-256
  `5d9ece174edb587dbd8da160185d6babaf486d02ed5d2ef13c664228620dc4fc`
  znaleziono kompletne środkowe etykiety przy aktywnym bounded rozszerzeniu ROI.
  Nazwa `seq_21169-21177.jpg` nie uczestniczyła w lokalizacji ani dowodzie.
- `41` skoncentrowanych testów domeny/lokatora oraz `39` testów regresyjnych
  historycznego range-only OCR, schedulera, kontraktów i joba przechodzi.
  Ruff i mypy dla nowych modułów przechodzą.
- Pełna 19-klatkowa challenge sequence pozostaje niedostępna. Nie została
  zastąpiona sztucznym wynikiem i nadal jest bramką odbioru TASK-0370.
