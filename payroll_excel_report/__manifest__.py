# -*- coding: utf-8 -*-
{
    'name': 'Payroll Excel Report',
    'version': '18.0.1.0.0',
    'summary': 'Generate Excel reports from payroll batches',
    'category': 'Human Resources/Payroll',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': [
        'hr_payroll_community',
        'hr_basic_proration',
        'overtime_management',
        'employee_perdiem',
    ],
    'data': [
        'wizards/payroll_excel_wizard_views.xml',
        'wizards/payroll_batch_excel_wizard_views.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
}

