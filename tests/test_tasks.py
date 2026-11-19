async def test_user_sees_own_and_project_tasks(client, create_project, create_user, _get_auth_headers, create_task):
    user_mail = "tasks_user@test.com"
    proj_name = "own_project_from_user1"
    task_name = "own_task_from_user1"
    st, stop = 1, 10

    await create_user(user_mail)
    u_headers = await _get_auth_headers(user_mail)

    await create_task(headers=u_headers, title=task_name)

    resp = await client.get("/tasks", headers=u_headers)
    assert resp.status_code == 200
    assert task_name in [t["title"] for t in resp.json()]

    project = await create_project(headers=u_headers, name=proj_name)
    project_id = project["id"]

    for i in range(st, stop):
        await create_task(headers=u_headers, title=f"{task_name}_{i}", project_id=project_id)

    resp = await client.get(f"/projects/{project_id}", headers=u_headers)
    assert resp.status_code == 200

    resp = await client.get("/tasks", params={"project_id": project_id}, headers=u_headers)
    #   resp = await client.get(f"/tasks?project_id={project_id}", headers=u_headers)   # same
    assert resp.status_code == 200
    titles = {t["title"] for t in resp.json()}
    assert titles == {f"{task_name}_{i}" for i in range(st, stop)}


async def test_cannot_read_others_tasks(client, create_user, _get_auth_headers, create_task):
    user_owner = "user_owner@test.com"
    user_other = "user_other@test.com"

    await create_user(user_owner)
    await create_user(user_other)

    owner_headers = await _get_auth_headers(user_owner)
    other_headers = await _get_auth_headers(user_other)

    resp_owner_task = await create_task(headers=owner_headers, title="My OWN TASK!")
    task_id = resp_owner_task["id"]

    resp = await client.get("/tasks", headers=owner_headers)
    assert resp.status_code == 200
    assert task_id in {t["id"] for t in resp.json()}

    resp = await client.get("/tasks", headers=other_headers)
    assert resp.status_code == 200
    assert task_id not in {t["id"] for t in resp.json()}

    resp = await client.patch(f"/tasks/{task_id}", json={"title": "Hacked"}, headers=other_headers)
    assert resp.status_code == 404
    resp = await client.delete(f"/tasks/{task_id}", headers=other_headers)
    assert resp.status_code == 404
























