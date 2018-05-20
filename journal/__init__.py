from flask import Flask, request

from journal.db import DatabaseInterface
from journal.db.util import JWTEncoder
from journal.modules import web


def create_app(**settings) -> Flask:
    db = DatabaseInterface(
        settings['mongodb_uri'], settings['mongodb_db'], settings['idgen_worker_id'], settings['secret_key']
    )

    app = Flask(__name__, static_folder=None)
    app.register_blueprint(web.bp)

    @app.before_request
    def setup():
        request.db = db
        request.recaptcha = settings['recaptcha']
        return

    return app
