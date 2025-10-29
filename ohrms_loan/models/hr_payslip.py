# -*- coding: utf-8 -*-
#############################################################################
#    A part of Open HRMS Project <https://www.openhrms.com>
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2023-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
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
from odoo import models


class HrPayslip(models.Model):
    """ Extends the 'hr.payslip' model to include
    additional functionality related to employee loans."""
    _inherit = 'hr.payslip'

    def action_payslip_done(self):
        """ Mark loan lines as paid when payslip is confirmed"""
        result = super(HrPayslip, self).action_payslip_done()
        
        # Mark loan lines as paid for this payroll period
        for payslip in self:
            if payslip.employee_id and payslip.contract_id:
                # Find approved loans for this employee
                loans = self.env['hr.loan'].search([
                    ('employee_id', '=', payslip.employee_id.id),
                    ('state', '=', 'approve'),
                    ('company_id', 'in', self.env.companies.ids),
                ])
                
                for loan in loans:
                    # Find loan lines within the payroll period that are not yet paid
                    loan_lines = loan.loan_lines.filtered(
                        lambda line: (
                            payslip.date_from <= line.date <= payslip.date_to and 
                            not line.paid
                        )
                    )
                    # Mark them as paid
                    loan_lines.write({'paid': True})
                    # Recompute loan totals
                    loan._compute_total_amount()
        
        return result
