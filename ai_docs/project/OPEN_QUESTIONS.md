---
title: Open product and architecture questions
status: active
last_updated: 2026-07-29
---

# Otwarte pytania

Ten dokument zawiera wyłącznie pytania, które nadal wymagają odpowiedzi.

Q-001–Q-015 oraz Q-018 zostały rozstrzygnięte. Obowiązujące decyzje znajdują
się w [Decision Log](../process/DECISION_LOG.md), a dokładny zapis odpowiedzi
właściciela w
[ukończonym Task 0001](../tasks/completed/0001-architecture-clarification.md).

## Obraz i import

### Q-016 — Stabilność układu strony

**Status: closed 2026-07-28.** Strona ma maksymalnie dziewięć mini-layoutów
w siatce 3 × 3. Ostatnia strona ciągu może zawierać mniej pozycji, ponieważ
liczba layoutów gry nie musi być podzielna przez dziewięć. Pozycje występują
bez luk od indeksu 0 w kolejności row-major. Pełna strona nadal wymaga
dziewięciu pozycji.

### Q-017 — Zestaw treningowy

**Status: closed 2026-07-28.** Właściciel potwierdził możliwość zebrania około
100 przykładów na symbol. Obecne 43 zdjęcia obejmują 387 layoutów i 5805
automatycznie utworzonych cell crops. Właściciel nie wycina ich ręcznie;
manualna praca dotyczy zatwierdzenia lub korekty etykiety. Podział
train/validation/test nadal odbywa się według zdjęcia źródłowego.

## Administracja i wdrożenie

### Q-019 — Wielu administratorów

**Status: closed 2026-07-29.** Lokalny panel początkowo obsługuje właściciela,
ale docelowo zdalny moduł review ma umożliwić pracę co najmniej jednej innej
osobie. Każda decyzja musi mieć aktora, sesję, append-only audyt i optimistic
revision. Zdalny recenzent ma dostęp wyłącznie do wskazanej gry i review, nie do
pełnej administracji.

### Q-021 — Transport zdalnego review

**Status: closed 2026-07-30.** Dla czasowego zdalnego review v0.1 wybrano
Cloudflare Quick Tunnel do publicznego originu samej aplikacji Reviewer.
Połączenie jest wychodzące, używa losowego adresu HTTPS i nie otwiera portu
routera. API, Admin i PostgreSQL pozostają na loopback. Tryb nie ma SLA i służy
testom/pilotowi; stały adres wymaga później named tunnel.

### Q-020 — Aplikacja referencyjna

Czy istnieje zgoda właściciela aplikacji Windows na analizę jej zachowania, plików i ruchu sieciowego? Bez zgody prace należy ograniczyć do obserwacji funkcji, dostarczonych zdjęć i ręcznego tworzenia specyfikacji.

## Warunek rozpoczęcia etapów

- M1 nie ma otwartych pytań blokujących.
- Techniczne decyzje toolchain/build podejmowane w M1.1 nie wymagają odpowiedzi
  produktowej, ale muszą zostać zapisane w Decision Log.
- Q-016/Q-017 są zamknięte. D-057 dopuszcza M6 na przejrzanych goldenach i
  automatycznych cropach, przy OCR pozostającym w trybie manual-review-only.
- M2 i lokalny M6.5 mogą używać panelu właściciela na loopback. Q-019 jest
  zamknięte; zdalna autoryzacja wielu recenzentów należy do M8.7 i wymaga
  rozstrzygnięcia Q-021.
- Analiza aplikacji referencyjnej poza obserwacją wymaga odpowiedzi na Q-020.
