---
title: Laboratorium wizji — odbiór etapu A
status: active
last_updated: 2026-09-26
---

# Etap A — dane, galeria i baseline

## Zakres i pochodzenie

Użytkownik wznowił pracę nad silnikiem i dostarczył
`C:\Users\tuszy\Documents\new_traning_set` do testowania modelu.
Katalog docelowy to `C:\Users\tuszy\Documents\game_predictor_vision_data`.
To lokalne pliki bez powiązania z identyfikatorami DB i bez zatwierdzonych
anotacji. Sam podgląd ani wynik baseline nie kwalifikują ich do treningu.

## Wykonana kontrola wejścia

Read-only inwentaryzacja folderów, SHA-256 każdego JPEG-a i `PIL.Image.verify`
objęły wszystkie 1180 plików. Nie wykryto błędów odczytu struktury JPEG;
kontrola nie zastępuje oceny rozmycia, zasłonięć, geometrii ani etykiet.
Całość zajmuje 409110998 bajtów (około 390 MiB).

| Folder gry | Zdjęcia | Kandydaci rodzin według prefiksu |
|---|---:|---:|
| 777 | 240 | 24 |
| blazing zd | 120 | 12 |
| gang zd | 190 | 19 |
| mumie wybrane | 240 | 24 |
| reels | 230 | 23 |
| tresure zd | 160 | 16 |
| Razem | 1180 | 118 |

Występuje 1160 unikalnych sum SHA-256 i 20 par identycznych obrazów:
po 10 par `reels/REELS450100` z `reels/REELS451200` oraz
`reels/REELS471200` z `reels/REELS475500`. Wystąpienia i ich pochodzenie
muszą pozostać w manifeście. W T03 pochodne i duplikaty należą do tej samej
grupy podziału; sam prefiks nie stanowi dowodu niezależności nagrań.

Folder `777` pozostaje historycznym `comparison_only`. Pozostałe pięć
folderów jest materiałem testowym bez ustalonych podziałów i bez etykiet.
Przed użyciem treningowym obowiązują D-447 i kontrola pochodzenia z T03.

## Weryfikacja implementacji

Snapshot plikowy opublikowano pod
`C:\Users\tuszy\Documents\game_predictor_vision_data\snapshots\8a6035046a5746959c826489e2d7b0453f25b62ce04ccba80c52cd89fb38bce9`.
Importer uruchomiony ponownie w nowym procesie sprawdził pliki i zwrócił
ten sam snapshot. Kolejny proces załadował 1180 wystąpień do katalogu.

Ograniczony smoke (pierwsze zdjęcie każdej gry w kolejności manifestu,
topologia 5 × 3) dał poniższe wyniki. `complete` jest statusem propozycji
baseline; liczby nie są oceną poprawności względem ręcznej referencji.

| Gra | Status baseline | Plansze | Status complete | Zwrócone rekordy komórek |
|---|---|---:|---:|---:|
| 777 | detected | 9 | 9 | 135 |
| blazing zd | detected | 9 | 9 | 135 |
| gang zd | failed: LAYOUT_PANELS_INSUFFICIENT | 0 | 0 | 0 |
| mumie wybrane | detected | 9 | 9 | 135 |
| reels | detected, wszystkie do sprawdzenia | 9 | 0 | 60 |
| tresure zd | detected | 9 | 8 | 135 |

EXIF-transposed współrzędne mają 1080 × 688 dla próbki 777 oraz 1520 × 2704
dla pozostałych pięciu próbek. Łączny przebieg trwał około 80 s, z limitem
120 s, bez treningu i bez trwałego zapisu predykcji. Wyjście buforował
PowerShell Job; przy kontroli ciszy proces zdążył zakończyć się naturalnie.
Kontrola tożsamości procesów potwierdziła brak pozostawionego procesu smoke.

Testy końcowe: Python 19/19 (także niezależny przebieg audytora), granice
proxy UI 2/2, żądanie generowanego klienta 1/1. Ruff/format, scoped mypy
(8 modułów), ESLint, typecheck obu workspace'ów, Prettier oraz production
build UI przeszły. Główne `openapi:check` obejmuje Admin i laboratorium;
kontrakt labu nie ma dryfu.

Audyt `gpt-6-astra` / `medium`, cykl 2: brak nierozwiązanych P0–P2.
Poprawiono zachowanie `absent`/`occluded`/`unreadable` bez węzłów oraz
odczyt obrazu: pojedynczy bufor do SHA i dekodera, limit 64 MiB i kontrola
reparse przy każdym odczycie. Regresje obejmują zmianę pliku między
weryfikacją a dekodowaniem. Nieblokująca uwaga pozostaje: szersze mapowanie
wyjątków `KeyError`/`ValueError` w API może utrudniać diagnozę błędu silnika.

Odbiór przeglądarkowy obejmuje galerię 1180 zdjęć, wszystkie sześć filtrów
gier, duplikaty w `reels`, źródło z nakładką i cropami oraz jawne
`BASELINE_TOPOLOGY_UNSUPPORTED` dla 3 × 3. Sprawdzono wąski widok desktopowej
przeglądarki; nie wykonano testu na fizycznym Androidzie. Po restarcie API
odczytano 1180 źródeł, a production UI otwarto w świeżej karcie (poprzednia
karta zachowała błąd połączenia z okresu restartu).

Nie uruchomiono pełnego zestawu testów repozytorium ani benchmarku.
Nie wykonano treningu ani pomiaru jakości nowej hybrydy.

## STOP A i wejście do etapu B

Pełny folder może zasilać galerię. Pilot anotacji pozostaje ograniczony
do 40 zdjęć na grę i co najmniej 10 rodzin, jeśli są dostępne; początkowo
30 pełnych siatek na kombinację gra–topologia. Pierwsze 10 zdjęć na grę
służy pomiarowi czasu. Większa galeria nie rozszerza tego budżetu.

Wstępnym kandydatem gry niewidzianej jest `gang zd` (19 prefiksów — środkowa
liczba wśród pięciu niehistorycznych gier). To propozycja do sprawdzenia
pochodzenia i topologii w T03, a nie zamrożony wybór. Jeżeli nie ma
niezależnych rodzin lub wybór usunie jedyną topologię z treningu, T03 musi
odnotować brak wiarygodnego testu między grami.

Etap B wymaga osobnego uruchomienia. Przed instalacją T04 należy sprawdzić
GPU i dostępność przypiętych PyTorch 2.12.1, torchvision 0.27.1, CUDA 13.0
w izolowanym środowisku oraz pokazać listę i wielkość pobrań. Główne
środowisko pozostaje bez zmian. Budżet T05: do 50 kroków testowych i jeden
trening do 20 epok lub 30 minut, z kontrolowanym procesem i raportem.
