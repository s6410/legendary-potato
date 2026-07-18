# Månadssparande med sparplan och utökad sparande-dashboard

*Design godkänd 2026-07-18. Bakgrund: användaren månadssparar 5 000 kr i ISK med
fonder. Sparande-sidan visar idag bara totala värden och kan inte skilja insatt
kapital från avkastning. En sparplan per konto ger uppdelningen insatt/avkastning,
prognoser och månatliga köpförslag — utan manuell loggning av varje insättning.*

## Beslut från brainstorming

- **Sparplan, inte insättningsloggning**: appen antar att planbeloppet sätts in
  varje månad. Faktiska insättningar bokförs inte.
- **Fördelningen mellan fonder återanvänder kontots målfördelning** (`target_pct`
  per innehav) — ingen egen fördelning per plan.
- **Planen startar "nu"** (valfritt startdatum, men ingen bakåträkning av
  historik): kontots värde vid planstart blir startkapital, där tidigare
  klumpinsättningar ingår.
- **Dynamiska prognosvärden**: scenarioprocent och eget målbelopp är
  användarinställningar, inte hårdkodade konstanter.

> **Revidering 2026-07-18 (efter driftsättning):** startkapitalet lagras inte
> längre i `start_value_ore` (kolumnen finns kvar men används inte). Insatt
> kapital beräknas live: kontots värde vid *första* planradens start (ur
> snapshots vid läsning) + alla antagna insättningar över raderna. Det rättar
> två buggar: (1) plan skapad/ändrad innan värden matats in fick startkapital 0
> och visade hela kontovärdet som avkastning; (2) plan med framtida startdatum
> visade avkastning i stället för 0 — nu räknas dagens värde som startkapital
> tills planen startar. Dessutom: en omsparad plan vars gamla rad startade i
> samma kalendermånad ersätter raden helt (rättning) i stället för att kedjas
> (beloppsbyte).

## Datamodell

Ny tabell `savings_plans`:

| Kolumn | Typ | Beskrivning |
|---|---|---|
| `id` | INTEGER PK | |
| `savings_account_id` | INTEGER FK → `savings_accounts.id`, ON DELETE CASCADE | Måste vara toppnivåkonto (`parent_id IS NULL`) |
| `monthly_amount_ore` | INTEGER | > 0, t.ex. 500 000 (5 000 kr) |
| `start_date` | DATE | Default idag |
| `start_value_ore` | INTEGER | Ackumulerat insatt kapital vid radens start |
| `end_date` | DATE NULL | NULL = aktiv; max en aktiv rad per konto |

**Insatt kapital** vid datum D (för den planrad som är aktiv vid D) =
`start_value_ore` + antal månadsinsättningar sedan `start_date` t.o.m. D ×
`monthly_amount_ore`. Insättningar antas ske samma månadsdag som startdatumet;
dag 29–31 klampas till månadens sista dag (31 jan → 28/29 feb).

- Vid planstart: `start_value_ore` = kontots senaste totala värde ≤ startdatum
  (0 om inga snapshots).
- Vid beloppsändring: aktiv rad får `end_date`, ny rad skapas med
  `start_value_ore` = ackumulerat insatt kapital vid bytet. Historiken förblir
  korrekt över kedjade rader.

## API

- `PUT /savings/accounts/{id}/plan` — skapa eller ersätt aktiv plan:
  `{monthly_amount_ore, start_date?}`. Validering: kontot är toppnivå (annars
  422), belopp > 0 (annars 422). Ersättning kedjar planrader enligt ovan.
- `DELETE /savings/accounts/{id}/plan` — avslutar aktiv plan (`end_date` = idag);
  historiken behålls. 404 om ingen aktiv plan.
- `GET /savings/plan-summary?rates=4,7,10&goal_ore=...` — per konto med plan:
  - plan: `monthly_amount_ore`, `start_date`
  - `invested_ore` (idag), `current_value_ore`, `return_ore`, `return_pct`
  - dessutom totalrad över alla konton med plan
  - `forecast`: per inskickad procentsats (1–3 st, validerade 0–30 %, annars
    422): årliga punkter (år 0–30) med månadsvis ränta-på-ränta
    (`v ← v·(1+r/12) + månadsbelopp`), beräknat på summan av konton med plan
  - `milestones`: de tre närmaste beloppen över dagens värde ur
    100k/250k/500k/750k/1M/1,5M/2M plus ev. `goal_ore`, med första datum de nås
    per scenario
- `GET /savings/history` utökas med `invested`-serie: ackumulerat insatt kapital
  (summa över konton med plan) per datum; `null` före första planstart.
- Scenarioprocent och målbelopp persisteras via befintligt inställnings-API
  (`settings`), nycklar `savings_forecast_rates` och `savings_goal_ore`.
  Frontend läser inställningarna och skickar dem som query-parametrar.

Månadens köpförslag kräver inget nytt API: frontend återanvänder
`GET /savings/rebalance?account_id=X&contribution=<planbelopp>` (water-filling
mot innehavens målfördelning, justerat för drift).

## UI (Sparande-sidan)

1. **Toppkortet** "Totalt sparande" blir nyckeltalsrad: totalt värde · insatt
   kapital · avkastning (+X kr / +Y %). Utan plan visas bara totalt värde som
   idag.
2. **Nytt kort "Månadssparande"**: "5 000 kr/mån till ISK sedan [datum]" med
   knappen *Ändra* samt *Avsluta*; därunder **månadens fördelning** mellan
   kontots innehav enligt målfördelning justerat för drift (t.ex. 4 100 kr
   LF Global, 900 kr räntefond). Konto utan innehav: hela beloppet till kontot.
   Utan plan visas "Starta månadssparande".
3. **Historikgrafen** får en streckad, ostackad linje "Insatt kapital".
4. **Nytt kort "Prognos"**: graf med en bana per scenarioprocent (mittersta
   framhävd) och milstolpstext, t.ex. "500 000 kr nås ca mars 2029 vid 7 %".
   Procentsatserna är inmatningsfält i kortet (förifyllda 4/7/10 första gången)
   och ett valfritt eget målbelopp — båda sparas i inställningarna.

Plandialogen: välj konto (endast toppnivå), belopp kr/mån, startdatum (default
idag), med text om att fördelningen följer kontots målfördelning.

**Refaktorering som del av arbetet**: `Savings.tsx` (~750 rader) delas upp —
befintliga dialoger och de nya korten flyttas till
`frontend/src/components/savings/` så varje fil håller sig väl under 800 rader.

## Felhantering & kantfall

- Plan på innehav (barn) → 422. Belopp ≤ 0 → 422. Ogiltiga rates → 422.
- Konto utan snapshots vid planstart: startkapital 0.
- Konto med aktiv plan raderas → planrader kaskadraderas.
- Avkastning kan bli negativ; visas med minustecken och "bad"-färg.
- `return_pct` definieras som `return_ore / invested_ore` (0 om insatt är 0).

## Tester

Backend (pytest, samma mönster som befintliga savings-tester):

- Månadsdagslogik: antal insättningar över månadsskarvar, 31:a → 28/29 feb.
  Insättning nr 1 sker på startdatumet; occurrences = antal förfallodagar i
  [start_date, D].
- Insatt kapital vid beloppsbyte (kedjade rader).
- plan-summary: invested/return/return_pct, totalrad, forecast-värden mot
  handräknat facit, milstolpsdatum inkl. eget målbelopp.
- history: invested-serien, null före planstart.
- API: plan på innehav → 422, belopp ≤ 0 → 422, rates utanför 0–30 → 422,
  PUT ersätter (kedjar), DELETE avslutar, DELETE utan plan → 404,
  kaskadradering med kontot.
