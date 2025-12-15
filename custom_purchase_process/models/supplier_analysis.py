from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, UserError
from datetime import datetime

class SupplierAnalysis(models.Model):
    _name = 'supplier.analysis'
    _description = 'Supplier Analysis'
    _inherit = ["mail.thread", "mail.activity.mixin", "analytic.mixin"]

    name = fields.Char(
        string="Analysis Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    state = fields.Selection([
        ('draft', 'On Draft'),
        ('checked', 'Analysed'),
        ('in_progress', 'Checked'),
        ('committee_approved', 'Approved by Committee'),
        ('procurement_approved', 'Approved by Procurrement Manager'),
        ('pre_odit_review', 'Reviewed by Pre-audit'),
        ('gm_approved', 'Approved by CEO'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default='draft', required=True, tracking=True)

    purchase_request_id = fields.Many2one('purchase.request', string="Purchase Request", required=True)
    committee_remark = fields.Char("Committee Approval Remark")
    remark = fields.Char("Remark" )
    reason_for_cancel = fields.Char("Reason for Cancellation")
    reason_for_set_draft = fields.Char("Reason for Reset to Draft")
    rejection_reason = fields.Text(string="Rejection Reason", readonly=True)
    supplier_analysis_lines = fields.One2many('supplier.analysis.line', 'analysis_id', string="Product Lines")
    qa_required = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No')
    ], string="QA Required", default='')

    date_requested = fields.Date(string="Date Requested", default=fields.Datetime.now, required=True)
    requested_by = fields.Many2one('res.users', string="Procurrement Officer", default=lambda self: self.env.user)
    approved_by = fields.Many2one('res.users', string="Approved By")
    checked_by_id = fields.Many2one('res.users', string="Checked By")
    committee_approved_by_id = fields.Many2one('res.users', string="Approved Committee")
    reviewed_by_id = fields.Many2one('res.users', string="Reviewed Auditor")
    gm_approved_by_id = fields.Many2one('res.users', string="Approved CEO")
    done_by_id = fields.Many2one('res.users', string="Done By")
    company_id = fields.Many2one(
        'res.company', string="Company", readonly=True, force_save=True,
        required=True, default=lambda self: self.env.company
    )
    user_id = fields.Many2one(
        'res.users', string="Purchaser",
        domain=lambda self: [
            ('groups_id', 'in', self.env.ref('purchase.group_purchase_user').id),
            ('company_ids', 'in', self.env.context.get('allowed_company_ids', []))
        ],
    )
    remaining_approvers_ids = fields.Many2many('res.users', string="Remaining Committee Approvers", help="Committee approvers remaining to approve", compute="_compute_remaining_approvers")
    remaining_approvers_count = fields.Integer(string="Remaining Approvers", compute="_compute_remaining_approvers", help="Number of approvers remaining")

    @api.depends('approved_user_ids', 'state', 'approver_ids')
    def _compute_remaining_approvers(self):
        for record in self:
            if record.state in ['in_progress', 'committee_approved']:
                remaining_users = record.approver_ids - record.approved_user_ids
                record.remaining_approvers_ids = remaining_users
                record.remaining_approvers_count = len(remaining_users)
            else:
                record.remaining_approvers_ids = [(5, 0, 0)]  # Clear the field
                record.remaining_approvers_count = 0

    purchase_order_count = fields.Integer(string="Purchase Order Count", compute="_compute_purchase_order_count")
    po_ids = fields.One2many('purchase.order', 'purchase_request_supplier_id', string='POs')
    supplier_analysis_po_count = fields.Integer(string="Supplier Analysis PO Count", compute="_compute_supplier_analysis_po_count")


    committee_id = fields.Many2one(
        'res.user.access.control',
        string="Approval Committee",
        domain="[('company_id', '=', company_id)]",
    )
    reason_for_selecting_vendor = fields.Html(string="Reason for Selecting/Updating Vendor")
    approver_ids = fields.Many2many('res.users', compute='_compute_approver_ids', string='Approvers', store=False)
    approved_user_ids = fields.Many2many('res.users', string='Users Approved', copy=False)
    button_show_approve = fields.Boolean(string="Can Approve", compute='_compute_button_show_approve')
    dont_show_quality_inspection_button = fields.Boolean(string="Don't Show Quality Inspection Button", compute='_compute_dont_show_quality_inspection_button')
    threshold_id = fields.Many2one(
            'supplier_analysis.threshold',
            string="Approval Threshold",
           
            tracking=True
        )


    total_amount = fields.Float(
        string="Total Amount",
        compute="_compute_total_amount",
        store=True,
        help="Sum of all line subtotals"
    )

    @api.depends('supplier_analysis_lines.subtotal', 'supplier_analysis_lines.selected')
    def _compute_total_amount(self):
        for analysis in self:
            selected_lines = analysis.supplier_analysis_lines.filtered(lambda l: l.selected)
            analysis.total_amount = sum(selected_lines.mapped('subtotal')) if selected_lines else 0.0

    # Create sequence
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('supplier.analysis') or _('New')
        return super(SupplierAnalysis, self).create(vals)

    @api.depends('po_ids')
    def _compute_purchase_order_count(self):
        for record in self:
            record.purchase_order_count = len(record.po_ids)
    
    @api.depends('po_ids')
    def _compute_supplier_analysis_po_count(self):
        for record in self:
            # Count purchase orders directly related to this supplier analysis
            record.supplier_analysis_po_count = self.env['purchase.order'].search_count([
                ('purchase_request_supplier_id', '=', record.id)
            ])

    

    def _compute_button_show_approve(self):
        for rec in self:
            rec.button_show_approve = (
                self.env.user in rec.approver_ids and
                self.env.user not in rec.approved_user_ids and
                rec.state == 'in_progress'
            )

    def _compute_dont_show_quality_inspection_button(self):
        for rec in self:
            # Show quality inspection button if QA is required ('yes') and state is 'in_progress'
            # Hide button in all other cases
            rec.dont_show_quality_inspection_button = not (
                rec.qa_required == 'yes' and
                rec.state == 'in_progress'
            )

    def action_view_po_supplier(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Orders',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('purchase_request_id', '=', self.purchase_request_id.id)],
            'context': dict(self.env.context, create=False),
        }
    
    def action_view_supplier_analysis_pos(self):
        """View purchase orders directly linked to this supplier analysis"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Purchase Orders - {self.name}',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('purchase_request_supplier_id', '=', self.id)],
            'context': {
                'default_purchase_request_supplier_id': self.id,
                'create': False
            },
            'target': 'current',
        }

    def action_view_sa(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Quality Inspection',
            'res_model': 'quality.inspection',
            'view_mode': 'list,form',
            'domain': [('supplier_analysis_id', '=', self.id)],
            'context': dict(self.env.context, create=False),
        }
    @api.onchange('qa_required', 'supplier_analysis_lines.selected')
    def _onchange_qa_required(self):
        if self.qa_required and self.qa_required == 'yes':
            self.supplier_analysis_lines.filtered(lambda l: l.selected).chosen_for_inspection = True
        else:
            self.supplier_analysis_lines.filtered(lambda l: l.selected).chosen_for_inspection = False
            self.supplier_analysis_lines.filtered(lambda l: l.selected).passed_inspection = False

    def action_generate_quality_inspection(self):
        """Generate quality inspection records for products that need inspection - enhanced version"""
        quality_inspection_model = self.env['quality.inspection']
        created_inspections = []
        
        for record in self:
            # Only allow from in_progress or committee_approved states if QA is required
            if record.state not in ['in_progress', 'committee_approved']:
                raise UserError(_("Quality inspection can only be generated from In Progress or Committee Approved state."))
                
            if record.qa_required != 'yes':
                raise UserError(_("Quality inspection is not required for this analysis."))
            
            # Check for existing quality inspections (excluding 'failed' state)
            existing_inspections = quality_inspection_model.search([
                ('supplier_analysis_id', '=', record.id),
                ('state', 'in', ['draft', 'requested_docs', 'approved'])
            ])
            
            # If there are existing inspections, check their status
            if existing_inspections:
                # First, check ALL inspections for failed items (regardless of state)
                failed_inspections = existing_inspections.filtered(lambda inv: inv.has_failed_items())
                
                if failed_inspections:
                    # If any inspection has failed items, change those to 'failed' state and allow creating new one
                    failed_inspections.write({'state': 'failed'})
                else:
                    # No failed items - check if there are approved inspections with all passed items
                    approved_inspections = existing_inspections.filtered(lambda inv: inv.state == 'approved')
                    approved_with_all_passed = approved_inspections.filtered(lambda inv: inv.has_passed_items())
                    
                    if approved_with_all_passed:
                        # If approved inspection with all passed items exists, don't create another
                        raise UserError(_("Quality inspection are already created with all passed items. Cannot create another inspection. Only create new inspection if the existing one has failed items."))
                    else:
                        # There are draft/requested_docs inspections (not approved yet) or approved without all passed
                        # Don't create another one
                        raise UserError(_("Quality inspection are already created. Cannot create another inspection. Only create new inspection if the existing one has failed items."))
            
            # If there are any other active inspections (draft/requested_docs without failed items), 
            # we should also handle them - but based on requirements, we only care about approved with passed
            # So we'll allow creating new ones if previous ones are not approved with all passed
            
            # Get lines that are selected
            selected_lines = record.supplier_analysis_lines.filtered(lambda l: l.selected)
            if not selected_lines:
                raise UserError(_("No lines selected for inspection."))

            # If there are existing quality inspections, filter to only include lines with failed items OR new vendors
            lines_to_inspect = selected_lines
            if existing_inspections:
                # Find all quality inspection lines for this supplier analysis (to identify previously inspected vendors)
                all_qi_lines = self.env['quality.inspection.line'].search([
                    ('quality_inspection_id.supplier_analysis_id', '=', record.id)
                ])
                
                # Get all previously inspected combinations (supplier_analysis_line_id, partner_id)
                previously_inspected = set()
                for qi_line in all_qi_lines:
                    if qi_line.supplier_analysis_line_id and qi_line.partner_id:
                        previously_inspected.add((
                            qi_line.supplier_analysis_line_id.id,
                            qi_line.partner_id.id
                        ))
                
                # Get combinations that failed
                failed_qi_lines = all_qi_lines.filtered(lambda l: l.failed_inspection)
                failed_combinations = set()
                for qi_line in failed_qi_lines:
                    if qi_line.supplier_analysis_line_id and qi_line.partner_id:
                        failed_combinations.add((
                            qi_line.supplier_analysis_line_id.id,
                            qi_line.partner_id.id
                        ))
                
                # Filter selected_lines to include:
                # 1. Lines that have failed items (from previous inspection)
                # 2. Lines for NEW vendors (not previously inspected)
                lines_to_inspect = selected_lines.filtered(
                    lambda l: l.partner_id and (
                        (l.id, l.partner_id.id) in failed_combinations or  # Has failed items
                        (l.id, l.partner_id.id) not in previously_inspected  # New vendor, not inspected before
                    )
                )
                
                if not lines_to_inspect:
                    raise UserError(_("No lines with failed items or new vendors found. Cannot create quality inspection. Only create inspection for lines that have failed items from previous inspection or for new vendors."))

            # Auto-mark lines for inspection (batch update)
            lines_to_inspect.filtered(lambda l: not l.chosen_for_inspection).write({'chosen_for_inspection': True})

            # Group by vendor for efficient processing
            selected_lines_by_vendor = {}
            for line in lines_to_inspect:
                if not line.partner_id:
                    raise UserError(_("Each selected line must have a vendor assigned."))
                selected_lines_by_vendor.setdefault(line.partner_id.id, []).append(line)

            # Create quality inspections per vendor
            for vendor_id, lines in selected_lines_by_vendor.items():
                inspection = quality_inspection_model.create({
                    'name': self.env['ir.sequence'].next_by_code('quality.inspection') or _('New'),
                    'supplier_analysis_id': record.id,
                    'requested_date': record.date_requested,
                    'partner_id': vendor_id,
                    'quality_inspections_line_ids': [(0, 0, {
                        'supplier_analysis_line_id': line.id,
                        'partner_id': vendor_id,  # Set vendor directly for better performance
                        'product_id': line.product_id.id,
                        'name': line.name,
                        'passed_inspection': False,
                        'inspection_remark': '',
                    }) for line in lines],
                })
                created_inspections.append(inspection)
                
        return {
            'type': 'ir.actions.act_window',
            'name': 'Generated Quality Inspections',
            'res_model': 'quality.inspection',
            'view_mode': 'list,form',
            'domain': [('id', 'in', [i.id for i in created_inspections])],
            'target': 'current',
        }

    
    
    def action_in_progress(self):
        for record in self:
            if not record.qa_required:
                raise UserError(_("Please select quality inspection choice"))
            if record.state != 'draft':
                raise UserError(_("Only records in Draft state can be moved to In Progress."))
            if not record.remark:
                raise UserError(_("Please provide a remark before moving to In Progress."))
            
            # Clear the "newly added" flag when moving to next state
            record.supplier_analysis_lines.filtered(lambda l: l.is_newly_added).write({'is_newly_added': False})
            record.state = 'checked'


    @api.depends()
    def _compute_approver_ids(self):
        # Cache approvers per company within the current env to avoid repeated queries
        cache_attr = '_sa_approvers_by_company'
        approvers_by_company = getattr(self.env, cache_attr, None)
        if not isinstance(approvers_by_company, dict):
            approvers_by_company = {}

        approver_group = self.env.ref('custom_purchase_process.group_supplier_analysis_approver')

        for rec in self:
            company_id = rec.company_id.id or self.env.company.id
            if company_id not in approvers_by_company:
                committees = self.env['res.user.access.control'].sudo().search([
                    ('company_id', '=', company_id)
                ])
                committee_users = committees.mapped('committee_user_ids')
                approvers = committee_users.filtered(lambda u: approver_group in u.groups_id)
                approvers_by_company[company_id] = approvers

            rec.approver_ids = approvers_by_company.get(company_id, self.env['res.users'])

        setattr(self.env, cache_attr, approvers_by_company)

    
    button_show_client_approve = fields.Boolean(
        string="Show Client Approve Button",
        compute="_compute_button_show_client_approve",
        store=False,
    )

    @api.depends('approved_user_ids')
    def _compute_button_show_client_approve(self):
        for rec in self:
            rec.button_show_client_approve = (
                self.env.user in rec.approver_ids and
                self.env.user not in rec.approved_user_ids and
                rec.state == 'in_progress'  # or whatever state you want to restrict
            )

    
    def action_committee_approve(self):
        self.committee_approved_by_id = self.env.user.id
        """Committee approval method - optimized version"""
        for record in self:
            # Basic validations
            if record.state != 'in_progress':
                raise UserError(_("Only records In Progress can be Committee Approved."))

            if self.env.user not in record.approver_ids:
                raise UserError(_("You are not authorized to approve this record."))

            if self.env.user in record.approved_user_ids:
                raise UserError(_("You have already approved this record."))

            selected_lines = record.supplier_analysis_lines.filtered(lambda l: l.selected)
            if not selected_lines:
                raise UserError(_("At least one product must be selected for Committee Approval."))
            
            # Quality inspection validation - only check if quality inspection has been generated
            if record.qa_required == 'yes':
                # Auto-mark selected lines for inspection (this will be used when generating quality inspection)
                selected_lines.write({'chosen_for_inspection': True})

            # Batch update purchase request lines (optimized)
            for line in selected_lines:
                # Update material request lines if exists
                if record.purchase_request_id.material_request_id:
                    matching_request_lines = record.purchase_request_id.material_request_id.material_request_line_ids.filtered(
                        lambda x: x.product_id == line.product_id
                    )
                    # Only update if fields exist on the model
                    if matching_request_lines and hasattr(matching_request_lines, 'supplier_id') and hasattr(matching_request_lines, 'cost_price'):
                        matching_request_lines.write({
                            'supplier_id': line.partner_id.id,
                            'cost_price': line.unit_price
                        })

                # Update purchase request lines
                purchase_request_lines = record.purchase_request_id.purchase_request_line_ids.filtered(
                    lambda x: x.product_id == line.product_id
                )
                for request_line in purchase_request_lines:
                    request_line.write({
                        'unit_price': line.unit_price,
                        'subtotal': line.unit_price * request_line.quantity
                    })

            # Track approval
            record.approved_user_ids = [(4, self.env.user.id)]

            # Check if all approvers have approved (optimized)
            if set(record.approved_user_ids.ids) == set(record.approver_ids.ids):
                record.state = 'committee_approved'

    
    def action_gm_approve(self):
        for record in self:
            # Can approve from procurement_approved or pre_odit_review state
            if record.state not in ['procurement_approved', 'pre_odit_review']:
                raise UserError(_("GM can only approve from Procurement Approved or Pre-Audit Review state."))
                
            # Check if quality inspection is required and completed
            if record.qa_required:
                qa_lines = record.supplier_analysis_lines.filtered(lambda l: l.selected and l.chosen_for_inspection)
                if qa_lines:
                    # Check if all QA lines have been inspected
                    uninspected_lines = qa_lines.filtered(lambda l: not l.passed_inspection)
                    if uninspected_lines:
                        raise UserError(_("Quality inspection is required but some items have not passed inspection or are still pending."))

            # First, change state to gm_approved
            record.state = 'gm_approved'

            # Now automatically create purchase orders and confirm them
            selected_lines = record.supplier_analysis_lines.filtered(lambda l: l.selected)
            
            if not selected_lines:
                raise UserError(_("No supplier analysis lines have been marked as selected."))

            # Validate that all selected lines have partners
            lines_without_partners = selected_lines.filtered(lambda l: not l.partner_id)
            if lines_without_partners:
                raise UserError(_("The following lines are selected but have no vendor assigned: %s") % 
                              ', '.join(lines_without_partners.mapped('name')))

            grouped_lines = {}
            for line in selected_lines:
                grouped_lines.setdefault(line.partner_id.id, []).append(line)

            purchase_orders = []
            for partner_id, lines in grouped_lines.items():
                # Validate partner_id is not False/None
                if not partner_id:
                    raise UserError(_("Invalid partner_id found in grouped lines. Please check vendor assignments."))
                
                po_vals = {
                    'partner_id': partner_id,
                    'origin': record.purchase_request_id.name,
                    'date_order': fields.Datetime.now(),
                    'purchase_request_id': record.purchase_request_id.id,
                    'remark': record.remark,
                    'purchase_request_supplier_id': record.id,  # Link to supplier analysis
                }
                
                # Validate po_vals before creation
                if not po_vals.get('partner_id'):
                    raise UserError(_("Partner ID is missing from purchase order values. Cannot create purchase order."))
                
                purchase_order = self.env['purchase.order'].create(po_vals)
                purchase_orders.append(purchase_order)

                for line in lines:
                    self.env['purchase.order.line'].create({
                        'order_id': purchase_order.id,
                        'product_id': line.product_id.id,
                        'name': line.name or line.product_id.name,
                        'price_unit': line.unit_price,
                        'product_qty': line.quantity,
                        'date_planned': fields.Datetime.now(),
                    })

                # Automatically confirm the purchase order to advance_payment state
                try:
                    purchase_order.button_confirm()
                except Exception as e:
                    # Log the error but don't break the workflow
                    import logging
                    _logger = logging.getLogger(__name__)
                    _logger.warning(f"Failed to confirm purchase order {purchase_order.name}: {str(e)}")

            # Change state to done
            record.state = 'done'
            record.purchase_request_id.state = 'purchase_order'

            # Return action to show created purchase orders
            return {
                'type': 'ir.actions.act_window',
                'name': _('Purchase Orders'),
                'res_model': 'purchase.order',
                'view_mode': 'list,form',
                'domain': [('id', 'in', [po.id for po in purchase_orders])],
                'target': 'current',
            }



    def action_done(self):
        self.ensure_one()
        selected_lines = self.env['supplier.analysis.line'].search([
            ('analysis_id.purchase_request_id', '=', self.purchase_request_id.id),
            ('selected', '=', True)
        ])
        if not selected_lines:
            raise UserError(_("No supplier analysis lines have been marked as selected."))

        grouped_lines = {}
        for line in selected_lines:
            grouped_lines.setdefault(line.partner_id.id, []).append(line)

        purchase_orders = []
        for partner_id, lines in grouped_lines.items():
            po_vals = {
                'partner_id': partner_id,
                'origin': self.purchase_request_id.name,
                'date_order': fields.Datetime.now(),
                'purchase_request_id': self.purchase_request_id.id,
                'remark': self.remark,
            }
            purchase_order = self.env['purchase.order'].create(po_vals)
            purchase_orders.append(purchase_order)

            for line in lines:
                self.env['purchase.order.line'].create({
                    'order_id': purchase_order.id,
                    'product_id': line.product_id.id,
                    'name': line.name or line.product_id.name,
                    'price_unit': line.unit_price,
                    'product_qty': line.quantity,
                    'date_planned': fields.Datetime.now(),
                })

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
        """Cancel the supplier analysis with a required reason."""
        for record in self:
            if not record.reason_for_cancel:
                raise UserError(_("Please provide a reason for cancellation before cancelling this supplier analysis."))
            
            if record.state not in ['draft', 'in_progress', 'committee_approved', 'gm_approved']:
                raise UserError(_("Only certain states can be cancelled."))
            
            record.state = 'cancelled'

    def action_reset_to_draft(self):
        """Reset the supplier analysis to draft with a required reason."""
        for record in self:
            if not record.reason_for_set_draft:
                raise UserError(_("Please provide a reason for resetting to draft before proceeding."))
            
            record.state = 'draft'
            # Clear approved users so they can approve again
            record.approved_user_ids = [(5, 0, 0)]
            
            # Reset quality inspection fields on supplier analysis lines
            record.supplier_analysis_lines.write({
                'chosen_for_inspection': False,
                'passed_inspection': False,
            })

    def action_check(self):
        self.checked_by_id = self.env.user.id
        self.state = 'in_progress'

    def action_procurement_approve(self):
        # Check if any selected vendor has failed items
        selected_lines = self.supplier_analysis_lines.filtered(lambda l: l.selected)
        failed_vendors = []
        missing_qi_vendors = []
        
        for line in selected_lines:
            if not line.partner_id:
                continue
            
            # Find quality inspection line where:
            # 1. supplier_analysis_line_id matches this line
            # 2. partner_id (vendor) matches this line's vendor
            # 3. quality inspection state is 'approved' or 'failed'
            # 4. failed_inspection is True
            failed_qi_line = self.env['quality.inspection.line'].search([
                ('supplier_analysis_line_id', '=', line.id),
                ('partner_id', '=', line.partner_id.id),
                ('quality_inspection_id.state', 'in', ['approved', 'failed']),
                ('failed_inspection', '=', True)
            ], limit=1)
            
            if failed_qi_line:
                failed_vendors.append(line.partner_id.name or 'Unknown Vendor')
            
            # Check if quality inspection exists for this vendor and is in valid state (approved or failed)
            # Only check if QA is required
            if self.qa_required == 'yes':
                qi_line_exists = self.env['quality.inspection.line'].search([
                    ('supplier_analysis_line_id', '=', line.id),
                    ('partner_id', '=', line.partner_id.id),
                    ('quality_inspection_id.state', 'in', ['approved', 'failed'])
                ], limit=1)
                
                if not qi_line_exists:
                    missing_qi_vendors.append(line.partner_id.name or 'Unknown Vendor')
        
        if failed_vendors:
            vendor_names = ', '.join(failed_vendors)
            raise UserError(_("NOT PASS VENDOR IS SELECTED and also failed not impossible this must change vendor or deselect the selected vendor. Failed vendors: %s") % vendor_names)
        
        if missing_qi_vendors:
            vendor_names = ', '.join(missing_qi_vendors)
            raise UserError(_("Create quality inspection for new selected vendor. Missing quality inspections for vendors: %s") % vendor_names)
        
        # Check if QA is required and Quality Inspection is not approved
        if self.qa_required == 'yes':
            # Get all quality inspections for this supplier analysis
            quality_inspections = self.env['quality.inspection'].search([
                ('supplier_analysis_id', '=', self.id)
            ])
            
            if not quality_inspections:
                raise UserError(_("Quality inspection is required but no quality inspections have been generated. Please generate quality inspections first."))
            
            # Check if any quality inspection is not in 'approved' or 'failed' state
            # 'failed' state is allowed because it means the inspection was done but failed, and user can proceed
            non_approved_inspections = quality_inspections.filtered(lambda qi: qi.state not in ['approved', 'failed'])
            if non_approved_inspections:
                inspection_names = ', '.join(non_approved_inspections.mapped('name'))
                raise UserError(_("Quality inspection is required but the following quality inspections are not approved or failed: %s. Please ensure all quality inspections are approved or failed before procurement approval.") % inspection_names)
        
        self.approved_by = self.env.user.id
        self.state = 'procurement_approved'

    def action_pre_odit_review(self):
        self.reviewed_by_id = self.env.user.id
        self.state = 'pre_odit_review'
        
        # Schedule activity for CEO users in the same company
        ceo_group = self.env.ref('custom_purchase_process.group_supplier_analysis_ceo')
        ceo_users = ceo_group.users.filtered(lambda user: user.company_id == self.company_id)
        
        for ceo_user in ceo_users:
            self.sudo().activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=ceo_user.id,
                summary=f"CEO Approval Required - {self.name}",
                note=f"Supplier Analysis {self.name} is ready for CEO approval",
            )

    def action_update_supplier_analysis(self):
        """Update supplier analysis with new vendors from RFQs - Enhanced to maintain product grouping"""
        self.ensure_one()
        
        if self.state != 'draft':
            raise UserError(_("Supplier analysis can only be updated when in draft state."))
        
        # Get all quotations for this purchase request
        quotations = self.env['purchase.quotation'].search([
            ('purchase_request_id', '=', self.purchase_request_id.id)
        ])
        
        if not quotations:
            raise UserError(_("No quotations found for this purchase request."))
        
        # Get existing vendor-product combinations in this analysis
        existing_combinations = set()
        for line in self.supplier_analysis_lines:
            if line.product_id and line.partner_id:
                existing_combinations.add((line.product_id.id, line.partner_id.id))
        
        # Group new vendors by product
        new_vendors_by_product = {}
        for quotation in quotations:
            for quotation_line in quotation.quotation_line_ids:
                if quotation_line.product_id and quotation.partner_id:
                    combination = (quotation_line.product_id.id, quotation.partner_id.id)
                    if combination not in existing_combinations:
                        product_id = quotation_line.product_id.id
                        if product_id not in new_vendors_by_product:
                            new_vendors_by_product[product_id] = []
                        
                        new_vendors_by_product[product_id].append({
                            'analysis_id': self.id,
                            'product_id': quotation_line.product_id.id,
                            'partner_id': quotation.partner_id.id,
                            'name': quotation_line.description or quotation_line.product_id.name,
                            'product_uom_id': quotation_line.product_uom_id.id,
                            'quantity': quotation_line.quantity,
                            'unit_price': quotation_line.unit_price,
                            'selected': False,
                            'is_merge_line': False,
                            'is_newly_added': False,  # Don't highlight - treat as normal
                        })
                        existing_combinations.add(combination)
        
        if new_vendors_by_product:
            total_added = 0
            # Get all existing lines sorted by sequence/id
            all_lines = self.supplier_analysis_lines.sorted('id')
            
            # For each product that has new vendors
            for product_id, new_lines_data in new_vendors_by_product.items():
                # Find the last line for this product (skip merge lines)
                last_product_line = None
                last_product_line_index = -1
                
                for idx, line in enumerate(all_lines):
                    if line.product_id.id == product_id and not line.is_merge_line:
                        last_product_line = line
                        last_product_line_index = idx
                
                if last_product_line:
                    # Get the sequence/position after the last line of this product
                    # Find the next line after the last product line
                    if last_product_line_index + 1 < len(all_lines):
                        next_line = all_lines[last_product_line_index + 1]
                        # Insert new lines before the next line (which could be a merge line for next product)
                        for new_line_data in new_lines_data:
                            # Create the line - Odoo will append it to the end by default
                            created_line = self.env['supplier.analysis.line'].with_context(allow_create_supplier_analysis_line=True).create(new_line_data)
                            total_added += 1
                    else:
                        # Last product in the list, just create at the end
                        for new_line_data in new_lines_data:
                            self.env['supplier.analysis.line'].with_context(allow_create_supplier_analysis_line=True).create(new_line_data)
                            total_added += 1
                else:
                    # Product not found in existing lines (shouldn't happen, but handle it)
                    for new_line_data in new_lines_data:
                        self.env['supplier.analysis.line'].create(new_line_data)
                        total_added += 1
            
            # Reorder lines to ensure proper grouping: merge line -> product lines -> merge line -> product lines
            self._reorder_analysis_lines()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Added %d new vendor entries to the supplier analysis in proper product groups.') % total_added,
                    'type': 'success',
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Information'),
                    'message': _('No new vendors found to add to the supplier analysis.'),
                    'type': 'info',
                }
            }
    
    def _reorder_analysis_lines(self):
        """Reorder supplier analysis lines to maintain product grouping"""
        self.ensure_one()
        
        # Group lines by product
        lines_by_product = {}
        merge_lines_by_product = {}
        
        for line in self.supplier_analysis_lines:
            if line.is_merge_line:
                merge_lines_by_product[line.product_id.id] = line
            else:
                if line.product_id.id not in lines_by_product:
                    lines_by_product[line.product_id.id] = []
                lines_by_product[line.product_id.id].append(line)
        
        # Reorder: for each product, set sequence for merge line first, then product lines
        sequence = 10
        for product_id in sorted(lines_by_product.keys()):
            # Set sequence for merge line
            if product_id in merge_lines_by_product:
                merge_lines_by_product[product_id].write({'sequence': sequence})
                sequence += 10
            
            # Set sequence for product lines
            for line in lines_by_product[product_id]:
                line.write({'sequence': sequence})
                sequence += 10


class SupplierAnalysisLine(models.Model):
    _name = 'supplier.analysis.line'
    _description = 'Supplier Analysis Line'
    _order = 'sequence, id'

    @api.model_create_multi
    def create(self, vals_list):
        # Prevent manual creation of supplier analysis lines
        # Allow creation only if context flag 'allow_create_supplier_analysis_line' is set (for programmatic creation)
        if not self.env.context.get('allow_create_supplier_analysis_line'):
            raise UserError(_('Supplier analysis lines cannot be created manually. They must be created through the purchase request workflow.'))
        return super().create(vals_list)

    sequence = fields.Integer(string="Sequence", default=10)
    analysis_id = fields.Many2one('supplier.analysis', string="Analysis")
    # Mirror parent state so we can control readonly in views without attrs
    state = fields.Selection(related='analysis_id.state', string="Status", store=False, readonly=True)
    is_merge_line = fields.Boolean("Is Merge Line", default=False)
    merge_note = fields.Char("Merge Note")

    product_id = fields.Many2one(
        'product.product', 
        string="Product",
    )
    partner_id = fields.Many2one('res.partner', string="Vendor")
    name = fields.Char("Description")
    product_uom_id = fields.Many2one(
        'uom.uom',
        string="Unit of Measure",
        readonly=True,
        store=True
    )
    # Editable only when parent analysis is in draft state
    unit_price = fields.Float(
        "Unit Price",
        help="Unit price - editable only when parent analysis is in draft state"
    )
    quantity = fields.Float("Quantity")
    
    selected = fields.Boolean("Selected")
    selected_readonly = fields.Boolean(
        string="Selected Readonly",
        compute="_compute_selected_readonly",
        store=False,
    )

    @api.depends('analysis_id.state')
    def _compute_selected_readonly(self):
        for line in self:
            # Make readonly if parent state is not draft
            line.selected_readonly = line.analysis_id.state != 'draft'
    chosen_for_inspection = fields.Boolean("Inspect",compute="_compute_chosen_for_inspection")
    passed_inspection = fields.Boolean("Passed Inspection",readonly=True)
    
    quality_inspection_status = fields.Selection(
        [('passed', 'Passed'), ('failed', 'Failed')],
        string="Inspection Status",
        compute="_compute_quality_inspection_status",
        store=False,
        help="Shows the inspection status from the related Quality Inspection Line for the matching vendor"
    )

    show_merge_note = fields.Boolean(compute="_compute_field_visibility")
    hide_merge_fields = fields.Boolean(compute="_compute_field_visibility")

    subtotal = fields.Float(
        string="Subtotal", compute="_compute_subtotal", store=True
    )
    is_newly_added = fields.Boolean(
        string="Newly Added", 
        default=False,
        help="Indicates if this line was added via the Update button"
    )

    @api.depends('selected','analysis_id.qa_required')
    def _compute_chosen_for_inspection(self):
        for line in self:
            if line.selected and line.analysis_id.qa_required == 'yes':
                line.chosen_for_inspection = True
            else:
                line.chosen_for_inspection = False

    @api.depends('unit_price', 'quantity')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.unit_price * line.quantity

    @api.depends('is_merge_line')
    def _compute_field_visibility(self):
        for line in self:
            line.show_merge_note = line.is_merge_line
            line.hide_merge_fields = line.is_merge_line

    def _compute_quality_inspection_status(self):
        """Compute inspection status from related quality.inspection.line matching the vendor"""
        for line in self:
            if not line.partner_id:
                line.quality_inspection_status = False
                continue
            
            # Find the quality inspection line where:
            # 1. supplier_analysis_line_id matches this line
            # 2. The quality inspection's partner_id matches this line's partner_id (vendor)
            quality_inspection_line = self.env['quality.inspection.line'].search([
                ('supplier_analysis_line_id', '=', line.id),
                ('quality_inspection_id.partner_id', '=', line.partner_id.id)
            ], limit=1)
            
            if quality_inspection_line:
                # Show passed/failed if quality inspection is in approved or failed state
                qi_state = quality_inspection_line.quality_inspection_id.state
                if qi_state in ['approved', 'failed']:
                    if quality_inspection_line.passed_inspection:
                        line.quality_inspection_status = 'passed'
                    elif quality_inspection_line.failed_inspection:
                        line.quality_inspection_status = 'failed'
                    else:
                        line.quality_inspection_status = False
                else:
                    # Quality inspection not approved/failed yet, don't show status
                    line.quality_inspection_status = False
            else:
                line.quality_inspection_status = False

    def unlink(self):
        """Prevent deletion of supplier analysis records unless they are in draft state."""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('You cannot delete records that are not in draft state.'))
        return super(SupplierAnalysis, self).unlink()




