---
title: TASK-0260 numeric import order and concise reviewer labels
status: done
release: "0.7"
last_updated: 2026-08-22
---

# TASK-0260 — Numeryczna kolejność importów i czytelny wybór Reviewera

## Goal

Lista gotowych stagingów w `Import plansz` ma odzwierciedlać kolejność zakresów,
a wybór joba w `Zatwierdzaniu plansz` ma identyfikować import nazwą katalogu
zamiast skrótem technicznego ID.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- sortowanie nazw zaczynających się od `<liczba>-` rosnąco po pierwszej liczbie,
- stabilny fallback dla nazw bez zakresu,
- krótka data i godzina, nazwa katalogu oraz krótki status w dropdownie,
- pełne ID wybranego joba widoczne osobno,
- ograniczona szerokość i ellipsis wybranego tekstu.

## Out of scope

- zmiana kolejności wykonywania jobów,
- zmiana API, modelu danych albo nazw zapisanych stagingów,
- zmiana statusów domenowych importu.

## Acceptance criteria

- [x] `20000-99999` jest przed `100000-150000` niezależnie od daty uploadu.
- [x] Nazwy bez liczbowego prefiksu są deterministycznie za zakresami.
- [x] Dropdown pokazuje nazwę katalogu, a nie skrót ID.
- [x] Data używa krótkiego formatu z godziną, a status ma krótką etykietę.
- [x] Pełne ID wybranego joba jest widoczne osobno.
- [x] Testy Admina, typecheck, lint, format i build przechodzą.

## Outcome

Gotowe stagingi są sortowane po liczbowym początku zakresu z deterministycznym
fallbackiem. Wybór Reviewera pokazuje krótki czas, nazwę źródłowego katalogu i
krótki status, natomiast pełne ID znajduje się osobno pod kontrolką. Dodano
testy kolejności, etykiety oraz kontraktu launchera. Przeszło `227/227` testów
Admina, typecheck, ESLint, Prettier oraz produkcyjny build Admina.
