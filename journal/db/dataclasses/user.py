import argon2
import datetime
import pymongo
import pymongo.errors
import pymongo.results
import pytz
import typing
from autoslot import Slots

from .entry import Entry

if typing.TYPE_CHECKING:
    from journal.db import DatabaseInterface


class User(Slots):
    def __init__(self, db: 'DatabaseInterface' = None, **data):
        self.db = db
        # meta
        self.id = data.get('_id')
        self._username = data.get('username')
        self._pw_hash = data.get('password')
        display_backup = self._username.replace('-', ' ').replace('_', ' ').replace('.', ' ').title()
        self._display_name = data.get('display_name', display_backup)
        self.flags = data.get('flags', [])
        self._timezone = pytz.timezone(data.get('timezone', 'UTC'))
        # tokens
        self._token_revision = data.get('token_revision') or 0
        self._token_expiry = data.get('token_expiry') or 0
        # UI
        self._ui_theme = data.get('ui_theme') or 'light'
        self._ui_font_title = data.get('ui_font_title') or 'Lato'
        self._ui_font_body = data.get('ui_font_body') or 'Open Sans'

        settings = data.get('settings', {})
        if settings:
            if 'title_font' in settings:
                self._ui_font_title = settings['title_font']
            if 'body_font' in settings:
                self._ui_font_body = settings['body_font']
            if 'theme' in settings:
                self._ui_theme = settings['theme']

    def __repr__(self):
        return '<User username={0.username!r} display_name={0.display_name!r}>'.format(self)

    def serialize(self) -> typing.Dict[str, typing.AnyStr]:
        return {
            'username': self.username,
            'password': self._pw_hash,  # I can't believe people still fail to properly store passwords
            'display_name': self._display_name,
            'flags': self.flags,
            'timezone': self._timezone.zone,
            'token_revision': self.token_revision,
            'ui_theme': self._ui_theme,
            'ui_font_title': self._ui_font_title,
            'ui_font_body': self._ui_font_body,
        }

    def to_json(self) -> dict:
        """Returns a JSON-compatible dictionary."""
        data = self.serialize()
        del data['password']  # even though it's hashed, let's not leak it
        del data['token_revision']  # not really interesting to the user or developers
        return data

    def commit(self) -> pymongo.results.UpdateResult:
        res = self.db.users.replace_one({'_id': self.id}, self.serialize())
        assert res.matched_count == 1
        return res

    def check_pw(self, password: str):
        try:
            self.db.argon2.verify(self._pw_hash, password)
            return True
        except argon2.exceptions.VerificationError:
            return False

    @property
    def username(self):
        return self._username

    @username.setter
    def username(self, value: typing.Optional[str]):
        if not value or not value.strip() or value.strip() == self.username:
            return  # our work here is done

        value = value.strip().lower()

        for char in value:
            if char not in 'abcdefghijklmnopqrstuvwxyz0123456789-_.':
                raise AssertionError('Unable to set username: Illegal characters.')
        old_username = self.username
        try:
            self._username = value
            self.commit()
        except pymongo.errors.DuplicateKeyError:
            self._username = old_username
            raise AssertionError('Unable to set username: Username is taken.')

    @property
    def display_name(self):
        return self._display_name

    @display_name.setter
    def display_name(self, value):
        if not value or not value.strip():
            return
        self._display_name = value.strip()

    @property
    def password(self):
        return self._pw_hash

    @password.setter
    def password(self, value):
        if not value or not value.strip():
            return

        password = self.db.argon2.hash(value)
        del value  # get that thing out of memory ASAP
        self._pw_hash = password
        self.invalidate_tokens()
        self.commit()

    @property
    def timezone(self):
        return self._timezone

    @timezone.setter
    def timezone(self, value):
        if not value:
            return
        if value not in pytz.all_timezones:
            raise AssertionError('Invalid timezone given.')
        self._timezone = pytz.timezone(value)

    @property
    def token_revision(self) -> int:  # not making a setter for this, making one would be a Bad Idea(tm)
        return self._token_revision

    def invalidate_tokens(self):
        self._token_revision += 1  # state-keeping the best we can
        self.commit()

    @property
    def token_expiry(self) -> typing.Optional[datetime.timedelta]:
        if not self._token_expiry:
            return
        return datetime.timedelta(seconds=self._token_expiry)

    @token_expiry.setter
    def token_expiry(self, value: int):
        if not value:
            return
        if value < 0:
            raise AssertionError('Cannot set a negative value for expiry.')
        self._token_expiry = value
        self.invalidate_tokens()  # this commits for us

    def create_token(self) -> str:
        additional = {}
        if self.token_expiry:
            additional['exp'] = datetime.datetime.now(tz=pytz.UTC) + self.token_expiry
        return self.db.jwt.encode(uid=self.id, rev=self.token_revision, **additional)

    def entries(self, tag=None):
        if tag:
            cursor = self.db.entries.find({'author_id': self.id, 'tags': tag.lower()})
        else:
            cursor = self.db.entries.find({'author_id': self.id})

        cursor = cursor.sort('timestamp', pymongo.DESCENDING)

        for raw_entry in cursor:
            yield Entry(self.db, **raw_entry)

    @property
    def ui_theme(self):
        return self._ui_theme

    @ui_theme.setter
    def ui_theme(self, value: str):
        if not value:
            return
        if value not in ['light', 'dark']:
            raise AttributeError('Invalid theme set.')
        self._ui_theme = value

    @staticmethod
    def _validate_font(value):
        for c in value:
            if c.lower() not in 'abcdefghijklmnopqrstuvwxyz ':
                raise AssertionError('Invalid font given.')

    @property
    def ui_font_title(self):
        return self._ui_font_title

    @ui_font_title.setter
    def ui_font_title(self, value):
        if not value or not value.strip():  # sacrificing speed for readability, oh well
            return
        value = value.strip()
        self._validate_font(value)
        self._ui_font_title = value

    @property
    def ui_font_body(self):
        return self._ui_font_body

    @ui_font_body.setter
    def ui_font_body(self, value):
        if not value or not value.strip():  # sacrificing speed for readability, oh well
            return
        value = value.strip()
        self._validate_font(value)
        self._ui_font_body = value

    def delete(self):
        self.db.users.delete_one({'_id': self.id})
        self.db.entries.delete_many({'author_id': self.id})
