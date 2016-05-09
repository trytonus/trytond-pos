# -*- coding: utf-8 -*-
"""
    sale.py

"""
from datetime import datetime, timedelta
from sql import Literal
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.rpc import RPC
from trytond.model import ModelView
from trytond.pyson import Eval, Bool, And
from trytond import backend
from math import floor
from decimal import Decimal


__metaclass__ = PoolMeta
__all__ = ["Sale", "SaleChannel", "SaleLine"]


class SaleConfiguration:
    'Sale Configuration'
    __name__ = 'sale.configuration'

    round_down_account = fields.Property(
        fields.Many2One('account.account', 'Round Down Account', required=True)
    )


class SaleChannel:
    __name__ = 'sale.channel'

    anonymous_customer = fields.Many2One(
        'party.party', "Anonymous Customer", states={
            'required': Eval('source') == 'pos',
            'invisible': Eval('source') != 'pos',
        }
    )

    # The warehouse from which backorders will be shipped.
    #
    # TODO: Default to channel's warehouse.
    backorder_warehouse = fields.Many2One(
        'stock.location', "Warehouse (Backorder)",
        domain=[('type', '=', 'warehouse')], states={
            'required': Eval('source') == 'pos',
            'invisible': Eval('source') != 'pos',
        }
    )

    delivery_mode = fields.Selection([
        (None, ''),
        ('pick_up', 'Pick Up'),
        ('ship', 'Ship'),
    ], 'Delivery Mode')

    @classmethod
    def get_source(cls):
        """
        Override the get_source method to add 'pos' as a source in channel
        """
        sources = super(SaleChannel, cls).get_source()
        sources.append(('pos', 'POS'))

        return sources

    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')
        cursor = Transaction().cursor
        table = TableHandler(cursor, cls, module_name)

        # Remove not null constraint from anonymous_customer
        table.not_null_action('anonymous_customer', action='remove')

        # Remove not null constraint from ship_to_warehouse
        table.not_null_action('ship_to_warehouse', action='remove')

        # Rename ship_to_warehouse to backorder_warehouse
        table.column_rename('ship_to_warehouse', 'backorder_warehouse')

        # Remove not null constraint from delivery_mode
        table.not_null_action('delivery_mode', action='remove')

        super(SaleChannel, cls).__register__(module_name)


class Sale:
    __name__ = "sale.sale"

    @staticmethod
    def default_party():
        User = Pool().get('res.user')
        user = User(Transaction().user)
        if (
            'use_anonymous_customer' not in Transaction().context
        ):  # pragma: no cover
            return
        if user.current_channel and user.current_channel.anonymous_customer:
            return user.current_channel.anonymous_customer.id

    @classmethod
    def __setup__(cls):
        super(Sale, cls).__setup__()
        cls.__rpc__.update({
            'pos_add_product': RPC(instantiate=0, readonly=False),
            'pos_serialize': RPC(instantiate=0, readonly=True),
            'get_recent_sales': RPC(readonly=True),
        })
        cls.lines.context = {
            'current_channel': Eval('channel'),
        }
        cls._buttons.update({
            'round_down_total': {
                'invisible': ~Eval('state').in_(['draft', 'quotation']),
            },
        })

    @classmethod
    @ModelView.button
    def round_down_total(cls, records):
        '''
        Round down total order price and add remaining amount as new sale line
        '''
        SaleLine = Pool().get('sale.line')

        sale_lines = []
        for record in records:
            # Check if there's already a roundoff line, remove and create new
            # if there is.
            round_off_line = SaleLine.search([
                ('sale', '=', record.id),
                ('is_round_off', '=', True),
            ])
            if round_off_line:
                SaleLine.delete(round_off_line)

            floored_total = floor(record.total_amount)
            amount_diff = record.total_amount - Decimal(floored_total)
            sale_lines.append({
                'sale': record,
                'is_round_off': True,
                'type': 'line',
                'quantity': -1,
                'unit_price': amount_diff,
                'description': 'Round Off'
            })

        SaleLine.create(
            [line for line in sale_lines if line['unit_price']]
        )

    @classmethod
    def get_recent_sales(cls):
        """
        Return sales of current channel, which were made within last 5 days
        and are in draft state. Sort by write_date or create_date of Sale and
        sale lines.
        """
        SaleLine = Pool().get('sale.line')

        context = Transaction().context
        date = (
            datetime.now() - timedelta(days=5)
        ).strftime('%Y-%m-%d %H:%M:%S')
        current_channel = context['current_channel']

        SaleTable = cls.__table__()
        SaleLineTable = SaleLine.__table__()

        cursor = Transaction().cursor
        query = SaleTable.join(
            SaleLineTable,
            condition=(SaleTable.id == SaleLineTable.sale)
        ).select(
            SaleTable.id,
            where=(
                (SaleTable.channel == Literal(current_channel)) &
                (SaleTable.state.in_([
                    'draft', 'quotation', 'confirmed', 'processing'
                ])) &
                (
                    (SaleTable.write_date >= Literal(date)) |
                    (SaleTable.create_date >= Literal(date))
                )
            ),
            order_by=(
                SaleLineTable.write_date.desc,
                SaleLineTable.create_date.desc,
                SaleTable.write_date.desc,
                SaleTable.create_date.desc
            )
        )
        cursor.execute(*query)
        ids = [x[0] for x in cursor.fetchall()]
        return [cls(id).serialize('recent_sales') for id in ids]

    def pos_find_sale_line_domain(self):
        """
        Return domain to find existing sale line for given product.
        """
        domain = [
            ('sale', '=', self.id),
        ]

        context = Transaction().context

        if 'product' in context:
            domain.append(('product', '=', context['product']))

        if 'delivery_mode' in context:
            domain.append(('delivery_mode', '=', context['delivery_mode']))

        return domain

    def pos_add_product(self, product_ids, quantity, unit_price=None):
        """
        Add product to sale from POS.
        This method is for POS, to add multiple products to cart in single call
        """
        AccountTax = Pool().get('account.tax')
        SaleLine = Pool().get('sale.line')

        updated_lines = []
        for product_id in product_ids:
            Transaction().set_context(product=product_id)
            try:
                if 'sale_line' in Transaction().context:
                    sale_line = SaleLine(Transaction().context.get('sale_line'))
                else:
                    sale_line, = SaleLine.search(
                        self.pos_find_sale_line_domain()
                    )
            except ValueError:
                sale_line = None

            delivery_mode = Transaction().context.get(
                'delivery_mode', 'pick_up'
            )

            if sale_line:
                values = {
                    'product': sale_line.product.id,
                    '_parent_sale.currency': self.currency.id,
                    '_parent_sale.party': self.party.id,
                    '_parent_sale.price_list': (
                        self.price_list.id if self.price_list else None
                    ),
                    '_parent_sale.sale_date': self.sale_date,
                    '_parent_sale.channel': self.channel,
                    '_parent_sale.shipment_address': self.shipment_address,
                    'warehouse': self.warehouse,
                    '_parent_sale.warehouse': self.warehouse,
                    'unit': sale_line.unit.id,
                    'quantity': quantity,
                    'type': 'line',
                    'delivery_mode': delivery_mode,
                }

                # Update the values by triggering an onchange which should
                # fill missing vals
                values.update(SaleLine(**values).on_change_quantity())
                values.update(SaleLine(**values).on_change_delivery_mode())

                values['unit_price'] = Decimal(unit_price) if unit_price else\
                    sale_line.unit_price

                new_values = {}
                for key, value in values.iteritems():
                    if '.' in key:
                        continue
                    if key == 'taxes':
                        # Difficult to reach here unless taxes change when
                        # quantities change.
                        continue    # pragma: no cover
                    new_values[key] = value
                SaleLine.write([sale_line], new_values)
            else:
                values = {
                    'product': product_id,
                    '_parent_sale.currency': self.currency.id,
                    '_parent_sale.party': self.party.id,
                    '_parent_sale.price_list': (
                        self.price_list.id if self.price_list else None
                    ),
                    '_parent_sale.sale_date': self.sale_date,
                    '_parent_sale.channel': self.channel,
                    '_parent_sale.shipment_address': self.shipment_address,
                    'warehouse': self.warehouse,
                    '_parent_sale.warehouse': self.warehouse,
                    'sale': self.id,
                    'type': 'line',
                    'quantity': quantity,
                    'unit': None,
                    'description': None,
                    'delivery_mode': delivery_mode,
                }
                values.update(SaleLine(**values).on_change_product())
                values.update(SaleLine(**values).on_change_quantity())
                values.update(SaleLine(**values).on_change_delivery_mode())
                new_values = {}
                for key, value in values.iteritems():
                    if '.' in key:
                        continue
                    if key == 'taxes':
                        continue
                    new_values[key] = value
                sale_line = SaleLine.create([new_values])[0]

            updated_lines.append(sale_line.id)
            if 'taxes' in values:
                sale_line.taxes = AccountTax.browse(values['taxes'])
                sale_line.save()

        # Now that the sale line is built, return a serializable response
        # which ensures that the client does not have to call again.
        res = {
            'sale': self.serialize('pos'),
            'updated_lines': updated_lines,
        }
        return res

    def pos_serialize(self):
        """
        Serialize sale for pos
        """
        return self.serialize('pos')

    def serialize(self, purpose=None):
        """
        Serialize with information needed for POS
        """
        if purpose == 'pos':
            invoice_address = self.invoice_address or \
                self.party.address_get('invoice')
            shipment_address = self.shipment_address or \
                self.party.address_get('delivery')
            return {
                'party': self.party.id,
                'total_amount': self.total_amount,
                'untaxed_amount': self.untaxed_amount,
                'tax_amount': self.tax_amount,
                'comment': self.comment,
                'state': self.state,
                'invoice_address': invoice_address and
                    invoice_address.serialize(purpose),
                'shipment_address': shipment_address and
                    shipment_address.serialize(purpose),
                'lines': [line.serialize(purpose) for line in self.lines],
                'reference': self.reference,
            }
        elif purpose == 'recent_sales':
            return {
                'id': self.id,
                'party': {
                    'id': self.party.id,
                    'name': self.party.name,
                },
                'total_amount': self.total_amount,
                'create_date': self.create_date,
                'state': self.state,
                'reference': self.reference,
            }
        elif hasattr(super(Sale, self), 'serialize'):
            return super(SaleLine, self).serialize(purpose)  # pragma: no cover

    def _group_shipment_key(self, moves, move):
        """
        This method returns a key based on which Tryton creates shipments
        for a given sale order. By default Tryton uses the planned_date for the
        delivery and warehouse to separate shipments.

        We use the same functionality to split the shipments for items being
        picked up and delivered. This is later used to auto proceed and finish
        the shipping of the picked up products.

        :param moves: A list of all moves
        :param move: move is a tuple of line id and a move
        """
        SaleLine = Pool().get('sale.line')

        line = SaleLine(move[0])
        rv = super(Sale, self)._group_shipment_key(moves, move)
        return rv + (('delivery_mode', line.delivery_mode),)

    _group_return_key = _group_shipment_key

    def create_shipment(self, shipment_type):
        """
        This method creates the shipments for the given sale order.

        This implementation inspects the order lines to look for lines which
        are expected to be picked up instantly and the shipment created for
        pick_up is automatically processed all the way through.
        """
        pool = Pool()

        shipments = super(Sale, self).create_shipment(shipment_type)

        if self.shipment_method == 'manual':
            # shipments will be None but for future return the value
            # returned by the super function
            return shipments

        if not shipments:
            return shipments

        picked_up_shipments = filter(
            lambda s: s.delivery_mode == 'pick_up', shipments
        )

        if shipment_type == 'out':
            Shipment = pool.get('stock.shipment.out')

            with Transaction().set_user(0, set_context=True):
                # If we are going to "process" a shipment, it is
                # equivalent to sale being processed.
                #
                # Doing this here helps in an edge case where the
                # sale total is 0. When a shipment is "Done" it
                # tries to recprocess the order state, but
                # usually this happens after sale is in
                # processing state. Since we push things through in the
                # next few lines, that call happens when the sale is in
                # confirmed state and there is no transition from
                # Confirmed to Done.
                self.state = 'processing'
                self.save()
                # Assign and complete the shipments
                if not Shipment.assign_try(picked_up_shipments):
                    draft_moves = filter(
                        lambda m: m.state == 'draft',
                        [m for s in picked_up_shipments for m in s.inventory_moves]  # noqa
                    )
                    products_out_of_stock = [
                        m.product.rec_name for m in draft_moves
                    ]
                    self.raise_user_error(
                        "Order cannot be processed as the following items are "
                        "out of stock:\n" + "\n".join(products_out_of_stock)
                    )
                Shipment.pack(picked_up_shipments)
                Shipment.done(picked_up_shipments)
        elif shipment_type == 'return':
            Shipment = pool.get('stock.shipment.out.return')
            with Transaction().set_user(0, set_context=True):
                Shipment.receive(picked_up_shipments)
                Shipment.done(picked_up_shipments)

        # Finally return the value the super function returned, but after
        # reloading the active records.
        return Shipment.browse(map(int, shipments))

    def create_invoice(self, invoice_type):
        """
        Sale creates draft invoices. But if the invoices are created from
        shipments, then they should be automatically opened
        """
        Invoice = Pool().get('account.invoice')

        invoice = super(Sale, self).create_invoice(invoice_type)

        if not invoice:
            return invoice

        if self.invoice_method == 'shipment':
            # Invoices created from shipment can be automatically opened
            # for payment.
            Invoice.post([invoice])

        return invoice


class SaleLine:
    __name__ = 'sale.line'

    is_round_off = fields.Boolean('Round Off', readonly=True)

    delivery_mode = fields.Selection([
        (None, ''),
        ('pick_up', 'Pick Up'),
        ('ship', 'Ship'),
    ], 'Delivery Mode', states={
        'invisible': Eval('type') != 'line',
        'required': And(
            Eval('type') == 'line',
            Bool(Eval('product_type_is_goods'))
        )
    }, depends=['type', 'product_type_is_goods'])

    product_type_is_goods = fields.Function(
        fields.Boolean('Product Type is Goods?'), 'get_product_type_is_goods'
    )

    @classmethod
    def __register__(cls, module_name):
        super(SaleLine, cls).__register__(module_name)

        TableHandler = backend.get('TableHandler')
        cursor = Transaction().cursor

        table = TableHandler(cursor, cls, module_name)

        table.not_null_action('delivery_mode', action='remove')

    @classmethod
    def __setup__(cls):
        super(SaleLine, cls).__setup__()

        # Hide product and unit fields.
        cls.product.states['invisible'] |= Bool(Eval('is_round_off'))
        cls.unit.states['invisible'] |= Bool(Eval('is_round_off'))
        cls.delivery_mode.states['invisible'] |= Bool(Eval('is_round_off'))
        cls.product.depends.insert(0, 'is_round_off')
        cls.unit.depends.insert(0, 'is_round_off')

    @fields.depends(
        'product', 'unit', 'quantity', '_parent_sale.party',
        '_parent_sale.currency', '_parent_sale.sale_date', 'delivery_mode',
        '_parent_sale.channel', '_parent_sale.shipment_address',
        'warehouse', '_parent_sale.warehouse'
    )
    def on_change_delivery_mode(self):
        """
        This method can be overridden by downstream modules to make changes
        according to delivery mode. Like change taxes according to delivery
        mode.
        """
        res = {}
        if self.delivery_mode == 'ship' and \
                self.sale.channel.backorder_warehouse:
            res['warehouse'] = self.sale.channel.backorder_warehouse.id
        return res

    @fields.depends('_parent_sale.channel')
    def on_change_product(self):
        """
        Set fulfil strategy on sale line from channel
        """
        res = super(SaleLine, self).on_change_product()

        if self.sale.channel and self.sale.channel.delivery_mode:
            res['delivery_mode'] = self.sale.channel.delivery_mode

        return res

    @staticmethod
    def default_delivery_mode():
        Channel = Pool().get('sale.channel')
        User = Pool().get('res.user')

        user = User(Transaction().user)
        sale_channel = user.current_channel
        if Transaction().context.get('current_channel'):
            sale_channel = Channel(
                Transaction().context.get('current_channel')
            )
        return sale_channel and sale_channel.delivery_mode

    @staticmethod
    def default_is_round_off():
        return False

    def get_invoice_line(self, invoice_type):
        SaleConfiguration = Pool().get('sale.configuration')
        InvoiceLine = Pool().get('account.invoice.line')

        if not self.is_round_off:
            return super(SaleLine, self).get_invoice_line(invoice_type)

        # The line is a round off line and apply the logic here.

        # Check if the invoice line already exists for the sale line
        # If yes, then no line needs to be created
        # XXX: What if the invoice was cancelled ?
        if self.invoice_lines:
            return []

        round_down_account = SaleConfiguration(1).round_down_account
        if not round_down_account:
            self.raise_user_error(
                '''Set round down account from Sale Configuration to
                add round off line'''
            )

        invoice_line = InvoiceLine()
        invoice_line.origin = self
        invoice_line.account = round_down_account
        invoice_line.unit_price = self.unit_price
        invoice_line.description = self.description

        # For positive sales transactions (where the order is effectively
        # a positive total), the round_down is applied on out_invoice
        # and if overall order total is negative, then the round_down is
        # tied to credit note.
        if self.sale.total_amount >= Decimal('0'):
            if invoice_type == 'out_credit_note':
                # positive order looking for credit note
                return []
            invoice_line.quantity = self.quantity
        else:
            if invoice_type == 'out_invoice':
                # negative order looking for invoice
                return []
            invoice_line.quantity = -self.quantity

        return [invoice_line]

    def serialize(self, purpose=None):
        """
        Serialize for the purpose of POS
        """
        if purpose == 'pos':
            return {
                'id': self.id,
                'description': self.description,
                'product': self.product and {
                    'id': self.product.id,
                    'code': self.product.code,
                    'rec_name': self.product.rec_name,
                    'default_image': self.product.default_image and
                                    self.product.default_image.id,
                },
                'unit': self.unit and {
                    'id': self.unit.id,
                    'rec_name': self.unit.rec_name,
                },
                'unit_price': self.unit_price,
                'quantity': self.quantity,
                'amount': self.amount,
                'delivery_mode': self.delivery_mode
            }
        elif hasattr(super(SaleLine, self), 'serialize'):
            return super(SaleLine, self).serialize(purpose)  # pragma: no cover

    def get_product_type_is_goods(self, name):
        """
        Return True if product is of type goods
        """
        if self.product and self.product.type == 'goods':
            return True
        return False
