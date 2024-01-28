from odoo import fields,models,api,_
# from odoo.tools.func import default

class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    check_options = fields.Selection([
        ('oversea', 'Oversea PO'),
        ('local', 'Local PO')], string="PO Type",default="local" )

    approve_state = fields.Selection([('draft','Draft'),('approve', 'Approve')], string="State", default='draft',tracking=True )

    def action_approve(self):
        for rec in self:
            rec.approve_state = 'approve'

    def get_current_user(self):
        result = False
        user_id = self.env.uid
        user = self.env['res.users'].browse(user_id)
        is_purchase_user_id = False
        group_purchase_user_id = self.env['ir.model.data'].get_object_reference('purchase', 'group_purchase_user')[1]

        group_manager_id = self.env['ir.model.data'].get_object_reference('purchase', 'group_purchase_manager')[1]

        if group_purchase_user_id and not group_manager_id in [g.id for g in user.groups_id]:
            is_purchase_user_id = True

        if is_purchase_user_id:
            result=True
        self.get_user = result

    get_user =fields.Boolean(compute='get_current_user',string='Get User')
