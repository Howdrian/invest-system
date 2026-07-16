import re


def test_resolve_analysis_run_date_prefers_valid_env(monkeypatch):
    from src.core.run_context import compact_run_date, report_filename_for_date, resolve_analysis_run_date

    monkeypatch.setenv("ANALYSIS_RUN_DATE", "2099-01-02")

    assert resolve_analysis_run_date() == "2099-01-02"
    assert compact_run_date() == "20990102"
    assert report_filename_for_date() == "report_20990102.md"


def test_resolve_analysis_run_date_warns_and_falls_back_on_invalid_env(monkeypatch, caplog):
    from src.core.run_context import resolve_analysis_run_date

    monkeypatch.setenv("ANALYSIS_RUN_DATE", "bad-date")

    run_date = resolve_analysis_run_date()

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", run_date)
    assert "Invalid ANALYSIS_RUN_DATE" in caplog.text


def test_notification_default_report_filename_uses_analysis_run_date(tmp_path, monkeypatch):
    import src.notification as notification

    notifier = notification.NotificationService.__new__(notification.NotificationService)
    fake_module_file = tmp_path / "src" / "notification.py"
    fake_module_file.parent.mkdir()
    fake_module_file.write_text("# test", encoding="utf-8")
    monkeypatch.setattr(notification, "__file__", str(fake_module_file))
    monkeypatch.setenv("ANALYSIS_RUN_DATE", "2099-01-02")

    saved = notifier.save_report_to_file("# report")

    assert saved == str(tmp_path / "reports" / "report_20990102.md")
    assert (tmp_path / "reports" / "report_20990102.md").read_text(encoding="utf-8") == "# report"
