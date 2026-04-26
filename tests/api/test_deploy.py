import asyncio

import pytest

pytestmark = pytest.mark.api

BASIC = ("admin", "testpass123")


async def test_deploy_redirects_and_records_job(client, ui_modules, initial_password, monkeypatch):
    deploy = ui_modules["deploy"]
    started = asyncio.Event()
    finish = asyncio.Event()

    async def fake_start(cfg, limit, local_entry):
        log = deploy.JobLog()
        log.kind = f"deploy ({limit})"
        deploy.jobs.current = log
        log.append("PLAY [all]\n")
        started.set()
        await finish.wait()
        log.append("ok=1\n")
        log.finish(0)
        deploy.jobs.last = log
        deploy.jobs.current = None
        return log

    monkeypatch.setattr(deploy, "start_deploy", fake_start)

    resp = await client.post(
        "/api/deploy", data={"limit": "all"}, auth=BASIC, follow_redirects=False
    )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/deploy"

    await started.wait()
    assert deploy.jobs.status()["state"] == "running"

    finish.set()
    for _ in range(50):
        await asyncio.sleep(0.01)
        if deploy.jobs.status()["state"] == "done":
            break
    assert deploy.jobs.status()["state"] == "done"
    assert deploy.jobs.status()["exit_code"] == 0


async def test_deploy_conflict_when_job_running(client, ui_modules, initial_password, monkeypatch):
    deploy = ui_modules["deploy"]
    log = deploy.JobLog()
    log.kind = "deploy (all)"
    deploy.jobs.current = log

    try:
        resp = await client.post(
            "/api/deploy", data={"limit": "all"}, auth=BASIC, follow_redirects=False
        )
        assert resp.status_code == 409
    finally:
        log.finish(0)
        deploy.jobs.last = log
        deploy.jobs.current = None


async def test_deploy_stream_emits_lines_and_done_event(
    client, ui_modules, initial_password
):
    deploy = ui_modules["deploy"]
    log = deploy.JobLog()
    log.kind = "deploy (all)"
    log.append("first line\n")
    log.append("second line\n")
    log.finish(0)
    deploy.jobs.last = log

    resp = await client.get("/api/deploy/stream", auth=BASIC)

    assert resp.status_code == 200
    body = resp.text
    assert "data: first line" in body
    assert "data: second line" in body
    assert "event: done" in body
    assert "data: 0" in body


async def test_deploy_stream_when_no_job(client, ui_modules, initial_password):
    deploy = ui_modules["deploy"]
    deploy.jobs.current = None
    deploy.jobs.last = None

    resp = await client.get("/api/deploy/stream", auth=BASIC)

    assert resp.status_code == 200
    assert "no job yet" in resp.text
