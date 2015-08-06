# -*- coding: utf-8 -*-
"""
    __init__.py

"""
from trytond.pool import Pool

from sale import Sale, SaleChannel, SaleLine, SaleConfiguration
from address import Address
from shipment import ShipmentOut, ShipmentOutReturn


def register():
    Pool.register(
        SaleChannel,
        Sale,
        SaleLine,
        ShipmentOut,
        ShipmentOutReturn,
        Address,
        SaleConfiguration,
        module='pos', type_='model'
    )
