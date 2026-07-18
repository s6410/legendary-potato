from pathlib import Path

import pytest

from app.services.normalize import normalize_description
from app.services.parsing import (
    ParseOptions,
    inspect_file,
    parse_amount,
    parse_with_options,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# ------------------------------------------------------------------ inspect

def test_swedbank_inspection_cp1252_comma_preamble():
    r = inspect_file(load("swedbank.csv"), "swedbank.csv")
    assert r.encoding == "cp1252"
    assert r.delimiter == ","
    assert r.header_row_index == 1
    assert r.header[5] == "Bokföringsdag"
    m = r.suggested_mapping
    assert m["date"] == 5 and m["description"] == 9 and m["amount"] == 10 and m["balance"] == 11
    assert r.suggested_decimal_separator == "."
    assert not r.suggested_invert_sign


def test_nordea_inspection_bom_semicolon_slashdates():
    r = inspect_file(load("nordea.csv"), "nordea.csv")
    assert r.encoding == "utf-8-sig"
    assert r.delimiter == ";"
    assert r.header_row_index == 0
    m = r.suggested_mapping
    assert m["date"] == 0 and m["amount"] == 1 and m["description"] == 4 and m["balance"] == 6
    assert r.suggested_date_format == "%Y/%m/%d"
    assert r.suggested_decimal_separator == ","


def test_seb_xlsx_header_on_row5():
    r = inspect_file(load("seb.xlsx"), "seb.xlsx")
    assert r.file_type == "xlsx"
    assert r.header_row_index == 4
    m = r.suggested_mapping
    assert m["date"] == 0 and m["description"] == 3 and m["amount"] == 4 and m["balance"] == 5


def test_entercard_suggests_sign_inversion():
    r = inspect_file(load("entercard.csv"), "entercard.csv")
    assert r.suggested_invert_sign is True
    assert r.suggested_mapping["amount"] == 3


def test_preamble_generic_split_columns_and_dotted_dates():
    r = inspect_file(load("preamble.csv"), "preamble.csv")
    assert r.header_row_index == 4
    m = r.suggested_mapping
    assert m["amount_in"] == 2 and m["amount_out"] == 3 and m["date"] == 0
    assert r.suggested_date_format == "%d.%m.%Y"
    assert r.suggested_thousands_separator == " "


def test_handelsbanken_konto_xlsx_header_after_metadata():
    r = inspect_file(load("handelsbanken_konto.xlsx"), "handelsbanken_konto.xlsx")
    assert r.header_row_index == 8
    m = r.suggested_mapping
    assert m["date"] == 1 and m["description"] == 2 and m["amount"] == 3 and m["balance"] == 4
    assert not r.suggested_invert_sign


def test_handelsbanken_platinum_header_after_invoice_block():
    # Fakturainfo-blocket (rad 8–9) innehåller en datum+belopp-rad och får
    # inte misstas för tabellheadern — riktiga headern är rad 11 (index 10)
    r = inspect_file(load("handelsbanken_platinum.xlsx"), "handelsbanken_platinum.xlsx")
    assert r.header_row_index == 10
    m = r.suggested_mapping
    assert m["date"] == 0 and m["description"] == 1 and m["amount"] == 2
    assert not r.suggested_invert_sign  # köpen är redan negativa


def test_parse_handelsbanken_platinum_excludes_invoice_total():
    res = parse_with_options(
        load("handelsbanken_platinum.xlsx"),
        "handelsbanken_platinum.xlsx",
        _opts_from_inspection("handelsbanken_platinum.xlsx"),
    )
    assert [r.amount_ore for r in res.rows] == [-19363, -3900, -69000, -12950]
    # fakturans totalbelopp (-62 691,42) ska inte finnas bland raderna
    assert all(r.amount_ore != -6269142 for r in res.rows)
    assert res.rows[0].description_raw == "ICA NARA LJUNGSKOGEN"


def test_inspect_with_manual_header_row_override():
    data = load("handelsbanken_platinum.xlsx")
    auto = inspect_file(data, "handelsbanken_platinum.xlsx")
    forced = inspect_file(data, "handelsbanken_platinum.xlsx", header_row_index=7)
    assert forced.header_row_index == 7
    assert forced.header[0] == "Faktura information"
    # mappning och fingeravtryck ska räknas om utifrån den valda raden
    assert forced.fingerprint != auto.fingerprint


def test_fingerprint_stable_and_distinct():
    a1 = inspect_file(load("swedbank.csv"), "swedbank.csv").fingerprint
    a2 = inspect_file(load("swedbank.csv"), "swedbank.csv").fingerprint
    b = inspect_file(load("nordea.csv"), "nordea.csv").fingerprint
    assert a1 == a2 and a1 != b


# -------------------------------------------------------------------- parse

def _opts_from_inspection(name: str, **overrides) -> ParseOptions:
    r = inspect_file(load(name), name)
    opts = ParseOptions(
        file_type=r.file_type,
        column_mapping=r.suggested_mapping,
        delimiter=r.delimiter,
        encoding=r.encoding,
        decimal_separator=r.suggested_decimal_separator,
        thousands_separator=r.suggested_thousands_separator,
        date_format=r.suggested_date_format,
        header_row_index=r.header_row_index,
        invert_sign=r.suggested_invert_sign,
    )
    for k, v in overrides.items():
        setattr(opts, k, v)
    return opts


def test_parse_swedbank_amounts_in_ore():
    res = parse_with_options(load("swedbank.csv"), "swedbank.csv", _opts_from_inspection("swedbank.csv"))
    assert len(res.rows) == 4
    ica = res.rows[0]
    assert ica.booked_date == "2026-06-28"
    assert ica.amount_ore == -48250
    assert ica.balance_ore == 1234567
    assert "ica supermarket söder" == ica.description_norm
    lon = res.rows[2]
    assert lon.amount_ore == 3520000


def test_parse_nordea_skips_reserverat():
    res = parse_with_options(load("nordea.csv"), "nordea.csv", _opts_from_inspection("nordea.csv"))
    assert len(res.rows) == 4
    assert len(res.skipped) == 1
    assert res.skipped[0]["reason"] == "reserverad"
    assert res.rows[0].booked_date == "2026-06-30"
    assert res.rows[0].amount_ore == -125000


def test_parse_seb_native_xlsx_dates():
    res = parse_with_options(load("seb.xlsx"), "seb.xlsx", _opts_from_inspection("seb.xlsx"))
    assert len(res.rows) == 4
    assert res.rows[0].booked_date == "2026-06-29"
    assert res.rows[0].amount_ore == -4500
    # SEB-suffix "/26-06-28" ska normaliseras bort
    assert res.rows[0].description_norm == "pressbyran"


def test_parse_entercard_sign_inverted():
    res = parse_with_options(load("entercard.csv"), "entercard.csv", _opts_from_inspection("entercard.csv"))
    amounts = [r.amount_ore for r in res.rows]
    assert amounts == [-124900, -389000, -16900, 845000]  # köp negativa, inbetalning positiv


def test_parse_preamble_split_in_out_columns():
    res = parse_with_options(load("preamble.csv"), "preamble.csv", _opts_from_inspection("preamble.csv"))
    assert [r.amount_ore for r in res.rows] == [-123456, 4100000, -65000]
    assert res.rows[0].booked_date == "2026-06-30"


def test_parse_amex_xlsx():
    res = parse_with_options(load("amex.xlsx"), "amex.xlsx", _opts_from_inspection("amex.xlsx"))
    assert [r.amount_ore for r in res.rows] == [-82350, -9900, 1240000]


# ------------------------------------------------------------------- enheter

@pytest.mark.parametrize(
    "raw,dec,thou,expected",
    [
        ("-482.50", ".", None, -48250),
        ("-1250,00", ",", None, -125000),
        ("1 234,56", ",", " ", 123456),
        ("1\xa0234,56", ",", " ", 123456),
        ("35200.00", ".", None, 3520000),
        ("−89,00", ",", None, -8900),  # unicode-minus
    ],
)
def test_parse_amount(raw, dec, thou, expected):
    assert parse_amount(raw, dec, thou) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("KORTKÖP 250114 ICA SUPERMARKET SÖDER", "ica supermarket söder"),
        ("Kortköp 250619 ICA SUPERMARKET SÖDER", "ica supermarket söder"),
        ("PRESSBYRAN/26-06-28", "pressbyran"),
        ("SAS 117-2345678901 STOCKHOLM", "sas 117- stockholm"),
        ("Swish inbetalning KALLE KARLSSON", "kalle karlsson"),
    ],
)
def test_normalize_description(raw, expected):
    assert normalize_description(raw) == expected
