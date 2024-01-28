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


class AccountMove(models.Model):
	_inherit = "account.move"

	employee_id = fields.Many2one('hr.employee','Employees',ondelete="set null", domain="[('active','=',True)]")

class AccountMoveLine(models.Model):
	_inherit = "account.move.line"

	employee_id = fields.Many2one('hr.employee','Employees',ondelete='restrict', domain="[('active','=',True)]")
	general_exp_id = fields.Many2one('expense.prepaid','General Expenses')
	exp_exp_id = fields.Many2one('expense.prepaid','Advance Expenses')
	adj_exp_id = fields.Many2one('expense.prepaid','Adjustment Expenses')
	expense_id = fields.Many2one('hr.expense','Expenses')
	acc_transfer_id = fields.Many2one('account.transfer','Account Transfer Journal')
	adv_claim_id = fields.Many2one('advance.claim','Advance Claim')


class AccountAccount(models.Model):
	_inherit = "account.account"
	_description = "Account"
	_order = "code"

	# @api.multi
	@api.depends('name', 'code')
	def name_get(self):
		result = []
		for account in self:
			name = account.name
			result.append((account.id, name))
		return result


class hr_general_expense(models.Model):
	_name = "hr.expense"
	_inherit = ['hr.expense','mail.thread', 'mail.activity.mixin']
	_description = "Advance Clearing"
	_order = "date desc"

	#by yma 20201026
	# batch_id= fields.Many2one('education.batch','Batch')
	# programme = fields.Many2one('product.product','Programme', domain=([('type','=','service'),('sale_ok','=',True)]))
	# module_id = fields.Many2many('education.module',string='Modules')
	# check = fields.Boolean('Check Module',default=False)
	
	# @api.onchange('programme')
	# def _onchange_module(self):
	# 	module = []
	# 	check=False
	# 	if self.programme:
	# 		module_ids = self.env['education.module'].search([('certification_id','=',self.programme.id)])
	# 		# print ('this module is is issi',module_ids,self.programme.id)
	# 		if module_ids:
	# 			for record in module_ids:
	# 				module.append(record._origin.id)
	# 			#print ("Hello programme>>>>>>> True",module,'----------------',module_ids)
	# 			self.module_id = module
	# 			self.check=True
	# 			#print ("hello module name True--------------------------------------",self.check)
	# 		else:
	# 			for record in module_ids:
	# 				module.append(record._origin.id)
	# 			#print ("Hello programme>>>>>>>False ",module,'----------------',module_ids)
	# 			self.module_id = module
	# 			self.check=False
	# 			#print ("hello module name False--------------------------------------",self.check)

	
	def get_sequence(self):
		sequence = self.env['ir.sequence'].next_by_code('hr.expense')
		year = datetime.now().year
		month = datetime.now().month
		if month < 10:
			month = '0'+str(month)
		seq_no = str(self.env.user.company_id.code)+'-'+'AC-'+str(year)+'-'+str(month)+sequence
		return seq_no


	# @api.multi
	# @api.onchange('line_ids')
	def _amount(self):
		# #print "000000amount000000000"
		total = 0.0
		if self.line_ids:
			
			for line in self.line_ids:
				total += line.amount
		return total

	@api.model
	def get_default_date(self):
		##print "--------------------GET DEFAULT DATE------------------------"
		my_date = fields.Datetime.context_timestamp(self, timestamp=datetime.now())
		_logger.critical("default Date>> '" + str(my_date))
		return my_date

	product_id = fields.Many2many('product.product', 'hrexpense_product_rel', 'expense_id', 'product_id',string='Product', domain="[('can_be_expensed','=',False)]")
	# product_uom_id = fields.Many2one('product.uom', string='Unit of Measure', required=False, readonly=True, states={'draft': [('readonly', False)], 'refused': [('readonly', False)]}, default=lambda self: self.env['product.uom'].search([], limit=1, order='id'))
	unit_amount = fields.Float(string='Unit Price', readonly=False, required=False, states={'draft': [('readonly', False)], 'refused': [('readonly', False)]}, digits=dp.get_precision('Product Price'))

	name = fields.Char(string='Invoice No',store=True, required=False,tracking=True)
	# 'id'fields.Integer('Sheet ID', readonly=True),
	date = fields.Date(string='Date',default=get_default_date, select=True, readonly=True, states={'draft':[('readonly',False)], 'confirm':[('readonly',False)]},required=True,tracking=True)
	journal_id = fields.Many2one('account.journal', 'Force Journal', help = "The journal used when the expense is done."),
	# employee_id = fields.Many2one('hr.employee', "Employee", default='_employee_get' ,required=True, readonly=True, states={'draft':[('readonly',False)], 'confirm':[('readonly',False)]})
	employee_id = fields.Many2one('hr.employee','Employee',states={'draft':[('readonly',False)], 'confirm':[('readonly',False)]},required=True, domain="[('active','=',True)]",tracking=True)
	user_id = fields.Many2one('res.users', 'User', required=True)
	date_confirm = fields.Date('Confirmation Date', select=True, copy=False,
								help="Date of the confirmation of the sheet expense. It's filled when the button Confirm is pressed.")
	date_valid = fields.Date('Validation Date', select=True, copy=False,
							  help="Date of the acceptation of the sheet expense. It's filled when the button Accept is pressed.")
	user_valid = fields.Many2one('res.users', 'Validation By', readonly=True, copy=False,
								  states={'draft':[('readonly',False)], 'confirm':[('readonly',False)]})
	line_ids = fields.One2many('hr.expense.line', 'expense_id', 'Expense Lines')
	note = fields.Text('Note')
	paid_date = fields.Date('Paid Date', states={'done':[('required', True)], 'paid':[('readonly', True)]})
	paid_ref = fields.Char('Paid Ref', states={'done':[('required', True)], 'paid':[('readonly', True)]})
	description = fields.Char('Description', require=True)
	expense_prepaid_ids = fields.Many2one('expense.prepaid', 'Advance Expense',domain=[('state','=','paid')])
	amount = fields.Float(string='Total Amount',compute="_amount",store=True,tracking=True)
	currency_id = fields.Many2one('res.currency', 'Currency',required=True, domain=[('active','=',True)] ,states={'draft':[('readonly',False)], 'confirm':[('readonly',False)]})

	department_id = fields.Many2one('hr.department','Department', readonly=True, states={'draft':[('readonly',False)], 'confirm':[('readonly',False)]},related="employee_id.department_id",tracking=True)
	# TPS ===============
	company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id, required=True)
	# TPS ===============
	compliance_officer = fields.Boolean('Compliance Officer Approve')
	paid_datev= fields.Date('Paid Date', states={'done':[('required', True)], 'paid':[('readonly', True)]})
	paid_ref = fields.Char('Paid Ref', states={'done':[('required', True)], 'paid':[('readonly', True)]})
	analytic_id = fields.Many2one("account.analytic.account",store="True")
	state = fields.Selection([
		('draft', 'New Request'),
		('confirm', 'Submitted'),
		('manager_approve','Manager Approved'),
		('approved', 'Finance Approved'),
		('gm_approve', 'GM Approved'),
		('cancel', 'Cancelled'),
		('paid', 'Paid'),
		('refused','Refused'),
		('reported','Reported')
		],
		'Status',default="draft",tracking=True)
	can_reset = fields.Boolean(string='Reset')
	can_approve = fields.Boolean(string='Approved')
	state_type = fields.Many2one('account.journal', string='Journal')
	cash_account = fields.Many2one('account.account',string="Paid By",domain=[('user_type_id','=','Bank and Cash')])
	cash_inv = fields.Boolean(string='Cash Invisible')
	exp_move_line_ids = fields.One2many('account.move.line', 'expense_id', string='Journal Expense', store=True)
	account_move_id = fields.Many2one('account.move', string='Advance Journal Entry', copy=False, track_visibility="onchange")
	advance_amount = fields.Float(string='Advance Amount', store=True, default=0.0)
	advance_account_move_id = fields.Many2one('account.move', string='Close Journal Entry', copy=False, track_visibility="onchange")
	# main_category = fields.Many2one('hr.main.category', string='Main Category', required=True)
	# sub_category = fields.Many2one('hr.sub.category', string='Sub Category', domain="[('categ_id', '=', main_category)]", required=True)
	# 20190527 by yma
	prepaid_type = fields.Many2one('hr.prepaid.type', string='Type')
	# team_id = fields.Many2one('res.partner.coveredteam', string='Team', required=True)
	currency_rate = fields.Float(string='Currency Rate')
	approved_by_id = fields.Many2one('hr.employee',string='Approved By Manager')
	finance_approved_id = fields.Many2one('hr.employee',string='Finance Approved', domain="[('finance','=',True)]")
	is_approve = fields.Boolean('Is Approve Manager ?',compute='get_approve',default=False)
	is_approve_finance = fields.Boolean('Is Approve Finance ?',compute='get_approve',default=False)
	user_id = fields.Many2one('res.users','User', default=lambda self: self.env.user)
	is_cashier = fields.Boolean('Is Cashier',compute='get_approve', default=False)
	adjustment_amount = fields.Float(string='Adjustment Amount', store=True, default=0.0)

	def get_approve(self):
		for approve in self:
			reason = False
			finance = False
			cashier = False
			to_approve_id = self.env.uid
			user = approve.user_id
			# to_approve_id= self.env['hr.employee'].search([('user_id', '=', self.env.uid)]).id
			if to_approve_id == approve.approved_by_id.user_id.id:
				reason = True
			if to_approve_id == approve.finance_approved_id.user_id.id:
				finance = True
			if user.has_group('petty_cash_expense_extension.group_petty_cashier'):
				cashier = True
			approve.is_approve = reason
			approve.is_approve_finance = finance
			approve.is_cashier = cashier

	# @api.model
	# @api.onchange('currency_id')
	# def get_apiData(self):
	# 	locale.setlocale(locale.LC_ALL, '')
	# 	url = 'https://forex.cbm.gov.mm/api/latest'
	# 	resp = requests.get(url, verify=False)
	# 	response = json.loads(resp.text)
	# 	api_data = response['rates']
	# 	if self.currency_id:
	# 		if self.currency_id.name != 'MMK':
	# 			self.currency_rate = locale.atof(api_data[self.currency_id.name])
	# 		else:
	# 			self.currency_rate = 1.0
	# TPS Update 21/6/2019
	# ============

	# @api.multi
	# @api.onchange('employee_id')
	# def get_advance_data(self):
	#     if self.employee_id:
	#         self.analytic_id = self.employee_id.department_id.account_ids

	def print_adv_clear(self):
		par=self.ids
		if par:
			url = 'http://localhost:8080/birt/frameset?__report=idealab_advance_clear.rptdesign&order_id=' + str(self.ids[0])
		if url :
			return {
			'type' : 'ir.actions.act_url',
			'url' : url,
			'target': 'new',
				}
		else:
			raise ValidationError('Not Found')            
		return True

	

	# @api.multi
	@api.onchange('expense_prepaid_ids')
	def get_advance_data(self):
		if self.expense_prepaid_ids:
			self.employee_id = self.expense_prepaid_ids.employee_name
			#self.state_type = self.expense_prepaid_ids.state_type
			self.advance_amount = self.expense_prepaid_ids.advance_amount
			self.cash_inv = True
			# self.main_category = self.expense_prepaid_ids.main_category
			# self.sub_category = self.expense_prepaid_ids.sub_category
			temp = []
			for product in self.expense_prepaid_ids.product_id:
				temp.append(product.id)
			self.product_id = [(6,0,temp)]
			#[(6,0,self.expense_prepaid_ids.product_id)]
			# 20190527 by yma
			# self.prepaid_type = self.expense_prepaid_ids.prepaid_type
			self.company_id = self.expense_prepaid_ids.company_id
			self.currency_id = self.expense_prepaid_ids.currency_id
			# self.team_id = self.expense_prepaid_ids.team_id
			self.currency_rate = self.expense_prepaid_ids.currency_rate
		else:
			self.cash_inv = False

	   
	@api.onchange('product_id')
	def _onchange_product_id(self):
		if self.product_id:
			if not self.name:
				temp_name = ''
				for pp in self.product_id:
					temp_name += str(pp.display_name or '') + ', '
				self.name = temp_name
			#self.unit_amount = self.product_id.price_compute('standard_price')[self.product_id.id]
			#self.product_uom_id = self.product_id.uom_id
			#self.tax_ids = self.product_id.supplier_taxes_id
			# account = self.product_id.product_tmpl_id._get_product_accounts()['expense']
			# if account:
			#     self.account_id = account

	def _get_currency(self):
		user = self.env['res.users'].browse(self.env.uid)[0]
		return user.company_id.currency_id.id

	def _get_can_reset(self):
		return True

	# @api.one
	def _get_can_approve(self):
		##print '--------------------GET CAN APPROVE-------------------------'
		result = False
		##print self.env.user , self.fst_aproval.user_id
		if self.fst_aproval.user_id == self.env.user:
			##print "Correct User"
			self.can_approve = True
		else:
			self.fst_aproval

	

	@api.model
	def create(self, vals):
		vals['name'] = self.get_sequence()
		vals['user_id'] = 1
		total_amount = 0
		record_id = super(hr_general_expense, self).create(vals)
		if vals.get('expense_prepaid_ids'):
			##print "prepaid>>>>",vals['expense_prepaid_ids']
			prepaid_ids = self.env['expense.prepaid'].search([('id','=',vals['expense_prepaid_ids'])])
			##print prepaid_ids
			##print prepaid_ids.line_ids
			for line in prepaid_ids.line_ids:
				line_vals = []
				line_vals = {
					'product_id': line.product_id.id,
					'date_value': line.date_value,
					'analytic_account':line.analytic_account.id,
					'account_ids': line.account_ids.id,
					'amount': line.amount,
					'ref': line.ref,
					'expense_id': record_id.id,
				}
				self.env['hr.expense.line'].create(line_vals)
		record_id.amount = record_id._amount()      
		return record_id

	# @api.one
	def write(self,vals):
		##print "0-----writing expense"
		total = self._amount()
		##print total
		vals['amount'] = total
		record = super(hr_general_expense, self).write(vals)
		return record

	# @api.multi
	def unlink(self):
		for rec in self.browse(self.ids):
			if rec.state != 'draft':
				raise ValidationError ('You can only delete draft expenses!')
			for rec_line in rec.line_ids:
				rec_line.unlink()
		return super(hr_general_expense, self).unlink()

	def onchange_currency_id(self, cr, uid, ids, currency_id=False, company_id=False, context=None):
		res =  {'value': {'journal_id': False}}
		journal_ids = self.pool.get('account.journal').search(cr, uid, [('type','=','purchase'), ('currency','=',currency_id), ('company_id', '=', company_id)], context=context)
		if journal_ids:
			res['value']['journal_id'] = journal_ids[0]
		return res

	def onchange_employee_id(self, cr, uid, ids, employee_id, context=None):
		emp_obj = self.pool.get('hr.employee')
		department_id = False
		company_id = False
		if employee_id:
			employee = emp_obj.browse(cr, uid, employee_id, context=context)
			department_id = employee.department_id.id
			company_id = employee.company_id.id
		return {'value': {'department_id': department_id, 'company_id': company_id}}


	# @api.one
	def general_expense_confirm(self):
		mail_ids = self.env['mail.activity']
		model_ids = self.env['ir.model'].search([('model','=','hr.expense')])
		ids = self.approved_by_id.user_id
		date = self.date
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
		# Need for loop lines to input the variables 
		# for la in self.line_ids.amount:
		amount = self.line_ids.amount
		adv = self.expense_prepaid_ids.advance_amount
		err = amount - adv
		if amount > adv:
			raise ValidationError ('Exceed amount it should be add in Additional Amount.')
		self.adjustment_amount = self.line_ids.adjustment_amount
		print('------------------- adj = ',self.adjustment_amount,' , Line ID = ',self.line_ids)
		return self.write({'state': 'confirm', 'date_confirm': time.strftime('%Y-%m-%d')})


	# @api.one
	def general_expense_draft(self):
		return self.write({'state': 'draft'})

	######## Department Manager #########

	# @api.one
	def general_expense_manager_accept(self):
		mail_ids = self.env['mail.activity']
		model_ids = self.env['ir.model'].search([('model','=','hr.expense')])
		ids = self.finance_approved_id.user_id
		date = self.date
		name = self.name
		dd = self.ids
		cc = ''
		for d in dd:
			cc += str(d)
		cc = int(cc)
		# print('........................................... id ',str(dd),' and cc ',cc)
		mail_s = mail_ids.search([('res_model','=','hr.expense'),('res_id','=',cc)])
		# print('>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<< +++++++++++++++  ',mail_s)
		mail_s.unlink()
		value = {
				'activity_type_id': 4,
				'date_deadline': date,
				'user_id': ids.id,
				'res_model_id': model_ids.id,
				'res_name': name,
				'res_id': cc,
		}
		mail_ids.create(value)
		self.adjustment_amount = self.line_ids.adjustment_amount
		print('------------------- adj = ',self.adjustment_amount,' , Line ID = ',self.line_ids)
		return self.write({'state': 'manager_approve', 'date_valid': time.strftime('%Y-%m-%d'),})

	# @api.one
	# def general_expense_manager_accept_snd(self):
	# 	return self.write({'state': 'manager_accepted_snd', 'date_valid': time.strftime('%Y-%m-%d'),})
	def approve(self):
		mail_ids = self.env['mail.activity']
		# model_ids = self.env['ir.model'].search([('model','=','hr.expense')])
		# ids = self.env['hr.employee'].search([('is_gm','=',True)])
		# ids = self.finance_approved_id.user_id
		# date = self.date
		# name = self.name
		dd = self.ids
		cc = ''
		for d in dd:
			cc += str(d)
		cc = int(cc)
		# print('........................................... id ',str(dd),' and cc ',cc)
		mail_s = mail_ids.search([('res_model','=','hr.expense'),('res_id','=',cc)])
		# print('>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<< +++++++++++++++  ',mail_s)
		mail_s.unlink()
		# value = {
		# 		'activity_type_id': 4,
		# 		'date_deadline': date,
		# 		'user_id': ids.user_id.id,
		# 		'res_model_id': model_ids.id,
		# 		'res_name': name,
		# 		'res_id': cc,
		# }
		# mail_ids.create(value)
		return self.write({'state': 'approved'})

	def gm_approve(self):
		# mail_ids = self.env['mail.activity']
		# dd = self.ids
		# cc = ''
		# for d in dd:
		# 	cc += str(d)
		# cc = int(cc)
		# mail_s = mail_ids.search([('res_model','=','hr.expense'),('res_id','=',cc)])
		# # print('>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<< +++++++++++++++  ',mail_s)
		# mail_s.unlink()
		return self.write({'state': 'gm_approve'})
	# @api.one
	def cancel(self):
		return self.write({'state': 'cancel'})

	def reset_to_draft(self):
		return self.write({'state': 'draft'})


	######## Cashier #########
		
	def general_expense_paid(self):
		amount = self.amount
		adv = self.advance_amount
		# if amount < adv:
		# print('..........///////////////// general_expense_paid.......... if condition')
		move_line_idd = self.env['account.move.line'].search([('general_exp_id','=',self.expense_prepaid_ids.id)])
		move_idd = self.env['account.move'].search([('id','=',move_line_idd.move_id.id)])
		print('.................. Move id .........',move_idd.name)
		# desc = 'Adv Clearing: ',str(move_idd.name)
		desc = 'Adv Clearing: ',str(self.expense_prepaid_ids.voucher_no)
		for expense in self:
			journal = expense.state_type
			if not journal:
				raise ValidationError('Define Journal')
			acc_date = expense.date
			expense.paid_date = date.today()
			print (acc_date,'something ------------------------------->><>> and journal ',journal)
			move = self.env['account.move'].create({
				'journal_id': journal.id,
				'company_id': self.env.user.company_id.id,
				'date': acc_date,
				'ref': desc,
				'name': '/',
				'employee_id': expense.employee_id.id,
			})
			company_currency = expense.company_id.currency_id
			diff_currency_p = expense.currency_id != company_currency
			move_lines = expense._move_line_get()
			##print "------------------MOVE LINE GET-------------------------"
			##print move_lines

			payment_id = False
			total, total_currency, move_lines = expense._compute_expense_totals(company_currency, move_lines, acc_date)
			if expense.expense_prepaid_ids:
				##print "-----------ADVANCE IS EXIT--------------"
				emp_account = expense.expense_prepaid_ids.account_ids.id
				aml_name = expense.expense_prepaid_ids.name_reference + ': ' + str(expense.expense_prepaid_ids.voucher_no)
			else:
				emp_account = expense.cash_account.id
				if not emp_account:
					raise ValidationError('Define Paid By')
				#print ('................ Expense Name = ',expense.name)
				aml_name = expense.employee_id.name + ': ' + str(expense.description)
			##print "Total>>", total
			##print "account id",emp_account
			move_lines.append({
					'type': 'dest',
					'name': aml_name,
					'date':acc_date,
					'analytic_account_id':expense.analytic_id.id,
					'price': total,
					'account_id': emp_account,
					'date_maturity': acc_date,
					'amount_currency': 0,
					'currency_id': False,
					'payment_id': payment_id,
					})
			##print "=============="

			#print('----------------still working here ------------->>>')

			##print move_lines
			lines = list(map(lambda x: (0, 0, expense._prepare_move_line(x)), move_lines))
			#print lines,'----------------'
			move.with_context(dont_create_taxes=True).write({'line_ids': lines})
			move.post()
			# acc_ids = self.env['account.account'].search([('name','=','Cash')])
			# exp = self.amount
			# adv = self.advance_amount
			# acc_ids = self.env['account.account'].search([('name','=','Cash')])
			# print('.......................... exp = ',exp,' and adv = ',adv)
			# if adv > exp:
			# 	collect = exp - adv
			# 	line_value = {
			# 			'account_id': acc_ids.id,
			# 			'debit': 0,
			# 			'credit': collect,

			# 	}
			if expense.expense_prepaid_ids:
				self.close_expenses()
				self.exchange_gain_loss_expenses()
				self.expense_prepaid_ids.prepaid_expense_cashier_closed()
				self.expense_prepaid_ids.write({'advance_account_move_id':move.id})
		return self.write({'state': 'paid', 'account_move_id':move.id})
		# else:
		# 	print('........./////////////////////// general_expense_paid>>>>>>>>>>>> else condition')
		# 	self.close_expenses()
		# 	self.expense_prepaid_ids.prepaid_expense_cashier_closed()
		# 	return self.write({'state': 'paid'})

	#general expense
	# @api.multi
	def _prepare_move_line_value(self):
		#print "----------------PREPARE MOVE LINE VALUE-------------------"
		self.ensure_one()
		move_line = []
		for line in self.line_ids:
			#print line.amount
			if not line.product_id.property_account_expense_id:
				raise ValidationError(str(line.product_id.name)+ ' has no Expense Account.')
			#print line.product_id.property_account_expense_id.id
			move_line_value = {
				'type': 'src',
				'analytic_account_id':self.analytic_id.id,
				'name': self.employee_id.name + ': ' + line.ref,
				'price_unit': line.amount,
				'quantity': 1,
				'price': line.amount,
				'account_id': line.product_id.property_account_expense_id.id,
				'product_id': line.product_id.id,
				'uom_id': 1,
			   # 'analytic_account_id': self.analytic_account_id.id,
			}
			move_line.append(move_line_value)
		#print "GENERAL EXPENSE PREPARE MOVE LINE"
		#print move_line
		return move_line

	#general expense
	# @api.multi
	def _compute_expense_totals(self, company_currency, account_move_lines, move_date):
		#print "-----COMPUTE EXPENSE TOTAL--------"
		account_move_lines = account_move_lines[0]
		#print 
		self.ensure_one()
		total = 0.0
		total_currency = 0.0
		for line in account_move_lines:
			#print line
			line['currency_id'] = False
			line['amount_currency'] = False
			if self.currency_id != company_currency:
				line['currency_id'] = self.currency_id.id
				line['amount_currency'] = line['price']
				#line['price'] = self.currency_id.compute(line['price'], company_currency)
				line['price'] = line['price']
			total -= line['price']
			total_currency -= line['amount_currency'] or line['price']
		return total, total_currency, account_move_lines

	# @api.multi
	def _move_line_get(self):
		account_move = []
		for expense in self:
			move_line = expense._prepare_move_line_value()
			account_move.append(move_line)
		return account_move

	def _prepare_move_line(self, line):
		#partner_id = self.employee_id.address_home_id.commercial_partner_id.id
		if self.currency_id.id !=self.company_id.currency_id.id:
	# 22-01-2021 Extra credit by M2h
			# exp = self.amount
			# adv = self.advance_amount
			# acc_ids = self.env['account.account'].search([('name','=','Cash')])
			# print('.......................... exp = ',exp,' and adv = ',adv)
			# if adv > exp:
			# 	collect = exp - adv
			return {
				'date_maturity': line.get('date_maturity'),
				'exp_exp_id': self.expense_prepaid_ids.id,
				'expense_id':self.id,
				#'partner_id': partner_id,
				'name': line['name'][:64],
				'debit': line['price'] > 0 and line['price'],
				'credit': line['price'] < 0 and - line['price'],
				'account_id': line['account_id'],
				'analytic_line_ids': line.get('analytic_line_ids'),
				'amount_currency': line['price'] > 0 and abs(line['price']) or - abs(line['price']),
				'currency_id': line.get('currency_id'),
				'tax_line_id': line.get('tax_line_id'),
				'tax_ids': line.get('tax_ids'),
				'quantity': line.get('quantity', 1.00),
				'product_id': line.get('product_id'),
				'analytic_account_id': line.get('analytic_account_id'),
				'payment_id': line.get('payment_id'),
			}
			
		else:
			return {
				'date_maturity': line.get('date_maturity'),
				'exp_exp_id': self.expense_prepaid_ids.id,
				'expense_id':self.id,
				#'partner_id': partner_id,
				'name': line['name'][:64],
				'debit': line['price'] > 0 and line['price'],
				'credit': line['price'] < 0 and - line['price'],
				'account_id': line['account_id'],
				'analytic_line_ids': line.get('analytic_line_ids'),
				# 'amount_currency': line['price'] > 0 and abs(line.get('amount_currency')) or - abs(line.get('amount_currency')),
				# 'currency_id': line.get('currency_id'),
				'tax_line_id': line.get('tax_line_id'),
				'tax_ids': line.get('tax_ids'),
				'quantity': line.get('quantity', 1.00),
				'product_id': line.get('product_id'),
				'analytic_account_id': line.get('analytic_account_id'),
				'payment_id': line.get('payment_id'),
			}

	def _prepare_move_line_adjustment(self, line):
		#partner_id = self.employee_id.address_home_id.commercial_partner_id.id
		if self.currency_id.id !=self.company_id.currency_id.id:
			return {
				'date_maturity': line.get('date_maturity'),
				'adj_exp_id': self.expense_prepaid_ids.id,
				#'partner_id': partner_id,
				'name': line['name'][:64],
				'debit': line['price'] > 0 and line['price'],
				'credit': line['price'] < 0 and - line['price'],
				'account_id': line['account_id'],
				'analytic_line_ids': line.get('analytic_line_ids'),
				'amount_currency': line['price'] > 0 and abs(line['price']) or - abs(line['price']),
				'currency_id': line.get('currency_id'),
				'tax_line_id': line.get('tax_line_id'),
				'tax_ids': line.get('tax_ids'),
				'quantity': line.get('quantity', 1.00),
				'product_id': line.get('product_id'),
				'analytic_account_id': line.get('analytic_account_id'),
				'payment_id': line.get('payment_id'),
			}
		else:
			 return {
				'date_maturity': line.get('date_maturity'),
				'adj_exp_id': self.expense_prepaid_ids.id,
				#'partner_id': partner_id,
				'name': line['name'][:64],
				'debit': line['price'] > 0 and line['price'],
				'credit': line['price'] < 0 and - line['price'],
				'account_id': line['account_id'],
				'analytic_line_ids': line.get('analytic_line_ids'),
				# 'amount_currency': line['price'] > 0 and abs(line.get('amount_currency')) or - abs(line.get('amount_currency')),
				# 'currency_id': line.get('currency_id'),
				'tax_line_id': line.get('tax_line_id'),
				'tax_ids': line.get('tax_ids'),
				'quantity': line.get('quantity', 1.00),
				'product_id': line.get('product_id'),
				'analytic_account_id': line.get('analytic_account_id'),
				'payment_id': line.get('payment_id'),
			}

	def general_expense_cashier_cancel(self):
		return self.write({'state': 'cancel'})

	# third journal
	# @api.multi
	def close_expenses(self):
		#print "-------------------CLOSE EXPENSE--------------------------"
		amount = self.amount
		adv = self.advance_amount
		adjust = self.adjustment_amount
			
		if adv > amount:
			journal_dict = {}
			move_line_idd = self.env['account.move.line'].search([('general_exp_id','=',self.expense_prepaid_ids.id)])
			move_idd = self.env['account.move'].search([('id','=',move_line_idd.move_id.id)])
			# collect = 'Collect: '+str(move_idd.name)
			# refund = 'Refund: '+str(move_idd.name)
			collect = 'Additional: '+str(self.expense_prepaid_ids.voucher_no)
			refund = 'Refund: '+str(self.expense_prepaid_ids.voucher_no)
			journal_idd = self.env['account.journal'].search([('code','=','JV')])
			for expense in self:
				if not expense.date:
					raise UserError(_('You must choose close date!'))
				acc_date = expense.date
				diff_amount = expense.advance_amount - expense.amount
				#print "Different", diff_amount
				if diff_amount != 0:
					journal = expense.state_type
					journal_dict.setdefault(journal, [])
					journal_dict[journal].append(expense)
					#print journal_dict.items()
					#create the move that will contain the accounting entries
					exp = expense.amount
					adv = expense.advance_amount
					if adv < exp:
						move = self.env['account.move'].create({
							'journal_id': journal_idd.id,
							'company_id': self.env.user.company_id.id,
							'date': acc_date,
							'ref': collect,
							'name': '/',
						})
						print (collect,'........... if condition')
					else:
						move = self.env['account.move'].create({
							'journal_id': journal.id,
							'company_id': self.env.user.company_id.id,
							'date': acc_date,
							'ref': refund,
							'name': '/',
						})
						print (refund,'........... else condition')

					for journal, expense_list in journal_dict.items():
						#print "CLOSING"
						#create the move that will contain the accounting entries
						for expense in expense_list:
							#print 'CLOSING LIST'
							#company_currency = expense.company_id.currency_id
							#diff_currency_p = expense.currency_id != company_currency
							
							move_lines = expense._finish_line_get()
							#print "LOOK!!---------------------"
							#print move_lines
							# if self.currency_id != company_scurrency:
							#     total_currency = self.currency_id.with_context(date=date_post or fields.Date.context_today(self)).compute(expense.amount_total, company_currency)
							

							aid = expense.expense_prepaid_ids.account_ids if diff_amount > 0 else expense.expense_prepaid_ids.cash_account
							amount = diff_amount if diff_amount < 0 else diff_amount * (-1)
							# if diff_amount < 0 and not expense.state_type.default_credit_account_id:
							#     raise UserError(_("No debit account found for the %s journal, please configure one.") % (expense.state_type.name))
							
							move_lines.append({
									'type': 'dest',
									'adj_exp_id': expense.expense_prepaid_ids.id,
									'name': expense.expense_prepaid_ids.voucher_no or expense.employee_id.name,
									'price': amount,
									'quantity': 1,
									'account_id': aid.id,
									'date_maturity': expense.date,
									'amount_currency': 0,
									'currency_id': False,
								})
							lines = list(map(lambda x:(0, 0, expense._prepare_move_line_adjustment(x)), move_lines))
							move.with_context(dont_create_taxes=True).write({'line_ids': lines})
							move.post()
							expense.expense_prepaid_ids.write({'adjustment_journal':move.id})
						print ('------------------------------close expense ----------------------------')
					# print move_lines

					#convert eml into an osv-valid format

		else:
			if adjust > 0:
				acc_model = self.env['account.move']
				collect = 'Additional: '+str(self.expense_prepaid_ids.voucher_no)
				journal_idd = self.env['account.journal'].search([('code','=','JV'),('company_id','=',self.company_id.id)])
				credit_acc = self.expense_prepaid_ids.cash_account
				debit_acc = self.line_ids.product_id.property_account_expense_id

				acc_move = acc_model.create({
					'journal_id': journal_idd.id,
					'company_id': self.env.user.company_id.id,
					'date': self.date,
					'ref': collect,
					'name': '/',
					'line_ids': [
						(0, 0,  {'name': self.expense_prepaid_ids.voucher_no,'date_maturity': self.date,'currency_id': self.currency_id.id, 'adj_exp_id': self.expense_prepaid_ids.id,'account_id':credit_acc.id, 'name':self.name, 'credit':self.adjustment_amount}),
						(0, 0,  {'name': self.expense_prepaid_ids.voucher_no,'date_maturity': self.date,'currency_id': self.currency_id.id,'adj_exp_id': self.expense_prepaid_ids.id,'account_id':debit_acc.id, 'name':self.name,  'debit':self.adjustment_amount})
					]
				})
				acc_move.action_post()
			else:
				journal_dict = {}
				move_line_idd = self.env['account.move.line'].search([('general_exp_id','=',self.expense_prepaid_ids.id)])
				move_idd = self.env['account.move'].search([('id','=',move_line_idd.move_id.id)])
				# collect = 'Collect: '+str(move_idd.name)
				# refund = 'Refund: '+str(move_idd.name)
				collect = 'Additional: '+str(self.expense_prepaid_ids.voucher_no)
				refund = 'Refund: '+str(self.expense_prepaid_ids.voucher_no)
				journal_idd = self.env['account.journal'].search([('code','=','JV')])
				journal_csh = self.env['account.account'].search([('name','=','Cash')])
				line_ids = self.env['hr.expense.line'].search([('expense_id','=',self.ids)])
				for expense in self:
					if not expense.date:
						raise UserError(_('You must choose close date!'))
					acc_date = expense.date
					diff_amount = expense.advance_amount - expense.amount
					#print "Different", diff_amount
					if diff_amount != 0:
						journal = expense.state_type
						journal_dict.setdefault(journal, [])
						journal_dict[journal].append(expense)
						#print journal_dict.items()
						#create the move that will contain the accounting entries
						exp = expense.amount
						adv = expense.advance_amount
						if adv < exp:
							move = self.env['account.move'].create({
								'journal_id': journal_idd.id,
								'company_id': self.env.user.company_id.id,
								'date': acc_date,
								'ref': collect,
								'name': '/',
							})
						else:
							move = self.env['account.move'].create({
								'journal_id': journal.id,
								'company_id': self.env.user.company_id.id,
								'date': acc_date,
								'ref': refund,
								'name': '/',
							})

						for journal, expense_list in journal_dict.items():
							#print "CLOSING"
							#create the move that will contain the accounting entries
							for expense in expense_list:
								#print 'CLOSING LIST'
								#company_currency = expense.company_id.currency_id
								#diff_currency_p = expense.currency_id != company_currency
								
								move_lines = expense._finish_line_get()
								#print "LOOK!!---------------------"
								#print move_lines
								# if self.currency_id != company_scurrency:
								#     total_currency = self.currency_id.with_context(date=date_post or fields.Date.context_today(self)).compute(expense.amount_total, company_currency)
								# if adv < amount:
								# 	aid = journal_csh
								# 	print('................... AID cash ',aid)
								# else:
								# 	aid = line_ids.product_id.account_ids
								# 	print('................... AID Line ',aid)
								aid = line_ids.product_id.property_account_expense_id if diff_amount > 0 else journal_csh
								# aid = expense.expense_prepaid_ids.account_ids if diff_amount > 0 else expense.expense_prepaid_ids.cash_account
								amount = diff_amount if diff_amount < 0 else diff_amount * (-1)
								# if diff_amount < 0 and not expense.state_type.default_credit_account_id:
								#     raise UserError(_("No debit account found for the %s journal, please configure one.") % (expense.state_type.name))
								
								move_lines.append({
										'type': 'dest',
										'adj_exp_id': expense.expense_prepaid_ids.id,
										'name': expense.expense_prepaid_ids.voucher_no or expense.employee_id.name,
										'price': amount,
										'quantity': 1,
										'account_id': aid.id,
										'date_maturity': expense.date,
										'amount_currency': 0,
										'currency_id': False,
									})
								lines = list(map(lambda x:(0, 0, expense._prepare_move_line_adjustment(x)), move_lines))
								move.with_context(dont_create_taxes=True).write({'line_ids': lines})
								move.post()
								expense.expense_prepaid_ids.write({'adjustment_journal':move.id})

		return True

	def adjustment_amount_calculate(self):
		for record in self:
			record.state = 'approved'
			acc_model = self.env['account.move']
			acc_model.create({
				'ref': record.name,
				'journal_id': record.journal_id.id,
				'line_ids': [
					(0, 0,  {'partner_id':record.partner_id.id,'account_id':record.account_id.id, 'name':record.name, 'credit':record.amount}),
					(0, 0,  {'partner_id':record.partner_id.id,'account_id':record.account_id.id, 'name':record.name,  'debit':record.amount})
				]
			})

	def exchange_gain_loss_expenses(self):
	#print "-------------------CLOSE EXPENSE--------------------------"
		journal_dict = {}
		line_ids = self.env['hr.expense.line'].search([('expense_id','=',self.ids)])
		for expense in self:
			if not expense.date:
				raise UserError(_('You must choose close date!'))
			if expense.expense_prepaid_ids:
				acc_date = expense.paid_date
				diff_amount = (expense.currency_rate-expense.expense_prepaid_ids.currency_rate)*expense.amount
				#print "Different", diff_amount
				if diff_amount != 0:
					if not expense.company_id.currency_exchange_journal_id:
						raise UserError(_('Set up Exchange Gain Lose Journal!'))
					journal = expense.company_id.currency_exchange_journal_id
					journal_dict.setdefault(journal, [])
					journal_dict[journal].append(expense)
					#print journal_dict.items()
					#create the move that will contain the accounting entries
					move = self.env['account.move'].create({
						'journal_id': journal.id,
						'company_id': self.env.user.company_id.id,
						'date': acc_date,
						'ref': expense.description,
						'name': '/',
					})

					for journal, expense_list in journal_dict.items():
						#print "CLOSING"
						#create the move that will contain the accounting entries
						for expense in expense_list:
							#print 'CLOSING LIST'
							#company_currency = expense.company_id.currency_id
							#diff_currency_p = expense.currency_id != company_currency
							
							move_lines = expense._gain_line_get()
							#print "LOOK!!---------------------"
							#print move_lines
							# if self.currency_id != company_scurrency:
							#     total_currency = self.currency_id.with_context(date=date_post or fields.Date.context_today(self)).compute(expense.amount_total, company_currency)
							
							# if adv < amount:
							# 	aid = journal_csh
							# else:
							# 	aid = line_ids.account_ids
							# aid = expense.expense_prepaid_ids.account_ids if diff_amount > 0 else expense.company_id.currency_exchange_journal_id.default_debit_account_id
							aid = line_ids.product_id.property_account_expense_id if diff_amount > 0 else expense.company_id.currency_exchange_journal_id.default_debit_account_id
							amount = diff_amount if diff_amount < 0 else diff_amount * (-1)
							if diff_amount < 0 and not expense.company_id.currency_exchange_journal_id.default_credit_account_id:
								raise UserError(_("No debit account found for the %s journal, please configure one.") % (expense.company_id.currency_exchange_journal_id.name))
							
							move_lines.append({
									'type': 'dest',
									'name': expense.expense_prepaid_ids.voucher_no or expense.employee_id.name,
									'price': amount,
									'quantity': 1,
									'account_id': aid.id,
									'date_maturity': expense.date,
									'ref': expense.expense_prepaid_ids.voucher_no or expense.employee_id.name,
								})
							lines = list(map(lambda x:(0, 0, expense._prepare_gain_line(x)), move_lines))
							move.with_context(dont_create_taxes=True).write({'line_ids': lines})
							move.post()
					#print move_lines

					
			return True

	def _prepare_gain_line(self, line):
		#partner_id = self.employee_id.address_home_id.commercial_partner_id.id
		return {
			'date_maturity': line.get('date_maturity'),            #'partner_id': partner_id,
			'name': line['name'][:64],
			'debit': line['price'] > 0 and line['price'],
			'credit': line['price'] < 0 and - line['price'],
			'account_id': line['account_id'],
			'analytic_line_ids': line.get('analytic_line_ids'),
			# 'amount_currency': 0.0,
			# 'currency_id': line.get('currency_id'),
			'tax_line_id': line.get('tax_line_id'),
			'tax_ids': line.get('tax_ids'),
			'quantity': line.get('quantity', 1.00),
			'product_id': line.get('product_id'),
			'analytic_account_id': line.get('analytic_account_id'),
			'payment_id': line.get('payment_id'),
		}

	# @api.multi
	def _finish_line_get(self):
		#print "---------------------finish line get---------------------------"
		account_move = []
		for expense in self:
			#print "loop 1"
			diff_amount = expense.advance_amount - expense.amount
			aid = expense.expense_prepaid_ids.account_ids if diff_amount < 0 else expense.expense_prepaid_ids.cash_account
			amount = diff_amount if diff_amount > 0 else diff_amount * (-1)
			#print amount
			if diff_amount > 0 and not expense.state_type.default_debit_account_id:
				raise UserError(_("No debit account found for the %s journal, please configure one.") % (expense.state_type.name))
			move_line = {
					'type': 'src',
					'adj_exp_id': expense.expense_prepaid_ids.id,
					'name': expense.expense_prepaid_ids.voucher_no or expense.employee_id.name,
					'price': amount,
					'quantity': 1,
					'account_id': aid.id,
					'date_maturity': expense.date,
					'ref': expense.expense_prepaid_ids.voucher_no or expense.employee_id.name,
				}
			account_move.append(move_line)
		#print "---------------account move---------------------"
		#print account_move
		return account_move
	def _gain_line_get(self):
		#print "---------------------finish line get---------------------------"
		account_move = []
		for expense in self:
			#print "loop 1"
			diff_amount = (expense.currency_rate-expense.expense_prepaid_ids.currency_rate)*expense.amount
			aid = expense.expense_prepaid_ids.account_ids if diff_amount < 0 else expense.company_id.currency_exchange_journal_id.default_debit_account_id
			amount = diff_amount if diff_amount > 0 else diff_amount * (-1)
			#print amount
			if diff_amount > 0 and not expense.state_type.default_debit_account_id:
				raise UserError(_("No debit account found for the %s journal, please configure one.") % (expense.state_type.name))
			move_line = {
					'type': 'src',
					'name': expense.expense_prepaid_ids.voucher_no or expense.employee_id.name,
					'price': amount,
					'quantity': 1,
					'account_id': aid.id,
					'date_maturity': expense.date,
					'ref': expense.expense_prepaid_ids.voucher_no or expense.employee_id.name,
				}
			account_move.append(move_line)
		#print "---------------account move---------------------"
		#print account_move
		return account_move


# class hr_main_gory(models.Model):
# 	_name = "hr.main.category"

# 	name = fields.Char('Main Category', required=True)


# class hr_sub_category(models.Model):
# 	_name = "hr.sub.category"

# 	name = fields.Char('Sub Category', required=True)
# 	categ_id = fields.Many2one('hr.main.category', string='Category', required=True)




class hr_general_expense_line(models.Model):
	_name = "hr.expense.line"
	_description = "General Expense Line"
	_order = "sequence, date_value desc"

	# @api.one
	def _get_uom_id(self):
		result = self.env['ir.model.data'].get_object_reference('product', 'product_uom_unit')
		return result and result[1] or False

	
	
	product_id = fields.Many2one('product.product',string='Title',default=[] , domain="[('can_be_expensed','=',True)]")    
	account_ids = fields.Many2one('account.account', string='Account Name',store=True)
	account_code = fields.Char(string='Account Code',related='account_ids.code',store=True)
	# project_id = fields.Many2one('hr.expense.prepaid.project', 'Project')
	# group_ids = fields.Many2one('expense.prepaid.group', 'Group Name',require=True)
	# group_code = fields.Char(related = 'group_ids.group_code')
	amount = fields.Float('Amount')
	adjustment_amount = fields.Float('Additional Amount')
	ref = fields.Char('Description', required=True)
	line_no = fields.Integer(compute='_get_line_numbers', string='Sr')
	name = fields.Char('Expense Note')
	date_value = fields.Date('Date',required=True,store=True)
	expense_id = fields.Many2one('hr.expense', 'Expense', ondelete='cascade', required=False)
	prepaid_id = fields.Many2one('expense.prepaid', 'Advance', ondelete='cascade', required=False)
	total_amount = fields.Float(string='Total')
	unit_amount = fields.Float('Unit Price')
	unit_quantity = fields.Float('Quantities',default=1)
	# uom_id = fields.Many2one('product.uom', 'Unit of Measure',default=_get_uom_id)
	description = fields.Text('Description')
	analytic_account = fields.Many2one('account.analytic.account','Analytic account',related="expense_id.analytic_id")
	sequence = fields.Integer('Sequence', select=True, help="Gives the sequence order when displaying a list of expense lines.")


	# @api.multi
	def _get_line_numbers(self):
		for expense in self.mapped('expense_id'):
			line_no = 1
			for line in expense.line_ids:
				line.line_no = line_no
				line_no += 1

	@api.model
	def default_get(self, fields_list):
		res = super(hr_general_expense_line, self).default_get(fields_list)
		res.update({'line_no': len(self._context.get('line_ids', [])) + 1}) 
		return res


	@api.model
	def create(self,data):
		if data:
			#print data,"Data_______"
			record = super(hr_general_expense_line, self).create(data)
		return record

	# @api.one
	def write(self,vals):
		flag = super(hr_general_expense_line, self).write(vals)

		return flag

	@api.model
	@api.onchange('product_id')
	def onchange_product_id(self):
		if self.product_id:
			product = self.env['product.product'].browse(self.product_id)
			product=product.id
			amount_unit = product.standard_price
			self.unit_amount = amount_unit
			self.uom_id = product.uom_id.id
			self.date_value = self.expense_id.date
			self.account_ids = self.product_id.property_account_expense_id
			self.analytic_account = self.expense_id.analytic_id
			self.ref = self.expense_id.description


# class HrExpenseSheet(models.Model):
# 	_inherit = "hr.expense.sheet"

# 	def action_submit_sheet(self):
#         self.write({'state': 'submit'})
#         self.activity_update()   