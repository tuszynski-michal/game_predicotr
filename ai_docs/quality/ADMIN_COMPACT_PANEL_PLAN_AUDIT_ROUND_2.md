Druga runda audytu. Zweryfikowałem nowe twierdzenia o stanie: `startSymbolCodes`, `ManagementPinnedPoint` tylko z `balanceCredits`, pełny wynik bez paginacji API, manifest `v2`, komendy testów — wszystko zgodne. Notatka do wklejenia:

```markdown
# Audyt planu „Minimalistyczny Panel Administracyjny” — runda 2 (Claude, 2026-10-08)

Werdykt: **PASS z uwagami**. Wszystkie P0 z rundy 1 są rozstrzygnięte albo świadomie
zaakceptowane decyzją operatora. Sekcja „Potwierdzony stan obecny” zgadza się z kodem.
Poniżej uwagi, które warto domknąć przed materializacją tasków; żadna nie blokuje
akceptacji, ale pierwsze trzy zmieniają kontrakt i trzeba je rozstrzygnąć w TASK-0940.

## P1

1. **`DELETE` z ciałem JSON.** Potwierdzenie kasowania ma nieść `operationId`,
   `expectedRevision`, `previewToken`, `confirmed`. Ciało w `DELETE` jest legalne,
   ale nie wszystkie warstwy je przenoszą, a proxy Reviewera (`management-proxy.ts`)
   dziś rozpoznaje tylko `GET/POST/PUT` i ma ograniczone strumieniowanie ciał.
   Tokenu nie wolno przenieść do query (trafia do logów i historii). Rekomendacja:
   `POST …/delete` z ciałem JSON zamiast metody `DELETE`, spójnie dla punktu,
   maszyny i obu prefiksów.

2. **Dziennik samego usunięcia.** `management_journal.point_id` jest `NOT NULL`
   z FK `RESTRICT`, więc po skasowaniu punktu nie da się zapisać wpisu dziennika
   o tej operacji. Plan daje trwałe metadane zakresu tylko receiptom. Wymagania
   D-533 mówią, że dziennik rejestruje zmiany strukturalne. Rozstrzygnij w D-536:
   usunięcie jest widoczne wyłącznie w receipcie (i to jest akceptowane), albo
   powstaje osobna, niezmienna tabela zdarzeń kasowania bez FK. Nie zostawiaj tego
   wykonawcy.

3. **Receipt operacji kasującej nie może zostać zredagowany.** „Odpowiedzi
   związanych operacji są zastępowane znacznikiem usunięcia” musi jawnie wyłączać
   receipt samej operacji delete, inaczej retry udanego kasowania zwróci
   `409 MANAGEMENT_TARGET_DELETED` zamiast własnego wyniku, a UI uzna operację za
   nierozstrzygniętą.

4. **Migracja redagująca dawne receipty zmienia dane operatora.** Trigger
   niezmienności blokuje `UPDATE` także dla właściciela, więc migracja musi
   korzystać z tej samej flagi transakcyjnej co procedura kasowania; zapisz to.
   Zakres da się wyznaczyć deterministycznie dla każdego typu receiptu (punkt,
   maszyna, przypisania, save/clear/refresh/korekta mają identyfikatory w
   odpowiedzi lub dzienniku). `legacy_redacted` powinno być wyjątkiem z policzoną
   liczbą w preview migracji, nie domyślną ścieżką; instrukcja operatora ma
   pokazać tę liczbę przed `db:migrate`.

## P2

5. **Tabela `management_mutation_previews` bez sprzątania.** TTL 10 minut, ale
   plan nie mówi, kto usuwa wygasłe wiersze. Zapisz: ograniczone usunięcie
   wygasłych wierszy tego samego aktora przy tworzeniu nowego preview, bez
   crona i bez GC. Tabela nie jest historią, więc nie dostaje triggera
   niezmienności; dodaj ją do manifestu `v3` jako `shared`.

6. **Zależność od TASK-0933–0936.** To wiąże start panelu z etapami S-B/S-C planu
   Mumii, które jeszcze nie ruszyły. Uzasadnienie (migracje, koszt per pozycja,
   wspólne komponenty) jest słuszne; upewnij się, że operator to akceptuje jako
   kolejność, a nie tylko techniczny warunek. Jeśli S-B/S-C mają się opóźnić,
   plan potrzebuje wariantu: własny numer migracji po 0151 i ponowne
   sprawdzenie strażnika przy merge.

7. **Fingerprint preview dla dużego punktu.** Obejmuje identyfikatory wszystkich
   wpisów dziennika zakresu. Przy 40 maszynach i długiej historii to pełny skan
   przy każdym preview i potwierdzeniu. Wystarczy `count` + `max(created_at)`
   dziennika na maszynę zamiast listy ID; semantyka „każdy nowy wpis unieważnia”
   zostaje.

8. **`confirmed: true` jest nadmiarowe** przy obowiązkowym `previewToken`.
   Zostaw, jeśli ma chronić przed przypadkowym wywołaniem z klienta, ale nie
   buduj na nim logiki.

9. **Parametry URL `mpPoint/mpMachine/mpGame/mpStake`.** Zapisz, że `mpStake`
   odtwarza tylko wybór kafelka, nie otwiera edytora ze szkicem (szkic nigdy nie
   jest w URL), oraz że nieistniejące UUID są ignorowane bez błędu.

10. **Uzupełnianie starych `pinnedPoints` przy odczycie** z zamrożonego payloadu
    wymaga otwarcia pełnego `payload` wersji wyniku w `GET` summary, czyli
    dokładnie tego, czego karty miały unikać. Ogranicz do co najwyżej 6 punktów
    × 6 slotów i tylko gdy pola są `null`; albo uzupełnij raz w migracji danych
    pod tą samą flagą (wersje wyniku są niezmienne, więc tylko `stake_slots.pinned_points`).

11. **Testy roli:** dodaj przypadek „rola aplikacyjna ustawia flagę i wykonuje
    `DELETE` bezpośrednio → trigger odrzuca” oraz „właściciel bez flagi → odrzuca”.
    W tabeli pokrycia jest pierwszy; drugiego brakuje.

12. **Komenda `npm run test --workspace @game-predictor/admin-api-client`**
    uruchamia `npm run build` przed testami; w izolowanej kopii mieści się w
    120 s, ale w repozytorium operatora nadpisuje `dist`. Zaznacz, że działa
    w izolowanej kopii, albo użyj `openapi:check` jako kontroli kontraktu.

## Zgodne z rundą 1 i w porządku

Decyzje operatora 1–6 zapisane jawnie z ryzykiem; kolejność blokad i kasowania
zgodna z realnym schematem; dedup wersji wyniku sprawdzany w slotach i
dziennikach wszystkich maszyn; SECURITY DEFINER + flaga + sprawdzenie właściciela
w triggerze; manifest `v3`; `archived` zostaje w API; wariant kompaktowy nie
dotyka domyślnych konsumentów; maszyna stanów przycisków; komendy weryfikacji
istnieją w repo; tabela modeli zgodna z PLAN_STANDARD i AGENTS.md.
```

Najważniejsze do decyzji operatora: punkt 2 (czy usunięcie ma ślad w dzienniku) i punkt 6 (czekanie na S-B/S-C Mumii).