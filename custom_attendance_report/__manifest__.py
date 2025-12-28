# -*- coding: utf-8 -*-
{
    'name': "Custom Attendance Report",
    'summary': "Generate Excel attendance reports with weekly breakdown",
    'description': """
        Custom Attendance Report Module
        ===============================
        This module allows you to generate Excel reports for employee attendance
        with weekly breakdown showing check-in and check-out times.
        
        Features:
        - Filter by company, department, and employee
        - Weekly breakdown with separate sheets per week
        - Shows first check-in and last check-out per day
        - Displays "Absent" for days without attendance
    """,
    'author': "Your Company",
    'website': "http://www.yourcompany.com",
    'category': 'Human Resources',
    'version': '18.0.1.0.0',
    'depends': ['base', 'hr', 'hr_attendance'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_attendance_view.xml',
        'views/attendance_report_wizard_view.xml',
        'views/res_config_settings_view.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
    'post_init_hook': 'post_init_update_attendance_times',
}

