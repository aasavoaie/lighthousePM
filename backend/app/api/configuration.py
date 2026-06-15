from fastapi import APIRouter, HTTPException

from app.schemas.configuration import JiraConfigurationResponse, JiraConfigurationUpdate
from app.services.configuration_service import get_jira_configuration, update_jira_configuration

router = APIRouter(prefix="/config", tags=["configuration"])


@router.get("/jira", response_model=JiraConfigurationResponse)
def read_jira_configuration() -> JiraConfigurationResponse:
    return get_jira_configuration()


@router.put("/jira", response_model=JiraConfigurationResponse)
def write_jira_configuration(update: JiraConfigurationUpdate) -> JiraConfigurationResponse:
    try:
        return update_jira_configuration(update)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
