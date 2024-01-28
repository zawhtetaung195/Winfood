from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools import float_round
from odoo.tools import OrderedSet
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from collections import defaultdict

class MrpBomLineInherit(models.Model):
    _inherit = 'mrp.bom.line'

    product_qty = fields.Float('Quantity', default=1.0, digits='Product Unit of Measure For BOM', required=True)

class MrpProductionInherit(models.Model):
    _inherit = 'mrp.production'
    product_qty = fields.Float('Quantity To Produce', default=1.0, digits='Product Unit of Measure For BOM', readonly=True, required=True, tracking=True, states={'draft': [('readonly', False)]})
    qty_producing = fields.Float(string="Quantity Producing", digits='Product Unit of Measure For BOM', copy=False)

    def button_mark_done(self):
        self._button_mark_done_sanity_checks()

        if not self.env.context.get('button_mark_done_production_ids'):
            self = self.with_context(button_mark_done_production_ids=self.ids)
        res = self._pre_button_mark_done()
        if res is not True:
            return res

        if self.env.context.get('mo_ids_to_backorder'):
            productions_to_backorder = self.browse(self.env.context['mo_ids_to_backorder'])
            productions_not_to_backorder = self - productions_to_backorder
            close_mo = False
        else:
            productions_not_to_backorder = self
            productions_to_backorder = self.env['mrp.production']
            close_mo = True

        self.workorder_ids.button_finish()

        backorders = productions_to_backorder._generate_backorder_productions(close_mo=close_mo)
        productions_not_to_backorder._post_inventory(cancel_backorder=True)
        productions_to_backorder._post_inventory(cancel_backorder=True)

        # if completed products make other confirmed/partially_available moves available, assign them
        done_move_finished_ids = (productions_to_backorder.move_finished_ids | productions_not_to_backorder.move_finished_ids).filtered(lambda m: m.state == 'done')
        done_move_finished_ids._trigger_assign()

        # Moves without quantity done are not posted => set them as done instead of canceling. In
        # case the user edits the MO later on and sets some consumed quantity on those, we do not
        # want the move lines to be canceled.
        (productions_not_to_backorder.move_raw_ids | productions_not_to_backorder.move_finished_ids).filtered(lambda x: x.state not in ('done', 'cancel')).write({
            'state': 'done',
            'product_uom_qty': 0.0,
        })

        for production in self:
            production.write({
                'date_finished': fields.Datetime.now(),
                # 'product_qty': production.qty_produced, #SLO commend
                'priority': '0',
                'is_locked': True,
                'state': 'done',
            })

        for workorder in self.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel')):
            workorder.duration_expected = workorder._get_duration_expected()

        if not backorders:
            if self.env.context.get('from_workorder'):
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'mrp.production',
                    'views': [[self.env.ref('mrp.mrp_production_form_view').id, 'form']],
                    'res_id': self.id,
                    'target': 'main',
                }
            return True
        context = self.env.context.copy()
        context = {k: v for k, v in context.items() if not k.startswith('default_')}
        for k, v in context.items():
            if k.startswith('skip_'):
                context[k] = False
        action = {
            'res_model': 'mrp.production',
            'type': 'ir.actions.act_window',
            'context': dict(context, mo_ids_to_backorder=None, button_mark_done_production_ids=None)
        }
        if len(backorders) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': backorders[0].id,
            })
        else:
            action.update({
                'name': _("Backorder MO"),
                'domain': [('id', 'in', backorders.ids)],
                'view_mode': 'tree,form',
            })
        return action


class UOMInherit(models.Model):
    _inherit = 'uom.uom'

    rounding = fields.Float(
        'Rounding Precision', default=0.001, digits='Product Unit of Measure For BOM', required=True,
        help="The computed quantity will be a multiple of this value. "
             "Use 1.0 for a Unit of Measure that cannot be further split, such as a piece.")

    # product_qty = fields.Float(
    #     'Real Quantity', compute='_compute_product_qty', inverse='_set_product_qty',
    #     digits='Product Unit of Measure For BOM', store=True, compute_sudo=True,
    #     help='Quantity in the default UoM of the product')
    # product_uom_qty = fields.Float(
    #     'Reserved', default=0.0, digits='Product Unit of Measure For BOM', required=True, copy=False)
    # forecast_availability = fields.Float('Forecast Availability', compute='_compute_forecast_information', default=0.0, digits='Product Unit of Measure For BOM', compute_sudo=True)
    # quantity_done = fields.Float('Quantity Done', compute='_quantity_done_compute', digits='Product Unit of Measure For BOM', inverse='_quantity_done_set')


    # def _get_moves_raw_values(self):
    #     moves = []
    #     for production in self:
    #         if not production.bom_id:
    #             continue
    #         factor = production.product_uom_id._compute_quantity(production.product_qty, production.bom_id.product_uom_id) / production.bom_id.product_qty
    #         boms, lines = production.bom_id.explode(production.product_id, factor, picking_type=production.bom_id.picking_type_id)
    #         for bom_line, line_data in lines:
    #             if bom_line.child_bom_id and bom_line.child_bom_id.type == 'phantom' or\
    #                     bom_line.product_id.type not in ['product', 'consu']:
    #                 continue
    #             operation = bom_line.operation_id.id or line_data['parent_line'] and line_data['parent_line'].operation_id.id
    #             moves.append(production._get_move_raw_values(
    #                 bom_line.product_id,
    #                 line_data['qty'],
    #                 bom_line.product_uom_id,
    #                 operation,
    #                 bom_line
    #             ))
    #     return moves

class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    product_qty = fields.Float('Quantity', default=1.0, digits='Product Unit of Measure For BOM', required=True)

    def explode(self, product, quantity, picking_type=False):
        """
            Explodes the BoM and creates two lists with all the information you need: bom_done and line_done
            Quantity describes the number of times you need the BoM: so the quantity divided by the number created by the BoM
            and converted into its UoM
        """
        from collections import defaultdict

        graph = defaultdict(list)
        V = set()

        def check_cycle(v, visited, recStack, graph):
            visited[v] = True
            recStack[v] = True
            for neighbour in graph[v]:
                if visited[neighbour] == False:
                    if check_cycle(neighbour, visited, recStack, graph) == True:
                        return True
                elif recStack[neighbour] == True:
                    return True
            recStack[v] = False
            return False

        product_ids = set()
        product_boms = {}
        def update_product_boms():
            products = self.env['product.product'].browse(product_ids)
            product_boms.update(self._bom_find(products, picking_type=picking_type or self.picking_type_id,
                company_id=self.company_id.id, bom_type='phantom'))
            # Set missing keys to default value
            for product in products:
                product_boms.setdefault(product, self.env['mrp.bom'])

        boms_done = [(self, {'qty': quantity, 'product': product, 'original_qty': quantity, 'parent_line': False})]
        lines_done = []
        V |= set([product.product_tmpl_id.id])

        bom_lines = []
        for bom_line in self.bom_line_ids:
            product_id = bom_line.product_id
            V |= set([product_id.product_tmpl_id.id])
            graph[product.product_tmpl_id.id].append(product_id.product_tmpl_id.id)
            bom_lines.append((bom_line, product, quantity, False))
            product_ids.add(product_id.id)
        update_product_boms()
        product_ids.clear()
        while bom_lines:
            current_line, current_product, current_qty, parent_line = bom_lines[0]
            bom_lines = bom_lines[1:]

            if current_line._skip_bom_line(current_product):
                continue

            line_quantity = current_qty * current_line.product_qty
            if not current_line.product_id in product_boms:
                update_product_boms()
                product_ids.clear()
            bom = product_boms.get(current_line.product_id)
            if bom:
                converted_line_quantity = current_line.product_uom_id._compute_quantity(line_quantity / bom.product_qty, bom.product_uom_id)
                bom_lines += [(line, current_line.product_id, converted_line_quantity, current_line) for line in bom.bom_line_ids]
                for bom_line in bom.bom_line_ids:
                    graph[current_line.product_id.product_tmpl_id.id].append(bom_line.product_id.product_tmpl_id.id)
                    if bom_line.product_id.product_tmpl_id.id in V and check_cycle(bom_line.product_id.product_tmpl_id.id, {key: False for  key in V}, {key: False for  key in V}, graph):
                        raise UserError(_('Recursion error!  A product with a Bill of Material should not have itself in its BoM or child BoMs!'))
                    V |= set([bom_line.product_id.product_tmpl_id.id])
                    if not bom_line.product_id in product_boms:
                        product_ids.add(bom_line.product_id.id)
                boms_done.append((bom, {'qty': converted_line_quantity, 'product': current_product, 'original_qty': quantity, 'parent_line': current_line}))
            else:
                # We round up here because the user expects that if he has to consume a little more, the whole UOM unit
                # should be consumed.
                rounding = current_line.product_uom_id.rounding
                line_quantity = line_quantity
                lines_done.append((current_line, {'qty': line_quantity, 'product': current_product, 'original_qty': quantity, 'parent_line': parent_line}))

        return boms_done, lines_done

class StockMoveInherit(models.Model):
    _inherit = 'stock.move'
    product_uom_qty = fields.Float('Demand',
    digits='Product Unit of Measure For BOM',
    default=1.0, required=True, states={'done': [('readonly', True)]},
    help="This is the quantity of products from an inventory "
            "point of view. For moves in the state 'done', this is the "
            "quantity of products that were actually moved. For other "
            "moves, this is the quantity of product that is planned to "
            "be moved. Lowering this quantity does not generate a "
            "backorder. Changing this quantity on assigned moves affects "
            "the product reservation, and should be done with care.")
    forecast_availability = fields.Float('Forecast Availability', compute='_compute_forecast_information', default=0.000, digits='Product Unit of Measure For BOM', compute_sudo=True)
    quantity_done = fields.Float('Quantity Done', compute='_quantity_done_compute', digits='Product Unit of Measure For BOM', inverse='_quantity_done_set')
    reserved_availability = fields.Float(
        'Quantity Reserved', compute='_compute_reserved_availability',
        digits='Product Unit of Measure For BOM',
        readonly=True, help='Quantity that has already been reserved for this move')

    should_consume_qty = fields.Float('Quantity To Consume', compute='_compute_should_consume_qty', digits='Product Unit of Measure For BOM')

    @api.depends('product_id', 'product_qty', 'picking_type_id', 'reserved_availability', 'priority', 'state', 'product_uom_qty', 'location_id')
    def _compute_forecast_information(self):
        """ Compute forecasted information of the related product by warehouse."""
        self.forecast_availability = False
        self.forecast_expected_date = False

        # Prefetch product info to avoid fetching all product fields
        self.product_id.read(['type', 'uom_id'], load=False)

        not_product_moves = self.filtered(lambda move: move.product_id.type != 'product')
        for move in not_product_moves:
            move.forecast_availability = move.product_qty

        product_moves = (self - not_product_moves)

        outgoing_unreserved_moves_per_warehouse = defaultdict(set)
        now = fields.Datetime.now()

        def key_virtual_available(move, incoming=False):
            warehouse_id = move.location_dest_id.warehouse_id.id if incoming else move.location_id.warehouse_id.id
            return warehouse_id, max(move.date, now)

        # Prefetch efficiently virtual_available for _consuming_picking_types draft move.
        prefetch_virtual_available = defaultdict(set)
        virtual_available_dict = {}
        for move in product_moves:
            if move.picking_type_id.code in self._consuming_picking_types() and move.state == 'draft':
                prefetch_virtual_available[key_virtual_available(move)].add(move.product_id.id)
            elif move.picking_type_id.code == 'incoming':
                prefetch_virtual_available[key_virtual_available(move, incoming=True)].add(move.product_id.id)
        for key_context, product_ids in prefetch_virtual_available.items():
            read_res = self.env['product.product'].browse(product_ids).with_context(warehouse=key_context[0], to_date=key_context[1]).read(['virtual_available'])
            virtual_available_dict[key_context] = {res['id']: res['virtual_available'] for res in read_res}

        for move in product_moves:
            if move.picking_type_id.code in self._consuming_picking_types():
                if move.state == 'assigned':
                    # move.forecast_availability = move.product_uom._compute_quantity(
                    #     move.reserved_availability, move.product_id.uom_id, rounding_method='HALF-UP')
                    move.forecast_availability = move.product_uom_qty
                    # print (move.forecast_availability,move.product_uom_qty,'forecast_availability---------------------------------------') #SLO
                elif move.state == 'draft':
                    # for move _consuming_picking_types and in draft -> the forecast_availability > 0 if in stock
                    move.forecast_availability = virtual_available_dict[key_virtual_available(move)][move.product_id.id] - move.product_qty
                    if move.raw_material_production_id:
                        move.forecast_availability = move.product_uom_qty
                    # print (move.forecast_availability,move.product_uom_qty,'forecast_availability---------------------------------------') #SLO
                elif move.state in ('waiting', 'confirmed', 'partially_available'):
                    outgoing_unreserved_moves_per_warehouse[move.location_id.warehouse_id].add(move.id)
            elif move.picking_type_id.code == 'incoming':
                forecast_availability = virtual_available_dict[key_virtual_available(move, incoming=True)][move.product_id.id]
                if move.state == 'draft':
                    forecast_availability += move.product_qty
                move.forecast_availability = forecast_availability

        for warehouse, moves_ids in outgoing_unreserved_moves_per_warehouse.items():
            if not warehouse:  # No prediction possible if no warehouse.
                continue
            moves = self.browse(moves_ids)
            forecast_info = moves._get_forecast_availability_outgoing(warehouse)
            for move in moves:
                move.forecast_availability, move.forecast_expected_date = forecast_info[move]

    # @api.depends('move_line_ids.qty_done', 'move_line_ids.product_uom_id', 'move_line_nosuggest_ids.qty_done', 'picking_type_id.show_reserved')
    # def _quantity_done_compute(self):
    #     # print('stock move ------------------------------------>><<',self.ids)
    #     """ This field represents the sum of the move lines `qty_done`. It allows the user to know
    #     if there is still work to do.

    #     We take care of rounding this value at the general decimal precision and not the rounding
    #     of the move's UOM to make sure this value is really close to the real sum, because this
    #     field will be used in `_action_done` in order to know if the move will need a backorder or
    #     an extra move.
    #     """
    #     if not any(self._ids):
    #         # print('not any(self._ids)====================>>>')
    #         # onchange
    #         for move in self:
    #             quantity_done = 0
    #             for move_line in move._get_move_lines():
    #                 quantity_done += move_line.product_uom_id._compute_quantity(
    #                     move_line.qty_done, move.product_uom, round=False)
    #             move.quantity_done = quantity_done
    #     else:
    #         # compute
    #         move_lines_ids = set()
    #         for move in self:
    #             move_lines_ids |= set(move._get_move_lines().ids)

    #         data = self.env['stock.move.line'].read_group(
    #             [('id', 'in', list(move_lines_ids))],
    #             ['move_id', 'product_uom_id', 'qty_done'], ['move_id', 'product_uom_id'],
    #             lazy=False
    #         )

    #         rec = defaultdict(list)
    #         for d in data:
    #             rec[d['move_id'][0]] += [(d['product_uom_id'][0], d['qty_done'])]

    #         for move in self:
    #             uom = move.product_uom
    #             move.quantity_done = sum(
    #                 self.env['uom.uom'].browse(line_uom_id)._compute_quantity(qty, uom, round=False)
    #                  for line_uom_id, qty in rec.get(move.ids[0] if move.ids else move.id, [])
    #             )
    #             # print('move.raw_material_production_id---------------------------->>><<<',move.raw_material_production_id)
    #             if move.raw_material_production_id:
    #                 move.quantity_done = move.forecast_availability
                # print(self.env.context.get('active_ids'),'move.quantity done 000000=================>>>>',move.quantity_done)#SLO

    @api.depends('move_line_ids.product_qty')
    def _compute_reserved_availability(self):
        """ Fill the `availability` field on a stock move, which is the actual reserved quantity
        and is represented by the aggregated `product_qty` on the linked move lines. If the move
        is force assigned, the value will be 0.
        """
        if not any(self._ids):
            # onchange
            for move in self:
                reserved_availability = sum(move.move_line_ids.mapped('product_qty'))
                move.reserved_availability = move.product_id.uom_id._compute_quantity(
                    reserved_availability, move.product_uom)
                if move.raw_material_production_id:
                    move.reserved_availability = move.forecast_availability
                # print('move.reserved_availability===================11',move.reserved_availability)
        else:
            # compute
            result = {data['move_id'][0]: data['product_qty'] for data in
                      self.env['stock.move.line'].read_group([('move_id', 'in', self.ids)], ['move_id', 'product_qty'], ['move_id'])}
            for move in self:
                move.reserved_availability = move.product_id.uom_id._compute_quantity(
                    result.get(move.id, 0.0), move.product_uom)
                # print(move.raw_material_production_id,"move.forecast_availability===^^^^^^^",move.forecast_availability)
                if move.raw_material_production_id:
                    move.reserved_availability = move.forecast_availability
                # print('move.reserved_availability===================22',move.reserved_availability)


    @api.depends('raw_material_production_id.qty_producing', 'product_uom_qty', 'product_uom')
    def _compute_should_consume_qty(self):
        for move in self:
            mo = move.raw_material_production_id
            if not mo or not move.product_uom:
                move.should_consume_qty = 0
                continue
            move.should_consume_qty = float_round((mo.qty_producing - mo.qty_produced) * move.unit_factor, precision_rounding=0.00001)
            # print('should_consume_qty===========================>>>',move.should_consume_qty )
    
class MRPWorkorderinherit(models.Model):
    _inherit = 'mrp.workorder'

    qty_producing = fields.Float(
        compute='_compute_qty_producing', inverse='_set_qty_producing',
        string='Currently Produced Quantity', digits='Product Unit of Measure For BOM')
    qty_remaining = fields.Float('Quantity To Be Produced', compute='_compute_qty_remaining', digits='Product Unit of Measure For BOM')
    qty_produced = fields.Float(
        'Quantity', default=0.0,
        readonly=True,
        digits='Product Unit of Measure For BOM',
        copy=False,
        help="The number of products already handled by this work order")

class ChangeProductQTY(models.TransientModel):
    _inherit = 'change.production.qty'

    product_qty = fields.Float(
        'Quantity To Produce',
        digits='Product Unit of Measure For BOM', required=True)

class StockQuantInherit(models.Model):
    _inherit = 'stock.quant'

    inventory_quantity = fields.Float(
        'Counted Quantity', digits='Product Unit of Measure For BOM',
        help="The product's counted quantity.")
    reserved_quantity = fields.Float(
        'Reserved Quantity',
        default=0.0,
        help='Quantity of reserved products in this quant, in the default unit of measure of the product',
        readonly=True, required=True, digits='Product Unit of Measure For BOM')
    available_quantity = fields.Float(
        'Available Quantity',
        help="On hand quantity which hasn't been reserved on a transfer, in the default unit of measure of the product",
        compute='_compute_available_quantity', digits='Product Unit of Measure For BOM')
    quantity = fields.Float(
        'Quantity',
        help='Quantity of products in this quant, in the default unit of measure of the product',
        readonly=True, digits='Product Unit of Measure For BOM')
    inventory_quantity_auto_apply = fields.Float(
        'Inventoried Quantity', compute='_compute_inventory_quantity_auto_apply',
        inverse='_set_inventory_quantity', groups='stock.group_stock_manager',digits='Product Unit of Measure For BOM'
    )
    qty_produced = fields.Float(compute="_get_produced_qty", string="Quantity Produced",digits='Product Unit of Measure For BOM')
    inventory_diff_quantity = fields.Float(
        'Difference', compute='_compute_inventory_diff_quantity', store=True,
        help="Indicates the gap between the product's theoretical quantity and its counted quantity.",
        readonly=True, digits='Product Unit of Measure For BOM')


class StockMoveLineInherit(models.Model):
    _inherit = 'stock.move.line'

    qty_done = fields.Float('Done', default=0.0, digits='Product Unit of Measure For BOM', copy=False)
    product_uom_qty = fields.Float(
        'Reserved', default=0.0, digits='Product Unit of Measure For BOM', required=True, copy=False)
    product_qty = fields.Float(
        'Real Reserved Quantity', digits=0, copy=False,
        compute='_compute_product_qty', inverse='_set_product_qty', store=True)#

    def _set_product_qty(self):
        return True

    def _action_done(self):
        """ This method is called during a move's `action_done`. It'll actually move a quant from
        the source location to the destination location, and unreserve if needed in the source
        location.

        This method is intended to be called on all the move lines of a move. This method is not
        intended to be called when editing a `done` move (that's what the override of `write` here
        is done.
        """
        Quant = self.env['stock.quant']

        # First, we loop over all the move lines to do a preliminary check: `qty_done` should not
        # be negative and, according to the presence of a picking type or a linked inventory
        # adjustment, enforce some rules on the `lot_id` field. If `qty_done` is null, we unlink
        # the line. It is mandatory in order to free the reservation and correctly apply
        # `action_done` on the next move lines.
        ml_ids_tracked_without_lot = OrderedSet()
        ml_ids_to_delete = OrderedSet()
        ml_ids_to_create_lot = OrderedSet()
        for ml in self:
            # Check here if `ml.qty_done` respects the rounding of `ml.product_uom_id`.
            uom_qty = float_round(ml.qty_done, precision_rounding=ml.product_uom_id.rounding, rounding_method='HALF-UP')
            precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            qty_done = float_round(ml.qty_done, precision_digits=precision_digits, rounding_method='HALF-UP')
            if float_compare(uom_qty, qty_done, precision_digits=precision_digits) != 0:
                raise UserError(_('The quantity done for the product "%s" doesn\'t respect the rounding precision '
                                  'defined on the unit of measure "%s". Please change the quantity done or the '
                                  'rounding precision of your unit of measure.') % (ml.product_id.display_name, ml.product_uom_id.name))

            qty_done_float_compared = float_compare(ml.qty_done, 0, precision_rounding=ml.product_uom_id.rounding)
            if qty_done_float_compared > 0:
                if ml.product_id.tracking != 'none':
                    picking_type_id = ml.move_id.picking_type_id
                    if picking_type_id:
                        if picking_type_id.use_create_lots:
                            # If a picking type is linked, we may have to create a production lot on
                            # the fly before assigning it to the move line if the user checked both
                            # `use_create_lots` and `use_existing_lots`.
                            if ml.lot_name and not ml.lot_id:
                                lot = self.env['stock.production.lot'].search([
                                    ('company_id', '=', ml.company_id.id),
                                    ('product_id', '=', ml.product_id.id),
                                    ('name', '=', ml.lot_name),
                                ], limit=1)
                                if lot:
                                    ml.lot_id = lot.id
                                else:
                                    ml_ids_to_create_lot.add(ml.id)
                        elif not picking_type_id.use_create_lots and not picking_type_id.use_existing_lots:
                            # If the user disabled both `use_create_lots` and `use_existing_lots`
                            # checkboxes on the picking type, he's allowed to enter tracked
                            # products without a `lot_id`.
                            continue
                    elif ml.is_inventory:
                        # If an inventory adjustment is linked, the user is allowed to enter
                        # tracked products without a `lot_id`.
                        continue

                    if not ml.lot_id and ml.id not in ml_ids_to_create_lot:
                        ml_ids_tracked_without_lot.add(ml.id)
            elif qty_done_float_compared < 0:
                raise UserError(_('No negative quantities allowed'))
            elif not ml.is_inventory:
                ml_ids_to_delete.add(ml.id)

        if ml_ids_tracked_without_lot:
            mls_tracked_without_lot = self.env['stock.move.line'].browse(ml_ids_tracked_without_lot)
            raise UserError(_('You need to supply a Lot/Serial Number for product: \n - ') +
                              '\n - '.join(mls_tracked_without_lot.mapped('product_id.display_name')))
        ml_to_create_lot = self.env['stock.move.line'].browse(ml_ids_to_create_lot)
        ml_to_create_lot._create_and_assign_production_lot()

        mls_to_delete = self.env['stock.move.line'].browse(ml_ids_to_delete)
        mls_to_delete.unlink()

        mls_todo = (self - mls_to_delete)
        mls_todo._check_company()

        # Now, we can actually move the quant.
        ml_ids_to_ignore = OrderedSet()
        for ml in mls_todo:
            if ml.product_id.type == 'product':
                rounding = ml.product_uom_id.rounding

                # if this move line is force assigned, unreserve elsewhere if needed
                if not ml.move_id._should_bypass_reservation(ml.location_id) and float_compare(ml.qty_done, ml.product_uom_qty, precision_rounding=rounding) > 0:
                    qty_done_product_uom = ml.product_uom_id._compute_quantity(ml.qty_done, ml.product_id.uom_id, rounding_method='HALF-UP')
                    # print(ml.move_id.raw_material_production_id,'------------------------------mr production')
                    if ml.move_id.raw_material_production_id:
                        qty_done_product_uom = ml.qty_done
                    # print('qty_done_product_uom------------------------------>>',qty_done_product_uom,'-----',ml.qty_done)#SLO
                    
                    extra_qty = qty_done_product_uom - ml.product_qty
                    # print('extra_qty------------------------>>',extra_qty)
                    ml._free_reservation(ml.product_id, ml.location_id, extra_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id, ml_ids_to_ignore=ml_ids_to_ignore)
                # unreserve what's been reserved
                if not ml.move_id._should_bypass_reservation(ml.location_id) and ml.product_id.type == 'product' and ml.product_qty:
                    # print('----------------------------------------------------------------------------------------->>',ml.qty_done)
                    if ml.move_id.raw_material_production_id:
                        ml.product_qty = ml.qty_done
                    try:
                        Quant._update_reserved_quantity(ml.product_id, ml.location_id, -ml.product_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)
                    except UserError:
                        Quant._update_reserved_quantity(ml.product_id, ml.location_id, -ml.product_qty, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)

                # move what's been actually done
                quantity = ml.product_uom_id._compute_quantity(ml.qty_done, ml.move_id.product_id.uom_id, rounding_method='HALF-UP')
                available_qty, in_date = Quant._update_available_quantity(ml.product_id, ml.location_id, -quantity, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id)
                if available_qty < 0 and ml.lot_id:
                    # see if we can compensate the negative quants with some untracked quants
                    untracked_qty = Quant._get_available_quantity(ml.product_id, ml.location_id, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id, strict=True)
                    if untracked_qty:
                        taken_from_untracked_qty = min(untracked_qty, abs(quantity))
                        Quant._update_available_quantity(ml.product_id, ml.location_id, -taken_from_untracked_qty, lot_id=False, package_id=ml.package_id, owner_id=ml.owner_id)
                        Quant._update_available_quantity(ml.product_id, ml.location_id, taken_from_untracked_qty, lot_id=ml.lot_id, package_id=ml.package_id, owner_id=ml.owner_id)
                Quant._update_available_quantity(ml.product_id, ml.location_dest_id, quantity, lot_id=ml.lot_id, package_id=ml.result_package_id, owner_id=ml.owner_id, in_date=in_date)
            ml_ids_to_ignore.add(ml.id)
        # Reset the reserved quantity as we just moved it to the destination location.
        mls_todo.with_context(bypass_reservation_update=True).write({
            'product_uom_qty': 0.00,
            'date': fields.Datetime.now(),
        })
