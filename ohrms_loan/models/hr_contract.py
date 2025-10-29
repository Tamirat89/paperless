# -*- coding: utf-8 -*-
#############################################################################
#    A part of Open HRMS Project <https://www.openhrms.com>
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

from odoo import models, fields, api


class HrContract(models.Model):
    _inherit = 'hr.contract'

    def get_loan_amount(self, date_from, date_to):
        """Calculate total loan deduction amount for payroll period"""
        self.ensure_one()
        
        # Search for approved loans for this employee
        loans = self.env['hr.loan'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'approve'),
            ('company_id', 'in', self.env.companies.ids),
        ])
        
        total_deduction = 0.0
        for loan in loans:
            # Find loan lines within the payroll period that are not yet paid
            loan_lines = loan.loan_lines.filtered(
                lambda line: (
                    date_from <= line.date <= date_to and 
                    not line.paid
                )
            )
            total_deduction += sum(loan_lines.mapped('amount'))
        
        return total_deduction
