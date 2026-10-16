---
title: TASK-0995 — Rozliczenie audytu Claude przez Codex
status: active
last_updated: 2026-10-16
---

# TASK-0995 — Rozliczenie audytu

Claude Code `claude-fable-5-1/high` wydał REVISE w rundzie1 po648.089326s,
przy limicie1200s. Oryginalny raport oraz jego kopiaR1 pozostają bez zmian;
SHA256 `1912d965ecfd54ddc332fa1a86bbac81bc6c45330337e0936a49ab5b2e91be48`.
Root potwierdził niezmienność91 plików zakresu i539 dowodów podczas audytu.
Przegląd nie uruchamiał testów i nie jest pomiarem jakości modelu.

## Jedna runda poprawek

| Uwaga | Działanie | Stan |
|---|---|---|
| P1-1 | Publisher tworzy .tmp-hex.part. Rzeczywisty subprocess kończy się os._exit(73) po fsync/przed replace; skaner widzi rzeczywisty pozostawiony plik, chroni go przed24h/przy ref i kwalifikuje po25h bez ref. | Zamknięte przez R2 PASS. |
| P2-1 | Nowa niezacommitowana0163 emituje SOURCE_REMOVED_NEW_USE_BLOCKED; test sprawdza rzeczywisty SQL triggera. Historycznych notices nie przepisujemy. | Zamknięte przez R2 PASS. |
| P2-2 | Mapper obejmuje GRID_COHORT_; parametrized test potwierdza typed409 i używalny caller transaction po rollback savepointu. | Zamknięte przez R2 PASS. |
| P2-3 | Completion wymaga aktualnego własnego nieodrzuconego targetu wskazującego dokładną rewizję, pod istniejącym ownership/source fence. Siedem przypadków potwierdza dopuszczenie bieżącego targetu i odmowę historycznego/obcego/odrzuconego/superseded/brakującego. Kontrakt utrwalono przed poprawką. | Zamknięte przez R2 PASS. |
| P2-4 | Outcome opisuje już wybraną i wdrożoną politykę blokady nowego użycia usuniętego źródła. | Zamknięte przez R2 PASS. |

Ponowny audyt jest wymagany, ponieważ poprawka zmienia zachowanie objęte P1-1.
R2 obejmie konkretne zmienione moduły/testy, rzeczywisty diff wobec zamrożonego
R1 i dowody korekty. Nie tworzymy pętli audytów ani drugiej rundy kodowania.
Otwarte P0/P1 po R2 zatrzymują task przed commitem.

## Weryfikacja korekty

CPU01 pozostaje whole FAIL:75PASS/7FAIL,11.438s. Wszystkie7 niepowodzeń dotyczyło
brakującego argumentu expected SHA w nowym fixture; poprawiono wyłącznie fixture,
bez osłabiania produkcyjnego dekodera lub asercji. Exact7 CPU02 PASS4.938s.
Przechodzące części pierwszej komendy: GC API10, core41, storage19, worker5.
Ruff/format8 plików PASS; mypy3 produkcyjne57.454s i nowa migracja9s PASS.
Mapy/kontrola diffu PASS; source hashes oraz własne PID/TEMP cleanup potwierdzone.
Nie uruchamiano ponownie HTTP, PG ani pełnego120target fixture.

Manifest korekty: artifacts/audits/TASK-0995_R1_CORRECTION_MANIFEST.json,
SHA `d55559b0781412e67da178b41938a65d633a31392db8ccdedd4bb78caac6b1dc`;
7 zmienionych źródeł, pełne77 bieżących SHA i23 nowe dowody.
Wcześniejsze539 dowodów nie zmieniło się. Dokładny diff względem zamrożonegoR1:
artifacts/audits/TASK-0995_R1_CORRECTION_VS_R1.patch,
SHA `d286330479cab695b76bf046b6543eca5f62370141a41e90b65fd0e3dc4d5edc`.

## Wynik R2 i przyjęte ryzyko

R2 **PASS**, `claude-fable-5-1/high`, 288.719457s/do1200s.
Raport i kopiaR2: SHA `c17dfb4b1a4bcfd63a121fb6d051310fc1c266b5054ee8ab2cb2cfb2989e3ba4`. Root potwierdził niezmienność93
plików i562 dowodów podczas przeglądu. Wszystkie pięć uwagR1 zamknięto;
brak otwartych P0/P1. RaportyR1/R2 pozostają niezmienione.

Nowe P2-5 przyjęto jako niskie ryzyko pokrycia: stary glob `*.staged`
w istniejącym teście udanej publikacji nie sprawdza aktualnych `.tmp-*.part`.
Kod produkcyjnego finally nie został zmieniony, a nowy rzeczywisty hard-crash
i guarded scan/24h/reference test przeszedł. Zgodnie z regułą jednej korekty
nie rozpoczynamy kolejnej rundy zmian. TASK-1001 otrzymuje konkretną poprawkę
asercji sukcesu/replay. To jawne ryzyko testu, nie nierozwiązany P0/P1.

Nie powtarzano całego CPU01 po naprawie jego7 fixture cases. Zachowujemy
75PASS/7FAIL oraz osobne7PASS, bez fikcyjnego jednego whole-suite PASS.
Ograniczenia nowego runtime PG, layout resetu i dawnych pełnych zestawów
pozostają w Outcome.

## Stan

TASK-0995 gotowy do własnego commita v1.7.385; pełny hash po jego utworzeniu.
Wynik na gałęzi codex/v3-grid-fine-tuning, bez integracji. Następnie przekazanie:
Claude Code wykonuje pozostałe6 tasków, Codex audytuje. TASK-1005 nie rozpoczęto.
Bez operatorDB migration, nowego backupu, usług, rzeczywistego treningu,
inferencji, GPU, fizycznego cleanupu, merge i push.
