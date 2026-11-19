from fastapi import APIRouter
from fastapi import Depends, HTTPException, Response

from src.database import get_session
from src.dependencies import get_current_user, Pagination
from src.models import UsersOrm, ContactsRequestsStatus
from src.queries.orm import ContactsRepository, UsersRepository, ContactsRequestsRepository
from src.schemas import ContactRequestResult, PublicUser, ContactRequestRead, ContactRead, ContactUpdate, \
    ContactRequestCreate
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/contacts", tags=["contacts"])

@router.post("/requests", response_model=ContactRequestResult)
async def invite_to_contacts(payload: ContactRequestCreate,
                             current_user: UsersOrm = Depends(get_current_user),
                             session: AsyncSession = Depends(get_session)):

    target_user = await UsersRepository.get_by_public_id(session, payload.public_id)
    if target_user is None or target_user.is_active == False:
        return ContactRequestResult()

    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="cannot invite yourself")

    if await ContactsRepository.exist_in_contacts(session, current_user.id, target_user.id):
        raise HTTPException(status_code=409, detail="Already in contacts")

    already_sent = await ContactsRequestsRepository.get_pending(session, current_user.id, target_user.id)
    if already_sent is not None:
        return ContactRequestResult()

    incoming = await ContactsRequestsRepository.get_pending(session, target_user.id, current_user.id)
    if incoming is not None:
        await ContactsRequestsRepository.accept_invite(session, incoming)
        return ContactRequestResult()

    if await ContactsRequestsRepository.declined_recently(session, current_user.id, target_user.id):
        return ContactRequestResult()

    await ContactsRequestsRepository.create_request(session, current_user.id, target_user.id)
    return ContactRequestResult()


@router.get("/requests", response_model=list[ContactRequestRead])
async def get_request_list(session: AsyncSession = Depends(get_session),
                           current_user: UsersOrm = Depends(get_current_user)):
    rows = await ContactsRequestsRepository.request_list(session, current_user.id)
    return [
        ContactRequestRead(
            id=req.id,
            created_at=req.created_at,
            from_user=PublicUser.model_validate(u)
        )
        for req, u in rows
    ]


@router.post("/requests/{request_id}/accept", response_model=ContactRequestRead)
async def accept_contact_request(request_id: int,
                      session: AsyncSession = Depends(get_session),
                      current_user: UsersOrm = Depends(get_current_user),):
    req = await ContactsRequestsRepository.get(session, request_id)
    if req is None or req.to_id != current_user.id:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != ContactsRequestsStatus.pending:
        raise HTTPException(status_code=409, detail="Request already processed")

    sender = await UsersRepository.get(session, req.from_id)
    result = ContactRequestRead(id=req.id, created_at=req.created_at,
                                from_user=PublicUser.model_validate(sender))

    await ContactsRequestsRepository.accept_invite(session, req)
    return result


@router.post("/requests/{request_id}/decline", response_model=ContactRequestRead)
async def decline_contact_request(request_id: int,
                      session: AsyncSession = Depends(get_session),
                      current_user: UsersOrm = Depends(get_current_user),):
    req = await ContactsRequestsRepository.get(session, request_id)
    if req is None or req.to_id != current_user.id:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != ContactsRequestsStatus.pending:
        raise HTTPException(status_code=409, detail="Request already processed")

    sender = await UsersRepository.get(session, req.from_id)
    result = ContactRequestRead(id=req.id, created_at=req.created_at,
                                from_user=PublicUser.model_validate(sender))

    await ContactsRequestsRepository.decline_request(session, req)
    return result


@router.delete("/requests/{public_id}", status_code=204)
async def delete_contact_request(public_id: str,
                                 current_user: UsersOrm = Depends(get_current_user),
                                 session: AsyncSession = Depends(get_session)):
    target = await UsersRepository.get_by_public_id(session, public_id)
    if target is None or not target.is_active:
        return

    pending = await ContactsRequestsRepository.get_pending(session, current_user.id, target.id)
    if pending is not None:
        await ContactsRequestsRepository.cancel_request(session, pending)


@router.get("", response_model=list[ContactRead])
async def list_contacts(response: Response,
                        session: AsyncSession = Depends(get_session),
                        current_user: UsersOrm = Depends(get_current_user),
                        page: Pagination = Depends()):
    rows, total = await ContactsRepository.get_contact_list(session, current_user.id, page.limit, page.offset)
    response.headers["X-Total-Count"] = str(total)
    return [ContactRead(user=PublicUser.model_validate(u), alias=c.alias) for c, u in rows]


@router.patch("/{public_id}", response_model=ContactRead)
async def contact_alias(public_id: str,
                        payload: ContactUpdate,
                        session: AsyncSession = Depends(get_session),
                        current_user: UsersOrm = Depends(get_current_user),
                        ):
    target = await UsersRepository.get_by_public_id(session, public_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    contact = await ContactsRepository.get_contact(session, current_user.id, target.id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    card = PublicUser.model_validate(target)
    contact = await ContactsRepository.update(session, contact, payload.model_dump(exclude_unset=True))
    return ContactRead(user=card, alias=contact.alias)


@router.delete("/{public_id}", status_code=204)
async def delete_contact(public_id: str,
                         session: AsyncSession = Depends(get_session),
                         current_user: UsersOrm = Depends(get_current_user)):
    target = await UsersRepository.get_by_public_id(session, public_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    deleted = await ContactsRepository.contact_delete(session, current_user.id, target.id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Contact not found")


@router.get("/{public_id}", response_model=ContactRead)
async def get_contact_profile(public_id: str,
                              session: AsyncSession = Depends(get_session),
                              current_user: UsersOrm = Depends(get_current_user)):

    target = await UsersRepository.get_by_public_id(session, public_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    contact = await ContactsRepository.get_contact(session, current_user.id, target.id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    return ContactRead(user=PublicUser.model_validate(target), alias=contact.alias)