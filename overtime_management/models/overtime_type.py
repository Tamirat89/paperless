from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class OvertimeType(models.Model):
    _name = 'overtime.type'
    _description = 'Overtime Type'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _sql_constraints = [
        ('name_company_unique', 'UNIQUE(name, company_id)', 'This overtime type already exists for this company!')
    ]

    name = fields.Selection([
        ('regular', 'Regular'),
        ('sunday', 'Sunday'),
        ('night', 'Night'),
        ('holiday', 'Holiday'), 
        ('other', 'Other'),
    ], required=True, tracking=True, default='regular')
    multiplier = fields.Float(string="Multiplier", required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', 
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        index=True,
        tracking=True,
        readonly=True
    )
    active = fields.Boolean(default=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='State', default='draft', tracking=True)
    
    def action_approve(self):
        self.state = 'approved'
    
    def action_reject(self):
        self.state = 'rejected'
    
    def action_reset(self):
        self.state = 'draft'

    @api.constrains('name', 'company_id', 'state')
    def _check_unique_approved_type(self):
        for record in self:
            if record.state == 'approved':
                duplicate = self.search([
                    ('id', '!=', record.id),
                    ('name', '=', record.name),
                    ('company_id', '=', record.company_id.id),
                    ('state', '=', 'approved'),
                ])
                if duplicate:
                    raise ValidationError(_(
                        'An approved overtime type "%(name)s" already exists for company "%(company)s".',
                        name=record.name,
                        company=record.company_id.name
                    ))
    


