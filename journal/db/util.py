import time

import datetime
import jwt
import pytz
from threading import RLock

EPOCH = datetime.datetime(2018, 1, 1, tzinfo=pytz.UTC).timestamp()


def id_to_time(_id):
    return datetime.datetime.fromtimestamp((_id >> 22) / 1000 + EPOCH, pytz.UTC)


class IDGenerator:
    def __init__(self, worker_id=0):
        self._worker_id = None
        self._last_gen_ms = 0
        self._last_gen_c = 0
        self._lock = RLock()

        self.counter = 0
        self.worker_id = worker_id

    @property
    def worker_id(self) -> int:
        return self._worker_id

    @worker_id.setter
    def worker_id(self, _id):
        if not 0 <= _id < 1024:
            raise ValueError('Worker ID must be between 0 and 1023 (inclusive).')
        self._worker_id = _id

    def generate(self):
        self._lock.acquire()

        now_ms = int((time.time() - EPOCH) * 1000)
        if self._last_gen_ms < now_ms:
            self._last_gen_ms = now_ms
            self._last_gen_c = self.counter
        elif self._last_gen_ms > now_ms:
            raise RuntimeError('Time ran backwards!')

        next_iteration = (self.counter + 1) % 4096
        if now_ms == self._last_gen_ms and next_iteration == self._last_gen_c:
            raise RuntimeError('4095 IDs generated in one millisecond?!')

        self.counter = next_iteration

        self._lock.release()

        # 64 - 22: time
        # 22 - 12: worker ID
        # 12 - 0: counter

        return now_ms << 22 | self.worker_id << 10 | self.counter


class JWTEncoder:
    def __init__(self, signing_key):
        self.key = signing_key

    def encode(self, **data) -> str:
        if 'iat' not in data:
            data['iat'] = datetime.datetime.now(tz=pytz.UTC)
        return jwt.encode(data, self.key, 'HS256').decode()

    def decode(self, data: str, **kwargs) -> dict:
        return jwt.decode(data, self.key, algorithms=['HS256'], **kwargs)
