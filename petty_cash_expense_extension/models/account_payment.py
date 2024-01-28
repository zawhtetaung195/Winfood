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
from odoo.tools import float_is_zero, float_compare, safe_eval, date_utils, email_split, email_escape_char, email_re
from odoo.tools.misc import formatLang, format_date, get_lang


class AccountPayment(models.Model):
	_inherit = 'account.payment'

	payment_type = fields.Selection([
		('outbound', 'Send Money'), ('inbound', 'Receive Money'), 
		('transfer', 'Internal Transfer'), ('br_bu', 'BR to BU Transfer')], string='Payment Type', required=True, readonly=True, states={'draft': [('readonly', False)]})
	# transfer_journal_id = fields.Many2one('account.journal',string="Transfer To", required=True)
	approve_person_id = fields.Many2one('hr.employee',string='Approval Person')
	company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id)
	internal_transfer_type = fields.Selection([
		('journal_to_journal', 'Journal to Journal'), ('journal_to_account', 'Journal to Account'), 
		('account_to_journal', 'Account to Journal')], string='Internal Transfer Type')
	petty_cash_id = fields.Many2one('petty.cash.expense',stirng='Petty Cash')

	def post(self):
		""" Create the journal items for the payment and update the payment's state to 'posted'.
			A journal entry is created containing an item in the source liquidity account (selected journal's default_debit or default_credit)
			and another in the destination reconcilable account (see _compute_destination_account_id).
			If invoice_ids is not empty, there will be one reconcilable move line per invoice to reconcile with.
			If the payment is a transfer, a second journal entry is created in the destination journal to receive money from the transfer account.
		"""
		AccountMove = self.env['account.move'].with_context(default_type='entry')
		for rec in self:

			if rec.state != 'draft':
				raise UserError(_("Only a draft payment can be posted."))

			if any(inv.state != 'posted' for inv in rec.invoice_ids):
				raise ValidationError(_("The payment cannot be processed because the invoice is not open!"))

			# keep the name in case of a payment reset to draft
			if not rec.name:
				# Use the right sequence to set the name
				if rec.payment_type == 'transfer':
					sequence_code = 'account.payment.transfer'
				else:
					if rec.partner_type == 'customer':
						if rec.payment_type == 'inbound':
							sequence_code = 'account.payment.customer.invoice'
						if rec.payment_type == 'outbound':
							sequence_code = 'account.payment.customer.refund'
					if rec.partner_type == 'supplier':
						if rec.payment_type == 'inbound':
							sequence_code = 'account.payment.supplier.refund'
						if rec.payment_type == 'outbound':
							sequence_code = 'account.payment.supplier.invoice'
				# rec.name = self.env['ir.sequence'].next_by_code(sequence_code, sequence_date=rec.payment_date)
				seq = self.env['ir.sequence'].next_by_code('account.payment')
				seq_code = self.sequence
				rec.name = str(seq_code)+seq
				if not rec.name and rec.payment_type != 'transfer':
					raise UserError(_("You have to define a sequence for %s in your company.") % (sequence_code,))

			moves = AccountMove.create(rec._prepare_payment_moves())
			moves.filtered(lambda move: move.journal_id.post_at != 'bank_rec').post()

			# Update the state / move before performing any reconciliation.
			move_name = self._get_move_name_transfer_separator().join(moves.mapped('name'))
			rec.write({'state': 'posted', 'move_name': move_name})

			if rec.payment_type in ('inbound', 'outbound'):
				# ==== 'inbound' / 'outbound' ====
				if rec.invoice_ids:
					(moves[0] + rec.invoice_ids).line_ids \
						.filtered(lambda line: not line.reconciled and line.account_id == rec.destination_account_id and not (line.account_id == line.payment_id.writeoff_account_id and line.name == line.payment_id.writeoff_label))\
						.reconcile()
			elif rec.payment_type == 'transfer':
				# ==== 'transfer' ====
				moves.mapped('line_ids')\
					.filtered(lambda line: line.account_id == rec.company_id.transfer_account_id)\
					.reconcile()

class AccountMove(models.Model):
	_inherit = 'account.move'
	_order = 'create_no asc'

	create_no = fields.Char('Create ID',store=True)

	def post(self):
		# for move in self:
		# 	move.create_no += 1
		# 	print('.......................... Create No = ',move.create_no)
		# 	move.write(move.create_no)
		# `user_has_group` won't be bypassed by `sudo()` since it doesn't change the user anymore.
		if not self.env.su and not self.env.user.has_group('account.group_account_invoice'):
			raise AccessError(_("You don't have the access rights to post an invoice."))
		for move in self:
			if not move.line_ids.filtered(lambda line: not line.display_type):
				raise UserError(_('You need to add a line before posting.'))
			if move.auto_post and move.date > fields.Date.today():
				date_msg = move.date.strftime(get_lang(self.env).date_format)
				raise UserError(_("This move is configured to be auto-posted on %s" % date_msg))

			if not move.partner_id:
				if move.is_sale_document():
					raise UserError(_("The field 'Customer' is required, please complete it to validate the Customer Invoice."))
				elif move.is_purchase_document():
					raise UserError(_("The field 'Vendor' is required, please complete it to validate the Vendor Bill."))

			if move.is_invoice(include_receipts=True) and float_compare(move.amount_total, 0.0, precision_rounding=move.currency_id.rounding) < 0:
				raise UserError(_("You cannot validate an invoice with a negative total amount. You should create a credit note instead. Use the action menu to transform it into a credit note or refund."))

			# Handle case when the invoice_date is not set. In that case, the invoice_date is set at today and then,
			# lines are recomputed accordingly.
			# /!\ 'check_move_validity' must be there since the dynamic lines will be recomputed outside the 'onchange'
			# environment.
			if not move.invoice_date and move.is_invoice(include_receipts=True):
				move.invoice_date = fields.Date.context_today(self)
				move.with_context(check_move_validity=False)._onchange_invoice_date()

			# When the accounting date is prior to the tax lock date, move it automatically to the next available date.
			# /!\ 'check_move_validity' must be there since the dynamic lines will be recomputed outside the 'onchange'
			# environment.
			if (move.company_id.tax_lock_date and move.date <= move.company_id.tax_lock_date) and (move.line_ids.tax_ids or move.line_ids.tag_ids):
				move.date = move.company_id.tax_lock_date + timedelta(days=1)
				move.with_context(check_move_validity=False)._onchange_currency()

		# Create the analytic lines in batch is faster as it leads to less cache invalidation.
		self.mapped('line_ids').create_analytic_lines()
		for move in self:
			if move.auto_post and move.date > fields.Date.today():
				raise UserError(_("This move is configured to be auto-posted on {}".format(move.date.strftime(get_lang(self.env).date_format))))

			move.message_subscribe([p.id for p in [move.partner_id] if p not in move.sudo().message_partner_ids])

			to_write = {'state': 'posted'}

			if move.name == '/':
				# Get the journal's sequence.
				sequence = move._get_sequence()
				if not sequence:
					raise UserError(_('Please define a sequence on your journal.'))

				# Consume a new number.

			# 11-01-2021 by M2h ************************************************
				
				# year = datetime.now().year
				# month = datetime.now().month
				# journal = self.journal_id.code
				# seq = self.env['ir.sequence'].next_by_code('account.move')
				# to_write['name'] = str(self.env.user.company_id.code)+'/'+str(journal)+'/'+str(year)+'/'+str(month)+seq
				# to_write['create_no'] = str('C')+seq
				to_write['name'] = sequence.with_context(ir_sequence_date=move.date).next_by_id()

			move.write(to_write)

			# Compute 'ref' for 'out_invoice'.
			if move.type == 'out_invoice' and not move.invoice_payment_ref:
				to_write = {
					'invoice_payment_ref': move._get_invoice_computed_reference(),
					'line_ids': []
				}
				for line in move.line_ids.filtered(lambda line: line.account_id.user_type_id.type in ('receivable', 'payable')):
					to_write['line_ids'].append((1, line.id, {'name': to_write['invoice_payment_ref']}))
				move.write(to_write)

			if move == move.company_id.account_opening_move_id and not move.company_id.account_bank_reconciliation_start:
				# For opening moves, we set the reconciliation date threshold
				# to the move's date if it wasn't already set (we don't want
				# to have to reconcile all the older payments -made before
				# installing Accounting- with bank statements)
				move.company_id.account_bank_reconciliation_start = move.date

		for move in self:
			if not move.partner_id: continue
			if move.type.startswith('out_'):
				move.partner_id._increase_rank('customer_rank')
			elif move.type.startswith('in_'):
				move.partner_id._increase_rank('supplier_rank')
			else:
				continue

		# Trigger action for paid invoices in amount is zero
		self.filtered(
			lambda m: m.is_invoice(include_receipts=True) and m.currency_id.is_zero(m.amount_total)
		).action_invoice_paid()

		# Force balance check since nothing prevents another module to create an incorrect entry.
		# This is performed at the very end to avoid flushing fields before the whole processing.
		self._check_balanced()
		return True

class ResCompany(models.Model):
	_name = 'res.company'
	_inherit = 'res.company'

	code = fields.Char('Code', required=True)

class AccountJournal(models.Model):
	_inherit = 'account.journal'

	def name_get(self):
		res = []
		for journal in self:
			currency = journal.currency_id or journal.company_id.currency_id
			name = "%s (%s)" % (journal.name, journal.code)
			res += [(journal.id, name)]
		return res