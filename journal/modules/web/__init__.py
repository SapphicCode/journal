import functools
import markdown2
import requests
import typing
from flask import Blueprint, render_template, request, Request, redirect, abort
from jinja2 import escape

from journal.db import DatabaseInterface, User

bp = Blueprint('web', __name__, url_prefix='', static_folder='static', template_folder='templates')
session = requests.Session()


class ExtendedRequest(Request):  # just to make my IDE happy
    db: DatabaseInterface
    recaptcha: typing.Dict[str, str]
    user: User


request: ExtendedRequest = request


def active(request: Request, page):
    if request.full_path.startswith(page):
        return 'active'
    return ''


def base_data(request: ExtendedRequest, **additional):
    data = {'request': request, 'active': lambda page: active(request, page), 'len': len}
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


@bp.route('/')
def root():
    return redirect('/login', 302)


@bp.before_request
def setup():
    token = request.cookies.get('token')
    request.user = request.db.get_user(token=token)


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not request.user:
            return redirect('/logout', 302)
        return f(*args, **kwargs)
    return decorated


@bp.route('/static/style.css')
def style():
    return bp.send_static_file('style.css')


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
                resp.set_cookie('token', request.db.create_token(user))
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
    return render_template('app/entries.jinja2', **base_data(request), entries=list(request.user.entries))


@bp.route('/app/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        warn = ''
        if request.form.get('username'):
            try:
                request.user.username = request.form.get('username')
            except AssertionError as e:
                warn += str(e) + '\n'
        if request.form.get('display-name'):
            request.user.display_name = request.form.get('display-name')
        if request.form.get('password'):
            request.user.password = request.form.get('password')
        new_settings = {
            'title_font': request.form.get('title-font'),
            'body_font': request.form.get('body-font'),
        }
        request.user.settings.update(new_settings)
        request.user.save_setings()
        return render_template('app/settings.jinja2', **base_data(request), settings=request.user.settings,
                               notice='Settings saved.', warn=warn.strip())
    return render_template('app/settings.jinja2', **base_data(request), settings=request.user.settings)


@bp.route('/app/entries/new')
def entries_new():
    e = request.db.create_entry()
    e.author = request.user
    return redirect('/app/entry/{}/edit'.format(e.id), 302)


@bp.errorhandler(404)
def not_found(_):
    return render_template('app/404.jinja2', **base_data(request))


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
                           entry_html=markdown2.markdown(escape(entry.content)), heading=entry.title)


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
        new_title = request.form.get('title')
        if new_title:
            entry.title = new_title
        new_body = request.form.get('body')
        if new_body:
            entry.content = new_body
        return redirect('app/entry/{}/view'.format(_id), 302)

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
