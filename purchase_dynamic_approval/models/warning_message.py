from odoo import _, models, fields

class RaiseWarning(models.TransientModel):
    _name = "approval.warning.message"
    _description = "Approval Warnning Message"

    name = fields.Char('Message')