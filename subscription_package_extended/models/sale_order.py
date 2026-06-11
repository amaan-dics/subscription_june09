# -*- coding: utf-8 -*-
from odoo import models
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _action_confirm(self):
        res = super()._action_confirm()
        for order in self:
            if order.state == 'sale':
                subscriptions = self.env['subscription.package'].search([('sale_order_id', '=', order.id)])
                for subscription in subscriptions:
                    if subscription.stage_id.category == 'draft':
                        subscription.button_start_date()
                # [CHANGE] If this order contains the verification product, ensure partner is marked verified
                try:
                    verification_tmpl = self.env.ref('subscription_package_extended.product_template_verification')
                except Exception:
                    verification_tmpl = None

                if verification_tmpl:
                    try:
                        if any(line.product_id.product_tmpl_id.id == verification_tmpl.id for line in order.order_line):
                            partner = order.partner_id
                            if partner:
                                verification_obj = self.env['user.verification'].sudo()
                                existing = verification_obj.search([('partner_id', '=', partner.id)], limit=1)
                                if not existing:
                                    verification_obj.create({
                                        'partner_id': partner.id,
                                        'payment_reference': order.name or '',
                                    })
                                    _logger.info('Created user.verification for partner %s from sale.order %s', partner.id, order.name)
                                if not partner.is_verified:
                                    partner.sudo().write({'is_verified': True})
                                    _logger.info('Marked partner %s as verified from sale.order %s', partner.id, order.name)
                    except Exception:
                        _logger.exception('Error while creating verification from sale.order %s', order.name)
        return res
