---
title: Odbiór uczenia siatek Mumie A2 po naprawach
status: active
last_updated: 2026-11-03
---

# Uczenie siatek — odbiór rzeczywistego przebiegu 2026-11-03

Operator zatwierdził scalenie/push poprawek TASK-1136–1137, restart GPU,
wznowienie istniejącego uczenia i porównanie pozostałych siatek w HTML.
Nie jest to zgoda na publikację/aktywację nowego modelu jako default.

## Wdrożenie

- Main/origin w momencie restartu: `0a1405af6ed7b6d8ead88d27688900133cff1b42` (v1.7.533), zakres v1.7.529–533. Oba commity tasków są przodkami main. Gałąź implementacji usunięta, cudze trzy worktree zachowane.
- Preflight: fast-forward, bez migracji. Kolizja D-579 rozwiązana na D-581 (D-580 również zajęte w innym torze). Historyczne kolizje wersji v1.7.529–530 pozostawiono zgodnie ze skillem, bez przepisywania historii.
- Audyty kodu Opus 5.5/high: [1136 PASS](TASK-1136_AUDIT_claude-opus-5-5.md), [1137 PASS](TASK-1137_AUDIT_claude-opus-5-5.md). Uwagi P2 rozliczone w Outcome tasków. Ten dokument zapisuje wykonanie operacji; nie jest kolejnym audytem ani nową zmianą funkcjonalną.
- GPU: stary supervisor 52860 zatrzymany; nowy launcher 27456, supervisor 51888, start 04:51:06 UTC. Główny worker 28084 zachowany. API/Admin/Reviewer nie restartowane. Potwierdzono nowe heartbeat GPU i HTTP 200 Admina oraz zdrowie API.

## Rzeczywiste uczenie i ocena

- Gra: Mumie A2 `246a1f54-eee8-49d5-b11a-0fde70e5eecd`.
- Parent: `ecdb88d5-3808-4069-bd64-e122d52cfa62`, trening: `5eeaac0b-5e3e-4dfe-8f49-4fe618cb0837`. Te same identyfikatory, kohorta i historyczne próby; bez nowego runu.
- Kohorta `862f79ce-5a3b-51b1-9280-ab324a1e865e`, frozen revision 164: TRAIN 60 zdjęć/77 plansz, VALIDATION 13/17, REGRESSION 13/20.
- Próba 3 wznowiła checkpoint 3400, zakończyła plan 3600 kroków i eksport z parity. Checkpoint `c7e7fe78c4118c820cd577ef9fcc64ef9c171e3ced3ceb991b4577de4479f383`.
- D-581 przyjęta jeden raz: 8000 kroków / 7200 s. Finalne zużycie: 4200 skumulowanych rezerwacji, 1265,547 s, 3 próby, dokładnie jeden receipt podwyższenia. Stare zużycie 4000/1149,282 zachowane. Indywidualny skrypt +200 został wyłączony bez wykonania.
- Kandydat `0ce39122-00b0-59a3-a12f-7feee2dac5aa`, wersja `r5eeaac0b-c7e7fe78`.
- Ocena `72af65a3-0780-4f1b-a12e-6f8f2d42e3b3`, raport `b0367313-8ab2-5f4e-bde1-c3f3dd73bb85`: completed/PASS. Parent completed/PASS o 04:54:32 UTC.

| Rola | Zdjęcia | Poprawne: baza → kandydat | Błąd: baza → kandydat | Spadek błędu |
|---|---:|---:|---:|---:|
| VALIDATION | 13 | 12/17 → 14/17 | 0,01734436 → 0,01343460 | 22,54% |
| REGRESSION | 13 | 14/20 → 15/20 | 0,01483923 → 0,01220253 | 17,77% |

W obu rolach dopasowano wszystkie opisane cele. Kontrole obejmują jedynie
Mumie A2 i częściowo opisane zdjęcia: bez dowodu jakości całych zdjęć,
fałszywych detekcji poza opisanymi celami ani niezależności nagrań.
Nieznanego użycia danych w starszych przodkach nie można wykluczyć.
Progi PASS są regułą produktu, nie testem istotności statystycznej.
Pierwsza awaria procesu po 388 krokach nadal nieodtworzona; nie przypisano
jej OOM ani błędowi danych. Udane wznowienie nie jest dowodem jej przyczyny.

## Porównanie pozostałych siatek i HTML

- `artifacts/grid-learning-report-20261103/comparison.html` (także `index.html`): 230 aktualnych plansz „Zła siatka”, 147 oryginałów. Aktualność identyfikatorów, rewizji i SHA geometrii potwierdzono ograniczonym odczytem READ ONLY przed finalizacją.
- Oba modele: 147/147 odczytów poprawnych. Wykonanie CPU na oryginalnej rozdzielczości, sprawdzone SHA plików/pikseli i bundle. JPEG pomniejszono wyłącznie do wyświetlania.
- Dla 230/230 plansz istnieje przypisanie do pozycji przy 9 detekcjach obu modeli. W 218 punktowe propozycje zmieniły się średnio o ≥1 px. To liczba zmian, nie liczba poprawionych plansz: pozostałe błędne siatki nie mają zatwierdzonych celów do automatycznej oceny.
- Żadne z tych zdjęć nie było użyte w TRAIN bieżącej kohorty. Nie oznacza to braku historycznego użycia ani niezależności sesji; jedno zdjęcie uczestniczyło w REGRESSION przez opisany cel.
- Raport pokazuje zapisane cięcie, bazę i kandydata; wyszukiwanie numeru, filtry, 20 stron, CSV i przełącznik linii. Topologia pochodzi z danych planszy: 3 wiersze × 5 kolumn, 24 punkty. Podgląd czterech rzeczywistych przykładów obejrzano na `contact-sheet.png`.
- Statyczna walidacja JS w Node VM PASS: paginacja, wyszukiwanie, filtry/empty state, przełącznik, topologia, 24 punkty i wszystkie ścieżki zdjęć. Nie wykonywano automatycznego renderowania HTML w przeglądarce.
- HTML SHA-256: `1393e14a21b763f7f6bf7cc0449a69a3914647039452fc1a9880b47630aa998c`.

Nie nadpisano ręcznej geometrii ani istniejących importów. Globalny default
pozostał `158a740f-1f54-523f-94f3-508477dbea7a`, revision 1. Nowa wersja jest
kandydatem po pozytywnej ocenie; zastosowanie pozostaje osobną decyzją operatora.

## Dowody lokalne i pozostałe ograniczenia

- `artifacts/task1137-integration-preflight-final.json`, worker-stop/start/state/heartbeat, resume-response.
- `artifacts/grid-learning-report-20261103/learning-final.json`, `evaluation-final.json`, `training-final.json`, `selection-currentness.json`, `post-training-health.json`, `verification.json`, `base/`, `candidate/` i `photos/`.
- Testy kodu sprzed integracji: 95 testów workera i nowy test API PASS; 40 pozostałych testów API PASS, dwa zastane FAIL podglądu opisane w TASK-1137 i oknie. Scoped mypy, lint/format, docs/map PASS; nie przedstawiać tego jako pełnego mypy projektu.
- Wymagany restart GPU został wykonany. Nowy tag koperty budżetu oznacza, że rollback do starego readera samym cofnięciem kodu nie jest obsługiwany (D-581).
