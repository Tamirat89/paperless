# -*- coding: utf-8 -*-
{
    'name': 'Working Days Configuration',
    'version': '18.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Configure working days per company with approval workflow',
    'description': """
Working Days Configuration
==========================

This module allows you to:
* Configure number of working days per company
* Approval workflow for working days configuration
* Company-specific working days settings
* HR Manager approval required for changes
* Validation for working days range (1-31 days)

Features:
* Company-specific configuration
* Draft/Approved state management
* HR Manager approval workflow
* Data validation and constraints
* Mail tracking and activity management
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'hr',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/working_days_config_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
}
