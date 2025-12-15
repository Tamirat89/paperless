from odoo import _, api, fields, models
from collections import defaultdict
from odoo.exceptions import ValidationError, UserError
from odoo.osv.expression import AND

from datetime import datetime, timedelta
import pdb
class StockLocation(models.Model):
    _inherit = 'stock.location'

    located_company_id = fields.Many2one(
        'res.company',
        string="Located in",
        default=lambda self: self.env.company
    )

class StockPickingLine(models.Model):
    _inherit = 'stock.move'

    material_request_line_id = fields.Many2one("material.request.line")
    product_siv_line_id = fields.Many2one("product.siv.line")


class StockPickingUpdate(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        """Override button_validate to update material request lines and handle purchase order state."""
        # Avoid recursion by ensuring this is not re-entered
        if self._context.get('button_validate_recursion'):
            return super(StockPickingUpdate, self).button_validate()

        # Call the original button_validate method
        res = super(StockPickingUpdate, self.with_context(button_validate_recursion=True)).button_validate()

        # Update purchase order state if linked
        for picking in self:
            purchase_orders = picking.move_ids_without_package.mapped('purchase_line_id.order_id')
            for po in purchase_orders:
                if po and po.state not in ['done', 'cancel']:
                    po.write({'state': 'credit_settlement'})
                    po.message_post(body=_("State updated to Credit Settlement after stock picking validation."))


        # Update delivered_qty in material request lines
        for move in self.move_ids:
            if move.material_request_line_id:
                delivered_qty = move.quantity
                if delivered_qty > 0:
                    material_request_line = move.material_request_line_id
                    material_request_line.sudo().write({
                        'delivered_qty': material_request_line.delivered_qty + delivered_qty,
                    })


        return res


class MaterialRequest(models.Model):
    _name = 'material.request'
    _description = 'Material Request'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('approval_requested', 'Approval Requested'),
        ('approved', 'Approved'),
        ('pr', 'Purchase Request'),
        ('siv', 'Store Issue Voucher'),
        ('delivered', 'Delivered')
    ], string='State', default='draft')
    name = fields.Char(
        string="Request Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('material.request') or _('New')
        return super(MaterialRequest, self).create(vals)

    def action_view_siv(self):
        self.ensure_one()
        action = self.env.ref('custom_purchase_process.action_product_siv').read()[0]
        action['domain'] = [('material_request_id', '=', self.id)]
        action['context'] = dict(self.env.context, default_material_request_id=self.id)
        return action

    purchase_request_count = fields.Integer(string="Purchase Request Count", compute="_compute_purchase_request_count")

    def _compute_purchase_request_count(self):
        for record in self:
            record.purchase_request_count = self.env['purchase.request'].search_count([('material_request_id', '=', record.id)])

    def action_view_purchase_requests(self):
        """Open related Purchase Requests."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Requests',
            'res_model': 'purchase.request',
            'view_mode': 'list,form',
            'domain': [('material_request_id', '=', self.id)],
            'context': dict(self.env.context, default_material_request_id=self.id),
        }



    date_requested = fields.Datetime(string="Date Requested", default=fields.Datetime.now)
    date_approved = fields.Datetime(string="Date Approved")

    requested_by_id = fields.Many2one('res.users', string="Requested By", default=lambda self: self.env.user)
    approved_by_id = fields.Many2one('res.users', string="Approved By")

    requested_by_char = fields.Char(string="Requested By (Name)", compute="_compute_requested_by_char", store=True)
    approved_by_char = fields.Char(string="Approved By (Name)", compute="_compute_approved_by_char", store=True)

    requesting_company_id = fields.Many2one('res.company', string="Requesting Company",
                                            default=lambda self: self.env.company)
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        default=lambda self: self.env.company
    )
    from_location_id = fields.Many2one(
        "stock.location",
        string="Store",
        domain="[('company_id', '=', company_id),('usage','=','internal')]"
    )

    picking_type_id = fields.Many2one(
        "stock.picking.type",
        string="SIV Voucher",
        domain="[('default_location_src_id', '=', from_location_id), ('code', '=', 'outgoing')]"
    )

    generate_siv = fields.Boolean(string="Generate SR")
    generate_pr = fields.Boolean(string="Generate PR")

    material_request_line_ids = fields.One2many(
        'material.request.line',
        'material_request_id',
        string="Material Request Lines"
    )

    siv_count = fields.Integer(string="SIV Count", compute="_compute_siv_count")


    def _compute_siv_count(self):
        for record in self:
            record.siv_count = self.env['product.siv'].search_count([('material_request_id', '=', record.id)])



    def check_stock(self):
        if not self.from_location_id:
            raise UserError(_("Please specify a source location (Store) before checking stock."))

        for line in self.material_request_line_ids:
            if not line.product_id:
                continue
            available_qty = self.env['stock.quant']._get_available_quantity(line.product_id, self.from_location_id)
            line.available_qty = available_qty
            line.pr_qty = line.requested_qty
            line.siv_qty = line.requested_qty

        return True

    @api.depends('requested_by_id')
    def _compute_requested_by_char(self):
        for record in self:
            record.requested_by_char = record.requested_by_id.name if record.requested_by_id else ""

    @api.depends('approved_by_id')
    def _compute_approved_by_char(self):
        for record in self:
            record.approved_by_char = record.approved_by_id.name if record.approved_by_id else ""

    def action_submit(self):
        """Move to 'Approval Requested'"""
        if not self.material_request_line_ids:
            raise ValidationError(_("You cannot submit a request without any material lines."))
        self.state = 'approval_requested'

    def action_approve(self):
        """Move to 'Approved'"""
        if self.state != 'approval_requested':
            raise UserError(_("Only requests in 'Approval Requested' state can be approved."))

        self.state = 'approved'
        self.check_stock()
        self.approved_by_id = self.env.user.id
        self.date_approved = fields.Datetime.now()

    def action_reject(self):
        """Move back to 'Draft'"""
        if self.state not in ['approval_requested', 'pr', 'siv']:
            raise UserError(_("Only certain states can be rejected."))
        self.state = 'draft'

    def action_create_pr(self):
        """Move to 'Purchase Request' and create a Purchase Request."""
        if self.state != 'approved':
            raise UserError(_("Only approved requests can generate a Purchase Request."))

        if not self.material_request_line_ids:
            raise UserError(_("No material request lines to create a Purchase Request."))

        # Create Purchase Request
        pr_vals = {
            'name': self.env['ir.sequence'].next_by_code('purchase.request') or _('New'),
            'material_request_id': self.id,
            'date_requested': fields.Datetime.now(),
            'requested_by': self.env.user.id,
            'company_id': self.env.company.id,
        }
        purchase_request = self.env['purchase.request'].create(pr_vals)

        # Create Purchase Request Lines
        for line in self.material_request_line_ids:
            self.env['purchase.request.line'].with_context(allow_create_purchase_request_line=True).create({
                'purchase_request_id': purchase_request.id,
                'material_request_line_id': line.id,
                'product_id': line.product_id.id,
                'description': line.product_id.display_name,
                'quantity': line.pr_qty,
                'unit_price': 0.0,  # Initialize with 0.0; to be updated during procurement
            })

        # Update Material Request state and flag
        self.state = 'pr'
        self.generate_pr = True

        # Open the created Purchase Request in form view
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.request',
            'view_mode': 'form',
            'res_id': purchase_request.id,
            'target': 'current',
        }

    def action_create_siv(self):
        """Move to 'Store Issue Voucher' and create Product SIV"""

        if not self.material_request_line_ids:
            raise UserError(_("There are no material request lines to create a Store Issue Voucher."))
        for line in self.material_request_line_ids:
            if line.siv_qty > line.requested_qty:
                raise UserError(_("You cannot issue more than requested."))

        # Create the Product SIV record
        siv = self.env['product.siv'].create({
            'material_request_id': self.id,
            'requested_by': self.requested_by_id.id,
            'state': 'draft',
            'operation_type_id': self.picking_type_id.id,  # Ensure picking_type_id exists in your model
        })

        # Create lines for Product SIV based on Material Request lines
        for line in self.material_request_line_ids:
            if line.siv_qty > 0:
                self.env['product.siv.line'].create({
                    'product_siv_id': siv.id,
                    'material_request_line_id':line.id,
                    'product_id': line.product_id.id,
                    'requested_qty': line.siv_qty,
                    'issued_qty': 0.0,  # Set initial issued quantity to 0
                })

        # Update the state and flags
        self.generate_siv = False
        self.state = 'siv'
        self.generate_siv = True

        # Open the created Product SIV record in form view
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.siv',
            'view_mode': 'form',
            'res_id': siv.id,
            'target': 'current',
        }

    def action_deliver(self):
        """Mark as Delivered"""
        if self.state != 'siv':
            raise UserError(_("Only requests in 'Store Issue Voucher' state can be marked as delivered."))
        self.state = 'delivered'

class MaterialRequestLine(models.Model):
    _name = 'material.request.line'
    _description = 'Material Request Line'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('approval_requested', 'Approval Requested'),
        ('approved', 'Approved'),
        ('pr', 'Purchase Request'),
        ('siv', 'Store Issue Voucher'),
        ('delivered', 'Delivered')
    ], string='State', related='material_request_id.state')

    material_request_id = fields.Many2one(
        'material.request',
        string="Material Request",
        ondelete='cascade'
    )

    product_id = fields.Many2one(
        'product.product',
        string="Product",
        required=True
    )
    generate_siv = fields.Boolean(string="Generate SIV",related="material_request_id.generate_siv")
    generate_pr = fields.Boolean(string="Generate PR",related="material_request_id.generate_pr")

    requested_qty = fields.Float(string="Requested Quantity", required=True)
    available_qty = fields.Float(string="Available Quantity")
    delivered_qty = fields.Float(string="Delivered Quantity", default=0.0)
    pr_qty = fields.Float(string="Purchase Request Quantity", default=0.0)
    siv_qty = fields.Float(string="Store Issue Voucher Quantity", default=0.0)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    siv_id = fields.Many2one('product.siv', string="SIV Reference")

    @api.model
    def action_done(self):
        res = super(StockPicking, self).action_done()

        # Check if this picking is linked to a product.siv
        for picking in self:
            if picking.siv_id:
                siv = picking.siv_id
                # Update the state of the associated product.siv to 'delivered'
                siv.state = 'delivered'

        return res

class PurchaseRequest(models.Model):
    _name = 'purchase.request'
    _description = 'Purchase Request'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'company_id' in vals:
                # Apply the company context
                self = self.with_company(vals['company_id'])
            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals.get('date_request'))
                ) if 'date_request' in vals else None
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'purchase.request', sequence_date=seq_date) or _("New")
        return super(PurchaseRequest, self).create(vals_list)

    name = fields.Char(string="Request Reference", required=True, copy=False, readonly=True, default=lambda self: 'New')
    material_request_id = fields.Many2one('material.request', string="Material Request")
    date_requested = fields.Date(string="Date Requested", default=fields.Datetime.now, required=True)
    requested_by = fields.Many2one('res.users', string="Requested By", required=True, default=lambda self: self.env.user)
    approved_by = fields.Many2one('res.users', string="Approved By")
    quality_evaluation = fields.Boolean(string="Quality Assurance")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rfq', 'RFQ'),
        ('supplier_analysis', 'Supplier Analysis'),
        ('quality_evaluation', 'Quality Evaluation'),
        ('purchase_order', 'Purchase Order'),
        ('rejected', 'Rejected')
    ], string="Status", default='draft', required=True)

    purchase_request_line_ids = fields.One2many('purchase.request.line', 'purchase_request_id', string="Request Lines")
    purchase_order_ids = fields.One2many('purchase.order', 'purchase_request_id', string="Purchase Orders")
    company_id = fields.Many2one('res.company', string="Company", required=True, default=lambda self: self.env.company)
    total_amount = fields.Float(string="Total Amount", compute="_compute_total_amount", store=True)
    company_id = fields.Many2one(
        'res.company',
        string="Company",
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

    quotation_count = fields.Integer(string="Quotation Count", compute="_compute_quotation_count")

    def action_generate_purchase_order(self):
        """Generate Purchase Order based on selected Supplier Analysis."""
        self.ensure_one()
        if not self.state == 'supplier_analysis':
            raise UserError(_("Purchase orders can only be generated in the 'Supplier Analysis' state."))

        # Get selected supplier analysis lines
        selected_lines = self.env['supplier.analysis.line'].search([
            ('analysis_id.purchase_request_id', '=', self.id),
            ('selected', '=', True)
        ])

        if not selected_lines:
            raise UserError(_("No supplier analysis lines have been marked as selected."))

        # Group lines by vendor (partner_id)
        grouped_lines = {}
        for line in selected_lines:
            if line.partner_id.id not in grouped_lines:
                grouped_lines[line.partner_id.id] = []
            grouped_lines[line.partner_id.id].append(line)

        purchase_orders = []

        # Create Purchase Orders for each vendor
        for partner_id, lines in grouped_lines.items():
            # Prepare purchase order values
            po_vals = {
                'partner_id': partner_id,
                'origin': self.name,
                'date_order': fields.Datetime.now(),
                'purchase_request_id': self.id,
            }
            purchase_order = self.env['purchase.order'].create(po_vals)
            purchase_orders.append(purchase_order)

            # Add lines to the purchase order
            for line in lines:
                self.env['purchase.order.line'].create({
                    'order_id': purchase_order.id,
                    'product_id': line.product_id.id,
                    'name': line.name or line.product_id.name,
                    'price_unit': line.unit_price,
                    'product_qty': line.quantity,  # Default quantity, adjust if necessary
                    'date_planned': fields.Datetime.now(),
                })

        # Transition to Purchase Order state
        self.state = 'purchase_order'

        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Orders'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', [po.id for po in purchase_orders])],
            'target': 'current',
        }

    def action_generate_purchase_request(self):
        """Generate Purchase Requests based on Sales Request Lines."""
        self.ensure_one()
        if not self.request_lines:
            raise UserError(_("No request lines available to generate a Purchase Request."))

        purchase_request_model = self.env['purchase.request']
        purchase_request_line_model = self.env['purchase.request.line']

        # Create the Purchase Request
        purchase_request = purchase_request_model.create({
            'name': self.env['ir.sequence'].next_by_code('purchase.request') or _('New'),
            'material_request_id': None,  # Link to a material request if applicable
            'date_requested': fields.Datetime.now(),
            'requested_by': self.env.user.id,
            'company_id': self.env.company.id,
        })

        # Create Purchase Request Lines
        for line in self.request_lines:
            if not line.product_id or not line.quantity:
                raise UserError(_("Please ensure all request lines have a product and quantity specified."))

            purchase_request_line_model.with_context(allow_create_purchase_request_line=True).create({
                'purchase_request_id': purchase_request.id,
                'product_id': line.product_id.id,
                'description': line.product_id.name or line.description,
                'quantity': line.quantity,
                'unit_price': line.cost_price,
            })

        # Link the purchase request to the sales request
        self.procurement_ids = [(4, purchase_request.id)]
        self.state = 'procurement'

        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Request'),
            'res_model': 'purchase.request',
            'view_mode': 'form',
            'res_id': purchase_request.id,
            'target': 'current',
        }

    def _compute_quotation_count(self):
        for record in self:
            record.quotation_count = self.env['purchase.quotation'].search_count([('purchase_request_id', '=', record.id)])

    def action_view_quotations(self):
        """Open the related purchase quotations."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Quotations',
            'res_model': 'purchase.quotation',
            'view_mode': 'list,form',
            'domain': [('purchase_request_id', '=', self.id)],
            'context': dict(self.env.context, create=False),
        }

    def action_view_sa(self):
        """Open the related purchase quotations."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Supplier Analysis',
            'res_model': 'supplier.analysis',
            'view_mode': 'list,form',
            'domain': [('purchase_request_id', '=', self.id)],
            'context': dict(self.env.context, create=False),
        }

    def action_view_po(self):
        """Open the related purchase quotations."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Orders',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('purchase_request_id', '=', self.id)],
            'context': dict(self.env.context, create=False),
        }


    @api.depends('purchase_request_line_ids.subtotal')
    def _compute_total_amount(self):
        for request in self:
            request.total_amount = sum(line.subtotal for line in request.purchase_request_line_ids)

    def action_submit(self):
        self.state = 'submitted'

    def action_approve(self):
        if not self.user_id:
            raise UserError(_("Please assign a purchaser first."))

        self.state = 'approved'

    def action_set_rfq(self):
        """Set state to RFQ and create a Purchase Quotation."""
        if not self.purchase_request_line_ids:
            raise UserError(_("No purchase request lines to generate a quotation."))


        # Create Purchase Quotation
        quotation_vals = {
            'name': self.env['ir.sequence'].next_by_code('purchase.quotation') or _('New'),
            'material_request_id': self.material_request_id.id if self.material_request_id else None,
            'purchase_request_id': self.id,
            'quality_evaluation': self.quality_evaluation,
            'partner_id': None,  # To be filled later with the vendor
            'date_order': fields.Datetime.now(),
            'procurement_type': 'pay_to_procure',  # Default type, change if necessary
            'state': 'draft',
        }
        quotation = self.env['purchase.quotation'].create(quotation_vals)

        # Create Quotation Lines
        for line in self.purchase_request_line_ids:
            self.env['purchase.quotation.line'].with_context(allow_create_quotation_line=True).create({
                'quotation_id': quotation.id,
                'product_id': line.product_id.id,
                'description': line.description or line.product_id.name,
                'quantity': line.quantity,
                'unit_price': 0.0,
            })

        # Transition to RFQ state
        self.state = 'rfq'

        # Return the created quotation for review
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Quotation',
            'res_model': 'purchase.quotation',
            'view_mode': 'form',
            'res_id': quotation.id,
            'target': 'current',
        }

    def action_set_proforma(self):
        self.state = 'proforma'

    def action_set_supplier_analysis(self):
        self.ensure_one()
        self.state = 'supplier_analysis'
        if not self.purchase_request_line_ids:
            raise UserError(_("No lines found in the purchase request to generate the Supplier Analysis."))

        # Create Supplier Analysis
        supplier_analysis = self.env['supplier.analysis'].create({
            'purchase_request_id': self.id,
            'state': 'draft',
            'date_requested': fields.Datetime.now(),
            'requested_by': self.env.user.id,
        })

        product_lines = []
        for request_line in self.purchase_request_line_ids:
            # Search all purchase quotations related to this purchase request
            quotations = self.env['purchase.quotation'].search([
                ('purchase_request_id', '=', self.id)
            ])

            if not quotations:
                continue

            qa_required = False
            # Loop through all quotations and gather vendor offers for the current product
            for quotation in quotations:
                quotation_line = quotation.quotation_line_ids.filtered(
                    lambda ql: ql.product_id == request_line.product_id)
                if quotation_line:
                    if request_line.qa_required:
                        qa_required = True
                    product_lines.append({
                        'analysis_id': supplier_analysis.id,
                        'product_id': quotation_line.product_id.id,
                        'partner_id': quotation.partner_id.id,
                        'name': quotation_line.description,
                        'quantity':request_line.quantity,
                        'chosen_for_inspection':request_line.qa_required,
                        'unit_price': quotation_line.unit_price,
                    })
            if qa_required:
                supplier_analysis.qa_required = True
        if not product_lines:
            raise UserError(_("No quotations were found for the products in this purchase request."))

        # Create supplier analysis lines
        self.env['supplier.analysis.line'].with_context(allow_create_supplier_analysis_line=True).create(product_lines)



        return {
            'type': 'ir.actions.act_window',
            'name': 'Supplier Analysis',
            'res_model': 'supplier.analysis',
            'view_mode': 'form',
            'res_id': supplier_analysis.id,
            'target': 'current',
        }
    def action_set_purchase_order(self):
        self.state = 'purchase_order'




    def action_reject(self):
        self.state = 'rejected'

class PurchaseRequestLine(models.Model):
    _name = 'purchase.request.line'
    _description = 'Purchase Request Line'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rfq', 'RFQ'),
        ('supplier_analysis', 'Supplier Analysis'),
        ('purchase_order', 'Purchase Order'),
        ('rejected', 'Rejected')
    ], string="Status", related='purchase_request_id.state')
    purchase_request_id = fields.Many2one('purchase.request', string="Purchase Request", ondelete='cascade', required=True)
    material_request_line_id = fields.Many2one('material.request.line', string="Material Request Line")
    product_id = fields.Many2one('product.product', string="Product", readonly=True)
    description = fields.Text(string="Description")
    quantity = fields.Float(string="Quantity")
    unit_price = fields.Float(string="Est. Price", required=True)
    subtotal = fields.Float(string="Subtotal", compute="_compute_subtotal", store=True)
    qa_required = fields.Boolean("QA")

    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price

class PurchaseQuotation(models.Model):
    _name = 'purchase.quotation'
    _description = 'Purchase Quotation'

    name = fields.Char(string="Quotation Reference", required=True, copy=False, readonly=True, default=lambda self: 'New')
    material_request_id = fields.Many2one('material.request', string="Material Request")
    purchase_request_id = fields.Many2one('purchase.request', string="Purchase Request", required=True)
    partner_id = fields.Many2one('res.partner', string="Vendor")
    date_order = fields.Datetime(string="Quotation Date", default=fields.Datetime.now, required=True)
    quality_evaluation = fields.Boolean(string="Quality Evaluation")
    procurement_type = fields.Selection([
        ('pay_to_procure', 'Pay to Procure'),
        ('procure_to_pay', 'Procure to Pay')
    ], string="Procurement Type", required=True)
    quotation_line_ids = fields.One2many('purchase.quotation.line', 'quotation_id', string="Quotation Lines")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent to Vendor'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected')
    ], string="Status", default='draft', required=True)
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

    @api.depends('quotation_line_ids.subtotal')
    def _compute_amount_total(self):
        for quotation in self:
            quotation.amount_total = sum(line.subtotal for line in quotation.quotation_line_ids)

    def action_send_to_vendor(self):
        self.state = 'sent'

    def action_accept(self):
        self.state = 'accepted'

    def action_reject(self):
        self.state = 'rejected'

class PurchaseQuotationLine(models.Model):
    _name = 'purchase.quotation.line'
    _description = 'Purchase Quotation Line'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent to Vendor'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected')
    ], string="Status", related='quotation_id.state')
    quotation_id = fields.Many2one('purchase.quotation', string="Quotation", ondelete='cascade', required=True)
    product_id = fields.Many2one('product.product', string="Product", required=True)
    description = fields.Text(string="Description")
    quantity = fields.Float(string="Quantity", required=True, default=1.0)
    unit_price = fields.Float(string="Unit Price", required=True)
    subtotal = fields.Float(string="Subtotal", compute="_compute_subtotal", store=True)

    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price

class SupplierAnalysis(models.Model):
    _name = 'supplier.analysis'
    _description = 'Supplier Analysis'

    def action_view_po(self):
        """Open the related purchase quotations."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Orders',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('purchase_request_id', '=', self.purchase_request_id.id)],
            'context': dict(self.env.context, create=False),
        }
    name = fields.Char(
        string="Analysis Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('committee_approved', 'Committee Approved'),
        ('gm_approved', 'GM Approved'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default='draft', required=True)

    def action_view_sa(self):
        """Open the related purchase quotations."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quality Inspection',
            'res_model': 'quality.inspection',
            'view_mode': 'list,form',
            'domain': [('supplier_analysis_id', '=', self.id)],
            'context': dict(self.env.context, create=False),
        }

    def action_generate_quality_inspection(self):

        quality_inspection_model = self.env['quality.inspection']
        for record in self:
            # Group selected lines by vendor
            selected_lines_by_vendor = {}
            for line in record.supplier_analysis_lines.filtered(lambda l: l.selected):
                if not line.partner_id:
                    raise UserError(_("Each selected line must have a vendor assigned."))
                if line.partner_id.id not in selected_lines_by_vendor:
                    selected_lines_by_vendor[line.partner_id.id] = []
                selected_lines_by_vendor[line.partner_id.id].append(line)

            if not selected_lines_by_vendor:
                raise UserError(_("No lines selected for inspection."))

            # Create a Quality Inspection for each vendor
            for vendor_id, lines in selected_lines_by_vendor.items():
                quality_inspection = quality_inspection_model.create({
                    'name': self.env['ir.sequence'].next_by_code('quality.inspection') or _('New'),
                    'supplier_analysis_id': record.id,
                    'partner_id': vendor_id,
                    'quality_inspections_line_ids': [(0, 0, {
                        'supplier_analysis_line_id': line.id,
                        'product_id': line.product_id.id,
                        'name': line.name,
                        'passed_inspection': False,
                        'inspection_remark': '',
                    }) for line in lines],
                })


        self.state = 'quality_inspection'
        return True

    def action_in_progress(self):
        """Move to 'In Progress' state."""
        if self.state != 'draft':
            raise UserError(_("Only records in Draft state can be moved to In Progress."))
        self.state = 'in_progress'

    def action_department_approve(self):
        """Move to 'Department Approved' state."""
        if self.state != 'in_progress':
            raise UserError(_("Only records In Progress can be Department Approved."))

        for record in self:
            # Filter selected lines
            selected_lines = record.supplier_analysis_lines.filtered(lambda l: l.selected)
            if not selected_lines:
                raise UserError(_("At least one product must be selected for Department Approval."))

            for line in selected_lines:
                # Ensure related material request lines exist for the selected product
                if record.purchase_request_id.material_request_id:
                    matching_request_lines = record.purchase_request_id.material_request_id.material_request_line_ids.filtered(
                        lambda x: x.product_id.id == line.product_id.id
                    )

                    if not matching_request_lines:
                        raise UserError(_(
                            "No matching material request line found for the product: %s." % line.product_id.display_name
                        ))

                    # Update the related material request line with vendor and cost information
                    # Only update if fields exist on the model
                    for request_line in matching_request_lines:
                        if hasattr(request_line, 'supplier_id') and hasattr(request_line, 'cost_price'):
                            request_line.supplier_id = line.partner_id.id
                            request_line.cost_price = line.unit_price

                purchase_request_lines = record.purchase_request_id.purchase_request_line_ids.filtered(
                    lambda x: x.product_id.id == line.product_id.id
                )

                # Update the related purchase request line with vendor and cost information
                for request_line in purchase_request_lines:
                    request_line.unit_price = line.unit_price
                    request_line.subtotal = line.unit_price * request_line.quantity

        # Update the state to 'committee_approved'
        self.state = 'committee_approved'


    def action_committee_approvez(self):
        """Move to 'Committee Approved' state."""
        if self.state != 'in_progress':
            raise UserError(_("Only records In Progress can be Committee Approved."))
        self.state = 'committee_approved'
        for record in self:
            # On supplier analysis to to purchase request and get the sales_request_id

            for line in record.supplier_analysis_lines.filtered(lambda l: l.selected):
                if record.purchase_request_id.material_request_id:
                    for x in record.purchase_request_id.material_request_id.material_request_line_ids:
                        if x.product_id.id == line.product_id.id:
                            if hasattr(x, 'supplier_id') and hasattr(x, 'cost_price'):
                                x.supplier_id = line.partner_id.id
                                x.cost_price = line.unit_price

    def action_gm_approve(self):
        """Move to 'GM Approved' state."""
        for line in self.supplier_analysis_lines:
            if line.chosen_for_inspection and not line.passed_inspection:
                raise UserError(_("You have selected Items that have failed inspection."))

        self.state = 'gm_approved'

    def action_done(self):
        """Move to 'Done' state."""

        """Generate Purchase Order based on selected Supplier Analysis."""
        self.ensure_one()

        # Get selected supplier analysis lines
        selected_lines = self.env['supplier.analysis.line'].search([
            ('analysis_id.purchase_request_id', '=', self.purchase_request_id.id),
            ('selected', '=', True)
        ])

        if not selected_lines:
            raise UserError(_("No supplier analysis lines have been marked as selected."))

        # Group lines by vendor (partner_id)
        grouped_lines = {}
        for line in selected_lines:
            if line.partner_id.id not in grouped_lines:
                grouped_lines[line.partner_id.id] = []
            grouped_lines[line.partner_id.id].append(line)

        purchase_orders = []

        # Create Purchase Orders for each vendor
        for partner_id, lines in grouped_lines.items():
            # Prepare purchase order values
            po_vals = {
                'partner_id': partner_id,
                'origin': self.purchase_request_id.name,
                'date_order': fields.Datetime.now(),
                'purchase_request_id': self.purchase_request_id.id,
            }
            purchase_order = self.env['purchase.order'].create(po_vals)
            purchase_orders.append(purchase_order)

            # Add lines to the purchase order
            for line in lines:
                self.env['purchase.order.line'].create({
                    'order_id': purchase_order.id,
                    'product_id': line.product_id.id,
                    'name': line.name or line.product_id.name,
                    'price_unit': line.unit_price,
                    'product_qty': line.quantity,  # Default quantity, adjust if necessary
                    'date_planned': fields.Datetime.now(),
                })

        # Transition to Purchase Order state
        self.state = 'done'
        self.purchase_request_id.state = 'purchase_order'

        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Orders'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', [po.id for po in purchase_orders])],
            'target': 'current',
        }

    def action_cancel(self):
        """Move to 'Cancelled' state."""
        if self.state not in ['draft', 'in_progress', 'committee_approved', 'gm_approved']:
            raise UserError(_("Only certain states can be cancelled."))
        self.state = 'cancelled'

    def action_reset_to_draft(self):
        """Move back to 'Draft' state."""
        self.state = 'draft'
    date_requested = fields.Date(string="Date Requested", default=fields.Datetime.now, required=True)
    requested_by = fields.Many2one('res.users', string="Requested By", required=True, default=lambda self: self.env.user)
    approved_by = fields.Many2one('res.users', string="Approved By")
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
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('supplier.analysis') or _('New')
        return super(SupplierAnalysis, self).create(vals)

    purchase_request_id = fields.Many2one('purchase.request', string="Purchase Request", required=True)
    committee_remark = fields.Char("Committee Remark")
    supplier_analysis_lines = fields.One2many('supplier.analysis.line', 'analysis_id', string="Product Lines")
    qa_required = fields.Boolean("QA Required")

class SupplierAnalysisLine(models.Model):
    _name = 'supplier.analysis.line'
    _description = 'Supplier Analysis Line'


    @api.onchange("selected")
    def selected_inspection(self):
        for rec in self:
            if rec.selected:
                rec.chosen_for_inspection = True
            else:
                rec.chosen_for_inspection = False

    qa_required = fields.Boolean("QA Required")
    analysis_id = fields.Many2one('supplier.analysis', string="Analysis", ondelete='cascade', required=True)
    product_id = fields.Many2one('product.product', string="Product", required=True)
    partner_id = fields.Many2one("res.partner","Vendor")
    name = fields.Char("Description")
    chosen_for_inspection = fields.Boolean("Inspect")
    passed_inspection = fields.Boolean("Passed Inspection")
    inspection_remark = fields.Char("Inspection Remark")
    unit_price = fields.Float("Unit Price")
    quantity = fields.Float("Quantity")
    selected = fields.Boolean("Selected")

class QualityInspection(models.Model):
    _name = "quality.inspection"
    _description = "Quality Inspection"

    name = fields.Char("Reference", required=True, readonly=True, default=lambda self: _('New'))
    state = fields.Selection([
        ('draft', 'Draft'),
        ('requested_docs', 'Requested'),
        ('parameters_received', 'Parameters Received'),
        ('approved', 'Approved')
    ], string="Status", default='draft', required=True)
    requested_date = fields.Date("Requested Date", readonly=True)
    inspected_date = fields.Date("Inspected Date", readonly=True)
    inspected_by = fields.Many2one("res.users", string="Inspected By", readonly=True, default=lambda self: self.env.user)
    partner_id = fields.Many2one("res.partner", string="Vendor", required=True)
    supplier_analysis_id = fields.Many2one("supplier.analysis", string="Supplier Analysis", required=True)
    quality_inspections_line_ids = fields.One2many("quality.inspection.line", "quality_inspection_id", string="Inspection Lines")

    @api.model
    def create(self, vals):
        """Generate a unique name for each quality inspection."""
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('quality.inspection') or _('New')
        return super(QualityInspection, self).create(vals)

    def action_request_documents(self):
        """Transition the record to the 'Requested' state."""
        if self.state != 'draft':
            raise UserError(_("Only records in the 'Draft' state can request documents."))
        self.write({
            'state': 'requested_docs',
            'requested_date': fields.Date.today(),
        })

    def action_receive_parameters(self):
        """Transition the record to the 'Parameters Received' state."""
        if self.state != 'requested_docs':
            raise UserError(_("You can only move to 'Parameters Received' after requesting documents."))
        self.write({'state': 'parameters_received'})

    def action_approve(self):
        """Transition the record to the 'Approved' state."""
        if self.state != 'parameters_received':
            raise UserError(_("You can only approve records that have received parameters."))
        for line in self.quality_inspections_line_ids:
            line.supplier_analysis_line_id.passed_inspection = line.passed_inspection
        self.write({
            'state': 'approved',
            'inspected_date': fields.Date.today(),
            'inspected_by': self.env.user.id,
        })

    def action_reset_to_draft(self):
        """Reset the record back to the 'Draft' state."""
        if self.state == 'draft':
            raise UserError(_("The record is already in the 'Draft' state."))
        self.write({'state': 'draft'})

class QualityInspectionLine(models.Model):
    _name = "quality.inspection.line"


    quality_inspection_id = fields.Many2one("quality.inspection")
    supplier_analysis_line_id = fields.Many2one("supplier.analysis.line")
    product_id = fields.Many2one('product.product', string="Product", required=True)
    name = fields.Char("Description")
    passed_inspection = fields.Boolean("Passed Inspection")
    inspection_remark = fields.Char("Inspection Remark")


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    quality_evaluation = fields.Boolean(string="Quality Assurance")
    passed_evaluation = fields.Boolean(string="Passed Evaluation")
    evaluation_remark = fields.Char(string="Evaluation Remark")
    purchase_request_id = fields.Many2one('purchase.request', string="Purchase Request")
    state = fields.Selection(selection_add=[
        ('advance_payment', 'Adv. Payment'),
        ('awaiting_delivery', 'Awaiting Delivery'),
        ('credit_settlement', 'Credit Settlement'),
        ('done', 'Done'),
    ], ondelete={
        'advance_payment': 'set default',
        'awaiting_delivery': 'set default',
        'credit_settlement': 'set default'
    })

    procurement_type = fields.Selection([
        ('pay_to_procure', 'Pay to Procure'),
        ('procure_to_pay', 'Procure to Pay')
    ], string="Procurement Type", required=True, default='pay_to_procure')

    delivery_instruction_ids = fields.One2many(
        'delivery.instruction.line', 'purchase_order_id', string="Delivery Instructions"
    )
    

    def action_view_purchase_orders(self):
        """Open the purchase orders related to this purchase request."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Orders'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('purchase_request_id', '=', self.id)],
            'context': {'default_purchase_request_id': self.id},
        }

def button_confirm(self):
        """Override confirm button to handle state transitions with conditions."""
        super(PurchaseOrder, self).button_confirm()

        for order in self:
            if order.procurement_type == 'pay_to_procure':
                order.state = 'advance_payment'
            elif order.procurement_type == 'procure_to_pay':
                order.state = 'awaiting_delivery'
                

    


    def action_awaiting_delivery(self):
        """Transition to 'credit_settlement'."""
        if self.state != 'awaiting_delivery':
            raise UserError(_("You can only transition to Credit Settlement from Awaiting Delivery."))
        self.write({'state': 'credit_settlement'})

    def action_credit_settlement(self):
        """Transition to 'done'."""
        if self.state != 'credit_settlement':
            raise UserError(_("You can only mark the order as Done from Credit Settlement."))
        self.write({'state': 'done'})

    def action_create_invoice(self):
        """
        Allow creating invoices in states: 'advance_payment', 'awaiting_delivery', 'credit_settlement',
        and ensure the invoice is linked to the purchase order.
        """
        allowed_states = ['advance_payment', 'awaiting_delivery', 'credit_settlement', 'purchase']
        if self.state not in allowed_states:
            raise UserError(
                _("Invoices can only be created in the states: Advance Payment, Awaiting Delivery, Credit Settlement, or Purchase."))

        # For states other than 'purchase', create an invoice manually
        if self.state in ['advance_payment', 'awaiting_delivery', 'credit_settlement']:
            invoice_vals = self._prepare_invoice()
            invoice = self.env['account.move'].create(invoice_vals)

            for line in self.order_line:
                invoice_line_vals = self._prepare_invoice_line(line)
                if invoice_line_vals:
                    invoice_line_vals.update({'move_id': invoice.id})
                    self.env['account.move.line'].create(invoice_line_vals)

            # Establish the link between purchase order and bill
            invoice.write({'purchase_id': self.id})
            self.write({'invoice_ids': [(4, invoice.id)]})

            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': invoice.id,
                'target': 'current',
            }

        # Call the original method for 'purchase' state
        return super(PurchaseOrder, self).action_create_invoice()

    def _prepare_invoice_line(self, line):
        """Prepare invoice line for non-standard states with validation."""
        # Check if the quantity has already been invoiced
        already_invoiced_qty = sum(
            self.env['account.move.line'].search([
                ('purchase_line_id', '=', line.id),
                ('move_id.state', '!=', 'cancel')  # Exclude canceled invoices
            ]).mapped('quantity')
        )

        remaining_qty = line.product_qty - already_invoiced_qty
        if remaining_qty <= 0:
            raise UserError(_("You cannot invoice the same quantity twice for the line: %s.") % line.name)

        if line.product_id and remaining_qty > 0:
            return {
                'product_id': line.product_id.id,
                'quantity': remaining_qty,  # Invoice only the remaining quantity
                'price_unit': line.price_unit,
                'name': line.name or line.product_id.name,
                'tax_ids': [(6, 0, line.taxes_id.ids)],
                'purchase_line_id': line.id  # Link to the purchase order line
            }
        return {}

    def _prepare_invoice(self):
        """Prepare the invoice values for manual creation."""
        return {
            'move_type': 'in_invoice',
            'partner_id': self.partner_id.id,
            'currency_id': self.currency_id.id,
            'invoice_origin': self.name,
            'invoice_payment_term_id': self.payment_term_id.id,
            'fiscal_position_id': self.fiscal_position_id.id,
            'company_id': self.company_id.id,
        }

class DeliveryInstructionLine(models.Model):
    _name = 'delivery.instruction.line'
    _description = 'Delivery Instruction Line'

    name = fields.Char(string="Remark", required=True)
    expected_date = fields.Date(string="Expected Date", required=True)
    quantity = fields.Float(string="Quantity", required=True)
    purchase_order_id = fields.Many2one('purchase.order', string="Purchase Order", required=True, ondelete='cascade')

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    @api.model
    def create(self, vals):
        # Call the super method to create the payment register
        payment_register = super(AccountPaymentRegister, self).create(vals)

        # Check if the payment is linked to a purchase bill
        if vals.get('move_id'):

            move_id = payment_register.env['account.move'].browse(vals.get('move_id'))
            if move_id:
                if move_id.move_type == 'in_invoice':  # Check if it's a vendor bill
                    purchase_order = move_id.purchase_id
                    if purchase_order:
                        # Change the state of the related purchase order to 'awaiting_delivery'
                        purchase_order.write({'state': 'awaiting_delivery'})

        return payment_register


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Override the default value for the 'type' field
    type = fields.Selection(default='product')

class UpdateHrExpense(models.Model):
    _inherit = "hr.expense"

    payment_mode = fields.Selection(
        selection=[
            ('own_account', "Employee (to reimburse)"),
            ('company_account', "Company")
        ],
        string="Paid By",
        default='own_account',
        tracking=True,
    )
