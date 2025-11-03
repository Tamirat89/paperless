# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import io
import xlsxwriter
import base64
from datetime import datetime, timedelta

class PayrollBatchExcelWizard(models.TransientModel):
    _name = 'payroll.batch.excel.wizard'
    _description = 'Payroll Batch Excel Report Wizard (Dynamic Columns)'

    batch_id = fields.Many2one(
        'hr.payslip.run',
        string='Payroll Batch',
        required=True,
        default=lambda self: self._context.get('default_batch_id')
    )

    def _calculate_working_days(self, employee, payslip_start, payslip_end):
        """
        Calculate working days from payroll period, excluding Sundays.
        If employee contract started after payroll start, calculate from contract start date.
        """
        # Get employee's active contract
        contract = employee.contract_ids.filtered(lambda c: c.state == 'open')[:1] or employee.contract_ids[:1]
        
        # Determine actual start date: later of contract start or payroll start
        if contract and contract.date_start and contract.date_start > payslip_start:
            actual_start_date = contract.date_start
        else:
            actual_start_date = payslip_start
            
        # Calculate total calendar days in the period
        total_days = (payslip_end - actual_start_date).days + 1
        
        # Count Sundays in the period (exclude them from working days)
        sundays_count = 0
        current_date = actual_start_date
        while current_date <= payslip_end:
            if current_date.weekday() == 6:  # Sunday is weekday 6
                sundays_count += 1
            current_date += timedelta(days=1)
        
        # Calculate actual working days (total days minus Sundays)
        actual_working_days = total_days - sundays_count
        
        return actual_working_days

    def action_generate_excel(self):
        self.ensure_one()
        batch = self.batch_id

        if not batch.slip_ids:
            raise UserError("The selected payroll batch has no payslips.")

        # Create an in-memory Excel file
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)

        # Get company
        company = self.env.company
        
        # Define month_year
        month_year = batch.date_start.strftime('%B %Y')

        # --- Define Formats ---
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'align': 'center',
            'valign': 'vcenter',
            'border': 2,
            'border_color': '#000000',
        })
        
        title_format_2 = workbook.add_format({
            'bold': True,
            'font_size': 18,
            'italic': True,
            'align': 'center',
            'valign': 'vcenter',
            'border': 2,
            'border_color': '#000000',
        })
        
        cell_format = workbook.add_format({
            'bold': True,
            'border': 2,
            'border_color': '#000000',
            'align': 'left',
            'valign': 'vcenter',
        })
        
        dynamic_cell_format = workbook.add_format({
            'border': 1,
            'align': 'left',
            'valign': 'vcenter',
        })
        
        dynamic_subtitle_format = workbook.add_format({
            'font_size': 12,
            'align': 'center',
            'valign': 'vcenter',
            'bold': True,
            'border': 2,
            'border_color': '#000000',
        })
        
        dynamic_revision_format = workbook.add_format({
            'font_size': 10,
            'align': 'left',
            'valign': 'vcenter',
            'border': 2,
            'border_color': '#000000',
        })
        
        header_format = workbook.add_format({
            'bold': True,
            'border': 1,
            'border_color': '#000000',
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#D3D3D3'
        })
        
        dynamic_number_format = workbook.add_format({
            'border': 1,
            'align': 'right',
            'valign': 'vcenter',
            'num_format': '#,##0.00',
        })
        
        department_total_format = workbook.add_format({
            'bold': True,
            'border': 2,
            'align': 'left',
            'valign': 'vcenter',
            'bg_color': '#FFFF99'
        })
        
        department_total_number_format = workbook.add_format({
            'bold': True,
            'border': 1,
            'align': 'right',
            'valign': 'vcenter',
            'num_format': '#,##0.00',
            'bg_color': '#FFFF99'
        })

        # --- Create Worksheet ---
        worksheet = workbook.add_worksheet(f"Payroll {month_year.upper()}")

        # Set row heights
        worksheet.set_row(1, 30)
        worksheet.set_row(2, 40)
        worksheet.set_row(3, 40)
        worksheet.set_row(4, 25)

        # --- Company Logo ---
        logo_data = company.logo
        if logo_data:
            try:
                logo_image = io.BytesIO(base64.b64decode(logo_data))
                worksheet.merge_range('A1:B3', '', cell_format)
                worksheet.insert_image('A1', 'company_logo.png', {
                    'image_data': logo_image,
                    'x_scale': 0.15,
                    'y_scale': 0.15,
                    'x_offset': 10,
                    'y_offset': 10
                })
            except Exception:
                worksheet.merge_range('A1:B3', 'Logo', cell_format)
        else:
            worksheet.merge_range('A1:B3', 'Logo', cell_format)

        # --- Header Rows ---
        worksheet.merge_range('C1:O1', company.name, title_format)
        worksheet.merge_range('C2:O2', 'PAYROLL SHEET FORM', title_format_2)
        worksheet.merge_range('P1:T1', f'Issue Date: {batch.date_start.strftime("%d/%m/%Y")} to {batch.date_end.strftime("%d/%m/%Y")}', dynamic_revision_format)
        worksheet.merge_range('P2:T2', 'Revision No: 01 | Page 1 of 1', dynamic_revision_format)
        worksheet.merge_range('C3:T3', f'FOR THE MONTH OF {month_year.upper()}', dynamic_subtitle_format)

        # --- Collect All Payslip Data ---
        all_payslip_data = []
        department_payslips = {}
        
        for payslip in batch.slip_ids:
            employee = payslip.employee_id
            department = employee.department_id.name if employee.department_id else 'No Department'
            if department not in department_payslips:
                department_payslips[department] = []
            department_payslips[department].append(payslip)
            
            # Collect all payslip data
            payslip_data = {
                'employee': employee,
                'payslip': payslip,
                'days_worked': self._calculate_working_days(employee, payslip.date_from, payslip.date_to),
                'basic_salary': payslip.line_ids.filtered(lambda l: l.code == 'BASIC').amount or 0.0,
                'overtime': payslip.line_ids.filtered(lambda l: l.code == 'OVERTIME').amount or 0.0,
                'per_diem': payslip.line_ids.filtered(lambda l: l.code == 'PERDIEM').amount or 0.0,
                'loan': abs(payslip.line_ids.filtered(lambda l: l.code == 'LOAN').amount or 0.0),
                'gross': payslip.line_ids.filtered(lambda l: l.code == 'GROSS').amount or 0.0,
                'tti': payslip.line_ids.filtered(lambda l: l.code == 'TTI').amount or 0.0,
                'income_tax': abs(payslip.line_ids.filtered(lambda l: l.code == 'INCOME_TAX').amount or 0.0),
                'ee_pension': payslip.line_ids.filtered(lambda l: l.code == 'EE_PENSION').amount or 0.0,
                'er_pension': payslip.line_ids.filtered(lambda l: l.code == 'EMP_PENSION').amount or 0.0,
                'total_deduction': payslip.line_ids.filtered(lambda l: l.code == 'TD').amount or 0.0,
                'net_pay': payslip.line_ids.filtered(lambda l: l.code == 'NET').amount or 0.0,
            }
            all_payslip_data.append(payslip_data)

        # --- Define All Possible Columns ---
        all_columns = [
            ('Sr No', 'sr_no'),
            ('Employee Name', 'name'),
            ('Days Worked', 'days_worked'),
            ('Basic Salary', 'basic_salary'),
            ('Overtime', 'overtime'),
            ('Per Diem', 'per_diem'),
            ('Loan Deduction', 'loan'),
            ('Gross Salary', 'gross'),
            ('Taxable Income (TTI)', 'tti'),
            ('Income Tax', 'income_tax'),
            ('Employee Pension (7%)', 'ee_pension'),
            ('Employer Pension (11%)', 'er_pension'),
            ('Total Deductions', 'total_deduction'),
            ('Net Salary', 'net_pay'),
            ('Bank Account', 'account_number'),
            ('Signature', 'signature'),
        ]

        # --- Filter Active Columns (with non-zero values) ---
        active_columns = []
        for header, field_key in all_columns:
            if field_key in ['sr_no', 'name', 'signature', 'account_number']:
                active_columns.append((header, field_key))
            else:
                has_value = any(abs(data.get(field_key, 0)) > 0.01 for data in all_payslip_data)
                if has_value:
                    active_columns.append((header, field_key))

        # --- Set Column Widths ---
        def calculate_column_width(header, field_key, data_list):
            header_length = len(header)
            max_width = 50
            
            if field_key == 'sr_no':
                return max(header_length + 2, len(str(len(data_list))) + 2)
            elif field_key == 'name':
                max_name = max([len(str(d['employee'].name or '')) for d in data_list] + [header_length])
                return min(max_name + 3, max_width)
            elif field_key == 'account_number':
                max_acc = max([len(str(d['employee'].bank_account_id.acc_number if d['employee'].bank_account_id else '')) for d in data_list] + [header_length])
                return max_acc + 2
            elif field_key == 'signature':
                return header_length + 5
            else:
                max_num = header_length
                for d in data_list:
                    val = d.get(field_key, 0.0)
                    if isinstance(val, (int, float)):
                        formatted = f"{val:,.2f}"
                        max_num = max(max_num, len(formatted))
                return max_num + 2
        
        for col_idx, (header, field_key) in enumerate(active_columns):
            width = calculate_column_width(header, field_key, all_payslip_data)
            worksheet.set_column(col_idx, col_idx, width)

        # --- Write Column Headers (Row 4) ---
        for col, (header, field_key) in enumerate(active_columns):
            worksheet.write(3, col, header, header_format)

        # --- Write Data Rows by Department ---
        row = 4  # Start right after headers (row 3 in 0-indexed = row 4 in Excel)
        sorted_departments = sorted(department_payslips.keys())
        global_idx = 1
        grand_totals = {}

        for department in sorted_departments:
            payslips = department_payslips[department]
            
            # Department Header
            dept_col_idx = next((i for i, (h, f) in enumerate(active_columns) if f == 'name'), 1)
            worksheet.write(row, dept_col_idx, f"{department} Department", department_total_format)
            row += 1

            dept_totals = {}
            
            for payslip_data in all_payslip_data:
                if payslip_data['payslip'] in payslips:
                    employee = payslip_data['employee']
                    account_number = employee.bank_account_id.acc_number if employee.bank_account_id else 'N/A'

                    # Write data for active columns
                    for col, (header, field_key) in enumerate(active_columns):
                        if field_key == 'sr_no':
                            worksheet.write(row, col, global_idx, dynamic_cell_format)
                        elif field_key == 'name':
                            worksheet.write(row, col, employee.name or '', dynamic_cell_format)
                        elif field_key == 'account_number':
                            worksheet.write(row, col, account_number, dynamic_cell_format)
                        elif field_key == 'signature':
                            worksheet.write(row, col, '', dynamic_cell_format)
                        else:
                            value = payslip_data.get(field_key, 0.0)
                            worksheet.write(row, col, value, dynamic_number_format)
                            
                            # Update totals
                            if field_key not in dept_totals:
                                dept_totals[field_key] = 0.0
                            if field_key not in grand_totals:
                                grand_totals[field_key] = 0.0
                            dept_totals[field_key] += value
                            grand_totals[field_key] += value

                    row += 1
                    global_idx += 1

            # Department Total Row
            worksheet.write(row, dept_col_idx, f"Total {department} Salary", department_total_format)
            for col, (header, field_key) in enumerate(active_columns):
                if field_key not in ['sr_no', 'name', 'signature', 'account_number']:
                    total_value = dept_totals.get(field_key, 0.0)
                    worksheet.write(row, col, total_value, department_total_number_format)
            row += 2  # Blank row after department

        # --- Grand Total Row ---
        grand_col_idx = next((i for i, (h, f) in enumerate(active_columns) if f == 'name'), 1)
        worksheet.write(row, grand_col_idx, "GRAND TOTAL", department_total_format)
        for col, (header, field_key) in enumerate(active_columns):
            if field_key not in ['sr_no', 'name', 'signature', 'account_number']:
                total_value = grand_totals.get(field_key, 0.0)
                worksheet.write(row, col, total_value, department_total_number_format)

        # --- Second Worksheet: Summary ---
        worksheet2 = workbook.add_worksheet('Summary of Payroll')
        worksheet2.set_row(0, 30)
        worksheet2.set_row(1, 25)
        worksheet2.merge_range('A1:E1', self.env.company.name, title_format)
        worksheet2.merge_range('A2:E2', f'SALARY FOR THE MONTH OF {month_year.upper()}', dynamic_subtitle_format)
        worksheet2.set_column('A:A', 10)
        worksheet2.set_column('B:B', 40)
        worksheet2.set_column('C:C', 20)
        worksheet2.set_column('D:D', 20)
        worksheet2.set_column('E:E', 15)

        headers2 = ['No', 'Name of Employee', 'Bank Name', 'Account No', 'Net Salary']
        for col, header in enumerate(headers2):
            worksheet2.write(3, col, header, header_format)

        row2 = 4
        total_net_salary = 0.0
        for idx, payslip in enumerate(batch.slip_ids, 1):
            employee = payslip.employee_id
            net_pay = payslip.line_ids.filtered(lambda l: l.code == 'NET').amount or 0.0
            total_net_salary += net_pay

            # Get bank account directly from employee
            account_number = employee.bank_account_id.acc_number if employee.bank_account_id else 'No Account'
            bank_name = employee.bank_account_id.bank_id.name if employee.bank_account_id and employee.bank_account_id.bank_id else 'No Bank'

            full_name = employee.name or ''
            if hasattr(employee, 'grandfather_name') and employee.grandfather_name:
                full_name += f" {employee.grandfather_name}"

            worksheet2.write(row2, 0, idx, dynamic_cell_format)
            worksheet2.write(row2, 1, full_name, dynamic_cell_format)
            worksheet2.write(row2, 2, bank_name, dynamic_cell_format)
            worksheet2.write(row2, 3, account_number, dynamic_cell_format)
            worksheet2.write(row2, 4, net_pay, dynamic_number_format)
            row2 += 1

        total_row2 = row2
        worksheet2.write(total_row2, 3, 'Total', department_total_format)
        worksheet2.write(total_row2, 4, total_net_salary, department_total_number_format)

        # --- Third Worksheet: Income Tax ---
        worksheet3 = workbook.add_worksheet('Income Tax')

        # Write the header (batch name and period) for Worksheet 3
        worksheet3.merge_range('A1:N1', f'Income Tax Report - {batch.name}', title_format)
        worksheet3.merge_range('A2:N2', f'Period: {batch.date_start.strftime("%d/%m/%Y")} to {batch.date_end.strftime("%d/%m/%Y")}', dynamic_subtitle_format)

        # Set column widths for Worksheet 3
        worksheet3.set_column('A:A', 10)   # Sr No
        worksheet3.set_column('B:B', 15)   # Employee TIN
        worksheet3.set_column('C:C', 20)   # Employee Name
        worksheet3.set_column('D:D', 10)   # Start Date
        worksheet3.set_column('E:E', 15)   # Basic Salary
        worksheet3.set_column('F:F', 20)   # Total Transportation Allowance
        worksheet3.set_column('G:G', 20)   # Taxable Transportation Allowance
        worksheet3.set_column('H:H', 15)   # Over Time
        worksheet3.set_column('I:I', 20)   # Other Taxable Benefits (Housing)
        worksheet3.set_column('J:J', 15)   # Taxable Income
        worksheet3.set_column('K:K', 15)   # Tax Withheld
        worksheet3.set_column('L:L', 15)   # Cost Sharing
        worksheet3.set_column('M:M', 15)   # Net Pay
        worksheet3.set_column('N:N', 20)   # Employee Signature

        # Write headers for Worksheet 3
        headers3 = [
            'Sr No', 'Employee TIN', 'Employee Name', 'Start Date', 'Basic Salary',
            'Total Transportation Allowance', 'Taxable Transportation Allowance',
            'Over Time', 'Other Taxable Benefits (Housing)', 'Taxable Income',
            'Tax Withheld', 'Cost Sharing', 'Net Pay', 'Employee Signature'
        ]
        for col, header in enumerate(headers3):
            worksheet3.write(3, col, header, header_format)

        # Write data for Worksheet 3
        row3 = 4
        for idx, payslip in enumerate(batch.slip_ids, 1):
            employee = payslip.employee_id
            
            # Get employee TIN
            emp_tin = employee.tin_number if hasattr(employee, 'tin_number') else ''
            
            # Get employee name with grandfather name
            full_name = employee.name or ''
            if hasattr(employee, 'grandfather_name') and employee.grandfather_name:
                full_name += f" {employee.grandfather_name}"
            
            # Get contract start date
            contract_start = payslip.contract_id.date_start if payslip.contract_id else ''
            
            # Get salary components
            basic_salary = payslip.line_ids.filtered(lambda l: l.code == 'BASIC').amount or 0.0
            total_transport = (payslip.line_ids.filtered(lambda l: l.code == 'TTRAT').amount or 0.0) + \
                             (payslip.line_ids.filtered(lambda l: l.code == 'NTRA').amount or 0.0)
            taxable_transport = payslip.line_ids.filtered(lambda l: l.code == 'TTRAT').amount or 0.0
            overtime = payslip.line_ids.filtered(lambda l: l.code == 'OVERTIME').amount or 0.0
            housing = payslip.line_ids.filtered(lambda l: l.code == 'HRA').amount or 0.0
            taxable_income = payslip.line_ids.filtered(lambda l: l.code == 'TTI').amount or 0.0
            tax_withheld = abs(payslip.line_ids.filtered(lambda l: l.code == 'INCOME_TAX').amount or 0.0)
            cost_sharing = payslip.line_ids.filtered(lambda l: l.code == 'EE_PENSION').amount or 0.0
            net_pay = payslip.line_ids.filtered(lambda l: l.code == 'NET').amount or 0.0
            
            # Write data
            worksheet3.write(row3, 0, idx, dynamic_cell_format)
            worksheet3.write(row3, 1, emp_tin, dynamic_cell_format)
            worksheet3.write(row3, 2, full_name, dynamic_cell_format)
            worksheet3.write(row3, 3, contract_start, dynamic_cell_format)
            worksheet3.write(row3, 4, basic_salary, dynamic_number_format)
            worksheet3.write(row3, 5, total_transport, dynamic_number_format)
            worksheet3.write(row3, 6, taxable_transport, dynamic_number_format)
            worksheet3.write(row3, 7, overtime, dynamic_number_format)
            worksheet3.write(row3, 8, housing, dynamic_number_format)
            worksheet3.write(row3, 9, taxable_income, dynamic_number_format)
            worksheet3.write(row3, 10, tax_withheld, dynamic_number_format)
            worksheet3.write(row3, 11, cost_sharing, dynamic_number_format)
            worksheet3.write(row3, 12, net_pay, dynamic_number_format)
            worksheet3.write(row3, 13, '', dynamic_cell_format)  # Signature column
            row3 += 1

        # --- Close and Save ---
        workbook.close()
        output.seek(0)
        
        # Create attachment
        filename = f"Payroll_{batch.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

