from odoo import _, api, fields, models
from collections import defaultdict
from odoo.exceptions import ValidationError, UserError
from odoo.osv.expression import AND

from datetime import datetime, timedelta
import pdb



class ProductSIV(models.Model):
    _name = 'product.siv'
    _description = 'Product Store Issue Voucher (SIV)'
    _inherit = ["mail.thread", "mail.activity.mixin", "analytic.mixin"]

    name = fields.Char(
        string="SIV Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )

    requested_date = fields.Date(
        string="Requested Date",
        required=True,
        default=fields.Date.today,
        help="Date when the SIV was requested",
        readonly=True,
    )

    picking_ids = fields.One2many('stock.picking','siv_id', string="Pickings")
    picking_count = fields.Integer(string="Picking Count", compute="_compute_picking_count")

    def _compute_picking_count(self):
        for record in self:
            record.picking_count = 1 if record.picking_id else 0

    def action_deliver(self):
        """Create stock picking for the SIV lines and set the state to delivered."""
        if self.state != 'approved':
            raise UserError(_("Only approved SIVs can be delivered."))

        if not self.product_siv_line_ids:
            raise UserError(_("There are no SIV lines to create a stock picking."))

        # Create Stock Picking
        picking_vals = {
            'partner_id': self.material_request_id.requested_by_id.partner_id.id if self.material_request_id.requested_by_id else None,
            'location_id': self.operation_type_id.default_location_src_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'picking_type_id': self.operation_type_id.id,
            'origin': self.name,
            'siv_id': self.id,
            'move_type': 'direct',
            'state': 'draft',
        }
        picking = self.env['stock.picking'].create(picking_vals)

        # Create Stock Moves within Picking
        for line in self.product_siv_line_ids:
            if line.requested_qty <= 0:
                raise UserError(_("Requested quantity must be greater than zero for product %s.") % line.product_id.name)

            self.env['stock.move'].create({
                'picking_id': picking.id,
                'product_id': line.product_id.id,
                'name': f"SIV: {self.name} - {line.product_id.display_name}",
                'product_uom_qty': line.requested_qty,
                'product_uom': line.product_id.uom_id.id,
                'material_request_line_id': line.material_request_line_id.id,
                'location_id': self.operation_type_id.default_location_src_id.id,
                'location_dest_id': self.env.ref('stock.stock_location_customers').id,
                'state': 'draft',
            })


        self.state = 'delivered'
        self.issued_by = self.env.user.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': picking.id,
            'target': 'current',
        }


    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('product.siv') or _('New')
        return super(ProductSIV, self).create(vals)

    material_request_id = fields.Many2one('material.request', string="Material Request")
    requested_by = fields.Many2one('res.users', string="Requested By", required=True)
    approved_by_id = fields.Many2one('res.users', string="Approved By")
    issued_by = fields.Many2one('res.users', string="Issued By")
    state = fields.Selection([('draft', 'Draft'), ('request_approval', 'Request Approval'), ('approved', 'Approved'), ('delivered', 'Delivered')], string="State", default='draft', required=True)
    operation_type_id = fields.Many2one('stock.picking.type', string="Operation Type", domain="[('code', '=', 'outgoing')]", required=True)
    product_siv_line_ids = fields.One2many('product.siv.line', 'product_siv_id', string="SIV Lines")
    company_id = fields.Many2one(
        'res.company',
        string="Company",readonly="1",force_save="1",
        required=True,
        default=lambda self: self.env.company
    )

    user_id = fields.Many2one(
        'res.users',
        string="Purchaser",
        domain=lambda self: [
            ('groups_id', 'in', self.env.ref('purchase.group_purchase_user').id),
            ('company_ids', 'in', self.env.context.get('allowed_company_ids', []))
        ],
    )

    @api.depends('approved_by_id')
    def _compute_approved_by_char(self):
        for record in self:
            record.approved_by_char = record.approved_by_id.name if record.approved_by_id else ""

    @api.depends('issued_by')
    def _compute_approved_by_chars(self):
        for record in self:
            record.approved_by_chars = record.issued_by.name if record.issued_by else ""

    def action_request_approval(self):
        """Set state to request approval and notify approvers."""
        for record in self:
            record.state = 'request_approval'

    def action_approve(self):
        for record in self:
            record.approved_by_id = self.env.user.id  # Set the approved_by field properly
            record.state = 'approved'





    def action_view_moves(self):
        """Open the related stock moves."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Stock Moves',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('siv_id', '=', self.id)],
            'context': dict(self.env.context, create=False),
        }


class ProductSIVLine(models.Model):
    _name = 'product.siv.line'
    _description = 'Product SIV Line'

    product_siv_id = fields.Many2one('product.siv', string="SIV Reference", ondelete='cascade', required=True)
    product_id = fields.Many2one('product.product', string="Product", required=True)
    material_request_line_id = fields.Many2one('material.request.line', string="Material Request Line", required=True)
    requested_qty = fields.Float(string="Requested Quantity", required=True)
    issued_qty = fields.Float(string="Issued Quantity", required=True)
