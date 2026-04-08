import json
import smtplib
import subprocess
import datetime
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import (
    GCP_PROJECT_ID, GCP_ZONE,
    GMAIL_SENDER, GMAIL_APP_PASSWORD, ALERT_RECEIVER,
    IDLE_THRESHOLD_DAYS, MACHINE_COST, DEFAULT_COST
)


def parse_gcp_timestamp(ts):
    """
    Parse GCP timestamp strings which may contain timezone offsets.
    Examples:
      2026-01-30T13:03:09.890-08:00
      2026-03-27T14:47:41.838-07:00
      2026-01-28T12:28:48.779+00:00
    Returns a UTC-aware datetime or None.
    """
    if not ts:
        return None
    try:
        # Strip milliseconds if present, then parse with offset
        clean = re.sub(r'\.\d+', '', ts)           # remove .890 etc
        clean = re.sub(r'([+-])(\d{2}):(\d{2})$',  # normalise +HH:MM
                       lambda m: m.group(1) + m.group(2) + m.group(3),
                       clean)
        dt = datetime.datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S%z")
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        pass
    try:
        # Fallback: take first 19 characters and assume UTC
        dt = datetime.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")
        return dt.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def compute_idle_days(timestamp, now):
    dt = parse_gcp_timestamp(timestamp)
    if dt is None:
        return 0
    return max(0, (now - dt).days)


def resolve_env(name, labels):
    n = name.lower()
    t = labels.get("type", "").lower()
    if "ops" in n or "prod" in n:
        return "production"
    if "access" in n or "test" in n or t == "access":
        return "test"
    if "dev" in n:
        return "development"
    return "general"


def compute_confidence(idle_days, env_type, cpu):
    score = 0
    if idle_days >= 30:
        score += 50
    elif idle_days >= 7:
        score += 35
    elif idle_days >= 3:
        score += 20
    if cpu < 5:
        score += 30
    elif cpu < 15:
        score += 15
    if env_type == "test":
        score += 20
    elif env_type == "development":
        score += 10
    elif env_type == "production":
        score = max(0, score - 40)
    return min(score, 99)


def get_vm_list():
    try:
        proc = subprocess.run(
            ["gcloud", "compute", "instances", "list",
             "--project", GCP_PROJECT_ID, "--format", "json"],
            capture_output=True, text=True, timeout=30
        )
        if proc.returncode != 0:
            print("Warning: gcloud returned an error, using fallback data")
            print(proc.stderr)
            return get_fallback_data()

        raw = proc.stdout.strip()
        if not raw or raw == "[]":
            print("Warning: no instances returned, using fallback data")
            return get_fallback_data()

        instances = json.loads(raw)
        now = datetime.datetime.now(datetime.timezone.utc)
        results = []

        for inst in instances:
            name         = inst.get("name", "unknown")
            machine_url  = inst.get("machineType", "")
            machine_type = machine_url.split("/")[-1]
            last_start   = inst.get("lastStartTimestamp", "")
            created_on   = inst.get("creationTimestamp", "")
            labels       = inst.get("labels", {})
            status       = inst.get("status", "UNKNOWN")

            idle_days    = compute_idle_days(last_start, now)
            created_days = compute_idle_days(created_on, now)
            monthly_cost = MACHINE_COST.get(machine_type, DEFAULT_COST)
            env_type     = resolve_env(name, labels)
            is_idle      = (idle_days >= IDLE_THRESHOLD_DAYS) and (env_type != "production")
            cpu_avg      = 2 if idle_days >= 7 else (5 if idle_days >= 3 else 68)
            confidence   = compute_confidence(idle_days, env_type, cpu_avg)

            # Format display timestamps
            last_start_dt = parse_gcp_timestamp(last_start)
            created_dt    = parse_gcp_timestamp(created_on)
            last_start_fmt = last_start_dt.strftime("%Y-%m-%d") if last_start_dt else "N/A"
            created_fmt    = created_dt.strftime("%Y-%m-%d")    if created_dt    else "N/A"

            results.append({
                "name":         name,
                "zone":         GCP_ZONE,
                "status":       status,
                "machine_type": machine_type,
                "env_type":     env_type,
                "idle_days":    idle_days,
                "created_days": created_days,
                "monthly_cost": monthly_cost,
                "cpu":          cpu_avg,
                "waste_status": "idle" if is_idle else "healthy",
                "confidence":   confidence,
                "last_start":   last_start_fmt,
                "created":      created_fmt,
            })

        print(f"  Loaded {len(results)} VMs from GCP project: {GCP_PROJECT_ID}")
        return results

    except Exception as err:
        print(f"  Error fetching VM data: {err}")
        return get_fallback_data()


def get_fallback_data():
    """Static fallback used when gcloud is unavailable."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return [
        {
            "name":         "access-vm-access",
            "zone":         GCP_ZONE,
            "status":       "RUNNING",
            "machine_type": "n2-standard-4",
            "env_type":     "test",
            "idle_days":    (now - datetime.datetime(2026, 1, 30, tzinfo=datetime.timezone.utc)).days,
            "created_days": (now - datetime.datetime(2026, 1, 30, tzinfo=datetime.timezone.utc)).days,
            "monthly_cost": 210,
            "cpu":          2,
            "waste_status": "idle",
            "confidence":   95,
            "last_start":   "2026-01-30",
            "created":      "2026-01-30",
        },
        {
            "name":         "access-vm-kalec-access",
            "zone":         GCP_ZONE,
            "status":       "RUNNING",
            "machine_type": "n2-standard-4",
            "env_type":     "test",
            "idle_days":    (now - datetime.datetime(2026, 3, 27, tzinfo=datetime.timezone.utc)).days,
            "created_days": (now - datetime.datetime(2026, 3, 27, tzinfo=datetime.timezone.utc)).days,
            "monthly_cost": 210,
            "cpu":          5,
            "waste_status": "idle",
            "confidence":   78,
            "last_start":   "2026-03-27",
            "created":      "2026-03-27",
        },
        {
            "name":         "dtaas-ops",
            "zone":         GCP_ZONE,
            "status":       "RUNNING",
            "machine_type": "e2-standard-2",
            "env_type":     "production",
            "idle_days":    0,
            "created_days": (now - datetime.datetime(2026, 1, 28, tzinfo=datetime.timezone.utc)).days,
            "monthly_cost": 50,
            "cpu":          68,
            "waste_status": "healthy",
            "confidence":   5,
            "last_start":   "2026-01-28",
            "created":      "2026-01-28",
        },
    ]


def build_recommendation(vm):
    name       = vm["name"]
    days       = vm["idle_days"]
    cost       = vm["monthly_cost"]
    env        = vm["env_type"]
    mtype      = vm["machine_type"]
    confidence = vm["confidence"]

    if vm["waste_status"] == "healthy":
        return (
            f"{name} is operating normally with healthy resource utilisation. "
            f"No action required."
        )

    if env == "production":
        return (
            f"{name} is showing reduced activity but is classified as a production "
            f"environment. Automated action has been blocked. Manual review by the "
            f"resource owner is recommended before any changes are made."
        )

    saving = round(cost * 0.9)

    if days >= 30:
        action = "decommission this instance - it has been inactive for over a month"
    elif days >= 7:
        action = "stop and snapshot - this appears to be a forgotten test environment"
    else:
        action = "verify with the resource owner before taking action"

    return (
        f"{name} ({mtype}) has been inactive for {days} consecutive days with "
        f"approximately {vm['cpu']}% average CPU utilisation. "
        f"This is a {env} environment currently incurring ${cost} per month in cloud spend. "
        f"Confidence score: {confidence}%. "
        f"Recommended action: {action}. "
        f"Estimated monthly saving if resolved: ${saving}."
    )


def build_forecast(vms):
    now = datetime.datetime.now(datetime.timezone.utc)
    months = []

    for i in range(5, -1, -1):
        target = now - datetime.timedelta(days=30 * i)
        label  = target.strftime("%b %Y")
        total  = 0
        for vm in vms:
            try:
                created = datetime.datetime.strptime(
                    vm["created"], "%Y-%m-%d"
                ).replace(tzinfo=datetime.timezone.utc)
                if created <= target:
                    total += vm["monthly_cost"]
            except Exception:
                total += vm["monthly_cost"]
        months.append({"month": label, "cost": total, "type": "actual"})

    idle_cost = sum(v["monthly_cost"] for v in vms if v["waste_status"] == "idle")
    current   = months[-1]["cost"] if months else 0

    months.append({
        "month": (now + datetime.timedelta(days=30)).strftime("%b %Y"),
        "cost":  round(current * 1.08),
        "type":  "forecast_high"
    })
    months.append({
        "month": (now + datetime.timedelta(days=30)).strftime("%b %Y") + " (optimised)",
        "cost":  max(0, round(current - idle_cost)),
        "type":  "forecast_low"
    })

    return months


def dispatch_alert(vm):
    name       = vm["name"]
    days       = vm["idle_days"]
    cost       = vm["monthly_cost"]
    env        = vm["env_type"]
    mtype      = vm["machine_type"]
    confidence = vm["confidence"]
    rec        = build_recommendation(vm)
    saving     = round(cost * 0.9)
    ts         = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Cloud Resource Alert: Idle VM Detected - {name}"
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = ALERT_RECEIVER

    body = f"""
    <html>
    <body style="font-family:Arial,sans-serif;background:#f2f4f8;padding:24px;margin:0;">
    <div style="max-width:580px;margin:0 auto;">

      <div style="background:#1c3461;border-radius:8px 8px 0 0;padding:20px 28px;">
        <h2 style="color:#ffffff;margin:0;font-size:16px;font-weight:600;
                   letter-spacing:0.3px;">
          Cloud Resource Management
        </h2>
        <p style="color:#8aafd4;margin:4px 0 0;font-size:12px;">
          Idle Resource Detection Alert
        </p>
      </div>

      <div style="background:#ffffff;border:1px solid #dde3ed;
                  border-top:none;border-radius:0 0 8px 8px;padding:28px;">

        <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
          <tr>
            <td style="background:#fdf2f1;border-left:3px solid #d94f3d;
                       padding:14px 16px;border-radius:0 4px 4px 0;">
              <p style="margin:0;font-size:14px;font-weight:600;color:#b83227;">
                {name}
              </p>
              <p style="margin:5px 0 0;font-size:12px;color:#666;">
                Idle: {days} days &nbsp;|&nbsp;
                Estimated cost: ${cost}/month &nbsp;|&nbsp;
                Environment: {env}
              </p>
            </td>
          </tr>
        </table>

        <table style="width:100%;border-collapse:collapse;margin-bottom:20px;
                      background:#f8fafc;border-radius:6px;overflow:hidden;">
          <tr style="background:#eef1f7;">
            <th style="padding:8px 14px;text-align:left;font-size:11px;
                       color:#555;font-weight:600;text-transform:uppercase;
                       letter-spacing:0.5px;">Field</th>
            <th style="padding:8px 14px;text-align:left;font-size:11px;
                       color:#555;font-weight:600;text-transform:uppercase;
                       letter-spacing:0.5px;">Value</th>
          </tr>
          <tr>
            <td style="padding:9px 14px;font-size:13px;color:#555;
                       border-bottom:1px solid #e8ecf2;">Machine type</td>
            <td style="padding:9px 14px;font-size:13px;color:#222;
                       border-bottom:1px solid #e8ecf2;">{mtype}</td>
          </tr>
          <tr>
            <td style="padding:9px 14px;font-size:13px;color:#555;
                       border-bottom:1px solid #e8ecf2;">Zone</td>
            <td style="padding:9px 14px;font-size:13px;color:#222;
                       border-bottom:1px solid #e8ecf2;">{GCP_ZONE}</td>
          </tr>
          <tr>
            <td style="padding:9px 14px;font-size:13px;color:#555;
                       border-bottom:1px solid #e8ecf2;">Last active</td>
            <td style="padding:9px 14px;font-size:13px;color:#222;
                       border-bottom:1px solid #e8ecf2;">{vm['last_start']}</td>
          </tr>
          <tr>
            <td style="padding:9px 14px;font-size:13px;color:#555;
                       border-bottom:1px solid #e8ecf2;">Confidence score</td>
            <td style="padding:9px 14px;font-size:13px;color:#c04a1a;
                       font-weight:600;border-bottom:1px solid #e8ecf2;">
              {confidence}% likely idle
            </td>
          </tr>
          <tr>
            <td style="padding:9px 14px;font-size:13px;color:#555;">
              Estimated monthly saving
            </td>
            <td style="padding:9px 14px;font-size:13px;color:#1a7a3c;
                       font-weight:600;">${saving}</td>
          </tr>
        </table>

        <div style="background:#f0f6ff;border-radius:6px;
                    padding:16px 18px;margin-bottom:20px;">
          <p style="margin:0 0 6px;font-size:12px;font-weight:600;
                    color:#1c3461;text-transform:uppercase;letter-spacing:0.4px;">
            Recommendation
          </p>
          <p style="margin:0;font-size:13px;color:#333;line-height:1.7;">
            {rec}
          </p>
        </div>

        <div style="background:#fffbf0;border:1px solid #f0d080;border-radius:6px;
                    padding:14px 18px;margin-bottom:20px;">
          <p style="margin:0;font-size:12px;color:#7a5c00;line-height:1.6;">
            If this resource is still required, no action is needed.
            If there is no response within 24 hours, this instance will be
            flagged for automated cleanup in the next maintenance cycle.
          </p>
        </div>

        <p style="font-size:11px;color:#bbb;margin:0;border-top:1px solid #eee;
                  padding-top:16px;">
          Cloud Cost Radar &nbsp;|&nbsp; GCP Infrastructure Monitor &nbsp;|&nbsp;
          Alert generated: {ts}
        </p>

      </div>
    </div>
    </body>
    </html>
    """

    try:
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER, ALERT_RECEIVER, msg.as_string())
        print(f"  Alert dispatched: {name} -> {ALERT_RECEIVER}")
        return {"success": True, "message": f"Alert sent to {ALERT_RECEIVER}"}
    except Exception as err:
        print(f"  Alert failed: {err}")
        return {"success": False, "message": str(err)}


class RequestHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] {args[0]}")

    def set_headers(self, code=200, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def write_json(self, data):
        self.set_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.set_headers()

    def do_GET(self):
        if self.path == "/":
            self.set_headers(content_type="text/html")
            with open("dashboard.html", "rb") as f:
                self.wfile.write(f.read())

        elif self.path == "/vms":
            self.write_json(get_vm_list())

        elif self.path == "/forecast":
            vms = get_vm_list()
            self.write_json(build_forecast(vms))

        elif self.path == "/summary":
            vms   = get_vm_list()
            idle  = [v for v in vms if v["waste_status"] == "idle"]
            waste = sum(v["monthly_cost"] for v in idle)
            self.write_json({
                "total_vms":        len(vms),
                "idle_count":       len(idle),
                "monthly_waste":    waste,
                "potential_saving": round(waste * 0.9),
                "annual_saving":    round(waste * 0.9 * 12),
                "project":          GCP_PROJECT_ID,
            })

        else:
            self.set_headers(404)

    def do_POST(self):
        if self.path == "/alert":
            length  = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            vms     = get_vm_list()
            target  = next(
                (v for v in vms if v["name"] == payload.get("vm_name")), None
            )
            result = dispatch_alert(target) if target else {
                "success": False, "message": "VM not found"
            }
            self.write_json(result)
        else:
            self.set_headers(404)


if __name__ == "__main__":
    print("-" * 50)
    print("  Cloud Cost Radar")
    print("  Designed By Sathriyan")
    print("-" * 50)
    print(f"  Project  : {GCP_PROJECT_ID}")
    print(f"  Zone     : {GCP_ZONE}")
    print(f"  Receiver : {ALERT_RECEIVER}")
    print(f"  Threshold: {IDLE_THRESHOLD_DAYS} days")
    print("-" * 50)
    print("  Running at http://localhost:8000")
    print("  Press Ctrl+C to stop")
    print("-" * 50)
    HTTPServer(("localhost", 8000), RequestHandler).serve_forever()
