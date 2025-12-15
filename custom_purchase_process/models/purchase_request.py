from odoo import _, api, fields, models
from collections import defaultdict
from odoo.exceptions import ValidationError, UserError
from odoo.osv.expression import AND


class PurchaseRequest(models.Model):
    _name = 'purchase.request'
    _description = 'Purchase Request'
    _inherit = ["mail.thread", "mail.activity.mixin", "analytic.mixin"]


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
    approved_by_id = fields.Many2one('res.users', string="Approved By")
    checked_by_id = fields.Many2one('res.users', string="Checked By")
    reviewed_by_id = fields.Many2one('res.users', string="Reviewed By")
    quality_evaluation = fields.Boolean(string="Quality Assurance")
    reason_for_rejection = fields.Char(string="Reason for Rejection" )
    rejection_reason = fields.Text(string="Rejection Reason", readonly=True)

    state = fields.Selection([
        ('draft', 'On Draft'),
        ('checked','Checked'),
        ('reviewed', 'Reviewed'),
        ('approved', 'Approved'),
        ('rfq', 'On RFQ'),
        ('supplier_analysis', 'On Supplier Analysis'),
        ('quality_evaluation', 'On Quality Evaluation'),
        ('purchase_order', 'Purchase Ordered'),
        ('rejected', 'Rejected')
    ], string="Status", default='draft', required=True,tracking=True)

    purchase_request_line_ids = fields.One2many('purchase.request.line', 'purchase_request_id', string="Request Lines")
    purchase_order_ids = fields.One2many('purchase.order', 'purchase_request_id', string="Purchase Orders")
    company_id = fields.Many2one('res.company', string="Company", required=True, default=lambda self: self.env.company)
    total_amount = fields.Float(string="Total Amount", compute="_compute_total_amount", store=True)
    request_department_id = fields.Many2one(
        'hr.department',
        string="Request Department",
        compute="_compute_request_department",
        store=True
    )
   

    user_id = fields.Many2one(
        'res.users',
        string="Procurement Officer", tracking=True,
        domain=lambda self: self._get_explicit_purchasers_domain()
    )

    @api.model
    def _get_explicit_purchasers_domain(self):
        # Get all groups in the purchase request module
        readonly_group = self.env.ref('custom_purchase_process.group_custom_purchase_request_readonly')
        purchaser_group = self.env.ref('custom_purchase_process.group_custom_purchase_request_purchaser')
        approver_group = self.env.ref('custom_purchase_process.group_custom_purchase_request_approvers')
        ceo_group = self.env.ref('custom_purchase_process.group_purchase_request_ceos')
        super_admin_group = self.env.ref('custom_purchase_process.group_custom_purchase_request_super_admin')
        
        # Get users who have access to any group in the purchase request module
        all_groups = [purchaser_group, approver_group, ceo_group, super_admin_group, readonly_group]
        all_users = set()
        for group in all_groups:
            all_users.update(group.users.ids)
        
        # Get users who only have readonly access
        readonly_users = set(readonly_group.users.ids)
        
        # Get users who have access to other groups (not just readonly)
        other_groups = [purchaser_group, approver_group, ceo_group, super_admin_group]
        users_with_other_access = set()
        for group in other_groups:
            users_with_other_access.update(group.users.ids)
        
        # Users who only have readonly access (exclude them)
        users_only_readonly = readonly_users - users_with_other_access
        
        # Final list: all users minus those who only have readonly access
        final_users = list(all_users - users_only_readonly)
        
        return [('id', 'in', final_users)]


    @api.depends('approved_by_id')
    def _compute_approved_by_char(self):
        for record in self:
            record.approved_by_char = record.approved_by_id.name if record.approved_by_id else ""

    @api.depends('requested_by')
    def _compute_request_department(self):
        for record in self:
            employee = self.env['hr.employee'].search([('user_id', '=', record.requested_by.id)], limit=1)
            record.request_department_id = employee.department_id if employee else False

    quotation_count = fields.Integer(string="Quotation Count", compute="_compute_quotation_count")
    supplier_analysis_count = fields.Integer(string="Supplier Analysis Count", compute="_compute_supplier_analysis_count")

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

    qo_ids = fields.One2many('purchase.quotation', 'purchase_request_id', string='POs')
    supplier_analysis_ids = fields.One2many('supplier.analysis', 'purchase_request_id', string='Supplier Analysis')

    
    @api.depends('qo_ids')
    def _compute_quotation_count(self):
        """ Compute the count of related POs. """
        for record in self:
            record.quotation_count = len(record.qo_ids)

    @api.depends('supplier_analysis_ids')
    def _compute_supplier_analysis_count(self):
        """ Compute the count of related supplier analysis. """
        for record in self:
            record.supplier_analysis_count = len(record.supplier_analysis_ids)

    # @api.depends_context('uid')  # to ensure count updates on form reload
    # def _compute_quotation_count(self):
    #     for record in self:
    #         record.quotation_count = self.env['purchase.quotation'].search_count([('purchase_request_id', '=', record.id)])

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

    
    purchase_order_count = fields.Integer(string="Purchase Order Count", compute="_compute_purchase_order_count")
    po_ids = fields.One2many('purchase.order', 'purchase_request_id', string='POs')

    
    @api.depends('po_ids')
    def _compute_purchase_order_count(self):
        """ Compute the count of related POs. """
        for record in self:
            record.purchase_order_count = len(record.po_ids)
    
    
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
        self.state = 'reviewed'



    def action_approve(self):
        if not self.user_id:
            raise UserError(_("Please assign a procurrement officer first."))

        self.approved_by_id = self.env.user.id
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
            'created_by': self.env.user.id,
        }
        quotation = self.env['purchase.quotation'].create(quotation_vals)

        # Create Quotation Lines
        for line in self.purchase_request_line_ids:
            self.env['purchase.quotation.line'].with_context(allow_create_quotation_line=True).create({
                'quotation_id': quotation.id,
                'product_id': line.product_id.id,
                'description': line.description or line.product_id.name,
                'product_uom_id': line.product_uom_id.id,
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

   

    remark = fields.Char("Remark")
    def action_set_supplier_analysis(self):
        self.ensure_one()
        self.state = 'supplier_analysis'
        if not self.purchase_request_line_ids:
            raise UserError(_("No lines found in the purchase request to generate the Supplier Analysis."))

        # Check if there's already a supplier analysis for this purchase request
        existing_analysis = self.env['supplier.analysis'].search([
            ('purchase_request_id', '=', self.id),
            
        ], limit=1)

        # If analysis exists, open it instead of creating new one
        if existing_analysis:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Supplier Analysis',
                'res_model': 'supplier.analysis',
                'view_mode': 'form',
                'res_id': existing_analysis.id,
                'target': 'current',
            }

        # Get all quotations for this purchase request
        quotations = self.env['purchase.quotation'].search([
            ('purchase_request_id', '=', self.id)
        ])
        if not quotations:
            raise UserError(_("No quotations found for this request."))

        # Validate that ALL quotations are in 'received' state
        quotations_not_received = quotations.filtered(lambda q: q.state != 'received')
        if quotations_not_received:
            quotation_names = ', '.join(quotations_not_received.mapped('name'))
            raise UserError(_("Supplier analysis cannot be created. The following RFQ quotations are not in 'received' state: %s. Please ensure all quotations are received before creating supplier analysis.") % quotation_names)

        # Create Supplier Analysis (only if no analysis exists)
        supplier_analysis = self.env['supplier.analysis'].create({
            'purchase_request_id': self.id,
            'state': 'draft',
            'date_requested': fields.Datetime.now(),
            'requested_by': self.env.user.id,
        })

        product_lines = []
        if not self.purchase_request_line_ids:
            raise UserError(_("No product lines in the purchase request."))

        # Group request lines by product
        grouped_lines = {}
        for line in self.purchase_request_line_ids:
            grouped_lines.setdefault(line.product_id.id, []).append(line)

        for product_id, request_lines in grouped_lines.items():
            # Add merge line BEFORE product group
            merge_line = {
                'analysis_id': supplier_analysis.id,
                'product_id': product_id,
                'is_merge_line': True,
                'merge_note': f'Notes for {self.env["product.product"].browse(product_id).name}',

                # All other fields empty/False
                'partner_id': False,
                'name': '',
                'unit_price': 0.0,
                
                'selected': False,
                'chosen_for_inspection': False,
                'passed_inspection': False,
            }
            product_lines.append(merge_line)

            # Process ALL lines for this product - match by index
            for request_line_index, request_line in enumerate(request_lines):
                print(f"Request Line {request_line_index}: {request_line}")
                qa_required = False
                
                for quotation in quotations:
                    print(f"Quotation: {quotation}")
                    # Get all quotation lines for this product (ordered)
                    quotation_lines_for_product = quotation.quotation_line_ids.filtered(
                        lambda ql: ql.product_id.id == product_id
                    )
                    
                    # Match by index - get the corresponding quotation line
                    if request_line_index < len(quotation_lines_for_product):
                        quotation_line = quotation_lines_for_product[request_line_index]
                    else:
                        # If quotation has fewer lines than request, skip or use last available
                        quotation_line = quotation_lines_for_product[-1] if quotation_lines_for_product else False
                
                    if quotation_line:
                        print(f"Matched Quotation Line {request_line_index}: {quotation_line} with price {quotation_line.unit_price}")

                        if request_line.qa_required:
                            qa_required = True
                        product_lines.append({
                            'analysis_id': supplier_analysis.id,
                            'product_id': quotation_line.product_id.id,
                            'partner_id': quotation.partner_id.id,
                            'name': request_line.description,  # Use request line description
                            'product_uom_id': request_line.product_uom_id.id,  # Use request line UOM
                            'quantity': request_line.quantity,  # Use request line quantity
                            'chosen_for_inspection': request_line.qa_required,
                            'unit_price': quotation_line.unit_price,  # Use matched quotation line's unit price
                            'selected': False,
                            'is_merge_line': False,
                        })
                if qa_required:
                    supplier_analysis.qa_required = True

        if not product_lines:
            raise UserError(_("No valid supplier analysis lines could be generated."))

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
        """Open wizard to get rejection reason and reject purchase request."""
        self.ensure_one()
        
        # Check if state is draft
        if self.state != 'draft':
            raise UserError(_('This action can only be performed when the purchase request is in draft state.'))
        
        # Open wizard dialog
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Purchase Request'),
            'res_model': 'reject.purchase.request.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_purchase_request_id': self.id,
            }
        }
    
    def action_reset_to_draft_from_states(self):
        """Reset purchase request to draft and also reset related quotations and supplier analysis."""
        self.ensure_one()
        
        # Check if state is in allowed states
        if self.state not in ['approved', 'rfq', 'supplier_analysis']:
            raise UserError(_('This action can only be performed when the purchase request is in approved, rfq, or supplier_analysis state.'))
        
        # Reset purchase request to draft
        self.state = 'draft'
        
        # Reset all related purchase quotations to draft
        quotations = self.env['purchase.quotation'].search([
            ('purchase_request_id', '=', self.id)
        ])
        for quotation in quotations:
            quotation.state = 'draft'
        
        # Reset all related supplier analysis to draft
        supplier_analyses = self.env['supplier.analysis'].search([
            ('purchase_request_id', '=', self.id)
        ])
        for analysis in supplier_analyses:
            analysis.state = 'draft'
        
        # Note: Do NOT change material.request state as per requirements

    def action_check(self):
        self.checked_by_id = self.env.user.id
        self.state = 'checked'

    def action_review(self):
        self.reviewed_by_id = self.env.user.id
        self.state = 'reviewed'

    def action_reset_to_draft(self):
        self.state = 'draft'    

    def action_back_to_sr(self):
        """Open wizard to get reason and then reset material request to draft and delete purchase request."""
        self.ensure_one()
        
        # Check if state is draft
        if self.state != 'draft':
            raise UserError(_('This action can only be performed when the purchase request is in draft state.'))
        
        # Open wizard dialog
        return {
            'type': 'ir.actions.act_window',
            'name': _('Back to SR'),
            'res_model': 'back.to.sr.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_purchase_request_id': self.id,
            }
        }

    

class PurchaseRequestLine(models.Model):
    _name = 'purchase.request.line'
    _description = 'Purchase Request Line'

    @api.model_create_multi
    def create(self, vals_list):
        # Prevent manual creation of purchase request lines
        # Allow creation only if context flag 'allow_create_line' is set (for programmatic creation)
        if not self.env.context.get('allow_create_purchase_request_line'):
            raise UserError(_('Purchase request lines cannot be created manually. They must be created through the purchase request workflow.'))
        return super().create(vals_list)

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
    product_uom_id = fields.Many2one(
        'uom.uom',
        string="Unit of Measure",
        readonly=True,
        store=True
    )
    quantity = fields.Float(string="Quantity")
    unit_price = fields.Float(string="Est. Price", required=True)
    subtotal = fields.Float(string="Subtotal", compute="_compute_subtotal", store=True)
    qa_required = fields.Boolean("QA")

    @api.depends('quantity', 'unit_price')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price
