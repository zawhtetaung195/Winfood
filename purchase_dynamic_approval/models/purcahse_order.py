from email.policy import default
from odoo import _, models, fields, api

class PurchaseOrder(models.Model):

    _inherit = 'purchase.order'
    state = fields.Selection(selection_add=[('waiting_ack', 'Waiting Acknowledge'),('waiting_approval', 'Waiting Approval'),('to approve',)])
    approver_ids = fields.Many2many('res.users', 'po_approver_rel', string='Approvers')
    acknowledger_ids = fields.Many2many('res.users', 'po_acknowledger_rel', string='Acknowledgers')
    
    done_ids = fields.Many2many('res.users', 'po_done_id_rel', string="Users", help='The users who already approved', tracking=True)

    def set_approval_process(self):
        defc = self.env.ref('base.main_company').currency_id #DEFAULT CURRENCY 
        for line in self.order_line:
            if line.account_analytic_id:
                approval = self.env['purchase.order.approval'].search([('analytic_account_id', '=', line.account_analytic_id.id)])
                if defc == self.currency_id:
                    self.write({'approver_ids': approval.get_approvers(self.amount_total)})
                else:
                    self.write({'approver_ids': approval.get_approvers(self.amount_total, self.currency_id)})
                self.write({'acknowledger_ids': approval.get_acknowledgers()})
                self.set_to_waiting_ack()

    def remove_approval_process(self):
        self.write({'approver_ids': False,'acknowledger_ids': False, 'done_ids': False, 'state': 'draft'})
    
    def acknowledger_approve(self):
        user = self.env.user
        for line in self.order_line:
            if line.account_analytic_id:
                rule = self.env['purchase.order.approval'].search([('analytic_account_id','=',line.account_analytic_id.id)])
                acknowledgers = rule.get_acknowledgers()
                warning = {
                    'name': _('Warning'),
                    'type': 'ir.actions.act_window',
                    'view_mode': 'form',
                    'res_model': 'approval.warning.message',
                    'target': 'new',
                }
                if rule:
                    if user.id in acknowledgers:
                        flag = True
                        ack_list = acknowledgers[0:acknowledgers.index(user.id)]
                        for i in ack_list:
                            if not i in self.done_ids.ids:
                                flag = False
                        if flag:
                            self.write({'acknowledger_ids': [(3, user.id)], 'done_ids': [(4, user.id)]})
                            if not self.acknowledger_ids:
                                self.write({'state': 'waiting_approval'})
                        else:
                            warning.update({'context': {'default_name': "This is not your place!!!"}})
                            return warning
                    else:
                        warning.update({'context': {'default_name': "You are not an acknowledge person!"}})
                        return warning                      
                else:
                    break

    def set_to_draft(self):
        self.write({'state':'draft'})

    def set_to_waiting_ack(self):
        self.write({'state':'waiting_ack'})

    def approver_approve(self):
        user = self.env.user
        for line in self.order_line:
            if line.account_analytic_id:
                rule = self.env['purchase.order.approval'].search([('analytic_account_id','=',line.account_analytic_id.id)])
                defc = self.env.ref('base.main_company').currency_id #DEFAULT CURRENCY
                exchanged = False 
                if defc == self.currency_id:
                    approvers = rule.get_approvers(self.amount_total)
                else:
                    approvers = rule.get_approvers(self.amount_total, self.currency_id)
                    exchanged = True
                warning = {
                    'name': _('Warning'),
                    'type': 'ir.actions.act_window',
                    'view_mode': 'form',
                    'res_model': 'approval.warning.message',
                    'target': 'new',
                }
                if self.acknowledger_ids.ids != []:
                    warning.update({'context': {'default_name': "Acknowledger First!"}})
                    return warning
                if rule:
                    if user.id in approvers:
                        flag = True
                        app_list = approvers[0:approvers.index(user.id)]
                        for i in app_list:
                            if not i in self.done_ids.ids:
                                flag = False                        
                        if flag:
                            check = rule.is_approvers(self.amount_total, self.currency_id) if exchanged else rule.is_approvers(self.amount_total)
                            self.write({'approver_ids': [(3, user.id)], 'done_ids': [(4, user.id)]})
                            if not self.acknowledger_ids and not self.approver_ids:
                                self.button_confirm()
                        else:
                            warning.update({'context': {'default_name': "This is not your place!!!"}})
                            return warning
                    else:
                        warning.update({'context': {'default_name': "You are not approver!"}})
                        return warning
                break

    @api.model
    def create(self, values):
        result = super(PurchaseOrder, self).create(values)
        if result:
            result.set_approval_process()
            result.set_to_waiting_ack()

        return result

    def button_confirm(self):
        for order in self:
            if order.state not in ['draft', 'sent', 'waiting_ack', 'waiting_approval']:
                continue
            order._add_supplier_to_product()
            # Deal with double validation process
            if order._approval_allowed():
                order.button_approve()
            else:
                order.write({'state': 'to approve'})
            if order.partner_id not in order.message_partner_ids:
                order.message_subscribe([order.partner_id.id])
        return True

    ami_responsible_ack = fields.Boolean(string='Responsible', compute='_check_ami_responsible_ack' )
    
    def _check_ami_responsible_ack(self):
        uid = self.env.user.id
        self.ami_responsible_ack = True if uid in self.acknowledger_ids.ids and uid not in self.done_ids.ids else False

    ami_responsible_approve = fields.Boolean(string='Responsible', compute='_check_ami_responsible_approve' )
    def _check_ami_responsible_approve(self):
        uid = self.env.user.id
        self.ami_responsible_approve = True if uid in self.approver_ids.ids and uid not in self.done_ids.ids else False
class PurchaseApproverLine(models.Model):

    _name = 'purchase.approval.line'
    _description = 'Purchase Approval Line'
    _order = 'maximum_amount'

    name = fields.Char(string='Description')
    approver_id = fields.Many2one('res.users', string='Approver')
    minimum_amount = fields.Float(string='Minimum Amount')
    maximum_amount = fields.Float(string='maximum Amount')
    approval_id = fields.Many2one('purchase.order.approval', string="Approve ID")

class PurchaseAcknowledgeLine(models.Model):

    _name = 'purchase.acknowledge.line'
    _description = 'Purchase Acknowledge Line'
    _order = 'sequence_no'

    name = fields.Char(string='Level')
    sequence_no = fields.Integer('Sequence')
    acknowledger_id = fields.Many2one('res.users', string='Acknowledger')
    approval_id = fields.Many2one('purchase.order.approval', string="Approve ID")

class PurchaseOrderApproval(models.Model):

    _name = 'purchase.order.approval'
    _description = 'Purchase Order Approval'

    _rec_name = 'name'
    _order = 'id ASC'

    name = fields.Char(string='Name',required=True,default=lambda self: _('New'),copy=False)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    company_id = fields.Many2one('res.company', string='Company')
    department_id = fields.Many2one('hr.department', string='Department')
    approval_line_ids = fields.One2many('purchase.approval.line', 'approval_id', string='Approve Users')
    acknowledge_line_ids = fields.One2many('purchase.acknowledge.line', 'approval_id', string='Acknowledge Users')

    @api.onchange('department_id')
    def onchange_department_id(self):
        if self.department_id:
            self.analytic_account_id = self.department_id.analytic_account_id.id
            self.company_id = self.env.user.company_id.id

    def get_approvers(self, amount=None, currency_id=None):
        if currency_id:
            amount = amount * currency_id.inverse_rate
        approver_ids = []
        for line in self.approval_line_ids:
            if amount != None and amount >= line.minimum_amount:
                approver_ids.append(line.approver_id.id)
        return approver_ids

    def get_acknowledgers(self):
        acknowledger_ids = []
        for line in self.acknowledge_line_ids:
            acknowledger_ids.append(line.acknowledger_id.id)
        return acknowledger_ids

    def is_approvers(self,po_amount=None, currency_id=None):
        if self.env.user.id in self.get_approvers():
            if currency_id:
                po_amount = po_amount * currency_id.inverse_rate
            check = self.env['purchase.approval.line'].search([('id', 'in', self.approval_line_ids.ids),('approver_id', '=', self.env.user.id), ('maximum_amount', '<=', po_amount)])
            return check


    def is_acknowledger(self):
        return True if self.env.user.id in self.get_acknowledgers() else False

