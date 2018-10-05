# noinspection PyPackageRequirements
import argon2
import jwt
import pymongo
import pymongo.errors
import pytz
import typing
from bson.codec_options import CodecOptions

from journal.db.dataclasses import User, Entry
from journal.db.util import IDGenerator, JWTEncoder


class DatabaseInterface:
    def __init__(self, mongo_uri, db_name, worker_id, signing_key):
        # noinspection PyArgumentList
        options = CodecOptions(tz_aware=True, tzinfo=pytz.UTC)
        self.db = pymongo.MongoClient(mongo_uri).get_database(db_name, codec_options=options)

        self.users = self.db.get_collection('users')
        self.users.create_index([('username', pymongo.ASCENDING)], unique=True)

        self.entries = self.db.get_collection('entries')
        self.entries.create_index([('author_id', pymongo.ASCENDING)])
        self.entries.create_index([('timestamp', pymongo.DESCENDING)])

        self.argon2 = argon2.PasswordHasher()
        self.id_gen = IDGenerator(int(worker_id))
        self.jwt = JWTEncoder(signing_key)

    def create_user(self, username: str, password: str) -> typing.Optional[User]:
        _id = self.id_gen.generate()
        self.users.insert_one({'_id': _id})

        new = self.get_user(id=_id)
        new.password = password
        del password  # *shudder*
        try:
            new.username = username
        except AssertionError as e:
            new.delete()
            raise e

        return new

    # noinspection PyShadowingBuiltins
    def get_user(self, *, id=None, username=None, email=None, token=None) -> typing.Optional[User]:
        data = None

        if username:
            data = self.users.find_one({'username': username.lower()})
        if email:
            data = self.users.find_one({'email': email})
        if id:
            data = self.users.find_one({'_id': id})
        if token:  # ! special case
            try:
                token_data = self.jwt.decode(token)
            except jwt.InvalidTokenError:
                return
            for f in ['uid', 'rev']:
                if f not in token_data:
                    return
            user = self.get_user(id=token_data['uid'])
            if not user:  # might happen, user could've deleted their account
                return
            if user.token_revision != token_data['rev']:
                return
            return user

        if not data:
            return

        # migration
        if 'tokens' in data:
            self.users.update_one({'_id': data['_id']}, {'$unset': {'tokens': None}})

        return User(self, **data)

    def create_entry(self, user: User) -> Entry:
        return Entry(self, timezone=user.timezone.zone, author_id=user.id).new()

    def get_entry(self, _id) -> typing.Optional[Entry]:
        entry = self.entries.find_one({'_id': _id})
        if entry is None:
            return
        return Entry(self, **entry)
