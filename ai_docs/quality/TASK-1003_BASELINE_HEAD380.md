# TASK-1003 — pełny baseline interakcji Admina przed zmianą

Data: 2026-10-15. Weryfikacja uzupełniająca po Claude R2 PASS, bez zmian kodu
i testów, bez kolejnego audytu. Nie jest to raport nowego audytora.

Pełny zestaw `test:geometry` na źródłach v1.7.380 /
`a688a40108f33ede3a894002a6fc8a8ed53d8141`: **215 PASS,10 FAIL,225 testów**,12.109s,
limit120s. Po TASK-1003 zestaw miał **226 PASS,10 FAIL,236 testów**.
Wszystkie dziesięć nazw nieudanych testów i komunikatów wyjątków jest
identycznych. Każdy błąd dotyczy `undefinedSeriesCountLabel` w
`super-game-series-state.ts:101`, wywołanego z `SeriesList` w
`super-game-series-workspace.tsx:905`. Błąd występował przed TASK-1003.
Różna liczba testów wynika ze zmiany zestawu interakcji panelu1003;
nie przedstawiamy wcześniejszego zestawu jako tych samych236 przypadków.

## Metoda i ograniczenia

- Wyeksportowano przez Git wyłącznie `apps/admin`, `packages` i manifesty
  root z dokładnego commita380 do ignorowanego katalogu dowodów. To eksport
  źródeł, nie osobny Git worktree. Każdy plik porównano z obiektem Git;
  dopuszczono wyłącznie potwierdzoną konwersję LF/CRLF zgodną z checkoutem.
  697 plików źródeł i kopii pakietów sprawdzono SHA256 przed/po teście.
- Wewnętrzne pakiety rozwiązują się do kopii tych samych zweryfikowanych
  źródeł. Zależności zewnętrzne pochodzą z istniejącej instalacji; nie
  instalowano pakietów ani nie budowano aplikacji. Uruchomiono tę samą
  komendę TSX/tsconfig/wzorzec wszystkich plików interakcji co npm script.
- Pierwsza kontrola eksportu zatrzymała się przed testem na Windows CRLF,
  następna na zabronionym tworzeniu junction. Nie uruchamiały testów.
  Po sprawdzeniu kanonicznych obiektów Git użyto zwykłych kopii pakietów.
  Jedyna pełna próba testów zakończyła się powyższym FAIL. Wrapper po
  zapisaniu JSON napotkał błąd kodowania konsoli cp1250; dowody i wyniki
  są kompletne, odczytano je z plików bez ponownego uruchamiania testu.
- PID36648 zakończony, brak usług, bazy, GPU i mutacji roboczego kodu.
  Nie wykonano testu na fizycznym urządzeniu ani pełnego builda.

## Dowody i rozstrzygnięcie

W `artifacts/audits/`: `TASK-1003_HEAD380_ADMIN_geometry.log`,
`TASK-1003_HEAD380_ADMIN_BASELINE.json`, `TASK-1003_HEAD380_ADMIN_SOURCE_SHA.json`
i `TASK-1003_BASELINE_COMPARISON.json`. Log SHA256:
`18e2c8e6cde28d328ec90a45f28877934257e86e8476e4f7fc2b85a8a8ca6024`. JSON baseline SHA256:
`9f069314cf1d4486bb50068e8572d0e3de78b3d8623aa6268afbf09713454196`. Zachowano niezmienione logi R2.

P2-8 otrzymuje pełny dowód istniejących dziesięciu błędów interakcji;
ograniczenie helper-only zostało uzupełnione. Pełny zestaw nadal jest
czerwony i pozostaje długiem poza zakresem1003. Nie zastosowano xfail,
zmiany asercji, naprawy SuperGame ani fikcyjnego PASS. Końcowy odbiór1001
porównuje aktualne błędy z tym baseline i nie ignoruje nowych regresji.
Raporty Claude i historyczne wyniki zachowują pierwotną treść.
