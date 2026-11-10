# Shows `ventoux doctor`'s rule temporal.identities saying "each certificate in date" of a certificate whose validity starts next year.
"""Run: uv run python reviews/2026-11/probes/p3_doctor_certificate_not_yet_valid.py

`certificate_problems` (src/ventoux/tooling/doctor.py) compares only the certificate's end with
now. Past the supported names: `ventoux.tooling.doctor.identities_are_sound`, called as doctor
calls it, with a configuration read from a temporary pyproject.toml.
"""

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from ventoux.tooling.deployment import read
from ventoux.tooling.doctor import Context, identities_are_sound

with tempfile.TemporaryDirectory() as folder:
    project = Path(folder)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "operator")])
    starts = datetime.now(UTC) + timedelta(days=365)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(starts)
        .not_valid_after(starts + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    (project / "operator.pem").write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    (project / "operator.key").write_bytes(b"not read by doctor\n")
    (project / "operator.key").chmod(0o600)
    (project / "pyproject.toml").write_text(
        '[tool.ventoux.temporal]\naddress = "localhost:7233"\nnamespace = "default"\n'
        "[tool.ventoux.temporal.identities.operator]\n"
        f'cert = "{project / "operator.pem"}"\nkey = "{project / "operator.key"}"\n'
    )
    found = read(project / "pyproject.toml")
    verdict, said = asyncio.run(identities_are_sound(Context(found, "production", None, 1.0)))  # type: ignore[arg-type]
    print(f"the certificate is valid from {starts.date().isoformat()}")
    print(f"temporal.identities: {verdict}: {said}")

if verdict == "passed":
    print(
        "RESULT: BROKEN - doctor says a certificate that isn't valid yet is in date; a connection "
        "with it would be refused"
    )
else:
    print("RESULT: HELD - a certificate not yet valid isn't passed")
