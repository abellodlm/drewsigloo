# Assets Directory

This directory contains static assets for the P&L reporting system:

## Required Files

1. **gradient_background.png** (copied from WeeklyDeskPnL)
   - Background image for PDF reports

2. **logo_hextrust.png** (copied from WeeklyDeskPnL) 
   - Company logo for PDF reports

## Google Service Account Credentials

The Google service account credentials (htmdrew-73d8bc647c51.json) are stored securely in AWS SSM Parameters:

- `/pnl-bot/GOOGLE_SERVICE_ACCOUNT_EMAIL`
- `/pnl-bot/GOOGLE_PRIVATE_KEY`
- `/pnl-bot/GOOGLE_PROJECT_ID`
- `/pnl-bot/GOOGLE_PRIVATE_KEY_ID`
- `/pnl-bot/GOOGLE_CLIENT_ID`
- `/pnl-bot/GOOGLE_SHEET_ID`

## Setup Instructions

To set up the SSM parameters from the existing JSON file:

```bash
# Extract values from htmdrew-73d8bc647c51.json and store in SSM
aws ssm put-parameter --name "/pnl-bot/GOOGLE_SERVICE_ACCOUNT_EMAIL" --value "your-service-account@project.iam.gserviceaccount.com" --type "SecureString"
aws ssm put-parameter --name "/pnl-bot/GOOGLE_PRIVATE_KEY" --value "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----" --type "SecureString"
aws ssm put-parameter --name "/pnl-bot/GOOGLE_PROJECT_ID" --value "htmdrew" --type "SecureString"
aws ssm put-parameter --name "/pnl-bot/GOOGLE_PRIVATE_KEY_ID" --value "73d8bc647c51" --type "SecureString"
aws ssm put-parameter --name "/pnl-bot/GOOGLE_CLIENT_ID" --value "client-id-from-json" --type "SecureString"
aws ssm put-parameter --name "/pnl-bot/GOOGLE_SHEET_ID" --value "1fgFPF_rUoGfn_sHcQDuCw7hpuoZuXXZz5CVlaa6yXcI" --type "SecureString"
```