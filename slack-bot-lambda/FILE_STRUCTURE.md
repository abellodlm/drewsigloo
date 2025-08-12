# Trading Desk Slack Bot - File Structure

## 📁 Core Services

### FLR Report Service
- `handler.py` - Main FLR report handler (lightweight Lambda)
- `serverless.yml` - FLR service deployment configuration
- `requirements.txt` - FLR service dependencies

### P&L Report Service  
- `pnl_handler.py` - P&L report handler (containerized)
- `pnl_serverless.yml` - P&L service deployment configuration
- `pnl_requirements.txt` - P&L service dependencies (heavy)
- `Dockerfile` - Container configuration for P&L service

### Order Monitor Service
- `monitor_handler.py` - Monitor slash command handler
- `monitor_simple.yml` - Monitor service deployment configuration
- `monitor_requirements.txt` - Monitor service dependencies

### Real-time Monitor (EC2)
- `ec2_talos_monitor.py` - **EC2-based WebSocket client for real-time monitoring**
- `terraform/ec2_only.tf` - Infrastructure as Code for EC2 deployment
- `terraform/user_data_ec2_only.sh` - EC2 initialization script
- `terraform/terraform.tfvars` - Configuration variables

---

## 📁 Supporting Files

### Utilities
- `utils/calculations.py` - Trading calculations and metrics
- `utils/chart_generator.py` - Chart generation for P&L reports
- `utils/google_sheets.py` - Google Sheets integration
- `utils/pdf_builder.py` - PDF report generation

### Assets
- `assets/gradient_background.png` - P&L report background
- `assets/logo_hextrust.png` - Company logo for reports

### Package Management
- `package.json` / `package-lock.json` - Serverless Framework dependencies
- `node_modules/` - Node.js dependencies (for Serverless)

---

## 📁 Documentation

### Main Documentation
- `README.md` - **Complete system overview and deployment guide**
- `EC2_DEPLOYMENT.md` - **EC2-only real-time monitoring deployment**
- `FILE_STRUCTURE.md` - This file structure overview

---

## 🚀 Deployment Files by Service

### FLR Reports
```
handler.py
serverless.yml  
requirements.txt
utils/ (shared)
assets/ (shared)
```

### P&L Reports  
```
pnl_handler.py
pnl_serverless.yml
pnl_requirements.txt
Dockerfile
utils/ (shared)
assets/ (shared)
```

### Order Monitor (Lambda)
```
monitor_handler.py
monitor_simple.yml
monitor_requirements.txt
```

### Real-time Monitor (EC2)
```
ec2_talos_monitor.py
terraform/ec2_only.tf
terraform/user_data_ec2_only.sh
terraform/terraform.tfvars
```

---

## 🔧 Key Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Environment variables (API keys, tokens) |
| `terraform/terraform.tfvars` | EC2 deployment configuration |
| `monitor_simple.yml` | Monitor Lambda configuration |
| `pnl_serverless.yml` | P&L service configuration |
| `serverless.yml` | FLR service configuration |

---

## 📋 Deployment Order

1. **Deploy Lambda Services** (FLR, P&L, Monitor)
   ```bash
   serverless deploy                    # FLR service
   serverless deploy -c pnl_serverless.yml     # P&L service  
   serverless deploy -c monitor_simple.yml     # Monitor service
   ```

2. **Deploy Real-time Monitor** (EC2)
   ```bash
   cd terraform/
   terraform apply
   ```

3. **Configure Slack** 
   - Add slash commands pointing to Lambda endpoints
   - Real-time notifications work automatically

The system is now **production-ready** with clean separation of concerns! 🎯