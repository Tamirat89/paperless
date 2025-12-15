from odoo import _, api, fields, models
from collections import defaultdict
from odoo.exceptions import ValidationError, UserError
from odoo.osv.expression import AND

from datetime import datetime, timedelta
import pdb


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    quality_evaluation = fields.Boolean(string="Quality Assurance")
    passed_evaluation = fields.Boolean(string="Passed Evaluation")
    evaluation_remark = fields.Char(string="Evaluation Remark")
    remark = fields.Char(string="Remark", required="1")
    purchase_request_id = fields.Many2one('purchase.request', string="Purchase Request")
    purchase_request_supplier_id = fields.Many2one('supplier.analysis', string="Purchase Request")

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
    
    def action_view_purchase_orders_suppliers(self):
        """Open the purchase orders related to this purchase request."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Purchase Orders'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('purchase_request_supplier_id', '=', self.id)],
            'context': {'default_purchase_request_supplier_id': self.id},
        }

    
    def button_confirm(self):
        """Override confirm button to handle state transitions with conditions."""
        super(PurchaseOrder, self).button_confirm()

        for order in self:
            if order.procurement_type == 'pay_to_procure':
                order.state = 'advance_payment'
            elif order.procurement_type == 'procure_to_pay':
                order.state = 'awaiting_delivery'

    def action_done(self):
        for record in self:
            if record.state == 'credit_settlement':
                if record.invoice_ids:
                    for invoice in record.invoice_ids:
                        if invoice.payment_state != 'paid':
                            raise UserError(_("The bill is not fully paid."))
                else:
                    raise UserError(_("No bill found."))
                if record.picking_type_id:
                    for picking in record.picking_ids:
                        if picking.state != 'done':
                            raise UserError(_("The delivery is not done."))
                else:
                    raise UserError(_("There is no delivery."))
            else:
                raise UserError(_("You can only mark the order as Done from Credit Settlement."))
        self.write({'state': 'done'})
    


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
            invoice = self.env['account.move'].sudo().create(invoice_vals)

            for line in self.order_line:
                invoice_line_vals = self._prepare_invoice_line(line)
                if invoice_line_vals:
                    invoice_line_vals.update({'move_id': invoice.id})
                    self.env['account.move.line'].sudo().create(invoice_line_vals)

            # Establish the link between purchase order and bill (with sudo for access)
            invoice.sudo().write({'purchase_id': self.id})
            self.sudo().write({'invoice_ids': [(4, invoice.id)]})
            

            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': invoice.id,
                'target': 'new',
            }

        # Call the original method for 'purchase' state
        return super(PurchaseOrder, self).action_create_invoice()

    def _prepare_invoice_line(self, line):
        """Prepare invoice line for non-standard states with validation."""
        # Check if the quantity has already been invoiced
        already_invoiced_qty = sum(
            self.env['account.move.line'].sudo().search([
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
            'invoice_date': self.date_order,
            'invoice_origin': self.name,
            'invoice_date': self.date_order,
            'invoice_payment_term_id': self.payment_term_id.id,
            'fiscal_position_id': self.fiscal_position_id.id,
            'company_id': self.company_id.id,
        }
