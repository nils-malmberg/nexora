from app.worker import scheduler


def test_main_starts_metrics_server_schedules_job_and_runs_once_immediately(monkeypatch):
    started_ports = []
    monkeypatch.setattr(scheduler, "start_http_server", lambda port: started_ports.append(port))

    immediate_calls = []
    monkeypatch.setattr(scheduler, "run_all_enabled_providers", lambda: immediate_calls.append(1))

    added_jobs = []

    class FakeScheduler:
        def add_job(self, func, trigger, **kwargs):
            added_jobs.append((func, trigger, kwargs))

        def start(self):
            pass

    monkeypatch.setattr(scheduler, "BlockingScheduler", FakeScheduler)

    scheduler.main()

    assert started_ports == [scheduler.settings.worker_metrics_port]
    assert len(added_jobs) == 1
    # No explicit next_run_time: passing one (e.g. None) leaves the job
    # permanently unscheduled in APScheduler - verified empirically - so the
    # trigger must compute it, and jitter must be the configured bound, not
    # a value we pre-randomize ourselves.
    assert "next_run_time" not in added_jobs[0][2]
    assert added_jobs[0][2]["jitter"] == scheduler.settings.ingestion_jitter_seconds
    assert immediate_calls == [1]  # runs once at startup, not only after a full interval
