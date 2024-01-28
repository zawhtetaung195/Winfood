from odoo import models,fields,_

class AccountMove(models.Model):
    _inherit = "account.move"
    customer_confirmation = fields.Boolean(string="Customer Information")

    def action_customerIfo(self):
        for rec in self:
            rec.customer_confirmation = True
