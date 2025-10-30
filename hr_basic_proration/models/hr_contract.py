# -*- coding: utf-8 -*-

from odoo import models, fields
from datetime import datetime, timedelta
from odoo.tools import float_round


class Contract(models.Model):
    _inherit = 'hr.contract'

    def _count_working_days_excluding_sunday(self, start_date, end_date):
        """
        Count days between start_date and end_date (inclusive) excluding Sundays.
        Accepts either date or string in 'YYYY-MM-DD'. Returns integer.
        """
        if not start_date or not end_date:
            return 0
        
        # normalize to date objects
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        if start_date > end_date:
            return 0
        
        days = 0
        cur = start_date
        while cur <= end_date:
            # Monday=0 ... Sunday=6
            if cur.weekday() != 6:  # Exclude Sunday
                days += 1
            cur += timedelta(days=1)
        return days

    def _prorated_basic(self, payslip_date_from, payslip_date_to):
        """
        Compute prorated basic salary for the given payslip period excluding Sundays.
        Also considers the contract start date - if employee started mid-period,
        only pay from the contract start date.
        
        Usage in salary rule Python code: 
        `result = contract._prorated_basic(payslip.date_from, payslip.date_to)`
        
        Returns float (rounded to 2 decimals using company currency rounding if available).
        """
        self.ensure_one()
        wage = float(self.wage or 0.0)
        if wage == 0.0:
            return 0.0

        # normalize payslip dates to date
        if isinstance(payslip_date_from, str):
            payslip_date_from = datetime.strptime(payslip_date_from, '%Y-%m-%d').date()
        if isinstance(payslip_date_to, str):
            payslip_date_to = datetime.strptime(payslip_date_to, '%Y-%m-%d').date()

        if not payslip_date_from or not payslip_date_to or payslip_date_from > payslip_date_to:
            return 0.0

        # Get contract start date
        contract_start = self.date_start
        if not contract_start:
            return 0.0
            
        # Convert contract start to date if it's datetime
        if hasattr(contract_start, 'date'):
            contract_start = contract_start.date()

        # Determine the effective start date for salary calculation
        # Use the later date between payslip start and contract start
        effective_start_date = max(payslip_date_from, contract_start)
        
        # If contract starts after payslip period ends, no salary
        if effective_start_date > payslip_date_to:
            return 0.0

        # compute month start and end (month containing payslip_date_from)
        month_start = payslip_date_from.replace(day=1)
        # compute next month first day
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        month_end = next_month - timedelta(days=1)

        # count total working days in the month (excluding Sundays)
        total_working_days = self._count_working_days_excluding_sunday(month_start, month_end)
        
        if total_working_days == 0:
            return 0.0

        # count actual working days from effective start date to payslip end (excluding Sundays)
        actual_working_days = self._count_working_days_excluding_sunday(effective_start_date, payslip_date_to)

        # calculate prorated salary
        prorated = wage * actual_working_days / total_working_days

        # get currency rounding precision
        rounding = 0.01  # default to 2 decimal places
        if self.company_id and self.company_id.currency_id:
            rounding = self.company_id.currency_id.rounding

        return float_round(prorated, precision_rounding=rounding)
