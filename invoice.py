# -*- coding: utf-8 -*-
"""
    invoice.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import PoolMeta
from trytond.pyson import Eval
from decimal import Decimal


__metaclass__ = PoolMeta
__all__ = ["Invoice", "InvoiceLine"]


class Invoice:
    'Invoice'
    __name__ = 'account.invoice'

    @classmethod
    def get_amount(cls, invoices, names):
        rv = super(Invoice, cls).get_amount(invoices, names)
        for invoice in invoices:
            for line in filter(lambda l: l.type == 'roundoff', invoice.lines):
                if 'total_amount' in rv:
                    rv['total_amount'][invoice.id] += line.amount
        return rv


class InvoiceLine:
    'Invoice Line'
    __name__ = 'account.invoice.line'

    @classmethod
    def __setup__(cls):
        super(InvoiceLine, cls).__setup__()
        if ('roundoff', 'Round Off') not in cls.type.selection:
            cls.type.selection.append(
                ('roundoff', 'Round Off'),
            )
        cls.amount.states['invisible'] = \
            cls.amount.states['invisible'] & ~(Eval('type') == 'roundoff')

        cls.unit_price.states['invisible'] = \
            cls.unit_price.states['invisible'] & ~(Eval('type') == 'roundoff')

        cls.quantity.states['invisible'] = \
            cls.quantity.states['invisible'] & ~(Eval('type') == 'roundoff')

    def get_amount(self, name):
        rv = super(InvoiceLine, self).get_amount(name)
        if self.type == 'roundoff':
            return self.currency.round(
                Decimal(str(self.quantity)) * self.unit_price)
        return rv
