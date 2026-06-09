# -*- coding: utf-8 -*-

from odoo import fields, models


class ChatBlockUser(models.Model):
    _name = 'chat.block.user'
    _description = 'Blocked Users'

    user_id = fields.Many2one('res.partner', required=True, ondelete='cascade')
    blocked_user_id = fields.Many2one('res.partner',required=True, ondelete='cascade')
