# -*- coding: utf-8 -*-
{
    "name": "HR Basic Salary Proration (exclude Sundays)",
    "version": "1.0.0",
    "summary": "Compute prorated basic salary excluding Sundays and expose method for salary rule",
    "category": "Human Resources/Payroll",
    "author": "Your Name",
    "license": "AGPL-3",
    "depends": ["hr_contract", "hr_payroll_community"],
    "data": [
        "security/ir.model.access.csv",
        "data/salary_rules.xml",
    ],
    "installable": True,
    "application": False,
}
