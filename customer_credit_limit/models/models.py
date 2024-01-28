from odoo import models, fields, api, _

class ResPartner(models.Model):
    _inherit = 'res.partner'

    amount_credit_limit = fields.Monetary('Credit Limit')

class SaleOrder(models.Model):
    _inherit = "sale.order"

    state = fields.Selection([
        ('draft', 'Quotation'),
        ('request','Request'),
        ('sent', 'Quotation Sent'),
        ('sale', 'Sales Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
        ], string='Status', readonly=True, copy=False, index=True, tracking=3, default='draft')
        
    credit_approve = fields.Boolean('Approved', default=False)
    manager_approve = fields.Boolean(default=False,compute='compute_manager_approve')

    def compute_manager_approve(self):
        for rec in self:
            result=True
            user = self.env.uid
            if self.env.user.has_group('sales_team.group_sale_manager'):
                rec.manager_approve = result
            else:
                rec.manager_approve = False

    def action_confirm(self):

        if self.partner_id and \
                self.partner_id.amount_credit_limit != 0 and not self._context.get('skip_credit_check'):
            amount_due =self.partner_id.credit
            message = "Your credit limit is  %s Ks.Currently, your payable amount is %s Ks" % (str(self.partner_id.amount_credit_limit), amount_due)
            if amount_due > self.partner_id.amount_credit_limit and not self.credit_approve:
                return {
                    'name': _('Warning'),
                    'type': 'ir.actions.act_window',
                    'view_mode': 'form',
                    'res_model': 'warning.warning',
                    'target': 'new',
                    'context': {
                        'default_name': message,'default_manager_approve':self.manager_approve
                    },
                }
        return super(SaleOrder, self).action_confirm()