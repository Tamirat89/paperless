# -*- coding: utf-8 -*-
{
    'name': 'Employee Per Diem Management',
    'version': '18.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Manage employee per diem allowances with daily breakdown',
    'description': """
Employee Per Diem Management
============================

This module allows you to:
* Create per diem requests for employees
* Automatically generate daily breakdown lines
* Configure daily per diem rates
* Manage approval workflow (Submit → Review → Approve)
* Track total per diem amounts

Features:
* Employee-specific per diem requests
* Date range validation
* Daily value calculation from configuration
* Security groups and record rules
* Approval workflow with state management
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'hr',
        'hr_payroll_community',
        'mail',
    ],
    'data': [
        'security/perdiem_security.xml',
        'security/ir.model.access.csv',
        'data/perdiem_config_data.xml',
        'data/perdiem_salary_rule.xml',
        'views/perdiem_config_views.xml',
        'views/employee_perdiem_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
}
