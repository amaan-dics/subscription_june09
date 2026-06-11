# -*- coding: utf-8 -*-
# ============================================================
# user_verification.py
# MODULE: subscription_package_extended
# FILE PATH: models/user_verification.py
#
# [CHANGE 15] USER VERIFICATION BADGE
# Tracks which users have paid for the verification badge.
# A simple one-time payment feature that grants a visible badge
# on the user's profile across all pages.
# ============================================================

from odoo import models, fields


class UserVerification(models.Model):
    _name = 'user.verification'
    _description = 'User Verification Badge'
    _rec_name = 'partner_id'

    # The user who purchased verification
    partner_id = fields.Many2one(
        'res.partner',
        string='User',
        required=True,
        ondelete='cascade',
        index=True,
        # Note: Odoo Field does not accept `unique` param. Use SQL constraint instead.
    )

    # When was verification purchased (for record-keeping)
    purchase_date = fields.Datetime(
        string='Purchase Date',
        default=fields.Datetime.now,
        readonly=True,
    )

    # Payment reference/transaction id (optional, for audit trail)
    payment_reference = fields.Char(
        string='Payment Reference',
        readonly=True,
    )

    # Status (always True for this model, kept for extensibility)
    is_verified = fields.Boolean(
        string='Is Verified',
        default=True,
        readonly=True,
    )

    _sql_constraints = [
        ('unique_partner_verification', 'unique(partner_id)', 'This partner already has a verification record.'),
    ]