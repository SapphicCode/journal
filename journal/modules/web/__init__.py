import datetime
import functools
import jwt.exceptions
import mistune
import pytz
from flask import Blueprint, render_template, request, Request, redirect, abort, Response, current_app

from journal.db import User
from journal.helpers import recaptcha

bp = Blueprint('web', __name__, url_prefix='', static_folder='static', static_url_path='/static',
               template_folder='templates')


class ExtendedRequest(Request):  # just to make my IDE happy
    user: User


class ValidationError(Exception):
    pass


request: ExtendedRequest = request
markdown = mistune.Markdown()


def active(request: Request, page):
    if request.full_path.startswith(page):
        return 'active'
    return ''


def base_data(request: ExtendedRequest, **additional):
    # noinspection PyUnresolvedReferences
    data = {
        'request': request, 'active': lambda page: active(request, page), 'b': __builtins__,
        'csrf': lambda **kwargs: generate_csrf(request, **kwargs), 'app': current_app, 'recaptcha': recaptcha,
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


def generate_csrf(request: ExtendedRequest, expiry=60 * 60 * 24) -> str:
    expiry = datetime.datetime.now(tz=pytz.UTC) + datetime.timedelta(seconds=expiry)
    audience = str(request.user.id if request.user else None)
    return current_app.db.jwt.encode(exp=expiry, aud=audience)


def validate_form(request: ExtendedRequest):
    data = request.form.get('csrf', '')
    audience = str(request.user.id if request.user else None)
    try:
        current_app.db.jwt.decode(data, audience=audience)
    except (jwt.DecodeError, jwt.InvalidTokenError):
        raise ValidationError('The CSRF token submitted with the form is invalid.')


@bp.route('/')
def root():
    return redirect('/login', 302)


@bp.before_request
def setup():
    token = request.cookies.get('token')
    request.user = current_app.db.get_user(token=token)


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


@bp.route('/terms')
def terms():
    return render_template('terms.jinja2', **base_data(request))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        resp = redirect('/app', 302)

        username = request.form.get('username')
        password = request.form.get('password')
        if not (username and password):
            return render_template('login.jinja2', **base_data(request), warn='Required fields left empty.')

        if recaptcha.is_enabled():
            if not recaptcha.validate(request.form.get('g-recaptcha-response')):
                return render_template('login.jinja2', **base_data(request), warn='reCAPTCHA failed.')

        user = current_app.db.get_user(username=username)
        if user:
            if user.check_pw(password):
                resp.set_cookie('token', user.create_token(),
                                expires=datetime.datetime.now(tz=pytz.UTC) + datetime.timedelta(days=365))
                return resp
            else:
                return render_template('login.jinja2', **base_data(request), warn='Invalid password. Please try again.')
        else:
            try:
                user = current_app.db.create_user(username, password)
            except AssertionError as e:
                return render_template('login.jinja2', **base_data(request),
                                       warn='Unable to create account: {}'.format(e))
            resp.set_cookie('token', user.create_token(),
                            expires=datetime.datetime.now(tz=pytz.UTC) + datetime.timedelta(days=365))
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
        new_token_required = False

        # security settings
        uname = request.form.get('username')
        if uname:
            try:
                request.user.username = uname
            except AssertionError as e:
                warn += str(e) + '\n'
        if request.form.get('password'):
            request.user.password = request.form.get('password')
            new_token_required = True

        # personalization
        dname = request.form.get('display-name')
        if dname:
            request.user.display_name = dname
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
            'title_font': request.form.get('title-font') or request.user.settings.get('title_font'),
            'body_font': request.form.get('body-font') or request.user.settings.get('body_font'),
        }
        expiry = request.form.get('session-length')
        if expiry:
            try:
                expiry = int(expiry)
                if expiry < 0:
                    raise ValueError('Cannot have a negative expiry time.')
                if 0 < expiry < 3600:  # cleverly dodging 0
                    raise ValueError('A session expiry time under 1 hour is potentially dangerous '
                                     'and could lock you out of your account forever.')
                request.user.token_expiry = datetime.timedelta(seconds=expiry)
                new_token_required = True
            except ValueError as e:
                warn += f'{e}\n'
            except OverflowError:
                warn += f'Please pick a smaller session expiry time.'
        request.user.settings.update(new_settings)
        request.user.save_setings()

        r = render_template('app/settings.jinja2', **base_data(request), settings=request.user.settings,
                            notice='Settings saved.', warn=warn.strip(), **additional)
        r = Response(r)
        if new_token_required:
            r.set_cookie('token', request.user.create_token(),
                         expires=datetime.datetime.now(tz=pytz.UTC) + datetime.timedelta(days=365))
        return r
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
    e = current_app.db.create_entry(request.user)
    return redirect('/app/entry/{}/edit'.format(e.id), 302)


@bp.errorhandler(404)
def not_found(_):
    return render_template('errors/404.jinja2', **base_data(request))


@bp.errorhandler(403)
def forbidden(_):
    return render_template('errors/403.jinja2', **base_data(request))


@bp.errorhandler(ValidationError)
def validation_error(e):
    return render_template('errors/403.jinja2', info=str(e), **base_data(request))


@bp.route('/app/entry/<_id>/view')
@login_required
def entry_view(_id):
    try:
        entry = current_app.db.get_entry(int(_id))
    except ValueError:
        entry = None
    if entry is None or not entry.can_access(request.user):
        return abort(404)

    return render_template('app/entry/view.jinja2', **base_data(request),
                           entry_html=markdown(entry.content), entry=entry)


@bp.route('/app/entry/<_id>/edit', methods=['GET', 'POST'])
@login_required
def entry_edit(_id):
    try:
        entry = current_app.db.get_entry(int(_id))
    except ValueError:
        entry = None
    if entry is None or not entry.can_edit(request.user):
        return abort(404)

    if request.method == 'POST':
        entry.title = request.form.get('title', '')
        entry.content = request.form.get('body', '')
        entry.tags_human = request.form.get('tags', '')
        entry.commit()
        return redirect('/app/entry/{}/view'.format(_id), 302)

    return render_template('app/entry/edit.jinja2', **base_data(request), entry=entry)


@bp.route('/app/entry/<_id>/delete', methods=['GET', 'POST'])
@login_required
def entry_delete(_id):
    try:
        entry = current_app.db.get_entry(int(_id))
    except ValueError:
        entry = None
    if entry is None or not entry.can_edit(request.user):
        return abort(404)

    if request.method == 'POST':
        entry.delete()
        return redirect('/app/entries', 302)

    return render_template('app/entry/delete.jinja2', **base_data(request), entry=entry)


@bp.route('/app/admin')
@login_required
def admin():
    if 'admin' not in request.user.flags:
        return abort(403)
    return render_template('app/admin.jinja2', **base_data(request))
