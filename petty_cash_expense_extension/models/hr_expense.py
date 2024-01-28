from odoo import models, fields, api
from datetime import date,timedelta,datetime
import logging
_logger = logging.getLogger(__name__)
from odoo.exceptions import UserError, ValidationError
import odoo.addons.decimal_precision as dp
import time
from odoo.tools.translate import _
import calendar
from dateutil.relativedelta import relativedelta
from requests.auth import HTTPBasicAuth
import hashlib
import json
import requests
import locale
from odoo.tools import email_split, float_is_zero

class HrExpense(models.Model):
	_inherit = 'hr.expense'

	payment_mode = fields.Selection([
		("own_account", "Employee (to reimburse)"),
		("company_account", "Company"),
		("advance","From Cash Advance")
	], default='own_account', states={'done': [('readonly', True)], 'approved': [('readonly', True)], 'reported': [('readonly', True)]}, string="Paid By")
	approved_by_id = fields.Many2one('hr.employee',string='Approved By', required=True)

	def _create_sheet_from_expenses(self):
		if any(expense.state != 'draft' or expense.sheet_id for expense in self):
			raise UserError(_("You cannot report twice the same line!"))
		if len(self.mapped('employee_id')) != 1:
			raise UserError(_("You cannot report expenses for different employees in the same report."))
		if any(not expense.product_id for expense in self):
			raise UserError(_("You can not create report without product."))

		todo = self.filtered(lambda x: x.payment_mode=='own_account') or self.filtered(lambda x: x.payment_mode=='company_account') or self.filtered(lambda x: x.payment_mode=='advance')
		sheet = self.env['hr.expense.sheet'].create({
			'company_id': self.company_id.id,
			'employee_id': self[0].employee_id.id,
			'name': todo[0].name if len(todo) == 1 else '',
			'approved_by_id': self.approved_by_id.id,
			'expense_line_ids': [(6, 0, todo.ids)]
		})
		sheet._onchange_employee_id()
		return sheet

	def _get_expense_account_destination(self):
		self.ensure_one()
		account_dest = self.env['account.account']
		if self.payment_mode == 'company_account':
			if not self.sheet_id.bank_journal_id.default_credit_account_id:
				raise UserError(_("No credit account found for the %s journal, please configure one.") % (self.sheet_id.bank_journal_id.name))
			account_dest = self.sheet_id.bank_journal_id.default_credit_account_id.id
		elif self.payment_mode == 'advance':
			if not self.sheet_id.bank_journal_id.default_credit_account_id:
				raise UserError(_("No credit account found for the %s journal, please configure one.") % (self.sheet_id.bank_journal_id.name))
			account_dest = self.sheet_id.bank_journal_id.default_credit_account_id.id
		else:
			if not self.employee_id.sudo().address_home_id:
				raise UserError(_("No Home Address found for the employee %s, please configure one.") % (self.employee_id.name))
			partner = self.employee_id.sudo().address_home_id.with_context(force_company=self.company_id.id)
			account_dest = partner.property_account_payable_id.id or partner.parent_id.property_account_payable_id.id
		return account_dest

	def action_move_create(self):
		'''
		main function that is called when trying to create the accounting entries related to an expense
		'''
		move_group_by_sheet = self._get_account_move_by_sheet()

		move_line_values_by_expense = self._get_account_move_line_values()

		move_to_keep_draft = self.env['account.move']

		company_payments = self.env['account.payment']

		for expense in self:
			company_currency = expense.company_id.currency_id
			different_currency = expense.currency_id != company_currency

			# get the account move of the related sheet
			move = move_group_by_sheet[expense.sheet_id.id]

			# get move line values
			move_line_values = move_line_values_by_expense.get(expense.id)
			move_line_dst = move_line_values[-1]
			total_amount = move_line_dst['debit'] or -move_line_dst['credit']
			total_amount_currency = move_line_dst['amount_currency']

			# create one more move line, a counterline for the total on payable account
			if expense.payment_mode == 'company_account':
				if not expense.sheet_id.bank_journal_id.default_credit_account_id:
					raise UserError(_("No credit account found for the %s journal, please configure one.") % (expense.sheet_id.bank_journal_id.name))
				journal = expense.sheet_id.bank_journal_id
				# create payment
				payment_methods = journal.outbound_payment_method_ids if total_amount < 0 else journal.inbound_payment_method_ids
				journal_currency = journal.currency_id or journal.company_id.currency_id
				payment = self.env['account.payment'].create({
					'payment_method_id': payment_methods and payment_methods[0].id or False,
					'payment_type': 'outbound' if total_amount < 0 else 'inbound',
					'partner_id': expense.employee_id.address_home_id.commercial_partner_id.id,
					'partner_type': 'supplier',
					'journal_id': journal.id,
					'payment_date': expense.date,
					'state': 'draft',
					'currency_id': expense.currency_id.id if different_currency else journal_currency.id,
					'amount': abs(total_amount_currency) if different_currency else abs(total_amount),
					'name': expense.name,
				})
				move_line_dst['payment_id'] = payment.id

			if expense.payment_mode == 'advance':
				if not expense.sheet_id.bank_journal_id.default_credit_account_id:
					raise UserError(_("No credit account found for the %s journal, please configure one.") % (expense.sheet_id.bank_journal_id.name))
				journal = expense.sheet_id.bank_journal_id
				# create payment
				payment_methods = journal.outbound_payment_method_ids if total_amount < 0 else journal.inbound_payment_method_ids
				journal_currency = journal.currency_id or journal.company_id.currency_id
				advance_vlaue = self.env['account.payment'].create({
					'payment_method_id': payment_methods and payment_methods[0].id or False,
					'payment_type': 'outbound' if total_amount < 0 else 'inbound',
					'partner_id': expense.employee_id.address_home_id.commercial_partner_id.id,
					'partner_type': 'supplier',
					'journal_id': journal.id,
					'payment_date': expense.date,
					'state': 'draft',
					'currency_id': expense.currency_id.id if different_currency else journal_currency.id,
					'amount': abs(total_amount_currency) if different_currency else abs(total_amount),
					'name': expense.name,
				})
				move_line_dst['payment_id'] = advance_vlaue.id

			# link move lines to move, and move to expense sheet
			move.write({'line_ids': [(0, 0, line) for line in move_line_values]})
			expense.sheet_id.write({'account_move_id': move.id})

			if expense.payment_mode == 'company_account':
				company_payments |= payment
				if journal.post_at == 'bank_rec':
					move_to_keep_draft |= move

				expense.sheet_id.paid_expense_sheets()

			elif expense.payment_mode == 'advance':
				company_payments |= advance_vlaue
				if journal.post_at == 'bank_rec':
					move_to_keep_draft |= move

				expense.sheet_id.paid_expense_sheets()

		company_payments.filtered(lambda x: x.journal_id.post_at == 'pay_val').write({'state':'reconciled'})
		company_payments.filtered(lambda x: x.journal_id.post_at == 'bank_rec').write({'state':'posted'})

		# post the moves
		for move in move_group_by_sheet.values():
			if move in move_to_keep_draft:
				continue
			move.post()

		return move_group_by_sheet

class HrExpenseSheet(models.Model):
	_inherit = 'hr.expense.sheet'

	approved_by_id = fields.Many2one('hr.employee',string='Approved By')
	is_approve = fields.Boolean('Is Approve ?',compute='get_approve',default=False)

	def get_approve(self):
		for approve in self:
			reason = False
			to_approve_id = self.env.uid
			# to_approve_id= self.env['hr.employee'].search([('user_id', '=', self.env.uid)]).id
			if to_approve_id == approve.approved_by_id.user_id.id:
				reason = True
			approve.is_approve = reason

	def action_sheet_move_create(self):
		if any(sheet.state != 'approve' for sheet in self):
			raise UserError(_("You can only generate accounting entry for approved expense(s)."))

		if any(not sheet.journal_id for sheet in self):
			raise UserError(_("Expenses must have an expense journal specified to generate accounting entries."))

		expense_line_ids = self.mapped('expense_line_ids')\
			.filtered(lambda r: not float_is_zero(r.total_amount, precision_rounding=(r.currency_id or self.env.company.currency_id).rounding))
		res = expense_line_ids.action_move_create()

		if not self.accounting_date:
			self.accounting_date = self.account_move_id.date

		if self.payment_mode == 'own_account' and expense_line_ids:
			self.write({'state': 'post'})
		elif self.payment_mode == 'advance' and expense_line_ids:
			self.write({'state': 'post'})
		else:
			self.write({'state': 'done'})
		self.activity_update()
		return res

	def approve_expense_sheets(self):
		# if not self.user_has_groups('hr_expense.group_hr_expense_team_approver'):
		#     raise UserError(_("Only Managers and HR Officers can approve expenses"))
		# elif not self.user_has_groups('hr_expense.group_hr_expense_manager'):
		#     current_managers = self.employee_id.expense_manager_id | self.employee_id.parent_id.user_id | self.employee_id.department_id.manager_id.user_id

		#     if self.employee_id.user_id == self.env.user:
		#         raise UserError(_("You cannot approve your own expenses"))

		#     if not self.env.user in current_managers and not self.user_has_groups('hr_expense.group_hr_expense_user') and self.employee_id.expense_manager_id != self.env.user:
		#         raise UserError(_("You can only approve your department expenses"))

		# responsible_id = self.user_id.id or self.env.user.id
		self.write({'state': 'approve'})
		# self.activity_update()

	