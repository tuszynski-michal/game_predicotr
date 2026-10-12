---
title: Lokalny selektor Windows — poprawki po audycie implementacji
status: accepted
last_updated: 2026-10-12
---

# Poprawki po audycie selektora Windows

## Stan obecny i zgoda

[Audyt Claude](../quality/OFFLINE_PHOTO_SELECTOR_IMPLEMENTATION_AUDIT_CLAUDE_20261012.md)
operatora ocenił v1.7.323 jako REVISE.109/109 testów i sumy ZIP są zgodne,
ale opóźnienia1,7–2,6 s wymagają naprawy przed pilotażem. Raport pozostaje
niezmieniony; nowe dowody nie przepisują jego werdyktu.
Operator2026-10-12 zaakceptował pełną dodatkową rundę poprawek oraz szacunek
2–4 godzin z testami i nowym ZIP-em. Brak wiarygodnego szacunku tokenów.
Runda obejmuje wykonanie trzech poniższych tasków i delegowanie według tabeli.
Końcowy audyt poprawionego zakresu nadal wykonuje operator; nie uruchamiamy
samodzielnie Claude ani nie zastępujemy go Codex. Fizyczny odbiór0979 pozostaje
odrębny. Baza rundy: d21f9f3ed6c5739f8fce7fac128cc59a8094330b.

## Reguły i decyzje

- Usuwamy koszt startu osobnego PowerShell dla każdego odczytu. Proponowany
  native/windows-check-worker.ts obsługuje jeden ukryty, kontrolowany proces
  JSONL o zamkniętym zestawie operacji: DriveInfo, atrybuty ReparsePoint oraz
  tożsamość procesu. Argumenty są danymi, nie kodem. Każde zapytanie ma ID,
  walidację i wersję protokołu, limit wejścia/stdout/stderr oraz kolejki FIFO.
  Termin żądania obejmuje oczekiwanie w kolejce; dekoder poprawnie składa UTF-8.
  Nieznany ID, uszkodzony protokół lub timeout kończą własny proces.
  Błąd procesu odrzuca
  oczekujące kontrole, a nie traktuje ich jako sukces. Proces kończy się z aplikacją.
- Kontrole pozostają świeże: nie usuwamy atrybutów Windows przy preview ani
  nie uznajemy mtime/size za dowód checksumy. Zachowane lstat/realpath,
  reparse, file identity, SHA przed zmianą JPEG i reguły lock/lease.
- Zweryfikowany indeks źródła przekazujemy natywnemu controllerowi; nie
  skanujemy tego samego źródła ponownie tylko dla rejestracji podglądu.
  Wynik natywnego skanu zachowuje ułamkowe mtimeMs, powiązanie z rootem
  i fingerprint; sam zapisany inventory z całymi milisekundami nie jest proof.
  Pełny SHA każdego zaakceptowanego wyniku przy open/recovery zostaje.
- Najpierw naprawiamy dominujący koszt startu procesów. Potwierdzony kursor
  nadal jest trwale zapisany przed odpowiedzią; nie zmieniamy go na cache UI.
  Odchudzenie dziennika lub retencja receiptów mogą wejść tylko po wykazaniu
  potrzeby i zachowaniu idempotencji/historycznego recovery. Nie skracamy
  ochrony starych identyfikatorów operacji dla samego zielonego pomiaru.
- Przy LOCK_LOST zakończenie oczekuje na szereg operacji, nie usuwa cudzej
  blokady i pozwala zamknąć program z diagnostyką. Nie resetuje projektu.
- RANGE_CONFLICT chroni zaakceptowane zakresy, nie historyczne skipped.
  To przywrócenie semantyki Reviewera wymaganej D-545, nie nowa reguła produktu.
- Brakujący wynik przywraca się z kopii do zgodnej lokalizacji i używa resume;
  brak kopii wymaga diagnostyki. Nie dodajemy automatycznego naprawiania plików
  ani ręcznej edycji manifestu. Instrukcja opisze OUTPUT_MISSING_FILE.
- Scroll zapisuje ostatni widok po debounce250 ms; flush przy zamknięciu lub
  zmianie projektu nie może zgubić ostatnich ustawień ani opóźniać decyzji
  kolejką wszystkich pośrednich zdarzeń. Decyzje i kursor nie są debounce'owane.
- UI pokaże weryfikację źródła i checksum podczas open. Komunikat o trwałym
  wyborze dotyczy decyzji, nie samego przesunięcia kursora. Nieużywany picker
  nie może unieważniać podglądu aktywnego projektu.
- Nowy ZIP ma wersję0.1.1. Zachowujemy0.1.0 i jego sumy. Odbiór aktualizacji
  testujemy na własnej kopii projektu między obiema wersjami; fizyczny reboot
  oraz komputer odbiorcy nadal wymagają dowodu operatora.
- P3 poza powyższym zakresem dostaje jawne rozstrzygnięcie w Outcome. Nie
  przepisujemy historii commitów ani lockfile dla usunięcia drugiego esbuild.
  Nie przejmujemy starego pustego recovery-lock bez dowodu właściciela;
  nieznana blokada pozostaje fail-closed. Dysk wymienny nie otrzyma mylącego
  komunikatu o udziale sieciowym; nie rozszerzamy po cichu obsługi storage.

## Taski i kolejność

1. [TASK-0980](../tasks/completed/0980-selector-desktop-native-checks-and-recovery.md):
   natywne kontrole, pojedynczy indeks, backend close i reguły zakresów.
2. [TASK-0981](../tasks/completed/0981-selector-desktop-audit-ux.md):
   UI zamknięcia/weryfikacji, debounce, picker i procedury błędów.
3. [TASK-0982](../tasks/completed/0982-selector-desktop-remediated-pilot.md):
   nowy ZIP, zgodność aktualizacji, sumy i przekazanie do ponownego audytu.

0980 i0981 mogą być kodowane równolegle z rozłącznym ownership plików;
commity w kolejności0980→0981.0982 po obu commitach. Każdy task ma osobny
commit, Outcome, mapy i CURRENT_STATE. Dokumentacja jest własnością leada.

## Weryfikacja i granice

Najpierw testy zmienionych modułów, potem lint/typecheck oraz regresja trwałych
projektów i importu. Każda grupa ma rzeczywisty timeout do120 s. Bounded test
funkcjonalny na małym istniejącym fixture sprawdzi ciepłą nawigację i preview,
liczbę startów workerów, crash/timeout i brak osieroconych procesów. Nie
uruchamiamy benchmarków ani korpusów15000/dużych syntetycznych zbiorów.
Celem pomiaru jest usunięcie stałego narzutu startu procesu; nie obiecujemy
stałego czasu hashowania dowolnie dużego JPEG-a. Wyniki zapisujemy w Outcome.
Pełny/source-relink/legacy smoke poprawionego ZIP-a, test aktualizacji kopii,
docs:check i code-map:check obowiązkowe. Obce i zmienione pliki nadal blokują.

| Ustalenie | Task | Dowód |
|---|---|---|
| P1-1 |0980,0982|świeże kontrole, ograniczony pomiar, ZIP smoke|
| P2-1 |0980,0981|utrata locka i zamknięcie bez usuwania cudzych plików|
| P2-2 |0981|instrukcja przywrócenia kopii, brak resetu|
| P2-3 |0980|skipped→korekta→accepted oraz ochrona accepted|
| P2-4 |0980,0981|jeden skan, zachowany SHA, komunikat weryfikacji|
| P3 scroll/picker/komunikaty |0981|ostatni widok/flush i aktywny podgląd|
| Wydanie i audyt |0982|SHA/provenance, wersje0.1.0→0.1.1, lista uwag|

## Wynik wykonania — 2026-10-12

TASK-0980/0981/0982 zakończone w kodzie i lokalnych testach. Commity wykonania:
v1.7.324 a5ae9604, v1.7.325 892c34f1, v1.7.326 ede94bdc. ZIP 0.1.1 ma
applicationSourceDirty=false. 130 unikalnych testów PASS oraz full/shortcuts/
source-relink/legacy/UX i rzeczywista aktualizacja0.1.0→0.1.1 na własnej kopii.
[Raport dowodów](../quality/OFFLINE_PHOTO_SELECTOR_AUDIT_REMEDIATION_20261012.md)
i [rejestr paczki](../quality/OFFLINE_PHOTO_SELECTOR_ACCEPTANCE.md) podają
sumy, pełne hashe, komendy oraz ograniczenia. Końcowy audyt operatora i
fizyczny odbiór0979 pozostają pending. Oryginalny werdykt REVISE bez zmian.

## Aktualna finalizacja — 2026-10-12

Wszystkie rundy implementacji, w tym TASK-0984–0987, są wykonane na osobnej
gałęzi. Aktualna paczka to ZIP 0.1.3 z v1.7.337 /
`0b1ab3302df2119efb2519661e2f82b8bdf545df`.
[Plan finalizacji](OFFLINE_PHOTO_SELECTOR_FINALIZATION_PLAN_20261012.md)
opisuje D-546, zgodną migrację i pełną retencję receiptów.
[Aktualne dowody](../quality/OFFLINE_PHOTO_SELECTOR_FINAL_VERIFICATION_20261012.md)
obejmują 262 testy desktopu, pięć wariantów finalnego release smoke,
rzeczywiste aktualizacje 0.1.0/0.1.2 do 0.1.3 i pomiar 15 000.
Wcześniejsze wyniki w tym planie są historyczne; nie nadpisano ich.
[Końcowy brief Claude](../quality/OFFLINE_PHOTO_SELECTOR_FINAL_CLAUDE_AUDIT_BRIEF_20261012.md)
jest gotowy do przekazania operatorowi. Audyt nowych zmian i fizyczny
odbiór TASK-0979 pozostają osobne; nie są zaliczone lokalnymi testami.

## Przypisanie modeli do zadań

Wykonawcy oraz reasoning są dostępni w narzędziach tej sesji. Końcowy review
prowadzi operator; model/effort jego Claude CLI nie są tutaj weryfikowane,
więc zalecenie konkretnego audytora pozostaje warunkowe. Brak tego CLI nie
blokuje zatwierdzonej implementacji; nie ogłaszamy PASS własnego audytu.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
|TASK-0980|gpt-6.1-sol|high|Granice natywne, procesy, idempotencja, lock i recovery.|Operator po rundzie; warunkowo Claude, konfiguracja do potwierdzenia.|
|TASK-0981|gpt-6.1-sol|medium|UI i cache widoku z kontrolowanym zamknięciem.|Operator po rundzie; warunkowo Claude, konfiguracja do potwierdzenia.|
|TASK-0982|gpt-6.1-sol|medium|Wersjonowane wydanie i dowody aktualizacji kopii.|Operator po rundzie; warunkowo Claude, konfiguracja do potwierdzenia.|
