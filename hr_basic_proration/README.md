# HR Basic Salary Proration (exclude Sundays)

## Overview

This module extends the HR Contract model to provide prorated basic salary calculation that excludes Sundays from the working days count.

## Features

- **Exclude Sundays**: Automatically excludes Sundays from working days calculation
- **Prorated Salary**: Calculates prorated basic salary based on actual working days
- **Payroll Integration**: Provides methods that can be used directly in salary rules
- **Currency Precision**: Respects company currency rounding for accurate calculations

## Usage in Salary Rules

To use the prorated basic salary in your salary rule Python code:

```python
# Call the contract helper method defined by this module
result = contract._prorated_basic(payslip.date_from, payslip.date_to)
```

## Methods

### `_count_working_days_excluding_sunday(start_date, end_date)`

Counts the number of working days between two dates, excluding Sundays.

**Parameters:**
- `start_date`: Start date (date object or string in 'YYYY-MM-DD' format)
- `end_date`: End date (date object or string in 'YYYY-MM-DD' format)

**Returns:** Integer count of working days

### `_prorated_basic(payslip_date_from, payslip_date_to)`

Calculates the prorated basic salary for a given payslip period.

**Parameters:**
- `payslip_date_from`: Payslip start date
- `payslip_date_to`: Payslip end date

**Returns:** Float value of prorated salary (rounded to currency precision)

## Installation

1. Copy the module to your Odoo addons directory
2. Update the apps list
3. Install the "HR Basic Salary Proration (exclude Sundays)" module

## Dependencies

- `hr_contract`
- `hr_payroll_community`

## License

AGPL-3
