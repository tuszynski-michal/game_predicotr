---
title: Finalizacja selektora po pełnym audycie Claude
status: accepted
last_updated: 2026-10-12
---

# Finalizacja lokalnego selektora — TASK-0984–0987

## Stan obecny, zgoda i cel

Kod ZIP0.1.2 z c4181f7ddc8fca2518c2d9abc363ce3bcd307d5f ma niezależny
PASS Claude rundy2,140 testów i otwarte P2-A–P2-E/P3-A–P3-E.
Raport: `quality/OFFLINE_PHOTO_SELECTOR_REAUDIT_CLAUDE_20261012.md`.
Operator polecił dokończyć wszystkie zadania i wyraźnie zaakceptował nową
rundę3–5 h: wszystkie poprawki, zgodną migrację zapisu, testy, kontrolowany
pomiar15000 JPEG i nowy ZIP. Odbiór przez operatora nastąpi na samym końcu.
Nie obniżamy limitu15000. Poprzednie raporty i paczki pozostają historyczne.

Cel: gotowa paczka0.1.3 z zamkniętymi uwagami implementacyjnymi i pełnym
zestawem dowodów; fizyczny odbiór TASK-0979 pozostaje odrębny.
Worktree `D:\game_predicotr\worktrees\offline-photo-selector`, gałąź
`codex/offline-photo-selector`; baza tej rundy v1.7.332 /
`c7b9d52ea09b22b4a5f174d4ce8212a242a43eca`.

## Reguły funkcjonalne i błędy

- Źródło, decyzje i wyniki zostają lokalnie. Jeden picker zdjęć, foldery
  `<źródło> selekcja` i `<źródło> wybrane` obok niego, etykieta gry i historia.
- Brak projektu z historii nigdy nie powoduje automatycznego resetu.
  Komunikat zawiera ścieżkę i możliwość wskazania przeniesionego projektu
  przez Otwórz projekt. Nowa partia wymaga jawnego potwierdzenia; usuwa tylko
  martwy wpis cache, nie pliki. Niewybrana/anulowana akcja zachowuje pracę.
- Historia preferuje najnowszy wpis i usuwa duplikaty projectRoot przy remember.
  Tożsamość źródła/id nadal sprawdzana pod lockiem przed odzyskiwaniem.
- Oba docelowe foldery są sprawdzane przed utworzeniem któregokolwiek.
  Niepusty obcy folder dostaje osobny kod/pełną ścieżkę; nic nie jest usuwane.
  Otwieranie obcego katalogu bez markerów projektu nie tworzy locka.
- Repeat Enter/F/Tab/Ctrl+Z/A nie uruchamia accept/skip/undo; strzałki mogą
  powtarzać nawigację. Zmiana dotyczy desktopu, bez zmiany Reviewera/rdzenia.
- LOCK_LOST i LOCK_OWNER_UNKNOWN przy close kończą własny store, logują
  problem i nie usuwają obcej blokady. Zapis pozostaje zablokowany.
- Drugie uruchomienie w trakcie zamykania planuje jedno ponowne otwarcie
  po zakończeniu własnego procesu, zamiast cichego braku reakcji.
- Hipoteza zimnego WMI nie jest diagnozą. Identity ma ograniczone ponowienie
  i pomiar czasu, nigdy nie uznaje timeoutu za martwy proces. Smoke zachowuje
  logi przy błędzie i sprząta tylko własne procesy/fixture'y po weryfikacji.

## Trwałość i wydajność — D-546

Logiczny ProjectState schema1 i operator-local v2 pozostają zgodne.
Nowy format dyskowy head2 używa istniejących nazw primary/backup. Inventory
oraz baseline są niezmienne, adresowane checksumą i mają niezależne kopie.
Baseline zapisuje konfigurację, decyzje i wszystkie dotychczasowe receipty
jednorazowo. Dwa mirrory append-only ledgeru przechowują nowe operacje.
Nie usuwamy starych operationId ani nie osłabiamy idempotencji.

Head wskazuje inventory/baseline, projectId, rewizję, długość zatwierdzonego
prefixu, chain hash, stan kursora/numeracji i bindings katalogów. Journal3
operacji zawiera before/after heads, dokładny record, copy/removals i fazę.
Record przechowuje receipt, skalary i deltę decyzji none/append/pop/clear,
bez roots. Relink zmienia tylko zweryfikowane bindings head/journalu.

Commit: intent prepared → JPEG pod output lease → journal jpeg_written →
fsync identycznego recordu w obu ledgerach → primary head → journal committed
→ zgodny manifest → backup head → release lease → usunięcie journalu →
potwierdzenie. Recovery dopisuje tylko brakujący, dokładnie zgodny suffix
pending recordu. Nadmiar/inne bajty blokują; bez journalu nie uznajemy ogona
za zatwierdzony. Zdrowa kopia odtwarza uszkodzoną tylko po dowodzie zgodności.
Obie uszkodzone kopie zatrzymują zapis. Inventory/baseline też mają backup.

Migracja pod lockiem: odczyt starego stanu i kontrola expected source/id →
pełne recovery journal1/2 → atomowy descriptor upgrade journal3 z dokładnym
starym stanem → zapis/zweryfikowanie sidecarów i dwóch ledgerów → primary
head2 → backup head2 → usunięcie descriptoru. Descriptor blokuje starszego
readera przed publikacją; po migracji obie stare nazwy mają schema2.
Awaria każdego kroku jest wznawialna. Manifest i JPEG-i podczas upgrade nie
zmieniają się. Nie zostawiamy używanego legacy backupu jako fallbacku.

Pełna walidacja open/upgrade jest O(N+R+D), z Set ścieżek zamiast R*N.
Operacja waliduje deltę i nowy receipt. Współdzieli immutable inventory,
nie klonuje dwukrotnie całego stanu ani nie przepisuje indeksu receiptów.
Publiczny snapshot pozostaje odizolowany; odpowiedź UI korzysta z bezpiecznej
projekcji bez całej historii receiptów. Pełny manifest O(D), SHA przy open
oraz memoria O(N+R+D) pozostają jawnymi kosztami. Brak nowej gwarancji przy
utracie zasilania/fsync katalogu Windows; potwierdzamy awarie procesu.

## Taski i kolejność

0984 →0985 →0986 →0987. Każdy ma osobny commit, Outcome i zapis stanu.

| Wymaganie / uwaga | Task | Dowód |
|---|---|---|
| Martwa historia, obce foldery, nowa partia bez resetu P2-A/D |0984| Regresje start/resume, anulowanie, tożsamość i niezmienione obce dane |
| Repeat i zamykanie P2-C/P3-A/B |0984| Testy handlerów oraz rzeczywistego EXE/relaunch |
| Koszt inventory/receiptów P2-B |0985,0987| Fault/retry/upgrade, stare ID, pomiar15k przed/po i nowy proces |
| Diagnostyka start/update P2-E |0986,0987| Timeout/retry/logs, błędny smoke z zachowanym logiem i czysty finalny przebieg |
| Zawartość asar P3-E |0986| Automatyczne archive/build-info/provenance checks |
| Dokumentacja i odtworzenie JPEG P3-C/D |0987| Spójne taski/plan/rejestr i instrukcja decisions[].imagePath + SHA |
| Gotowa paczka i oba kierunki |0987| ZIP0.1.3, sumy, sześć scenariuszy i aktualizacje0.1.0/0.1.2→0.1.3 |

## Weryfikacja, audyt i granice

Najpierw testy zmienionego pionu, lint/typecheck, następnie cały desktop,
rdzeń/zgodność Reviewera gdy potrzebna, code-map i docs:check. Komendy używają
istniejącego run-bounded.mjs, maksymalnie120 s. Finalny release i scenariusze
są kontrolowanymi buildami, oczekiwane po kilkadziesiąt sekund.
Kontrolowany pomiar15000 jest wyraźnie autoryzowany; własne syntetyczne JPEG,
bez danych operatora. Raport podaje sprzęt, p50/p95, koszty etapów, liczby
operacji i rozmiary plików. Cel inżynierski dla małych fixture: ciepłe NAV
p50<500 ms i brak ponownego zapisu inventory/historii na krok; wynik jest
pomiarem, nie uniwersalną gwarancją dla dowolnego dysku/JPEG. Nie ograniczamy
retencji i nie usuwamy testów dla zieleni.

D-545 zachowuje polecenie operatora: audyt krzyżowy wykonuje operator na końcu,
bez lokalnego CLI gate i bez zastępowania Claude inną rodziną. Możliwy
wewnętrzny przegląd kodu przez Codex jest weryfikacją inżynierską, nie audytem
krzyżowym. CLI Claude nie jest obecnie dostępne. Plan dopisuje gotowy brief
końcowy, nie udaje niezależnego PASS nowych zmian. Fizyczny odbiór0979
(komputer odbiorcy/reboot/dystrybucja/ochrona) nie jest lokalnym smoke.
Bez uploadu/linków/chmury, zmian API/Admin/Reviewera/bazy, usług operatora,
instalatora/podpisu, danych użytkownika, push ani merge.

## Przypisanie modeli do zadań

Wykonawcy potwierdzeni w narzędziach sesji. Review Claude pozostaje warunkowe:
konfigurację i dostępność potwierdza operator przy końcowym audycie zgodnie
z D-545; nie stanowi bramki implementacji tej rundy.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0984 | gpt-6.1-sol | medium | Ograniczone poprawki startu, ochrony plików i zdarzeń UI. | Warunkowo claude-sonnet-5-5 / medium, audyt operatora na końcu. |
| TASK-0985 | gpt-6.1-sol | high | Migracja, journal/ledger, odporność na awarie i idempotencja. | Warunkowo claude-sonnet-5-5 / high, audyt operatora na końcu; wewnętrzny review gpt-6-astra / high. |
| TASK-0986 | gpt-6.1-sol | medium | Ograniczone timeouty, diagnostyka i kontrola paczki. | Warunkowo claude-sonnet-5-5 / medium, audyt operatora na końcu. |
| TASK-0987 | gpt-6.1-sol | medium | Finalny ZIP, pomiar i dowody całego przepływu. | Warunkowo claude-sonnet-5-5 / medium, audyt operatora na końcu. |
