from odoo import _, api, fields, models
from collections import defaultdict
from odoo.exceptions import ValidationError, UserError
from odoo.osv.expression import AND

from datetime import datetime, timedelta
import pdb



class PurchaseQuotation(models.Model):
    _name = 'purchase.quotation'
    _description = 'Purchase Quotation'
    _inherit = ["mail.thread", "mail.activity.mixin", "analytic.mixin"]

    name = fields.Char(string="Quotation Reference", required=True, copy=False, readonly=True, default=lambda self: 'New')
    material_request_id = fields.Many2one('material.request', string="Material Request", readonly=True)
    purchase_request_id = fields.Many2one('purchase.request', string="Purchase Request", required=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string="Vendor")
    date_order = fields.Datetime(string="Quotation Date", default=fields.Datetime.now, required=True, readonly=True)
    quality_evaluation = fields.Boolean(string="Quality Evaluation")
    created_by = fields.Many2one('res.users', string="Created By", readonly=True)
    rejection_reason = fields.Text(string="Rejection Reason", readonly=True)
    procurement_type = fields.Selection([
        ('pay_to_procure', 'Pay to Procure'),
        ('procure_to_pay', 'Procure to Pay')
    ], string="Procurement Type", required=True,readonly=True)
    quotation_line_ids = fields.One2many('purchase.quotation.line', 'quotation_id', string="Quotation Lines")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent to Vendor'),
        ('received', 'Received'),
        ('rejected', 'Rejected')
    ], string="Status", default='draft', required=True,tracking=True)
    amount_total = fields.Float(string="Total Amount", compute="_compute_amount_total", store=True)
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

    # True only when at least one line has price and at least one line has no price
    needs_receive_confirm = fields.Boolean(string="Needs Receive Confirm", compute="_compute_needs_receive_confirm", store=False)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('purchase.quotation') or 'New'
        return super(PurchaseQuotation, self).create(vals)

    
    @api.depends('quotation_line_ids.subtotal')
    def _compute_amount_total(self):
        for quotation in self:
            quotation.amount_total = sum(line.subtotal for line in quotation.quotation_line_ids)

    @api.depends('quotation_line_ids', 'quotation_line_ids.unit_price')
    def _compute_needs_receive_confirm(self):
        for quotation in self:
            if not quotation.quotation_line_ids:
                quotation.needs_receive_confirm = False
                continue
            prices = [line.unit_price or 0.0 for line in quotation.quotation_line_ids]
            any_priced = any(p > 0.0 for p in prices)
            any_unpriced = any(p <= 0.0 for p in prices)
            quotation.needs_receive_confirm = bool(any_priced and any_unpriced)

    def action_send_to_vendor(self):
        multi_company_partners = self.env['res.company'].search([]).mapped('partner_id')
        
        for quotation in self:
            if not quotation.partner_id:
                raise UserError(_("You must select a vendor before sending the quotation."))

        self.state = 'sent'

   

    def action_receive(self):
        for quotation in self:
            # Check if at least one line has a unit price
            lines_with_price = quotation.quotation_line_ids.filtered(lambda l: l.unit_price > 0)
            if not lines_with_price:
                raise ValidationError(_("At least one line must have a Unit Price before completing the quotation."))

            quotation.state = 'received'


    def action_reject(self):
        self.state = 'rejected'

    def action_reset_to_draft(self):
        """Reset quotation to draft state"""
        self.ensure_one()
        self.write({'state': 'draft'})

class PurchaseQuotationLine(models.Model):
    _name = 'purchase.quotation.line'
    _description = 'Purchase Quotation Line'

    @api.model_create_multi
    def create(self, vals_list):
        # Prevent manual creation of quotation lines
        # Allow creation only if context flag 'allow_create_quotation_line' is set (for programmatic creation)
        if not self.env.context.get('allow_create_quotation_line'):
            raise UserError(_('Purchase quotation lines cannot be created manually. They must be created through the purchase request workflow.'))
        return super().create(vals_list)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent to Vendor'),
        ('received', 'Received'),
        ('rejected', 'Rejected')
    ], string="Status", related='quotation_id.state')
    quotation_id = fields.Many2one('purchase.quotation', string="Quotation", ondelete='cascade', required=True)
    product_id = fields.Many2one('product.product', string="Product", required=True, readonly=True)
    description = fields.Text(string="Description", readonly=True)
    product_uom_id = fields.Many2one(
        'uom.uom',
        string="Unit of Measure",
        readonly=True,
        store=True
    )
    quantity = fields.Float(string="Quantity", required=True, default=1.0)
    unit_price = fields.Float(string="Unit Price", required=True)
    subtotal = fields.Float(string="Subtotal", compute="_compute_subtotal", store=True)

    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price
