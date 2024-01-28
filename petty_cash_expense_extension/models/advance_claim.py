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

class ProductProduct(models.Model):
	_inherit = 'product.product'

	adv_claim_id = fields.Many2one('advance.claim','Advance Claim')

class Expense_Prepaid(models.Model):
	_name = 'advance.claim'
	_inherit = ['mail.thread', 'mail.activity.mixin']
	_description = 'Claim Request'
	_order = "invoice_date desc, voucher_no desc"


	@api.model
	def get_today(self):
		my_date = fields.Datetime.context_timestamp(self, timestamp=datetime.now())
		return my_date


	state = fields.Selection([
		('draft', 'Draft'),
		('confirm', 'Confirm'),
		('manager_approve','Manager Approved'),
		('approve', 'Finance Approved'),
		('gm_approve', 'GM Approved'),
		('cancel', 'Cancelled'),
		('paid', 'Paid'),
		('closed', 'Close'),
		],
		'Status',default="draft",tracking=True)

	def employee_get(self):        
		emp_id = self.env.context.get('default_employee_name', False)
		if emp_id:
			return emp_id
		ids = self.env['hr.employee'].search([('user_id', '=', self.env.uid)])
		if ids:
			return ids[0]
		return False

	account_ids = fields.Many2one('account.account', 'Advanced Account Name')
	account_code = fields.Char(related = 'account_ids.code',string='Advanced Account Code')
	name_reference = fields.Char('Reference', required=True)
	voucher_no = fields.Char(string='Invoice No',states={'draft':[('readonly',False)], 'confirm':[('readonly',False)]}, copy=False,tracking=True)
	invoice_date = fields.Date('Date', default=get_today, required=True,tracking=True)
	employee_name = fields.Many2one('hr.employee', 'Employee', default=employee_get, domain="[('active','=',True)]", required=True,tracking=True)
	department_id = fields.Many2one('hr.department','Department')
	advance_amount = fields.Float('Advanced Amount',tracking=True)
	manager_approve_date = fields.Date('Manager Approve Date',default=fields.date.today() , states={'manager_approve':[('required', True)]})
	# finance_approve_date = fields.Date('Finance Approve Date')
	# next_approval_person = fields.Many2one('hr.employee','Next Approveal Person')
	expense_total = fields.Float('Expenses Total',tracking=True)
	chart_of_account = fields.Many2one('account.account','Chart of Account')
	currency_id = fields.Many2one('res.currency', 'Currency',required=True, default=119, readonly=True, states={'draft':[('readonly',False)],'cancelled':[('readonly',False)]})
	account_name = fields.Char(' ')
	state_type = fields.Many2one('account.journal', string='Journal',required=True,store=True)
	cash_account = fields.Many2one('account.account','Paid By')
	move_line_ids = fields.One2many('account.move.line', 'adv_claim_id', string='Journal Advance Claim', store=True)
	# exp_move_line_ids = fields.One2many('account.move.line', 'exp_exp_id', string='Journal Expense', store=True)
	# adj_move_line_ids = fields.One2many('account.move.line', 'adj_exp_id', string='Journal Adjustment', store=True)
	note = fields.Text('ADVANCE NOTE')
	can_reset = fields.Boolean(compute='_get_can_reset')
	can_approve = fields.Boolean(compute='_get_can_approve')
	paid_date = fields.Date('Cash Paid Date',default=fields.date.today() , states={'approve':[('required', True)], 'paid':[('readonly', True)], 'closed':[('readonly', True)]})
	paid_ref = fields.Char('Paid Ref', states={'paid':[('readonly', True)], 'closed':[('readonly', True)]})
	close_date = fields.Date('Cash Refund Date', states={'closed':[('readonly', True)]})
	close_ref = fields.Char('Close Ref', states={'closed':[('readonly', True)]})
	account_move_id = fields.Many2one('account.move', string='Advance Journal Entry', copy=False, track_visibility="onchange")
	advance_account_move_id = fields.Many2one('account.move', string='Expense Journal Entry', copy=False, track_visibility="onchange")
	adjustment_journal =  fields.Many2one('account.move', string='Adjustment Journal Entry', copy=False, track_visibility="onchange")
	diff_amount = fields.Float('Balance Amount', readonly=True, default=0.0)
	fst_aproval = fields.Many2one('hr.employee', string='First Aproval', domain="[('active','=',True)]")
	snd_aproval = fields.Many2one('hr.employee', string='Second Aproval', domain="[('active','=',True)]" )
	analytic_id = fields.Many2one('account.analytic.account','Analytic Account')
	company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id, required=True)
	line_ids = fields.One2many('advance.claim.line', 'calim_id', 'Expense Lines')
	# TPS===================
	product_id = fields.Many2many('product.product', 'prepaid_product_rel', 'calim_id', 'product_id',string='Product')
	# TPS===================

		# product_id = fields.Many2one('product.product', 'Product', required=True, domain="[('can_be_expensed','=',False)]")
	# 20190524 by yma
	# prepaid_type = fields.Many2one('hr.prepaid.type',string='Type')
	currency_rate = fields.Float(string='Currency Rate')
	# md = fields.Boolean('Need MD Approved ?')
	approved_by_id = fields.Many2one('hr.employee',string='Approved By Manager', required=True)
	finance_approved_id = fields.Many2one('hr.employee',string='Finance Approved', domain="[('finance','=',True)]", required=True)
	is_approve = fields.Boolean('Is Approve Manager ?',compute='get_approve',default=False)
	is_approve_finance = fields.Boolean('Is Approve Finance ?',compute='get_approve',default=False)
	is_user = fields.Boolean('Is User',compute='get_approve',default=False)
	user_id = fields.Many2one('res.users','User', default=lambda self: self.env.user,tracking=True)
	is_cashier = fields.Boolean('Is Cashier',compute='get_approve', default=False)

	def get_approve(self):
		for approve in self:
			reason = False
			finance = False
			cashier = False
			user = False
			approver = False
			admin = False
			to_approve_id = self.env.uid
			user = approve.user_id
			# to_approve_id= self.env['hr.employee'].search([('user_id', '=', self.env.uid)]).id

			if to_approve_id == approve.approved_by_id.user_id.id:
				reason = True
			if to_approve_id == approve.finance_approved_id.user_id.id:
				finance = True
			# if user.has_group('petty_cash_expense_extension.group_petty_cashier'):
			# 	cashier = True
			# 	print('........................... cashier ',cashier)
			if user.has_group('petty_cash_expense_extension.group_users'):
				user = True
			approve.is_approve = reason
			approve.is_approve_finance = finance
			# approve.is_cashier = cashier
			# approve.is_user = user
			# approve.write({'is_cashier': cashier})
			approve.write({'is_user': user})

	def get_sequence(self):
	# 11-01-2021 by M2h ********************************************8
		sequence = self.env['ir.sequence'].next_by_code('advance.claim')
		journal = self.state_type.id
		journal_ids = self.env['account.journal'].search([('id','=',journal)])
		code = journal_ids.code
		year = datetime.now().year
		month = datetime.now().month
		if month < 10:
			month = '0'+str(month)
		seq_no = str(self.env.user.company_id.code)+'-'+str(code)+'-'+str(year)+'-'+str(month)+sequence
		return seq_no

	@api.onchange('employee_name')
	def onchange_employee(self):
		self.department_id = self.employee_name.department_id.id

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

	def print_adv_claim(self):
		par=self.ids
		if par:
			url = 'http://localhost:8080/birt/frameset?__report=idealab_claim_req.rptdesign&order_id=' + str(self.ids[0])
		if url :
			return {
			'type' : 'ir.actions.act_url',
			'url' : url,
			'target': 'new',
				}
		else:
			raise ValidationError('Not Found')            
		return True

	   
	@api.onchange('line_ids')
	def compute_amount(self):
		if self.line_ids:
			total = 0.0
			print ('why no woking ----------------------------------------------->><<>><<>><<>>')
			for line in self.line_ids:
				total += line.amount
			self.advance_amount = total

	def advance_claim_paid(self):
		for expense in self:
			journal = expense.state_type
			expense.paid_date = date.today()
			if not journal:
				raise ValidationError('Define Journal')
			#create the move that will contain the accounting entries
			acc_date = date.today()
			move = self.env['account.move'].create({
				'journal_id': journal.id,
				'company_id': self.env.user.company_id.id,
				'date': acc_date,
				'ref': expense.voucher_no,
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
			# emp_account = expense.cash_account.id
			emp_account = expense.cash_account.id
			if not emp_account:
				raise ValidationError('Define Paid By')

			aml_name = self.employee_name.name + ': ' + self.voucher_no.split('\n')[0][:64]
			move_lines.append({
					'type': 'dest',
					'name': aml_name,
					'analytic_account_id':expense.analytic_id.id,
					'price': total,
					'account_id': emp_account,
					'date_maturity': acc_date,
					'amount_currency': expense.advance_amount*-1,
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
		aml_name = self.employee_name.name + ': ' + self.voucher_no.split('\n')[0][:64]
		if not self.account_ids:
			raise ValidationError('Define Advance Account')
		move_line = {
			'type': 'src',
			'name': aml_name,
			'analytic_account_id':self.analytic_id.id,
			'price_unit': self.advance_amount,
			'quantity': 1,
			'price': self.advance_amount,
			'account_id': self.account_ids.id,
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
		#partner_id = self.employee_name.address_home_id.commercial_partner_id.i
		if self.currency_id.id !=self.company_id.currency_id.id:
			return {
				'date_maturity': line.get('date_maturity'),
				'adv_claim_id': self.id,
				#'partner_id': partner_id,
				'name': line['name'][:64],
				'debit': line['price'] > 0 and line['price'],
				'credit': line['price'] < 0 and - line['price'],
				'account_id': line['account_id'],
				'analytic_line_ids': line.get('analytic_line_ids'),
				'amount_currency': line['price'] > 0 and abs(line.get('amount_currency')) or - abs(line.get('amount_currency')),
				# 'exchange_rate':self.currency_rate,
				'currency_id': self.currency_id.id,
				'tax_line_id': line.get('tax_line_id'),
				'tax_ids': line.get('tax_ids'),
				'quantity': line.get('quantity', 1.00),
				'product_id': line.get('product_id'),
				'product_uom_id': line.get('uom_id'),
				'analytic_account_id': line.get('analytic_account_id'),
				'payment_id': line.get('payment_id'),
			}
		else:
			return {
				'date_maturity': line.get('date_maturity'),
				'adv_claim_id': self.id,
				#'partner_id': partner_id,
				'name': line['name'][:64],
				'debit': line['price'] > 0 and line['price'],
				'credit': line['price'] < 0 and - line['price'],
				'account_id': line['account_id'],
				'analytic_line_ids': line.get('analytic_line_ids'),
				# 'exchange_rate':self.currency_rate,
				# 'amount_currency': line['price'] > 0 and abs(line.get('amount_currency')) or - abs(line.get('amount_currency')),
				# 'currency_id': line.get('currency_id'),
				'tax_line_id': line.get('tax_line_id'),
				'tax_ids': line.get('tax_ids'),
				'quantity': line.get('quantity', 1.00),
				'product_id': line.get('product_id'),
				'product_uom_id': line.get('uom_id'),
				'analytic_account_id': line.get('analytic_account_id'),
				'payment_id': line.get('payment_id'),
			}

	def _get_currency(self, cr, uid, context=None):
		user = self.pool.get('res.users').browse(cr, uid, [uid], context=context)[0]
		return user.company_id.currency_id.id

	#@api.one
	def _get_can_reset(self):
		result = False
		is_financial_manager = False
		user = self.env['res.users'].browse()
		group_financial_manager_id = self.env['ir.model.data'].get_object_reference('account', 'group_account_manager')[1]
		if group_financial_manager_id in [g.id for g in user.groups_id]:
			is_financial_manager = True

		for expense in self.browse(self.id):
			if expense.state in ['confirm','cancel']:
				if is_financial_manager:
					result = False
				elif expense.employee_name and expense.employee_name.user_id and expense.employee_name.user_id.id == self.env.uid:
					result = True
		self.can_reset = result

	# @api.one
	def _get_can_approve(self):
		#print '--------------------GET CAN APPROVE-------------------------'
		# result = False
		# #print self.env.user , self.fst_aproval.user_id
		# if self.fst_aproval.user_id == self.env.user:
		#     #print "Correct User"
		#     self.can_approve = True
		self.can_approve = True

	@api.model
	def create(self, data):
		# data['voucher_no'] = self.get_sequence()
		record_id = super(Expense_Prepaid, self).create(data)
		return record_id

	# @api.multi
	def name_get(self):
		res = super(Expense_Prepaid, self).name_get()
		data = []
		for expense in self:
			display_value = ''
			display_value += str(expense.voucher_no) or ""
			data.append((expense.id, display_value))
		return data

	@api.model
	def name_search(self, name, args=None, operator='ilike', limit=100):
		args = args or []
		recs = self.browse()
		if not recs:
			recs = self.search([('name_reference', operator, name)] + args, limit=limit)
		if not recs:
			recs = self.search([('voucher_no', operator, name)] + args, limit=limit)
		return recs.name_get()

	def advance_claim_confirm(self):
		mail_ids = self.env['mail.activity']
		model_ids = self.env['ir.model'].search([('model','=','advance.claim')])
		ids = self.approved_by_id.user_id
		date = self.invoice_date
		name = self.voucher_no
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
		self.voucher_no = self.get_sequence()
		# print('............... mail.activity created',mail_ids)
		return self.write({'state': 'confirm'})

	# def md_approved(self):
	# 	return self.write({'state': 'md'})

	def advance_claim_draft(self):
		user_ids = self.env['res.users'].search([('id','=',self.env.uid)])
		if user_ids.has_group('petty_cash_expense_extension.group_users'):
			raise ValidationError('User group not allowed for this!')
		return self.write({'state': 'draft'})

	######## Line Manager #########

	def advance_claim_manager_accept(self):
		mail_ids = self.env['mail.activity']
		model_ids = self.env['ir.model'].search([('model','=','advance.claim')])
		ids = self.finance_approved_id.user_id
		date = self.invoice_date
		name = self.voucher_no
		dd = self.ids
		cc = ''
		for d in dd:
			cc += str(d)
		cc = int(cc)
		# print('........................................... id ',str(dd),' and cc ',cc)
		mail_s = mail_ids.search([('res_model','=','advance.claim'),('res_id','=',cc)])
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
		# print('............... mail.activity created',mail_ids)
		return self.write({'state': 'manager_approve'})

	def approve(self):
		mail_ids = self.env['mail.activity']
		# model_ids = self.env['ir.model'].search([('model','=','advance.claim')])
		# ids = self.env['hr.employee'].search([('is_gm','=',True)])
		# ids = self.finance_approved_id.user_id
		# date = self.invoice_date
		# name = self.voucher_no
		dd = self.ids
		cc = ''
		for d in dd:
			cc += str(d)
		cc = int(cc)
		# print('........................................... id ',str(dd),' and cc ',cc)
		mail_s = mail_ids.search([('res_model','=','advance.claim'),('res_id','=',cc)])
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
		# print('............... mail.activity created',mail_ids)
		return self.write({'state': 'approve'})

	def gm_approve(self):
		# mail_ids = self.env['mail.activity']
		# dd = self.ids
		# cc = ''
		# for d in dd:
		# 	cc += str(d)
		# cc = int(cc)
		# mail_s = mail_ids.search([('res_model','=','advance.claim'),('res_id','=',cc)])
		# # print('>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<< +++++++++++++++  ',mail_s)
		# mail_s.unlink()
		return self.write({'state': 'gm_approve'})

	# @api.one
	# def advance_claim_manager_accept_snd(self):
	# 	return self.write({'state': 'manager_accepted_snd'})

	# @api.one
	def cancel(self):
		return self.write({'state': 'cancel'})

		

	def advance_claim_cashier_closed(self):
		date = self.get_today()
		close_ref = self.name_reference
		return self.write({'close_date': date,'state': 'closed','close_ref':close_ref})

	#for closed function
	# @api.multi
	def _move_line_get_closed(self):
		account_move = []
		for expense in self:
			move_line = expense._prepare_move_line_value_closed()
			account_move.append(move_line)
		return account_move

	# @api.multi
	def _prepare_move_line_value_closed(self):
		self.ensure_one()
		aml_name = self.employee_name.name + ': ' + self.voucher_no.split('\n')[0][:64]
		move_line = {
			'type': 'src',
			'name': aml_name,
			'price_unit': self.advance_amount,
			'quantity': 1,
			'price': self.advance_amount,
			'account_id': self.cahs.id,
		}
		return move_line

	def expense_accept(self, cr, uid, ids, context=None):
		for expense in self.browse(cr, uid, ids):
		  if not expense.manager_approve_date:
			  raise ValidationError('You must choose approve date!')
		return self.write(cr, uid, ids, {'state': 'accepted'}, context=context)
	  
	def expense_post(self, cr, uid, ids, context=None):
		for expense in self.browse(cr, uid, ids):
		  if not expense.post_date:
			  raise ValidationError('You must choose post date!')
		  if not expense.advance_amount > 0.0:
			  raise ValidationError('You must add advanced amount!')
		return self.write(cr, uid, ids, {'state': 'paid'}, context=context)
	  
	def expense_close(self, cr, uid, ids, context=None):
		for expense in self.browse(cr, uid, ids):
		  if not expense.close_date:
			  raise ValidationError('You must choose close date!')
		return self.write(cr, uid, ids, {'state': 'closed'}, context=context)

	def expense_canceled(self, cr, uid, ids, context=None):
		return self.write(cr, uid, ids, {'state': 'cancelled'}, context=context)

	def reset_to_draft(self, cr, uid, ids, context=None):
		return self.write(cr, uid, ids, {'state': 'draft'}, context=context)


class Expense_Prepaid_Line(models.Model):
	_name = 'advance.claim.line'
	_description = 'Expense Prepaid Line'    

	calim_id = fields.Many2one('advance.claim', 'Title', ondelete='cascade', select=True)    
	product_id = fields.Many2one('product.product', 'Product', domain="[('can_be_expensed','=',True)]")
	sequence = fields.Integer('Sequence', select=True, help="Gives the sequence order when displaying a list of expense lines.")
	date_value = fields.Date('Date',required=True,store=True)
	analytic_account = fields.Many2one('account.analytic.account','Analytic account',related="calim_id.analytic_id")
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
			self.date_value = self.calim_id.invoice_date
			self.account_ids = self.product_id.property_account_expense_id
			self.analytic_account = self.calim_id.analytic_id
			self.ref = self.calim_id.name_reference

	# @api.multi
	def _get_line_numbers(self):
		for expense in self.mapped('calim_id'):
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
			calim_id = super(Expense_Prepaid_Line, self).create(data)
		return calim_id
	
	# @api.one
	def write(self,vals):
		flag = super(Expense_Prepaid_Line, self).write(vals)

		return flag
		