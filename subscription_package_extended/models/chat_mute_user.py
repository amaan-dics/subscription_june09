# -*- coding: utf-8 -*-
# ============================================================
# chat_mute_user.py
# MODULE: subscription_package_extended
# FILE PATH: models/chat_mute_user.py
#
# [CHANGE 13] MUTE USER MODEL
# Mirrors chat.block.user exactly — same fields, same logic.
# A record here means: user_id has muted muted_user_id.
# Effect: popup notifications from muted_user_id are suppressed
# in /portal/notifications. Messages still arrive and are visible.
#
# Add to security/ir.model.access.csv:
#   access_chat_mute_user,chat.mute.user,model_chat_mute_user,base.group_portal,1,1,1,0
#
# Add to __manifest__.py models list:
#   'models/chat_mute_user.py',
# ============================================================

from odoo import models, fields


class ChatMuteUser(models.Model):
    _name = 'chat.mute.user'
    _description = 'Muted Chat Users'
    _rec_name = 'muted_user_id'

    # The user who performed the mute action (res.partner)
    user_id = fields.Many2one(
        'res.partner',
        string='User',
        required=True,
        ondelete='cascade',
        index=True,
    )

    # The partner whose notifications are being suppressed
    muted_user_id = fields.Many2one(
        'res.partner',
        string='Muted User',
        required=True,
        ondelete='cascade',
        index=True,
    )

    # Prevent duplicate mute records for the same pair
    _sql_constraints = [
        (
            'unique_mute_pair',
            'UNIQUE(user_id, muted_user_id)',
            'This user is already muted.'
        )
    ]