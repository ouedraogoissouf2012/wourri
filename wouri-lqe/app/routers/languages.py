from fastapi import APIRouter, Depends

from app.data.languages import known_languages
from app.routers.session import current_user

router = APIRouter(prefix="/languages")


@router.get("")
def list_languages(_: dict = Depends(current_user)):
    return {"languages": known_languages()}
