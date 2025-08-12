#!/usr/bin/env python3
"""
EC2-Only Talos Real-time Order Monitor
- Connects to Talos WebSocket for real-time order updates
- Sends direct Slack notifications for significant changes
- Integrates with existing /monitor command DynamoDB table
- Single service, no Lambda dependencies
"""

import json
import time
import logging
import boto3
import os
import hmac
import hashlib
import base64
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from websocket import create_connection
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('talos-monitor-local.log', 'a')
    ]
)
logger = logging.getLogger(__name__)

class TalosRealtimeMonitor:
    def __init__(self):
        # Configuration from environment
        self.api_host = os.getenv('API_HOST')
        self.api_key = os.getenv('API_KEY')
        self.api_secret = os.getenv('API_SECRET')
        self.slack_token = os.getenv('SLACK_BOT_TOKEN')
        
        # Slack client
        self.slack_client = WebClient(token=self.slack_token)
        
        # DynamoDB setup
        self.dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        self.table = self.dynamodb.Table('monitor-bot-dev')
        
        # WebSocket connection
        self.websocket = None
        self.is_connected = False
        self.is_running = True
        self.reconnect_interval = 30  # seconds
        
        # Track monitored orders for change detection
        self.order_cache = {}  # order_id -> last_known_state
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        logger.info(f"🚀 Initialized Talos Monitor for host: {self.api_host}")
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"📨 Received signal {signum}, shutting down...")
        self.is_running = False
        if self.websocket:
            self.websocket.close()
        
    def connect_websocket(self):
        """Connect to Talos WebSocket API with proper authentication"""
        try:
            # Generate timestamp and signature
            utc_now = datetime.utcnow()
            utc_datetime = utc_now.strftime("%Y-%m-%dT%H:%M:%S.000000Z")
            
            host = self.api_host
            path = "/ws/v1"
            
            # Create signature payload
            params = "\n".join([
                "GET",
                utc_datetime,
                host,
                path,
            ])
            
            # Generate HMAC signature
            hash_obj = hmac.new(
                self.api_secret.encode('ascii'), 
                params.encode('ascii'), 
                hashlib.sha256
            )
            signature = base64.urlsafe_b64encode(hash_obj.digest()).decode()
            
            # Create authentication headers
            headers = {
                "TALOS-KEY": self.api_key,
                "TALOS-SIGN": signature,
                "TALOS-TS": utc_datetime,
            }
            
            # Connect to WebSocket
            ws_url = f"wss://{host}{path}"
            logger.info(f"🔌 Connecting to: {ws_url}")
            
            self.websocket = create_connection(ws_url, header=headers, timeout=30)
            self.is_connected = True
            logger.info("✅ Connected to Talos WebSocket")
            
            # Subscribe to Order stream
            self.subscribe_to_orders()
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to WebSocket: {e}")
            self.is_connected = False
            raise
    
    def subscribe_to_orders(self):
        """Subscribe to Talos Order stream"""
        subscription = {
            "reqid": int(time.time()),
            "type": "subscribe",
            "streams": [{
                "name": "Order",
                "StartDate": datetime.utcnow().isoformat() + "Z"
            }]
        }
        
        logger.info("📡 Subscribing to Order stream...")
        self.websocket.send(json.dumps(subscription))
        logger.info("✅ Subscribed to Order stream")
    
    def handle_message(self, message: str):
        """Process incoming WebSocket messages"""
        try:
            data = json.loads(message)
            msg_type = data.get('type', 'unknown')
            
            if msg_type == 'Order':
                self.process_order_update(data)
            elif msg_type == 'error':
                logger.error(f"❌ Talos error: {data}")
            elif msg_type == 'hello':
                logger.info("👋 Received hello from Talos")
            else:
                logger.debug(f"📊 Message type: {msg_type}")
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    def process_order_update(self, order_data: Dict[str, Any]):
        """Process order update from Talos"""
        if 'data' not in order_data:
            return
            
        orders_processed = 0
        monitored_found = 0
        
        for order in order_data['data']:
            orders_processed += 1
            order_id = order.get('OrderID')
            if not order_id:
                continue
                
            # Check if this order is being monitored
            if self.is_order_monitored(order_id):
                monitored_found += 1
                self.handle_monitored_order(order_id, order)
        
        if orders_processed > 0:
            logger.debug(f"📊 Processed {orders_processed} orders, {monitored_found} monitored")
    
    def is_order_monitored(self, order_id: str) -> bool:
        """Check if order is in our monitoring table"""
        try:
            response = self.table.get_item(Key={'order_id': order_id})
            return 'Item' in response
        except Exception as e:
            logger.error(f"Error checking monitored orders: {e}")
            return False
    
    def handle_monitored_order(self, order_id: str, order_data: Dict[str, Any]):
        """Handle a monitored order update"""
        try:
            # Extract current order state
            current_state = {
                'status': order_data.get('OrdStatus', 'Unknown'),
                'symbol': order_data.get('Symbol', 'Unknown'),
                'cum_qty': float(order_data.get('CumQty', '0')),
                'order_qty': float(order_data.get('OrderQty', '0')),
                'avg_px': float(order_data.get('AvgPx', '0')),
                'leaves_qty': float(order_data.get('LeavesQty', '0')),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
            
            # Calculate fill percentage
            fill_pct = (current_state['cum_qty'] / current_state['order_qty'] * 100) if current_state['order_qty'] > 0 else 0
            current_state['fill_pct'] = fill_pct
            
            # Check for significant changes
            last_state = self.order_cache.get(order_id, {})
            significant_changes = self.detect_significant_changes(last_state, current_state)
            
            if significant_changes:
                # Send notification
                self.send_notification(order_id, current_state, significant_changes)
                
                # Update DynamoDB with latest state
                self.update_order_in_db(order_id, current_state)
            
            # Cache current state
            self.order_cache[order_id] = current_state
            
            # Log order status
            logger.info(f"📈 {current_state['symbol']} {order_id[:8]}... - {current_state['status']} ({fill_pct:.1f}% filled)")
            
        except Exception as e:
            logger.error(f"Error handling monitored order {order_id}: {e}")
    
    def detect_significant_changes(self, old_state: Dict[str, Any], new_state: Dict[str, Any]) -> list:
        """Detect significant changes that warrant notifications"""
        changes = []
        
        # First time seeing this order
        if not old_state:
            changes.append("🆕 Started real-time monitoring")
            return changes
        
        # Status change
        old_status = old_state.get('status', 'Unknown')
        new_status = new_state.get('status', 'Unknown')
        if old_status != new_status:
            status_emoji = self.get_status_emoji(new_status)
            changes.append(f"{status_emoji} Status: {old_status} → **{new_status}**")
        
        # Fill percentage change notifications removed per user request
        old_fill = old_state.get('fill_pct', 0)
        new_fill = new_state.get('fill_pct', 0)
        # fill_diff = new_fill - old_fill
        # 
        # if fill_diff >= 5:  # 5% or more increase
        #     changes.append(f"📈 Fill increased by {fill_diff:.1f}% ({old_fill:.1f}% → {new_fill:.1f}%)")
        
        # Order completion
        if new_fill >= 100 and old_fill < 100:
            changes.append("🎉 **Order completed (100% filled)**")
        
        # Significant price change (commented out - might need later)
        # old_price = old_state.get('avg_px', 0)
        # new_price = new_state.get('avg_px', 0)
        # if old_price > 0 and new_price > 0:
        #     price_change_pct = abs(new_price - old_price) / old_price * 100
        #     if price_change_pct > 0.1:  # 0.1% price change
        #         direction = "improved" if new_price > old_price else "worsened"
        #         changes.append(f"💰 Avg price {direction}: ${old_price:.4f} → ${new_price:.4f}")
        
        return changes
    
    def get_status_emoji(self, status: str) -> str:
        """Get emoji for order status"""
        status_emojis = {
            'New': '🆕',
            'PartiallyFilled': '🔄',
            'Filled': '✅',
            'Canceled': '❌',
            'Rejected': '🚫',
            'PendingCancel': '⏳',
            'PendingNew': '⏳'
        }
        return status_emojis.get(status, '📊')
    
    def send_notification(self, order_id: str, order_state: Dict[str, Any], changes: list):
        """Send Slack notification for order changes"""
        try:
            # Get channel from DynamoDB
            response = self.table.get_item(Key={'order_id': order_id})
            if 'Item' not in response:
                logger.warning(f"Order {order_id} not found in monitoring table")
                return
            
            channel_id = response['Item'].get('channel_id')
            if not channel_id:
                logger.warning(f"No channel found for order {order_id}")
                return
            
            # Format notification message
            message = self.format_notification_message(order_id, order_state, changes)
            
            # Send to Slack
            self.slack_client.chat_postMessage(
                channel=channel_id,
                text=message,
                mrkdwn=True
            )
            
            logger.info(f"🔔 Sent notification to {channel_id} for order {order_id[:8]}...")
            
        except SlackApiError as e:
            logger.error(f"Slack API error: {e.response['error']}")
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
    
    def format_notification_message(self, order_id: str, order_state: Dict[str, Any], changes: list) -> str:
        """Format the Slack notification message"""
        symbol = order_state['symbol']
        status = order_state['status']
        fill_pct = order_state['fill_pct']
        avg_px = order_state['avg_px']
        cum_qty = order_state['cum_qty']
        leaves_qty = order_state['leaves_qty']
        
        # Format quantities
        cum_qty_str = self.format_quantity(cum_qty, symbol)
        leaves_qty_str = self.format_quantity(leaves_qty, symbol)
        
        # Build message
        header = "🔔 **Real-time Order Update**"
        order_info = f"**{symbol}** `{order_id[:8]}...`"
        status_line = f"Status: **{status}** ({fill_pct:.1f}% filled)"
        
        details = []
        if avg_px > 0:
            details.append(f"Avg Price: ${avg_px:,.4f}")
        if cum_qty > 0:
            details.append(f"Filled: {cum_qty_str}")
        if leaves_qty > 0:
            details.append(f"Remaining: {leaves_qty_str}")
        
        changes_text = "\n".join(f"• {change}" for change in changes)
        
        message_parts = [header, order_info, status_line]
        if details:
            message_parts.append(" | ".join(details))
        message_parts.append(f"\n**Changes:**\n{changes_text}")
        
        return "\n".join(message_parts)
    
    def format_quantity(self, qty: float, symbol: str) -> str:
        """Format quantity with appropriate precision"""
        if symbol.endswith(('USD', 'USDT')):
            if qty < 1:
                return f"{qty:.8f}"
            elif qty < 100:
                return f"{qty:.6f}"
            else:
                return f"{qty:,.4f}"
        else:
            if qty < 1:
                return f"{qty:.6f}"
            else:
                return f"{qty:,.2f}"
    
    def update_order_in_db(self, order_id: str, order_state: Dict[str, Any]):
        """Update order state in DynamoDB"""
        try:
            self.table.update_item(
                Key={'order_id': order_id},
                UpdateExpression="""
                    SET last_update = :timestamp,
                        last_status = :status,
                        last_fill_pct = :fill_pct
                """,
                ExpressionAttributeValues={
                    ':timestamp': order_state['timestamp'],
                    ':status': order_state['status'],
                    ':fill_pct': order_state['fill_pct']
                }
            )
        except Exception as e:
            logger.error(f"Error updating order in DB: {e}")
    
    def health_check(self):
        """Perform periodic health checks"""
        try:
            # Check WebSocket connection
            if self.websocket and not self.websocket.closed:
                # Send ping if possible
                pass
            
            # Log health status
            monitored_count = len(self.order_cache)
            logger.info(f"💓 Health check - Connected: {self.is_connected}, Monitoring: {monitored_count} orders")
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            self.is_connected = False
    
    def run(self):
        """Main event loop with automatic reconnection"""
        logger.info("🚀 Starting Talos Real-time Monitor")
        
        last_health_check = time.time()
        health_check_interval = 300  # 5 minutes
        
        while self.is_running:
            try:
                # Connect if not connected
                if not self.is_connected:
                    self.connect_websocket()
                
                # Receive and process messages
                if self.is_connected and self.websocket:
                    try:
                        # Set a timeout for receive to allow periodic health checks
                        self.websocket.settimeout(10)
                        message = self.websocket.recv()
                        if message:
                            self.handle_message(message)
                    except Exception as recv_error:
                        if "timed out" not in str(recv_error):
                            logger.error(f"Error receiving message: {recv_error}")
                            self.is_connected = False
                
                # Periodic health check
                current_time = time.time()
                if current_time - last_health_check > health_check_interval:
                    self.health_check()
                    last_health_check = current_time
                    
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}")
                self.is_connected = False
                
                if self.is_running:
                    logger.info(f"⏳ Reconnecting in {self.reconnect_interval} seconds...")
                    time.sleep(self.reconnect_interval)
        
        # Cleanup
        if self.websocket:
            self.websocket.close()
        logger.info("👋 Talos Monitor stopped")

def main():
    """Main entry point"""
    monitor = TalosRealtimeMonitor()
    
    try:
        monitor.run()
    except KeyboardInterrupt:
        logger.info("⏹️ Shutting down monitor...")
        monitor.is_running = False
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()