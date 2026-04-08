# Configuration - Cloud Cost Radar
# Update GMAIL_APP_PASSWORD before running

GCP_PROJECT_ID = "niinp-dtaas-napsup-okyal"
GCP_ZONE       = "us-east4-c"

GMAIL_SENDER       = "sathriyan.marannan@gmail.com"
GMAIL_APP_PASSWORD = "wuhcbtvykrwddits"
ALERT_RECEIVER     = "sathriyan.marannan@nokia.com"

IDLE_THRESHOLD_DAYS = 3

MACHINE_COST = {
    "n2-standard-4": 210,
    "n2-standard-2": 105,
    "e2-standard-2":  50,
    "e2-standard-4":  97,
    "n1-standard-1":  25,
    "n1-standard-2":  48,
    "n1-standard-4":  97,
}
DEFAULT_COST = 80
