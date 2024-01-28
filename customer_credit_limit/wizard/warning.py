from odoo import models, fields, _


class RaiseWarning(models.TransientModel):
    _name = "warning.warning"
    _description = "Warning"

    name = fields.Char("Credit Limit")
    manager_approve = fields.Boolean('')
    credit = fields.Float("Total Receivable", help="Total amount this customer owes you.")
    def action_confirm(self):
        order = self.env['sale.order'].browse(self._context.get('active_id'))
        if order.exists():
            return order.with_context(skip_credit_check=True).action_confirm()

    def action_approve_credit_limit(self):
        order = self.env['sale.order'].browse(self._context.get('active_id'))

        if self.env.user.has_group('sales_team.group_sale_manager'):
            order.credit_approve = True
        else:
            order.write({'state': 'request'})