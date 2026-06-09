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