"""Creates a small real dataset through the HTTP API of a running production container.

Used by the recovery drill (docs/runbooks/backup-restore.md). Standard library only.
usage: drill_seed.py BASE_URL MAIL_COMMAND...   (the mail command prints the emailed message files)
"""

import http.client
import json
import re
import subprocess
import sys
import uuid
from urllib.parse import urlparse

base = urlparse(sys.argv[1])
mail_cmd = sys.argv[2:]
PASSWORD = "drill-password-long-enough"  # pragma: allowlist secret
EMAIL = f"drill-{uuid.uuid4().hex[:8]}@example.test"
cookies: dict[str, str] = {}
csrf = ""


def call(
    method: str,
    path: str,
    body=None,
    raw: bytes | None = None,
    ctype: str = "application/json",
):
    conn = http.client.HTTPConnection(base.hostname, base.port, timeout=30)
    headers = {
        "X-Forwarded-Proto": "https",
        "Host": base.netloc,
        "Origin": f"http://{base.netloc}",
    }
    if cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    if csrf:
        headers["X-CSRFToken"] = csrf
    if method != "GET":
        headers["Idempotency-Key"] = str(uuid.uuid4())
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    if data is not None:
        headers["Content-Type"] = ctype
    conn.request(method, "/api/v1" + path, data, headers)
    response = conn.getresponse()
    payload = response.read()
    for name, value in response.getheaders():
        if name.lower() == "set-cookie":
            key, _, rest = value.partition("=")
            cookies[key] = rest.split(";")[0]
    if response.status >= 400:
        raise SystemExit(f"{method} {path} -> {response.status} {payload[:300]!r}")
    return json.loads(payload) if payload else None


def refresh_csrf() -> None:
    global csrf
    csrf = call("GET", "/auth/session")["csrf_token"]


call("POST", "/auth/register", {"email": EMAIL, "password": PASSWORD})
token = None
for _ in range(30):
    text = subprocess.run(mail_cmd, capture_output=True, text=True, check=False).stdout  # noqa: S603
    found = re.search(rf"To: {re.escape(EMAIL)}.*?token=([^\s&]+)", text, re.S)
    if found:
        token = found.group(1)
        break
    subprocess.run(["sleep", "1"], check=False)  # noqa: S603, S607
if not token:
    raise SystemExit("verification email never arrived (is the worker running?)")
call("POST", "/auth/verify-email", {"token": token})
call("POST", "/auth/login", {"email": EMAIL, "password": PASSWORD})
refresh_csrf()
ws = call(
    "POST",
    "/workspaces",
    {
        "name": "Drill Studio",
        "country": "IN",
        "timezone": "Asia/Kolkata",
        "default_currency": "INR",
    },
)["id"]
refresh_csrf()
rows = "".join(f"DRL-{n:03d},Client {n % 4},2026-07-01,INR,{100 + n}.00,2026-06-01\n" for n in range(1, 21))
csv_bytes = ("Invoice No,Client,Due,Currency,Total,Issued\n" + rows).encode()
boundary = uuid.uuid4().hex
multipart = (
    (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="drill.csv"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode()
    + csv_bytes
    + f"\r\n--{boundary}--\r\n".encode()
)
upload = call(
    "POST",
    f"/workspaces/{ws}/imports/invoices",
    raw=multipart,
    ctype=f"multipart/form-data; boundary={boundary}",
)
mapping = {
    "invoice_number": "Invoice No",
    "client_name": "Client",
    "due_date": "Due",
    "currency": "Currency",
    "total": "Total",
    "issue_date": "Issued",
}
call(
    "PUT",
    f"/workspaces/{ws}/imports/{upload['id']}/mapping",
    {"mapping": mapping, "date_format": "YYYY-MM-DD"},
)
call("POST", f"/workspaces/{ws}/imports/{upload['id']}/commit", {"decisions": {}})
print(json.dumps({"workspace": ws, "email": EMAIL}))
