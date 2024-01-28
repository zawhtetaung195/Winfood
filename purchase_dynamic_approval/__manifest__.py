# -*- coding: utf-8 -*-
{
    'name': "Purchase Dynamic Approval",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Long description of module's purpose
    """,

    'author': 'UMG',
    'website': "",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','purchase', 'purchase_enterprise', 'hr'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/hr_department.xml',
        'views/purchase_order_approval.xml',
        'views/approve_acknowledge_view.xml',
        'views/purchase_order.xml',
        'views/warning.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
