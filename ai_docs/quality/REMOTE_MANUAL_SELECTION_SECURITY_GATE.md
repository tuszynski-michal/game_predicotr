---
title: Remote manual selection security gate
status: accepted
last_updated: 2026-08-24
---

# Bramka bezpieczeństwa zdalnej ręcznej selekcji

## Decyzja

`PASSED` dla zakresu TASK-0289. Publiczny rollout nadal wymaga etapowego
benchmarku i decyzji TASK 18. Test przez prawdziwy Quick Tunnel oraz pentest
strony trzeciej pozostają świadomie poza tą bramką.

Maszynowym źródłem wyniku jest
`ai_docs/quality/remote-manual-selection-security-gate-v1.json`. Raport zawiera
stały zestaw ośmiu kontroli, jawne findings i checksumę kanonicznej treści.
SHA-256 raportu bez pola podpisu:
`8386c3676422ecb3d98994c854bb7c447f5c5452592990485f7bd9af3e4b4360`.

## Wynik audytu

- allowlista proxy odpowiada dokładnie publicznym operacjom OpenAPI; wszystkie
  pozostałe metody oraz Admin/Reviewer routes są default-deny,
- kod dostępu nie jest bearer tokenem, cookies obu modułów są rozdzielone, a
  token jednej sesji nie autoryzuje innej,
- mutacje wymagają zgodnego `Origin` i `Sec-Fetch-Site: same-origin`; nagłówki
  forwarded nie mogą zmienić oczekiwanego hosta,
- budżet control plane jest per sesja, także dla replay, a transfer zachowuje
  limity pliku, sesji i współbieżności,
- host path jest wybierany lokalnie; corpus Windows, reparse, TOCTOU oraz obcy
  plik kończą się fail-closed,
- publiczne odpowiedzi i audit payloady blokują zagnieżdżone sekrety oraz
  absolutne ścieżki hosta,
- brak otwartych findingów `critical` lub `high`.

## Weryfikacja raportu

```powershell
.venv\Scripts\python.exe scripts\verify_remote_manual_selection_security_gate.py
```

Pełny wynik komend implementacyjnych i ograniczenia środowiska są zapisane w
`CURRENT_STATE.md` oraz Outcome TASK-0289.
