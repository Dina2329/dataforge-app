from pydantic import BaseModel


class GroupCleanupRequest(BaseModel):
    group_field: str
    value_field: str
    score_field: str


class GroupCleanupPreviewResponse(BaseModel):
    group_field: str
    value_field: str
    score_field: str
    qualifying_groups: int
    rows_to_delete: int
    sample_group_values: list[str]


class GroupCleanupResultResponse(BaseModel):
    groups_deleted: int
    rows_deleted: int
