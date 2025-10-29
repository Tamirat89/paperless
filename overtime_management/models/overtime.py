from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta, time
import logging

_logger = logging.getLogger(__name__)

class HrContract(models.Model):
    _inherit = 'hr.contract'

    def get_overtime_amount(self, date_from, date_to):
        self.ensure_one()
        overtimes = self.env['employee.overtime'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'hr_approved'),
            ('start_datetime', '<=', date_to),
            ('end_datetime', '>=', date_from),
            ('company_id', 'in', self.env.companies.ids),
        ])
        return sum(o.amount_birr for o in overtimes)

class EmployeeOvertime(models.Model):
    _name = 'employee.overtime'
    _description = 'Employee Overtime'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Request Reference", required=True, copy=False, readonly=True, default=lambda self: _('New'))
    employee_id = fields.Many2one('hr.employee', string="Employee", required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, required=True, index=True, tracking=True, readonly=True)
    department_id = fields.Many2one(related='employee_id.department_id', store=True)
    start_datetime = fields.Datetime(string="Start Time", required=True)
    end_datetime = fields.Datetime(string="End Time", required=True)
    overtime_type_id = fields.Many2one('overtime.type', string="Overtime Type", required=True)

    worked_hours = fields.Float(string="Total Hours", compute='_compute_worked_hours', store=True)
    worked_days = fields.Float(string="Worked Days", compute='_compute_worked_hours', store=True)
    lunch_hours_deducted = fields.Float(string="Lunch Hours Deducted", compute='_compute_worked_hours', store=True)
    amount_birr = fields.Float(string="Total Amount (Birr)", compute='_compute_amount', store=True)
    reason = fields.Html(string="Reason")

    department_head_approved = fields.Boolean(string="Approved by Department Head")
    hr_approved = fields.Boolean(string="HR Approved")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submitted'),
        ('dept_approved', 'Department Approved'),
        ('hr_approved', 'HR Approved'),
        ('done', 'Done'),
        ('rejected', 'Rejected')
    ], default='draft', tracking=True)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('employee.overtime') or _('New')
        return super().create(vals)

    def _get_lunch_hours(self, start_dt, end_dt):
        """
        Calculate lunch hours to deduct based on approved lunch time configuration.
        Uses company-specific lunch configuration instead of hardcoded times.
        Handles timezone conversion properly by converting to user's timezone.
        """
        # Get approved and active lunch configuration for the company
        lunch_config = self.env['lunch.time.configuration'].search([
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'approved'),
            ('is_active_config', '=', True),
        ], limit=1)
        
        if not lunch_config:
            _logger.warning(f"No approved and active lunch time configuration found for company {self.company_id.name}. No lunch hours will be deducted.")
            return 0.0
        
        # Convert datetime from UTC to user's local timezone
        # Odoo stores datetimes in UTC, so we need to convert to local time for comparison
        from pytz import timezone as pytz_timezone, UTC
        user_tz = self.env.user.tz or 'UTC'
        local_tz = pytz_timezone(user_tz)
        
        _logger.info(f"Original start_dt: {start_dt}, tzinfo: {start_dt.tzinfo}")
        _logger.info(f"Original end_dt: {end_dt}, tzinfo: {end_dt.tzinfo}")
        _logger.info(f"User timezone: {user_tz}")
        
        # If datetime is naive (no timezone), assume it's UTC
        if start_dt.tzinfo is None:
            start_dt = UTC.localize(start_dt)
        if end_dt.tzinfo is None:
            end_dt = UTC.localize(end_dt)
        
        # Convert to local timezone and remove timezone info
        start_dt = start_dt.astimezone(local_tz).replace(tzinfo=None)
        end_dt = end_dt.astimezone(local_tz).replace(tzinfo=None)
        
        total_lunch_hours = 0.0
        current_date = start_dt.date()
        _logger.info(f"start_dt (local, naive): {start_dt}, end_dt (local, naive): {end_dt}")
        _logger.info(f"Using lunch config: {lunch_config.name}, start: {lunch_config.lunch_start_time}, end: {lunch_config.lunch_end_time}")

        # Convert float time to time object
        def float_to_time(float_time):
            """Convert float time (e.g., 12.5) to time object (12:30)"""
            hours = int(float_time)
            minutes = int((float_time - hours) * 60)
            return time(hours, minutes)

        lunch_start_time = float_to_time(lunch_config.lunch_start_time)
        lunch_end_time = float_to_time(lunch_config.lunch_end_time)

        while current_date <= end_dt.date():
            # Create naive datetime objects (no timezone)
            lunch_start = datetime.combine(current_date, lunch_start_time)
            lunch_end = datetime.combine(current_date, lunch_end_time)
            _logger.info(f"current_date: {current_date}, lunch_start: {lunch_start}, lunch_end: {lunch_end}")

            # Check if overtime overlaps lunch period
            latest_start = max(start_dt, lunch_start)
            earliest_end = min(end_dt, lunch_end)
            _logger.info(f"latest_start: {latest_start}, earliest_end: {earliest_end}")

            if latest_start < earliest_end:
                # Calculate only the overlapping portion
                overlap = (earliest_end - latest_start).total_seconds() / 3600.0
                _logger.info(f"overlap: {overlap}")
                total_lunch_hours += overlap
            else:
                _logger.info("No overlap detected")

            current_date += timedelta(days=1)

        _logger.info(f"total_lunch_hours: {total_lunch_hours}")
        return total_lunch_hours

    @api.depends('start_datetime', 'end_datetime')
    def _compute_worked_hours(self):
        for rec in self:
            if rec.start_datetime and rec.end_datetime:
                duration = (rec.end_datetime - rec.start_datetime).total_seconds() / 3600.0
                lunch_hours = rec._get_lunch_hours(rec.start_datetime, rec.end_datetime)
                _logger.info(f"duration: {duration}, lunch_hours: {lunch_hours}")
                rec.lunch_hours_deducted = lunch_hours
                rec.worked_hours = max(0.0, duration - lunch_hours)
                rec.worked_days = rec.worked_hours / 8.0
                _logger.info(f"worked_hours: {rec.worked_hours}, worked_days: {rec.worked_days}")
            else:
                rec.worked_hours = rec.worked_days = rec.lunch_hours_deducted = 0.0

    @api.depends('worked_days', 'overtime_type_id', 'employee_id')
    def _compute_amount(self):
        for rec in self:
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', rec.employee_id.id),
                ('state', '=', 'open')
            ], limit=1)
            if contract:
                # Get approved working days config from custom_employee_module
                working_days_config = self.env['working.days.config'].search([
                    ('state', '=', 'approved'),
                    ('company_id', '=', self.env.company.id)
                ], limit=1)
                
                if not working_days_config:
                    raise UserError(_("No approved working days configuration found. Please configure working days first."))
                
                daily_wage = contract.wage / working_days_config.number_of_working_days
                rec.amount_birr = rec.worked_days * daily_wage * rec.overtime_type_id.multiplier
                _logger.info(f"daily_wage: {daily_wage}, multiplier: {rec.overtime_type_id.multiplier}, amount_birr: {rec.amount_birr}")
            else:
                rec.amount_birr = 0.0
                _logger.info("No active contract found for employee")

    @api.constrains('start_datetime', 'end_datetime')
    def _check_dates(self):
        for rec in self:
            if rec.start_datetime >= rec.end_datetime:
                raise ValidationError("End time must be after start time.")

    @api.constrains('employee_id', 'start_datetime', 'end_datetime', 'state')
    def _check_overlap(self):
        for rec in self:
            if rec.state != 'draft':
                overlapping = self.env['employee.overtime'].search([
                    ('id', '!=', rec.id),
                    ('employee_id', '=', rec.employee_id.id),
                    ('state', 'not in', ['draft', 'rejected']),
                    '|',
                    '&', ('start_datetime', '<=', rec.start_datetime), ('end_datetime', '>', rec.start_datetime),
                    '|',
                    '&', ('start_datetime', '<', rec.end_datetime), ('end_datetime', '>=', rec.end_datetime),
                    '&', ('start_datetime', '>=', rec.start_datetime), ('end_datetime', '<=', rec.end_datetime)
                ])
                if overlapping:
                    raise ValidationError("Overlapping overtime entries detected for employee %s." % rec.employee_id.name)

    def schedule_activity_for_derestrict(self, summary, note):
        for rec in self:
            manager = rec.department_id.manager_id
            if manager and manager.user_id:
                rec.activity_schedule('mail.mail_activity_data_todo', user_id=manager.user_id.id, summary=summary, note=note)

    def schedule_activity_for_hr(self, summary, note):
        hr_group = self.env.ref('overtime_management.group_overtime_request_hr_manager')
        hr_users = self.env['res.users'].search([('groups_id', 'in', hr_group.id)])
        for rec in self:
            for hr_user in hr_users:
                rec.activity_schedule('mail.mail_activity_data_todo', user_id=hr_user.id, summary=summary, note=note)

    def action_submit(self):
        self.ensure_one()
        self._check_overlap()
        self.state = 'submit'
        self.schedule_activity_for_derestrict(
            summary="Overtime Request Submitted",
            note="The overtime request %s has been submitted." % self.name
        )

    def action_approve_department(self):
        self.ensure_one()
        if self.state != 'submit':
            raise UserError("Only 'Submitted' requests can be approved.")

        # Check if user has HR manager access (can approve all departments)
        has_hr_manager_access = self.env.user.has_group('overtime_management.group_overtime_request_hr_manager')
        
        # Check if user has department manager access
        has_dept_manager_access = self.env.user.has_group('overtime_management.group_overtime_request_department_manager')
        
        if not has_dept_manager_access and not has_hr_manager_access:
            raise UserError("Only department managers or HR managers can approve.")

        # If user is not HR manager, check if they are the department manager
        if not has_hr_manager_access:
            if self.department_id.manager_id.user_id != self.env.user:
                raise UserError("Only for your own department.")

        self.write({'department_head_approved': True, 'state': 'dept_approved'})
        self.schedule_activity_for_hr("Department Approved", "Overtime request %s approved." % self.name)

    def action_approve_hr(self):
        for rec in self:
            # HR managers can approve even without department approval
            has_hr_manager_access = self.env.user.has_group('overtime_management.group_overtime_request_hr_manager')
            
            if not rec.department_head_approved and not has_hr_manager_access:
                raise UserError("Department Head must approve first.")
            
            rec.hr_approved = True
            rec.state = 'hr_approved'

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def action_reject(self):
        self.write({'state': 'rejected'})

    @api.constrains('employee_id', 'department_id')
    def _check_department_manager_access(self):
        for rec in self:
            # HR managers have access to all departments
            if self.env.user.has_group('overtime_management.group_overtime_request_hr_manager'):
                continue
                
            # Department managers can only access their own department
            if self.env.user.has_group('overtime_management.group_overtime_request_department_manager'):
                if rec.department_id.manager_id.user_id != self.env.user:
                    raise ValidationError("Only your department's requests allowed.")