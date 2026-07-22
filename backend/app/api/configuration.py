from fastapi import APIRouter, HTTPException

from app.schemas.configuration import JiraConfigurationResponse, JiraConfigurationUpdate, JiraConnectionTestResponse
from app.schemas.errors import ApiErrorResponse
from app.services.configuration_service import get_jira_configuration, test_jira_connection, update_jira_configuration

router = APIRouter(prefix="/config", tags=["configuration"])


@router.get(
    "/jira",
    response_model=JiraConfigurationResponse,
    operation_id="read_jira_configuration",
    summary="Get Jira configuration",
)
def read_jira_configuration() -> JiraConfigurationResponse:
    return get_jira_configuration()


@router.put(
    "/jira",
    response_model=JiraConfigurationResponse,
    operation_id="write_jira_configuration",
    summary="Update Jira configuration",
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "The Jira configuration is invalid.",
        }
    },
)
def write_jira_configuration(update: JiraConfigurationUpdate) -> JiraConfigurationResponse:
    try:
        return update_jira_configuration(update)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/jira/test",
    response_model=JiraConnectionTestResponse,
    operation_id="test_jira_configuration",
    summary="Test Jira configuration",
    responses={
        400: {
            "model": ApiErrorResponse,
            "description": "The candidate Jira configuration is invalid.",
        }
    },
)
async def test_jira_configuration(update: JiraConfigurationUpdate | None = None) -> JiraConnectionTestResponse:
    try:
        return await test_jira_connection(update)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
