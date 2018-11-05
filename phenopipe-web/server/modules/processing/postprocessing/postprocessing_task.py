import json
from collections import OrderedDict

from rq.job import Job, JobStatus

from server.modules.processing.task import Task
from server.modules.processing.task_state import TaskState
from server.utils.util import as_string


class PostprocessingTask(Task):
    PREFIX = b'post_tasks'

    # TODO Add snapshots
    def __init__(self, connection, analysis_id, postprocessing_stack_id, username='',
                 name='', description='', postprocessing_stack_name='',
                 control_group_id='',
                 snapshot_ids=list(),
                 note='',
                 processing_job=None,
                 rq_queue_name='postprocessing'):

        if snapshot_ids is None:
            snapshot_ids = []
        jobs = OrderedDict([('processing_job', processing_job)])
        super(PostprocessingTask, self).__init__(connection, jobs, username, rq_queue_name, name, description)

        self._analysis_id = analysis_id
        self._postprocessing_stack_id = postprocessing_stack_id
        self._postprocessing_stack_name = postprocessing_stack_name
        self._control_group_id = control_group_id
        self._snapshot_ids = snapshot_ids
        self._note = note

    @classmethod
    def key_for(cls, analysis_id, postprocessing_stack_id):
        """The Redis key that is used to store task hash under."""
        return PostprocessingTask.PREFIX + ':' + str(analysis_id) + ':' + str(postprocessing_stack_id)

    # TODO move to parent?
    @classmethod
    def fetch(cls, connection, *ids):
        """Fetches a persisted task from its corresponding Redis key and
        instantiates it.
        """
        task = cls(connection, ids[0], ids[1])
        task.load()
        return task

    @property
    def key(self):
        """The Redis key that is used to store task hash under."""
        return self.key_for(self.analysis_id, self.postprocessing_stack_id)

    @property
    def postprocessing_stack_id(self):
        return self._postprocessing_stack_id

    @postprocessing_stack_id.setter
    def postprocessing_stack_id(self, value):
        self._postprocessing_stack_id = value

    @property
    def postprocessing_stack_name(self):
        return self._postprocessing_stack_name

    @postprocessing_stack_name.setter
    def postprocessing_stack_name(self, value):
        self._postprocessing_stack_name = value

    @property
    def control_group_id(self):
        return self._control_group_id

    @control_group_id.setter
    def control_group_id(self, value):
        self._control_group_id = value

    @property
    def snapshot_ids(self):
        return self._snapshot_ids

    @snapshot_ids.setter
    def snapshot_ids(self, value):
        self._snapshot_ids = value

    @property
    def note(self):
        return self._note

    @note.setter
    def note(self, value):
        self._note = value

    def to_dict(self):
        """
        Returns a serialization of the current Task instance

        """
        obj = super(PostprocessingTask, self).to_dict()
        obj['postprocessing_stack_id'] = self.postprocessing_stack_id
        obj['postprocessing_stack_name'] = self.postprocessing_stack_name
        obj['control_group_id'] = self.control_group_id
        obj['snapshot_ids'] = json.dumps(self.snapshot_ids)
        if self.processing_job is not None:
            obj['processing_job'] = self.processing_job.id
        return obj

    def load(self):
        obj = super(PostprocessingTask, self).load()
        self.control_group_id = as_string(obj.get('control_group_id', None))
        self.postprocessing_stack_id = as_string(obj.get('postprocessing_stack_id', None))
        self.postprocessing_stack_name = as_string(obj.get('postprocessing_stack_name', None))
        self.snapshot_ids = json.loads(obj.get('snapshot_ids', []))
        processing_job_id = as_string(obj.get('processing_job', None))
        self.processing_job = self._queue.fetch_job(processing_job_id)

    @property
    def state(self):
        state = self.processing_job.get_status()
        if state == JobStatus.DEFERRED:
            return TaskState.CREATED
        if state == JobStatus.QUEUED:
            return TaskState.QUEUED
        if state == JobStatus.STARTED:
            return TaskState.RUNNING
        if state == JobStatus.FAILED:
            return TaskState.FAILED
        return TaskState.FINISHED

    @property
    def analysis_id(self):
        return self._analysis_id

    @property
    def postprocessing_stack_id(self):
        return self._postprocessing_stack_id

    @property
    def processing_job(self):
        return self._jobs.get('processing_job')

    @processing_job.setter
    def processing_job(self, value):
        if value is None or isinstance(value, Job):
            self._jobs['processing_job'] = value
        else:
            raise TypeError('Argument has to be of type "rq.Job".')
