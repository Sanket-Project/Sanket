"""Real TLS SMTP delivery to a synthetic loopback sink, never external recipients."""

import ipaddress
import socket
import ssl
import threading
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.services.notifications.email import EmailConfig, send_email


def start_sink(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_path, key_path)
    client_context = ssl.create_default_context(cafile=str(cert_path))
    captured, errors = [], []
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(10)
    port = listener.getsockname()[1]

    def serve():
        try:
            conn, _ = listener.accept()
            conn.settimeout(5)
            conn.sendall(b"220 synthetic sink\r\n")
            stream = conn.makefile("rb")
            while line := stream.readline():
                command = line.upper()
                if command.startswith(b"EHLO"):
                    conn.sendall(b"250-localhost\r\n250 STARTTLS\r\n")
                elif command.startswith(b"STARTTLS"):
                    conn.sendall(b"220 Ready\r\n")
                    stream.close()
                    conn = server_context.wrap_socket(conn, server_side=True)
                    stream = conn.makefile("rb")
                elif command.startswith((b"MAIL FROM", b"RCPT TO")):
                    conn.sendall(b"250 OK\r\n")
                elif command.startswith(b"DATA"):
                    conn.sendall(b"354 Send data\r\n")
                    chunks = []
                    while (body_line := stream.readline()) != b".\r\n":
                        if not body_line:
                            break
                        chunks.append(body_line)
                    captured.append(b"".join(chunks))
                    conn.sendall(b"250 Accepted\r\n")
                elif command.startswith(b"QUIT"):
                    conn.sendall(b"221 Bye\r\n")
                    break
            stream.close()
            conn.close()
        except Exception as exc:
            errors.append(type(exc).__name__)
        finally:
            listener.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return (
        EmailConfig(host="127.0.0.1", port=port, sender="sanket@example.test"),
        client_context,
        captured,
        errors,
        thread,
    )


def test_actual_local_tls_sink_accepts_message(tmp_path):
    config, client_context, captured, errors, thread = start_sink(tmp_path)
    with patch("ssl.create_default_context", return_value=client_context):
        state = send_email(
            config,
            "synthetic@example.test",
            "Weekly planning summary",
            "Accepted recommendations: 7. /workspace/decisions",
        )
    thread.join(timeout=5)
    assert not errors
    assert state == "sent"
    assert len(captured) == 1
    assert b"Accepted recommendations: 7." in captured[0]
    assert b"/workspace/decisions" in captured[0]


async def test_weekly_coordinator_delivers_real_facts_through_tls_and_replay_does_not_resend(
    tmp_path, db_session, make_tenant, app_role_db
):
    import uuid
    from email import policy
    from email.parser import BytesParser
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from sqlalchemy import text

    from app.models.enums import IndustryCode
    from app.services.llm.contracts import AIResult
    from app.services.llm.facts import NarrativeBlock, NarrativeOutput
    from app.services.llm.policy import AIContext, PolicyStore
    from app.services.notifications.communications import write_preferences
    from app.services.notifications.preferences import Preferences
    from app.services.notifications.weekly import run_weekly_summary

    tenant, uid = await make_tenant(), uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO users(id,tenant_id,email,full_name,role,is_active) VALUES(:uid,:tid,'synthetic@example.test','Synthetic TLS recipient','owner',true)"
        ),
        {"uid": uid, "tid": tenant},
    )
    await db_session.commit()
    await write_preferences(app_role_db, tenant, uid, Preferences(weekly_enabled=True))
    await PolicyStore(app_role_db).configure(
        AIContext(tenant, uid, IndustryCode.fashion, task_name="weekly_summary"),
        enabled=True,
        tasks={"weekly_summary": True},
        sharing="headers_only",
        aggregate_context=True,
        product_names=False,
    )

    async def select_facts(ctx, task):
        facts = {fact.id: fact for fact in task.input.facts}
        assert facts["recommendations_accepted"].value == "0"
        assert facts["realized_savings"].value is None
        return AIResult(
            state="success",
            value=NarrativeOutput(
                blocks=[
                    NarrativeBlock(proposition="fact", fact_ids=["recommendations_accepted"]),
                    NarrativeBlock(proposition="missing", fact_ids=["realized_savings"]),
                ]
            ),
        )

    ai = SimpleNamespace(run=AsyncMock(side_effect=select_facts))
    config, client_context, captured, errors, thread = start_sink(tmp_path)
    due = datetime(2026, 11, 2, 2, 30, tzinfo=UTC)
    now = due.isoformat()
    with (
        patch("app.services.notifications.weekly.EmailConfig.from_settings", return_value=config),
        patch("ssl.create_default_context", return_value=client_context),
    ):
        result = await run_weekly_summary(
            {"db": app_role_db, "ai": ai, "clock": lambda: due},
            str(tenant),
            str(uid),
            "fashion",
            now,
        )
        replay = await run_weekly_summary(
            {"db": app_role_db, "ai": ai, "clock": lambda: due},
            str(tenant),
            str(uid),
            "fashion",
            now,
        )
    thread.join(timeout=5)
    assert not errors
    assert result["state"] == "sent"
    assert replay["state"] == "sent"
    assert replay["replayed"] is True
    assert len(captured) == 1
    message = BytesParser(policy=policy.default).parsebytes(captured[0])
    assert message["To"] == "synthetic@example.test"
    assert message["Subject"] == "Weekly planning summary"
    body = message.get_body(preferencelist=("plain",)).get_content()
    assert "Accepted recommendations: 0" in body
    assert "Data unavailable: Realised savings" in body
    assert "/workspace/decisions" in body
    async with app_role_db.session(str(tenant)) as session:
        assert (
            await session.scalar(
                text(
                    "SELECT state FROM communication_deliveries WHERE tenant_id=:tid AND user_id=:uid"
                ),
                {"tid": tenant, "uid": uid},
            )
            == "sent"
        )
