---
title: Weryfikacja poprawki zgodności schematu przy wdrożeniu
status: active
last_updated: 2026-11-09
---

# TASK-1169 — zgodność schematu i preflight

## Przyczyna i zakres

Podczas zatwierdzonego cutover po T0–T5 main/origin przeszedł fast-forward
do c0bf0368/v1.7.578, a migracje0182/0183 zakończyły się poprawnie12,62s.
Nie zmieniły liczby166971zdjęć,4przypisań ani wspólnego defaultu.
API odmówiło startu: EXPECTED_ALEMBIC_HEAD nadal0181 wobec bazy0183.
Pominięto aktualizację globalnego strażnika i związany test przy nowych
migracjach; wcześniejsze scoped QA i audyty tego nie wykryły. Nie był to
błąd operatora ani powód do cofania migracji lub wyłączenia kontroli.

TASK-1169 naprawia to niezależnie: wspólny exactguard0183/manifestv22,
aktualny test rzeczywistego grafu oraz statyczna bariera przed kolejnym
merge/cutover. Nie zmienia geometrii, progów, modeli ani danych.

## Wykonana weryfikacja

Wykonawca Sol/high,4źródła; strict manifest
artifacts/TASK-1169_HELPER.scope.json SHA
9dbdad0344d78b923ce012eaa7353dffa2dad4d4fee608c4757279be48667cb3.

- Guard i rzeczywiste odrzucenie schematu przez worker:29PASS,5deselected,
  13,24s. Dynamiczny ScriptDirectory, chain183→182→181, odmowa181/182.
- Scoped preflight:12PASS,27deselected,25,46s; przypadki unknown, pinnedref
  vsbrudnycheckout oraz dotychczasowy JSON/text/readonly. Osobny nextmigration
  test1PASS37,52s: brak aktualizacji guardu blokuje, zgodna aktualizacja
  daje matched. Nie importuje kodu migracji/aplikacji ani nie łączy się z DB.
- Ruff/format4PASS; strictmypy2PASS2,376s/597modułów/0errors.
  Przerwany szeroki stary zestaw nie jest PASS; własne procesy sprawdzono.
- Root uruchomił nowy preflight na rzeczywistym przypiętym c0bf0368:
  48,16s, poprawnie mismatch181↔183/blocks_merge=true. Niezacommitowana
  poprawka nie wpływa na analizowany ref; po commicie wymagany matched.
  To pojedyncza obserwacja czasu, nie benchmark. Skrypt nie zmienia exit0
  dla poprawnego raportu; procedura merge musi sprawdzić blocks_merge.
- Root: nowy interpreter, jawny PYTHONPATH poprawionych modułów, istniejąca
  baza0183 i rola aplikacyjna — require_alembic_head PASS; worker importuje
  dokładnie tę samą funkcję. To odczyt, bez uruchamiania serwera lub joba.

Canonical merge-to-main i kopia .agents są zgodne: wymagają matched/false,
unknown/mismatch blokują mimo exit0. Zaktualizowano instrukcję cutover.
CLI jest wewnętrznym raportem, nie zmianą HTTP/OpenAPI/SDK.

## Odbiór

Scoped QA jest gotowe; root kończy docs/map i rzeczywisty terminalowy
Opus przed commitem. Nie ma zastępczego PASS. Po integracji tej poprawki
root wznowi zatwierdzone starty API/Reviewera/workerów i live GET smoke;
wyniki pozostają w root artifacts/full-symbol-deployment-20261109.
Trening, default i import691 nie należą do tego cutover.

## Audyt i zamknięcie kodu

Operator jednoznacznie zatwierdził pakiet TASK-1169 do Anthropic. Poprzednie
odrzucenia automatycznej kontroli nie uruchomiły audytora. Terminalowy
Opus5.5/high(requested) wykonał R1 w196,75s: PASS0P0/0P1. Report/receipt
TASK-1169_AUDIT_claude-opus-5-5 mają payloadSHA320b590e55e90c13da93150286e3c5fa10d25f7619b99cfbf2fe5395b75bfc70
i reportSHA54ec1d50b328360db35e0c5cf333c76944dc372695cd1d2fa594c157c7355745.
Observed main model jest claude-opus-5-5; nie deklarujemy backendowego
potwierdzenia effort. Pełny raport i receipt odczytano i sprawdzono.

P2-1 zaakceptowany: brak osobnych trzech przypadków grafu (osiągalny cykl,
duplikat revision, udany tuplemerge); implementacja jest fail-closed,
dynamiczny rzeczywisty graf i8negativecases są pokryte. Nie nazwano tego
pełnym pokryciem gałęzi. P2-2 poprawiono doprecyzowaniem samej instrukcji:
worktree gałęzi, jawny argument z gitbranch oraz zatrzymanie przy kodzie1.
Nie zmieniono po audycie produkcyjnego zachowania ani testów.

Kod jest gotowy do osobnego commita/task-close. Zgodny wynik statyczny
przypiętego nowego commita i pełny start usług zostaną zapisane w raporcie
operacyjnym po integracji; bez nowej migracji i bez treningu w TASK-1169.
