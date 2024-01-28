from odoo import models, fields


class StockMoveInherit(models.Model):
    _inherit = 'stock.move'

    def button_set_to_draft(self):
        return self.write({'state':'draft'}) 
        
class StockPickingInherit(models.Model):
    _inherit = 'stock.picking'

    def button_set_to_draft(self):
        self.mapped('move_lines').button_set_to_draft()
        return self.write({'state':'draft'})




