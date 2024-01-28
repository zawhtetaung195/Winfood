from odoo import fields, api, models, _
from random import randint
from odoo.exceptions import UserError,ValidationError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    city_id = fields.Many2one('res.city', string="City")
    township_id = fields.Many2one('res.township', string="TownShip", domain="[('city_id', '=', city_id)]")
    phone = fields.Char(required=True)
    gene_password = fields.Char(string="Password", readonly=True)
    barcode = fields.Char("Reference")

    @api.model
    def create(self, vals):
        name = vals.get('name')
        phone = vals.get('phone')
        # menu_id = self._context.get('params').get('menu_id') if self._context.get('params') else None
        result = super(ResPartner, self).create(vals)
        partner_mode = self.env.context.get('res_partner_search_mode')
        if partner_mode:
            sequence = self.env['ir.sequence'].search([('code','=',partner_mode)])
            if not sequence:
                raise ValidationError('Sequence cannot be found.')
            code = sequence.next_by_code(partner_mode)
            result.write({'barcode':code})
        if self._context.get('default_customer_rank') and phone:
            gene_password = randint(10 ** (6 - 1), (10 ** 6) - 1)
            result.write({'gene_password': gene_password})
            self.env['res.users'].create({
                'name': name,
                'login': phone,
                'password': str(gene_password),
                'partner_id': result.id,
                'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
            })                
        else:
            pass
        return result
   
    def _display_address(self, without_company=False):

        '''
        The purpose of this function is to build and return an address formatted accordingly to the
        standards of the country where it belongs.

        :param address: browse record of the res.partner to format
        :returns: the address formatted in a display that fit its country habits (or the default ones
            if not country is specified)
        :rtype: string
        '''
        # get the information that will be injected into the display format
        # get the address format
        address_format = self._get_address_format()
        address_format = "%(street)s %(street2)s %(township_name)s %(city_id)s %(country_name)s"
        
        args = {
            'state_code': self.state_id.code or '',
            'state_name': self.state_id.name or '',
            'city_id': self.city_id.name or '',
            'township_name': self.township_id.name or '',
            'country_code': self.country_id.code or '',
            'country_name': self._get_country_name(),
            'company_name': self.commercial_company_name or '',
        }
        for field in self._formatting_address_fields():
            args[field] = getattr(self, field) or ''
        if without_company:
            args['company_name'] = ''
        elif self.commercial_company_name:
            address_format = '%(company_name)s\n' + address_format
        result = address_format % args
        return result


class City(models.Model):
    _name = 'res.city'
    _description = "City Name"
    name = fields.Char(string="City", required=True)
    state_id = fields.Many2one('res.country.state', string='State')

class TownShip(models.Model):
    _name = 'res.township'
    _description = "TownShip Name"
    name = fields.Char(string="TownShip", required=True)
    city_id = fields.Many2one('res.city', string="City", required=True)

