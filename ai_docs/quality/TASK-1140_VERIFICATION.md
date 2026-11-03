---
title: TASK-1140 — Weryfikacja panelu przyrostu korekt
status: active
last_updated: 2026-11-03
---

# TASK-1140 — Weryfikacja panelu przyrostu korekt

## Zakres i izolacja

Praca w `D:\game_predicotr\worktrees\grid-correction-growth`, branch
`codex/grid-correction-growth`, baza `v1.7.536`. UI jest zależne od addytywnego
kontraktu `progressCounts` TASK-1139. Żaden test nie wywoływał operacyjnego API.
Początkowy patch UI lead przeniósł z głównego checkoutu i przywrócił go przed
weryfikacją. Wszystkie kontrole poniżej wykonano już z izolowanego worktree.
Testy interakcji używają fake API, także dla POST aktualności i zastosowania.
Nie uruchamiano ani nie zatrzymywano usług; nie wykonywano treningu, publikacji,
zastosowania, migracji ani zmiany defaultu.

## Zmiana

- Backendowe liczniki zatwierdzonych korekt, dostępnego TRAIN, etykiet w zamrożonych
  zestawach TRAIN i nowych etykiet, zatwierdzonych kontroli, rezerw bez etykiet,
  buforów i wyłączeń. Zapis w zestawie nie oznacza ukończenia treningu modelu.
  UI nie sumuje nakładających się kategorii zdjęć i nie rekonstruuje podziału.
- Osobna sekcja gotowości następnego uczenia i historyczny wynik przebiegu.
  Objaśnienie rezerw i potrzeby korekty zarezerwowanych zdjęć albo nowego importu.
- Jawne sprawdzenie aktualności zapisanych dowodów przez istniejącą metodę
  `verifyGridModelEvaluationCurrentness`; następnie GET przypiętej oceny i nowego
  podglądu zastosowania.
- Synchronous guard oraz generacje odpowiedzi chronią podwójne kliknięcie,
  zmianę wyboru, nowszy odczyt i unmount. Utrata odpowiedzi nie odblokowuje nowego apply;
  późniejszy autorytatywny GET może uzgodnić stan bez automatycznego ponawiania POST.
- Podgląd apply jest przypięty do zakresu i generacji odczytu. Odświeżenie usuwa
  poprzednie potwierdzenie, a stara optymistyczna odpowiedź nie przywraca zgody.

## Wykonane kontrole

Każde polecenie uruchomiono przez Python `subprocess.run(..., timeout=120)`.

| Kontrola | Wynik |
|---|---|
| Interakcje panelu korekt po R1 | PASS, 40/40 (18 nowych i 22 wcześniejsze) |
| Interakcje panelu, grid-model-workspace, grid-cohort-preview i model-quality-loading po R1 | PASS, 74/74, ok. 5,5 s wykonania testów |
| Scoped ESLint 3 modułów TS/TSX i testu interakcji, z katalogu apps/admin | PASS, 0 błędów i 0 ostrzeżeń |
| TypeScript lokalnego Admina z aliasami do źródeł klienta worktree | PASS |
| Admin production build po R1, Next.js 16.2.11 / Turbopack | PASS; kompilacja 4,6 s, TypeScript 16,8 s, 3 strony statyczne |

Pierwsze wywołanie ESLint z katalogu repo nie znalazło konfiguracji. Ponowienie
z `apps/admin` użyło istniejącej konfiguracji. Dwa ostrzeżenia nowego testu o
nieużywanych pozycjach destrukturyzacji usunięto przed końcowym PASS.

### Komendy i lokalne aliasy

Współdzielone `node_modules/@game-predictor` wskazuje główny checkout.
Tymczasowy `apps/admin/tsconfig.growth-local.json` rozszerzał istniejący tsconfig
i kierował `@game-predictor/admin-api-client` oraz
`@game-predictor/vision-lab-api-client` do źródeł worktree. Zachowano `@/*`.
Testy importują zmienione komponenty bezpośrednio ze ścieżek worktree; klient
runtime i jego wygenerowane typy są lokalne dzięki aliasom. Niezmienione
zależności pozostają współdzielone.

Po testach lokalny wariant tsconfig przeniesiono do ignorowanego
`artifacts/task1140-tsconfig-used.json`. Odtworzenie poniższych komend w tym
worktree wymaga skopiowania go z powrotem do
`apps/admin/tsconfig.growth-local.json`; jego ścieżki są względne wobec tego
położenia. Nie dodawać go do commita.

```powershell
npx tsx --tsconfig apps/admin/tsconfig.growth-local.json --test apps/admin/test-interactions/grid-correction-learning-panel.test.mjs apps/admin/test-interactions/grid-model-workspace.test.mjs apps/admin/test-interactions/grid-cohort-preview.test.mjs apps/admin/test-interactions/model-quality-loading.test.mjs

# cwd: apps/admin
npx eslint src/features/model-quality/grid-correction-learning-panel.tsx src/features/model-quality/grid-correction-apply-panel.tsx src/features/model-quality/grid-model-state.ts test-interactions/grid-correction-learning-panel.test.mjs
npx tsc --noEmit -p tsconfig.growth-local.json

# cwd: repo worktree; chwilowe lokalne aliasy w tsconfig.json, przywrócone w finally
npm run build --workspace @game-predictor/admin
```

Na czas builda te same aliasy wpisano do lokalnego `apps/admin/tsconfig.json`,
a oryginalne bajty przywrócono w `finally`. Brak trwałej zmiany konfiguracji.
Next ostrzegł, że wybrał nadrzędny katalog repo jako root grafu Turbopack z powodu
dwóch lockfile. Zmienione moduły i klient były przypięte do worktree; wynik
`.next/BUILD_ID` powstał w lokalnym `apps/admin/.next`. Nie zmieniano wspólnego
`node_modules` ani konfiguracji działającego Admina w głównym checkoutcie.

## Pokryte przypadki

1. Wzrost TRAIN i nowych plansz po kolejnej korekcie; wzrost kontroli nie zwiększa TRAIN.
2. Rezerwa bez etykiet ma zero plansz; wyłączenia mają proste polskie przyczyny.
3. Stale → jeden jawny POST mimo dwóch kliknięć → nowa ocena → nowy podgląd,
   z ponownym potwierdzeniem zakresu.
4. Zmieniona/wycofana etykieta nadal blokuje zastosowanie, także przy checkboxie
   i niezgodnym optymistycznym preview fake API.
5. Utrata odpowiedzi POST, błąd GET oceny i błąd GET preview pozostają widoczne;
   jawne ponowienie działa, bez automatycznego treningu/publikacji/apply.
6. Spóźniona odpowiedź POST oraz GET oceny nie zastępuje innego przebiegu;
   unmount/inna gra nie uruchamiają dalszego odczytu starej oceny.
7. Stary optymistyczny GET preview nie zastępuje nowszej blokady przypisania.
8. Odświeżenie po utracie odpowiedzi czeka na autorytatywny GET; reload uzgadnia
   zakończone sprawdzenie wyłącznie odczytem i nie ponawia POST.
9. Regresje TASK-1138: niezależne odczyty, allSettled, widoczna historia mimo
   wolniejszej gotowości, guard refresh i czas pełnego udanego odczytu.
10. Częściowo zakończony failed apply z rzeczywistym evaluationId i stale oceną
    wysyła resume; nowe zastosowanie nadal pozostaje zablokowane.
11. Utracona odpowiedź startu apply, następnie stale ocena i reload: jawny replay
    wysyła identyczny idempotencyKey i payload, bez automatycznego POST.
12. Jawna allowlista metod GET przy wejściu i zmianie wyboru nie dopuszcza
    `previewGridCorrectionLearning`, które jest POST.
13. GET przebiegu/oceny po błędzie kończy loading, utrzymuje blokadę nowego apply
    i wskazuje odświeżenie stanu; retry przywraca bieżącą ocenę.
14. Ocena processing, także z reportId i raportem, oraz completed bez raportu
    nie umożliwiają sprawdzania aktualności i nie udają zakończonego wyniku.
15. Nieopisane chronione zdjęcie poza kolejką korekt ma rezerwę zero, wyłączenia
    1 zdjęcia / 0 plansz i powód GRID_CORRECTION_CONTROL_NOT_PENDING.

## Jedyna runda poprawek po audycie R1

Raport `TASK-1140_AUDIT_claude-opus-5-5_R1.md` miał wynik REVISE. Poprzednie wyniki
34/34 i 68/68 były poprawne dla ówczesnych testów, lecz nie wykrywały regresji
durable resume/replay. Po poprawce evidenceBlocked obejmuje tylko nowy apply.
Resume zawsze dociera do backendu; replay omija lokalną blokadę wyłącznie, gdy
polecenie dokładnie odpowiada zarówno pending w stanie komponentu, jak i komendzie
w localStorage. Nowe apply i checkboxy nadal podlegają blokadzie aktualności.

P1-1/P1-2 otrzymały testy rzeczywistego evaluationId + stale. P2-1 otrzymał
allowlistę GET, P2-2 prawidłowe kończenie loading i wskazanie retry. P2-3 należy
do leada: osobne hunki i commity dokumentacji TASK-1139/1140. Dodatkowe uwagi
leada o completed+raporcie, semantyce zamrożonych TRAIN i nieopisanych kontrolach
uwzględniono w kodzie, treści i testach. Focused review R2 zakończył się PASS:
`TASK-1140_AUDIT_claude-opus-5-5.md`. Otwarte P2-3 dotyczy wyłącznie rozdzielenia
hunków dokumentacji między osobne commity i należy do prowadzącego.

## Pozostaje leadowi

Po osobnym commicie danych e33b71ab odtworzono panel i porównano hashe z drzewem
R2 audytu: pięć plików i cały blok architektury są identyczne. Ponownie wykonano
74/74 interakcje, TypeScript, generację mapy, docs:check i code-map:check — PASS.
Logi: `artifacts/task1140-interactions-final.log`, `task1140-typecheck-final.log`,
`task1140-docs-preclose.log`, `task1140-map-preclose.log`; dowód hashy:
`artifacts/task1140-restored-hashes.json`.

P2-3: dane zapisano osobnym commitem bez apps/admin i bloku architektury TASK-1140.
Staged diff UI jest kontrolowany oddzielnie; dołącza wyłącznie wymagane metadane
hasza poprzedniego taska. Nie zmieniono kodu po pozytywnym audycie R2.

- Zamknięcie TASK-1140 przez task-close i osobny commit z zapisem hasha.
- Odbiór operatora po wdrożeniu, bez operacyjnych POST w tej weryfikacji.

Lista ścieżek do audytu: `artifacts/task1140-audit-paths.txt`. Hunk UI w
`VISION_LAB.md` zaczyna się od `TASK-1140: readiness renders` i kończy na
`old optimistic response cannot restore a stale preview or its confirmation.`
