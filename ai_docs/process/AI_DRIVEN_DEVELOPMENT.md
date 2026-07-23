---
title: AI Driven Development workflow
status: active
last_updated: 2026-07-23
---

# Proces AI Driven Development

## Cel

Model AI ma otrzymywać mały, jednoznaczny kontekst, wykonać ograniczone zadanie, zweryfikować wynik i pozostawić dokumentację w stanie pozwalającym kontynuować pracę w nowej sesji.

## Jednostka pracy

Jednostką pracy jest plik zadania utworzony z `TASK_TEMPLATE.md`.

Dobre zadanie:

- ma jeden rezultat,
- wskazuje dokumenty źródłowe,
- podaje zakres i poza zakresem,
- ma mierzalne kryteria akceptacji,
- zawiera komendy weryfikacyjne,
- zwykle mieści się w jednym pull requeście.

## Cykl iteracji

### 1. Select

Wybierz następne zadanie zgodne z `CURRENT_STATE.md` i aktywnym milestone'em.

### 2. Read

Przeczytaj tylko:

- `AGENTS.md`,
- `CURRENT_STATE.md`,
- aktywne zadanie,
- dokumenty z `Relevant docs`.

### 3. Plan

Agent zapisuje krótki plan w zadaniu lub raporcie. Jeżeli odkryje sprzeczność, zatrzymuje implementację części zależnej i aktualizuje `Open questions` albo `Decision log`.

### 4. Implement

Małe zmiany, testy razem z kodem, brak nieuzasadnionego refaktoru.

### 5. Verify

Uruchom odpowiednie komendy. Nie oznaczaj zadania jako done, jeżeli testy nie zostały uruchomione. Brak możliwości uruchomienia testu musi być jawny.

### 6. Document

Zaktualizuj:

- wymagania, jeśli zmieniło się zachowanie,
- architekturę, jeśli zmieniła się struktura,
- OpenAPI/data model, jeśli zmienił się kontrakt,
- Decision Log, jeśli podjęto istotną decyzję,
- Current State zawsze.

### 7. Handoff

Raport końcowy ma umożliwić nowej sesji rozpoczęcie bez odtwarzania historii czatu.

## Praca z niejasnościami

### Założenie lokalne

Można przyjąć, gdy:

- jest łatwo odwracalne,
- nie zmienia publicznego API ani modelu danych,
- jest zapisane w zadaniu.

### Decyzja architektoniczna

Wymaga Decision Log, gdy:

- wpływa na kilka modułów,
- zmienia dane lub wdrożenie,
- wprowadza nową technologię,
- jest kosztowna do odwrócenia.

### Pytanie produktowe

Nie powinno być rozstrzygane przez AI, gdy dotyczy zasad gry, znaczenia wyniku lub oczekiwanego zachowania użytkownika.

## Dokumentowanie zmian

Nie twórz dziennika każdej drobnej edycji. Decision Log przechowuje tylko istotne wybory. `CURRENT_STATE.md` przechowuje stan teraz, a historia kodu przechowuje szczegóły implementacji.

## Zalecany prompt zadaniowy

```text
Wykonaj zadanie ai_docs/tasks/XXXX-name.md zgodnie z AGENTS.md.
Najpierw przeczytaj wskazane Relevant docs. Nie rozszerzaj zakresu.
Po implementacji uruchom weryfikację, zaktualizuj Outcome i CURRENT_STATE.md.
```

## Antywzorce

- „Zbuduj całą aplikację na podstawie wszystkich dokumentów”.
- Implementowanie admina, forecastu i OCR w jednym zadaniu.
- Traktowanie istniejącego kodu jako jedynej prawdy.
- Dodawanie technologii tylko dlatego, że są popularne.
- Kopiowanie typów API ręcznie do kilku aplikacji.
- Ukrywanie nieuruchomionych testów.
- Aktualizowanie dokumentacji bez aktualizacji implementacji lub odwrotnie.
