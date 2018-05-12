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
        self._title = data.get('title', 'Untitled entry')
        self._content = data.get('content', '')
        self.tags = data.get('tags', [])

    def _update(self, **fields) -> pymongo.results.UpdateResult:
        return self.db.users.update_one({'_id': self.id}, {'$set': fields})

    @property
    def author_id(self):
        return self._author_id

    @author_id.setter
    def author_id(self, value):
        self._author_id = value
        assert self._update(author_id=self.author_id)

    @property
    def author(self):
        return self.db.get_user(id=self._author_id)

    @author.setter
    def author(self, value: 'User'):
        self.author_id = value.id

    @property
    def title(self):
        return self._title

    @property

    @property
    def timestamp_human(self):
        return self._timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')

    @title.setter
    def title(self, value):
        self._title = value.strip()
        assert self._update(title=self._title).matched_count == 1

    @property
    def content(self):
        return self._content

    @content.setter
    def content(self, value):
        self._content = value.strip()
        assert self._update(content=self._content).matched_count == 1

    def new(self):
        """Initializes the database record if necessary."""
        try:
            self.db.entries.insert_one({
                '_id': self.id, 'timestamp': self._timestamp, 'timezone': str(self._timestamp.tzinfo),
            })
            return True
        except pymongo.errors.DuplicateKeyError:
            return False

    def delete(self):
        """Clears the database record"""
        res = self.db.entries.delete_one({'_id': self.id})
        return res.deleted_count == 1

    def __repr__(self):
        return '<Entry id={0.id!r} author_id={0.author_id!r} title={0.title!r}>'.format(self)
