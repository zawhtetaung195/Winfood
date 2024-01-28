from odoo import models, fields, api
from datetime import date,timedelta,datetime
import logging
_logger = logging.getLogger(__name__)
from odoo.exceptions import ValidationError
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

class AccountTransfer(models.Model):
	_name = 'account.transfer'
	_inherit = ['mail.thread', 'mail.activity.mixin']
	_order = "transfer_date desc, name desc"

	def employee_get(self):        
		emp_id = self.env.context.get('default_requested_by_id', False)
		if emp_id:
			return emp_id
		ids = self.env['hr.employee'].search([('user_id', '=', self.env.uid)])
		if ids:
			return ids[0]
		return False

	name = fields.Char('Reference',states={'draft':[('readonly',False)], 'confirm':[('readonly',False)]},tracking=True)
	employee_name = fields.Many2one('hr.employee', 'Employee', default=employee_get, domain="[('active','=',True)]", required=True,tracking=True)
	from_account_id = fields.Many2one('account.account',string='From Account',required=True,tracking=True)
	to_account_id = fields.Many2one('account.account',string='To Account',required=True,tracking=True)
	transfer_date = fields.Date('Transfer Date', default=fields.date.today())
	paid_ref = fields.Char('Paid Ref', states={'paid':[('readonly', True)], 'closed':[('readonly', True)]})
	finance_approved_id = fields.Many2one('hr.employee',string='Finance Approved', domain="[('finance','=',True)]", required=True)
	is_approve_finance = fields.Boolean('Is Approve Finance ?',compute='get_approve',default=False)
	state = fields.Selection([
		('draft', 'Draft'),
		('confirm', 'Confirm'),
		('finance_approve','Finance Approved'),
		('paid','Paid'),
		('closed', 'Close'),
		('cancel','Cancel')
		],
		'Status',default="draft",tracking=True)
	amount = fields.Float('Amount',tracking=True)
	fees = fields.Float('Transfer Fees')
	state_type = fields.Many2one('account.journal', string='Journal')
	currency_id = fields.Many2one('res.currency', 'Currency', default=119,required=True, readonly=True)
	analytic_id = fields.Many2one('account.analytic.account','Analytic Account')
	account_move_id = fields.Many2one('account.move', string='Transfer Journal Entry', copy=False, track_visibility="onchange")
	company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id, required=True)
	move_line_ids = fields.One2many('account.move.line','acc_transfer_id',string='Account Move Line',stored=True)
	product_id = fields.Many2many('product.product', 'transfer_product_rel', 'transfer_id', 'product_id',string='Product')
	line_ids = fields.One2many('account.transfer.line', 'transfer_id', 'Account Transfer Lines')

	@api.model
	def _needaction_domain_get(self):
		return [('needaction', '=', True)]
		
	def get_sequence(self):
	  return self.env['ir.sequence'].next_by_code('account.transfer')

	def get_approve(self):
		for approve in self:
			finance = False
			to_approve_id = self.env.uid
			if to_approve_id == approve.finance_approved_id.user_id.id:
				finance = True
			approve.is_approve_finance = finance

	@api.onchange('line_ids')
	def compute_amount(self):
		if self.line_ids:
			total = 0.0
			print ('why no woking ----------------------------------------------->><<>><<>><<>>')
			for line in self.line_ids:
				total += line.amount
			self.amount = total

	def reset_to_draft(self):
		self.write({'state': 'draft'})

	def confirm(self):
		mail_ids = self.env['mail.activity']
		model_ids = self.env['ir.model'].search([('model','=','account.transfer')])
		ids = self.finance_approved_id.user_id
		date = self.transfer_date
		name = self.name
		dd = self.ids
		cc = ''
		for d in dd:
			cc += str(d)
		cc = int(cc)
		# print('........................................... id ',str(dd),' and cc ',cc)
		value = {
				'activity_type_id': 4,
				'date_deadline': date,
				'user_id': ids.id,
				'res_model_id': model_ids.id,
				'res_name': name,
				'res_id': cc,
		}
		mail_ids.create(value)
		# print('............... mail.activity created',mail_ids)
		self.write({'state': 'confirm'})

	def finance_approve(self):
		mail_ids = self.env['mail.activity']
		dd = self.ids
		cc = ''
		for d in dd:
			cc += str(d)
		cc = int(cc)
		mail_s = mail_ids.search([('res_model','=','account.transfer'),('res_id','=',cc)])
		# print('>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<< +++++++++++++++  ',mail_s)
		mail_s.unlink()
		self.write({'state': 'finance_approve'})

	def closed(self):
		self.write({'state': 'closed'})

	def cancel(self):
		self.write({'state': 'cancel'})

	def transfer_paid(self):
		for expense in self:
			journal = expense.state_type
			expense.transfer_date = date.today()
			if not journal:
				raise ValidationError('Define Journal')
			#create the move that will contain the accounting entries
			acc_date = date.today()
			move = self.env['account.move'].create({
				'journal_id': journal.id,
				'company_id': self.env.user.company_id.id,
				'date': acc_date,
				'ref': expense.name,
				'employee_id': self.employee_name.id,
				# force the name to the default value, to avoid an eventual 'default_name' in the context
				# to set it to '' which cause no number to be given to the account.move when posted.
				'name': '/',
			})
			company_currency = expense.company_id.currency_id
			diff_currency_p = expense.currency_id != company_currency
			#one account.move.line per expense (+taxes..)
			move_lines = expense._move_line_get()

			#create one more move line, a counterline for the total on payable account
			payment_id = False
			total, total_currency, move_lines = expense._compute_expense_totals(company_currency, move_lines, acc_date)
			emp_account = expense.from_account_id.id
			if not emp_account:
				raise ValidationError('Define From Account')

			aml_name = self.employee_name.name + ': ' + self.name.split('\n')[0][:64]
			move_lines.append({
					'type': 'dest',
					'name': aml_name,
					'analytic_account_id':expense.analytic_id.id,
					'price': total,
					'account_id': emp_account,
					'date_maturity': acc_date,
					'amount_currency': expense.amount*-1,
					'currency_id': False,
					'payment_id': payment_id,
					})

			#convert eml into an osv-valid format
			lines = list(map(lambda x: (0, 0, expense._prepare_move_line(x)), move_lines))
			move.with_context(dont_create_taxes=True).write({'line_ids': lines})
			move.post()
		return self.write({'account_move_id': move.id,'state': 'paid'})

	#expense prepaid
	# @api.multi
	def _prepare_move_line_value(self):
		self.ensure_one()
		aml_name = self.employee_name.name + ': ' + self.name.split('\n')[0][:64]
		if not self.to_account_id:
			raise ValidationError('Define Advance Account')
		move_line = {
			'type': 'src',
			'name': aml_name,
			'analytic_account_id':self.analytic_id.id,
			'price_unit': self.amount,
			'quantity': 1,
			'price': self.amount,
			'account_id': self.to_account_id.id,
		}
		return move_line

	

	# @api.multi
	def _compute_expense_totals(self, company_currency, account_move_lines, move_date):
		#print "----------------cumpute expense total--------------------"
		self.ensure_one()
		total = 0.0
		total_currency = 0.0
		for line in account_move_lines:
			#print "line loop"
			line['currency_id'] = False
			line['amount_currency'] = False
			if self.currency_id != company_currency:
				line['currency_id'] = self.currency_id.id
				line['amount_currency'] = line['price']
				#line['price'] = self.currency_id.compute(line['price'], company_currency)
				line['price'] = line['price']
			total -= line['price']
			#print line['price'], line['amount_currency']
			total_currency -= line['amount_currency'] or line['price']
			#raise ValidationError('Emergenncy Stop')
		return total, total_currency, account_move_lines

	# @api.multi
	def _move_line_get(self):
		account_move = []
		for expense in self:
			move_line = expense._prepare_move_line_value()
			account_move.append(move_line)
		return account_move


	# @api.multi
	def unlink(self):
		for rec in self.browse(self.ids):
			if rec.state != 'draft':
				raise ValidationError ('You can only delete draft prepaid expense!')
			for rec_line in rec.line_ids:
				rec_line.unlink()
		return super(Expense_Prepaid, self).unlink()

	

	def _prepare_move_line(self, line):
		print('woking here ---------------------------->><<>>><<>>>',line['price'])
		return {
			'date_maturity': line.get('date_maturity'),
			'acc_transfer_id': self.id,
			#'partner_id': partner_id,
			'name': line['name'][:64],
			'debit': line['price'] > 0 and line['price'],
			'credit': line['price'] < 0 and - line['price'],
			'account_id': line['account_id'],
			'analytic_line_ids': line.get('analytic_line_ids'),
			'amount_currency': line['price'] > 0 and abs(line.get('amount_currency')) or - abs(line.get('amount_currency')),
			# 'exchange_rate':self.currency_rate,
			'currency_id': self.currency_id.id,
			# 'tax_line_id': line.get('tax_line_id'),
			# 'tax_ids': line.get('tax_ids'),
			'quantity': line.get('quantity', 1.00),
			'product_id': line.get('product_id'),
			# 'product_uom_id': line.get('uom_id'),
			'analytic_account_id': line.get('analytic_account_id'),
			'payment_id': line.get('payment_id'),
		}
		

	def _get_currency(self, cr, uid, context=None):
		user = self.pool.get('res.users').browse(cr, uid, [uid], context=context)[0]
		return user.company_id.currency_id.id

	#@api.one
	# def _get_can_reset(self):
	#     result = False
	#     is_financial_manager = False
	#     user = self.env['res.users'].browse()
	#     group_financial_manager_id = self.env['ir.model.data'].get_object_reference('account', 'group_account_manager')[1]
	#     if group_financial_manager_id in [g.id for g in user.groups_id]:
	#         is_financial_manager = True

	#     for expense in self.browse(self.id):
	#         if expense.state in ['confirm','cancel']:
	#             if is_financial_manager:
	#                 result = False
	#             elif expense.employee_name and expense.employee_name.user_id and expense.employee_name.user_id.id == self.env.uid:
	#                 result = True
	#     self.can_reset = result

	@api.model
	def create(self, data):
		data['name'] = self.get_sequence()
		record_id = super(AccountTransfer, self).create(data)
		return record_id

class Account_Transfer_Line(models.Model):
	_name = 'account.transfer.line'    

	transfer_id = fields.Many2one('account.transfer', 'Title', ondelete='cascade', select=True)    
	product_id = fields.Many2one('product.product', 'Product', domain="[('can_be_expensed','=',True)]")
	sequence = fields.Integer('Sequence', select=True, help="Gives the sequence order when displaying a list of expense lines.")
	date_value = fields.Date('Date',required=True,store=True)
	analytic_account = fields.Many2one('account.analytic.account','Analytic account',related="transfer_id.analytic_id")
	account_ids = fields.Many2one('account.account', string='Account Name',store=True)
	account_code = fields.Char(string='Account Code',related='account_ids.code',store=True)
	amount = fields.Float(string='Total Amount',store=True)
	line_no = fields.Integer(compute='_get_line_numbers', string='Sr')
	ref = fields.Char('Description', required=True) 

	@api.model
	@api.onchange('product_id')
	def onchange_product_id(self):
		if self.product_id:
			product = self.env['product.product'].browse(self.product_id)
			product=product.id
			amount_unit = product.standard_price
			self.uom_id = product.uom_id.id
			self.date_value = self.transfer_id.invoice_date
			self.account_ids = self.product_id.property_account_expense_id
			self.analytic_account = self.transfer_id.analytic_id
			self.ref = self.transfer_id.name_reference

	# @api.multi
	def _get_line_numbers(self):
		for expense in self.mapped('transfer_id'):
			line_no = 1
			for line in expense.line_ids:
				line.line_no = line_no
				line_no += 1

	@api.model
	def default_get(self, fields_list):
		res = super(Expense_Prepaid_Line, self).default_get(fields_list)
		res.update({'line_no': len(self._context.get('line_ids', [])) + 1}) 
		return res


	@api.model
	def create(self,data):
		if data:
			#print data,"Data_______"
			transfer_id = super(Expense_Prepaid_Line, self).create(data)
		return transfer_id
	
	# @api.one
	def write(self,vals):
		flag = super(Expense_Prepaid_Line, self).write(vals)

		return flag