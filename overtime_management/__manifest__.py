# -*- coding: utf-8 -*-
{
    'name': "Overtime management",

    'summary': "Tolo Customized Employee Module",

    'description': """
Long description of module's purpose
    """,

    'author': "Tolo Solutions LLC",
    'website': "https://www.tolosolutions.com",
    'icon': '',
    'sequence': -1000,

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Human Resources',
    'version': '18.0.1.0.0',

    # any module necessary for this one to work correctly
    'depends': [
            'hr',
            'hr_contract',
            'hr_payroll_community',
            'date_range',
            'working_days_config',
            # 'additional_custom_employee_module',
        ],


    # always loaded
    'data': [
        'security/employee_overtime_security.xml',  # Load security groups first
        'security/employee_overtime_rule.xml',      # Then load security rules
        'security/ir.model.access.csv',            # Then load access rights
        
        'data/overtime_sequence.xml',
        'data/hr_salary_rule_overtime.xml',

        'views/overtime_views.xml',
        'views/overtime_type_views.xml',
        'views/lunch_time_configuration_views.xml',
    ],
   
    'installable': True,
    'application': False,
}
