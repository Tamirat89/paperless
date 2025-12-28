# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    attendance_hour_offset = fields.Integer(
        string='Hour Offset',
        default=0,
        help='Hours to add (positive) or subtract (negative) from check-in and check-out times displayed in start_date and end_date fields.'
    )
    attendance_minute_offset = fields.Integer(
        string='Minute Offset',
        default=0,
        help='Minutes to add (positive) or subtract (negative) from check-in and check-out times displayed in start_date and end_date fields.'
    )

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        offsets = self.env['attendance.time.offset.config'].get_offsets()
        res.update({
            'attendance_hour_offset': offsets['hour_offset'],
            'attendance_minute_offset': offsets['minute_offset'],
        })
        return res

    def set_values(self):
        super().set_values()
        config = self.env['attendance.time.offset.config'].get_active_config()
        old_hour_offset = config.hour_offset
        old_minute_offset = config.minute_offset
        
        config.write({
            'hour_offset': self.attendance_hour_offset,
            'minute_offset': self.attendance_minute_offset,
        })
        
        # If offset values changed, recompute all existing attendance records
        if (old_hour_offset != self.attendance_hour_offset or 
            old_minute_offset != self.attendance_minute_offset):
            self.env['hr.attendance'].recompute_all_start_end_times()

