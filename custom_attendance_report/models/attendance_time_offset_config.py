# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AttendanceTimeOffsetConfig(models.Model):
    _name = 'attendance.time.offset.config'
    _description = 'Attendance Time Offset Configuration'
    _order = 'id desc'

    name = fields.Char(string='Name', default='Time Offset Configuration', required=True)
    hour_offset = fields.Integer(
        string='Hour Offset',
        default=0,
        help='Hours to add (positive) or subtract (negative) from check-in and check-out times. '
             'Example: 3 adds 3 hours, -3 subtracts 3 hours.'
    )
    minute_offset = fields.Integer(
        string='Minute Offset',
        default=0,
        help='Minutes to add (positive) or subtract (negative) from check-in and check-out times. '
             'Example: 30 adds 30 minutes, -30 subtracts 30 minutes.'
    )
    active = fields.Boolean(string='Active', default=True, help='Only one active configuration will be used.')

    @api.model
    def get_active_config(self):
        """Get the active configuration record"""
        config = self.search([('active', '=', True)], limit=1, order='id desc')
        if not config:
            # Create default config if none exists
            config = self.create({
                'name': 'Default Time Offset Configuration',
                'hour_offset': 0,
                'minute_offset': 0,
                'active': True
            })
        return config

    @api.model
    def get_offsets(self):
        """Get hour and minute offsets from active configuration"""
        config = self.get_active_config()
        return {
            'hour_offset': config.hour_offset or 0,
            'minute_offset': config.minute_offset or 0
        }

