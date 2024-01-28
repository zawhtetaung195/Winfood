from odoo import http
from odoo.http import request


class PettyCash(http.Controller):
    @http.route('/petty_cash_expense_extension/kiosk_keepalive', auth='user', type='json', methods=['POST'])
    def kiosk_keepalive(self):
        return request.env['expense.prepaid'].browse(int(self.ids or 0))
        return {}