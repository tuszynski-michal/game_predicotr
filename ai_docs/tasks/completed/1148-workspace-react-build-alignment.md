---
title: Spójne zależności React podczas wdrożenia
status: done
last_updated: 2026-11-03
---

# TASK-1148 — Spójne zależności React podczas wdrożenia

## Status

`done`

## Goal

Standardowy build Admina i Reviewera z głównego katalogu przechodzi bez aliasów typów i bez pomijania kontroli TypeScript.

## Context

Zatwierdzone wdrożenie 777 A2 jest na bazie0177. Build Admina ujawnił dwie nominalnie różne definicje React Ref/VoidOrUndefinedOnly. Lockfile zawiera root @types/react19.2.17, podczas gdy aplikacje i board-search-ui przypinają19.2.2; board-search-ui jako jedyny przypina React/DOM19.2.8 zamiast19.2.3 z TECH_STACK. Standardowa reinstalacja nie rozwiąże konfliktu zapisanego w repozytorium. Pierwszy npm12ci odmówił istniejącej zależności git Electron; do dalszej pracy używamy packageManager npm11.18.0. To konieczna wąska poprawka zatwierdzonego wdrożenia, bez rozszerzenia produktu.

## Dependencies / entry conditions

Start9f1d69c5. Task1147 zarezerwowany przez drugie okno;1148 sprawdzony i uzgodniony przed zmianą. Wszystkie usługi zatrzymane za zgodą użytkownika. Nie zmieniać pozostałych worktree ani API.

## Recommended execution

gpt-6-astra/high; mała korekta manifestów i lockfile. Niezależny claude-opus-5-5/high przed commitem, najwyżej6 celowanych odczytów. Eskalacja tylko przy konflikcie wymagań lub P0/P1.

## Relevant docs

- AGENTS.md; ai_docs/process/DEFINITION_OF_DONE.md.
- ai_docs/architecture/TECH_STACK.md, Admin web.
- ai_docs/requirements/ADMIN_APP.md, plan wymiany zdjęć.
- ai_docs/quality/777A2_DEPLOYMENT_BLOCKER_20261103.md.
- .codex/skills/claude-audit/SKILL.md; .agents/skills/task-close/SKILL.md.

## Scope

Root devDependency @types/react19.2.2 jako wspólna wersja dla zależności typów; board-search-ui devReact/DOM19.2.3 zgodnie z aplikacjami; lockfile generowany npm11.18.0. Bez ręcznych zmian JSX/ref, aliasów tsconfig, wyłączenia sprawdzania typów lub aktualizacji innych bibliotek.

## Acceptance criteria

- [x] Wszystkie instalowane @types/react mają jedną wersję19.2.2; React/DOM aplikacji i biblioteki19.2.3.
- [x] Standardowe buildy Admin/Reviewer i istniejące testy board-search-ui przechodzą w nowym procesie.
- [x] Audyt Opus5.5 bez P0/P1, docs checks; task-close i osobny commit/hash prowadzi koordynator przed kontynuacją wdrożenia.

## Expected files

package.json; packages/board-search-ui/package.json; package-lock.json; task, CURRENT_STATE i raport audytu. Bez zmiany modułów/publicznych symboli; mapa kodu nie wymaga regeneracji.

## Verification

Każde polecenie z subprocess timeout120s, znane buildy300s po uprzedzeniu operatora. Użyć npm11.18.0, bez zmiany globalnej konfiguracji. Lock-only w worktree, instalacja i standardowe buildy w root po scaleniu; przed commitem sprawdzić build na tym samym zestawie manifestów i lock. Audyt480s, zewnętrzny limit600s.

## Risks / open questions

Bez zmian mobilnego kontraktu ani aplikacji. Wspólne node_modules może być używane przez inne okno; uzgodniono wstrzymanie jego testów Node. Nie deklarować zielonego builda z aliasami. Nowy test jednostkowy odtwarzający listę wersji nie jest potrzebny; rzeczywisty build weryfikuje przyczynę.

## Outcome

Commit: v1.7.543 (hash dopisuje kolejny commit).

### Changed

Root przypina @types/react19.2.2. board-search-ui devReact/DOM19.2.3 zgadza się z aplikacjami i TECH_STACK. Lock-only wygenerowano npm11.18.0, bez zmian innych zależności; root transitive React/DOM19.2.8 pozostaje, aplikacje i biblioteka rozwiązują własny19.2.3. Nie dodano overrides, aliasów, rzutowania Ref ani pominięcia typów.

### Verification results

- Początkowy standardowy build Admina: FAIL, board-search-photo-navigation.tsx:150, nominalnie różne VoidOrUndefinedOnly. Przyczyna w dwóch wersjach @types/react.
- npm11.18.0 install --package-lock-only --ignore-scripts --no-audit --no-fund: PASS. Trzy pliki zależności tymczasowo skopiowane do zatrzymanego root po porównaniu z git HEAD i zapisaniu dokładnych kopii; po kontrolach zostaną przywrócone przed fast-forward. npm11.18.0 ci --prefer-offline --no-audit --no-fund: PASS, nowy proces, log artifacts/deploy-777a2-20261103/npm11-ci.log. Pierwsze npm12ci odmówiło istniejącej zależności git Electron; użyto wersji przypiętej w packageManager bez obchodzenia zabezpieczeń npm12 ani zmian globalnej konfiguracji.
- Root standardowy next build apps/admin: PASS32,36s; next build apps/reviewer: PASS21,11s, wraz z TypeScript. Bez aliasów tsconfig i app-local junctionów. Runnery subprocess300s; logi admin-build-20261103T103637.log i reviewer-build-20261103T103637.log.
- Istniejące npm run test --workspace @game-predictor/board-search-ui:113/113PASS,3,16s. Node resolver w nowym procesie potwierdza dla obu aplikacji i biblioteki React19.2.3 oraz typy19.2.2.
- Prettier --check dla trzech zmienionych manifestów/lock: PASS. Brak zmian kodu, publicznych symboli, schematu lub API, więc dodatkowe Python lint/OpenAPI/map nie dotyczą tej poprawki.
- Audyt [Opus5.5/high](../quality/TASK-1148_AUDIT_claude-opus-5-5.md): PASS, bez P0/P1. P2-1 domknięto przez root npm run typecheck --workspace ./apps/mobile: PASS, nowy proces, timeout120s, log t1148-mobile-typecheck.log. P2-2 przyjęto jawnie: transitive rootReact19.2.8 pozostaje; aplikacje i biblioteka rozwiązują19.2.3, dalsza globalna deduplikacja nie jest potrzebna do tego zakresu. P2-3: w międzyczasie uprawniony tor Selektora przesunął main/origin do0bcabfc4. Nie przywracano starego locka1.0.4: udowodniono zgodność pozostałych różnic wyłącznie z naszym stagingiem i zachowano jego wpisSelector1.0.5. Odtworzono trzy pliki z aktualnegoHEAD0bcabfc4; git diff --exit-code dla nich PASS. Rootdependencies odpowiadają testowanej poprawce, wszystkie usługi pozostają zatrzymane i drugie okna są poinformowane. Przed startem nastąpi FF do poprawionych manifestów.
- Cztery docs checkery i code-map --check: PASS; startup44739B. DoD: przyczyna usunięta w manifestach/lockfile i potwierdzona nowym npmci/procesami; brak sesyjnych aliasów. Wymagane zachowanie pokrywają dwa buildy,113testów i mobile typecheck. Brak zmiany domeny/API/schematu. Task-close/commit/hash przed kontynuacją wdrożenia.

### Not completed

Pełny test mobilny i aktualizacje bibliotek poza zakresem. Instalator zgłosił zastane ostrzeżenia deprecacji/allow-scripts; buildy Next potwierdzone. Usługi start/push pozostają częścią wdrożenia, po audycie.

### Documentation updates

Task/Outcome i CURRENT_STATE. Wersje odpowiadają istniejącemu TECH_STACK, bez nowej decyzji architektonicznej.

### Recommended next task

Dokończenie zatwierdzonego wdrożenia; drugie okno przejmie0178 po oddzielnym handover.
