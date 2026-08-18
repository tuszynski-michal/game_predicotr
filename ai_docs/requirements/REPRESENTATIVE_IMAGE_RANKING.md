---
title: Supervised representative image ranking
status: accepted
last_updated: 2026-08-18
---

# Supervised ranking reprezentantów

Ręczna zakładka pozostaje niezależnym i pełnoprawnym fallbackiem. Po jawnej
akcji operatora worker może zamrozić ślad sesji i wyliczyć kohortę per gra.
Kandydat jest używany wyłącznie wtedy, gdy został zdekodowany i wyświetlony co
najmniej 300 ms. `Enter` jest silnym pozytywem, `Tab` nie jest negatywem, a
`Ctrl+Z` usuwa etykietę z kohorty.

Kohorta zapisuje checksumy, ścieżki, folder źródłowy, zakres oraz względną
pozycję obrazu. Model dostaje siedem surowych `ImageQualityMetrics` bez
`overall_score` oraz względną pozycję, razem osiem cech. Używany jest
deterministyczny MLP `8 → 16 → 8 → 1` z ReLU i pairwise logistic loss.
Standaryzacja, seed, metryki i checksum ONNX są częścią snapshotu.

Trening odbywa się między partiami na skumulowanej kohorcie jednej gry. Split
jest deterministyczny po folderach i ciągłych blokach zakresów. Niejednoznaczne
pary są raportowane i wykluczane; JPEG-i nie są kopiowane do bazy.

Pierwszy snapshot działa tylko w trybie `shadow`: raportuje ranking pięciu
kandydatów, ale nie zmienia grup, zakresów, limitu pięciu weryfikacji ani pliku
wynikowego. Promocja wymaga co najmniej 300 zaakceptowanych grup, 1000 pewnych
par i dwóch folderów oraz osobnej akceptacji właściciela.
