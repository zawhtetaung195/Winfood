# -*- coding: utf-8 -*-
{
    'name': "Manufacturing Extension",

    'summary': """
        Inventory Customize Module""",

    'description': """
        Long description of module's purpose
    """,

    'author': "UMG",
    'website': "http://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Manufacturing',
    'version': '1.0.0',

    # any module necessary for this one to work correctly
    'depends': ['mrp'],

    # always loaded
    'data': [
        'data/new_decimal_precision.xml',
        # 'security/ir.model.access.csv',
        # 'views/stock_picking_view.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}