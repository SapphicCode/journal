import yaml
from flask import Flask, request

from journal.db import DatabaseInterface
from journal.db.util import JWTEncoder
from journal.modules import web


def create_app(**settings) -> Flask:
    recaptcha_enabled = settings.get('recaptcha_enabled', True)

    db = DatabaseInterface(
        settings['mongodb_uri'], settings['mongodb_db'], settings['idgen_worker_id'], settings['secret_key']
    )

    app = Flask(__name__, static_folder=None)

    app.recaptcha_enabled = recaptcha_enabled

    app.register_blueprint(web.bp)

    @app.before_request
    def setup():
        request.db = db
        if recaptcha_enabled:
            request.recaptcha = {'secret': settings['recaptcha_secret'], 'site': settings['recaptcha_site']}

    return app


def create_app_from_config_file(path='config.yml'):
    data = yaml.safe_load(open(path))
    app = create_app(
        idgen_worker_id=data.get('idgen_worker_id', 0),
        mongodb_db=data.get('mongodb_db', 'journal'),
        mongodb_uri=data.get('mongodb_uri', 'mongodb://localhost'),
        recaptcha_secret=data.get('recaptcha_secret', '6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe'),
        recaptcha_site=data.get('recaptcha_site', '6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI'),
        recaptcha_enabled=data.get('recaptcha_enabled', True),
        secret_key=data['secret_key'],
    )
    return app
