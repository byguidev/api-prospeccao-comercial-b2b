"""Testes das regras de limpeza. Executar: python -m unittest discover data_processing/scripts"""

import io
import unittest
from collections import Counter

from rf_cleaning import (
    clean_record,
    column_kinds,
    format_line,
    iter_records,
    normalize_date,
    normalize_decimal,
)
from rf_encoding import TextFixer
from rf_layout import LAYOUTS, detect_layout


def read(text: str, n_fields: int):
    stats, rejects = Counter(), []
    rows = list(iter_records(io.StringIO(text, newline=""), n_fields, stats, rejects))
    return rows, stats, rejects


class ReadingTest(unittest.TestCase):
    def test_semicolon_inside_field_is_not_a_separator(self):
        rows, _, _ = read('"1";"QUADRA 271;LOTE 18";"x"\n', 3)
        self.assertEqual(rows, [["1", "QUADRA 271;LOTE 18", "x"]])

    def test_escaped_quotes(self):
        rows, _, _ = read('"1";"CASA ""B""";"x"\n', 3)
        self.assertEqual(rows, [["1", 'CASA "B"', "x"]])

    def test_newline_inside_quoted_field(self):
        rows, stats, _ = read('"1";"RUA A\nAPTO 2";"x"\n"2";"b";"c"\n', 3)
        self.assertEqual(rows, [["1", "RUA A\nAPTO 2", "x"], ["2", "b", "c"]])
        self.assertEqual(stats["multiline_records"], 1)

    def test_record_broken_outside_quotes_is_merged(self):
        rows, stats, rejects = read('"1";"a"\n;"x"\n"2";"b";"c"\n', 3)
        self.assertEqual(rows, [["1", "a", "x"], ["2", "b", "c"]])
        self.assertEqual(stats["multiline_records"], 1)
        self.assertEqual(rejects, [])

    def test_truncated_record_is_rejected_without_losing_next(self):
        rows, stats, rejects = read('"1";"a"\n"2";"b";"c"\n', 3)
        self.assertEqual(rows, [["2", "b", "c"]])
        self.assertEqual(rejects, [(1, ["1", "a"])])
        self.assertEqual(stats["rejected"], 1)

    def test_too_many_fields_is_rejected(self):
        rows, _, rejects = read('"1";"a";"b";"c"\n', 3)
        self.assertEqual(rows, [])
        self.assertEqual(len(rejects), 1)


class DateTest(unittest.TestCase):
    def test_conversions(self):
        self.assertEqual(normalize_date("20230418"), ("20230418", "ok"))
        self.assertEqual(normalize_date("18/04/2023"), ("20230418", "br"))
        self.assertEqual(normalize_date("1/4/2023"), ("20230401", "br"))
        self.assertEqual(normalize_date("18-04-2023"), ("20230418", "br"))
        self.assertEqual(normalize_date("2023-04-18"), ("20230418", "iso"))

    def test_empty_and_invalid_become_null(self):
        for value in ("", "  ", "0", "00000000"):
            self.assertEqual(normalize_date(value), (None, "empty"))
        for value in ("20231301", "31/02/2023", "abc", "2023041"):
            self.assertEqual(normalize_date(value), (None, "invalid"))


class DecimalTest(unittest.TestCase):
    def test_conversions(self):
        self.assertEqual(normalize_decimal("5000,00"), "5000.00")
        self.assertEqual(normalize_decimal("1.234.567,89"), "1234567.89")
        self.assertEqual(normalize_decimal("0,00"), "0.00")
        self.assertEqual(normalize_decimal("150"), "150")
        self.assertIsNone(normalize_decimal("abc"))


class CleanRecordTest(unittest.TestCase):
    def test_empresas_record(self):
        layout = LAYOUTS["empresas"]
        kinds = column_kinds(7, frozenset(), layout.indexes_of(layout.decimal_columns))
        stats = Counter()
        out = clean_record(["00012345", "ACME\nLTDA", "2062", "49", "5000,00", "01", ""], kinds, stats)
        self.assertEqual(out, ["00012345", "ACME LTDA", "2062", "49", "5000.00", "01", None])
        self.assertEqual(stats["nulls"], 1)

    def test_empty_date_is_null(self):
        layout = LAYOUTS["socios"]
        kinds = column_kinds(11, layout.indexes_of(layout.date_columns), frozenset())
        row = ["1", "2", "N", "***1**", "22", "", "", "***0**", "", "00", "5"]
        out = clean_record(row, kinds, Counter())
        self.assertIsNone(out[5])
        self.assertIsNone(out[6])

    def test_format_line(self):
        line = format_line(["0001", None, 'CASA "B"', "A;B"], ";", "NULL")
        self.assertEqual(line, '"0001";NULL;"CASA ""B""";"A;B"\n')


class EncodingTest(unittest.TestCase):
    def setUp(self):
        self.fixer = TextFixer({"S?O": "SÃO", "IRM?O": "IRMÃO", "COM?RCIO": "COMÉRCIO", "CONCEI??O": "CONCEIÇÃO"})
        self.stats = Counter()

    def fix(self, value):
        return self.fixer.fix(value, self.stats)

    def test_lost_accent_restored_from_vocabulary(self):
        self.assertEqual(self.fix("RUA S?O JOSE"), "RUA SÃO JOSE")
        self.assertEqual(self.fix("ANEXO AO POSTO IRM?O"), "ANEXO AO POSTO IRMÃO")
        self.assertEqual(self.fix("Loja de Com?rcio"), "Loja de Comércio")
        self.assertEqual(self.fix("VILA CONCEIÇ?O"), "VILA CONCEIÇÃO")

    def test_unknown_word_and_real_question_mark_kept(self):
        self.assertEqual(self.fix("QUE TAL?PONTO"), "QUE TAL?PONTO")
        self.assertEqual(self.fix("S?N"), "S?N")
        self.assertEqual(self.fix("?"), "?")

    def test_apostrophe_restored(self):
        self.assertEqual(self.fix("MULTI KID?S LTDA"), "MULTI KID'S LTDA")
        self.assertEqual(self.fix("CORREGO DO PAU D?ALHO"), "CORREGO DO PAU D'ALHO")
        # Terminações portuguesas não viram apóstrofo
        self.assertEqual(self.fix("JAPON?S"), "JAPON?S")
        self.assertEqual(self.fix("PORTUGU?S"), "PORTUGU?S")
        self.assertEqual(self.fix("P?S"), "P?S")

    def test_ordinal_restored(self):
        self.assertEqual(self.fix("N? 01"), "Nº 01")
        self.assertEqual(self.fix("APT? 101"), "APTº 101")
        self.assertEqual(self.fix("2?ANDAR"), "2ºANDAR")
        self.assertEqual(self.fix("QUE TAL?"), "QUE TAL?")

    def test_mojibake_fixed_but_valid_latin1_untouched(self):
        self.assertEqual(self.fix("EDIF RaÃ­zes"), "EDIF Raízes")
        self.assertEqual(self.fix("NÂ° 1"), "N° 1")
        self.assertEqual(self.fix("NÃO INFORMADO"), "NÃO INFORMADO")

    def test_control_chars(self):
        self.assertEqual(self.fix("QUADRA 45	"), "QUADRA 45 ")
        self.assertEqual(self.fix("BODY DAY FIT"), "BODY DAY FIT")
        self.assertEqual(self.fix("URBANIZAO"), "URBANIZA??O")
        self.assertEqual(self.fix(""), "")

    def test_clean_record_uses_fixer_and_nulls_empty_after_fix(self):
        out = clean_record(["RUA S?O", ""], (0, 0), self.stats, self.fixer)
        self.assertEqual(out, ["RUA SÃO", None])


class LayoutTest(unittest.TestCase):
    def test_detection(self):
        self.assertEqual(detect_layout("estabelecimentos", "x").name, "estabelecimentos")
        self.assertEqual(detect_layout("outra", "F.K03200$W.SIMPLES.CSV.D61114").name, "simples")
        self.assertIsNone(detect_layout("outra", "README.txt"))


if __name__ == "__main__":
    unittest.main()
