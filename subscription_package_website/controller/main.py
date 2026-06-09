# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import base64


class WebsiteHeader(http.Controller):

    @http.route('/website_chat/mark_read', type='json', auth='user')
    def website_chat_mark_read(self, user_id=None, **kwargs):
        if not user_id:
            return {'status': 'error'}

        partner = request.env.user.partner_id
        other_partner = request.env['res.partner'].sudo().browse(user_id)

        # channel = request.env['discuss.channel'].sudo().search([
        #     ('channel_type', '=', 'chat'),
        #     ('channel_member_ids.partner_id', '=', partner.id),
        #     ('channel_member_ids.partner_id', '=', other_partner.id),
        # ], limit=1)

        channel = request.env['discuss.channel'].sudo().search([
            ('channel_type', '=', 'chat'),
            ('channel_partner_ids', 'in', [partner.id]),
            ('channel_partner_ids', 'in', [other_partner.id]),
        ], limit=1)

        if channel:
            member = channel.channel_member_ids.filtered(
                lambda m: m.partner_id == partner
            )
            if member:
                last_message = request.env['mail.message'].sudo().search([
                    ('res_id', '=', channel.id),
                    ('model', '=', 'discuss.channel'),
                    ('message_type', '=', 'comment'),
                ], order='id desc', limit=1)
                if last_message:
                    member[0].sudo().write({
                        'seen_message_id': last_message.id,
                    })

        return {'status': 'ok'}

    @http.route('/chat/unread_count', type='json', auth='user')
    def unread_count(self):
        partner = request.env.user.partner_id
        total_unread = 0
        partner_unread_counts = {}

        # Fetch blocked users to exclude them from calculations
        blocked_partner_ids = request.env['chat.block.user'].sudo().search([
            ('user_id', '=', partner.id)
        ]).mapped('blocked_user_id').ids

        # Fetch chat channel memberships for the current user
        members = request.env['discuss.channel.member'].sudo().search([
            ('partner_id', '=', partner.id),
            ('channel_id.channel_type', '=', 'chat')
        ])

        for member in members:
            channel = member.channel_id

            # Find the other contact in this direct chat
            other_partner = channel.channel_partner_ids.filtered(lambda p: p.id != partner.id)
            if not other_partner:
                continue

            other_partner_id = other_partner[0].id

            # Skip calculations if the partner is blocked
            if other_partner_id in blocked_partner_ids:
                continue

            seen_id = member.seen_message_id.id or 0

            # Count unread messages from this channel
            unread_messages = request.env['mail.message'].sudo().search_count([
                ('model', '=', 'discuss.channel'),
                ('res_id', '=', channel.id),
                ('id', '>', seen_id),
                ('author_id', '!=', partner.id),
                ('message_type', '=', 'comment')
            ])

            if unread_messages > 0:
                # Store by partner ID string for easy JavaScript object mapping
                partner_unread_counts[str(other_partner_id)] = unread_messages
                total_unread += unread_messages

        return {
            'unread_count': total_unread,
            'partner_unread_counts': partner_unread_counts
        }


class BlockController(http.Controller):

    @http.route('/chat/unblock_user/<int:block_id>', type='http', auth='user', website=True)
    def unblock_user(self, block_id, **kwargs):
        block = request.env['chat.block.user'].sudo().browse(block_id)

        if block.exists():
            block.unlink()

        return request.redirect('/blocked_contacts')

    @http.route('/blocked_contacts', type='http', auth='user', website=True)
    def blocked_contacts(self, **kwargs):
        current = request.env.user.partner_id
        blocked_records = request.env['chat.block.user'].sudo().search([
            ('user_id', '=', current.id)
        ])

        return request.render('subscription_package_website.blocked_contacts_template',
                              {'blocked_records': blocked_records})


class UserProfileController(http.Controller):

    @http.route(['/user/profile'], type='http', auth="user", website=True, methods=['GET', 'POST'])
    def user_profile(self, **post):
        user = request.env.user
        partner = user.partner_id

        if request.httprequest.method == 'POST':
            # 1. Update basic text fields and new address fields
            values = {
                'name': post.get('name'),
                'phone': post.get('phone'),
                'street': post.get('street', '').strip(),
                'street2': post.get('street2', '').strip(),
                'city': post.get('city', '').strip(),
                'zip': post.get('zip', '').strip(),
            }

            # Handle country selection safely
            country_id = post.get('country_id')
            if country_id:
                values['country_id'] = int(country_id)
            else:
                values['country_id'] = False

            # 2. Update email/login securely if changed
            new_email = post.get('email')
            if new_email and new_email != user.login:
                user.sudo().write({'login': new_email})
                partner.sudo().write({'email': new_email})

            # 3. Handle Profile Picture Upload securely
            profile_picture = post.get('profile_picture')
            if profile_picture and hasattr(profile_picture, 'read'):
                file_content = profile_picture.read()
                if file_content:  # Ensure the file is not empty
                    values['image_1920'] = base64.b64encode(file_content)

            # Write values to res.partner
            partner.sudo().write(values)
            return request.redirect('/user/profile?success=1')

        # Fetch all countries for the dropdown
        countries = request.env['res.country'].sudo().search([])

        values = {
            'user': user,
            'partner': partner,
            'countries': countries,
            'success': post.get('success'),
        }
        return request.render('subscription_package_website.user_profile_template', values)
