from abc import ABCMeta, abstractmethod, abstractproperty
from datetime import datetime

import dateutil.parser
from rq import Queue

from server.modules.processing.exceptions import InvalidJobIdError
from server.modules.processing.redis_log_store import LogStore
from server.utils.util import as_string


class Task:
    __metaclass__ = ABCMeta

    PREFIX = 'tasks'

    def __init__(self, connection, jobs, username='', rq_queue_name='', name='', description=''):
        self._connection = connection
        self._queue = Queue(rq_queue_name, connection=connection)
        self._name = name
        self._description = description
        self._jobs = jobs
        self._username = username
        self._created_at = datetime.utcnow()
        self._message = ''
        self._log_store = LogStore(connection)

    @classmethod
    def from_key(cls, connection, key):
        parts = key.split(':')
        task = cls.fetch(connection, *parts[1:])
        return task

    @classmethod
    @abstractmethod
    def key_for(cls, analysis_id, postprocessing_stack_id):
        """The Redis key that is used to store task hash under."""
        pass

    @classmethod
    @abstractmethod
    def fetch(cls, connection, *ids):
        """Fetches a persisted task from its corresponding Redis key and
        instantiates it.
        """
        pass

    @abstractproperty
    def key(self):
        pass

    @property
    def username(self):
        return self._username

    def log(self, job_id, message, progress=0):
        valid_id = False
        for job in self.jobs.values():
            if job.id == job_id:
                valid_id = True
                break
        if not valid_id:
            raise InvalidJobIdError(job_id,
                                    'The given Job ID "{}" is not associated with the Task under key "{}"'.format(
                                        job_id,
                                        self.key))
        self._log_store.put(job_id, message, progress)

    def to_dict(self):
        """
        Returns a serialization of the current Task instance

        """
        obj = {'queue_name': self._queue.name, 'created_at': self._created_at.isoformat(), 'name': self.name,
               'description': self.description, 'message': self.message, 'username': self.username}
        return obj

    def save(self):
        self._connection.hmset(self.key, self.to_dict())

    def load(self):
        key = self.key
        obj = self._connection.hgetall(key)
        if len(obj) == 0:
            raise ValueError('No such task: {0}'.format(key))

        def to_date(date_str):
            if date_str is None:
                return
            else:
                return dateutil.parser.parse(as_string(date_str))

        self._created_at = to_date(as_string(obj.get('created_at')))
        self.name = as_string(obj.get('name'))
        self.description = as_string(obj.get('description'))
        self.message = as_string(obj.get('message'))
        self._queue = Queue(as_string(obj.get('queue_name')), connection=self._connection)

        return obj

    def update_message(self, message):
        self._message = message
        # TODO Log message?
        self._connection.hset(self.key, 'message', message)

    def fetch_message(self):
        self.message = self._connection.hget(self.key, 'message')
        return self.message

    def delete(self):
        for job in self.jobs.values():
            self._log_store.delete_log(job.id)
            job.delete()
        self._connection.delete(self.key)

    def expire(self, ttl):
        self._connection.expire(self.key, ttl)
        for job in self.jobs.values():
            job.cleanup(ttl=ttl)
            self._log_store.expire(job.id, ttl)

    @abstractproperty
    def state(self):
        pass

    @property
    def jobs(self):
        return self._jobs

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def message(self):
        return self._message

    @message.setter
    def message(self, value):
        self.update_message(value)

    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, value):
        self._description = value

    @property
    def created_at(self):
        return self._created_at

    @property
    def rq_queue_name(self):
        return self._queue.name

    @rq_queue_name.setter
    def rq_queue_name(self, value):
        if value != '':
            self._queue = Queue(value, connection=self._connection)
