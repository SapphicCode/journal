import typing
import functools
import ujson

from flask import Blueprint, Response, current_app, abort, request
from werkzeug.exceptions import HTTPException

from journal.helpers import recaptcha
from journal.db.dataclasses import User, Entry


bp = Blueprint(name='api', import_name=__name__, url_prefix='/api')


class UserException(Exception):
    def __init__(self, msg):
        super().__init__(msg)


def verify_fields(data, check: typing.Dict[str, typing.Any], *ignore: str) -> dict:
    verified = {}

    if not isinstance(data, dict):
        raise UserException('Data payload is invalid.')

    for k, v in check.items():
        if k not in data:
            raise UserException('Required field "{}" missing.'.format(k))
        if not isinstance(data[k], v):
            raise UserException('Field "{}" was of type "{}", "{}" expected.'
                                .format(k, type(data[k]).__name__, v.__name__))
        verified[k] = data[k]

    for k in ignore:
        if k in data:
            verified[k] = data[k]

    return verified


def respond(data: typing.Optional[typing.Union[dict, list]] = None, *, status: int = 200):
    resp = Response()
    if not data:
        status = 204
    resp.status_code = status

    if data:
        if not isinstance(data, list) and not isinstance(data, dict):
            data['response'] = data
        resp.data = ujson.dumps(data)
        resp.headers = {'Content-Type': 'application/json'}

    return resp


def serialize_user(user: User) -> dict:
    return {
        'id': user.id,
        'username': user.username,
        'display_name': user.display_name,
        'flags': user.flags,
        'timezone': user.timezone.zone,
        'token_revision': user.token_revision,
        'token_expiry': user.token_expiry,
        'settings': user.settings,
    }


def serialize_entry(entry: Entry) -> dict:
    return {
        'id': entry.id,
        'author_id': entry.author_id,
        'title': entry.title,
        'content': entry.content,
        'tags': entry.tags,
        'timestamp': entry.timestamp.isoformat(),
    }


@bp.before_request
def setup():
    auth = request.headers.get('Authorization')
    if auth:
        request.user = current_app.db.get_user(token=auth)
    else:
        request.user = None


def auth_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not request.user:
            return abort(401)
        return f(*args, **kwargs)

    return decorated


def error(e):
    return respond({'error': {'code': e.code, 'name': e.name}}, status=e.code)


@bp.errorhandler(HTTPException)
def errorhandler(e):
    return error(e)


@bp.errorhandler(UserException)
def user_exception(e):
    return respond({'error': {'code': 400, 'name': 'Bad Request', 'info': str(e)}}, status=400)


@bp.route('/login', methods=['POST'])
def login():
    data = verify_fields(request.json, {'username': str, 'password': str}, 'recaptcha_response')
    if recaptcha.is_enabled():
        data = verify_fields(data, {'recaptcha_response': str}, 'username', 'password')
        if not recaptcha.validate(data['recaptcha_response']):
            raise UserException('reCAPTCHA was invalid.')

    user = current_app.db.get_user(username=data['username'])
    if user is None:
        raise UserException('Username or password invalid.')
    if not user.check_pw(data['password']):
        raise UserException('Username or password invalid.')
    return respond({'token': user.create_token()})


@bp.route('/users/@me', methods=['GET'])
@auth_required
def me():
    return respond(serialize_user(request.user))


@bp.route('/entries', methods=['GET'])
@auth_required
def entries():
    return respond([
        {'id': x.id, 'author_id': x.id, 'title': x.title, 'tags': x.tags, 'timestamp': x.timestamp.isoformat()}
        for x in request.user.entries()
    ])


# noinspection PyShadowingBuiltins
@bp.route('/entries/<id>', methods=['GET'])
@auth_required
def entry(id):
    try:
        id = int(id)
        if id < 0:
            raise ValueError()
    except ValueError:
        raise UserException('ID given is not an integer.')

    entry = current_app.db.get_entry(id)
    if not entry or not entry.can_access(request.user):
        return abort(404)

    return respond(serialize_entry(entry))
