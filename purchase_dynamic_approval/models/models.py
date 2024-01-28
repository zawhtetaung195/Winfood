# -*- coding: utf-8 -*-

from odoo import _, models, fields, api

class HRDepartment(models.Model):

    _inherit = 'hr.department'
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')

