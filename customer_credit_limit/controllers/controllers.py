# -*- coding: utf-8 -*-
# from odoo import http


# class CustomerCreditLimit(http.Controller):
#     @http.route('/customer_credit_limit/customer_credit_limit', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/customer_credit_limit/customer_credit_limit/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('customer_credit_limit.listing', {
#             'root': '/customer_credit_limit/customer_credit_limit',
#             'objects': http.request.env['customer_credit_limit.customer_credit_limit'].search([]),
#         })

#     @http.route('/customer_credit_limit/customer_credit_limit/objects/<model("customer_credit_limit.customer_credit_limit"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('customer_credit_limit.object', {
#             'object': obj
#         })
