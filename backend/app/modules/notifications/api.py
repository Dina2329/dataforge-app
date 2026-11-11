import uuid

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.modules.notifications.schemas import NotificationListResponse, NotificationResponse
from app.modules.notifications.service import NotificationService

router = APIRouter(tags=["notifications"])


@router.get("/api/notifications", response_model=NotificationListResponse)
async def list_notifications(current_user: CurrentUser, db: DbSession) -> NotificationListResponse:
    notifications, unread_count = await NotificationService(db).list_for_user(user_id=current_user.id)
    return NotificationListResponse(
        notifications=[NotificationResponse.model_validate(n) for n in notifications], unread_count=unread_count
    )


@router.post("/api/notifications/{notification_id}/read", status_code=204)
async def mark_notification_read(notification_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await NotificationService(db).mark_read(notification_id=notification_id, user_id=current_user.id)


@router.post("/api/notifications/read-all", status_code=204)
async def mark_all_notifications_read(current_user: CurrentUser, db: DbSession) -> None:
    await NotificationService(db).mark_all_read(user_id=current_user.id)
