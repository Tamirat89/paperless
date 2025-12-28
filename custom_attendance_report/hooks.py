# -*- coding: utf-8 -*-

def post_init_update_attendance_times(env):
    """Post-init hook to update all existing attendance records with new computed fields"""
    # Recompute all start_date and end_date fields for existing records
    env['hr.attendance'].recompute_all_start_end_times()

