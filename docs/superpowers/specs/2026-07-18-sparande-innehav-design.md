# Innehav med målfördelning per sparkonto

*Design godkänd 2026-07-18. Bakgrund: drift fanns bara globalt per tillgångsklass;
användaren behöver målfördelning och drift mellan innehav (fonder) inom ett konto,
t.ex. ett ISK med två fonder på 82 %/18 %.*

## Datamodell

`savings_accounts` får två nya kolumner:

- `parent_id INTEGER NULL` → FK till `savings_accounts.id`. Ett innehav är ett
  sparkonto med förälder. Max en nivå: innehav kan inte ha egna barn (API-validering).
- `target_pct REAL NULL` → innehavets målandel inom förälderkontot.

Innehav har fritt namn oberoende av tillgångsslag — två aktiefonder i samma ISK
hålls isär per innehav. Tillgångsslaget (`asset_class`) sätts per löv och används
för den övergripande klassdriften.

## Värderegler

- Snapshots får bara sättas på löv (innehav, eller konto utan innehav). Försök på
  förälder → 422.
- Förälderns värde = summan av barnens senaste värden.
- Ett konto som redan har snapshots kan inte få innehav → 422 (skydd mot dubbelräkning).
- Delete av förälder tar bort innehaven och all deras historik (bekräftas i UI).

## API

- `POST/PATCH /savings/accounts`: nya fält `parent_id`, `target_pct`.
- `PUT /savings/accounts/{id}/targets`: sätter alla innehavens mål atomiskt,
  summan valideras till 99–101 % (samma regel som klassmålen).
- `GET /savings/accounts`: returnerar `parent_id`, `target_pct`; föräldrar får
  `latest_value_ore` = summa av barnens senaste värden.
- `GET /savings/drift` utökas med:
  - `accounts`: per förälder med innehav — innehavens `value_ore`, `current_pct`,
    `target_pct`, `drift_pct`, `drift_ore`.
  - `by_account`: total fördelning per toppnivåkonto (`value_ore`, `share_pct`).
  - `classes` beräknas hädanefter över löven.
- `GET /savings/rebalance?account_id=`: water-filling över kontots innehav;
  utan `account_id` som idag över tillgångsklasser. Algoritmen generaliseras så
  båda nivåerna delar kod.

## UI (Sparande-sidan)

- Kontolistan visar innehav indragna under sitt konto, "+ Innehav"-knapp per konto.
- Ny dialog "Nytt innehav": namn, tillgångsslag, målandel %.
- "Uppdatera värden" listar bara löv, grupperade per förälder.
- Nytt kort "Fördelning inom konton": per konto med innehav visas nuvarande andel
  vs mål (samma stapelvisualisering som klassdriften) + driftbadge i procentenheter
  och kronor, samt måljustering med 100 %-validering.
- Rebalanseringskortet får väljare: hela sparandet (tillgångsklasser) eller ett
  enskilt konto (innehav).
- Klassdrift och historikgraf i övrigt oförändrade.

## Tester

- Service: föräldersummering, kontodrift (82/18), klassdrift över löv,
  rebalansering per konto.
- API: snapshot på förälder → 422, barn-till-barn → 422, konto med snapshots får
  ej innehav → 422, målsumma ≠ 100 % → 422, drift-svarets struktur, delete-kaskad.
