"""Genererar testfixturer som efterliknar riktiga svenska bankexporter.

Körs en gång: python generate_fixtures.py  (skriver filer i samma katalog)
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).parent


def swedbank() -> None:
    # Kommaavgränsad, decimalpunkt, Windows-1252, preamble-rad som börjar med *
    lines = [
        "* Transaktioner Period 2026-05-01 - 2026-06-30 Skapad 2026-07-01 08:15 CEST",
        "Radnummer,Clearingnummer,Kontonummer,Produkt,Valuta,Bokföringsdag,Transaktionsdag,"
        "Valutadag,Referens,Beskrivning,Belopp,Bokfört saldo",
        '1,8327-9,123 456 789-0,Privatkonto,SEK,2026-06-28,2026-06-27,2026-06-28,'
        'ICA SUPERMARKET SÖDER,"ICA SUPERMARKET SÖDER",-482.50,12345.67',
        '2,8327-9,123 456 789-0,Privatkonto,SEK,2026-06-27,2026-06-26,2026-06-27,'
        'SL,"SL Access",-930.00,12828.17',
        '3,8327-9,123 456 789-0,Privatkonto,SEK,2026-06-25,2026-06-25,2026-06-25,'
        'LÖN,"Lön Arbetsgivaren AB",35200.00,13758.17',
        '4,8327-9,123 456 789-0,Privatkonto,SEK,2026-06-24,2026-06-23,2026-06-24,'
        'SYSTEMBOLAGET,"SYSTEMBOLAGET 0123 STOCKHOLM",-356.00,-21441.83',
    ]
    (HERE / "swedbank.csv").write_bytes("\r\n".join(lines).encode("cp1252"))


def nordea() -> None:
    # Semikolon, decimalkomma, YYYY/MM/DD, UTF-8 med BOM, en Reserverat-rad
    lines = [
        "Bokföringsdag;Belopp;Avsändare;Mottagare;Namn;Rubrik;Saldo;Valuta",
        "2026/06/30;-1250,00;;;Willys Stockholm;Kortköp;8450,25;SEK",
        "Reserverat;-89,00;;;Espresso House;Kortköp;;SEK",
        "2026/06/28;-349,00;;;Comviq;Autogiro;9700,25;SEK",
        "2026/06/27;-89,00;;;Espresso House;Kortköp;10049,25;SEK",
        "2026/06/25;1500,00;Kalle Karlsson;;Swish inbetalning;Swish;10138,25;SEK",
    ]
    (HERE / "nordea.csv").write_bytes(("\n".join(lines)).encode("utf-8-sig"))


def seb() -> None:
    # XLSX: 4 metadatarader, header på rad 5
    wb = Workbook()
    ws = wb.active
    ws.append(["Privatkonto", "5000 12 345 67"])
    ws.append(["Saldo", "24 512,80"])
    ws.append(["Disponibelt belopp", "24 512,80"])
    ws.append([])
    ws.append(["Bokföringsdatum", "Valutadatum", "Verifikationsnummer",
               "Text/mottagare", "Belopp", "Saldo"])
    rows = [
        (date(2026, 6, 29), date(2026, 6, 29), "5490123456", "PRESSBYRAN/26-06-28", -45.0, 24512.80),
        (date(2026, 6, 27), date(2026, 6, 27), "5490123455", "WIRSTRÖMS PU/26-06-26", -180.0, 24557.80),
        (date(2026, 6, 25), date(2026, 6, 25), "5490123454", "LÖN", 41000.0, 24737.80),
        (date(2026, 6, 24), date(2026, 6, 24), "5490123453", "HYRA BOSTADS AB", -11500.0, -16262.20),
    ]
    for r in rows:
        ws.append(list(r))
    wb.save(HERE / "seb.xlsx")


def entercard() -> None:
    # Användarens PDF→CSV-skill: semikolon, decimalkomma, köp POSITIVA
    lines = [
        "Transaktionsdatum;Bokföringsdatum;Beskrivning;Belopp",
        "2026-06-26;2026-06-28;BAUHAUS SICKLA;1249,00",
        "2026-06-20;2026-06-22;SAS 117-2345678901 STOCKHOLM;3890,00",
        "2026-06-15;2026-06-16;SPOTIFY AB;169,00",
        "2026-06-10;2026-06-11;INBETALNING, TACK;-8450,00",
    ]
    (HERE / "entercard.csv").write_bytes("\n".join(lines).encode("utf-8"))


def amex() -> None:
    # XLSX, köp positiva, betalningar negativa
    wb = Workbook()
    ws = wb.active
    ws.append(["Datum", "Beskrivning", "Kortmedlem", "Belopp"])
    rows = [
        (datetime(2026, 6, 27), "COOP KONSUM SOLNA", "E KARLSSON", 823.5),
        (datetime(2026, 6, 21), "APPLE.COM/BILL STOCKHOLM", "E KARLSSON", 99.0),
        (datetime(2026, 6, 14), "BETALNING MOTTAGEN, TACK", "E KARLSSON", -12400.0),
    ]
    for r in rows:
        ws.append(list(r))
    wb.save(HERE / "amex.xlsx")


def overlaps() -> None:
    # Samma enkla format; B överlappar A:s sista dagar och lägger till nya.
    header = "Datum;Text;Belopp;Saldo"
    a = [
        header,
        "2026-05-28;ICA NÄRA;-250,00;10000,00",
        "2026-05-30;Espresso House;-45,00;9955,00",
        "2026-05-30;Espresso House;-45,00;9910,00",   # två identiska köp samma dag
        "2026-05-31;SL Access;-930,00;8980,00",
    ]
    b = [
        header,
        "2026-05-30;Espresso House;-45,00;9955,00",   # dubblett (index 0)
        "2026-05-30;Espresso House;-45,00;9910,00",   # dubblett (index 1)
        "2026-05-31;SL Access;-930,00;8980,00",       # dubblett
        "2026-06-02;Willys;-812,00;8168,00",          # ny
        "2026-05-30;Espresso House;-45,00;8123,00",   # TREDJE identiska köpet → ny (index 2)
    ]
    (HERE / "overlap_a.csv").write_bytes("\n".join(a).encode("utf-8"))
    (HERE / "overlap_b.csv").write_bytes("\n".join(b).encode("utf-8"))


def duplicate_coffee() -> None:
    lines = [
        "Datum;Text;Belopp;Saldo",
        "2026-06-10;Espresso House Odenplan;-42,00;5000,00",
        "2026-06-10;Espresso House Odenplan;-42,00;4958,00",
    ]
    (HERE / "duplicate_coffee.csv").write_bytes("\n".join(lines).encode("utf-8"))


def preamble() -> None:
    # Okänt generiskt format: metadata före header, tusentalsavgränsare med hårt mellanslag
    lines = [
        "Kontoutdrag",
        "Kontonummer: 9999 123 456",
        "Period: 2026-06-01 till 2026-06-30",
        "",
        "Transaktionsdatum;Specifikation;Insättning;Uttag;Saldo",
        "30.06.2026;Matbutiken AB;;1 234,56;15 000,00",
        "28.06.2026;Lön juni;41 000,00;;16 234,56",
        "27.06.2026;Bensinmacken;;650,00;-24 765,44",
    ]
    (HERE / "preamble.csv").write_bytes("\n".join(lines).encode("utf-8"))


if __name__ == "__main__":
    for fn in (swedbank, nordea, seb, entercard, amex, overlaps, duplicate_coffee, preamble):
        fn()
    print("Fixturer genererade i", HERE)
