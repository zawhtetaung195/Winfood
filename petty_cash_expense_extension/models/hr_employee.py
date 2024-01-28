from odoo import models, fields, api

class HrEmployee(models.Model):
	_inherit = 'hr.employee'

	gm_id = fields.Many2one('hr.employee',string='GM')
	is_gm = fields.Boolean('Is GM ?',default=False)
	finance = fields.Boolean('Finance')

	@api.onchange('gm_id')
	def onchange_gm_id(self):
		if self.gm_id:
			self.is_gm = False