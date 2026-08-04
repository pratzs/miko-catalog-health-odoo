# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

from .barcode_check import validate_gtin

# Fields a catalog needs before it can be scanned, sold online, or reported on.
# Kept deliberately small: every one of these breaks something concrete when
# absent, rather than being merely nice to have.
COMPLETENESS_FIELDS = [
    ('barcode', 'Barcode'),
    ('default_code', 'Internal Reference'),
    ('list_price', 'Sales Price'),
    ('standard_price', 'Cost'),
    ('categ_id', 'Product Category'),
    ('uom_id', 'Unit of Measure'),
    ('image_1920', 'Image'),
]

BARCODE_STATUS = [
    ('ok', 'Valid'),
    ('missing', 'Missing'),
    ('checksum', 'Wrong check digit'),
    ('nonnumeric', 'Not numeric'),
    ('length', 'Unusual length'),
    ('duplicate', 'Duplicate'),
    ('na', 'Not applicable'),
]

# A service has nothing to scan and nothing to put in a barcode. Flagging one for
# a missing barcode is a false positive, and a tool that reports every product as
# broken gets ignored, which costs more than the checks are worth.
NO_BARCODE_TYPES = ('service',)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    ch_barcode_status = fields.Selection(
        BARCODE_STATUS, string='Barcode Check', compute='_compute_catalog_health',
        store=True, index=True,
        help="Result of validating the barcode. A wrong check digit looks fine on "
             "screen but will not scan.")
    ch_barcode_expected = fields.Char(
        string='Should End With', compute='_compute_catalog_health', store=True,
        help="For a barcode with a bad check digit, the digit it should end with.")
    ch_missing = fields.Char(
        string='Missing Fields', compute='_compute_catalog_health', store=True)
    ch_issue_count = fields.Integer(
        string='Issues', compute='_compute_catalog_health', store=True, index=True)
    ch_is_healthy = fields.Boolean(
        string='Catalog OK', compute='_compute_catalog_health', store=True, index=True)

    @api.depends('barcode', 'default_code', 'list_price', 'standard_price',
                 'categ_id', 'uom_id', 'image_1920', 'type')
    def _compute_catalog_health(self):
        # Duplicate detection needs to look across the whole catalog, so resolve
        # it once per compute rather than per record.
        # Deliberately a plain search rather than read_group / _read_group: the
        # grouping API changed shape in Odoo 17 and a stored compute that breaks
        # on upgrade is worse than one extra query. search_read on an indexed
        # column is cheap and behaves identically on 17, 18, 19 and 20.
        barcodes = [t.barcode for t in self if t.barcode]
        duplicates = set()
        if barcodes:
            rows = self.env['product.template'].with_context(active_test=False).search_read(
                [('barcode', 'in', barcodes)], ['barcode'])
            seen = set()
            for row in rows:
                code = row.get('barcode')
                if code in seen:
                    duplicates.add(code)
                else:
                    seen.add(code)

        # Images are fields.Image, which Odoo stores in ir_attachment rather than
        # on product_template. Reading tmpl.image_1920 per record would pull every
        # binary out of the filestore, so a rescan of a large catalog would drag
        # the whole image library through memory. One id-only query instead.
        real_ids = [rid for rid in self.ids if isinstance(rid, int)]
        with_image = set()
        if real_ids:
            # Pending attachment writes must reach the table before the raw query
            # below can see them. flush_model() arrived in Odoo 16; 14 and 15 spell
            # it flush(). Checked at runtime so one source serves every series.
            attachment = self.env['ir.attachment']
            if hasattr(attachment, 'flush_model'):
                attachment.flush_model()
            else:  # Odoo 14 and 15
                attachment.flush()
            self.env.cr.execute(
                "SELECT res_id FROM ir_attachment "
                " WHERE res_model = 'product.template' AND res_field = 'image_1920'"
                "   AND res_id IN %s",
                (tuple(real_ids),))
            with_image = {row[0] for row in self.env.cr.fetchall()}

        for tmpl in self:
            scannable = tmpl.type not in NO_BARCODE_TYPES
            missing = []
            for fname, label in COMPLETENESS_FIELDS:
                if fname == 'barcode' and not scannable:
                    continue
                if fname == 'image_1920':
                    if tmpl.id not in with_image:
                        missing.append(label)
                    continue
                value = tmpl[fname]
                # 0.0 is a legitimate cost but never a legitimate sales price,
                # so only list_price treats zero as missing.
                if fname == 'list_price':
                    if not value:
                        missing.append(label)
                elif fname == 'standard_price':
                    continue  # informational only, not counted as an issue
                elif not value:
                    missing.append(label)

            status, _symbology, expected = validate_gtin(tmpl.barcode)
            if status == 'empty':
                # A service without a barcode is correct, not incomplete. One that
                # has been given a barcode is still validated below.
                barcode_status = 'missing' if scannable else 'na'
                expected_digit = False
            elif tmpl.barcode in duplicates:
                barcode_status = 'duplicate'
                expected_digit = False
            elif status == 'ok':
                barcode_status = 'ok'
                expected_digit = False
            else:
                barcode_status = status
                expected_digit = str(expected) if expected is not None else False

            # Only genuine breakage counts as an issue.
            #
            # 'length' and 'nonnumeric' are reported but NOT counted. Both mean
            # "this is not a GTIN", which is a legitimate choice: plenty of
            # businesses use internal codes like CUP-FILT-100 or a short shelf
            # code deliberately. Counting those would flag correct data as broken,
            # and a tool that cries wolf on a merchant's own convention is one
            # they stop trusting. What remains is unambiguous: no barcode at all,
            # a barcode that fails its own check digit, or the same barcode on two
            # products.
            counts_as_issue = barcode_status in ('missing', 'checksum', 'duplicate')
            issue_count = len(missing) + (1 if counts_as_issue and 'Barcode' not in missing else 0)

            tmpl.ch_barcode_status = barcode_status
            tmpl.ch_barcode_expected = expected_digit
            tmpl.ch_missing = ', '.join(missing) if missing else False
            tmpl.ch_issue_count = issue_count
            tmpl.ch_is_healthy = issue_count == 0

    @api.model
    def action_catalog_health_rescan(self):
        """Force a recompute across the whole catalog.

        Stored computes only refresh when a dependency changes, so a catalog
        imported before this module was installed needs one explicit pass.
        """
        products = self.search([])
        products._compute_catalog_health()
        # flush_recordset() arrived in Odoo 16; 14 and 15 spell it flush().
        if hasattr(products, 'flush_recordset'):
            products.flush_recordset()
        else:  # Odoo 14 and 15
            products.flush()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Catalog scanned'),
                'message': _('%(total)s products checked, %(bad)s with issues.') % {
                    'total': len(products),
                    'bad': len(products.filtered(lambda p: not p.ch_is_healthy)),
                },
                'type': 'success',
                'sticky': False,
            },
        }
