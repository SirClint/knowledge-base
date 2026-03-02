from fastapi import APIRouter, Depends, Query
from db.database import get_session
from search.service import search_keyword, search_semantic
from auth.users import current_active_user

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def search(
    q: str = Query(..., min_length=1),
    mode: str = Query("keyword", pattern="^(keyword|semantic|both)$"),
    session=Depends(get_session),
    user=Depends(current_active_user),
):
    if mode == "keyword":
        return await search_keyword(q, session)
    elif mode == "semantic":
        return await search_semantic(q)
    else:
        kw = await search_keyword(q, session)
        sem = await search_semantic(q)
        seen = {r["path"] for r in kw}
        combined = kw + [r for r in sem if r["path"] not in seen]
        return combined
