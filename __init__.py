# -*- coding: utf-8 -*-
"""
    __init__.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import Pool

from sale import Sale, SaleShop, SaleLine, SaleConfiguration
from address import Address
from shipment import ShipmentOut, ShipmentOutReturn


def register():
    Pool.register(
        SaleShop,
        Sale,
        SaleLine,
        ShipmentOut,
        ShipmentOutReturn,
        Address,
        SaleConfiguration,
        module='pos', type_='model'
    )
