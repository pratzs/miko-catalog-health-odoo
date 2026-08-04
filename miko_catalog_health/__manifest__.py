# -*- coding: utf-8 -*-
{
    'name': 'Barcode Validator & Catalog Audit (Miko)',
    'version': '18.0.1.0.0',
    'summary': 'Find broken barcodes and incomplete products before they cost you a sale',
    'description': """
Catalog Health
================

Audits your product catalog and shows you exactly what is broken, including the
faults that are invisible in a normal list view.

* Validates barcode check digits (EAN-8, UPC-A, EAN-13, ITF-14). A barcode with a
  wrong check digit looks perfectly normal on screen and silently fails at the
  scanner.
* Finds duplicate barcodes across the catalog.
* Flags products missing an internal reference, sales price, category, unit of
  measure or image.
* Gives every product an issue count so you can fix the worst first, in bulk.

Free and open source, from Tripster Developers.
""",
    'author': 'Tripster Developers',
    'website': 'https://tripsterdevelopers.com/odoo/',
    'support': 'hello@tripsterdevelopers.com',
    'category': 'Inventory/Inventory',
    'license': 'LGPL-3',
    'depends': ['product'],
    'data': [
        'views/miko_catalog_health_views.xml',
    ],
    'installable': True,
    'images': ['static/description/banner.png'],
    'application': True,
    'auto_install': False,
}
