# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class EmployeePerdiem(models.Model):
    _name = 'employee.perdiem'
    _description = 'Employee Per Diem Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'create_date desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True,
        readonly="state != 'draft'"
    )
    start_date = fields.Date(
        string='Start Date',
        required=True,
        tracking=True,
        readonly="state != 'draft'"
    )
    end_date = fields.Date(
        string='End Date',
        required=True,
        tracking=True,
        readonly="state != 'draft'"
    )
    perdiem_config_id = fields.Many2one(
        'perdiem.config',
        string='Per Diem Configuration',
        required=True,
        tracking=True,
        readonly="state != 'draft'",
        help='Select the per diem configuration to use for daily rates'
    )
    perdiem_value = fields.Float(
        string='Total Per Diem Value',
        compute='_compute_perdiem_value',
        store=True,
        tracking=True,
        readonly="state != 'draft'"
    )
    approved_by = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        tracking=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submitted'),
        ('reviewed', 'Reviewed'),
        ('approved', 'Approved')
    ], string='Status', default='draft', tracking=True)

    # Lines
    line_ids = fields.One2many(
        'employee.perdiem.line',
        'perdiem_id',
        string='Per Diem Lines',
        readonly="state == 'approved'"
    )

    # Computed fields
    total_days = fields.Integer(
        string='Total Days',
        compute='_compute_total_days',
        store=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('employee.perdiem') or _('New')
        return super(EmployeePerdiem, self).create(vals)

    @api.depends('line_ids')
    def _compute_total_days(self):
        for record in self:
            record.total_days = len(record.line_ids)

    @api.depends('line_ids.daily_value')
    def _compute_perdiem_value(self):
        for record in self:
            record.perdiem_value = sum(record.line_ids.mapped('daily_value'))

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for record in self:
            if record.start_date and record.end_date:
                if record.start_date > record.end_date:
                    raise ValidationError(_('Start date must be before end date.'))

    @api.onchange('perdiem_config_id')
    def _onchange_perdiem_config_id(self):
        """Update daily values in existing lines when configuration changes"""
        if self.perdiem_config_id and self.line_ids:
            for line in self.line_ids:
                line.write({'daily_value': self.perdiem_config_id.daily_rate})


    def action_submit(self):
        if not self.line_ids:
            raise UserError(_('Please add per diem lines before submitting.'))
        self.write({'state': 'submit'})

    def action_review(self):
        if not self.env.user.has_group('employee_perdiem.group_perdiem_manager'):
            raise UserError(_('Only Per Diem Managers can review requests.'))
        self.write({'state': 'reviewed'})

    def action_approve(self):
        if not self.env.user.has_group('employee_perdiem.group_perdiem_manager'):
            raise UserError(_('Only Per Diem Managers can approve requests.'))
        self.write({
            'state': 'approved',
            'approved_by': self.env.user.id
        })

    def action_reset_draft(self):
        if not self.env.user.has_group('employee_perdiem.group_perdiem_manager'):
            raise UserError(_('Only Per Diem Managers can reset to draft.'))
        self.write({
            'state': 'draft',
            'approved_by': False
        })


class EmployeePerdiemLine(models.Model):
    _name = 'employee.perdiem.line'
    _description = 'Employee Per Diem Line'
    _order = 'date'

    perdiem_id = fields.Many2one(
        'employee.perdiem',
        string='Per Diem Request',
        required=True,
        ondelete='cascade'
    )
    date = fields.Date(
        string='Date',
        required=True,
        readonly="perdiem_id.state != 'draft'"
    )
    daily_value = fields.Float(
        string='Daily Value',
        compute='_compute_daily_value',
        store=True,
        readonly=True
    )
    company_id = fields.Many2one(
        related='perdiem_id.company_id',
        store=True
    )

    @api.depends('perdiem_id.perdiem_config_id.daily_rate')
    def _compute_daily_value(self):
        """Compute daily value from selected configuration"""
        for line in self:
            if line.perdiem_id and line.perdiem_id.perdiem_config_id:
                line.daily_value = line.perdiem_id.perdiem_config_id.daily_rate
            else:
                line.daily_value = 0.0

    @api.constrains('date')
    def _check_date_range(self):
        for record in self:
            if record.perdiem_id.start_date and record.perdiem_id.end_date:
                if not (record.perdiem_id.start_date <= record.date <= record.perdiem_id.end_date):
                    raise ValidationError(_('Line date must be within the per diem request date range.'))
