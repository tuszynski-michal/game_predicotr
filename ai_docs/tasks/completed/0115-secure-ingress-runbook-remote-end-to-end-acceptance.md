---
title: Secure ingress runbook and remote end-to-end acceptance
status: done
last_updated: 2026-07-31
---

# TASK-0115 — Secure ingress runbook and remote end-to-end acceptance

## Status

`done`

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

- [x] Reviewer działa przez HTTPS z urządzenia w zewnętrznej sieci,
- [x] niepoprawny lub wygasły kod nie ujawnia danych,
- [x] zdalny użytkownik widzi tylko wskazaną grę/import,
- [x] odwołanie sesji działa natychmiast,
- [x] skan ekspozycji nie wykazuje Admin, bazy ani nieobjętych endpointów,
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

Odbiór zewnętrzny 2026-07-31 zakończył się powodzeniem. Właściciel otworzył
link HTTPS na innym urządzeniu podłączonym do innej sieci, zobaczył wcześniej
zatwierdzone układy, a zatwierdzanie przez `Enter` i `ArrowRight` działało na
tej samej trwałej kolejce. Oznacza to, że publiczny Reviewer odczytywał
właściwy scope i decyzje pozostały zapisane w PostgreSQL. Akcja
`Zatrzymaj udostępnianie` zakończyła publiczną dostępność aplikacji. Wraz z
automatycznymi testami bramki kodu, allowlisty proxy, revoke i loopback zamyka
to wszystkie kryteria TASK-0115 oraz bramkę G8.7.

Weryfikacja automatyczna końcowej implementacji:

- pełny pakiet API: `212 passed, 16 skipped`,
- klient Admin API: `18/18 passed`,
- testy serwisu ingressu: `3/3 passed`,
- build Admina i produkcyjnego Reviewera: zakończone powodzeniem,
- focused typecheck nowego serwisu: zakończony powodzeniem; pełny mypy
  przekroczył kontrolowany limit 120 sekund.
