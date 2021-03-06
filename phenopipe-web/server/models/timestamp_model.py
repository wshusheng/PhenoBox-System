from sqlalchemy import Index, Column
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from server.extensions import db
from server.models import BaseModel


class TimestampModel(BaseModel):
    __tablename__ = 'timestamp'

    #:Primary key of the Model
    id = db.Column(db.Integer, primary_key=True)
    #:The IAP ID of the corresponding File Import in IAP
    iap_exp_id = db.Column(db.String, unique=True)
    #: Indicates whether this timestamp is completed and a new one should created for future snapshots
    completed = db.Column(db.Boolean, server_default='f', default=False, nullable=False)
    #:Foreign key to the Experiment
    experiment_id = db.Column(db.Integer, db.ForeignKey('experiment.id'), nullable=False)
    #:SQLAlchemy relationship to the experiment
    experiment = db.relationship("ExperimentModel", back_populates="timestamps", single_parent=True)
    #:SQLAlchemy relationship to all corresponding snapshots
    snapshots = db.relationship("SnapshotModel", order_by="SnapshotModel.created_at", back_populates="timestamp",
                                cascade="all, delete-orphan")
    #:SQLAlchemy relationship to all corresponding analyses
    analyses = db.relationship("AnalysisModel", order_by="AnalysisModel.created_at", back_populates="timestamp",
                               cascade="all, delete-orphan")
    __table_args__ = (
        Index('idx_unique_open_timestamp', 'experiment_id', 'completed', unique=True,
              postgresql_where=Column('completed') == False),)

    @staticmethod
    def get_or_create(experiment_id, session=None):
        if session is None:
            session = db.session
        try:
            return session.query(TimestampModel).filter(
                TimestampModel.completed.is_(False),
                TimestampModel.experiment_id == experiment_id
            ).one(), False
        except NoResultFound:
            entry = TimestampModel(experiment_id)
            try:
                session.add(entry)
                session.flush()
                return entry, True
            except IntegrityError:
                session.rollback()
                return session.query(TimestampModel).filter(
                    TimestampModel.completed.is_(False),
                    TimestampModel.experiment_id == experiment_id
                ).one(), False

    def __init__(self, experiment_id):
        self.experiment_id = experiment_id

    def __repr__(self):
        return '<Timestamp of experiment %r>' % self.experiment_id
