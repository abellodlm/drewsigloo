#!/bin/bash
# EC2 User Data Script for Talos WebSocket Monitor (EC2-Only Architecture)
# This script sets up the EC2 instance to run the all-in-one Talos monitor

set -e

# Variables from Terraform
AWS_REGION="${aws_region}"
ENVIRONMENT="${environment}"
API_KEY="${api_key}"
API_SECRET="${api_secret}"
API_HOST="${api_host}"
SLACK_BOT_TOKEN="${slack_bot_token}"

# System setup
yum update -y
yum install -y python3 python3-pip git htop

# Install CloudWatch agent
yum install -y amazon-cloudwatch-agent

# Create application directory
mkdir -p /opt/talos-monitor
cd /opt/talos-monitor

# Download the Python application from the repo or copy it
# For now, we'll create it inline (in production, you'd copy from S3 or git)
cat > talos_monitor.py << 'EOF'
#!/usr/bin/env python3
# This would be the full ec2_talos_monitor.py content
# For brevity, using placeholder - in production copy the actual file
print("Placeholder for ec2_talos_monitor.py - replace with actual file content")
EOF

# Alternative: Copy from S3 bucket or git repository
# aws s3 cp s3://your-bucket/ec2_talos_monitor.py talos_monitor.py

# Create requirements file
cat > requirements.txt << 'EOF'
websocket-client>=1.8.0
boto3>=1.26.0
slack-sdk>=3.19.0
EOF

# Install Python dependencies
pip3 install -r requirements.txt

# Make script executable
chmod +x talos_monitor.py

# Create environment file for the service
cat > /opt/talos-monitor/.env << EOF
AWS_DEFAULT_REGION=${AWS_REGION}
API_KEY=${API_KEY}
API_SECRET=${API_SECRET}
API_HOST=${API_HOST}
SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}
EOF

# Create systemd service
cat > /etc/systemd/system/talos-monitor.service << EOF
[Unit]
Description=Talos Real-time Order Monitor (EC2-Only)
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/talos-monitor
ExecStart=/usr/bin/python3 /opt/talos-monitor/talos_monitor.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal
EnvironmentFile=/opt/talos-monitor/.env

[Install]
WantedBy=multi-user.target
EOF

# Configure CloudWatch agent
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << EOF
{
    "logs": {
        "logs_collected": {
            "files": {
                "collect_list": [
                    {
                        "file_path": "/var/log/talos-monitor.log",
                        "log_group_name": "/aws/ec2/talos-monitor-${ENVIRONMENT}",
                        "log_stream_name": "{instance_id}/talos-monitor.log"
                    }
                ]
            }
        }
    },
    "metrics": {
        "namespace": "TalosMonitor/${ENVIRONMENT}",
        "metrics_collected": {
            "cpu": {
                "measurement": [
                    "cpu_usage_idle",
                    "cpu_usage_user",
                    "cpu_usage_system"
                ],
                "metrics_collection_interval": 300
            },
            "mem": {
                "measurement": [
                    "mem_used_percent"
                ],
                "metrics_collection_interval": 300
            },
            "disk": {
                "measurement": [
                    "used_percent"
                ],
                "metrics_collection_interval": 300,
                "resources": [
                    "*"
                ]
            }
        }
    }
}
EOF

# Start and enable services
systemctl daemon-reload
systemctl enable amazon-cloudwatch-agent
systemctl start amazon-cloudwatch-agent
systemctl enable talos-monitor
systemctl start talos-monitor

# Create health check script
cat > /opt/talos-monitor/health_check.sh << 'EOF'
#!/bin/bash
# Health check script for Talos monitor

SERVICE_STATUS=$(systemctl is-active talos-monitor)
if [ "$SERVICE_STATUS" != "active" ]; then
    echo "ERROR: Talos monitor service is not running"
    exit 1
fi

# Check if process is actually running
if ! pgrep -f "talos_monitor.py" > /dev/null; then
    echo "ERROR: Talos monitor process not found"
    exit 1
fi

# Check log for recent activity (within last 5 minutes)
if [ -f /var/log/talos-monitor.log ]; then
    RECENT_LOG=$(find /var/log/talos-monitor.log -mmin -5)
    if [ -z "$RECENT_LOG" ]; then
        echo "WARNING: No recent log activity"
    fi
fi

echo "OK: Talos monitor is running"
exit 0
EOF

chmod +x /opt/talos-monitor/health_check.sh

# Add cron job for health monitoring
echo "*/5 * * * * /opt/talos-monitor/health_check.sh >> /var/log/health_check.log 2>&1" | crontab -

# Log completion
echo "$(date): Talos monitor setup completed successfully" >> /var/log/user-data.log
echo "Service status: $(systemctl is-active talos-monitor)" >> /var/log/user-data.log