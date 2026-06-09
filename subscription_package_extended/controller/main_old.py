# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
from odoo.addons.payment_custom.controllers.main import CustomController
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.payment.controllers.portal import PaymentPortal
import base64


class WebsiteHomeInherit(http.Controller):

    @http.route('/', type='http', auth='public', website=True)
    def homepage(self, **kwargs):
        user = request.env.user
        is_public = user._is_public()
        plans = request.env['subscription.package.plan'].sudo().search([])
        active_subscription = False
        current_plan_id = False
        remaining_days = 0
        amount = 0.00
        if not is_public:
            partner = user.partner_id
            active_subscription = request.env['subscription.package'].sudo().search([('partner_id', '=', partner.id),
                                                                                     ('stage_id.category', '=',
                                                                                      'progress')], limit=1)
            if active_subscription:
                current_plan_id = active_subscription.plan_id.id
                amount = active_subscription.total_recurring_price
                if partner.subscription_plan_id != active_subscription.plan_id:
                    partner.sudo().write({'subscription_plan_id': active_subscription.plan_id.id})
            else:
                partner.sudo().write({'subscription_plan_id': False})
            if active_subscription and active_subscription.next_invoice_date and active_subscription.start_date:
                exp_date = fields.Date.to_date(active_subscription.next_invoice_date)
                start_date = fields.Date.to_date(active_subscription.start_date)
                remaining_days = (exp_date - start_date).days
                if remaining_days < 0:
                    remaining_days = 0
        values = {'plans': plans, 'is_public': is_public, 'is_user': not is_public, 'amount': amount,
                  'active_subscription': active_subscription, 'current_plan_id': current_plan_id,
                  'remaining_days': remaining_days}
        return request.render('website.homepage', values)


class SignupExtended(AuthSignupHome):

    @http.route('/web/signup', type='http', auth='public', website=True, sitemap=False)
    def web_auth_signup(self, *args, **kw):
        kw['redirect'] = '/'
        response = super(SignupExtended, self).web_auth_signup(*args, **kw)
        if request.httprequest.method == 'POST':
            login = kw.get('login')
            selfie = kw.get('selfie')
            profile_pic = kw.get('profile_pic')
            id_proof = kw.get('id_proof')
            gender = kw.get('gender')
            age = kw.get('age')
            phone = kw.get('phone')
            address = kw.get('address')
            if login:
                user = request.env['res.users'].sudo().search([('login', '=', login)], limit=1)
                if user and user.partner_id:
                    vals = {
                        'kyc_status': 'pending',
                        'gender': gender,
                        'age': int(age) if age else False,
                        'phone': phone,
                        'address': address,
                    }
                    if selfie:
                        try:
                            if ',' in selfie:
                                selfie_data = selfie.split(',')[1]
                            else:
                                selfie_data = selfie
                            vals['selfie'] = selfie_data
                            vals['selfie_filename'] = 'selfie.png'
                        except Exception as e:
                            print("SELFIE ERROR:", e)

                    if id_proof:
                        vals['id_proof'] = base64.b64encode(id_proof.read())
                        vals['id_proof_filename'] = id_proof.filename
                    if profile_pic:
                        vals['image_1920'] = base64.b64encode(profile_pic.read())
                    user.partner_id.sudo().write(vals)
                    return request.redirect('/')
        return response


class SelfieController(http.Controller):

    @http.route('/selfie-capture', type='http', auth='public', website=True)
    def selfie_page(self, **kw):
        return request.render('subscription_package_extended.selfie_capture_template')


class PortalNotificationController(http.Controller):

    @http.route('/portal/notifications', type='json', auth='user')
    def get_notifications(self):
        current = request.env.user.partner_id

        # [CHANGE 13] Fetch muted partner ids for this user so we can
        # suppress their popup notifications below.
        muted_ids = request.env['chat.mute.user'].sudo().search([
            ('user_id', '=', current.id)
        ]).mapped('muted_user_id').ids

        notifications = request.env['portal.notification'].sudo().search([
            ('partner_id', '=', current.id),
            ('is_read', '=', False)
        ], order='create_date desc', limit=20)

        result = []
        for n in notifications:
            sender = n.ref_user_id

            # [CHANGE 13] Skip popup if sender is muted.
            # The notification is NOT deleted and still counts toward
            # unread_count — muting only suppresses the popup display.
            if sender.id in muted_ids:
                continue

            result.append({
                'id': n.id,
                'from': sender.name if sender else 'Unknown',
                'from_id': sender.id if sender else 0,
                'message': n.message or '',
                'image': '/partner/avatar/%s/image_128' % (n.ref_user_id.id if n.ref_user_id else 0)
            })

        # unread_count includes ALL unread notifications (including muted)
        # because the badge should reflect true unread state.
        unread_count = request.env['portal.notification'].sudo().search_count([
            ('partner_id', '=', current.id),
            ('is_read', '=', False)
        ])

        return {
            'notifications': result,
            'unread_count': unread_count,
        }


@http.route('/chat/contacts_unread_counts', type='json', auth='user')
def chat_contacts_unread_counts(self, **kwargs):
    partner = request.env.user.partner_id

    # Pull blocked contacts to exclude them from counts
    blocked_partner_ids = []
    if request.env['chat.block.user']:
        blocked_partner_ids = request.env['chat.block.user'].sudo().search([
            ('user_id', '=', partner.id)
        ]).mapped('blocked_user_id.id')

    # Find all chat channel memberships for the logged-in user
    members = request.env['discuss.channel.member'].sudo().search([
        ('partner_id', '=', partner.id)
    ])

    unread_map = {}
    for member in members:
        channel = member.channel_id
        if channel.channel_type != 'chat':
            continue

        # Identify the other user in this direct chat
        other_members = channel.channel_member_ids.filtered(lambda m: m.partner_id.id != partner.id)
        if not other_members:
            continue
        other_partner_id = other_members[0].partner_id.id

        if other_partner_id in blocked_partner_ids:
            continue

        # Compare against the user's last seen message ID milestone
        seen_id = member.seen_message_id.id or 0
        count = request.env['mail.message'].sudo().search_count([
            ('model', '=', 'discuss.channel'),
            ('res_id', '=', channel.id),
            ('id', '>', seen_id),
            ('author_id', '!=', partner.id),
            ('author_id', 'not in', blocked_partner_ids),
            ('message_type', '=', 'comment'),
        ])

        if count > 0:
            unread_map[other_partner_id] = count

    return unread_map

class PartnerAvatarController(http.Controller):

    @http.route('/partner/avatar/<int:partner_id>/<string:field>', type='http', auth='public', website=True)
    def get_partner_avatar(self, partner_id, field='image_128', **kwargs):
        # Force field security to prevent reading sensitive document fields
        if field not in ['image_128', 'image_1920']:
            field = 'image_128'

        partner = request.env['res.partner'].sudo().browse(partner_id)

        # Security Wall: Only serve avatars for users who are approved matches
        if not partner.exists() or partner.kyc_status != 'approved':
            return request.redirect('/web/static/img/placeholder.png')

        image_base64 = partner[field]
        if not image_base64:
            return request.redirect('/web/static/img/placeholder.png')

        try:
            image_data = base64.b64decode(image_base64)
        except Exception:
            return request.redirect('/web/static/img/placeholder.png')

        headers = [
            ('Content-Type', 'image/png'),
            ('Content-Length', len(image_data)),
            ('Cache-Control', 'public, max-age=86400'), # Cache for 24 hours to boost performance
        ]
        return request.make_response(image_data, headers)