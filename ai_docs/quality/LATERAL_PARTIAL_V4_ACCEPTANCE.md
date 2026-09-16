---
title: Lateral partial v4 real-corpus acceptance
status: accepted
last_updated: 2026-09-08
---

# Odbiór realnego korpusu v0.10.4

## Decyzja

Bramka TASK-0515 przeszła i testowy wariant
`structured_lattice_v4_partial_sides` może być jawnie wybrany dla nowego runu.
Nie zmienia to domyślnego v3, polityki gry ani obowiązku ręcznego potwierdzenia
propozycji `pending_partial`.

Raport jest związany z:

- korpusem `edb75cd8a55027903174076223f36d1ba94e96c74e165677abd3e86985aec519`,
- polityką `b016d18db566155d5e4ce0c30d486dfaa896185e9c1d844ff94e0bb6ea4f6c97`,
- raportem `002466ef722bdd555207b1f5af42bb8485c4cfb221b4414bd313a4a05caeb54f`.

Maszynowe źródła dowodu to
`lateral-partial-v4-real-corpus-v1.json` oraz
`lateral-partial-v4-real-acceptance-v1.json` w tym katalogu.

## Korpus i niezależność

Korpus ma 32 unikalne checksumy rzeczywistych JPEG-ów:

- 5 pełnych stron z bieżących, ręcznych override'ów `local-owner` i managed
  originals; każda strona ma 9 poświadczonych quadów,
- 27 zaakceptowanych ręcznie źródeł plansz z immutable golden M5.

Dla pięciu stron profil rejestracji jest source-disjoint: checksum badanego
źródła jest wykluczona z kotwic, a ORB działa bezpośrednio na rzeczywistych
cropach RGB. Te przypadki są dowodem całego przepływu rejestracja →
kandydatura → lokalny fit. Indeks z rzeczywistych cropów zawiera 9 kandydatur
lewych i 6 prawych. Dodatkowe 27 źródeł wykorzystuje
poświadczony quad jako jawny obszar wyszukiwania i bada wyłącznie lokalny fit,
maskę oraz negatywy; nie jest to dodatkowy pomiar trafności ORB.

W TASK-0515 nie strojono progów na korpusie (`tuningSourcesUsed = 0`). Korpus
M5 był wcześniej materiałem projektu, dlatego wynik nie jest deklaracją
ślepej generalizacji na inne gry. Jest ograniczonym, checksum-bound odbiorem
realnych pikseli dla tej rodziny źródeł.

`C:\Users\user\Documents\777` nie dostarczył dodatkowych poświadczonych quadów:
znaleziony indeks 2200 cropów miał puste wyniki. Nie importowano go i nie
uzupełniano przez zgadywanie. Baza oraz managed originals były tylko czytane;
derived cropy powstały wyłącznie w pamięci. Końcowa bramka ponownie sprawdziła
SHA-256 wszystkich 32 źródeł.

## Wynik bramki

| Miara | Wynik |
|---|---:|
| Pełne plansze | 72 |
| v3 / v4 zaakceptowane pełne | 70 / 70 |
| Scenariusze boczne | 84 |
| Propozycje boczne | 34 |
| Odzyskane lewe / prawe | 15 / 19 |
| Pozostawione do ręcznej korekty | 50 |
| Negatywy pionowe / ambiguous / missing | 96 |
| Indeks błędów | 0 |
| Wszystkie decyzje/scenariusze | 252, bez utraty i duplikatów |

Każda z bramek jest zielona: brak regresji pełnych plansz, przesunięć kolumn,
cropów wymagających brakujących pikseli, akceptacji pionowych/ambiguous/missing,
driftu replay i zmiany checksum źródeł. Każda propozycja ma niezależnie
wyliczoną maskę oraz dowód z rzeczywistego `VirtualCellRenderer`: wyrenderowane
są dokładnie dostępne indeksy, bez cropów wymagających brakujących pikseli.
Odrzucenia boczne pozostają widoczne w 50-elementowym `manualIndex`; nie są
przeliczane na sukces.

## Czas

Pomiar był parowany na tych samych 72 pełnych planszach, po 5 powtórzeń na
wariant, z naprzemienną kolejnością:

| Wariant | Mediana | p95 |
|---|---:|---:|
| v3 | 62,05305 ms | 101,401 ms |
| v4 | 62,39175 ms | 97,412 ms |

Łączna parowana różnica v4 wyniosła `-0,003978` (-0,3978%), przy dopuszczalnym
narzucie do 10%.
Windows i OpenCV wprowadzają szum czasowy, dlatego źródłem decyzji jest łączny
pomiar parowany, a nie pojedyncza próbka.

## Powtórzenie

W PowerShell z katalogu repozytorium:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_lateral_partial_v4.py --timing-repeats 5
```

Zwykłe uruchomienie nie czyta bazy i zapisuje wyłącznie raport w repozytorium.
`--freeze-from-reviewed` jest osobnym, jawnym eksportem metadanych: czyta
aktualne rewizje i zapisuje tylko manifest korpusu; nie wolno go używać jako
importu ani migracji danych.

## Ograniczenia operatorskie

- Wariant jest testowy i tylko opt-in per run; v3 pozostaje domyślny.
- Automatyczna propozycja nie renderuje pól i wymaga ręcznego potwierdzenia.
- 50/84 cropów bocznych poprawnie pozostało manualnych; coverage nie wynosi
  100% i nie powinno być przedstawiane jako takie.
- Guard rebind, brak zgodnego preflightu, brak managed JPEG-a lub drift SHA
  nadal blokują start zgodnie z istniejącym kontraktem.
- Nie wykonano reimportu, migracji, restartu ani mutacji danych operatora.
