---
title: Remote source browser capability spike
status: accepted
last_updated: 2026-08-23
---

# Remote source browser capability spike

## Decyzja

`GO_WITH_CONSTRAINTS` dla rozpoczęcia TASK 2 browser-only MVP.

Spike potwierdza, że zdalny operator może indeksować i oglądać jedną lokalną
partię bez masowego uploadu, a uchwyt katalogu można przechować przez structured
clone w IndexedDB. Architektura nie może jednak zakładać trwałego permission po
restarcie przeglądarki. Każde wznowienie musi wykonać `queryPermission`, a przy
braku uchwytu lub dostępu udostępnić bezpieczny relink.

Decyzja nie jest zgodą na publiczny rollout. Przed nim nadal wymagany jest
ręczny test natywnego pickera i odmowy/regrant na docelowych wersjach Chrome i
Edge.

## Granica spike'u

- Fixture istnieje wyłącznie pod `apps/reviewer/test/fixtures` i nie jest trasą
  Next ani częścią produkcyjnego UI.
- Nie dodano API, bazy, uploadu, tunelu ani publicznego linku.
- Katalog źródłowy jest proszony wyłącznie o permission `read`.
- Manifest zawiera wyłącznie względną nazwę, rozmiar, mtime i MIME. Nie czyta
  `arrayBuffer`, nie dekoduje JPEG-a i nie przechowuje ścieżki absolutnej.
- OPFS był użyty wyłącznie jako bezpieczny uchwyt testowy do sprawdzenia
  structured clone; nie zastępuje ręcznego testu katalogu OS.

## Macierz przeglądarek

| Środowisko | `showDirectoryPicker` | Handle w IndexedDB | Fallback | Decyzja |
| --- | --- | --- | --- | --- |
| Chrome desktop | secure context + gest | tak, permission sprawdzany ponownie | `webkitdirectory` + relink | wspierane MVP |
| Edge desktop | secure context + gest | tak, permission sprawdzany ponownie | `webkitdirectory` + relink | wspierane MVP |
| Firefox/Safari | brak gwarancji | brak gwarancji | tylko sesyjny wybór, gdy dostępny | poza zobowiązaniem MVP |

Źródła sprawdzone 2026-08-23:

- [MDN `showDirectoryPicker`](https://developer.mozilla.org/en-US/docs/Web/API/Window/showDirectoryPicker),
- [WICG File System Access](https://wicg.github.io/file-system-access/),
- [Chrome File System Access](https://developer.chrome.com/docs/capabilities/web-apis/file-system-access),
- [MDN file input](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/input/file).

## Wynik rzeczywistego smoke testu Chromium

Lokalny fixture uruchomiono na `http://127.0.0.1` bez tunelu. Przeglądarka
zgłosiła:

```json
{
  "secureContext": true,
  "showDirectoryPicker": true,
  "indexedDb": true,
  "originPrivateFileSystem": true,
  "webkitDirectoryFallback": true,
  "recommendedMode": "directory_handle"
}
```

Zaliczone scenariusze:

1. zapis uchwytu OPFS do IndexedDB i natychmiastowy odczyt,
2. odczyt tego samego uchwytu po reloadzie,
3. odczyt po zamknięciu karty i otwarciu nowej,
4. w każdym przypadku `kind=directory`, permission `granted`.

Nieautomatyzowane na tym etapie:

- zaakceptowanie natywnego pickera katalogu OS,
- zamknięcie całej przeglądarki i ponowny regrant,
- jawna odmowa permission,
- wybranie katalogu przez fallback `webkitdirectory`.

Fixture ma wszystkie te akcje. Pozostają bramką przed publicznym rolloutem,
ale nie blokują wydzielenia wspólnego core w TASK 2.

## Manifest i relink

`remote-source-manifest-v1`:

- normalizuje ścieżki do NFC,
- odrzuca absolute path, backslash, pusty segment, `.` i `..`,
- sortuje numerycznie i deterministycznie,
- blokuje duplikat relative path,
- ma checksumę SHA-256 kanonicznej zawartości,
- rozróżnia relink `same`, `different` i `incompatible`.

Fallback `webkitdirectory` jest zawsze oznaczony
`webkitdirectory_reselect`. Po reloadzie użytkownik ponownie wskazuje folder, a
aplikacja porównuje manifesty przed wznowieniem.

## Benchmark syntetyczny

Raport mierzy budowę metadanych i checksumy, bez decode i bez czytania bajtów.
Pierwszy pomiar zawiera cold start WebCrypto, dlatego nie służy do porównywania
przepustowości z kolejnymi próbami.

| Pliki | Decode | Odczyt bajtów | Wynik |
| ---: | ---: | ---: | --- |
| 1 | 0 | 0 | zaliczony |
| 500 | 0 | 0 | zaliczony |
| 1000 | 0 | 0 | zaliczony |

Dokładne czasy, rozmiary i checksumy znajdują się w wersjonowanym raporcie JSON.

## Artefakty

- `ai_docs/quality/remote-source-capability-report-v1.json`
- `ai_docs/quality/remote-source-capability-report-v1.schema.json`
- checksum raportu:
  `f04dc14c87b93f2bf69b56e1025364db32209d2e673f7214db3424965f69cd9e`

Weryfikacja:

```powershell
node apps/reviewer/test/run-remote-source-capability-spike.mjs --check
```

## Ograniczenia przekazane do TASK 2+

1. Wspólny core nie może zakładać trwałego uchwytu ani permission.
2. Source adapter musi obsługiwać `permission_required`, `relink_required` i
   `source_changed`.
3. Relink porównuje manifest przed wznowieniem.
4. W pamięci i IndexedDB nie przechowujemy blobów całej partii.
5. Zamknięcie karty zatrzymuje transfer; trwały outbox odtwarza pracę po
   powrocie.
6. MVP wspiera Chrome/Edge desktop. Pozostałe przeglądarki nie mają obietnicy
   trwałego wznowienia.
