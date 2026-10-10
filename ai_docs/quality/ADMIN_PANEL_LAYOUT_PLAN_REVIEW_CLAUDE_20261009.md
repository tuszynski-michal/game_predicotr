---
title: Przegląd planu korekty układu przez Claude Code
status: active
last_updated: 2026-10-09
---

# Przegląd planu korekty układu

Audytor: Claude Code, claude-opus-5-5 / medium.
Zakres: plan z2026-10-09 i wybrane fragmenty committed baseline v1.7.291.
Jedna runda; dostęp do narzędzi wyłączony. Ocena planu nie jest odbiorem UI.

**Werdykt: REVISE.** Wymaganie operatora jest spełnione w liniach 12–13, 36–38 i 42–44: plan nie tworzy ekranu maszyny ani przycisku „Cofnij do maszyn”, lista zostaje na stronie, a workspace jest pod nią. Zakres 0947 jest wykonalny bez API i migracji, bo UUID w URL już istnieją. Poprawki wymagają jednak semantyka historii, mechanika przewijania i odbiór wizualny w 0947.

## Istniejące dowody vs przyszłe testy

- **Istniejące:** z kodu wynika, że lista maszyn jest ukryta przy wybranej maszynie (`selected && !machine`, l. 893). W nagłówku dwa przyciski prowadzą do punktów („Punkty” i „Cofnij do punktów”, l. 749–776). Retry zachowuje `pending` przy 5xx, 401/403/429 i utracie odpowiedzi (l. 500–508). Przy 4xx `pending` jest usuwany (l. 452–465). Archiwalne maszyny są odfiltrowane (l. 907). Padding ma wynik Chromium 10/10. GET API działa. Operator potwierdził, że zapis działa.
- **Przyszłe (niewykonane):** wszystko z tabeli w l. 100–102.

## P0
Brak.

## P1

1. **Plan l. 59: „bez skoku całej strony” jest sprzeczne z typową implementacją.** `element.scrollIntoView()` przewija wszystkie przewijalne przodki, czyli także dokument. Reguła do dopisania: przewijać ręcznie, zmieniając tylko `listRef.scrollTop` na podstawie `offsetTop` kafelka względem kontenera. Robić to wyłącznie przy odtworzeniu z URL lub po reload. Przy kliknięciu kafelek jest już widoczny, więc nie przewijać. Do kontenera dodać `overscroll-behavior: contain`.

2. **Plan l. 72–79: brak semantyki historii dla wyboru maszyny.** Skoro maszyna jest stanem wyboru, a nie poziomem nawigacji, trzeba ustalić, czy zmiana maszyny używa `pushState`, czy `replaceState`. Stawka dziś używa `pushState` (l. 1039). Propozycja: zmiana maszyny i gry przez `replaceState`, stawka bez zmian. Wtedy Back z punktu wraca do listy punktów, a nie przechodzi przez historię 15 kliknięć w maszyny. Dirty guard na `popstate` zostaje.

3. **Plan l. 100 i 102: odbiór wyglądu dopiero w 0949.** 0947 może zostać zatwierdzony na podstawie samego DOM, wbrew l. 107–108. W 0947 dodać jeden test Chromium z pomiarem na 390×844, 40 maszynach i wyborze maszyny nr 35:
   - wysokość listy ≤ 288px;
   - `window.scrollY` niezmienione po wyborze;
   - `document.scrollingElement.scrollWidth <= clientWidth`;
   - nagłówek workspace mieści się w pierwszych ~1,5 viewportu;
   - computed `border-color` i `background` wybranego kafelka różnią się od sąsiedniego.

## P2

1. **Plan l. 55–58: 288px na telefonie pokazuje ok. 3 kafelki z 40.** To działa, ale jest mało czytelne. Proponuję `max-height: min(288px, 40vh)`. Przy liczbie maszyn powyżej ok. 12 dodać lokalny filtr nazwy; to tylko UI, bez API. Kontener potrzebuje `role="region"`, `aria-label` i `tabIndex={0}`, żeby był dostępny z klawiatury.

2. **Fokus.** Po otwarciu punktu fokus na nagłówek (`tabIndex=-1`). Po „Cofnij do punktów” fokus na kafelek punktu, z którego wrócono. Przy zmianie maszyny fokus zostaje na klikniętym kafelku, a wybór ogłasza `aria-live="polite"` („Wybrano maszynę X”). Dla wyboru jednego z wielu `aria-current="true"` jest semantycznie trafniejsze niż toggle `aria-pressed`. Oba warianty są akceptowalne, ale trzeba przyjąć jeden.

3. **Plan l. 89–94 i 101: przywracanie archiwalnych danych.** Słusznie pozostaje propozycją. Tabela 0948 nie powinna jednak go implementować przed akceptacją. Jest też niezweryfikowana zależność: czy istniejący PATCH przyjmuje `archived=false` dla punktu i maszyny. Jeśli nie, potrzebne jest nowe API, które jest poza zakresem (l. 121). Pokazanie archiwalnych maszyn wymaga też zdjęcia filtra z l. 907.

## Ochrona szkicu, UUID i retry

Kierunek jest dobry (l. 78–87). Klucz workspace zawiera `machine.id` (l. 1020), więc zmiana maszyny powoduje remount, a guard jest niezbędny. Plan go przewiduje. Brakuje jawnego testu na 4xx przy usuwaniu: `deleteTarget` jest czyszczony (l. 461–465), więc trzeba wskazać, gdzie wtedy pojawia się komunikat błędu, skoro modal znika.

## Rekomendacje do dopisania (max 3)

1. W 0947 dodać wpis `DECISION_LOG.md`, który zastępuje część D-538 dotyczącą zagnieżdżenia maszyny (l. 14). Bez tego D-538 pozostaje źródłem prawdy w konflikcie z planem.
2. Dopisać regułę historii i scroll z P1.1–P1.2: `replaceState` dla maszyny i gry, ręczne `scrollTop` tylko przy odtworzeniu, `overscroll-behavior: contain`.
3. Przenieść pomiar Chromium z P1.3 do kryteriów odbioru 0947. Z 0948 wydzielić przywracanie jako osobny, warunkowy task po akceptacji produktu i sprawdzeniu `archived=false` w API.

Przegląd statyczny planu, bez zmian w plikach.

## Odpowiedź autora planu — jedna runda korekt

Pierwotny werdykt Claude dotyczy wersji planu przed poniższą korektą. Autor
nie nadaje audytorowi nowego PASS; to zapis odpowiedzi na wskazane uwagi.

| Uwaga | Odpowiedź i stan |
|---|---|
| P1.1 scroll | Zamknięta w planie: zmiana wyłącznie scrollTop nazwanego regionu przy URL/reload, bez przewijania na klik; overscroll containment |
| P1.2 historia | Zamknięta w planie: punkt/Home pushState, maszyna/gra/stawka replaceState. Wszystkie wybory zastępują ten sam wpis, więc Back nie przechodzi przez stawki |
| P1.3 odbiór0947 | Zamknięta w planie i tasku: Chromium390x844/40 maszyn/35. wybór przed zamknięciem0947, z geometrią, scrollY i computed stanem wybrania |
| P2.1 region | Wysokość min(288px,40dvh), role/nazwa/tabIndex dopisane. Filtr nazw odłożony: dodatkowa funkcja nie jest konieczna dla tej korekty |
| P2.2 fokus | Nagłówek punktu/źródłowy kafelek Home, zachowany fokus maszyny, aria-pressed i ogłoszenie aria-live jawnie określone |
| P2.3 historyczny restore | Warunkowy zakres do akceptacji planu. Transport sprawdzony w źródłach: PUT w api/management.py; command.archived w storage/management_repository.py, bez nowego API |
|4xx delete | Dopisano osobny test: po zamknięciu dialogu błąd409/422 widoczny na stronie punktu; wyjątki401/403/429 zachowują obecny kontrakt |
| Decyzja D-539 | Już zapisana podczas tworzenia planu przed review; brief nie obejmował całego procesu. D-539 zastępuje wyłącznie maszynę jako poziom nawigacji |

Nie wykonano ponownego audytu ani implementacji. Uwagi planu zamknięto przez
konkretne reguły i kryteria przyszłego odbioru; to nie dowód spełnienia ich w UI.
