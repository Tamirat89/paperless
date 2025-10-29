# -*- coding: utf-8 -*-

from odoo import models, fields, api


class HrContract(models.Model):
    _inherit = 'hr.contract'

    def get_perdiem_amount(self, date_from, date_to):
        """Calculate total per diem amount for payroll period"""
        self.ensure_one()
        
        # Search for approved per diem requests within the payroll period
        perdiem_requests = self.env['employee.perdiem'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'approved'),
            ('company_id', 'in', self.env.companies.ids),
            # Check if per diem dates overlap with payroll period
            '|',
            '&', ('start_date', '>=', date_from), ('start_date', '<=', date_to),
            '&', ('end_date', '>=', date_from), ('end_date', '<=', date_to),
        ])
        
        # Return total per diem value
        return sum(perdiem_requests.mapped('perdiem_value'))
