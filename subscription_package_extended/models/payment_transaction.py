# -*- coding: utf-8 -*-
from odoo import models
import logging

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    # def _set_done(self):
    #     """
    #     Overridden to ensure that order processing, invoicing, and identity
    #     verification fulfillment only execute when the transaction is completely successful (done).
    #     """
    #     res = super()._set_done()
    #     for tx in self:
    #         reference = tx.reference
    #         sale_order = None
    #         if reference:
    #             sale_order = self.env['sale.order'].sudo().search([('name', '=', reference)], limit=1)
    #
    #         # Fallback: try to find a recent draft/sent sale.order for the same partner and amount
    #         if not sale_order:
    #             try:
    #                 partner = tx.partner_id if hasattr(tx, 'partner_id') else None
    #                 tx_amount = float(tx.amount or 0)
    #             except Exception:
    #                 partner = None
    #                 tx_amount = 0
    #
    #             if partner:
    #                 candidates = self.env['sale.order'].sudo().search([
    #                     ('partner_id', '=', partner.id),
    #                     ('state', 'in', ['draft', 'sent'])
    #                 ], order='create_date desc', limit=10)
    #                 for cand in candidates:
    #                     try:
    #                         amt = float(cand.amount_total or 0)
    #                     except Exception:
    #                         amt = 0
    #                     # allow small rounding differences
    #                     if abs(amt - tx_amount) < 0.5:
    #                         sale_order = cand
    #                         _logger.info('Mapped payment tx %s to sale.order %s by amount matching', reference, cand.name)
    #                         break
    #                 if not sale_order and candidates:
    #                     sale_order = candidates[0]
    #                     _logger.info('Fallback mapped payment tx %s to most recent sale.order %s', reference, sale_order.name)
    #             else:
    #                 _logger.warning('Payment tx %s has no partner; cannot fallback map to sale.order', reference)
    #         if sale_order:
    #             if sale_order.state in ['draft', 'sent']:
    #                 sale_order.action_confirm()
    #             invoices = sale_order._create_invoices()
    #             for inv in invoices:
    #                 if inv.state == 'draft':
    #                     inv.action_post()
    #                 payment_register = self.env['account.payment.register'].with_context(
    #                     active_model='account.move',
    #                     active_ids=inv.ids
    #                 ).create({'amount': inv.amount_total})
    #                 payment_register.action_create_payments()
    #
    #             # If this sale_order contains the verification product, mark partner verified
    #             try:
    #                 verification_tmpl = self.env.ref('subscription_package_extended.product_template_verification')
    #             except Exception:
    #                 verification_tmpl = None
    #
    #             if verification_tmpl:
    #                 if any(line.product_id.product_tmpl_id.id == verification_tmpl.id for line in
    #                        sale_order.order_line):
    #                     partner = sale_order.partner_id
    #                     if partner:
    #                         # Idempotency Guard: Avoid crashing on duplicate database unique constraints
    #                         verification_obj = self.env['user.verification'].sudo()
    #                         existing_verification = verification_obj.search([('partner_id', '=', partner.id)], limit=1)
    #
    #                         if not existing_verification:
    #                             verification_obj.create({
    #                                 'partner_id': partner.id,
    #                                 'payment_reference': reference or '',
    #                             })
    #
    #                         if not partner.is_verified:
    #                             partner.sudo().write({'is_verified': True})
    #     return res

    def _set_pending(self):
        res = super()._set_pending()
        for tx in self:
            reference = tx.reference
            sale_order = self.env['sale.order'].sudo().search([('name', '=', reference)], limit=1)
            if sale_order:
                if sale_order.state in ['draft', 'sent']:
                    sale_order.action_confirm()
                invoices = sale_order._create_invoices()
                for inv in invoices:
                    if inv.state == 'draft':
                        inv.action_post()
                    payment_register = self.env['account.payment.register'].with_context(active_model='account.move',
                                                                                         active_ids=inv.ids).create({
                                                                                        'amount': inv.amount_total})
                    payment_register.action_create_payments()
        return res