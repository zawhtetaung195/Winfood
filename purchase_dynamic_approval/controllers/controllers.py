# -*- coding: utf-8 -*-
# from odoo import http


# class PurchaseDynamicApproval(http.Controller):
#     @http.route('/purchase_dynamic_approval/purchase_dynamic_approval/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/purchase_dynamic_approval/purchase_dynamic_approval/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('purchase_dynamic_approval.listing', {
#             'root': '/purchase_dynamic_approval/purchase_dynamic_approval',
#             'objects': http.request.env['purchase_dynamic_approval.purchase_dynamic_approval'].search([]),
#         })

#     @http.route('/purchase_dynamic_approval/purchase_dynamic_approval/objects/<model("purchase_dynamic_approval.purchase_dynamic_approval"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('purchase_dynamic_approval.object', {
#             'object': obj
#         })
