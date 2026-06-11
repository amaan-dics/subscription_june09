# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
from markupsafe import escape
from html import escape
import re


class SubscriptionMixin:

    def _check_and_sync_subscription(self, partner):
        active_subscription = request.env['subscription.package'].sudo().search([('partner_id', '=', partner.id),
                                                                                 ('stage_id.category', '=', 'progress')
                                                                                 ], limit=1)
        if active_subscription:
            if partner.subscription_plan_id != active_subscription.plan_id:
                partner.sudo().write({'subscription_plan_id': active_subscription.plan_id.id})
            return True
        else:
            free_plan = request.env['subscription.package.plan'].sudo().search(
                [('price', '=', 0)], limit=1
            )
            if free_plan:
                if partner.subscription_plan_id != free_plan:
                    partner.sudo().write({'subscription_plan_id': free_plan.id})
                return True
            # No free plan configured — clear plan and block access
            if partner.subscription_plan_id:
                partner.sudo().write({'subscription_plan_id': False})
            return False


class GenderMatchController(http.Controller, SubscriptionMixin):

    @http.route('/match', type='http', auth='user', website=True)
    def find_match(self, age=None, location=None, **kwargs):
        user = request.env.user
        partner = user.partner_id
        if not self._check_and_sync_subscription(partner):
            return request.render('subscription_package_extended.no_plan_template')
        if partner.kyc_status != 'approved':
            return request.render('subscription_package_extended.kyc_pending_template')
        opposite_gender = 'female' if partner.gender == 'male' else 'male'
        accepted_requests = request.env['connect.request'].sudo().search([('state', '=', 'accepted'),
                                                                          '|', ('from_user_id', '=', partner.id),
                                                                          ('to_user_id', '=', partner.id)])
        excluded_partner_ids = []
        for req in accepted_requests:
            if req.from_user_id.id == partner.id:
                excluded_partner_ids.append(req.to_user_id.id)
            else:
                excluded_partner_ids.append(req.from_user_id.id)
        domain = [('gender', '=', opposite_gender), ('id', '!=', partner.id), ('id', 'not in', excluded_partner_ids),
                  ('kyc_status', '=', 'approved'), ('user_ids', '!=', False)]
        if age:

            if age == '18-25':
                domain += [
                    ('age', '>=', 18),
                    ('age', '<=', 25)
                ]

            elif age == '26-35':
                domain += [
                    ('age', '>=', 26),
                    ('age', '<=', 35)
                ]

            elif age == '36-50':
                domain += [
                    ('age', '>=', 36),
                    ('age', '<=', 50)
                ]
        if location:
            domain.append(('city', 'ilike', location))
        users = request.env['res.partner'].sudo().search(domain)
        requests = request.env['connect.request'].sudo().search(['|', '&', ('from_user_id', '=', partner.id),
                                                                 ('to_user_id', 'in', users.ids),
                                                                 '&', ('from_user_id', 'in', users.ids),
                                                                 ('to_user_id', '=', partner.id)])
        req_map = {}
        for req in requests:
            if req.from_user_id.id == partner.id:
                req_map[req.to_user_id.id] = req
            else:
                req_map[req.from_user_id.id] = req
        locations = request.env['res.partner'].sudo().search([('city', '!=', False)]).mapped('city')
        values = {
            'users': users,
            'current_user': partner,
            'req_map': req_map,
            'locations': sorted(set(locations)),
            'selected_age': age or '',
            'selected_location': location or '',
        }

        return request.render('subscription_package_extended.find_match_template', values)


class ConnectController(http.Controller, SubscriptionMixin):

    @http.route('/chat/<int:user_id>', type='http', auth='user', website=True)
    def chat_page(self, user_id, **kwargs):
        target = request.env['res.partner'].sudo().browse(user_id)
        return request.render('subscription_package_extended.chat_template', {'target_user': target})

    # @http.route('/chat/send', type='json', auth='user')
    # def send_message(self, user_id, message):
    #     current = request.env.user.partner_id
    #     target = request.env['res.partner'].sudo().browse(user_id)
    #     channel = request.env['discuss.channel'].sudo().search([('channel_type', '=', 'chat'),
    #                                                             ('channel_partner_ids', 'in', [current.id]),
    #                                                             ('channel_partner_ids', 'in', [target.id])])
    #     channel = channel.filtered(lambda c: len(c.channel_partner_ids) == 2)
    #     if not channel:
    #         channel = request.env['discuss.channel'].sudo().create({'channel_partner_ids': [(4, current.id),
    #                                                                                         (4, target.id)],
    #                                                                 'channel_type': 'chat',
    #                                                                 'name': f"{current.name}, {target.name}"})
    #     safe_msg = escape(message)
    #     channel.message_post(body=safe_msg, author_id=current.id, message_type='comment',
    #                          subtype_xmlid='mail.mt_comment')
    #     request.env['portal.notification'].sudo().create({'partner_id': target.id, 'message': safe_msg,
    #                                                       'ref_user_id': current.id})
    #     return {'status': 'ok'}

    @http.route('/chat/messages', type='json', auth='user')
    def get_messages(self, user_id):
        current = request.env.user.partner_id
        target = request.env['res.partner'].sudo().browse(int(user_id))
        channel = request.env['discuss.channel'].sudo().search([('channel_type', '=', 'chat'),
                                                                ('channel_partner_ids', 'in', [current.id]),
                                                                ('channel_partner_ids', 'in', [target.id])], limit=1)
        requiest_id = request.env['connect.request'].sudo().search([('to_user_id', '=', current.id),
                                                                    ('from_user_id', '=', int(user_id))], limit=1)

        # [CHANGE 3] Determine chat limit and whether this chat is within the allowed slots
        plan = current.subscription_plan_id
        chat_limit = plan.chat_limit if plan else 0
        all_channels = request.env['discuss.channel'].sudo().search([
            ('channel_type', '=', 'chat'),
            ('channel_partner_ids', 'in', [current.id])
        ])
        # Rank existing chat partners oldest-first so downgraded users keep their earliest chats
        all_channels_sorted = all_channels.sorted(key=lambda c: c.create_date)
        ranked_partner_ids = []
        for ch in all_channels_sorted:
            for p in ch.channel_partner_ids:
                if p.id != current.id and p.id not in ranked_partner_ids:
                    ranked_partner_ids.append(p.id)
        target_uid = int(user_id)
        is_new_chat = target_uid not in ranked_partner_ids
        chats_used = len(ranked_partner_ids)
        if chat_limit > 0 and not is_new_chat and target_uid in ranked_partner_ids:
            position = ranked_partner_ids.index(target_uid) + 1
            chat_limit_reached = position > chat_limit
        else:
            chat_limit_reached = chat_limit > 0 and is_new_chat and chats_used >= chat_limit

        if not channel:
            return {
                'messages': [],
                'channel_archived': False,
                'requiest_id_status': False,
                'chat_limit_reached': chat_limit_reached,  # [CHANGE 3]
            }
        msgs = channel.message_ids.filtered(lambda m: m.message_type == 'comment')
        result = []
        for m in msgs.sorted(key=lambda x: x.date):
            result.append({
                'body': m.body or '',
                'is_me': m.author_id.id == current.id,
                'date': m.date.strftime('%Y-%m-%d %H:%M:%S') if m.date else '',  # [CHANGE 2]
            })

        return {
            'messages': result,
            'requiest_id_status': requiest_id.state if requiest_id else False,
            'channel_archived': not channel.active,
            'channel_id': channel.id,
            'chat_limit_reached': chat_limit_reached,  # [CHANGE 3]
        }

    @http.route('/send_request/<int:user_id>', type='http', auth='user', website=True)
    def send_request(self, user_id, **kwargs):
        current_user = request.env.user.partner_id
        existing = request.env['connect.request'].sudo().search(['|', '&', ('from_user_id', '=', current_user.id),
                                                                 ('to_user_id', '=', user_id),
                                                                 '&', ('from_user_id', '=', user_id),
                                                                 ('to_user_id', '=', current_user.id)], limit=1)
        if not existing:
            req = request.env['connect.request'].sudo().create({'from_user_id': current_user.id, 'to_user_id': user_id})
            target = request.env['res.partner'].sudo().browse(user_id)
            if target.user_ids:
                request.env['bus.bus'].sudo()._sendone(target.id, 'connect_request', {'from': current_user.name,
                                                                                      'request_id': req.id})
        return request.redirect('/match')

    @http.route('/accept_request/<int:req_id>', type='http', auth='user', website=True)
    def accept_request(self, req_id, **kwargs):
        req = request.env['connect.request'].sudo().browse(req_id)
        req.state = 'accepted'
        reverse_req = request.env['connect.request'].sudo().search([('from_user_id', '=', req.to_user_id.id),
                                                                    ('to_user_id', '=', req.from_user_id.id)], limit=1)
        if not reverse_req:
            request.env['connect.request'].sudo().create({'from_user_id': req.to_user_id.id,
                                                          'to_user_id': req.from_user_id.id, 'state': 'accepted'})
        else:
            reverse_req.state = 'accepted'
        return request.redirect('/my_requests')

    @http.route('/reject_request/<int:req_id>', type='http', auth='user', website=True)
    def reject_request(self, req_id, **kwargs):
        req = request.env['connect.request'].sudo().browse(req_id)
        req.state = 'rejected'
        reverse_req = request.env['connect.request'].sudo().search([('from_user_id', '=', req.to_user_id.id),
                                                                    ('to_user_id', '=', req.from_user_id.id)], limit=1)
        if reverse_req:
            reverse_req.state = 'rejected'
        return request.redirect('/my_requests')

    @http.route('/my_requests', type='http', auth='user', website=True)
    def my_requests(self, **kwargs):
        user = request.env.user.partner_id
        if not self._check_and_sync_subscription(user):
            return request.render('subscription_package_extended.no_plan_template')
        if user.kyc_status != 'approved':
            return request.render('subscription_package_extended.kyc_pending_template')

        # 1. Incoming Pending Requests
        incoming_requests = request.env['connect.request'].sudo().search(
            [('to_user_id', '=', user.id), ('state', '=', 'pending')])

        # 2. Outgoing Sent Pending Requests
        sent_requests = request.env['connect.request'].sudo().search(
            [('from_user_id', '=', user.id), ('state', '=', 'pending')])

        # 3. Active Accepted Connections (Matches)
        # Since Odoo creates bidirectional rows on acceptance, searching where from_user_id = user
        # gives us exactly all users this user has successfully matched with.
        accepted_requests = request.env['connect.request'].sudo().search(
            [('from_user_id', '=', user.id), ('state', '=', 'accepted')])

        # [CHANGE 5] Pass connection_limit_reached so template can lock Accept buttons
        plan = user.subscription_plan_id
        connection_limit = plan.connection_limit if plan else 0
        connection_limit_reached = connection_limit > 0 and (user.connection_used / 2) >= connection_limit

        return request.render('subscription_package_extended.request_template', {
            'requests': incoming_requests,  # Kept for backward compatibility if needed
            'incoming_requests': incoming_requests,
            'sent_requests': sent_requests,
            'accepted_requests': accepted_requests,
            'connection_limit_reached': connection_limit_reached,
        })

    @http.route('/cancel_request/<int:req_id>', type='http', auth='user', website=True)
    def cancel_request(self, req_id, **kwargs):
        """Allows a user to cancel an outgoing pending request."""
        user = request.env.user.partner_id
        req = request.env['connect.request'].sudo().browse(req_id)
        if req and req.from_user_id.id == user.id and req.state == 'pending':
            req.unlink()
        return request.redirect('/my_requests')

    @http.route('/unmatch_request/<int:req_id>', type='http', auth='user', website=True)
    def unmatch_request(self, req_id, **kwargs):
        """Removes the connection and hides/archives the active chatbox discussion channel."""
        user = request.env.user.partner_id
        req = request.env['connect.request'].sudo().browse(req_id)

        if req and (req.from_user_id.id == user.id or req.to_user_id.id == user.id):
            partner_id = req.to_user_id.id if req.from_user_id.id == user.id else req.from_user_id.id

            # Find and delete both bidirectional connection records
            all_reqs = request.env['connect.request'].sudo().search([
                ('state', '=', 'accepted'),
                '|',
                '&', ('from_user_id', '=', user.id), ('to_user_id', '=', partner_id),
                '&', ('from_user_id', '=', partner_id), ('to_user_id', '=', user.id)
            ])
            all_reqs.unlink()

            # Archive the chatbox discussion channel so it immediately disappears from the sidebar
            channel = request.env['discuss.channel'].sudo().search([
                ('channel_type', '=', 'chat'),
                ('channel_partner_ids', 'in', [user.id]),
                ('channel_partner_ids', 'in', [partner_id])
            ], limit=1)
            if channel:
                channel.sudo().write({'active': False})

        return request.redirect('/my_requests')

    @http.route('/chatbox', type='http', auth='user', website=True)
    def chatbox(self, user_id=None, **kwargs):
        current = request.env.user.partner_id
        if not self._check_and_sync_subscription(current):
            return request.render('subscription_package_extended.no_plan_template')
        if current.kyc_status != 'approved':
            return request.render('subscription_package_extended.kyc_pending_template')
        plan = current.subscription_plan_id
        chat_limit = plan.chat_limit if plan else 0
        if chat_limit == 0:
            return request.render('subscription_package_extended.chat_limit_reached_template')
        partner_ids = set()
        blocked_ids = request.env['chat.block.user'].sudo().search(
            [('user_id', '=', current.id)]).mapped('blocked_user_id').ids

        muted_ids = request.env['chat.mute.user'].sudo().search([
            ('user_id', '=', request.env.user.partner_id.id)
        ]).mapped('muted_user_id.id')

        requests_data = request.env['connect.request'].sudo().search([('state', '=', 'accepted'), '|',
                                                                      ('from_user_id', '=', current.id),
                                                                      ('to_user_id', '=', current.id)])
        for req in requests_data:
            if req.from_user_id.id == current.id:
                partner_ids.add(req.to_user_id.id)
            else:
                partner_ids.add(req.from_user_id.id)
        channels = request.env['discuss.channel'].sudo().search([('channel_partner_ids', 'in', [current.id]),
                                                                 ('channel_type', '=', 'chat')])
        for channel in channels:
            for partner in channel.channel_partner_ids:
                if partner.id != current.id:
                    partner_ids.add(partner.id)
        partner_ids -= set(blocked_ids)
        partners = request.env['res.partner'].sudo().browse(list(partner_ids))
        selected_partner = False
        if user_id:
            selected_partner = request.env['res.partner'].sudo().browse(int(user_id))
        if not partners:
            return request.render('subscription_package_extended.no_chats_template')
        values = {'partners': partners, 'selected_partner': selected_partner,'muted_ids': muted_ids,}
        return request.render('subscription_package_extended.chatbox_template', values)


class ChatTermsController(http.Controller):
    @http.route('/chat/terms', type='json', auth='user')
    def get_terms(self, user_id=None):
        current = request.env.user.partner_id
        accepted = False
        if user_id:
            accepted = bool(request.env['chat.terms.acceptance'].sudo().search([('user_id', '=', current.id),
                                                                                ('partner_id', '=', int(user_id))],
                                                                               limit=1))
        terms = request.env['chat.terms'].sudo().search([('active', '=', True)], limit=1)
        return {'accepted': accepted, 'content': terms.content if terms else "", 'status': 'ok'}

    @http.route('/chat/terms/accept', type='json', auth='user')
    def accept_terms(self, user_id=None):
        current = request.env.user.partner_id
        if user_id:
            existing = request.env['chat.terms.acceptance'].sudo().search([('user_id', '=', current.id),
                                                                           ('partner_id', '=', int(user_id))], limit=1)
            if not existing:
                request.env['chat.terms.acceptance'].sudo().create({'user_id': current.id, 'partner_id': int(user_id),
                                                                    'accepted_date': fields.Datetime.now()})
        return {'status': 'ok'}

    def _mask_phone_numbers(self, text):
        pattern = r'(?:\+?\d[\d\s\-\(\)]{7,}\d)'

        def replace(match):
            digits = re.sub(r'\D', '', match.group(0))

            if len(digits) < 5:
                return match.group(0)

            return '*' * (len(digits) - 4) + digits[-4:]

        return re.sub(pattern, replace, text)

    def _mask_emails(self, text):
        pattern = r'([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'

        def replace(match):
            username = match.group(1)
            domain = match.group(2)

            if len(username) <= 2:
                masked = '*' * len(username)
            else:
                masked = username[:2] + ('*' * (len(username) - 2))

            return f"{masked}@{domain}"

        return re.sub(pattern, replace, text)

    @http.route('/chat/send', type='json', auth='user')
    def send_message(self, user_id, message):
        current = request.env.user.partner_id
        target = request.env['res.partner'].sudo().browse(user_id)

        channel = request.env['discuss.channel'].sudo().search([
            ('channel_type', '=', 'chat'),
            ('channel_partner_ids', 'in', [current.id]),
            ('channel_partner_ids', 'in', [target.id]),
        ])

        channel = channel.filtered(
            lambda c: len(c.channel_partner_ids) == 2
        )

        if not channel:
            channel = request.env['discuss.channel'].sudo().create({
                'channel_partner_ids': [
                    (4, current.id),
                    (4, target.id)
                ],
                'channel_type': 'chat',
                'name': f"{current.name}, {target.name}",
            })

        # Mask phone numbers
        message = self._mask_phone_numbers(message)

        # Mask emails
        message = self._mask_emails(message)

        safe_msg = escape(message)

        channel.message_post(
            body=safe_msg,
            author_id=current.id,
            message_type='comment',
            subtype_xmlid='mail.mt_comment'
        )

        request.env['portal.notification'].sudo().create({
            'partner_id': target.id,
            'message': safe_msg,
            'ref_user_id': current.id,
        })

        return {'status': 'ok'}

    @http.route('/chat/block_user', type='json', auth='user')
    def block_user(self, user_id):
        current = request.env.user.partner_id
        existing = request.env['chat.block.user'].sudo().search([('user_id', '=', current.id),
                                                                 ('blocked_user_id', '=', int(user_id))], limit=1)
        if not existing:
            request.env['chat.block.user'].sudo().create({'user_id': current.id, 'blocked_user_id': int(user_id)})
        return {'status': 'ok'}

    @http.route('/chat/toggle_block', type='json', auth='user')
    def toggle_block(self, user_id, action):
        print("BLOCK CLICKED", user_id, action)

        current = request.env.user.partner_id

        block_obj = request.env['chat.block.user'].sudo()

        existing = block_obj.search([
            ('user_id', '=', current.id),
            ('blocked_user_id', '=', int(user_id))
        ], limit=1)

        if action == 'block':
            if not existing:
                block_obj.create({
                    'user_id': current.id,
                    'blocked_user_id': int(user_id)
                })
                print("BLOCK CREATED")

        elif action == 'unblock':
            existing.unlink()

        return {'status': 'ok'}

    @http.route('/chat/toggle_mute', type='json', auth='user')
    def toggle_mute(self, user_id, action):
        """
        Toggles mute status for a user.
        Muted users: Messages still arrive + visible in chat.
        Only popup notifications are suppressed.
        """
        current = request.env.user.partner_id
        mute_obj = request.env['chat.mute.user'].sudo()

        existing = mute_obj.search([
            ('user_id', '=', current.id),
            ('muted_user_id', '=', int(user_id))
        ], limit=1)

        if action == 'mute':
            if not existing:
                mute_obj.create({
                    'user_id': current.id,
                    'muted_user_id': int(user_id)
                })
        elif action == 'unmute':
            if existing:
                existing.unlink()

        return {'status': 'ok'}

    # Optional: Single mute route (if you want simple mute without toggle)
    @http.route('/chat/mute_user', type='json', auth='user')
    def mute_user(self, user_id):
        current = request.env.user.partner_id
        existing = request.env['chat.mute.user'].sudo().search([
            ('user_id', '=', current.id),
            ('muted_user_id', '=', int(user_id))
        ], limit=1)
        if not existing:
            request.env['chat.mute.user'].sudo().create({
                'user_id': current.id,
                'muted_user_id': int(user_id)
            })
        return {'status': 'ok'}


