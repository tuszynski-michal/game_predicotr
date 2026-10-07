---
title: Jedna akcja zapisu i zatwierdzenia symbolu
status: completed
last_updated: 2026-10-07
---

# Jedna akcja zapisu i zatwierdzenia symbolu

## Stan obecny i cel

Użytkownik zgłasza pomyłki między `Zatwierdź` i `Zastosuj zmianę` w głównej
Weryfikacji symboli. Zleca połączenie ich w jeden zapis. Backend już obsługuje
`reassign_symbol_cell_review`: wybranie aktywnego symbolu, także identycznego
z bieżącym, zatwierdza aktualny crop oraz nadaje pochodzenie HUMAN.

Sprawdzone punkty wejścia:
`apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx` —
`SymbolReviewSelectionToolbar`, `previewOperation`, `handleKeyboardShortcut`;
`services/api/src/game_predictor_api/domain/image_symbol_reviews.py` —
`reassign_symbol_cell_review`. Zapis pojedynczy i masowy już korzystają z
tego samego kontraktu. Rozszerzenie API ani migracja nie są potrzebne.

## Reguły i zakres

- Jedyny podstawowy przycisk to `Zapisz i zatwierdź`; selektor nosi nazwę
  `Symbol do zatwierdzenia`. Operator wskazuje aktywny symbol, także bieżący.
  Brak symbolu lub zaznaczenia blokuje przycisk.
- Wybrany symbol zawsze trafia do istniejącej akcji `reassign`. Ten sam symbol
  przenosi pending do approved, inny atomowo poprawia i zatwierdza. Nie trzeba
  tymczasowo wybierać błędnej klasy. Zmiana filtrów nadal resetuje wybór celu.
- Dotyczy wszystkich gier tego workspace; nie dodajemy alternatywnej akcji
  `approve` ani zależności od profilu Mumii. Osobny wybór grafiki pozostaje.
- `Niewyraźny` zachowuje `mark_blurry` z celem i wyłączenie z treningu.
  Outside zachowuje logiczny zapis bez tworzenia cropa; wybór grafiki i
  niewyraźności pozostają zablokowane bez pikseli.
- Jeden target korzysta z szybkiego zapisu. Wiele targetów zachowuje preview,
  trwały job, idempotencję, kontrolę rewizji i zamrożenie strony. Enter wywołuje
  tę samą akcję; komunikaty mówią o zapisie i zatwierdzeniu.
- Nie wykonujemy decyzji na danych użytkownika, treningu, aktywacji, migracji,
  cleanupu, zmiany kolejności plansz ani merge/push.

## TASK-0894 — połączenie akcji zapisu

Zadanie: [0894-symbol-review-unified-save.md](../tasks/completed/0894-symbol-review-unified-save.md).
Zmienić toolbar oraz copy w istniejącym workspace. Zaktualizować regresje
interakcji i kontraktu UI. Sprawdzić istniejące testy domeny zatwierdzania.
Uzupełnić wymagania, opis kontraktu, instrukcję i inventory. Osobny commit
po audycie; dokument ukończonego taska przenieść do `completed/`.

## Odbiór i ryzyka

Scenariusze: brak wyboru blokuje zapis; ten sam symbol zatwierdza bez zmiany
klasy; inny symbol poprawia i zatwierdza; wiele cropów zachowuje preview oraz
zamrożenie; skróty, outside, niewyraźność i zmiana gry zachowują zabezpieczenia.
Testy interakcji korzystają z pamięciowego klienta, bez zapisów MAIN.
Odbiór przeglądarkowy jest odczytem UI, bez uruchomienia prawdziwej decyzji.

Najpierw focused testy, potem scoped format/lint/typecheck, następnie Admin
build. Każdy krok ma timeout 120 s; znany build można wydłużyć dopiero po
poinformowaniu użytkownika. Wyniki zapisuje Outcome; plan nie deklaruje
uprzednio zaliczonych testów.

## Wynik

TASK-0894 wykonany. Jeden zapis obsługuje zatwierdzenie obecnej klasy i korektę
na inną klasę. Testy domeny 32/32, interakcji 12/12 i Admina 40/40 zaliczone;
scoped format/lint/types oraz build Admina zaliczone. Kontrola przeglądarkowa
potwierdziła nowy przycisk bez zapisu do danych użytkownika. Szczegóły,
ograniczenia i wersję commita zawiera Outcome zadania.

## TASK-0895 — czyszczenie symbolu po każdej próbie zapisu

Zadanie: [0895-symbol-review-clear-save-target.md](../tasks/completed/0895-symbol-review-clear-save-target.md).
Użytkownik doprecyzował, że kolejny zapis zawsze wymaga ponownego wyboru
symbolu. `previewOperation` przechwytuje cel, następnie czyści selektor przed
wysłaniem pojedynczej decyzji lub przygotowaniem podglądu masowego. Enter
korzysta z tego samego wejścia. Podgląd/job zachowuje przechwycony cel; błąd
lub anulowanie nie przywraca starego wyboru. Inne akcje pozostają bez zmian.
Testy interakcji sprawdzają pierwszy i kolejny zapis, Enter bez celu, błędy,
anulowanie, blurry/outside oraz niezmieniony cel operacji masowej. Scoped
format/lint/types i build potwierdzają jakość; wyniki uzupełni Outcome.
Nie wykonujemy testowej decyzji na danych użytkownika.

TASK-0895 wykonany. Testy interakcji 13/13 oraz kontraktów/helperów 40/40
zaliczone. Scoped format/lint/types i build Admina zaliczone. Outcome zawiera
szczegóły; nie zmieniono kontraktu ani danych użytkownika.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
| --- | --- | --- | --- | --- |
| TASK-0894 | gpt-6.1-sol | high | Zmiana jednego workflow UI z istniejącym kontraktem; sprawdzenie semantyki tego samego symbolu i ochrony cropów. | Audyt własny diffu i testów; bez delegowania. |
| TASK-0895 | gpt-6.1-sol | high | Mała zmiana stanu UI; sprawdzenie przechwycenia celu i kolejnych zapisów bez ingerencji w kontrakt. | Audyt własny diffu i regresji; bez delegowania. |
