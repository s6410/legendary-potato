# Driftband per sparkonto

*Design godkänd 2026-07-18. Bakgrund: innehavsdrift inom ett konto (t.ex. 82/18
i en ISK) flaggas idag från 1 procentenhet och blir röd vid fasta 5 — vilket
uppmuntrar onödigt rebalanserande. Ett toleransband per konto (±X
procentenheter) låter små avvikelser vila.*

## Beslut

- Bandet gäller **innehavsdriften inom kontot**. Global klassdrift behåller
  dagens beteende.
- **Ett tröskelvärde** per konto (±X procentenheter), inte intervall/hysteres.
- `NULL` = inget band → exakt dagens beteende (varning ≥ 1, rött ≥ 5).

## Datamodell

Migration 006: `ALTER TABLE savings_accounts ADD COLUMN drift_band_pct REAL;`
Sätts på toppnivåkonton.

## API

- `PUT /savings/accounts/{id}/targets`: valfritt fält `drift_band_pct`.
  Skickas fältet sätts bandet (0–50, annars 422; `null` rensar). Utelämnat
  fält lämnar bandet orört (`model_fields_set`).
- `GET /savings/accounts`: returnerar `drift_band_pct`.
- `GET /savings/drift`: kontosektionerna får `band_pct`.

## UI

- "Ändra mål"-dialogen per konto får fältet "Toleransband ± procentenheter
  (valfritt)", förifyllt, tomt = inget band.
- "Fördelning inom konton": innehav inom bandet visar diskret "inom bandet
  ±4 %" i stället för Övervikt/Undervikt-varning; utanför bandet röd varning
  direkt. Kontorubriken visar "± 4 %". Utan band: dagens logik.
- Rebalanseringsförslaget i kontoscope utan nysparande: ligger alla innehav
  inom bandet visas "Allt inom toleransbandet — ingen rebalansering behövs"
  i stället för köp/sälj-listan. Med nysparande fördelas som vanligt.
- Månadssparandets köpförslag påverkas inte.

## Tester

Band persisteras via targets-PUT och syns i accounts + drift; `null` rensar;
utelämnat fält behåller; −1 och 51 → 422.
