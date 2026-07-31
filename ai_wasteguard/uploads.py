"""File upload handling: format validation, checksumming, safe storage.

Storage keys are generated server-side (never derived from the client's
filename) specifically to prevent path traversal - the original filename is
kept only as a display label.
"""
import hashlib
import os
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from ai_wasteguard.config import BASE_DIR
from ai_wasteguard.models import UploadedFile, UploadValidationStatus

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", BASE_DIR / "instance" / "uploads"))

# category -> allowed suffixes (checked longest-first so multi-part
# suffixes like .fastq.gz are matched before .gz would be).
_ALLOWED_SUFFIXES: dict[str, str] = {
    ".csv": "tabular",
    ".tsv": "tabular",
    ".txt": "tabular",
    ".xlsx": "tabular",
    ".xls": "tabular",
    ".json": "tabular",
    ".biom": "tabular",
    ".parquet": "tabular",
    ".fasta": "sequence",
    ".fa": "sequence",
    ".fasta.gz": "sequence",
    ".fa.gz": "sequence",
    ".fastq": "sequence",
    ".fq": "sequence",
    ".fastq.gz": "sequence",
    ".fq.gz": "sequence",
    ".fna": "sequence",
    ".faa": "sequence",
    ".gff": "sequence",
    ".gff3": "sequence",
    ".bam": "sequence",
    ".sam": "sequence",
    ".vcf": "sequence",
    ".bcf": "sequence",
}
_SORTED_SUFFIXES = sorted(_ALLOWED_SUFFIXES, key=len, reverse=True)
SUPPORTED_EXTENSIONS = sorted(_ALLOWED_SUFFIXES)

CHUNK_SIZE = 1024 * 1024  # 1 MiB


class UploadValidationError(Exception):
    pass


def detect_file_type(filename: str) -> tuple[str, str]:
    """Returns (matched_suffix, category). Raises UploadValidationError for
    unsupported or missing extensions."""
    lowered = filename.lower()
    for suffix in _SORTED_SUFFIXES:
        if lowered.endswith(suffix):
            return suffix, _ALLOWED_SUFFIXES[suffix]
    raise UploadValidationError(
        f"Unsupported file type for '{filename}'. Allowed extensions: "
        f"{', '.join(sorted(_ALLOWED_SUFFIXES))}"
    )


def save_upload(
    session: Session,
    sample_id: str,
    uploader_id: str,
    original_filename: str,
    file_obj: BinaryIO,
    omics_type: str | None = None,
) -> UploadedFile:
    """Streams file_obj to disk in chunks (never loading the whole file into
    memory at once), computing a SHA-256 checksum as it goes, then records
    the upload against the given sample."""
    suffix, category = detect_file_type(original_filename)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    storage_key = f"{uuid.uuid4()}{suffix}"
    destination = UPLOAD_DIR / storage_key

    hasher = hashlib.sha256()
    size_bytes = 0
    with open(destination, "wb") as out:
        while True:
            chunk = file_obj.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
            size_bytes += len(chunk)
            out.write(chunk)

    upload = UploadedFile(
        sample_id=sample_id,
        uploader_id=uploader_id,
        original_filename=os.path.basename(original_filename.replace("\\", "/")),
        storage_key=storage_key,
        file_type=category,
        omics_type=omics_type or None,
        size_bytes=size_bytes,
        checksum_sha256=hasher.hexdigest(),
        validation_status=UploadValidationStatus.VALID,
    )
    session.add(upload)
    session.flush()
    return upload


def list_uploads_for_sample(session: Session, sample_id: str) -> list[UploadedFile]:
    from sqlalchemy import select

    return list(
        session.execute(
            select(UploadedFile)
            .where(UploadedFile.sample_id == sample_id)
            .order_by(UploadedFile.created_at.desc())
        ).scalars()
    )
