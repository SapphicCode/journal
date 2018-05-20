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
        self.id = data.get('_id')
        self._username = data.get('username', '')
        self._pw_hash = data.get('password', b'')
        display_backup = self._username.replace('-', ' ').replace('_', ' ').replace('.', ' ').title()
        self._display_name = data.get('display_name', display_backup)
        self.tokens = data.get('tokens', [])
        self.flags = data.get('flags', [])
        self._timezone = pytz.timezone(data.get('timezone', 'UTC'))
        self._token_revision = data.get('token_revision', 0)
        self._token_expiry = data.get('token_expiry')
        self.settings = data.get('settings', {})

    def __repr__(self):
        return '<User username={0.username!r} display_name={0.display_name!r}>'.format(self)

    def check_pw(self, password: str):
        try:
            self.db.argon2.verify(self._pw_hash, password)
            return True
        except argon2.exceptions.VerificationError:
            return False

    def _update(self, **fields) -> pymongo.results.UpdateResult:
        res = self.db.users.update_one({'_id': self.id}, {'$set': fields})
        assert res.matched_count == 1
        return res

    def _increment(self, **fields):
        res = self.db.users.update_one({'_id': self.id}, {'$inc': fields})
        assert res.modified_count == 1  # we're assuming it actually was incremented
        return res

    @property
    def username(self):
        return self._username

    @username.setter
    def username(self, value):
        value = value.strip().lower()
        assert value, 'Unable to set username: Username is empty.'
        for char in value:
            if char not in 'abcdefghijklmnopqrstuvwxyz0123456789-_.':
                raise AssertionError('Unable to set username: Illegal characters.')
        try:
            self._update(username=value)
            self._username = value
        except pymongo.errors.DuplicateKeyError:
            raise AssertionError('Unable to set username: Username is taken.')

    @property
    def display_name(self):
        return self._display_name

    @display_name.setter
    def display_name(self, value):
        self._display_name = value
        self._update(display_name=self._display_name)

    @property
    def password(self):
        return self._pw_hash

    @password.setter
    def password(self, value):
        password = self.db.argon2.hash(value)
        del value  # get that thing out of memory ASAP
        self._pw_hash = password
        self._update(password=password)
        self.invalidate_tokens()

    @property
    def timezone(self):
        return self._timezone

    @timezone.setter
    def timezone(self, value):
        self._timezone = value
        self._update(timezone=value.zone)

    @property
    def token_revision(self) -> int:
        return self._token_revision

    def invalidate_tokens(self):
        self._token_revision += 1  # state-keeping the best we can
        self._increment(token_revision=1)

    @property
    def token_expiry(self) -> typing.Optional[datetime.timedelta]:
        if not self._token_expiry:
            return
        return datetime.timedelta(seconds=self._token_expiry)

    @token_expiry.setter
    def token_expiry(self, value: typing.Optional[datetime.timedelta]):
        if value is not None:
            value = int(value.total_seconds())
            value = value if value != 0 else None
        self._token_expiry = value
        self._update(token_expiry=value)
        self.invalidate_tokens()

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

    def save_setings(self):
        self._update(settings=self.settings)

    def save_flags(self):
        self._update(flags=self.flags)

    def delete(self):
        self.db.users.delete_one({'_id': self.id})
        self.db.entries.delete_many({'author_id': self.id})
