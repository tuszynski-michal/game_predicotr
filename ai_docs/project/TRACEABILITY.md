---
title: Requirements traceability
status: active
last_updated: 2026-07-29
---

# Mapa śledzenia wymagań

| Obszar | Dokument źródła prawdy | Milestone |
|---|---|---|
| Android całkowicie offline | `requirements/MOBILE_APP.md`, `architecture/SYSTEM_ARCHITECTURE.md` | M1 |
| Brak uprawnienia `INTERNET` w finalnym APK | `requirements/MOBILE_APP.md` | M1.6 |
| Prywatny APK na 3–5 urządzeń | `requirements/MOBILE_APP.md` | M1, M8 |
| Nowy APK aktywuje właściwy snapshot | `requirements/MOBILE_APP.md`, D-012, D-020 | M1.1, M3.4 |
| Header: game, undo, reset | `requirements/MOBILE_APP.md` | M1 |
| Plansza 3 × 5 i row-major | `requirements/MOBILE_APP.md` | M1 |
| Selection 10–12 symboli | `requirements/MOBILE_APP.md` | M1 |
| Modal jednego kandydata | `requirements/MOBILE_APP.md`, `requirements/ALGORITHMS.md` | M1 |
| Local exact/prefix lookup | `requirements/ALGORITHMS.md`, `architecture/DATA_MODEL.md` | M1 |
| Duplikat bez confirmation chain | `requirements/ALGORITHMS.md`, D-008 | M1 |
| Cykliczna sekwencja `N - 1` | `requirements/ALGORITHMS.md`, D-009 | M1 |
| PAYLINE po jednym polu na kolumnę | `requirements/ADMIN_APP.md`, `requirements/ALGORITHMS.md` | M1–M2 |
| Edytor i zakaz duplikatu payline | `requirements/ADMIN_APP.md` | M2 |
| Joker | `requirements/ALGORITHMS.md` | M1 |
| Sumowanie wszystkich prawidłowych linii | `requirements/ALGORITHMS.md` | M1 |
| Payout od pierwszej kolumny | `requirements/ALGORITHMS.md`, D-019 | M1–M2 |
| Minimum długości per symbol, domyślnie 3 | `requirements/ADMIN_APP.md`, `architecture/DATA_MODEL.md`, D-019 | M1–M2 |
| Kredyty symbol + długość od minimum | `requirements/ALGORITHMS.md`, `requirements/ADMIN_APP.md` | M1–M2 |
| Spin 0 bez kosztu/payoutu | `requirements/ALGORITHMS.md` | M1 |
| Koszt każdego ocenianego spinu | `requirements/ALGORITHMS.md` | M1 |
| Kumulacja wszystkich payoutów po drodze | `requirements/ALGORITHMS.md` | M1 |
| Dodatnie lokalne maksima i plateau | `requirements/ALGORITHMS.md`, D-009 | M1 |
| Tabela Target na dole i wirtualizacja | `requirements/MOBILE_APP.md` | M1 |
| Admin gier, symboli i reguł | `requirements/ADMIN_APP.md` | M2 |
| PostgreSQL jako baza kanoniczna | `architecture/DATA_MODEL.md`, D-005 | M2 |
| Precomputed payout i SQLite | `architecture/DATA_MODEL.md`, D-005 | M1, M3 |
| Panel przygotowania Android release | `requirements/ADMIN_APP.md`, `architecture/API_CONTRACT.md` | M3 |
| Ręczne dostarczenie danych | `delivery/ROADMAP.md` | M4 |
| Zdjęcia z telefonu i perspektywa | `requirements/IMAGE_INGESTION.md` | M5 |
| 9 layoutów na zdjęciu | `requirements/IMAGE_INGESTION.md` | M5 |
| OCR numeru pod layoutem | `requirements/IMAGE_INGESTION.md` | M5 |
| Około 100 próbek na symbol | `requirements/IMAGE_INGESTION.md` | M6 |
| Manual review | `requirements/IMAGE_INGESTION.md`, `requirements/ADMIN_APP.md` | M6 |
| Minimalistyczne zatwierdzanie całej planszy | `requirements/ADMIN_APP.md`, D-086 | M6.5 |
| Klawiatura, tooltip sugestii i pojedynczy zapis Enter | `requirements/ADMIN_APP.md` | M6.5 |
| Wersjonowana korekta geometrii z recrop | `requirements/IMAGE_INGESTION.md`, `architecture/DATA_MODEL.md` | M6.5 |
| Ochrona decyzji człowieka przed retrainingiem | `requirements/IMAGE_INGESTION.md`, D-086 | M6.5 |
| Kontrolowana publikacja ręcznie zweryfikowanego zakresu | `requirements/IMAGE_INGESTION.md`, D-086 | M6.5, M7 |
| Ograniczony zdalny link i kod review | `requirements/ADMIN_APP.md`, D-087 | M8.7 |
| Masowy wznawialny import | `requirements/IMAGE_INGESTION.md` | M7 |
| Skala 500 000 layoutów na grę | `project/PROJECT_BRIEF.md`, `quality/TEST_STRATEGY.md` | M3, M7 |
| Analiza aplikacji referencyjnej | `reverse_engineering/REFERENCE_APP_ANALYSIS.md`, Q-020 | opcjonalne |

## Plany wykonawcze

- M1: `delivery/MILESTONE_01_EXECUTION_PLAN.md`,
- M2: `delivery/MILESTONE_02_EXECUTION_PLAN.md`,
- M3: `delivery/MILESTONE_03_EXECUTION_PLAN.md`,
- M4: `delivery/MILESTONE_04_EXECUTION_PLAN.md`,
- M5: `delivery/MILESTONE_05_EXECUTION_PLAN.md`,
- M6: `delivery/MILESTONE_06_EXECUTION_PLAN.md`,
- M6.5: `delivery/MILESTONE_06_5_EXECUTION_PLAN.md`,
- M7: `delivery/MILESTONE_07_EXECUTION_PLAN.md`,
- M8: `delivery/MILESTONE_08_EXECUTION_PLAN.md`.

Plany wykonawcze mapują wymagania na kolejność podetapów, zadania i bramki, ale
nie zastępują dokumentów źródła prawdy wskazanych w tabeli.

## Reguła utrzymania

Przy dodaniu nowego wymagania:

1. wpisz je do właściwego dokumentu źródła prawdy,
2. wskaż milestone,
3. dodaj lub zaktualizuj wiersz tej tabeli,
4. nie traktuj samego wiersza jako pełnej specyfikacji.
