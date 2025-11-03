# -*- coding: utf-8 -*-

from odoo import models, fields
from odoo.exceptions import UserError
import io
import xlsxwriter
import base64
from datetime import datetime

class PayrollExcelWizard(models.TransientModel):
    _name = 'payroll.excel.wizard'
    _description = 'Payroll Excel Report Generator'

    batch_id = fields.Many2one('hr.payslip.run', string='Payroll Batch', required=True)

    def action_generate_excel(self):
        """Generate Excel file with payroll data"""
        self.ensure_one()
        
        if not self.batch_id.slip_ids:
            raise UserError("This batch has no payslips!")

        # Create Excel
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        sheet = workbook.add_worksheet('Payroll Report')

        # Get company info
        company = self.env.company
        batch = self.batch_id
        
        # Formats
        title_fmt = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'align': 'center',
            'valign': 'vcenter',
        })
        
        info_fmt = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'align': 'center',
            'valign': 'vcenter',
        })
        
        hdr = workbook.add_format({
            'bold': True,
            'bg_color': '#D3D3D3',
            'border': 1,
            'border_color': '#000000',
            'align': 'center',
            'valign': 'vcenter'
        })
        
        cell = workbook.add_format({
            'border': 1,
            'align': 'left',
            'valign': 'vcenter'
        })
        
        num = workbook.add_format({
            'border': 1,
            'align': 'right',
            'valign': 'vcenter',
            'num_format': '#,##0.00'
        })
        
        total_label_fmt = workbook.add_format({
            'bold': True,
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#FFFF99'
        })
        
        total_fmt = workbook.add_format({
            'bold': True,
            'border': 1,
            'align': 'right',
            'valign': 'vcenter',
            'num_format': '#,##0.00',
            'bg_color': '#FFFF99'
        })

        # Widths
        sheet.set_column('A:A', 6)
        sheet.set_column('B:B', 25)
        sheet.set_column('C:C', 15)
        sheet.set_column('D:D', 20)
        sheet.set_column('E:Q', 13)

        # Title (row 0)
        sheet.merge_range('A1:Q1', f'{company.name}', title_fmt)
        
        # Batch info (row 1)
        sheet.merge_range('A2:Q2', f'Payroll Report - {batch.name}', info_fmt)
        
        # Date range (row 2)
        date_from = batch.date_start.strftime('%d/%m/%Y') if batch.date_start else ''
        date_to = batch.date_end.strftime('%d/%m/%Y') if batch.date_end else ''
        sheet.merge_range('A3:Q3', f'Period: {date_from} - {date_to}', info_fmt)
        
        # Column Headers (row 4)
        cols = ['No', 'Employee', 'ID', 'Bank Account', 'Days', 'Basic Salary', 'Earning Salary', 
                'Overtime', 'Per Diem', 'Gross', 'TTI', 'Tax', 'EE Pension', 'ER Pension', 'Loan', 'Total Ded', 'Net']
        
        for i, col in enumerate(cols):
            sheet.write(4, i, col, hdr)

        # Initialize totals
        totals = {
            'days': 0, 'basic': 0, 'earning': 0, 'ot': 0, 'pd': 0,
            'gross': 0, 'tti': 0, 'tax': 0,
            'ee_pen': 0, 'er_pen': 0, 'loan': 0, 'td': 0, 'net': 0
        }
        
        # Data rows (start after header rows)
        row = 5
        sr_no = 1
        for payslip in self.batch_id.slip_ids:
            emp = payslip.employee_id
            
            # Get rule values
            def get_rule(code):
                line = payslip.line_ids.filtered(lambda x: x.code == code)
                return line.amount if line else 0.0
            
            # Employee info
            emp_id = emp.identification_id or emp.barcode or ''
            bank = emp.bank_account_id.acc_number if emp.bank_account_id else ''
            days = 0
            if payslip.contract_id:
                days = payslip.contract_id._count_working_days_excluding_sunday(
                    payslip.date_from, payslip.date_to)
            
            # Get contract wage (basic salary)
            basic_salary = payslip.contract_id.wage if payslip.contract_id else 0.0
            
            # Salary rules
            earning = get_rule('BASIC')  # Prorated earning
            ot = get_rule('OVERTIME')
            pd = get_rule('PERDIEM')
            gross = get_rule('GROSS')
            tti = get_rule('TTI')
            tax = abs(get_rule('INCOME_TAX'))
            ee_pen = get_rule('EE_PENSION')
            er_pen = get_rule('EMP_PENSION')
            loan = abs(get_rule('LOAN'))
            td = get_rule('TD')
            net = get_rule('NET')
            
            # Write
            sheet.write(row, 0, sr_no, cell)
            sheet.write(row, 1, emp.name, cell)
            sheet.write(row, 2, emp_id, cell)
            sheet.write(row, 3, bank, cell)
            sheet.write(row, 4, days, num)
            sheet.write(row, 5, basic_salary, num)
            sheet.write(row, 6, earning, num)
            sheet.write(row, 7, ot, num)
            sheet.write(row, 8, pd, num)
            sheet.write(row, 9, gross, num)
            sheet.write(row, 10, tti, num)
            sheet.write(row, 11, tax, num)
            sheet.write(row, 12, ee_pen, num)
            sheet.write(row, 13, er_pen, num)
            sheet.write(row, 14, loan, num)
            sheet.write(row, 15, td, num)
            sheet.write(row, 16, net, num)
            
            # Add to totals
            totals['days'] += days
            totals['basic'] += basic_salary
            totals['earning'] += earning
            totals['ot'] += ot
            totals['pd'] += pd
            totals['gross'] += gross
            totals['tti'] += tti
            totals['tax'] += tax
            totals['ee_pen'] += ee_pen
            totals['er_pen'] += er_pen
            totals['loan'] += loan
            totals['td'] += td
            totals['net'] += net
            
            row += 1
            sr_no += 1

        # Write totals row
        sheet.merge_range(row, 0, row, 3, 'TOTAL', total_label_fmt)
        sheet.write(row, 4, totals['days'], total_fmt)
        sheet.write(row, 5, totals['basic'], total_fmt)
        sheet.write(row, 6, totals['earning'], total_fmt)
        sheet.write(row, 7, totals['ot'], total_fmt)
        sheet.write(row, 8, totals['pd'], total_fmt)
        sheet.write(row, 9, totals['gross'], total_fmt)
        sheet.write(row, 10, totals['tti'], total_fmt)
        sheet.write(row, 11, totals['tax'], total_fmt)
        sheet.write(row, 12, totals['ee_pen'], total_fmt)
        sheet.write(row, 13, totals['er_pen'], total_fmt)
        sheet.write(row, 14, totals['loan'], total_fmt)
        sheet.write(row, 15, totals['td'], total_fmt)
        sheet.write(row, 16, totals['net'], total_fmt)

        workbook.close()
        output.seek(0)
        
        # Save attachment
        fname = f"Payroll_{self.batch_id.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        att = self.env['ir.attachment'].create({
            'name': fname,
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{att.id}?download=true',
            'target': 'self',
        }

