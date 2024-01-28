# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.osv import expression
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.tools.float_utils import float_compare
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.misc import formatLang, get_lang

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'
    _description = 'Purchase Order'

    check = fields.Boolean('Invisible',compute='get_invisible',defualt=False)

    @api.model
    def create(self, vals):
        res = super(PurchaseOrder, self).create(vals)
        for rec in res.order_line:
            if not rec.account_analytic_id:
                raise UserError(_("Can't define Analytic Account"))
        return res

    def button_unlock(self):
        if not self.order_line.filtered(lambda r: r.product_qty != r.qty_received):
            raise ValidationError('Need to return good receipts before unlock.')
        self.write({'state': 'purchase'})

    def button_done(self):
        lines = self.order_line.filtered(lambda r: r.product_qty != r.qty_received)
        if lines:
            for line in lines:
                line.filtered(lambda l: l.order_id.state == 'purchase')._create_or_update_picking()
        self.write({'state': 'done'})

    def get_invisible(self):
        for rec in self:
            lines = rec.order_line.filtered(lambda r: r.product_qty != r.qty_invoiced)
            if not lines:
                rec.check = True
            else:
                rec.check = False