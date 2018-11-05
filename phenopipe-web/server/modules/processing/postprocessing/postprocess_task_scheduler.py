from threading import RLock

from graphql_relay import to_global_id

from server.extensions import db
from server.models import PostprocessModel, SnapshotModel, AnalysisModel
from server.modules.processing.exceptions import AlreadyFinishedError
from server.modules.processing.postprocessing.postprocessing_jobs import invoke_r_postprocess
from server.modules.processing.postprocessing.postprocessing_task import PostprocessingTask
from server.modules.processing.task_scheduler import TaskScheduler


class PostprocessTaskScheduler(TaskScheduler):
    _lock = RLock()
    _timeout = 43200  # 12h

    def __init__(self, connection, namespace, rq_queue):
        """
        Initializes the Task Scheduler with a redis connection and the according namespace which it will use for its keys
        inside Redis.
        :param connection: The redis connection which is used by the Scheduler
        :param namespace: The top level key which will be used inside redis
        """
        super(PostprocessTaskScheduler, self).__init__(connection, namespace, rq_queue)

    def fetch_all_tasks(self, username):
        tasks = []
        keys = self.fetch_all_task_keys(username)
        for key in keys:
            tasks.append(PostprocessingTask.from_key(self._connection, key))
        return tasks

    def _evict_task(self, key):
        """
        Deletes the task with the given key from redis
        :param key: The unique key of the task which should be deleted
        :return: None
        """
        task = PostprocessingTask.from_key(self._connection, key)
        task.delete()

    def submit_task(self, task, depends_on=None):
        """
       Creates a Background Job for running a specific postprocessing stack on an analysis result and enqueues it.

       The Job will only be enqueued if there is no corresponding entry in the 'postprocess' table

       :return: A Tuple containing the created :class:`~server.modules.postprocessing.postprocessing_task.PostprocessingTask` and the :class:`~server.models.analysis_model.PostprocessModel` instance
       """

        if not task.instanceof(PostprocessingTask):
            raise TypeError('"task" parameter has to be of type "PostprocessingTask')
        task.rq_queue_name = self._rq_queue.name
        task.save()
        snapshots = db.session.query(SnapshotModel).filter(SnapshotModel.id.in_(task.snapshot_ids)).all()
        postprocess, created = PostprocessModel.get_or_create(task.analysis_id, task.postprocessing_stack_id,
                                                              task.control_group_id, snapshots, task.note)
        analysis = db.session.query(AnalysisModel).get(task.analysis_id)
        if created:
            db.session.commit()

            task.message("Postprocessing Task Enqueued")

            self._register_task(task.username, task.key)

            all_snapshots = db.session.query(SnapshotModel) \
                .filter(SnapshotModel.timestamp_id == analysis.timestamp.id) \
                .all()
            # TODO embed building of difference into query
            snap_set = set(snapshots)
            excluded_snapshots = [snap for snap in all_snapshots if snap not in snap_set]
            excluded_plants = [snapshot.plant.full_name for snapshot in excluded_snapshots]

            description = 'Run postprocessing stack({}) on the results of analysis ({})'.format(
                task.postprocessing_stack_name,
                to_global_id('Analysis', analysis.id))

            job = self._rq_queue.enqueue_call(invoke_r_postprocess,
                                              (analysis.timestmp.experiment.name, postprocess.id, analysis.id,
                                               excluded_plants,
                                               analysis.export_path,
                                               task.postprocessing_stack_id, task.postprocessing_stack_name,
                                               task.username, task.key),
                                              result_ttl=-1,
                                              ttl=-1,
                                              description=description,
                                              meta={'name': 'postprocessing_job', 'task_key': task.key},
                                              depends_on=depends_on
                                              )
            task.processing_job = job
            task.save()
            return task, postprocess

        else:
            if postprocess.finished_at is None:
                return PostprocessingTask.from_key(self._connection,
                                                   PostprocessingTask.key_for(analysis.id,
                                                                              task.postprocessing_stack_id)), postprocess
            else:
                raise AlreadyFinishedError('Postprocess', postprocess.id,
                                           'The requested postprocessing stack has already been processed')
