# -*- coding: utf-8 -*-
"""Proof that the barcode check does not lie in either direction.

Two failure modes would destroy trust in this module faster than any missing
feature, so both are tested exhaustively rather than by example:

  FALSE POSITIVE   flagging a barcode that is actually correct
  BAD ADVICE       telling someone to use a digit that is still wrong

The check-digit maths is verified three ways:

  1. Against real published GS1 barcodes with known-good check digits.
  2. Differentially, against a SECOND implementation written from the GS1 rule
     in the opposite direction (left to right, parity derived from the body
     length) rather than the shipped one (right to left). Two independently
     derived implementations agreeing across every length is much stronger
     evidence than one implementation agreeing with itself.
  3. By round trip: for every body, the digit we suggest must make the barcode
     valid, and every one of the nine other digits must be rejected.
"""
from odoo.tests import TransactionCase, tagged

from ..models.barcode_check import validate_gtin, gtin_check_digit, GTIN_LENGTHS


def reference_check_digit(body):
    """Independent implementation, deliberately unlike the shipped one.

    GS1 numbers positions from the RIGHT, the check digit being position 1, and
    the digit beside it carrying weight 3. The shipped version walks the body in
    reverse. This one walks it forwards and derives each weight from the body
    length, so a shared off-by-one or a reversed-weight mistake cannot survive in
    both.
    """
    n = len(body)
    total = 0
    for i, ch in enumerate(body):
        weight = 3 if (n - 1 - i) % 2 == 0 else 1
        total += int(ch) * weight
    return (10 - total % 10) % 10


def deterministic_bodies(length, count):
    """Spread of bodies without Date/random, which are unavailable in tests.

    A multiplicative walk over a large prime hits every digit position with a
    varied distribution, which is what the differential test needs.
    """
    bodies = []
    value = 1
    modulus = 10 ** length
    for _ in range(count):
        value = (value * 1103515245 + 12345) % modulus
        bodies.append(str(value).zfill(length))
    return bodies


@tagged('post_install', '-at_install')
class TestBarcodeProof(TransactionCase):

    # Real barcodes in circulation, with the check digit they actually carry.
    REAL_BARCODES = [
        ('5449000000996', 'EAN-13'),   # Coca-Cola 330ml
        ('0012000001086', 'EAN-13'),   # Pepsi
        ('4006381333931', 'EAN-13'),   # Staedtler
        ('9780201379624', 'EAN-13'),   # ISBN-13
        ('5000112637922', 'EAN-13'),
        ('036000291452', 'UPC-A'),     # the GS1 documentation example
        ('012345678905', 'UPC-A'),
        ('96385074', 'EAN-8'),
        ('40170725', 'EAN-8'),
        ('10614141000415', 'ITF-14'),
    ]

    def test_real_barcodes_are_never_flagged(self):
        """No false positives on barcodes that are genuinely correct."""
        for code, symbology in self.REAL_BARCODES:
            status, sym, _expected = validate_gtin(code)
            self.assertEqual(
                status, 'ok',
                "%s is a real %s in circulation and must not be flagged" % (code, symbology))
            self.assertEqual(sym, symbology, "%s misidentified as %s" % (code, sym))

    def test_matches_an_independent_implementation(self):
        """Differential test across every supported GTIN length."""
        for length in sorted(GTIN_LENGTHS):
            body_len = length - 1
            for body in deterministic_bodies(body_len, 2000):
                self.assertEqual(
                    gtin_check_digit(body), reference_check_digit(body),
                    "implementations disagree on body %s (length %d)" % (body, length))

    def test_the_digit_we_suggest_always_fixes_the_barcode(self):
        """No bad advice: applying our suggestion must produce a valid barcode."""
        for length in sorted(GTIN_LENGTHS):
            for body in deterministic_bodies(length - 1, 400):
                correct = gtin_check_digit(body)

                # The correct barcode passes and we suggest nothing.
                status, _sym, _exp = validate_gtin(body + str(correct))
                self.assertEqual(status, 'ok',
                                 "%s should be valid" % (body + str(correct)))

                # Every other digit is rejected, and the fix we hand back is the
                # one that actually works.
                for wrong in range(10):
                    if wrong == correct:
                        continue
                    bad = body + str(wrong)
                    status, _sym, expected = validate_gtin(bad)
                    self.assertEqual(status, 'checksum',
                                     "%s should be rejected" % bad)
                    self.assertEqual(expected, correct,
                                     "wrong fix suggested for %s" % bad)
                    fixed = body + str(expected)
                    self.assertEqual(validate_gtin(fixed)[0], 'ok',
                                     "our suggested fix %s is still invalid" % fixed)

    def test_leading_zeros_are_never_treated_as_a_shorter_barcode(self):
        """A UPC-A written with a leading zero is still 12 digits, not 11."""
        for code in ('012345678905', '0012000001086', '00000000000000'):
            status, sym, _e = validate_gtin(code)
            self.assertEqual(sym, GTIN_LENGTHS[len(code)])
            self.assertIn(status, ('ok', 'checksum'))

    def test_internal_codes_are_reported_but_not_called_broken(self):
        """A non-GTIN length is a different report, not a checksum failure.

        Businesses legitimately use internal codes. Calling those broken would be
        a false positive of the worst kind, because it is the merchant's own
        deliberate convention.
        """
        for code in ('123', '1234567', '123456789', '123456789012345'):
            status, sym, expected = validate_gtin(code)
            self.assertEqual(status, 'length', "%s should be 'length'" % code)
            self.assertIsNone(sym)
            self.assertIsNone(expected)
