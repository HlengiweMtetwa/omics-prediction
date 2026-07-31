from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ai_wasteguard import reports as reports_service
from ai_wasteguard.models import Report
from api.deps import get_current_user, get_db, require_owned_project
from api.schemas import ReportResponse

router = APIRouter(prefix="/api/v1", tags=["reports"])


def _to_response(report: Report) -> ReportResponse:
    return ReportResponse(
        id=report.id,
        project_id=report.project_id,
        report_type=report.report_type,
        content_hash=report.content_hash,
        created_at=report.created_at,
    )


def _require_owned_report(db: Session, report_id: str, current_user) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    require_owned_project(db, report.project_id, current_user)
    return report


@router.get("/projects/{project_id}/reports", response_model=list[ReportResponse])
def list_reports(project_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_owned_project(db, project_id, current_user)
    return [_to_response(r) for r in reports_service.list_reports_for_project(db, project_id)]


@router.post("/projects/{project_id}/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_report(project_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_owned_project(db, project_id, current_user)
    report = reports_service.generate_project_summary_report(db, project_id, current_user.id)
    return _to_response(report)


@router.get("/reports/{report_id}/content", response_class=HTMLResponse)
def get_report_content(report_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    report = _require_owned_report(db, report_id, current_user)
    return Path(report.file_path).read_text()
