---
title: Secure ingress runbook and remote end-to-end acceptance
status: in_progress
last_updated: 2026-07-31
---

# TASK-0115 — Secure ingress runbook and remote end-to-end acceptance

## Status

`in_progress`

## Goal

Udostępnić osobie na innym urządzeniu bezpieczny link HTTPS do samego Reviewera
i potwierdzić pełny zdalny scenariusz bez otwierania surowego portu routera.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/delivery/MILESTONE_08_EXECUTION_PLAN.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- wyniki `TASK-0113` i `TASK-0114`

## Scope

- skonfigurować zaakceptowany tunel HTTPS albo VPN,
- zachować lokalny loopback jako tryb domyślny,
- dodać kontrolowane start/stop/status i rotację adresu,
- umożliwić uruchomienie produkcyjnego Reviewera i tunelu jednym przyciskiem
  Admina oraz zatrzymanie publicznej ekspozycji drugim przyciskiem,
- opisać generowanie linku, oddzielne przekazanie kodu i odwołanie sesji,
- przeprowadzić test z urządzenia poza domową siecią,
- sprawdzić brak ekspozycji Admin, PostgreSQL i pozostałych endpointów.

## Out of scope

- chmura aplikacyjna, Google Play i publiczny backend,
- surowy port forwarding,
- stałe udostępnienie pełnej administracji.

## Acceptance criteria

- [ ] Reviewer działa przez HTTPS z urządzenia w zewnętrznej sieci,
- [ ] niepoprawny lub wygasły kod nie ujawnia danych,
- [ ] zdalny użytkownik widzi tylko wskazaną grę/import,
- [ ] odwołanie sesji działa natychmiast,
- [ ] skan ekspozycji nie wykazuje Admin, bazy ani nieobjętych endpointów,
- [x] runbook zawiera start, stop, status, odzyskanie i reakcję na incydent,
- [x] Admin ma typowane przyciski start/stop, jawny stan i publiczny URL,
- [x] start blokuje serwer developerski i nie przyjmuje dowolnej komendy,
- [x] lokalny tryb po wyłączeniu ingress nadal działa wyłącznie na loopback.

## Verification

```powershell
npm run api:test
npm run reviewer:build
```

Test zewnętrzny i kontrola HTTPS są obowiązkową częścią Outcome.

## Risks / open questions

- Blokada: wymaga ukończonych TASK-0113 i TASK-0114.

## Outcome

Zaimplementowano kontrolowane `setup/start/status/stop` Cloudflare Quick
Tunnel, automatyczne użycie aktywnego publicznego originu w nowej sesji oraz
runbook. Skrypty mają bounded 10-sekundowy start, zapis PID i walidację procesu.
Reviewer nadal binduje loopback, a publiczny proxy ma testowaną allowlistę i
nagłówki CSP/anti-clickjacking.

Rozszerzenie 2026-07-31 dodaje do lokalnego Admin API trzy typowane operacje
ingressu i przyciski `Utwórz link i wystaw online` oraz
`Zatrzymaj udostępnianie`. API uruchamia tylko stałe skrypty z timeoutem,
nie przyjmuje komendy ani portu, zapewnia produkcyjny Reviewer i blokuje
publikację trybu developerskiego. Stop próbuje unieważnić bieżącą sesję i
zamyka tunel również przy błędzie revoke; decyzje i audyt pozostają w bazie.

Lokalny odbiór 2026-07-31 potwierdził cały lifecycle UI:

- pierwszy start bez `cloudflared` zakończył się kontrolowanym błędem,
- oficjalny `cloudflared 2026.7.3` został zainstalowany przez winget, a skrypt
  znajduje również trwałą lokalizację instalacji bez restartu terminala,
- start utworzył publiczny HTTPS origin i scoped link bez kodu w URL,
- publiczny ekran pokazał bramę kodu bez danych gry,
- stop unieważnił bieżącą sesję, usunął stan tunelu i stary URL zwrócił
  Cloudflare `1033`,
- kolejny start wygenerował nowy URL i nową sesję,
- Admin, Reviewer i API słuchają wyłącznie na `127.0.0.1`.

Na Windows komunikacja API ze skryptem używa krótkiego pliku wyniku w
`.runtime`, a nie odziedziczonego stdout. Usuwa to możliwość utrzymania requestu
przez proces potomny; plik jest bez BOM, nadpisywany pod lockiem i usuwany po
odczycie.

Test zewnętrzny został rozpoczęty: aktywny link oczekuje na wejście właściciela
z drugiego komputera w innej sieci. Kryteria wymagające zewnętrznego klienta,
odczytu właściwego scope, zapisu decyzji i natychmiastowego revoke pozostają
niezaznaczone; do tego czasu TASK-0115 i G8.7 nie są zamknięte.
