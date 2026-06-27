from filezall_core.log_service import TransferLogService


def test_transfer_log_service_appends_and_exports_entries(tmp_path) -> None:
    service = TransferLogService()

    service.append("Connected to Production")
    service.append("Uploaded app.txt")
    output = tmp_path / "filezall.log"
    service.export(output)

    assert [entry.message for entry in service.entries()] == [
        "Connected to Production",
        "Uploaded app.txt",
    ]
    exported = output.read_text(encoding="utf-8")
    assert "UTC+00:00 [transfer] [info] Connected to Production" in exported
    assert "Connected to Production" in exported
    assert "Uploaded app.txt" in exported


def test_log_service_records_categories(tmp_path) -> None:
    service = TransferLogService()

    service.append_connection("Connected to Production")
    service.append_transfer("Uploaded app.txt")
    service.append_agent("Agent install: health check passed")
    service.append_resource("Resource snapshot refreshed")
    service.append_error("Connection failed")
    output = tmp_path / "filezall.log"
    service.export(output)

    records = service.records()
    assert [record.category for record in records] == [
        "connection",
        "transfer",
        "agent",
        "resource",
        "error",
    ]
    assert [record.level for record in records] == [
        "info",
        "info",
        "info",
        "info",
        "error",
    ]

    exported = output.read_text(encoding="utf-8")
    assert "[connection] [info] Connected to Production" in exported
    assert "[error] [error] Connection failed" in exported
