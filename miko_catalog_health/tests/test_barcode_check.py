# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.barcode_check import validate_gtin, gtin_check_digit


@tagged('post_install', '-at_install')
class TestBarcodeCheck(TransactionCase):
    """The check-digit maths, verified against barcodes with known-good digits."""

    def test_real_world_barcodes_validate(self):
        # Published GS1 barcodes. If these ever fail, the algorithm is wrong,
        # not the data.
        for code, symbology in [
            ('5449000000996', 'EAN-13'),   # Coca-Cola 330ml
            ('0012000001086', 'EAN-13'),
            ('96385074', 'EAN-8'),
            ('036000291452', 'UPC-A'),
        ]:
            status, sym, _expected = validate_gtin(code)
            self.assertEqual(status, 'ok', '%s should be a valid %s' % (code, symbology))
            self.assertEqual(sym, symbology)

    def test_wrong_check_digit_is_caught_and_corrected(self):
        # Same barcode as above with the last digit knocked off by one.
        status, _sym, expected = validate_gtin('5449000000995')
        self.assertEqual(status, 'checksum')
        self.assertEqual(expected, 6)

    def test_non_gtin_input(self):
        self.assertEqual(validate_gtin('ABC-123')[0], 'nonnumeric')
        self.assertEqual(validate_gtin('12345')[0], 'length')
        self.assertEqual(validate_gtin('')[0], 'empty')
        self.assertEqual(validate_gtin(False)[0], 'empty')

    def test_check_digit_helper(self):
        self.assertEqual(gtin_check_digit('544900000099'), 6)


@tagged('post_install', '-at_install')
class TestCatalogHealth(TransactionCase):
    """The compute, exercised through the ORM the way a merchant would hit it."""

    def _make(self, name, **vals):
        return self.env['product.template'].create(dict(name=name, **vals))

    def _invalidate(self):
        """env.invalidate_all() arrived after Odoo 14, which uses env.cache."""
        if hasattr(self.env, 'invalidate_all'):
            self.env.invalidate_all()
        else:  # Odoo 14
            self.env.cache.invalidate()

    def _flush_all(self):
        """Force pending writes to Postgres so SQL constraints actually fire.

        On Odoo 14 and 15 barcode uniqueness is a SQL constraint, which does not
        raise until flush. env.flush_all() arrived later.
        """
        if hasattr(self.env, 'flush_all'):
            self.env.flush_all()
        else:  # Odoo 14 and 15
            self.env['product.template'].flush()

    def _barcode_uniqueness_is_a_sql_constraint(self):
        """Odoo 14 and 15 enforce uniqueness in POSTGRES, 16+ in Python.

        Where it is a SQL constraint, a duplicate genuinely cannot exist, not even
        through a bulk import, so there is nothing for this module to find.
        """
        self.env.cr.execute("""
            SELECT 1 FROM pg_constraint
             WHERE conrelid = 'product_product'::regclass
               AND conname LIKE %s
        """, ('%barcode%',))
        return bool(self.env.cr.fetchone())

    def test_bad_check_digit_is_flagged_with_the_right_fix(self):
        p = self._make('Bad barcode', barcode='5449000000995')
        self.assertEqual(p.ch_barcode_status, 'checksum')
        self.assertEqual(p.ch_barcode_expected, '6')
        self.assertFalse(p.ch_is_healthy)

    def test_valid_barcode_passes(self):
        p = self._make('Good barcode', barcode='5449000000996')
        self.assertEqual(p.ch_barcode_status, 'ok')

    def test_odoo_itself_blocks_duplicate_barcodes(self):
        """Documents why duplicate detection is a secondary feature, not the headline.

        Odoo 19 enforces barcode uniqueness per company with an @api.constrains on
        product.product. A merchant cannot type a duplicate in. What Odoo does NOT
        check anywhere is whether the barcode is arithmetically valid.
        """
        self._make('Original', barcode='5449000000996')
        with self.assertRaises(Exception):
            # ValidationError on 16+, IntegrityError on 14 and 15. Either way the
            # merchant cannot type a duplicate in.
            self._make('Duplicate attempt', barcode='5449000000996')
            self._flush_all()

    def test_duplicates_are_flagged_on_both_products(self):
        """Duplicates still occur in the wild, just not through the form.

        They arrive by SQL import, by database restore from a version without the
        constraint, and across companies, since the core check is company-scoped.
        So the fixture writes straight to the table, which is the real mechanism.
        """
        if self._barcode_uniqueness_is_a_sql_constraint():
            self.skipTest(
                "Postgres enforces barcode uniqueness on this Odoo series, so a "
                "duplicate cannot be created even by a bulk import")
        a = self._make('Dupe A', barcode='5449000000996')
        b = self._make('Dupe B', barcode='5449000000997')
        # Bypass the ORM exactly the way a bulk import does.
        self.env.cr.execute(
            "UPDATE product_product SET barcode = %s WHERE product_tmpl_id = %s",
            ('5449000000996', b.id))
        # barcode lives on product.product, so invalidating only the templates
        # would leave the stale variant value in cache.
        self._invalidate()
        (a | b)._compute_catalog_health()
        self.assertEqual(a.ch_barcode_status, 'duplicate')
        self.assertEqual(b.ch_barcode_status, 'duplicate')

    def test_internal_codes_are_not_counted_as_broken(self):
        """A deliberate internal code is correct data, not a defect.

        Flagging a merchant's own convention is the false positive most likely to
        make them stop trusting the module.
        """
        alpha = self._make('Internal code', barcode='CUP-FILT-100')
        short = self._make('Shelf code', barcode='4471')
        self.assertEqual(alpha.ch_barcode_status, 'nonnumeric')
        self.assertEqual(short.ch_barcode_status, 'length')
        # Reported, but neither adds to the issue count.
        bare = self._make('No barcode at all')
        self.assertLess(alpha.ch_issue_count, bare.ch_issue_count)
        self.assertLess(short.ch_issue_count, bare.ch_issue_count)

    def test_missing_fields_are_listed(self):
        p = self._make('Bare product')
        self.assertIn('Barcode', p.ch_missing)
        self.assertIn('Internal Reference', p.ch_missing)
        self.assertGreater(p.ch_issue_count, 0)

    def test_status_updates_when_the_barcode_is_corrected(self):
        # The whole point of a stored compute: fixing the data clears the flag.
        p = self._make('Fixable', barcode='5449000000995')
        self.assertEqual(p.ch_barcode_status, 'checksum')
        p.barcode = '5449000000996'
        self.assertEqual(p.ch_barcode_status, 'ok')
        self.assertFalse(p.ch_missing and 'Barcode' in p.ch_missing)

    def test_image_presence_is_detected_without_reading_the_binary(self):
        """Images live in ir_attachment, so the compute resolves them by id.

        A 1x1 transparent PNG is enough to prove the join works both ways.
        """
        px = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
              "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
        p = self._make('No image yet')
        self.assertIn('Image', p.ch_missing)
        p.image_1920 = px
        self.assertNotIn('Image', p.ch_missing or '')

    def test_services_are_not_flagged_for_a_missing_barcode(self):
        """A service has nothing to scan, so a missing barcode is correct data.

        This is the difference between a tool merchants keep and one that cries
        wolf on every line of the catalog.
        """
        svc = self._make('Consulting hour', type='service')
        self.assertEqual(svc.ch_barcode_status, 'na')
        self.assertNotIn('Barcode', svc.ch_missing or '')

        goods = self._make('Physical thing', type='consu')
        self.assertEqual(goods.ch_barcode_status, 'missing')
        self.assertIn('Barcode', goods.ch_missing)

    def test_a_service_that_does_have_a_barcode_is_still_validated(self):
        svc = self._make('Boxed service', type='service', barcode='5449000000995')
        self.assertEqual(svc.ch_barcode_status, 'checksum')
        self.assertEqual(svc.ch_barcode_expected, '6')

    def test_rescan_action_returns_a_notification(self):
        action = self.env['product.template'].action_catalog_health_rescan()
        self.assertEqual(action['tag'], 'display_notification')
