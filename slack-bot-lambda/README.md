# Trading Desk Slack Bot

A comprehensive serverless Slack bot that generates trading reports using AWS Lambda.

## Services

### 1. FLR Report Service (`/flr-report`)
- Processes multiple order IDs: `/flr-report orderid1,orderid2,orderid3`
- Generates comprehensive PDF reports with:
  - Daily trading summaries
  - 30-day volume analysis
  - Sell pressure calculations
- Automatic PDF upload to S3 with secure download links

### 2. P&L Report Service (`/pnl-report`)
- Weekly P&L analysis: `/pnl-report last`
- Complete WeeklyDeskPnL integration with:
  - YTD, MTD, and weekly P&L calculations
  - Week-over-week change analysis
  - 8 interactive charts (cumulative, weekly bars, rankings, pie charts)
  - Professional landscape PDF reports with gradient background
  - Google Sheets data extraction (2000+ records)
  - Direct Slack file upload with S3 fallback

### 3. Order Monitor Service (`/monitor`)
- Real-time order monitoring: `/monitor orderid`
- Provides immediate execution report and continuous monitoring:
  - Current fill percentage and average net price
  - Automated 8-hour status updates until 100% filled
  - Final completion notification with cleanup
  - DynamoDB state persistence for reliable monitoring
- Lightweight service optimized for continuous operation

## Architecture

```
Slack → API Gateway → Lambda Functions → External APIs → S3/DynamoDB → Reports

Services:
- FLR Service: handler.py (lightweight)
- P&L Service: pnl_handler.py (containerized with heavy dependencies)
- Monitor Service: monitor_handler.py (lightweight, scheduled triggers)
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

**Optional: Restrict Monitor Service to Specific Channels**
```bash
# Add to .env to restrict /monitor command to specific channels
ALLOWED_CHANNELS=C1234567890,C0987654321

# To find channel IDs:
# 1. Right-click on channel name in Slack
# 2. Select "Copy link"
# 3. Extract ID from URL: https://workspace.slack.com/archives/C1234567890
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

### 5. Deploy P&L Service (Containerized)

The P&L service uses Docker containers for heavy dependencies:

```bash
# Deploy P&L service with container
serverless deploy -c pnl_serverless.yml

# Monitor deployment
serverless logs -f pnlBotV2 -c pnl_serverless.yml
```

**P&L Prerequisites:**
- Google Sheets API credentials stored in AWS SSM
- Required SSM parameters:
  - `/pnl-bot/GOOGLE_SERVICE_ACCOUNT_EMAIL`
  - `/pnl-bot/GOOGLE_PRIVATE_KEY`
  - `/pnl-bot/GOOGLE_PROJECT_ID`
  - `/pnl-bot/GOOGLE_SHEET_ID`

### 6. Configure Slack

1. Go to https://api.slack.com/apps
2. Create a new Slack app
3. Go to "Slash Commands" and create:
   - `/flr-report` → FLR service webhook URL
   - `/pnl-report` → P&L service webhook URL
   - `/monitor` → Monitor service webhook URL
4. Set the Request URLs to the webhook URLs from deployment output
5. Add required bot scopes: `files:write`, `chat:write`
6. Install the app to your workspace

## Usage

### FLR Reports
In Slack, use the command:
```
/flr-report 87526ab1-e9a2-4d6e-920f-ab05c399ea9a
```

Or multiple orders:
```
/flr-report orderid1,orderid2,orderid3
```

### P&L Reports
In Slack, use the command:
```
/pnl-report last    # Generate weekly P&L report
/pnl-report help    # Show help information
```

### Order Monitoring
In Slack, use the command:
```
/monitor 87526ab1-e9a2-4d6e-920f-ab05c399ea9a    # Start monitoring order
```

**What happens:**
1. **Immediate Report**: Current fill status with smart formatting (~7.10M FLR filled 70.96%)
2. **Duplicate Detection**: Warns if order already being monitored
3. **Batch Monitoring**: Groups all orders for scheduled updates
4. **Scheduled Updates**: 11:00 AM & 11:00 PM UTC with all active orders
5. **Auto Cleanup**: Completed orders automatically removed from monitoring
6. **Channel Security**: Only works in authorized channels

## Local Testing

```bash
python handler.py
```

## Deployment Commands

### FLR Service
```bash
# Deploy FLR service
serverless deploy

# View logs
serverless logs -f slackBot

# Remove deployment
serverless remove
```

### P&L Service
```bash
# Deploy P&L service (containerized)
serverless deploy -c pnl_serverless.yml

# View logs
serverless logs -f pnlBotV2 -c pnl_serverless.yml

# Remove P&L deployment
serverless remove -c pnl_serverless.yml
```

### Monitor Service
```bash
# Deploy Monitor service (with DynamoDB and EventBridge)
serverless deploy -c monitor_simple.yml

# View logs
serverless logs -f monitor -c monitor_simple.yml

# Check DynamoDB table
aws dynamodb describe-table --table-name monitor-bot-dev

# Manual batch check (for testing)
aws lambda invoke --function-name monitor-simple-dev-monitor \
  --payload '{"scheduled_check": true}' response.json

# Remove Monitor deployment
serverless remove -c monitor_simple.yml
```

## Cost Analysis & Optimization

### FLR Service Cost (per report)
**Lambda Function:**
- Memory: 1024 MB 
- Timeout: 5 minutes
- Architecture: ARM64 (20% cheaper than x86_64)
- Typical execution: 1-3 minutes
- Cost: ~$0.002-0.006 per report

### P&L Service Cost (per report)
**Lambda Function (Containerized):**
- Memory: 2048 MB (required for chart generation)
- Timeout: 29 seconds (API Gateway limit)
- Architecture: x86_64 (container compatibility)
- Actual execution: ~12 seconds
- Cost: ~$0.008-0.012 per report

**Container Storage (ECR):**
- Container image: ~2GB with heavy dependencies
- Cost: ~$0.20 per month (regardless of usage)

**Additional Services:**
- **API Gateway:** 1 REST API request (~$0.0000035)
- **S3 Storage:** PDF storage 2-3MB (~$0.0001)
- **Google Sheets API:** Free tier (100 requests/100 seconds)

### Monitor Service Cost (per order monitored)
**Lambda Function:**
- Memory: 512 MB (lightweight monitoring)
- Timeout: 30 seconds
- Architecture: ARM64 (20% cost savings)
- Initial execution: ~2-5 seconds
- Scheduled checks: ~1-2 seconds each
- Cost: ~$0.001 per initial setup + ~$0.0001 per 8-hour check

**DynamoDB:**
- Pay-per-request billing (cost-effective for monitoring workload)
- TTL enabled for automatic cleanup
- Cost: ~$0.0000001 per read/write operation

**EventBridge (Scheduled):**
- Twice daily triggers (11:00 AM & 11:00 PM UTC)
- Cost: ~$0.000001 per invocation (essentially free)

**Total Estimated Costs:**
- **FLR Report:** $0.002-0.007 per report
- **P&L Report:** $0.008-0.013 per report + $0.20/month container storage
- **Monitor Service:** $0.001-0.005 per order (depending on monitoring duration)

### Cost Optimizations Applied

**FLR Service:**
1. **ARM64 architecture** for 20% cost savings
2. **Optimized memory** at 1024MB for lightweight processing
3. **Batch size optimized** to 200 records per API call
4. **Data processing limited** to recent 30 days

**P&L Service:**
1. **Container deployment** for heavy dependencies efficiency
2. **Asynchronous processing** to avoid API Gateway timeout charges
3. **29-second timeout** (API Gateway maximum)
4. **Chart cleanup** removes temporary files immediately
5. **Single container image** serves multiple chart generation needs

**Monitor Service:**
1. **ARM64 architecture** for 20% cost savings on compute
2. **Lightweight memory** at 512MB for monitoring operations
3. **Pay-per-request DynamoDB** eliminates idle costs
4. **TTL-enabled cleanup** prevents storage cost accumulation
5. **8-hour intervals** balance timeliness with cost efficiency

### ⚠️ Monitoring Recommendations

**P&L Service (Recently Deployed):**
- **Actual performance:** 12 seconds execution, 311MB peak memory
- **Container cold start:** ~3.8 seconds initial overhead
- **Memory usage:** Well within 2048MB limit
- **No optimization needed** - service performs efficiently

**FLR Service:**
- Monitor for memory errors if processing large datasets
- Current 1024MB should be sufficient for most workloads

**Current Configurations:**
```yaml
# FLR Service (serverless.yml)
memorySize: 1024
timeout: 300
architecture: arm64

# P&L Service (pnl_serverless.yml) 
memorySize: 2048
timeout: 29
architecture: x86_64
```

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