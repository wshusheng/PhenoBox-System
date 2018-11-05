from threading import RLock

from flask import current_app

from server.extensions import db
from server.models import AnalysisModel, TimestampModel
from server.modules.processing.analysis import invoke_iap_import, invoke_iap_analysis, invoke_iap_export
from server.modules.processing.analysis.analysis_task import AnalysisTask
from server.modules.processing.exceptions import AlreadyFinishedError
from server.modules.processing.task_scheduler import TaskScheduler


class AnalysisTaskScheduler(TaskScheduler):
    _lock = RLock()
    _timeout_import = 43200  # 12h
    _timeout_analysis = 86400  # 24h
    _timeout_export = 600  # 10min

    def __init__(self, connection, namespace, rq_queue):
        """
        Initializes the Task Scheduler with a redis connection and the according namespace which it will use for its keys
        inside Redis.
        :param connection: The redis connection which is used by the Scheduler
        :param namespace: The top level key which will be used inside redis
        """
        super(AnalysisTaskScheduler, self).__init__(connection, namespace, rq_queue)

    def _get_import_job_id_key(self, timestamp_id):
        return '{}:{}:import_job'.format(self._namespace, str(timestamp_id))

    def _get_import_job_id(self, timestamp_id):
        return self._connection.get(self._get_import_job_id_key(timestamp_id))

    def _evict_task(self, key):
        """
        Deletes the task with the given key from redis
        :param key: The unique key of the task which should be deleted
        :return: None
        """
        task = AnalysisTask.from_key(self._connection, key)
        task.delete()

    def fetch_all_tasks(self, username):
        tasks = []
        keys = self.fetch_all_task_keys(username)
        for key in keys:
            tasks.append(AnalysisTask.from_key(self._connection, key))
        return tasks

    def submit_task(self, task):
        """
        Creates and Enqueues the necessary background jobs to import, analyze and export the data of the given timestamp

        """
        if not task.instanceof(AnalysisTask):
            raise TypeError('"task" parameter has to be of type "AnalysisTask')
        task.rq_queue_name = self._rq_queue.name
        task.save()
        analysis, created = AnalysisModel.get_or_create(task.timestamp_id, task.pipeline_id)
        if created:
            db.session.commit()
            task.message = "Analysis Task enqueued"

            self._register_task(task.username, task.key)
            # Lock to ensure only one import job is executed for multiple pipelines
            self._lock.acquire()
            import_job = None
            timestamp = db.session.query(TimestampModel).get(task.timestamp_id)
            if timestamp.iap_exp_id is None:
                import_job_id = self._get_import_job_id(task.timestamp_id)
                if import_job_id is None:
                    experiment_name = timestamp.experiment.name
                    description = 'Import Image data of experiment "{}" at timestamp [{}] to IAP'.format(
                        experiment_name, timestamp.created_at.strftime("%a %b %d %H:%M:%S UTC %Y"))
                    import_job = self._rq_queue.enqueue_call(invoke_iap_import, (timestamp.id, experiment_name,
                                                                                 task.username,
                                                                                 task.username,
                                                                                 task.input_path, task.username,
                                                                                 task.key),
                                                             result_ttl=-1,
                                                             ttl=-1,
                                                             timeout=self._timeout_import,
                                                             description=description,
                                                             meta={'name': 'import_job', 'task_key': task.key}
                                                             )

                    self._connection.set(self._get_import_job_id_key(timestamp.id), str(import_job.id))
                else:
                    import_job = self._rq_queue.fetch_job(import_job_id)
            task.import_job = import_job
            self._lock.release()
            description = 'Analyse the data of timestamp [{}] with the pipeline "{}" in IAP'.format(
                timestamp.created_at.strftime("%a %b %d %H:%M:%S UTC %Y"), task.pipeline_name)
            analysis_job = self._rq_queue.enqueue_call(invoke_iap_analysis, (analysis.id, timestamp.id,
                                                                             task.username, task.key,
                                                                             timestamp.iap_exp_id),
                                                       result_ttl=-1,
                                                       ttl=-1,
                                                       timeout=self._timeout_analysis,
                                                       description=description,
                                                       meta={'name': 'analysis_job', 'task_key': task.key},
                                                       depends_on=import_job)

            task.analysis_job = analysis_job
            shared_folder_map = current_app.config['SHARED_FOLDER_MAP']
            description = 'Export the IAP results for timestamp [{}] for further use'.format(
                timestamp.created_at.strftime("%a %b %d %H:%M:%S UTC %Y"))
            export_job = self._rq_queue.enqueue_call(invoke_iap_export,
                                                     (timestamp.id, task.output_path, task.username,
                                                      shared_folder_map, task.key),
                                                     result_ttl=-1,
                                                     ttl=-1,
                                                     timeout=self._timeout_export,
                                                     description=description,
                                                     meta={'name': 'export_job', 'task_key': task.key},
                                                     depends_on=analysis_job)

            task.export_job = export_job
            task.save()
            return task, analysis
        else:
            if analysis.finished_at is None:
                return AnalysisTask.from_key(self._connection,
                                             AnalysisTask.key_for(analysis.timestamp_id,
                                                                  analysis.pipeline_id)), analysis
            else:
                raise AlreadyFinishedError(AnalysisModel, analysis.id,
                                           'The requested analysis has already been processed')
