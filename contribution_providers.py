import json
import os
import re
from urllib.parse import urlsplit
from uuid import UUID

import requests


class ProviderError(Exception):
    pass


def public_url():
    base = os.getenv('PARISH_PUBLIC_URL', '').rstrip('/')
    url = urlsplit(base)
    if url.scheme == 'https' and url.hostname and not (url.path or url.query or url.fragment or url.username):
        return base
    return ''


def asaas_mode():
    mode = os.getenv('ASAAS_MODE')
    if (mode in ('sandbox', 'production') and public_url() and os.getenv('ASAAS_API_KEY')
            and len(os.getenv('ASAAS_WEBHOOK_TOKEN', '')) >= 32):
        return mode
    return None


def create_pix_checkout(amount, label, return_url):
    mode = asaas_mode()
    if not mode:
        raise ProviderError('Checkout indisponível')
    api = 'api-sandbox.asaas.com' if mode == 'sandbox' else 'api.asaas.com'
    host = 'sandbox.asaas.com' if mode == 'sandbox' else 'asaas.com'
    try:
        response = requests.post(
            f'https://{api}/v3/checkouts',
            headers={'access_token': os.environ['ASAAS_API_KEY']},
            json={
                'billingTypes': ['PIX'],
                'chargeTypes': ['DETACHED'],
                'minutesToExpire': 60,
                'callback': {key: return_url for key in ('successUrl', 'cancelUrl', 'expiredUrl')},
                'items': [{'name': label, 'quantity': 1, 'value': float(amount)}],
            },
            timeout=8, allow_redirects=False,
        )
        if not response.ok or response.is_redirect:
            raise ProviderError(f'Asaas respondeu com HTTP {response.status_code}')
        data = response.json()
        checkout_id = str(UUID(data['id']))
        link = data.get('link') or f'https://{host}/checkoutSession/show?id={checkout_id}'
        parsed = urlsplit(link)
        if parsed.scheme != 'https' or parsed.netloc != host or not parsed.path.startswith('/checkoutSession/show'):
            raise ProviderError('Link de checkout inesperado')
        return checkout_id, link
    except (requests.RequestException, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ProviderError('Resposta do Asaas indisponível ou inválida') from exc


def whatsapp_sender():
    sender = os.getenv('TWILIO_WHATSAPP_FROM', '')
    if (public_url() and re.fullmatch(r'whatsapp:\+[1-9][0-9]{7,14}', sender)
            and re.fullmatch(r'AC[0-9a-fA-F]{32}', os.getenv('TWILIO_ACCOUNT_SID', ''))
            and os.getenv('TWILIO_AUTH_TOKEN')):
        return sender
    return None


def reminder_template():
    sid = os.getenv('TWILIO_REMINDER_CONTENT_SID', '')
    if re.fullmatch(r'HX[0-9a-fA-F]{32}', sid):
        return sid
    return None


def send_reminder(phone, snippet, contribution_url):
    account = os.environ['TWILIO_ACCOUNT_SID']
    try:
        response = requests.post(
            f'https://api.twilio.com/2010-04-01/Accounts/{account}/Messages.json',
            auth=(account, os.environ['TWILIO_AUTH_TOKEN']),
            data={
                'From': whatsapp_sender(),
                'To': phone,
                'ContentSid': reminder_template(),
                'ContentVariables': json.dumps({'1': snippet, '2': contribution_url}),
            },
            timeout=8, allow_redirects=False,
        )
        if response.status_code != 201:
            raise ProviderError(f'Twilio respondeu com HTTP {response.status_code}')
        return response.json()['sid']
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise ProviderError('Resposta do Twilio indisponível ou inválida') from exc
