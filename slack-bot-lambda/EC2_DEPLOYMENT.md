# EC2-Only Talos Real-time Order Monitoring

## 🏗️ Simple Architecture

```
Slack /monitor → Lambda → DynamoDB
                    ↓
EC2 Instance ← → Talos WebSocket
     ↓
Direct Slack Notifications
```

**Benefits:**
- ✅ **Simple** - Single EC2 service handles everything
- ✅ **Reliable** - Persistent WebSocket connection
- ✅ **Cost-effective** - ~$8.50/month total
- ✅ **No Lambda complexity** - Direct notifications

---

## 🚀 Quick Deployment

### 1. Deploy with Terraform

```bash
cd terraform/
cp terraform.tfvars.example terraform.tfvars
# Edit with your values

terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

**Terraform creates:**
- EC2 t3.micro instance with Auto Scaling Group
- Security groups and IAM roles
- CloudWatch logging
- Automatic service startup

### 2. Verify Deployment

```bash
# Check Auto Scaling Group
terraform output auto_scaling_group_name

# Get instance ID
aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names [ASG_NAME]

# Check logs
aws logs tail /aws/ec2/talos-monitor-dev
```

---

## 📊 What the EC2 Service Does

### **Real-time WebSocket Monitoring**
- Connects to Talos WebSocket with proper authentication
- Receives order updates every ~250ms
- Automatically detects orders in your DynamoDB table

### **Smart Notifications**
- **Status changes**: New → PartiallyFilled → Filled
- **Significant fills**: >5% fill increase
- **Order completion**: 100% filled notifications
- **Price changes**: Avg execution price updates

### **Integration**
- Uses existing `monitor-bot-dev` DynamoDB table
- Works with existing `/monitor` Slack command
- No changes needed to current workflow

---

## 🔧 Configuration

All configuration is handled via Terraform variables:


---

## 🔍 Monitoring & Logs

### **Service Status**
```bash
# SSH to instance
ssh ec2-user@[INSTANCE_IP]

# Check service
sudo systemctl status talos-monitor

# View live logs  
sudo journalctl -u talos-monitor -f

# View application logs
sudo tail -f /var/log/talos-monitor.log
```

### **Health Checks**
- **Automatic**: Cron job every 5 minutes
- **Manual**: `/opt/talos-monitor/health_check.sh`
- **CloudWatch**: Metrics and log monitoring

### **Auto-restart**
- Service restarts automatically on failure
- Auto Scaling Group replaces unhealthy instances
- 30-second reconnection interval for WebSocket

---

## 📱 Example Notifications

When you run `/monitor orderid` in Slack:

**Initial Response:**
```
🔍 Starting monitoring for order 87526ab1...
BTC-USD Order - PartiallyFilled (45.2% filled)
Avg Price: $18,150.50 | Filled: 0.04520000 | Remaining: 0.05480000

✅ Real-time monitoring activated
• Live updates on status changes & significant fills
• Batch updates: 10:30 AM & 10:30 PM UTC
```

**Real-time Updates:**
```
🔔 Real-time Order Update
BTC-USD 87526ab1...
Status: PartiallyFilled (60.1% filled)
Avg Price: $18,148.25 | Filled: 0.06010000 | Remaining: 0.03990000

Changes:
• 📈 Fill increased by 14.9% (45.2% → 60.1%)
• 💰 Avg price improved: $18,150.50 → $18,148.25
```

---

## 💰 Cost Breakdown

**Monthly Costs:**
- **EC2 t3.micro**: $8.50 (24/7)
- **EBS storage**: $1.00 (30GB)
- **CloudWatch logs**: $0.50
- **Data transfer**: $0.50

**Total: ~$10.50/month** for unlimited real-time order monitoring

---

## 🛠️ Maintenance

### **Updates**
```bash
# Update the application
sudo systemctl stop talos-monitor
sudo cp new_talos_monitor.py /opt/talos-monitor/talos_monitor.py
sudo systemctl start talos-monitor
```

### **Scaling**
```bash
# Scale to multiple instances for HA
terraform apply -var="desired_capacity=2"
```

### **Cleanup**
```bash
# Remove all resources
terraform destroy
```

---

## ✅ Ready to Deploy!

1. **Update terraform.tfvars** with your credentials
2. **Run `terraform apply`**
3. **Watch real-time notifications** in Slack
4. **Your `/monitor` command now gives instant updates!**

The system is production-ready and will start working immediately after deployment! 🚀