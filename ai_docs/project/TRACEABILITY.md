---
title: Requirements traceability
status: active
last_updated: 2026-07-23
---

# Mapa śledzenia wymagań

| Pierwotny obszar | Dokument źródła prawdy | Milestone |
|---|---|---|
| Android jako główny klient | `requirements/MOBILE_APP.md` | M1 |
| Header: game, undo, reset | `requirements/MOBILE_APP.md` | M1 |
| Plansza 3 × 5 i row-major | `requirements/MOBILE_APP.md` | M1 |
| Selection 10–12 symboli | `requirements/MOBILE_APP.md` | M1 |
| Modal jednego kandydata | `requirements/MOBILE_APP.md`, `requirements/ALGORITHMS.md` | M1 |
| Exact layout lookup | `requirements/ALGORITHMS.md`, `architecture/API_CONTRACT.md` | M1 |
| Powtarzające się layouty | `requirements/ALGORITHMS.md` | M1 |
| Confirmation przez kolejny layout | `requirements/ALGORITHMS.md`, `architecture/API_CONTRACT.md` | M1 |
| Admin gier i symboli | `requirements/ADMIN_APP.md` | M2 |
| Wzorce wygranych | `requirements/ADMIN_APP.md`, `requirements/ALGORITHMS.md` | M2–M3 |
| Joker | `requirements/ALGORITHMS.md`, Q-009 | M3 |
| Sumowanie wygranych | `requirements/ALGORITHMS.md`, Q-010 | M3 |
| Koszt spinu | `requirements/ALGORITHMS.md` | M4 |
| Maksymalnie 100 000 pozycji | `requirements/ALGORITHMS.md` | M4 |
| Tabela rosnących wyników | `requirements/ALGORITHMS.md`, Q-013 | M4 |
| Ręczne dostarczenie danych | `delivery/ROADMAP.md` | M5 |
| Zdjęcia z telefonu i perspektywa | `requirements/IMAGE_INGESTION.md` | M6 |
| 9 layoutów na zdjęciu | `requirements/IMAGE_INGESTION.md`, Q-002/Q-016 | M6 |
| OCR numeru pod layoutem | `requirements/IMAGE_INGESTION.md` | M6 |
| Próbki symboli 10–20 | `requirements/IMAGE_INGESTION.md` | M6–M7 |
| Manual review | `requirements/IMAGE_INGESTION.md`, `requirements/ADMIN_APP.md` | M7 |
| Masowy import 500k | `requirements/IMAGE_INGESTION.md` | M8 |
| Dostarczenie danych do mobile | Q-001/Q-018, `architecture/SYSTEM_ARCHITECTURE.md` | M9 |
| Analiza aplikacji kolegi | `reverse_engineering/REFERENCE_APP_ANALYSIS.md` | opcjonalne |

## Reguła utrzymania

Przy dodaniu nowego wymagania:

1. wpisz je do właściwego dokumentu źródła prawdy,
2. wskaż milestone,
3. dodaj lub zaktualizuj wiersz tej tabeli,
4. nie traktuj samego wiersza w tej tabeli jako pełnej specyfikacji.
