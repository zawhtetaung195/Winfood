# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Purchase Order Extension',
    'version': '1.0.0',
    'author': 'UMG',
    'category': 'Purchase',
    'sequence': 60,
    'summary': 'Sale Extension',
    'description': "",
    'depends': ['purchase'],
    'data': [
        'views/purchase_view.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
