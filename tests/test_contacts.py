from src.models import ContactsRequestsOrm, ContactsOrm
from tests.conftest import async_session_test
from sqlalchemy import select, or_, and_


async def test_accept_contact_set_alias_and_delete(client, users, f_send_invite, f_get_list_contacts):
    usr1, usr2 = users["user_1"], users["user_2"]

    invite = await f_send_invite(usr1["headers"], usr2["row"].public_id)

    async with async_session_test() as session:
        req_id = await session.scalar(select(ContactsRequestsOrm.id)
                                      .where(ContactsRequestsOrm.from_id == usr1["row"].id,
                                             ContactsRequestsOrm.to_id == usr2["row"].id)
                                      )
    assert req_id is not None, f"Contact request not found, api answer: {invite}"

    resp = await client.get("/contacts/requests", headers=usr2["headers"])
    assert resp.status_code == 200, "Request not found"

    resp = await client.post(f"/contacts/requests/{req_id}/accept", headers=usr2["headers"])
    assert resp.status_code == 200, "Contact accept error"

    alias = "Boss"

    public_id = usr2["row"].public_id
    resp = await client.patch(f"/contacts/{public_id}", json={"alias": alias}, headers=usr1["headers"])
    assert resp.status_code == 200, resp.text

    #   API check
    resp = await client.get(f"/contacts/{public_id}", headers=usr1["headers"])
    assert resp.status_code == 200, resp.text

    res = resp.json()
    assert alias == res["alias"]


    resp = await client.delete(f"/contacts/{public_id}", headers=usr1["headers"])
    assert resp.status_code == 204, resp.text

    #   API check
    contacts_u1 = await f_get_list_contacts(headers=usr1["headers"])
    contacts_u2 = await f_get_list_contacts(headers=usr2["headers"])

    assert usr1["row"].public_id not in [u["user"]["public_id"] for u in contacts_u2]
    assert usr2["row"].public_id not in [u["user"]["public_id"] for u in contacts_u1]


async def test_cannot_invite_self(client, users):
    resp = await client.post("/contacts/requests", json={"public_id": users["user_1"]["row"].public_id},
                             headers=users["user_1"]["headers"])
    assert resp.status_code == 400


async def test_ignore_invalid_pub_id_invite(client, users, f_send_invite):
    resp = await f_send_invite(users["user_1"]["headers"], "FEFEFEFE")  # 8 len
    assert resp["status"] == "sent"


async def test_counter_request_accept(client, users, f_send_invite, f_get_list_contacts):
    usr2, usr2h = users["user_2"]["row"], users["user_2"]["headers"]
    usr3, usr3h = users["user_3"]["row"], users["user_3"]["headers"]

    await f_send_invite(usr2h, usr3.public_id)
    await f_send_invite(usr3h, usr2.public_id)

    # Orm test
    async with async_session_test() as session:
        contact = await session.execute(select(ContactsOrm).where(
                                     or_(
                                         and_(ContactsOrm.owner_id == usr2.id, ContactsOrm.contact_id == usr3.id),
                                         and_(ContactsOrm.owner_id == usr3.id, ContactsOrm.contact_id == usr2.id)
                                        )
                                    )
                                )
        res = contact.scalars().all()

    assert len(res) == 2, "Orm contact add failed"

    #   API check
    contacts_u2 = await f_get_list_contacts(headers=usr2h)
    contacts_u3 = await f_get_list_contacts(headers=usr3h)

    assert len(contacts_u3) and usr2.public_id in [u["user"]["public_id"] for u in contacts_u3], "API contact add failed"
    assert len(contacts_u2) and usr3.public_id in [u["user"]["public_id"] for u in contacts_u2], "API contact add failed"

async def test_cannot_with_non_contact(client, users):
    # view
    usr1, usr5 = users["user_1"], users["user_5"]
    public_id = usr5["row"].public_id
    resp = await client.get(f"/contacts/{public_id}", headers=usr1["headers"])
    assert resp.status_code == 404, "Non contact profile view error"

    # alias
    resp = await client.patch(f"/contacts/{public_id}", json={"alias": "my_friend"}, headers=usr1["headers"])
    assert resp.status_code == 404, resp.text

    # delete
    resp = await client.delete(f"/contacts/{public_id}", headers=usr1["headers"])
    assert resp.status_code == 404, resp.text


async def test_delete_contact_request(client, users, f_send_invite):
    usr1, usr2 = users["user_1"], users["user_4"]
    await f_send_invite(usr1["headers"], usr2["row"].public_id)

    #   API check
    resp = await client.get("/contacts/requests", headers=usr2["headers"])
    assert resp.status_code == 200, resp.text
    assert usr1["row"].public_id in [u["from_user"]["public_id"] for u in resp.json()]

    public_id = usr2["row"].public_id
    resp = await client.delete(f"/contacts/requests/{public_id}", headers=usr1["headers"])
    assert resp.status_code == 204

    #   API check
    resp = await client.get("/contacts/requests", headers=usr2["headers"])
    assert resp.status_code == 200, resp.text
    assert usr1["row"].public_id not in [u["from_user"]["public_id"] for u in resp.json()]


async def test_decline_contact_request(client, users, f_send_invite):
    usr1, usr2 = users["user_2"], users["user_4"]
    await f_send_invite(usr1["headers"], usr2["row"].public_id)

    async with async_session_test() as session:
        req_id = await session.scalar(select(ContactsRequestsOrm.id)
                                      .where(ContactsRequestsOrm.from_id == usr1["row"].id,
                                             ContactsRequestsOrm.to_id == usr2["row"].id)
                                      )
    resp = await client.post(f"/contacts/requests/{1000}/decline", headers=usr2["headers"])
    assert resp.status_code == 404, resp.text

    resp = await client.post(f"/contacts/requests/{req_id}/decline", headers=usr2["headers"])
    assert resp.status_code == 200, resp.text

    resp = await client.post(f"/contacts/requests/{req_id}/decline", headers=usr2["headers"])
    assert resp.status_code == 409, resp.text

    #   API check
    resp = await client.get("/contacts/requests", headers=usr2["headers"])
    assert resp.status_code == 200, resp.text
    assert usr1["row"].public_id not in [u["from_user"]["public_id"] for u in resp.json()]

async def test_can_view_non_contact_proj_member(client, users, create_project):
    pass