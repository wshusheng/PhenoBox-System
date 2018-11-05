from collections import OrderedDict

from rq.job import Job, JobStatus

from server.modules.processing.task import Task
from server.modules.processing.task_state import TaskState
from server.utils.util import as_string


class AnalysisTask(Task):
    PREFIX = b'ana_tasks'

    def __init__(self, connection, timestamp_id, pipeline_id, username='',
                 name='', description='', pipeline_name='', input_path='',
                 output_path='',
                 import_job=None,
                 analysis_job=None, export_job=None, rq_queue_name='analysis'):
        jobs = OrderedDict([('import_job', import_job),
                            ('analysis_job', analysis_job),
                            ('export_job', export_job)])
        super(AnalysisTask, self).__init__(connection, jobs, username, rq_queue_name, name, description)

        self._timestamp_id = timestamp_id
        self._pipeline_id = pipeline_id
        self._pipeline_name = pipeline_name
        self._input_path = input_path
        self._output_path = output_path

    @classmethod
    def key_for(cls, timestamp_id, pipeline_id):
        """The Redis key that is used to store task hash under."""
        return AnalysisTask.PREFIX + ':' + str(timestamp_id) + ':' + str(pipeline_id)

    # TODO move to parent?
    @classmethod
    def fetch(cls, connection, *ids):
        """Fetches a persisted task from its corresponding Redis key and
        instantiates it.
        """
        # todo rename to task
        task = cls(connection, ids[0], ids[1])
        task.load()
        return task

    @property
    def key(self):
        """The Redis key that is used to store task hash under."""
        return self.key_for(self.timestamp_id, self.pipeline_id)

    @property
    def pipeline_name(self):
        return self._pipeline_name

    @pipeline_name.setter
    def pipeline_name(self, value):
        self._pipeline_name = value

    @property
    def input_path(self):
        return self._input_path

    @input_path.setter
    def input_path(self, value):
        self._input_path = value

    @property
    def output_path(self):
        return self._output_path

    @output_path.setter
    def output_path(self, value):
        self._output_path = value

    def to_dict(self):
        """
        Returns a serialization of the current Task instance

        """
        obj = super(AnalysisTask, self).to_dict()
        obj['input_path'] = self.input_path
        obj['output_path'] = self.output_path
        if self.import_job is not None:
            obj['import_job'] = self.import_job.id
        if self.analysis_job is not None:
            obj['analysis_job'] = self.analysis_job.id
        if self.export_job is not None:
            obj['export_job'] = self.export_job.id
        return obj

    def load(self):
        obj = super(AnalysisTask, self).load()
        self.input_path = as_string(obj.get('input_path', None))
        self.output_path = as_string(obj.get('output_path', None))
        import_job_id = as_string(obj.get('import_job', None))
        analysis_job_id = as_string(obj.get('analysis_job', None))
        export_job_id = as_string(obj.get('export_job', None))
        self.import_job = self._queue.fetch_job(import_job_id)
        self.analysis_job = self._queue.fetch_job(analysis_job_id)
        self.export_job = self._queue.fetch_job(export_job_id)

    @property
    def state(self):
        if self.import_job is not None:
            first_state = self.import_job.get_status()
        else:
            first_state = self.analysis_job.get_status()

        if first_state == JobStatus.DEFERRED:
            return TaskState.CREATED
        if first_state == JobStatus.QUEUED:
            return TaskState.QUEUED
        if first_state == JobStatus.STARTED:
            return TaskState.RUNNING
        if first_state == JobStatus.FAILED:
            return TaskState.FAILED
        # first job finished
        if self.analysis_job.status == JobStatus.FINISHED and self.export_job.status == JobStatus.FINISHED:
            return TaskState.FINISHED
        elif self.analysis_job.get_status() == JobStatus.FAILED or self.export_job.status == JobStatus.FAILED:
            return TaskState.FAILED

        return TaskState.RUNNING

    @property
    def timestamp_id(self):
        return self._timestamp_id

    @property
    def pipeline_id(self):
        return self._pipeline_id

    @property
    def import_job(self):
        return self._jobs.get('import_job')

    @import_job.setter
    def import_job(self, value):
        if value is None or isinstance(value, Job):
            self._jobs['import_job'] = value
        else:
            raise TypeError('Argument has to be of type "rq.Job".')

    @property
    def analysis_job(self):
        return self._jobs.get('analysis_job')

    @analysis_job.setter
    def analysis_job(self, value):
        if value is None or isinstance(value, Job):
            self._jobs['analysis_job'] = value
        else:
            raise TypeError('Argument has to be of type "rq.Job".')

    @property
    def export_job(self):
        return self._jobs.get('export_job')

    @export_job.setter
    def export_job(self, value):
        if value is None or isinstance(value, Job):
            self._jobs['export_job'] = value
        else:
            raise TypeError('Argument has to be of type "rq.Job".')
