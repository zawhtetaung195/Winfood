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

class PettyCashExpense(models.Model):
	_name = 'petty.cash.expense'
	_inherit = ['mail.thread', 'mail.activity.mixin']
	_description = 'Petty Cash Request'

	# @api.model
	# def action_request(self):
	# 	current = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
	# 	print('.............. Current ID ',current)
	# 	self.env.context = dict(self.env.context)
	# 	self.env.context.update({'default_requested_by_id': current})
	# 	self.requested_by_id = current
	# 	print('......... request ',self.requested_by_id)

	def employee_get(self):        
		emp_id = self.env.context.get('default_requested_by_id', False)
		if emp_id:
			return emp_id
		ids = self.env['hr.employee'].search([('user_id', '=', self.env.uid)])
		if ids:
			return ids[0]
		return False

	name = fields.Char('Description',tracking=True)
	requested_by_id = fields.Many2one('hr.employee',string='Requested By', default=employee_get, required=True,tracking=True)
	approved_by_id = fields.Many2one('hr.employee',string='Approved By Manager', required=True)
	finance_approved_id = fields.Many2one('hr.employee',string='Finance Approved', domain="[('finance','=',True)]", required=True)
	amount = fields.Float('Amount',tracking=True)
	description = fields.Text('Description')
	request_journal_id = fields.Many2one('account.journal',string="To", required=True) 
	payment_journal_id = fields.Many2one('account.journal',string="Payment Journal") 
	date_requested = fields.Date('Date Requested', default=fields.Date.today,tracking=True)
	date_received = fields.Date('Date Received',tracking=True)
	payment_line_ids = fields.One2many('account.payment','petty_cash_id',string='Payment Line')
	move_line_ids = fields.One2many('account.move.line','petty_cash_id',string='Move Line')
	account_ids = fields.Many2one('account.account',string='Account')
	currency_id = fields.Many2one('res.currency',string='Currency',default=119)
	currency_rate = fields.Float(string='Currency Rate')
	company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id)
	state = fields.Selection([
		('draft', 'To Submit'),
		('request', 'Requested'),
		('manager_validate', 'Manager Approved'),
		('validate', 'Finance Approved'),
		('gm_approve', 'GM Approved'),
		('refuse', 'Refused'),
		('cancel', 'Cancel')
		], string='Status', readonly=True,tracking=True, copy=False, default='draft')
	is_approve = fields.Boolean('Is Approve Manager ?',compute='get_approve',default=False)
	is_approve_finance = fields.Boolean('Is Approve Finance ?',compute='get_approve',default=False)

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
				
	def draft(self):
		self.write({'state': 'draft'})

	def request(self):
		mail_ids = self.env['mail.activity']
		model_ids = self.env['ir.model'].search([('model','=','petty.cash.expense')])
		ids = self.approved_by_id.user_id
		date = self.date_requested
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
		self.write({'state': 'request'})

	def manager_validate(self):
		mail_ids = self.env['mail.activity']
		model_ids = self.env['ir.model'].search([('model','=','petty.cash.expense')])
		ids = self.finance_approved_id.user_id
		date = self.date_requested
		name = self.voucher_no
		dd = self.ids
		cc = ''
		for d in dd:
			cc += str(d)
		cc = int(cc)
		# print('........................................... id ',str(dd),' and cc ',cc)
		mail_s = mail_ids.search([('res_model','=','petty.cash.expense'),('res_id','=',cc)])
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
		self.write({'state': 'manager_validate'})

	def validate(self):
		if not self.date_received:
			raise ValidationError(_('Please Set Date Received before approve'))
		for expense in self:
			payment_obj = self.env['account.payment']
			ids = payment_obj.id + 1
			sequence_code = 'account.payment.transfer'
			post = payment_obj.post()
			print('................ IDS ',ids,' id ',self.id)
			payment_value = {
				'petty_cash_id': self.id,
				'payment_type': 'transfer',
				'internal_transfer_type': 'journal_to_journal',
				'company_id': expense.company_id.id,
				'amount': expense.amount,
				'payment_date': expense.date_received,
				'communication': expense.name,
				'journal_id': expense.payment_journal_id.id,
				'destination_journal_id': expense.request_journal_id.id,
				'approve_person_id': expense.approved_by_id.id,
				'payment_method_id': ids,
				# 'state': post,
				'name': self.env['ir.sequence'].next_by_code(sequence_code, sequence_date=payment_obj.payment_date),
			}
			aa = payment_obj.create(payment_value)
			aa.post()
		mail_ids = self.env['mail.activity']
		model_ids = self.env['ir.model'].search([('model','=','petty.cash.expense')])
		ids = self.env['hr.employee'].search([('is_gm','=',True)])
		# ids = self.finance_approved_id.user_id
		date = self.date_requested
		name = self.voucher_no
		dd = self.ids
		cc = ''
		for d in dd:
			cc += str(d)
		cc = int(cc)
		# print('........................................... id ',str(dd),' and cc ',cc)
		mail_s = mail_ids.search([('res_model','=','petty.cash.expense'),('res_id','=',cc)])
		# print('>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<< +++++++++++++++  ',mail_s)
		mail_s.unlink()
		value = {
				'activity_type_id': 4,
				'date_deadline': date,
				'user_id': ids.user_id.id,
				'res_model_id': model_ids.id,
				'res_name': name,
				'res_id': cc,
		}
		mail_ids.create(value)
		return self.write({'state': 'validate'})
		
	def gm_approve(self):
		mail_ids = self.env['mail.activity']
		dd = self.ids
		cc = ''
		for d in dd:
			cc += str(d)
		cc = int(cc)
		mail_s = mail_ids.search([('res_model','=','petty.cash.expense'),('res_id','=',cc)])
		# print('>>>>>>>>>>>>>>>>><<<<<<<<<<<<<<<<<<<<<< +++++++++++++++  ',mail_s)
		mail_s.unlink()
		return self.write({'state': 'gm_approve'})

	def refuse(self):
		self.write({'state': 'refuse'})

	def cancel(self):
		self.write({'state': 'cancel'})

	def get_sequence(self):
	  return self.env['ir.sequence'].next_by_code('petty.cash.expense')

	def get_approve(self):
		for approve in self:
			reason = False
			finance = False
			to_approve_id = self.env.uid
			if to_approve_id == approve.approved_by_id.user_id.id:
				reason = True
			if to_approve_id == approve.finance_approved_id.user_id.id:
				finance = True
			approve.is_approve = reason
			approve.is_approve_finance = finance

	@api.model
	def create(self, data):
		data['name'] = self.get_sequence()
		record_id = super(PettyCashExpense, self).create(data)
		return record_id


class PettyCashApprove(models.Model):
	_name = 'petty.cash.approve'

	petty_request = fields.Many2one('petty.cash.expense',string='Petty Request ID', required=True)
	payment_journal_id = fields.Many2one('account.journal',string="Payment Journal")

	def approve(self):
		tbl_petty_obj = self.env['petty.cash.expense']
		journal_id = self.payment_journal_id
		pc_id = tbl_petty_obj.search([('id','=',self.petty_request.id),('payment_journal_id','=',journal_id.id)])
		if journal_id.id == pc_id.payment_journal_id.id:
			# pc_value = {'state': 'validate'}
			# pc_id.write(pc_value)
			self.petty_request.validate() 
		else:
			raise ValidationError(_('You cannot use this general account in this journal, check the tab Entry Controls on the related journal.'))

class AccountMoveLine(models.Model):
	_inherit = 'account.move.line'

	petty_cash_id = fields.Many2one('petty.cash.expense',string='Petty Cash')

class AccountPayment(models.Model):
	_inherit = 'account.payment'

	sequence = fields.Char('Sequence Code',required=True)
	state = fields.Selection([('draft', 'Draft'), ('posted', 'Post'), ('sent', 'Sent'), ('reconciled', 'Reconciled'), ('cancelled', 'Cancelled')], readonly=True, default='draft', copy=False, string="Status")

	def cancel(self):
		self.write({'state': 'cancelled'})

	# def post(self):
	# 	""" Create the journal items for the payment and update the payment's state to 'posted'.
	# 		A journal entry is created containing an item in the source liquidity account (selected journal's default_debit or default_credit)
	# 		and another in the destination reconcilable account (see _compute_destination_account_id).
	# 		If invoice_ids is not empty, there will be one reconcilable move line per invoice to reconcile with.
	# 		If the payment is a transfer, a second journal entry is created in the destination journal to receive money from the transfer account.
	# 	"""
	# 	AccountMove = self.env['account.move'].with_context(default_type='entry')
	# 	year = datetime.strptime(str(self.payment_date),'%Y-%m-%d').strftime('%Y')
	# 	month = datetime.strptime(str(self.payment_date),'%Y-%m-%d').strftime('%m')
	# 	today_year = datetime.now().year
	# 	today_month = datetime.now().month
	# 	date_start = datetime(int(year), int(month), 1)
	# 	sequence = self.sequence

	# 	if int(month)==12:
	# 		month = 1
	# 		year = int(year)+1
	# 		date_end = datetime(int(year), int(month), 1)
	# 	else:
	# 		date_end = datetime(int(year), int(month)+1, 1)
			
	# 	payment_id=self.env['account.payment'].search([('name','!=',None), ('payment_date','>=',date_start),('payment_date','<=',date_end)],order="name desc",limit=1)

	# 	for rec in self:

	# 		if rec.state != 'draft':
	# 			raise UserError(_("Only a draft payment can be posted."))

	# 		if any(inv.state != 'posted' for inv in rec.invoice_ids):
	# 			raise ValidationError(_("The payment cannot be processed because the invoice is not open!"))

	# 		# keep the name in case of a payment reset to draft
	# 		if not rec.name:
	# 			# Use the right sequence to set the name
	# 			if payment_id:
	# 				print (payment_id.name,'why UserError')
	# 				code=str(payment_id.name)
	# 				if code.split('/')[2]:
	# 					digit=code.split('/')[2]
	# 				else:
	# 					digit=code.split('/')[2]
	# 				name = '%04d' % (int(digit)+1,)
	# 				rec.name = str(sequence) + '/' + str(year) + str(name)
	# 			else:
	# 				rec.name = str(sequence) + '/' + str(year) + '0001'
	# 			# if rec.payment_type == 'transfer':
	# 			# 	sequence_code = 'account.payment.transfer'
	# 			# else:
	# 			# 	if rec.partner_type == 'customer':
	# 			# 		if rec.payment_type == 'inbound':
	# 			# 			sequence_code = 'account.payment.customer.invoice'
	# 			# 		if rec.payment_type == 'outbound':
	# 			# 			sequence_code = 'account.payment.customer.refund'
	# 			# 	if rec.partner_type == 'supplier':
	# 			# 		if rec.payment_type == 'inbound':
	# 			# 			sequence_code = 'account.payment.supplier.refund'
	# 			# 		if rec.payment_type == 'outbound':
	# 			# 			sequence_code = 'account.payment.supplier.invoice'

	# 			# seq = 'account.payment'
	# 			# rec.name = self.env['ir.sequence'].next_by_code(seq, sequence_date=rec.payment_date)
	# 			# if not rec.name and rec.payment_type != 'transfer':
	# 			# 	raise UserError(_("You have to define a sequence for %s in your company.") % (sequence_code,))

	# 		moves = AccountMove.create(rec._prepare_payment_moves())
	# 		moves.filtered(lambda move: move.journal_id.post_at != 'bank_rec').post()

	# 		# Update the state / move before performing any reconciliation.
	# 		move_name = self._get_move_name_transfer_separator().join(moves.mapped('name'))
	# 		rec.write({'state': 'posted', 'move_name': move_name})

	# 		if rec.payment_type in ('inbound', 'outbound'):
	# 			# ==== 'inbound' / 'outbound' ====
	# 			if rec.invoice_ids:
	# 				(moves[0] + rec.invoice_ids).line_ids \
	# 					.filtered(lambda line: not line.reconciled and line.account_id == rec.destination_account_id and not (line.account_id == line.payment_id.writeoff_account_id and line.name == line.payment_id.writeoff_label))\
	# 					.reconcile()
	# 		elif rec.payment_type == 'transfer':
	# 			# ==== 'transfer' ====
	# 			moves.mapped('line_ids')\
	# 				.filtered(lambda line: line.account_id == rec.company_id.transfer_account_id)\
	# 				.reconcile()

	# 	return True