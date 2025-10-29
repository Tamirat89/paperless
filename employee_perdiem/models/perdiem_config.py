# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PerdiemConfig(models.Model):
    _name = 'perdiem.config'
    _description = 'Per Diem Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(
        string='Configuration Name',
        required=True,
        tracking=True
    )
    daily_rate = fields.Float(
        string='Daily Per Diem Rate',
        required=True,
        tracking=True,
        help='Fixed amount per day for per diem calculation'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    _sql_constraints = [
        ('positive_daily_rate', 'CHECK(daily_rate > 0)', 'Daily rate must be positive!'),
    ]

    @api.constrains('daily_rate')
    def _check_daily_rate(self):
        for record in self:
            if record.daily_rate <= 0:
                raise ValidationError(_('Daily per diem rate must be greater than zero.'))
