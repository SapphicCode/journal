import datetime
import functools
import markdown2
import pytz
import requests
import typing
import jwt.exceptions
from flask import Blueprint, render_template, request, Request, redirect, abort
from jinja2 import escape

from journal.db import DatabaseInterface, User
from journal.db.util import JWTEncoder

bp = Blueprint('web', __name__, url_prefix='', static_folder='static', static_url_path='/static',
               template_folder='templates')
session = requests.Session()


class ExtendedRequest(Request):  # just to make my IDE happy
    db: DatabaseInterface
    recaptcha: typing.Dict[str, str]
    user: User
    signer: JWTEncoder


class ValidationError(Exception):
    pass


request: ExtendedRequest = request


def active(request: Request, page):
    if request.full_path.startswith(page):
        return 'active'
    return ''


def base_data(request: ExtendedRequest, **additional):
    # noinspection PyUnresolvedReferences
    data = {
        'request': request, 'active': lambda page: active(request, page), 'b': __builtins__,
        'csrf': lambda **kwargs: generate_csrf(request, **kwargs),
    }
    data.update(additional)

    data['fonts'] = {}
    if request.user:
        data['fonts'] = {
            'title': request.user.settings.get('title_font'),
            'body': request.user.settings.get('body_font'),
        }
    if not data['fonts'].get('title'):
        data['fonts']['title'] = 'Lato'
    if not data['fonts'].get('body'):
        data['fonts']['body'] = 'Open Sans'

    return data


def generate_csrf(request: ExtendedRequest, expiry=60*60*24) -> str:
    expiry = datetime.datetime.now(tz=pytz.UTC) + datetime.timedelta(seconds=expiry)
    audience = str(request.user.id if request.user else None)
    return request.signer.encode(exp=expiry, aud=audience)


def validate_form(request: ExtendedRequest):
    data = request.form.get('csrf', '')
    audience = str(request.user.id if request.user else None)
    try:
        request.signer.decode(data, audience=audience)
    except (jwt.DecodeError, jwt.InvalidTokenError):
        raise ValidationError('The CSRF token submitted with the form is invalid.')


@bp.route('/')
def root():
    return redirect('/login', 302)


@bp.before_request
def setup():
    token = request.cookies.get('token')
    request.user = request.db.get_user(token=token)


@bp.before_request
def verify_csrf():
    if request.form:
        validate_form(request)


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not request.user:
            return redirect('/logout', 302)
        return f(*args, **kwargs)
    return decorated


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        resp = redirect('/app', 302)

        username = request.form.get('username')
        password = request.form.get('password')
        if not (username and password):
            return render_template('login.jinja2', **base_data(request), warn='Required fields left empty.')

        captcha = request.form.get('g-recaptcha-response')
        if not captcha:
            captcha = 'fail'
        success = session.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data={
                'secret': request.recaptcha['secret'],
                'response': captcha,
            }
        ).json()['success']
        if not success:
            return render_template('login.jinja2', **base_data(request), warn='reCAPTCHA failed.')

        user = request.db.get_user(username=username)
        if user:
            if user.check_pw(password):
                resp.set_cookie('token', request.db.create_token(user),
                                expires=datetime.datetime.now(tz=pytz.UTC) + datetime.timedelta(days=365))
                return resp
            else:
                return render_template('login.jinja2', **base_data(request), warn='Invalid password. Please try again.')
        else:
            try:
                user = request.db.create_user(username, password)
            except AssertionError as e:
                return render_template('login.jinja2', **base_data(request),
                                       warn='Unable to create account: {}'.format(e))
            resp.set_cookie('token', request.db.create_token(user))
            return resp

    token = request.cookies.get('token')
    if token:
        return redirect('/app', 302)

    return render_template('login.jinja2', **base_data(request))


@bp.route('/logout')
def logout():
    resp = redirect('/login', 302)
    resp.delete_cookie('token')
    return resp


@bp.route('/app')
@login_required
def app():
    return redirect('/app/entries', 302)


@bp.route('/app/entries')
@login_required
def entries():
    tag = request.args.get('tag')
    if tag:
        tag = tag.strip().lower()
    return render_template('app/entries.jinja2', **base_data(request),
                           entries=request.user.entries(tag), filter=tag)


@bp.route('/app/settings', methods=['GET', 'POST'])
@login_required
def settings():
    additional = {
        'timezones': pytz.common_timezones
    }
    if request.method == 'POST':
        warn = ''
        uname = request.form.get('username')
        if uname:
            try:
                request.user.username = uname
            except AssertionError as e:
                warn += str(e) + '\n'
        dname = request.form.get('display-name')
        if dname:
            request.user.display_name = dname
        if request.form.get('password'):
            request.user.password = request.form.get('password')
        theme = request.form.get('theme')
        if theme in ['light', 'dark']:
            request.user.settings['theme'] = theme
        tz = request.form.get('timezone')
        if tz:
            try:
                request.user.timezone = pytz.timezone(tz)
            except pytz.UnknownTimeZoneError:
                warn += 'Unknown time zone selected. What are you playing at?\n'
        new_settings = {
            'title_font': request.form.get('title-font'),
            'body_font': request.form.get('body-font'),
        }
        request.user.settings.update(new_settings)
        request.user.save_setings()
        return render_template('app/settings.jinja2', **base_data(request), settings=request.user.settings,
                               notice='Settings saved.', warn=warn.strip(), **additional)
    return render_template('app/settings.jinja2', **base_data(request), **additional, settings=request.user.settings)


@bp.route('/app/settings/delete-account', methods=['GET', 'POST'])
@login_required
def account_delete():
    if request.method == 'POST':
        request.user.delete()
        return redirect('/', 302)
    return render_template('app/account_delete.jinja2', **base_data(request))


@bp.route('/app/entries/new')
@login_required
def entries_new():
    e = request.db.create_entry(request.user)
    return redirect('/app/entry/{}/edit'.format(e.id), 302)


@bp.errorhandler(404)
def not_found(_):
    return render_template('app/404.jinja2', **base_data(request))


@bp.errorhandler(403)
def forbidden(_):
    return render_template('app/403.jinja2', **base_data(request))


@bp.errorhandler(ValidationError)
def validation_error(e):
    return render_template('app/403.jinja2', info=str(e), **base_data(request))


@bp.route('/app/entry/<_id>/view')
@login_required
def entry_view(_id):
    try:
        entry = request.db.get_entry(int(_id))
    except ValueError:
        entry = None
    if entry is None or entry.author_id != request.user.id:
        return abort(404)

    return render_template('app/entry_view.jinja2', **base_data(request),
                           entry_html=markdown2.markdown(escape(entry.content)), entry=entry)


@bp.route('/app/entry/<_id>/edit', methods=['GET', 'POST'])
@login_required
def entry_edit(_id):
    try:
        entry = request.db.get_entry(int(_id))
    except ValueError:
        entry = None
    if entry is None or entry.author_id != request.user.id:
        return abort(404)

    if request.method == 'POST':
        entry.title = request.form.get('title', '')
        entry.content = request.form.get('body', '')
        entry.tags = request.form.get('tags', '').split(',')
        return redirect('/app/entry/{}/view'.format(_id), 302)

    return render_template('app/entry_edit.jinja2', **base_data(request), entry=entry)


@bp.route('/app/entry/<_id>/delete', methods=['GET', 'POST'])
@login_required
def entry_delete(_id):
    try:
        entry = request.db.get_entry(int(_id))
    except ValueError:
        entry = None
    if entry is None or entry.author_id != request.user.id:
        return abort(404)

    if request.method == 'POST':
        entry.delete()
        return redirect('/app/entries', 302)

    return render_template('app/entry_delete.jinja2', **base_data(request), entry=entry)


@bp.route('/app/admin')
@login_required
def admin():
    if 'admin' not in request.user.flags:
        return abort(403)
    return render_template('app/admin.jinja2', **base_data(request))
