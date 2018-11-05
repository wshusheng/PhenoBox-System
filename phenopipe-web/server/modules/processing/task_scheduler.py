import calendar
import datetime
from abc import ABCMeta, abstractmethod

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from server.modules.processing.redis_log_store import LogStore


class TaskScheduler:
    __metaclass__ = ABCMeta
    IDENTIFIER_SET_NAME = 'identifiers'

    def __init__(self, connection, namespace, rq_queue, ttl=20160, eviction_interval=30):
        """
        Initializes the Task Scheduler with a redis connection and the according namespace which it will use for its keys
        inside Redis.
        :param connection: The redis connection which is used by the Scheduler
        :param namespace: The top level key which will be used inside redis
        """
        self._connection = connection
        self._namespace = namespace
        self._rq_queue = rq_queue
        self._log_store = LogStore(connection)
        self._ttl = ttl
        if eviction_interval != -1:
            self._eviction_scheduler = BackgroundScheduler()
            self._eviction_scheduler.add_job(self._evict, trigger=IntervalTrigger(minutes=eviction_interval))
            self._eviction_scheduler.start()

    def _get_identifier_set_key(self):
        return '{}:{}'.format(self._namespace, TaskScheduler.IDENTIFIER_SET_NAME)

    def _get_tracking_set_key(self, identifier):
        return '{}:{}'.format(self._namespace, identifier)

    def _get_task_hash_key(self, id_1, *args):
        parts = [self._namespace, str(id_1)].extend([str(arg) for arg in args])
        return ':'.join(parts)

    def _register_task(self, identifier, task_key, ttl=-1):
        if ttl == -1:
            ttl = self._ttl
        current_time = calendar.timegm(datetime.datetime.utcnow().utctimetuple())
        self._connection.zadd(self._get_tracking_set_key(identifier), current_time + ttl, task_key)
        self._connection.sadd(self._get_identifier_set_key(), identifier)

    def fetch_all_task_keys(self, username):
        return self._connection.smembers(self._get_tracking_set_key(username))

    @abstractmethod
    def fetch_all_tasks(self, username):
        pass

    @abstractmethod
    def submit_task(self, task):
        pass

    @abstractmethod
    def _evict_task(self, key):
        """
        Deletes the task with the given key from redis
        :param key: The unique key of the task which should be deleted
        :return: None
        """
        pass

    def _evict(self):
        """
        Gets tasks which have been stored for longer than ttl and removes them from the database
        :return: None
        """
        identifiers = self._connection.sscan_iter(self._get_identifier_set_key())
        score = calendar.timegm(datetime.datetime.utcnow().utctimetuple())
        for identifier in identifiers:
            expired = self._connection.zrangebyscore(self._get_tracking_set_key(identifier), 0, score)
            for task_key in expired:
                self._evict_task(task_key)
            self._connection.zremrangebyscore(self._get_tracking_set_key(identifier), 0, score)
            if not self._connection.exists(self._get_tracking_set_key(identifier)):
                self._connection.srem(self._get_identifier_set_key(), identifier)
