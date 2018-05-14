import pymongo
import pymongo.errors
import pymongo.results
import pytz
from autoslot import Slots

from journal.db.util import id_to_time


class Entry(Slots):
    def __init__(self, db: 'DatabaseInterface' = None, **data):
        self.db = db
        self.id = data.get('_id')
        self._timestamp = data.get('timestamp', id_to_time(self.id)).astimezone(
            pytz.timezone(data.get('timezone', 'UTC'))
        )
        self._author_id = data.get('author_id')
        self._title = data.get('title', '')
        self._content = data.get('content', '')
        self._tags = data.get('tags', [])

    def _update(self, **fields) -> pymongo.results.UpdateResult:
        res = self.db.entries.update_one({'_id': self.id}, {'$set': fields})
        assert res.matched_count == 1
        return res

    @property
    def author_id(self):
        return self._author_id

    @author_id.setter
    def author_id(self, value):
        self._author_id = value
        self._update(author_id=self.author_id)

    @property
    def author(self):
        return self.db.get_user(id=self._author_id)

    @author.setter
    def author(self, value: 'User'):
        self.author_id = value.id

    @property
    def title(self):
        return self._title if self._title else 'Untitled entry'

    @property
    def timestamp_human(self):
        return self._timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')

    @title.setter
    def title(self, value):
        self._title = value.strip()
        self._update(title=self._title)

    @property
    def content(self):
        return self._content

    @content.setter
    def content(self, value):
        self._content = value.strip()
        self._update(content=self._content)

    @property
    def timestamp(self):
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value):
        self._timestamp = value
        self._update(timestamp=value, timezone=str(value.tzinfo or pytz.UTC))

    @property
    def tags(self):
        return self._tags

    @tags.setter
    def tags(self, value):
        cleaned = sorted(x.strip().lower() for x in value if x.strip())
        self._tags = cleaned
        self._update(tags=self._tags)

    @property
    def tags_human(self):
        return ', '.join(self._tags)

    def new(self):
        """Initializes the database record if necessary."""
        try:
            self.db.entries.insert_one({'_id': self.id})
            self.timestamp = self._timestamp
            return True
        except pymongo.errors.DuplicateKeyError:
            return False

    def delete(self):
        """Clears the database record"""
        res = self.db.entries.delete_one({'_id': self.id})
        assert res.deleted_count == 1

    def __repr__(self):
        return '<Entry id={0.id!r} author_id={0.author_id!r} title={0.title!r}>'.format(self)
