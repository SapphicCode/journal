import typing

import requests
from flask import current_app as app


session = requests.Session()


def is_enabled() -> bool:
    return app.recaptcha_enabled


def get_site_key() -> str:
    if not is_enabled():
        return ''
    return app.recaptcha['site']


def _get_secret() -> str:
    return app.recaptcha['secret']


def validate(response: str) -> bool:
    if not is_enabled():
        return True

    success = False
    if not response:
        return success

    success = session.post(
        'https://www.google.com/recaptcha/api/siteverify',
        data={
            'secret': _get_secret(),
            'response': response,
        }
    ).json()['success']

    return success
