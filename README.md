# Miko Catalog Health for Odoo

Validates every barcode in an Odoo product catalog against the GS1 check-digit
standard, reports the digit each broken one should have ended with, and flags the
fields that are simply not filled in.

Published on the Odoo Apps Store by Tripster Developers.

## Branches

One branch per Odoo series. The Apps Store is registered against each separately.

| Branch | Odoo | Status |
|---|---|---|
| `14.0` | 14.0 | 20 tests passing |
| `15.0` | 15.0 | 20 tests passing |
| `16.0` | 16.0 | 20 tests passing |
| `17.0` | 17.0 | 20 tests passing |
| `18.0` | 18.0 | 20 tests passing |
| `19.0` | 19.0 | 20 tests passing |

## Running the tests

    odoo -d <db> -i miko_catalog_health --test-enable \
         --test-tags /miko_catalog_health --stop-after-init

## Hosting

Runs on Odoo.sh and on-premise. Odoo Online cannot run third-party modules that
contain Python, per the Odoo Apps FAQ.
