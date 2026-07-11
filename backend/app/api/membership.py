"""
Membership-status & product-listing endpoints.

- GET /membership/status   – current user's membership info
- GET /membership/products – available products to purchase
"""

from fastapi import APIRouter, Depends

from app.models.user import User
from app.services.payment import PRODUCTS
from app.utils.auth import get_current_user

router = APIRouter(prefix="/membership", tags=["会员"])


@router.get("/status")
async def membership_status(user: User = Depends(get_current_user)):
    """Return the current user's membership details."""
    return {
        "is_member": user.is_member,
        "expires_at": user.member_expires_at,
        "free_readings_today": user.free_readings_today,
        "free_chats_today": user.free_chats_today,
    }


@router.get("/products")
async def list_products():
    """List all purchasable products."""
    return [
        {"id": k, "name": v["name"], "price": v["price"]}
        for k, v in PRODUCTS.items()
    ]
