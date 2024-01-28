# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Sale Order Extension',
    'version': '1.0.0',
    'author': 'UMG',
    'category': 'Sale',
    'sequence': 60,
    'summary': 'Sale Extension',
    'description': "",
    'depends': ['sale'],
    'data': [
        'views/partner_view.xml',
        'views/sale_order_view.xml'
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
