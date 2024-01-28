{
	'name': 'Petty Cash Expenses',
	'version': '2.0.4',
	'category': 'Expense',
	'summary': "Petty Cash expenses by Myat Min Hein(M2h)",
	'author': 'UMG',
	'description': """

Advanced Expenses
======================================================
- Manage advanced payment and expenses
	used by employee
""",
	'depends': ['base',
				'hr_expense',
				'account',
				'mail',
				'hr'
				],
	'data': [
		'data/ir_sequence_data.xml',
		'security/security.xml',
		'security/account_security.xml',
		'security/ir.model.access.csv',
		'views/petty_cash_expense_view.xml',
		# 'views/payment_voucher_view.xml',
		# 'views/hr_expense_view.xml',
		'views/res_company_view.xml',
		'views/expense_view.xml',
		'views/hr_expense_prepaid_view.xml',
		'views/account_transfer_view.xml',
		'views/account_move_view.xml',
		'views/advance_claim_view.xml',
		'views/hr_employee_view.xml'
	],
	'demo': [
	],
	'images': [],
	'application': True,
	'installable': True,
	'auto_install': False,
}
