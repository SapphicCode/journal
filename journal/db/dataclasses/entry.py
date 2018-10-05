import pymongo.results
import pytz
import typing
from autoslot import Slots

from journal.db.util import id_to_time

if typing.TYPE_CHECKING:
    from journal.db import DatabaseInterface, User


class Entry(Slots):
    def __init__(self, db: 'DatabaseInterface' = None, **data):
        self.db = db
        self.id = data.get('_id') or self.db.id_gen.generate()
        self.timestamp = data.get('timestamp', id_to_time(self.id)).astimezone(
            pytz.timezone(data.get('timezone', 'UTC'))
        )
        self._author_id = data.get('author_id')
        self._title = data.get('title') or 'Untitled entry'
        self._content = data.get('content') or ''
        self._tags = data.get('tags') or []

    def serialize(self) -> typing.Dict[str, typing.Any]:
        """Returns a MongoDB-friendly dictionary for a replace() call."""
        return {
            '_id': self.id,
            'author_id': self._author_id,
            'title': self._title,
            'content': self._content,
            'tags': self._tags,
            'timestamp': self.timestamp,
            'timezone': (self.timestamp.tzinfo or pytz.UTC).zone,
        }

    def commit(self) -> pymongo.results.UpdateResult:
        res = self.db.entries.replace_one({'_id': self.id}, self.serialize())
        assert res.matched_count == 1
        return res

    @property
    def author_id(self) -> typing.Optional[int]:
        return self._author_id

    @property
    def author(self):
        return self.db.get_user(id=self._author_id)

    @author.setter
    def author(self, value: 'User'):
        # noinspection PyAttributeOutsideInit
        self._author_id = value.id

    @property
    def title(self):
        return self._title

    @property
    def timestamp_human(self):
        return self.timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')  # TODO: per-user formatting options?

    @title.setter
    def title(self, value):
        if value:
            self._title = value.strip()

    @property
    def content(self):
        return self._content

    @content.setter
    def content(self, value):
        if value:
            self._content = value.strip()

    @property
    def tags(self):
        return self._tags

    @tags.setter
    def tags(self, value: typing.List[str]):
        # we transform from list -> set -> list to remove duplicates
        self._tags = list(set(sorted(x.strip().lower() for x in value if x.strip())))

    @property
    def tags_human(self):
        return ', '.join(self._tags)

    @tags_human.setter
    def tags_human(self, tag_string: str):
        # IDEA likes to complain when we call our own properties
        # noinspection PyAttributeOutsideInit
        self.tags = tag_string.split(',')

    def new(self) -> 'Entry':
        """Initializes the database record."""
        self.db.entries.insert_one(self.serialize())
        return self

    def delete(self):
        """Clears the database record"""
        res = self.db.entries.delete_one({'_id': self.id})
        assert res.deleted_count == 1

    def can_access(self, user: 'User') -> bool:
        """Returns whether a user has access to this entry or not."""
        return self.author_id == user.id  # TODO: sharing feature

    def can_edit(self, user: 'User') -> bool:
        """Returns whether a user has owner rights on this entry."""
        return self.author_id == user.id  # (this one can probably stay as-is)

    def __repr__(self):
        return '<Entry id={0.id!r} author_id={0.author_id!r} title={0.title!r}>'.format(self)
