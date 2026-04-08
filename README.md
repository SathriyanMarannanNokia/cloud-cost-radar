# Cloud Cost Radar

A lightweight tool that monitors GCP cloud infrastructure, detects idle and underutilised virtual machines, and automatically alerts resource owners before costs escalate.

## What it does

- Connects to GCP and scans all running VMs in real time
- Flags VMs that have been idle based on CPU usage patterns
- Calculates estimated monthly waste per idle resource
- Sends automated email alerts to resource owners
- Forecasts next month cloud spend based on usage trends
- Supports auto-remediation with a safe confirmation window before stopping idle VMs
- Displays everything in a simple web dashboard

## How to run

1. Make sure Python 3 and gcloud CLI are installed
2. Authenticate gcloud with your GCP account:
   ```
   gcloud auth login
   gcloud config set project niinp-dtaas-napsup-okyal
   ```
3. Update `config.py` with your Gmail app password
4. Run the server:
   ```
   python app.py
   ```
5. Open in browser:
   ```
   http://localhost:8000
   ```

## Project structure

| File | Description |
|------|-------------|
| `app.py` | Backend server: fetches GCP data, handles alerts |
| `config.py` | Configuration: project ID, email settings, thresholds |
| `dashboard.html` | Frontend: real-time web dashboard |
| `main.yml` | CI/CD pipeline definition |

## Requirements

- Python 3.7 or above
- gcloud CLI authenticated with GCP project access
- Gmail account with App Password for sending alerts
