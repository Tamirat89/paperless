# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime, timedelta


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    start_date = fields.Char(
        string='Start Time',
        compute='_compute_start_end_time',
        store=True,
        readonly=True,
        help='Check-in time in HH:MM format'
    )
    
    end_date = fields.Char(
        string='End Time',
        compute='_compute_start_end_time',
        store=True,
        readonly=True,
        help='Check-out time in HH:MM format'
    )

    @api.model
    def recompute_all_start_end_times(self):
        """Recompute start_date and end_date for all existing attendance records
        This is useful when offset configuration changes
        """
        # Get all attendance records with check_in or check_out
        all_records = self.search([
            '|',
            ('check_in', '!=', False),
            ('check_out', '!=', False)
        ])
        
        if all_records:
            # Trigger recomputation by calling the compute method
            all_records._compute_start_end_time()
            # Force write to ensure stored values are updated
            all_records.flush_recordset(['start_date', 'end_date'])

    @api.depends('check_in', 'check_out')
    def _compute_start_end_time(self):
        """Compute start and end time from check_in and check_out datetime fields
        Read the timestamp as text from PostgreSQL, then extract time portion.
        Apply hour and minute offset from configuration.
        This bypasses any timezone conversion that psycopg2 or Odoo might apply.
        """
        if not self:
            return
        
        # Get offset configuration
        offsets = self.env['attendance.time.offset.config'].get_offsets()
        hour_offset = offsets.get('hour_offset', 0)
        minute_offset = offsets.get('minute_offset', 0)
        
        # Filter out NewId (temporary IDs for new records) and get only real database IDs
        record_ids = [rid for rid in self.ids if isinstance(rid, int)]
        
        # If no valid IDs (e.g., creating new record), compute directly from datetime objects
        if not record_ids:
            for record in self:
                if record.check_in:
                    # Apply offset to check_in datetime
                    adjusted_time = record.check_in + timedelta(hours=hour_offset, minutes=minute_offset)
                    record.start_date = adjusted_time.strftime('%H:%M')
                else:
                    record.start_date = ''
                
                if record.check_out:
                    # Apply offset to check_out datetime
                    adjusted_time = record.check_out + timedelta(hours=hour_offset, minutes=minute_offset)
                    record.end_date = adjusted_time.strftime('%H:%M')
                else:
                    record.end_date = ''
            return
        
        # Use PostgreSQL's time arithmetic: add interval using make_interval function
        # This is safer than string interpolation
        self.env.cr.execute("""
            SELECT 
                id,
                CASE 
                    WHEN check_in IS NOT NULL 
                    THEN (
                        (check_in AT TIME ZONE 'UTC') + 
                        make_interval(hours => %s, mins => %s)
                    )::time::text
                    ELSE NULL
                END as check_in_time,
                CASE 
                    WHEN check_out IS NOT NULL 
                    THEN (
                        (check_out AT TIME ZONE 'UTC') + 
                        make_interval(hours => %s, mins => %s)
                    )::time::text
                    ELSE NULL
                END as check_out_time
            FROM hr_attendance
            WHERE id IN %s
        """, (hour_offset, minute_offset, hour_offset, minute_offset, tuple(record_ids),))
        
        time_data = {}
        for row in self.env.cr.fetchall():
            att_id, check_in_time, check_out_time = row
            # Extract HH:MM from time string (format is HH:MM:SS)
            check_in_formatted = str(check_in_time)[:5] if check_in_time else ''
            check_out_formatted = str(check_out_time)[:5] if check_out_time else ''
            time_data[att_id] = {
                'check_in': check_in_formatted,
                'check_out': check_out_formatted
            }
        
        for record in self:
            if record.id in time_data:
                record.start_date = time_data[record.id].get('check_in', '')
                record.end_date = time_data[record.id].get('check_out', '')
            else:
                # For records not in query result (e.g., new records), compute directly
                if record.check_in:
                    adjusted_time = record.check_in + timedelta(hours=hour_offset, minutes=minute_offset)
                    record.start_date = adjusted_time.strftime('%H:%M')
                else:
                    record.start_date = ''
                
                if record.check_out:
                    adjusted_time = record.check_out + timedelta(hours=hour_offset, minutes=minute_offset)
                    record.end_date = adjusted_time.strftime('%H:%M')
                else:
                    record.end_date = ''

