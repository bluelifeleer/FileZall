from filezall_core.transfer_settings import TransferSettings


def test_transfer_settings_defaults_balance_throughput_and_server_load() -> None:
    settings = TransferSettings()

    assert settings.max_concurrent == 4
    assert settings.max_concurrent_per_server == 2
    assert settings.bytes_per_second_limit is None
