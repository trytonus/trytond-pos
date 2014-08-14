# -*- coding: utf-8 -*-
"""
    shipment.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.model import fields
from trytond.pool import PoolMeta

__metaclass__ = PoolMeta
__all__ = ['ShipmentOut', 'ShipmentOutReturn']


class ShipmentOut:
    __name__ = 'stock.shipment.out'

    delivery_mode = fields.Selection([
        ('pick_up', 'Pick Up'),
        ('ship', 'Ship'),
    ], 'Delivery Mode', required=True, readonly=True)

    @staticmethod
    def default_delivery_mode():
        return 'ship'


class ShipmentOutReturn:
    __name__ = 'stock.shipment.out.return'

    # XXX: Not sure if pick_up is the right word here ?
    # My intention is to indicate something like the customer walked into
    # the store and returned this item.
    #
    # While ship indicates that the customer intends to ship the item back
    # to us later by mail or something like that.
    delivery_mode = fields.Selection([
        ('pick_up', 'Pick Up'),
        ('ship', 'Ship'),
    ], 'Delivery Mode', required=True, readonly=True)

    @staticmethod
    def default_delivery_mode():
        return 'ship'
