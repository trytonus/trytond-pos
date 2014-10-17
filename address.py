# -*- coding: utf-8 -*-
"""
    address.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import PoolMeta

__metaclass__ = PoolMeta
__all__ = ["Address"]


class Address:
    __name__ = "party.address"

    def serialize(self, purpose=None):
        """
        Address serialization for the purpose of POS
        """
        if purpose == 'pos':
            return {
                'id': self.id,
                'name': self.name,
                'full_address': self.full_address,
            }
        elif hasattr(super(Address, self), 'serialize'):
            return super(Address, self).serialize(purpose)  # pragma: no cover
