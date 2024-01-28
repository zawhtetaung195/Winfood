from odoo import models

class PortalMixing(models.AbstractModel):
    _inherit = 'portal.mixin'

    def set_action_from_portal(self, suffix=None, report_type=None, download=None, query_string=None, anchor=None):
        self.ensure_one()
        order_id = int(self.access_url.replace("/my/orders/", ""))
        order = self.env['sale.order'].search([('id', '=', order_id)])
        # order.action_customerIfo()

    def account_action_from_portal(self, suffix=None, report_type=None, download=None, query_string=None, anchor=None):
        self.ensure_one()
        invoice_id = int(self.access_url.replace("/my/invoices/", ""))
        order = self.env['account.move'].search([('id', '=', invoice_id)])
        url = self.access_url +'/confirm' + '%s?access_token=%s%s%s' % (
            suffix if suffix else '',
            self._portal_ensure_token(),
            query_string if query_string else '',
            '#%s' % anchor if anchor else ''
        )
        return url
        # order.action_customerIfo()
    
    # set_action_confirm_from_portal
    def set_action_confirm_from_portal(self, suffix=None, report_type=None, download=None, query_string=None, anchor=None, confirm=None, type=None):
        self.ensure_one()
        access_url = self.access_url.replace('/my/orders','/my/quotes') if type in ['draft', 'sent'] else self.access_url
        url = access_url +'/confirm' + '%s?access_token=%s%s%s' % (
            suffix if suffix else '',
            self._portal_ensure_token(),
            query_string if query_string else '',
            '#%s' % anchor if anchor else ''
        )
        return url

    def get_portal_quotation_url(self, suffix=None, report_type=None, download=None, query_string=None, anchor=None, type=None):
        """
            Get a portal url for this model, including access_token.
            The associated route must handle the flags for them to have any effect.
            - suffix: string to append to the url, before the query string
            - report_type: report_type query string, often one of: html, pdf, text
            - download: set the download query string to true
            - query_string: additional query string
            - anchor: string to append after the anchor #
        """
        self.ensure_one()
        url = self.access_url.replace('/my/orders','/my/quotes') + '%s?access_token=%s%s%s%s%s' % (
            suffix if suffix else '',
            self._portal_ensure_token(),
            '&report_type=%s' % report_type if report_type else '',
            '&download=true' if download else '',
            query_string if query_string else '',
            '#%s' % anchor if anchor else ''
        )
        return url