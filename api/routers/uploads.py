from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ai_wasteguard import permissions, uploads as uploads_service
from api.deps import get_current_user, get_db, require_owned_sample
from api.schemas import UploadResponse

router = APIRouter(prefix="/api/v1", tags=["uploads"])


def _to_response(upload) -> UploadResponse:
    return UploadResponse(
        id=upload.id,
        sample_id=upload.sample_id,
        original_filename=upload.original_filename,
        file_type=upload.file_type,
        omics_type=upload.omics_type,
        size_bytes=upload.size_bytes,
        checksum_sha256=upload.checksum_sha256,
        validation_status=upload.validation_status.value,
        created_at=upload.created_at,
    )


@router.get("/samples/{sample_id}/uploads", response_model=list[UploadResponse])
def list_uploads(sample_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_owned_sample(db, sample_id, current_user)
    return [_to_response(u) for u in uploads_service.list_uploads_for_sample(db, sample_id)]


@router.post(
    "/samples/{sample_id}/uploads", response_model=UploadResponse, status_code=status.HTTP_201_CREATED
)
def create_upload(
    sample_id: str,
    file: UploadFile = File(...),
    omics_type: str | None = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owned_sample(db, sample_id, current_user)
    if current_user.role not in permissions.CAN_UPLOAD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{current_user.role.value}' is not permitted to upload files.",
        )
    try:
        upload = uploads_service.save_upload(
            db,
            sample_id=sample_id,
            uploader_id=current_user.id,
            original_filename=file.filename,
            file_obj=file.file,
            omics_type=omics_type,
        )
    except uploads_service.UploadValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _to_response(upload)
