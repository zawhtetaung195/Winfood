from odoo import models,fields

class SaleOrder(models.Model):
    _inherit = "sale.order"
    customer_confirmation = fields.Boolean(string="Customer Information")

    def action_customerIfo(self):
        for rec in self:
            rec.customer_confirmation = True

    def all_of_orders(self, domain):
        return self.env['sale.order'].sudo().search(domain)
