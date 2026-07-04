from sqlmodel import SQLModel, Session, create_engine

from app.models import User, Job, JobStatus


def make_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def test_transcribing_status_and_transcript_source_persist():
    engine = make_engine()
    with Session(engine) as session:
        user = User(email="a@example.com", hashed_password="x")
        session.add(user)
        session.commit()
        session.refresh(user)

        job = Job(user_id=user.id, youtube_url="https://youtube.com/watch?v=abc", interval_seconds=5)
        job.status = JobStatus.transcribing
        job.transcript_source = "whisper"
        session.add(job)
        session.commit()
        session.refresh(job)

        assert job.status == JobStatus.transcribing
        assert job.transcript_source == "whisper"
        assert JobStatus.transcribing.value == "transcribing"
