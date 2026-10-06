# Mumie — diagnoza preflightu2575 zdjęć

## Wynik odczytu

- Gra: fea55cc1-ebf4-4cee-b3ab-a520017ed1be.
- Folder:1 - 23175 cut; staging b770bcc8-0002-4de0-ad01-60efa82d4835.
- Job:1e5c0d7d-d317-4dc8-98da-068f1ac65d28, completed.
- Policy: page-geometry-preflight-v13-neural-mumie-pilot; wariant klasyczny null.
- Model: neural_grid, grid_profile_mumie_v1, Run5bc981568c3f42bd96f6f9238e57aedc,
  eksport iteration03-f896da7196431be2. Nie użyto starego silnika.
- Manifest SHA: dac92fddb8857f05c0f6286314a7c6347adc9e5eb27bdfd0de470fcdc5e2f015.

## Struktura istniejących wyników

Odczyt niezmiennego manifestu i istniejących funkcji neural_pending_payload
oraz full_neural_prediction_geometry, bez ponownej inferencji lub zapisu DB:

| Wynik | Liczba |
| --- | ---: |
| Zdjęcia, jednoznacznie przypisane |2575 |
| Wykryte i przypisane plansze |23175 |
| Pełne siatki spełniające neural-auto-crop-v1 |23175 |
| Sloty niespełniające tej kwalifikacji |0 |
| review_required / NEURAL_GRID_GATE_UNCALIBRATED |2575 |

Worker nadaje niekalibrowaną flagę wszystkim propozycjom niezależnie od
pełności. Przed TASK-0891 UI interpretował tę flagę jak obowiązek ręcznej
korekty każdego zdjęcia oraz pokazywał coverage0/2575, chociaż D-523 już
dopuszcza automatyczne cięcie pełnych siatek. Naprawa zmienia prezentację,
nie geometrię, approval ani źródła treningowej prawdy.

Kwalifikacja strukturalna nie potwierdza dokładności każdego podziału.
Rzeczywiste błędy pikseli należy oznaczać jako Zła siatka; dobre cropy
weryfikować zbiorczo. Import pozostaje osobną akcją operatora.

Dowody lokalne: artifacts/mumie-preflight-diagnosis-20261007/jobs.json,
summary.json i analyze_manifest.py. Analiza zakończona w36,92s. Nie zapisano
do bazy, nie uruchomiono importu, nowego treningu ani aktywacji.

## Weryfikacja naprawy

TASK-0891 poprawia znaczenie licznika, pokazuje2575/2575 przeanalizowanych
zdjęć i dokładny eksport sieci. Zamknięty podgląd nie pobiera szczegółowych
propozycji wszystkich źródeł (manifest ma270,98 MB). Dalszy import pozostaje
dostępny bez akceptacji każdego zdjęcia. Pełny jawny podgląd i walidacja
raportu nadal mają koszt odczytu dużego manifestu; nie dodano paginacji API.

Testy jednostkowe68/68 i interakcji30/30, lint/format/types oraz finalny
build30,20s przeszły. Główny raport sprawdzono po kontrolowanym restarcie API;
staging, model i wyniki zostały odtworzone, a zamknięty podgląd nie wysłał
review-sources. Widok390×844 nie ma poziomego przepełnienia. Dowody:
main-report.png, main-proposals.png i main-mobile.png w katalogu artefaktów.
