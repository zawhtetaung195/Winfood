# -*- coding: utf-8 -*-
# from odoo import http


# class MasterUnlock(http.Controller):
#     @http.route('/master_unlock/master_unlock', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/master_unlock/master_unlock/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('master_unlock.listing', {
#             'root': '/master_unlock/master_unlock',
#             'objects': http.request.env['master_unlock.master_unlock'].search([]),
#         })

#     @http.route('/master_unlock/master_unlock/objects/<model("master_unlock.master_unlock"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('master_unlock.object', {
#             'object': obj
#         })
