{
    'name': 'Winfood Contact',
    'author': 'UMG',
    'category': 'Contacts',
    'version': '1.1.0',
    'description': """Edit Contacts""",
    'summary': """Edit Contacts""",
    'depends': ['base', 'contacts', 'sale', 'account'],
    'license': 'LGPL-3',
    'data': [
        'security/ir.model.access.csv',
        'data/sale_order_rule.xml',
        'views/account_move.xml',
        'views/res_partner.xml',
        'views/sale_order.xml',
        'views/portal_view.xml',
        'data/sequence.xml',
    ],

}
