from odoo import api,models,fields
from odoo.exceptions import ValidationError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, float_compare, float_round

class SaleOrderInherited(models.Model):
    _inherit = 'sale.order'
    _description = 'Add Alert when unlock'

    def action_unlock(self):
        picking_type_id = self.env['stock.picking.type'].search([('sequence_code','=','OUT'),('warehouse_id','=',self.warehouse_id.id)])
        picking_ids = self.env['stock.picking'].search([('sale_id','=',self.id),('picking_type_id','=',picking_type_id.id),('state','=','done')])
        if picking_ids:
            for picking in picking_ids:
                quantity = 0.0
                for stock in picking.move_lines:
                    quantity = stock.product_qty
                    for move in stock.move_dest_ids:
                        if move.state in ('partially_available', 'assigned'):
                            quantity -= sum(move.move_line_ids.mapped('product_qty'))
                        elif move.state in ('done'):
                            quantity -= move.product_qty
                    quantity = float_round(quantity, precision_rounding=stock.product_uom.rounding)
                    if quantity == 0 or self.order_line.filtered(lambda r: r.product_uom_qty != r.qty_delivered):
                        continue
                    else:
                        raise ValidationError('Need to return good Delivery before unlock.')
        self.write({'state': 'sale'})

    def action_done(self):
        for order in self:
            tx = order.sudo().transaction_ids._get_last()
            if tx and tx.state == 'pending' and tx.acquirer_id.provider == 'transfer':
                tx._set_transaction_done()
                tx.write({'is_processed': True})
        lines = self.order_line.filtered(lambda r: r.product_uom_qty != r.qty_delivered)
        previous_product_uom_qty = {line.id: line.product_uom_qty - line.qty_delivered for line in lines}
        if lines and self.state=='sale':
            lines._action_launch_stock_rule(previous_product_uom_qty)
        return self.write({'state': 'done'})



