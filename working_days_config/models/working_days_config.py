# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class WorkingDaysConfig(models.Model):
    _name = 'working.days.config'
    _description = 'Working Days Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True, tracking=True)
    number_of_working_days = fields.Float(
        string='Number of Working Days',
        required=True,
        tracking=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved')
    ], string='Status', default='draft', tracking=True)

    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
        required=True,
        readonly=True
    )

    _sql_constraints = [
        ('unique_company_record', 'unique(company_id)', 'Only one record per company is allowed.')
    ]

    @api.constrains('number_of_working_days')
    def _check_working_days_range(self):
        for rec in self:
            if rec.number_of_working_days <= 0:
                raise ValidationError("Working days must be greater than 0.")
            if rec.number_of_working_days > 31:
                raise ValidationError("Working days cannot be more than 31.")

    def write(self, vals):
        for record in self:
            if record.state == 'approved' and not self.env.user.has_group('hr.group_hr_manager'):
                raise UserError(_("You cannot modify an approved record."))
            if record.state == 'approved' and not vals.get('state'):
                raise UserError(_("You cannot modify an approved record. Please reset to draft first."))
        return super(WorkingDaysConfig, self).write(vals)

    def action_approve(self):
        if not self.env.user.has_group('hr.group_hr_manager'):
            raise UserError(_("Only HR Managers can approve."))
        self.write({'state': 'approved'})

    def action_reset_draft(self):
        if not self.env.user.has_group('hr.group_hr_manager'):
            raise UserError(_("Only HR Managers can reset."))
        self.write({'state': 'draft'})
