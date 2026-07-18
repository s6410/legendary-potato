# Engångsinsättningar på sparkonton

*Design godkänd 2026-07-18. Bakgrund: användaren har gjort stora
engångsinsättningar i två fonder på ISK (kontoutdrag Handelsbanken apr–jun 2026)
utöver det stående månadssparandet. Sparplanen modellerar bara månadsbelopp, och
klumpinsättningar efter planstart visas därför felaktigt som avkastning.
Engångsinsättningar registreras som egna händelser och räknas in i insatt
kapital — värdeuppdateringar efter en insättning tolkas då inte som avkastning.*

## Beslut

- **Egen tabell, inte planrader**: en engångsinsättning är en faktisk händelse
  (datum + belopp) och blandas inte ihop med antaget månadssparande.
- **Per toppnivåkonto**, precis som sparplaner — insatt kapital följs per konto,
  inte per innehav.
- **Negativt belopp = engångsuttag.** Belopp 0 avvisas.
- **Snapshotkonvention**: en värdepunkt på datum D antas inkludera insättningar
  gjorda t.o.m. D (man uppdaterar värdet efter köpet). Baslinjen justeras därför
  så att en insättning med snapshot samma dag inte dubbelräknas.
- **Prognoskortet kräver fortsatt aktiv plan.** Konton med enbart
  engångsinsättningar (ingen plan) syns i grafens "Insatt kapital"-linje men
  inte i plan-summary — prognosen bygger på månadsbelopp.

## Datamodell

Ny tabell `savings_deposits` (migration 007):

| Kolumn | Typ | Beskrivning |
|---|---|---|
| `id` | INTEGER PK | |
| `savings_account_id` | INTEGER FK → `savings_accounts.id`, ON DELETE CASCADE | Måste vara toppnivåkonto |
| `deposit_date` | DATE | |
| `amount_ore` | INTEGER | ≠ 0; negativt = uttag |
| `note` | TEXT NULL | T.ex. "Arv", "Flytt från Avanza" |

## Beräkningslogik (`savings_plan.py`)

Med `oneoffs(≤ D)` = summan av kontots engångsinsättningar t.o.m. D:

- **`invested_at(D)`** = baslinje + planinsättningar t.o.m. D + `oneoffs(≤ D)`.
- **Första startdatum** = min(första planradens start, första insättningens
  datum). `invested_at` är `None` före det — insatt kapital-linjen börjar där.
  Fungerar även för konton helt utan planrader.
- **Baslinjen** (startkapitalet) subtraherar engångsinsättningar t.o.m. sitt
  referensdatum, eftersom snapshotvärdet redan innehåller dem:
  - Värden finns bakåt: baslinje = kontovärde vid första start −
    `oneoffs(≤ senaste värdepunkten ≤ första start)` — en äldre värdepunkt
    innehåller ju inte senare insättningar.
  - Första värdepunkten senare (bakdaterat): baslinje = första värdet −
    antagna planinsättningar dittills − `oneoffs(≤ första värdepunkten)`
    (befintlig "avkastning 0 fram till första värdet"-konvention).
- **`invested_series`** omfattar konton med planrader ∪ konton med insättningar.
- **`plan_summary`** räknar in engångsinsättningar i `invested_ore` för konton
  med aktiv plan (oförändrat urval).

## API

- `GET /savings/accounts/{id}/deposits` — kontots insättningar, senaste först.
- `POST /savings/accounts/{id}/deposits` — `{deposit_date, amount_ore, note?}`.
  Validering: konto finns (404), toppnivå (422), belopp ≠ 0 (422), giltigt
  datum (422).
- `DELETE /savings/deposits/{id}` — 204, 404 om okänd.

## UI (Sparande-sidan)

- Ny knapp **"Insättningar"** i sidhuvudet (bredvid "Uppdatera värden") öppnar
  en dialog: kontoväljare (toppnivå), formulär (datum, belopp i kr — negativt =
  uttag, valfri anteckning) och kontots befintliga insättningar med borttagning.
- Historikgrafens "Insatt kapital"-linje hoppar automatiskt vid insättningar
  (inget grafarbete behövs).

## Felhantering & kantfall

- Insättning på innehav (barn) → 422 med hänvisning till kontot.
- Insättning + snapshot samma dag → ingen dubbelräkning (se snapshotkonvention).
- Insättning daterad före planstart → flyttar insatt kapital-linjens start bakåt.
- Konto raderas → insättningar kaskadraderas (FK).
- Uttag kan göra insatt ≤ 0 → `return_pct` skyddas redan (`invested > 0`).

## Tester

Backend (pytest, `test_savings_deposits.py`):

- `invested_at` med insättning efter/före planstart, samma dag som snapshot
  (ingen dubbelräkning), bakdaterat utan tidiga värden, konto utan plan, uttag.
- Användarscenariot ur kontoutdraget: klumpar + månadsspar → avkastning =
  värde − omkostnadsbelopp.
- `plan_summary` och `history.invested` inkluderar insättningar.
- API: skapa/lista/radera, validering (innehav, belopp 0, ogiltigt datum,
  okänt konto), kaskadradering.
