# backend/tests/test_models.py
from sqlmodel import SQLModel, Session, create_engine

from app.models import User, Job, Frame, JobStatus


def make_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_job_requires_interval_or_timestamps_default_status_is_pending():
    engine = make_engine()
    with Session(engine) as session:
        user = User(email="a@example.com", hashed_password="x")
        session.add(user)
        session.commit()
        session.refresh(user)

        job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5)
        session.add(job)
        session.commit()
        session.refresh(job)

        assert job.status == JobStatus.pending
        assert job.frames_done == 0

        frame = Frame(job_id=job.id, timestamp_seconds=5.0, file_path="/data/1/1/frames/5.jpg")
        session.add(frame)
        session.commit()
        session.refresh(frame)

        assert frame.job_id == job.id
