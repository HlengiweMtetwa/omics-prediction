import hashlib
import io
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_wasteguard import auth, registry, uploads
from ai_wasteguard.db import Base
from ai_wasteguard.models import UploadValidationStatus


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        yield s


@pytest.fixture()
def sample_and_uploader(session, tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_DIR", tmp_path / "uploads")
    owner = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.flush()
    project = registry.create_project(session, owner.id, "Pilot")
    session.flush()
    site = registry.create_site(session, project.id, "Site A")
    session.flush()
    event = registry.create_sampling_event(session, site.id, datetime.now(timezone.utc))
    session.flush()
    sample = registry.create_sample(session, event.id)
    session.flush()
    return sample, owner


def test_detect_file_type_accepts_known_extensions():
    assert uploads.detect_file_type("reads.fastq.gz") == (".fastq.gz", "sequence")
    assert uploads.detect_file_type("counts.csv") == (".csv", "tabular")


def test_detect_file_type_rejects_unknown_extension():
    with pytest.raises(uploads.UploadValidationError):
        uploads.detect_file_type("malware.exe")


def test_save_upload_records_correct_checksum_and_size(session, sample_and_uploader):
    sample, owner = sample_and_uploader
    content = b"sample_id,value\n1,42\n"
    upload = uploads.save_upload(
        session, sample.id, owner.id, "counts.csv", io.BytesIO(content), omics_type="genomic"
    )
    session.commit()

    assert upload.size_bytes == len(content)
    assert upload.checksum_sha256 == hashlib.sha256(content).hexdigest()
    assert upload.validation_status == UploadValidationStatus.VALID
    assert upload.original_filename == "counts.csv"

    stored_path = uploads.UPLOAD_DIR / upload.storage_key
    assert stored_path.exists()
    assert stored_path.read_bytes() == content


def test_storage_key_ignores_path_traversal_in_filename(session, sample_and_uploader):
    """The storage key must never be derived from attacker-controlled input."""
    sample, owner = sample_and_uploader
    upload = uploads.save_upload(
        session, sample.id, owner.id, "../../etc/passwd.csv", io.BytesIO(b"data"), None
    )
    session.commit()

    assert "/" not in upload.storage_key
    assert ".." not in upload.storage_key
    assert upload.original_filename == "passwd.csv"
    stored_path = uploads.UPLOAD_DIR / upload.storage_key
    assert stored_path.resolve().parent == uploads.UPLOAD_DIR.resolve()


def test_save_upload_rejects_unsupported_extension(session, sample_and_uploader):
    sample, owner = sample_and_uploader
    with pytest.raises(uploads.UploadValidationError):
        uploads.save_upload(session, sample.id, owner.id, "script.exe", io.BytesIO(b"data"), None)


def test_list_uploads_for_sample(session, sample_and_uploader):
    sample, owner = sample_and_uploader
    uploads.save_upload(session, sample.id, owner.id, "a.csv", io.BytesIO(b"a"), None)
    uploads.save_upload(session, sample.id, owner.id, "b.fastq.gz", io.BytesIO(b"b"), "metagenomic")
    session.commit()

    files = uploads.list_uploads_for_sample(session, sample.id)
    assert {f.original_filename for f in files} == {"a.csv", "b.fastq.gz"}
