# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError
import io
import xlsxwriter
import base64
from datetime import datetime, timedelta
from collections import defaultdict


class AttendanceReportWizard(models.TransientModel):
    _name = 'attendance.report.wizard'
    _description = 'Attendance Report Wizard'

    start_date = fields.Date(string='Start Date', required=True, default=fields.Date.today)
    end_date = fields.Date(string='End Date', required=True, default=fields.Date.today)
    filter_type = fields.Selection([
        ('company', 'Company'),
        ('department', 'Department'),
        ('employee', 'Employee'),
    ], string='Filter By', required=True, default='company')
    company_ids = fields.Many2many('res.company', string='Companies', default=lambda self: [self.env.company.id])
    department_ids = fields.Many2many('hr.department', string='Departments')
    employee_ids = fields.Many2many('hr.employee', string='Employees')

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for record in self:
            if record.start_date > record.end_date:
                raise UserError("Start Date must be before End Date.")

    def _get_week_ranges(self, start_date, end_date):
        """Split date range into weeks"""
        weeks = []
        current_date = start_date
        week_start = None
        
        while current_date <= end_date:
            # Get the Monday of the current week
            days_since_monday = current_date.weekday()
            monday = current_date - timedelta(days=days_since_monday)
            
            if week_start is None or monday > week_start:
                # Start a new week
                if week_start is not None:
                    # End previous week (Sunday)
                    weeks.append({
                        'start': week_start,
                        'end': week_start + timedelta(days=6)
                    })
                week_start = monday
            
            current_date += timedelta(days=1)
        
        # Add the last week
        if week_start:
            last_sunday = min(week_start + timedelta(days=6), end_date)
            weeks.append({
                'start': week_start,
                'end': last_sunday
            })
        
        return weeks

    def _get_attendance_data(self, week_start, week_end):
        """Get attendance data for a specific week
        Uses start_date and end_date fields which already have offset applied
        """
        domain = [
            ('check_in', '>=', datetime.combine(week_start, datetime.min.time())),
            ('check_in', '<=', datetime.combine(week_end, datetime.max.time())),
        ]
        
        # Apply filters based on filter_type
        if self.filter_type == 'employee' and self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        elif self.filter_type == 'department' and self.department_ids:
            domain.append(('employee_id.department_id', 'in', self.department_ids.ids))
            if self.company_ids:
                domain.append(('employee_id.company_id', 'in', self.company_ids.ids))
        elif self.filter_type == 'company' and self.company_ids:
            domain.append(('employee_id.company_id', 'in', self.company_ids.ids))
        
        attendances = self.env['hr.attendance'].search(domain, order='check_in asc')
        
        if not attendances:
            return {}
        
        # Use start_date and end_date fields directly - they already have offset applied
        attendance_dict = defaultdict(lambda: defaultdict(lambda: {'check_ins': [], 'check_outs': []}))
        
        for attendance in attendances:
            employee = attendance.employee_id
            # Get date from check_in for grouping (use check_in date, not start_date)
            check_in_date = attendance.check_in.date() if attendance.check_in else None
            
            if not check_in_date:
                continue
            
            # Use start_date and end_date fields which already have offset and formatting applied
            if attendance.start_date:
                attendance_dict[employee][check_in_date]['check_ins'].append(attendance.start_date)
            
            if attendance.end_date:
                attendance_dict[employee][check_in_date]['check_outs'].append(attendance.end_date)
        
        return attendance_dict

    def _format_time(self, time_str):
        """Return time string directly - start_date and end_date are already formatted as HH:MM"""
        if time_str:
            # Time is already a string in HH:MM format from start_date/end_date fields
            return str(time_str)
        return ''

    def action_generate_excel(self):
        """Generate Excel report"""
        self.ensure_one()
        
        # Validate filters based on filter_type
        if self.filter_type == 'company' and not self.company_ids:
            raise UserError("Please select at least one company.")
        elif self.filter_type == 'department' and not self.department_ids:
            raise UserError("Please select at least one department.")
        elif self.filter_type == 'employee' and not self.employee_ids:
            raise UserError("Please select at least one employee.")
        
        # Get week ranges
        weeks = self._get_week_ranges(self.start_date, self.end_date)
        
        if not weeks:
            raise UserError("No weeks found in the selected date range.")
        
        # Create Excel workbook
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        # Day names (Monday to Sunday)
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        # Formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#D3D3D3',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'font_size': 10
        })
        
        cell_format = workbook.add_format({
            'border': 1,
            'align': 'left',
            'valign': 'vcenter',
            'font_size': 9
        })
        
        time_format = workbook.add_format({
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
            'font_size': 9
        })
        
        week_header_format = workbook.add_format({
            'bold': True,
            'font_size': 12,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#B0C4DE'
        })
        
        # Process each week
        for week_idx, week in enumerate(weeks):
            week_start = week['start']
            week_end = week['end']
            
            # Create sheet for this week
            sheet_name = f"Week {week_idx + 1}"
            if len(sheet_name) > 31:  # Excel sheet name limit
                sheet_name = f"W{week_idx + 1}"
            sheet = workbook.add_worksheet(sheet_name)
            
            # Set column widths
            sheet.set_column('A:A', 25)  # Employee name
            col = 1
            for day in day_names:
                if week_start + timedelta(days=day_names.index(day)) <= week_end:
                    sheet.set_column(col, col, 12)  # Check in
                    sheet.set_column(col + 1, col + 1, 12)  # Check out
                    col += 2
            
            # Week header
            week_header = f"Week {week_idx + 1}: {week_start.strftime('%b %d, %Y')} - {week_end.strftime('%b %d, %Y')}"
            num_cols = len([d for d in day_names if week_start + timedelta(days=day_names.index(d)) <= week_end]) * 2 + 1
            sheet.merge_range(0, 0, 0, num_cols - 1, week_header, week_header_format)
            
            # Column headers row
            row = 2
            col = 0
            sheet.write(row, col, 'Employee Name', header_format)
            col += 1
            
            for day in day_names:
                day_date = week_start + timedelta(days=day_names.index(day))
                if day_date <= week_end:
                    sheet.merge_range(row, col, row, col + 1, day, header_format)
                    sheet.write(row + 1, col, 'Check in', header_format)
                    sheet.write(row + 1, col + 1, 'Check out', header_format)
                    col += 2
            
            # Get attendance data for this week
            attendance_data = self._get_attendance_data(week_start, week_end)
            
            # Get all employees based on filter_type
            if self.filter_type == 'employee':
                if not self.employee_ids:
                    raise UserError("Please select at least one employee.")
                all_employees = self.employee_ids
            elif self.filter_type == 'department':
                if not self.department_ids:
                    raise UserError("Please select at least one department.")
                domain = [('department_id', 'in', self.department_ids.ids)]
                if self.company_ids:
                    domain.append(('company_id', 'in', self.company_ids.ids))
                all_employees = self.env['hr.employee'].search(domain)
            elif self.filter_type == 'company':
                if not self.company_ids:
                    raise UserError("Please select at least one company.")
                all_employees = self.env['hr.employee'].search([('company_id', 'in', self.company_ids.ids)])
            else:
                # If no filters, get all employees from attendance data
                employee_ids = list(set([emp.id for emp in attendance_data.keys()]))
                all_employees = self.env['hr.employee'].browse(employee_ids) if employee_ids else self.env['hr.employee']
            
            # Write employee data
            row = 4
            for employee in sorted(all_employees, key=lambda e: e.name):
                col = 0
                sheet.write(row, col, employee.name, cell_format)
                col += 1
                
                for day in day_names:
                    day_date = week_start + timedelta(days=day_names.index(day))
                    if day_date <= week_end:
                        if employee in attendance_data and day_date in attendance_data[employee]:
                            day_data = attendance_data[employee][day_date]
                            # First check-in
                            check_in = day_data['check_ins'][0] if day_data['check_ins'] else None
                            # Last check-out
                            check_out = day_data['check_outs'][-1] if day_data['check_outs'] else None
                            
                            sheet.write(row, col, self._format_time(check_in), time_format)
                            sheet.write(row, col + 1, self._format_time(check_out), time_format)
                        else:
                            sheet.write(row, col, 'Absent', time_format)
                            sheet.write(row, col + 1, '', time_format)
                        col += 2
                
                row += 1
        
        workbook.close()
        output.seek(0)
        
        # Create attachment
        filename = f"Attendance_Report_{self.start_date.strftime('%Y%m%d')}_to_{self.end_date.strftime('%Y%m%d')}.xlsx"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self.id,
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

