#   async def test_register_duplicate_email_rejected(client):
#
#       resp = await client.post("/users", json={"email": "robin-bobin@test.com", "password": "secret123"})
#       assert resp.status_code == 200
#
#       resp = await client.post("/users", json={"email": "robin-bobin@test.com", "password": "secret1234"})
#       assert resp.status_code == 409
#
#
#   async def test_create_and_read_project(client, _get_auth_headers):
#       headers = await _get_auth_headers("owner@test.com")
#
#       resp = await client.post("/projects", json={"name": "Test project"}, headers=headers)
#       assert resp.status_code == 200
#       project_id = resp.json()["id"]
#
#       resp = await client.get(f"/projects/{project_id}", headers=headers)
#       assert resp.status_code == 200
#       assert resp.json()["name"] == "Test project"
#
#
#   async def test_cannot_read_others_projects(client, _get_auth_headers):
#       owner_headers = await _get_auth_headers("owner2@test.com")
#       resp = await client.post("/projects", json={"name": "Private"}, headers=owner_headers)
#       project_id = resp.json()["id"]
#
#       intruder_headers = await _get_auth_headers("intruder@test.com", _get_auth_headers)
#       resp = await client.get(f"/projects/{project_id}", headers=intruder_headers)
#       assert resp.status_code == 404
#