# FLR Slack Bot

A serverless Slack bot that generates FLR (Flare) trading reports using AWS Lambda.

## Features

- Slack slash command `/flr-report` to generate PDF reports
- Processes multiple order IDs: `/flr-report orderid1,orderid2,orderid3`
- Generates comprehensive PDF reports with:
  - Daily trading summaries
  - 30-day volume analysis
  - Sell pressure calculations
- Automatic PDF upload to S3 with secure download links
- Auto-cleanup: Reports expire after 7 days

## Architecture

```
Slack → API Gateway → Lambda → Scripts → S3 → PDF Download Link
```

## Setup

### 1. Prerequisites

- AWS CLI configured
- Docker installed (for packaging heavy dependencies)
- Node.js and npm installed
- Serverless Framework: `npm install -g serverless`
- Python 3.9+

### 2. Install Dependencies

```bash
cd slack-bot-lambda
npm install serverless-python-requirements
```

### 3. Environment Setup

```bash
cp .env.example .env
# Edit .env with your actual values
```

### 4. Deploy (Optimized for Heavy Dependencies)

The deployment uses Lambda layers to handle heavy dependencies like pandas:

```bash
# Deploy to development (includes pandas layer)
serverless deploy

# Deploy to production
serverless deploy --stage prod
```

### 5. Troubleshooting Large Packages

If deployment fails due to package size:

**Option A: Use pre-built AWS layers**
```bash
# Use AWS Data Science layer (includes pandas, numpy, etc.)
# Add this to your serverless.yml functions section:
layers:
  - arn:aws:lambda:us-east-1:336392948345:layer:AWSSDKPandas-Python39:1
```

**Option B: Fallback to lightweight version**
```bash
# Use lightweight requirements
cp requirements-light.txt requirements.txt
serverless deploy
```

**Option C: Container deployment**
```bash
# Use container image (alternative approach)
# Update serverless.yml to use ECR image instead
```

### 5. Configure Slack

1. Go to https://api.slack.com/apps
2. Create a new Slack app
3. Go to "Slash Commands" and create `/flr-report`
4. Set the Request URL to the webhook URL from deployment output
5. Install the app to your workspace

## Usage

In Slack, use the command:
```
/flr-report 87526ab1-e9a2-4d6e-920f-ab05c399ea9a
```

Or multiple orders:
```
/flr-report orderid1,orderid2,orderid3
```

## Local Testing

```bash
python handler.py
```

## Deployment Commands

```bash
# Deploy
serverless deploy

# View logs
serverless logs -f slackBot

# Remove deployment
serverless remove
```

## Cost Optimization

- Lambda only charges for execution time
- S3 stores reports temporarily (7-day auto-cleanup)
- API Gateway charges per request
- Estimated cost: $0.01-0.05 per report

## Security

- S3 bucket is private with presigned URLs
- Environment variables for sensitive data
- IAM roles with minimal permissions
- Slack signing secret verification (optional)

## Troubleshooting

1. **Timeout errors**: Increase timeout in `serverless.yml`
2. **Memory errors**: Increase memorySize in `serverless.yml`
3. **Permission errors**: Check IAM roles in AWS console
4. **Slack verification**: Enable signing secret verification