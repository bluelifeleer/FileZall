from filezall_core.redaction import redact_sensitive


def test_redact_sensitive_values() -> None:
    text = (
        "password=secret passphrase='key phrase' token=abc123 "
        "Authorization: Bearer live-token FILEZALL_AGENT_TOKEN=agent-secret "
        "ssh_key_path=C:\\Users\\HUAWEI\\.ssh\\id_rsa "
        "agent_token_ref=site-1:agent-token"
    )

    redacted = redact_sensitive(text)

    assert "secret" not in redacted
    assert "key phrase" not in redacted
    assert "abc123" not in redacted
    assert "live-token" not in redacted
    assert "agent-secret" not in redacted
    assert "id_rsa" not in redacted
    assert "site-1:agent-token" not in redacted
    assert "password=<redacted>" in redacted
    assert "Authorization: Bearer <redacted>" in redacted
    assert "ssh_key_path=<redacted>" in redacted
    assert "agent_token_ref=<redacted>" in redacted
