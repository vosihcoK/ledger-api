import pytest_asyncio

@pytest_asyncio.fixture
async def f_send_invite(client):
    async def _make(headers: dict, public_id: str):
        response = await client.post("/contacts/requests",
                                     json={"public_id": public_id}, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()
    return _make

@pytest_asyncio.fixture
async def f_get_list_contacts(client):
    async def _make(headers: dict):
        response = await client.get("/contacts", headers=headers)
        assert response.status_code == 200, response.text
        return response.json()
    return _make