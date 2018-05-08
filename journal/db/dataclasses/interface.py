# noinspection PyPackageRequirements
import argon2
import pymongo
import pymongo.errors
import random
import typing

from journal.db.dataclasses import User, Entry
from journal.db.util import IDGenerator

token_ranges = (
    (0x30, 0x39),  # digits
    (0x41, 0x5a),  # upper alpha
    (0x61, 0x7a),  # lower alpha
)
token_chars = []
[[token_chars.append(chr(x)) for x in range(y[0], y[1] + 1)] for y in token_ranges]
del token_ranges


class DatabaseInterface:
    def __init__(self, mongo_uri, db_name, worker_id):
        self.db = pymongo.MongoClient(mongo_uri).get_database(db_name)

        self.users = self.db.get_collection('users')
        self.users.create_index([('username', pymongo.ASCENDING)], unique=True)
        self.users.create_index([('tokens', pymongo.ASCENDING)])

        self.entries = self.db.get_collection('entries')
        self.entries.create_index([('author_id', pymongo.ASCENDING)])
        self.entries.create_index([('timestamp', pymongo.DESCENDING)])

        self.argon2 = argon2.PasswordHasher()
        self.id_gen = IDGenerator(int(worker_id))

    def create_user(self, username: str, password: str) -> typing.Optional[User]:
        new_struct = {
            '_id': self.id_gen.generate(),
        }

        try:
            self.users.insert_one(new_struct)
        except pymongo.errors.DuplicateKeyError:
            return

        new = self.get_user(id=new_struct['_id'])
        new.password = password
        del password  # *shudder*
        try:
            new.username = username
        except AssertionError as e:
            new.delete()
            raise e

        return self.get_user(username=username)

    # noinspection PyShadowingBuiltins
    def get_user(self, *, id=None, username=None, email=None, token=None) -> typing.Optional[User]:
        data = None

        if username:
            data = self.users.find_one({'username': username.lower()})
        if email:
            data = self.users.find_one({'email': email})
        if token:
            data = self.users.find_one({'tokens': token})
        if id:
            data = self.users.find_one({'_id': id})

        if not data:
            return

        return User(self, **data)

    def create_token(self, user: User) -> str:
        new_token = ''.join(random.choice(token_chars) for _ in range(128))
        res = self.users.update_one({'_id': user.id}, {'$push': {'tokens': new_token}})
        assert res.matched_count == 1, 'User given to create_token not found'
        return new_token

    def invalidate_tokens(self, user: User):
        user.tokens = []
        res = self.users.update_one({'_id': user.id}, {'$unset': {'tokens': 1}})
        assert res.matched_count == 1, 'User given to invalidate_tokens not found'

    def create_entry(self) -> Entry:
        e = Entry(self, _id=self.id_gen.generate())
        assert e.new(), 'Entry ID generated already exists in the database.'
        return e

    def get_entry(self, _id) -> typing.Optional[Entry]:
        entry = self.entries.find_one({'_id': _id})
        if entry is None:
            return
        return Entry(self, **entry)

    def get_entries_by(self, user_id: int, skip=0, limit=50) -> typing.Iterable[Entry]:
        return [
            Entry(self, **x)
            for x in
            self.entries.find({'author_id': user_id}).sort('timestamp', pymongo.DESCENDING).skip(skip).limit(limit)
        ]

    def update_entry(self, entry: Entry):
        self.entries.update_one(
            {'_id': entry.id},
            {'$set': {
                'author_id': entry.author_id,
                'timestamp': entry.at,
                'title': entry.title,
                'content': entry.content,
                'tags': entry.tags,
            }},
            upsert=True,
        )

    def delete_entry(self, entry: Entry):
        self.entries.delete_one({'_id': entry.id})
