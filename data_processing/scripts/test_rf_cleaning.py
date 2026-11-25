"""Testes das regras de limpeza. Executar: python -m unittest discover data_processing/scripts"""

import io
import unittest
from collections import Counter

from rf_cleaning import (
    clean_record,
    column_kinds,
    drop_placeholder_duplicates,
    format_line,
    is_placeholder,
    iter_numbered_records,
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


def dedupe(text: str, layout_name: str = "empresas"):
    """Lê e aplica o descarte de placeholders com a chave do layout, como o process_receita faz."""
    layout = LAYOUTS[layout_name]
    stats, rejects = Counter(), []
    numbered = iter_numbered_records(io.StringIO(text, newline=""), len(layout.columns), stats, rejects)
    rows = list(drop_placeholder_duplicates(numbered, layout.key_indexes(), stats, rejects))
    return rows, stats, rejects


PLACEHOLDER = '"08314885";"";"0000";"00";"0,00";"";""\n'
REAL = '"08314885";"FLAVIO PAVAO DE SOUZA";"4120";"59";"0,00";"05";""\n'


class DuplicatePlaceholderTest(unittest.TestCase):
    def test_empty_record_after_real_one_is_dropped(self):
        # caso real de Empresas2: linhas 3 e 4 com o mesmo CNPJ
        rows, stats, rejects = dedupe('"08314884";"A";"1";"2";"0,00";"05";""\n' + REAL + PLACEHOLDER)
        self.assertEqual([r[0] for _, r in rows], ["08314884", "08314885"])
        self.assertEqual(rows[1][1][1], "FLAVIO PAVAO DE SOUZA")
        self.assertEqual([line for line, _ in rejects], [3])
        self.assertEqual((stats["rejected"], stats["duplicate_placeholder"]), (1, 1))

    def test_empty_record_before_real_one_is_dropped(self):
        rows, _, rejects = dedupe(PLACEHOLDER + REAL)
        self.assertEqual([r[1] for _, r in rows], ["FLAVIO PAVAO DE SOUZA"])
        self.assertEqual([line for line, _ in rejects], [1])

    def test_lone_empty_record_is_kept(self):
        # sem duplicata, o registro vazio pode ser o único daquela chave (e ter estabelecimentos)
        rows, stats, rejects = dedupe(REAL + '"08314886";"";"0000";"00";"0,00";"";""\n')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rejects, [])
        self.assertEqual(stats["duplicate_placeholder"], 0)

    def test_duplicates_with_data_in_both_are_kept_and_counted(self):
        other = '"08314885";"OUTRA RAZAO";"4120";"59";"0,00";"05";""\n'
        rows, stats, rejects = dedupe(REAL + other)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rejects, [])
        self.assertEqual(stats["duplicate_keys"], 1)

    def test_line_number_accounts_for_merged_multiline_records(self):
        text = REAL + '"08314885";"";"0000"\n;"00";"0,00";"";""\n'  # placeholder partido em 2 linhas físicas
        rows, _, rejects = dedupe(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual([line for line, _ in rejects], [2])

    def test_is_placeholder_ignores_key_and_accepts_zero_formats(self):
        key = frozenset({0})
        self.assertTrue(is_placeholder(["1", "", "0000", "00", "0,00", "", ""], key))
        self.assertTrue(is_placeholder(["1", " ", "0000", "00", "0.00", "", ""], key))
        self.assertFalse(is_placeholder(["1", "ACME", "0000", "00", "0,00", "", ""], key))
        self.assertFalse(is_placeholder(["1", "", "0000", "00", "5000,00", "", ""], key))

    def test_only_tables_with_declared_key_are_deduplicated(self):
        self.assertEqual(LAYOUTS["empresas"].key_indexes(), (0,))
        self.assertEqual(LAYOUTS["socios"].key_indexes(), ())  # sócios não tem chave natural


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
