---
title: TASK-0348 — Widoczny postęp browser uploadu
status: done
version: 0.10
---

# TASK-0348 — Widoczny postęp browser uploadu

## Cel

Zapobiec sytuacji, w której duży lokalny upload poprawnie zapisuje tysiące
JPEG-ów, lecz Admin przez cały czas pokazuje `0/N`.

## Diagnoza

Staging `b167c5ea-27d7-4403-aa49-9444990fdad3` przy pozornym stanie `0/2550`
faktycznie rósł na dysku, zakończył się wynikiem `2550/2550` i uruchomił
preflight. Problem dotyczył odmalowania postępu, nie transportu ani API.

## Outcome

- licznik korzysta z serwerowego potwierdzenia liczby plików;
- klient oddaje sterowanie po pierwszym potwierdzeniu i potem co 25 plików;
- test akcji uploadu sprawdza przekazanie potwierdzonego postępu;
- kontrakt panelu chroni mechanizm jawnego yieldowania.
