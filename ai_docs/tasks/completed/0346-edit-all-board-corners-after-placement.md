---
title: TASK-0346 — Edycja wszystkich narożników po wyznaczeniu plansz
status: done
version: 0.10
---

# TASK-0346 — Edycja wszystkich narożników po wyznaczeniu plansz

## Cel

Po osobnym wyznaczeniu dziewięciu plansz umożliwić natychmiastowe dopasowanie
każdego z 36 narożników, bez ograniczenia edycji do pierwszej planszy.

## Zakres

- bezstratnie mapować dziewięć quadów na 36 niezależnych punktów siatki;
- po ukończeniu planszy 9 automatycznie włączyć wszystkie uchwyty;
- udostępnić ten sam zakres jako `Wszystkie plansze — 36 narożników`;
- zachować bieżące obrysy także przy późniejszym przełączeniu na ten zakres;
- nie zmieniać API ani kontraktu dziewięciu finalnych quadów.

## Outcome

- Po ostatnim kliknięciu widoczne są uchwyty wszystkich plansz.
- Każdy narożnik można przesunąć niezależnie, a zapis nadal przekazuje dokładnie
  dziewięć quadów w kolejności row-major.
- Test round-trip potwierdza brak przesunięcia współrzędnych podczas konwersji
  quady → 36 punktów → quady.
