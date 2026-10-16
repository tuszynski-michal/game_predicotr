---
title: Przekazanie planu geometrii V3 po zamianie ról
status: active
last_updated: 2026-10-16
---

# Przekazanie Claude Code — geometria V3

Operator polecił2026-10-16 dokończyć bieżący TASK-0995, następnie zamienić role.
TASK-0995 nadal wykonuje Codex i audytuje Claude Code. Pozostałe zadania
wykonuje Claude Code, a audytuje Codex. Nie zmieniamy historycznych autorów,
raportów ani wyników ukończonych zadań.

## Miejsce pracy i źródła prawdy

- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`.
- Gałąź: `codex/v3-grid-fine-tuning`.
- Plan: `ai_docs/delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md`.
- Stan, faza i hashe: `ai_docs/process/CURRENT_STATE.md` oraz Outcome taska.
- Baza przed bieżącym taskiem: v1.7.384,
  `d2b692dbc59f1de339ad1acd2a961d402fced8c8`.

Przed rozpoczęciem następnego taska sprawdź rzeczywisty HEAD, gałąź i status,
potwierdź ukończenie oraz commit TASK-0995. Ten dokument nie zastępuje
wyniku audytu. Jeśli0995 pozostaje aktywny lub ma otwarte P0/P1, wróć do niego.
Nie resetuj checkoutu i nie przenoś zmian do głównego katalogu działającego API.

Czytaj AGENTS, README, CURRENT_STATE, indeks i pięć najnowszych decyzji,
PLAN_STANDARD, TASK_TEMPLATE, aktualny task oraz wyłącznie jego Relevant docs.
Dokładną kolejność wznawiania i protokół audytu określa sekcja3 planu.

## Zakres dalszej pracy

Kolejność po zamknięciu0995: TASK-1005 →0996 →0997 →1006 →1000 →1001.
Dokładne modele i reasoning podaje końcowa tabela planu oraz Recommended
execution każdego taska. Claude Code używa `claude-fable-5-1`; audytor
Codex `gpt-6-astra`, poziomy zgodne z zadaniem. Niedostępność przypisanej
konfiguracji wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

Cały koszt orientacyjny12–28 dni roboczych i wykonywanie planu zatwierdzono.
Każdy task kończy się własnymi kontrolami, audytem innej rodziny, Outcome,
aktualizacją stanu i osobnym commitem. Jedna runda audytu i jedna korekta;
ponowny audyt tylko według reguły P0/P1 lub na polecenie operatora.
Nie rozpoczynaj kolejnego taska przed zamknięciem poprzedniego.

## Wiążące decyzje

- Współdzielimy geometrię Mumii/777a2 i przyszłych V3. Symbole, katalogi,
  klasyfikatory i aktywacje symboli pozostają osobne dla każdej gry.
- Historyczna777, kod7, pozostaje archiwalna.
- Kontrola geometrii obejmuje wszystkie9 plansz zdjęcia. Symbole korzystają
  wyłącznie z istniejących aktualnych ręcznych zatwierdzeń; pozostałe są
  nieocenione.
- Usunięcie operacyjnego zdjęcia zachowuje historię zbioru, ale blokuje nowe
  treningi i oceny używające jego kopii. Samo usunięcie nie jest cofnięciem
  ludzkiej oceny. D-556 i kontrakt0995 rozdzielają aktualne zatwierdzenie,
  live link i dostępność bitmapy. `SOURCE_REMOVED_NEW_USE_BLOCKED` nie jest
  pozwoleniem na odtwarzanie źródła lub usuwanie historii.
- Domyślny model przypinamy nowym grom; istniejące przypisania wymagają
  jawnej aktywacji. Wspólny kandydat nie dostaje automatycznego PASS.
- Finalny panel1000 ma wybór po nazwach importów, nagrań i wersji.
  Techniczne pola UUID obecnego pomocniczego panelu0995 nie są finalnym UX.
- TASK-0997 musi dostarczyć rzeczywisty writer/zgodny v2 reader raportu, bezpieczne
  własne game bindings i globalną kontrolę aktualności przed publikacją.
  Sam identity binding0995 nie jest bramką jakości.

## Zgody operacyjne i ograniczenia

Nie uruchamiaj GPU smoke, treningu, inferencji, publikacji, aktywacji, zmiany
defaultu, operatorDB migration/backfill/cleanup ani szerokiego przetwarzania
bez właściwej osobnej zgody. Implementacja mechanizmu nie jest jego wykonaniem.
Usługi API/Admin/Reviewer i Docker pozostają pod kontrolą operatora.
Istniejąca kopia `D:\game_predictor_backup` wystarcza zgodnie z jego decyzją;
nie twórz nowego backupu bazy. Frozen kohorty są częścią mechanizmu treningu,
nie dodatkowym backupem bazy.

Nie wykonuj merge, push ani wdrożenia. Na końcu całego zakresu trzeba przedstawić
wynik i uzyskać zgodę na integrację. Gałęzią integracyjną jest od 2026-10-16 `main`;
`main` v1.7.374 scalono do gałęzi roboczej na polecenie operatora, aby końcowa
integracja mogła być fast-forwardem. Nowe numery patch i kolidujących tasków przydzielaj
według istniejącej zgody operatora: sprawdź wszystkie lokalne refs/worktree
HEADs, wybierz kolejny wolny numer i zapisz mapowanie.

## Dowody i znane ograniczenia

Niezależny rdzeń0995 zamrożono jako77 źródeł/dokumentów i520 dowodów.
Manifest ma SHA256
`8ca83fefaf3fc5738cdf915d2a3612fc55ec2d1a5fd32871f175e6625d4d506e`;
root potwierdził dokładne kopie i hashe. Późniejsza przyjęta polityka usuniętych
źródeł wymaga nowego manifestu końcowego; poprzedniego nie nadpisujemy.
Szczegółowe wyniki i aktualne zamknięcie0995 są w jego Outcome.

Skoncentrowany E2E03 przeszedł na120 geometriach/20 zdjęciach: rzeczywisty
freeze, odczyt w nowym procesie i cofnięcie korekty blokujące gotowy drugi
zbiór bez częściowego użycia. Nie jest to rzeczywisty trening ani pomiar jakości
modelu na danych operatora. Wcześniejsze niepowodzenia pozostają historią.

Istniejący layout reset ma znany błąd RESTRICT pending→review, poza0995.
Oddzielny full-game DELETE przeszedł, ale nie zastępuje resetu. Stare pełne
zestawy backendu i SuperGame UI zachowują jawne FAIL; nie nazywaj ich PASS
na podstawie skoncentrowanych wyników. Szczegóły wskazuje CURRENT_STATE.
Nie czytaj surowego TASK-1002_R1_PYTHON_TEST_AGGREGATE.json: zawiera poufne
dane połączeń. Korzystaj z przygotowanych bezpiecznych raportów.

## Stan przekazania

TASK-0995 ukończono technicznie: R1REVISE, jedna korekta, R2PASS
(288.719457s/high/do1200s), brakP0/P1. Przygotowany v1.7.385;
pełny hash jest zapisywany po commicie w Outcome i CURRENT_STATE, do porównania
z rzeczywistym GitHEAD. Nie wykonano integracji. Zadanie1005 nie zostało rozpoczęte.

Przyjęte P2-5 dotyczy wyłącznie starej asercji*.staged w teście sukcesu/replay,
która wymaga zamiany na faktyczne.tmp-*.part. TASK-1001 ma konkretny wpis.
Nie powtarzaj całego audytu0995 i nie przedstawiaj tego P2 jako otwartegoP1.
Nowy real hard-crash/guarded scan/24h/reference test przeszedł.

Kontynuuj według tabeli modeli od TASK-1005 jako Claude Code. Codex audytuje.
Sprawdź najpierw HEAD, status i dwie ewentualne jawne zmiany posthash taska/stanu;
zgodnie z AGENTS mogą wejść do następnego commita. Bez resetu lub amend.
