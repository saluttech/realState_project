from odoo import fields, models, api

class PropertyPayment(models.TransientModel):
    _name = 'property.payment.wizard'
    _description = 'Create Invoice For Rent'

    tenancy_id = fields.Many2one('tenancy.details', string='Tenancy No.')
    customer_id = fields.Many2one(related='tenancy_id.tenancy_id', string='Customer')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', string='Currency')
    type = fields.Selection([
        ('deposit', 'Deposit'),
        ('utility', 'Utility'),
        ('maintenance', 'Maintenance'),
        ('penalty', 'Penalty'),
        ('other', 'Other')
    ], string='Payment For')
    description = fields.Char(string='Description', translate=True)
    invoice_date = fields.Date(string='Date', default=fields.Date.today())
    rent_amount = fields.Monetary(string='Rent Amount', related='tenancy_id.total_rent')
    rent_invoice_id = fields.Many2one('account.move', string='Invoice')
    
    invoice_line_ids = fields.One2many('property.payment.wizard.line', 'wizard_id', string='Invoice Lines')
    total_amount = fields.Monetary(string='Total Amount', compute='_compute_total_amount', currency_field='currency_id')

    @api.depends('invoice_line_ids.amount')
    def _compute_total_amount(self):
        for wizard in self:
            wizard.total_amount = sum(wizard.invoice_line_ids.mapped('amount'))

    @api.model
    def default_get(self, fields):
        res = super(PropertyPayment, self).default_get(fields)
        active_id = self._context.get('active_id')
        res['tenancy_id'] = active_id
        return res

    def property_payment_action(self):
        invoice_post_type = self.env['ir.config_parameter'].sudo().get_param('rental_management.invoice_post_type')
        
        invoice_lines = []
        for line in self.invoice_line_ids:
            invoice_lines.append((0, 0, {
                'product_id': line.service_id.id,
                'name': line.description,
                'quantity': line.quantity,
                'price_unit': line.cost,
                'tax_ids': line.tax_ids.ids
            }))
        
        data = {
            'partner_id': self.customer_id.id,
            'move_type': 'out_invoice',
            'tenancy_id': self.tenancy_id.id,
            'invoice_date': self.invoice_date,
            'invoice_line_ids': invoice_lines
        }
        
        invoice_id = self.env['account.move'].sudo().create(data)
        
        if invoice_post_type == 'automatically':
            invoice_id.action_post()
        
        for line in self.invoice_line_ids:
            if line.is_storable:
                stock_quant = self.env['stock.quant'].sudo().search([
                    ('product_id', '=', line.service_id.id),
                    ('location_id.usage', '=', 'internal')
                ], limit=1)
                
                if stock_quant:
                    stock_quant.quantity -= line.quantity
            
            self.env['rent.invoice'].create({
                'tenancy_id': self.tenancy_id.id,
                'type': self.type,
                'invoice_date': self.invoice_date,
                'amount': line.amount,
                'description': line.description,
                'rent_invoice_id': invoice_id.id,
            })

class PropertyPaymentWizardLine(models.TransientModel):
    _name = 'property.payment.wizard.line'
    _description = 'Property Payment Wizard Line'

    wizard_id = fields.Many2one('property.payment.wizard', string='Wizard')
    service_id = fields.Many2one('product.product', string="Service", required=True)
    description = fields.Char(string='Description', required=True)
    quantity = fields.Float(string='Quantity', compute='_compute_quantity', store=True)
    cost = fields.Monetary(string='Cost', currency_field='currency_id', required=True)
    tax_ids = fields.Many2many('account.tax', string="Taxes")
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    amount = fields.Monetary(string='Amount', compute='_compute_amount', store=True, currency_field='currency_id')
    is_storable = fields.Boolean(string='Is Storable', compute='_compute_is_storable')
    on_hand_quantity = fields.Float(string='On Hand Quantity', compute='_compute_on_hand_quantity')
    initial_meter_reading = fields.Float(string='Initial Meter Reading')
    final_meter_reading = fields.Float(string='Final Meter Reading')

    @api.depends('service_id')
    def _compute_is_storable(self):
        for record in self:
            record.is_storable = record.service_id.type == 'product'

    @api.depends('service_id')
    def _compute_on_hand_quantity(self):
        for record in self:
            if record.is_storable:
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', record.service_id.id),
                    ('location_id.usage', '=', 'internal')
                ])
                record.on_hand_quantity = sum(quants.mapped('quantity'))
            else:
                record.on_hand_quantity = 0.0

    @api.depends('initial_meter_reading', 'final_meter_reading', 'wizard_id.type')
    def _compute_quantity(self):
        for record in self:
            if record.wizard_id.type == 'utility':
                record.quantity = record.final_meter_reading - record.initial_meter_reading
            else:
                record.quantity = 1.0

    @api.depends('quantity', 'cost')
    def _compute_amount(self):
        for record in self:
            record.amount = record.quantity * record.cost

    @api.onchange('service_id')
    def _onchange_service_id(self):
        if self.service_id:
            self.cost = self.service_id.standard_price
            self.tax_ids = self.service_id.taxes_id.filtered(lambda tax: tax.company_id == self.wizard_id.company_id)
            self.description = self.service_id.name