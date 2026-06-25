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
    assert "Connected to Production" in exported
    assert "Uploaded app.txt" in exported
