# -*- coding: utf-8 -*-
"""
    tests/test_address.py

    :copyright: (C) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
import sys
import os
import unittest

import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, USER, DB_NAME, CONTEXT
from trytond.transaction import Transaction

DIR = os.path.abspath(os.path.normpath(os.path.join(
    __file__, '..', '..', '..', '..', '..', 'trytond'
)))
if os.path.isdir(DIR):
    sys.path.insert(0, os.path.dirname(DIR))


class TestAddress(unittest.TestCase):
    '''
    Address Test Case for lie-nielsen module.
    '''

    def setup_defaults(self):
        """
        Setup Defaults
        """
        self.Party = POOL.get('party.party')
        self.Address = POOL.get('party.address')

        with Transaction().set_context(company=None):
            self.party1, = self.Party.create([{
                'name': 'Jon Doe'
            }])
            self.address, = self.Address.create([{
                'party': self.party1,
                'name': 'Jon Doe\'s Address'
            }])

    def test_0010_test_address_serialization(self):
        """
        Test address serialization
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            self.address.serialize('pos')
            self.address.serialize()


def suite():
    """
    Define suite
    """
    test_suite = trytond.tests.test_tryton.suite()
    test_suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestAddress)
    )
    return test_suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
