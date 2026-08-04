# -*- coding: utf-8 -*-
"""GTIN check-digit validation.

This is the part of the module that nothing else on the Odoo App Store does.
A barcode with a wrong check digit looks completely normal in a list view and
silently fails at the scanner, so it is invisible until someone is standing at
a till or a receiving bay with a product that will not scan.

Supported symbologies, all of which use the same modulo-10 scheme with
alternating weights, differing only in length and which position the weight of
3 starts on:

    EAN-8    8 digits    GTIN-8
    UPC-A   12 digits    GTIN-12
    EAN-13  13 digits    GTIN-13
    ITF-14  14 digits    GTIN-14 (outer case codes)
"""

GTIN_LENGTHS = {8: 'EAN-8', 12: 'UPC-A', 13: 'EAN-13', 14: 'ITF-14'}


def gtin_check_digit(body):
    """Return the correct check digit for a GTIN body (everything but the last
    digit). Weights alternate 3 and 1, applied from the RIGHT of the body, which
    is what makes one implementation work for every GTIN length.
    """
    total = 0
    for i, ch in enumerate(reversed(body)):
        weight = 3 if i % 2 == 0 else 1
        total += int(ch) * weight
    return (10 - (total % 10)) % 10


def validate_gtin(barcode):
    """Validate a barcode string.

    Returns a tuple of (status, symbology, expected_check_digit).

    status is one of:
        'ok'          valid GTIN with a correct check digit
        'checksum'    right length and all digits, but the check digit is wrong
        'nonnumeric'  contains characters that are not digits
        'length'      digits only, but not a GTIN length (8/12/13/14)
        'empty'       nothing to check

    A non-GTIN barcode is not automatically an error. Plenty of businesses use
    internal codes, so 'length' is reported separately from 'checksum' and the
    module treats it as informational rather than broken.
    """
    if not barcode:
        return 'empty', None, None

    code = barcode.strip()
    if not code:
        return 'empty', None, None

    if not code.isdigit():
        return 'nonnumeric', None, None

    symbology = GTIN_LENGTHS.get(len(code))
    if not symbology:
        return 'length', None, None

    expected = gtin_check_digit(code[:-1])
    if int(code[-1]) == expected:
        return 'ok', symbology, expected
    return 'checksum', symbology, expected
