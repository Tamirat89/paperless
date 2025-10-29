# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class LunchTimeConfiguration(models.Model):
    _name = 'lunch.time.configuration'
    _description = 'Lunch Time Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Configuration Name', required=True, tracking=True)
    lunch_start_time = fields.Float(
        string='Lunch Start Time',
        required=True,
        tracking=True,
        help='Lunch start time in 24-hour format (e.g., 12.0 for 12:00, 12.5 for 12:30)'
    )
    lunch_end_time = fields.Float(
        string='Lunch End Time',
        required=True,
        tracking=True,
        help='Lunch end time in 24-hour format (e.g., 13.0 for 13:00, 13.5 for 13:30)'
    )
    total_lunch_hours = fields.Float(
        string='Total Lunch Hours',
        compute='_compute_total_lunch_hours',
        store=True,
        readonly=True,
        tracking=True,
        help='Calculated as lunch_end_time - lunch_start_time'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        index=True,
        tracking=True,
        readonly=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='State', default='draft', tracking=True, required=True)
    
    is_active_config = fields.Boolean(
        string='Use in Calculation',
        default=True,
        tracking=True,
        help='If checked, this configuration will be used in overtime calculations. '
             'If unchecked, lunch hours will not be deducted even if configuration is approved.'
    )
    
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('company_unique', 'UNIQUE(company_id, state)', 
         'Only one approved lunch configuration is allowed per company!')
    ]

    @api.depends('lunch_start_time', 'lunch_end_time')
    def _compute_total_lunch_hours(self):
        for record in self:
            if record.lunch_start_time and record.lunch_end_time:
                record.total_lunch_hours = record.lunch_end_time - record.lunch_start_time
            else:
                record.total_lunch_hours = 0.0

    @api.constrains('lunch_start_time', 'lunch_end_time')
    def _check_lunch_times(self):
        for record in self:
            if record.lunch_start_time < 0 or record.lunch_start_time >= 24:
                raise ValidationError(_('Lunch start time must be between 0 and 24 hours.'))
            if record.lunch_end_time < 0 or record.lunch_end_time >= 24:
                raise ValidationError(_('Lunch end time must be between 0 and 24 hours.'))
            if record.lunch_end_time <= record.lunch_start_time:
                raise ValidationError(_('Lunch end time must be after lunch start time.'))

    @api.constrains('state', 'company_id')
    def _check_unique_approved_configuration(self):
        for record in self:
            if record.state == 'approved':
                # Check if another approved configuration exists for the same company
                duplicate = self.search([
                    ('id', '!=', record.id),
                    ('company_id', '=', record.company_id.id),
                    ('state', '=', 'approved'),
                ])
                if duplicate:
                    raise ValidationError(_(
                        'An approved lunch time configuration already exists for company "%(company)s". '
                        'Please reject or archive the existing configuration before approving a new one.',
                        company=record.company_id.name
                    ))

    def action_approve(self):
        """Approve the lunch time configuration"""
        for record in self:
            record.state = 'approved'

    def action_reject(self):
        """Reject the lunch time configuration"""
        for record in self:
            record.state = 'rejected'

    def action_reset_to_draft(self):
        """Reset to draft state"""
        for record in self:
            record.state = 'draft'

    def name_get(self):
        """Custom display name"""
        result = []
        for record in self:
            name = f"{record.name} ({record.company_id.name})"
            result.append((record.id, name))
        return result

