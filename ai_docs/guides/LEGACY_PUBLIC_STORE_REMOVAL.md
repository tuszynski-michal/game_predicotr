---
title: Operacyjne usunięcie legacy game-owned relations z public
status: active
last_updated: 2026-09-26
---

# Runbook: `0125_remove_legacy_public_game_store`

## Granica operacji

Ten runbook dotyczy tylko 65 historycznych, game-owned tabel z zamrożonego
manifestu `game-data-v2-manifest-v1`. Usuwa je wyłącznie Alembic revision
`0125_remove_legacy_public_game_store`, z `DROP TABLE … RESTRICT`.

Nie są kandydatami do usunięcia: `public.games`, `symbols`, `rules_versions`,
`rules_version_symbols`, `paylines`, `payout_rules`, globalne `jobs`,
`game_storage_*`, `alembic_version` ani shared/control plane. Nie używaj
ręcznego SQL, `CASCADE`, downgrade, globów nazw ani skryptu kopiującego dane.

`game_data_v2` pozostaje jedynym data plane gier; `public` nadal jest catalog,
control i shared plane.

## Role i warunek rozpoczęcia

Operator wykonuje tylko komendy z tego dokumentu. Właściciel zmiany przegląda
wynik preflightu i wydaje osobne, pisemne potwierdzenie apply. Zatwierdzenie
planu, wynik wcześniejszego rehearsal albo komunikat „wykonaj cały plan” nie
jest tym potwierdzeniem.

Przed rozpoczęciem potwierdź identyfikator release i używane środowisko bez
wypisywania URI bazy lub sekretów:

```powershell
Set-Location C:\Users\tuszy\Documents\game_predicotr
git rev-parse HEAD
.\.venv\Scripts\alembic.exe current
if ($LASTEXITCODE -ne 0) { throw 'Nie można odczytać bieżącej rewizji Alembic.' }
```

Planowany release musi być tym samym, który przeszedł readiness T08, a
rewizja przed apply ma być
`0124_game_data_v2_partial_visibility_constraints`. Nie przechodź dalej,
jeżeli jest inna albo `alembic current` nie zwróci jednoznacznego wyniku.

## Preflight: jedyna dozwolona ścieżka przed apply

W zamkniętym oknie maintenance, bez aktywnego importu, uruchom jedną świeżą
sesję audytu. Skrypt ustawia `REPEATABLE READ READ ONLY`, `statement_timeout`
15 s, `lock_timeout` 5 s i zapisuje atomowy raport bez URI ani haseł.

```powershell
Set-Location C:\Users\tuszy\Documents\game_predicotr
$reportName = 'legacy-public-preflight-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json'
$reportPath = Join-Path $PWD (Join-Path 'ai_docs\quality' $reportName)
& .\.venv\Scripts\python.exe scripts\audit_legacy_public_game_store.py --report $reportPath
if ($LASTEXITCODE -ne 0) { throw 'Preflight nie jest ready; nie uruchamiaj Alembic.' }
$reportHash = (Get-FileHash -LiteralPath $reportPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "PreflightReport=$reportPath"
Write-Output "PreflightSha256=$reportHash"
```

Akceptowalny wynik ma kod wyjścia `0`, status `ready` oraz dokładnie te
warunki w pliku raportu:

- 65 istniejących relacji `public`, każda `relkind = r` i `rowCount = 0`;
- wszystkie location to `game_data_v2`, generation co najmniej 2, manifest v1
  i `active`;
- brak aktywnej migracji, jobów `created`/`processing`, obcych locków,
  zewnętrznych FK i zewnętrznych zależności relacji.

Każdy inny exit code lub blocker — w tym niepustość, missing/drift relacji,
lock, timeout, aktywny job albo location nie-V2 — oznacza **STOP bez DDL**.
Zachowaj raport, checksumę, `git rev-parse HEAD` oraz `alembic current` do
decyzji właściciela. Nie naprawiaj wyniku ręcznym `DROP`, nie wyłączaj locków
ani triggerów i nie próbuj automatycznie ponownie.

## Wymagane, osobne potwierdzenie

Po pokazaniu świeżego raportu właściciel musi wysłać komunikat obejmujący jego
dokładną ścieżkę i checksumę, np.:

> Zatwierdzam jednokrotne uruchomienie `alembic upgrade
> 0125_remove_legacy_public_game_store` dla raportu `<ścieżka>` o SHA-256
> `<hash>`. Zakres to wyłącznie 65 pustych tabel legacy game-owned z
> manifestu v1; catalog/control/shared `public` i `game_data_v2` pozostają.

Brak tej zgody, niezgodność hash/path albo raport starszy niż bieżące okno
maintenance oznacza STOP. Nie pytaj skryptu o tekst potwierdzenia i nie
zastępuj go zmienną środowiskową: to decyzja człowieka na podstawie widocznego
raportu.

## Apply — tylko po zgodzie

Bezpośrednio po zatwierdzonym preflightcie i bez równoległych importerów
wykonaj jedną komendę. Migracja sama ustawia `lock_timeout = 2s` oraz
`statement_timeout = 30s`, ponownie blokuje wszystkie 65 tabel i przed
pierwszym dropem sprawdza ich rodzaj, pustość oraz zewnętrzne zależności.

```powershell
Set-Location C:\Users\tuszy\Documents\game_predicotr
& .\.venv\Scripts\alembic.exe upgrade 0125_remove_legacy_public_game_store
if ($LASTEXITCODE -ne 0) { throw '0125 nie zakończyła się sukcesem; zatrzymaj operację.' }
```

Nie kontynuuj po błędzie. Zapisz czas błędu, output Alembic, wcześniej
zatwierdzony raport i checksumę. `0125` jest transakcyjna; nie uruchamiaj
`downgrade` ani nie odtwarzaj pustych tabel. Przed następną decyzją wykonaj
wyłącznie ponowny, read-only preflight i ręczny przegląd katalogu.

## Postflight

W nowej sesji wykonaj ten sam audit i utrwal drugi raport oraz checksumę.
Po sukcesie jego status `blocked` jest **oczekiwany wyłącznie**, gdy każdy
blocker ma kod `LEGACY_PUBLIC_STORE_TABLE_MISSING` i dotyczy 65 legacy tabel;
inne kody są postflight failure.

```powershell
Set-Location C:\Users\tuszy\Documents\game_predicotr
$postflightName = 'legacy-public-postflight-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json'
$postflightPath = Join-Path $PWD (Join-Path 'ai_docs\quality' $postflightName)
& .\.venv\Scripts\python.exe scripts\audit_legacy_public_game_store.py --report $postflightPath
$postflightExitCode = $LASTEXITCODE
$postflightHash = (Get-FileHash -LiteralPath $postflightPath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "PostflightExitCode=$postflightExitCode"
Write-Output "PostflightReport=$postflightPath"
Write-Output "PostflightSha256=$postflightHash"
& .\.venv\Scripts\alembic.exe current
if ($LASTEXITCODE -ne 0) { throw 'Nie można odczytać rewizji po apply.' }
```

Odbiór T09 wymaga `0125_remove_legacy_public_game_store`, dokładnie 65
oczekiwanych blockerów missing-table oraz braku pozostałych blockerów.
Raport nadal potwierdza aktywne location V2, brak aktywnych migration/jobs i
brak obcych locków. Dodatkowy postflight T10 potwierdza API i worker na nowym
procesie; nie uruchamiaj go na produkcji bez kolejnego scope'u taska.

Jeżeli raport nie został zapisany, hash nie daje się policzyć, revision nie
jest `0125`, liczba/kody blockerów się nie zgadzają albo dowolna kontrola
catalog/control/shared/V2 zawiedzie, zatrzymaj D i przekaż komplet pre/post
raportów do ręcznej oceny. Nie ma automatycznego rollbacku.

## Dowód rehearsal i retencja

Przed T09 operator dołącza do zmiany: hash preflightu, hash postflightu,
rewizję aplikacji, revision Alembic przed/po, czas rozpoczęcia/zakończenia oraz
output migration. Rehearsal T06 na PostgreSQL 18.4 znajduje się w
`ai_docs/quality/LEGACY_PUBLIC_STORE_MIGRATION_REHEARSAL.md`; nie jest
substytutem produkcyjnego preflightu.
