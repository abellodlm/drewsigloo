#!/usr/bin/env python3
"""
EC2-Only Talos Real-time Order Monitor
- Connects to Talos WebSocket for real-time order updates
- Sends direct Slack notifications
- Integrates with existing /monitor command DynamoDB table
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
import threading
from collections import deque, OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Set, List
from functools import lru_cache
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
        
        # Performance and caching configuration
        self.max_cache_size = 10000  # Prevent unbounded memory growth
        self.monitored_orders_ttl = 300  # Refresh monitored orders every 5 minutes
        self.batch_notification_delay = 2  # Batch notifications for 2 seconds
        
        # Slack client with connection pooling
        self.slack_client = WebClient(
            token=self.slack_token,
            timeout=10,
            pool_maxsize=20
        )
        
        # DynamoDB setup with connection pooling
        self.dynamodb = boto3.resource(
            'dynamodb', 
            region_name='us-east-1',
            config=boto3.session.Config(
                max_pool_connections=50,
                retries={'max_attempts': 3}
            )
        )
        self.table = self.dynamodb.Table('monitor-bot-dev')
        
        # WebSocket connection
        self.websocket = None
        self.is_connected = False
        self.is_running = True
        self.reconnect_interval = 30  # seconds
        
        # Optimized caching and data structures
        self.order_cache = OrderedDict()  # LRU cache for order states
        self.monitored_orders_cache = set()  # Cached set of monitored order IDs
        self.monitored_orders_last_refresh = 0
        
        # Batch processing
        self.notification_queue = deque()
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="talos-monitor")
        self.notification_lock = threading.Lock()
        
        # Performance metrics
        self.metrics = {
            'orders_processed': 0,
            'notifications_sent': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'db_queries': 0,
            'start_time': time.time()
        }
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # Start background notification processor
        self._start_notification_processor()
        
        logger.info(f"🚀 Initialized optimized Talos Monitor for host: {self.api_host}")
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"📨 Received signal {signum}, shutting down...")
        self.is_running = False
        if self.websocket:
            self.websocket.close()
        self.executor.shutdown(wait=True)
    
    def _start_notification_processor(self):
        """Start background thread for batch notification processing"""
        def process_notifications():
            while self.is_running:
                try:
                    time.sleep(self.batch_notification_delay)
                    self._process_notification_batch()
                except Exception as e:
                    logger.error(f"Error in notification processor: {e}")
        
        self.executor.submit(process_notifications)
        logger.info("📨 Started background notification processor")
    
    def _process_notification_batch(self):
        """Process queued notifications in batch"""
        if not self.notification_queue:
            return
            
        with self.notification_lock:
            # Process up to 10 notifications per batch
            notifications_to_send = []
            for _ in range(min(10, len(self.notification_queue))):
                if self.notification_queue:
                    notifications_to_send.append(self.notification_queue.popleft())
        
        # Send notifications in parallel
        if notifications_to_send:
            futures = []
            for notification in notifications_to_send:
                future = self.executor.submit(self._send_single_notification, notification)
                futures.append(future)
            
            # Wait for all notifications to complete
            for future in futures:
                try:
                    future.result(timeout=5)
                    self.metrics['notifications_sent'] += 1
                except Exception as e:
                    logger.error(f"Failed to send notification: {e}")
    
    def _send_single_notification(self, notification_data):
        """Send a single notification to Slack"""
        try:
            channel_id, message = notification_data
            self.slack_client.chat_postMessage(
                channel=channel_id,
                text=message,
                mrkdwn=True
            )
        except SlackApiError as e:
            logger.error(f"Slack API error: {e.response.get('error', 'Unknown')}")
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
    
    def _maintain_cache_size(self):
        """Maintain LRU cache within size limits"""
        while len(self.order_cache) > self.max_cache_size:
            # Remove oldest item (LRU eviction)
            oldest_order = next(iter(self.order_cache))
            del self.order_cache[oldest_order]
    
    def _refresh_monitored_orders_cache(self):
        """Refresh the cached set of monitored orders from DynamoDB"""
        current_time = time.time()
        if current_time - self.monitored_orders_last_refresh < self.monitored_orders_ttl:
            self.metrics['cache_hits'] += 1
            return
        
        try:
            self.metrics['db_queries'] += 1
            response = self.table.scan(
                ProjectionExpression='order_id',
                FilterExpression='attribute_exists(order_id)'
            )
            
            new_monitored_orders = {item['order_id'] for item in response.get('Items', [])}
            
            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = self.table.scan(
                    ProjectionExpression='order_id',
                    FilterExpression='attribute_exists(order_id)',
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                new_monitored_orders.update(item['order_id'] for item in response.get('Items', []))
            
            self.monitored_orders_cache = new_monitored_orders
            self.monitored_orders_last_refresh = current_time
            self.metrics['cache_misses'] += 1
            
            logger.debug(f"🔄 Refreshed monitored orders cache: {len(self.monitored_orders_cache)} orders")
            
        except Exception as e:
            logger.error(f"Error refreshing monitored orders cache: {e}")
            # Use stale cache on error
            self.metrics['cache_hits'] += 1
        
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
        """Process order update from Talos with optimized batch processing"""
        if 'data' not in order_data:
            return
            
        # Refresh monitored orders cache if needed
        self._refresh_monitored_orders_cache()
        
        orders_processed = 0
        monitored_found = 0
        monitored_orders_batch = []
        
        for order in order_data['data']:
            orders_processed += 1
            order_id = order.get('OrderID')
            if not order_id:
                continue
            
            self.metrics['orders_processed'] += 1
                
            # Check if this order is being monitored (using cached set)
            if self.is_order_monitored_cached(order_id):
                monitored_found += 1
                monitored_orders_batch.append((order_id, order))
        
        # Process monitored orders in batch
        if monitored_orders_batch:
            self._process_monitored_orders_batch(monitored_orders_batch)
        
        if orders_processed > 0:
            logger.debug(f"📊 Processed {orders_processed} orders, {monitored_found} monitored")
    
    def _process_monitored_orders_batch(self, monitored_orders: List[tuple]):
        """Process multiple monitored orders efficiently"""
        for order_id, order_data in monitored_orders:
            try:
                self.handle_monitored_order(order_id, order_data)
            except Exception as e:
                logger.error(f"Error processing order {order_id}: {e}")
    
    def is_order_monitored_cached(self, order_id: str) -> bool:
        """Check if order is monitored using cached set (much faster)"""
        return order_id in self.monitored_orders_cache
    
    def is_order_monitored(self, order_id: str) -> bool:
        """Check if order is in our monitoring table"""
        try:
            response = self.table.get_item(Key={'order_id': order_id})
            return 'Item' in response
        except Exception as e:
            logger.error(f"Error checking monitored orders: {e}")
            return False
    
    def handle_monitored_order(self, order_id: str, order_data: Dict[str, Any]):
        """Handle a monitored order update with optimized caching"""
        try:
            # Extract current order state
            current_state = {
                'status': order_data.get('OrdStatus', 'Unknown'),
                'symbol': order_data.get('Symbol', 'Unknown'),
                'cum_qty': float(order_data.get('CumQty', '0')),
                'order_qty': float(order_data.get('OrderQty', '0')),
                'avg_px': float(order_data.get('AvgPx', '0')),
                'leaves_qty': float(order_data.get('LeavesQty', '0')),
                'comments': order_data.get('Comments', ''),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
            
            # Calculate fill percentage
            fill_pct = (current_state['cum_qty'] / current_state['order_qty'] * 100) if current_state['order_qty'] > 0 else 0
            current_state['fill_pct'] = fill_pct
            
            # Check for significant changes
            last_state = self.order_cache.get(order_id, {})
            significant_changes = self.detect_significant_changes(last_state, current_state)
            
            if significant_changes:
                # Queue notification for batch processing
                self.queue_notification(order_id, current_state, significant_changes)
                
                # Update DynamoDB with latest state (async)
                self.executor.submit(self.update_order_in_db, order_id, current_state)
            
            # Update LRU cache (move to end for LRU)
            if order_id in self.order_cache:
                del self.order_cache[order_id]
            self.order_cache[order_id] = current_state
            
            # Maintain cache size
            self._maintain_cache_size()
            
            # Log order status
            logger.debug(f"📈 {current_state['symbol']} {order_id[:8]}... - {current_state['status']} ({fill_pct:.1f}% filled)")
            
        except Exception as e:
            logger.error(f"Error handling monitored order {order_id}: {e}")
    
    def queue_notification(self, order_id: str, order_state: Dict[str, Any], changes: list):
        """Queue notification for batch processing"""
        try:
            # Get channel from cache or DynamoDB
            channel_id = self._get_order_channel_cached(order_id)
            if not channel_id:
                return
            
            # Format notification message
            message = self.format_notification_message(order_id, order_state, changes)
            
            # Add to queue
            with self.notification_lock:
                self.notification_queue.append((channel_id, message))
            
            logger.debug(f"🔔 Queued notification for order {order_id[:8]}...")
            
        except Exception as e:
            logger.error(f"Error queuing notification: {e}")
    
    def _get_order_channel_cached(self, order_id: str) -> Optional[str]:
        """Get order channel with caching"""
        try:
            self.metrics['db_queries'] += 1
            response = self.table.get_item(Key={'order_id': order_id})
            if 'Item' in response:
                return response['Item'].get('channel_id')
            return None
        except Exception as e:
            logger.error(f"Error getting channel for order {order_id}: {e}")
            return None
    
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
    
    @lru_cache(maxsize=32)
    def get_status_emoji(self, status: str) -> str:
        """Get emoji for order status (cached)"""
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
        comments = order_state.get('comments', '')
        
        # Format quantities
        cum_qty_str = self.format_quantity(cum_qty, symbol)
        leaves_qty_str = self.format_quantity(leaves_qty, symbol)
        
        # Build message
        header = "🔔 **Real-time Order Update**"
        order_info = f"**{symbol}** `{order_id[:8]}...`"
        if comments:
            order_info += f" - {comments}"
        
        # Create descriptive fill status line
        if cum_qty > 0 and avg_px > 0:
            # Extract base currency from symbol (e.g., BTC-USD -> BTC, CPOOL-USD -> CPOOL)
            base_currency = symbol.split('-')[0] if '-' in symbol else symbol
            fill_status = f"~{cum_qty_str} {base_currency} filled ({fill_pct:.2f}% of total order size) at average gross price of ${avg_px:,.6f}"
        else:
            fill_status = f"Status: **{status}** ({fill_pct:.1f}% filled)"
        
        changes_text = "\n".join(f"• {change}" for change in changes)
        
        message_parts = [header, order_info, fill_status]
        message_parts.append(f"\n**Changes:**\n{changes_text}")
        
        return "\n".join(message_parts)
    
    @lru_cache(maxsize=1000)
    def format_quantity(self, qty: float, symbol: str) -> str:
        """Format quantity with appropriate precision and human-readable scale (cached)"""
        # For large quantities, use K/M notation like ~244K
        if qty >= 1_000_000:
            return f"{qty/1_000_000:.1f}M"
        elif qty >= 1_000:
            return f"{qty/1_000:.0f}K"
        elif qty >= 1:
            return f"{qty:,.0f}"
        elif qty >= 0.01:
            return f"{qty:.2f}"
        elif qty >= 0.0001:
            return f"{qty:.4f}"
        else:
            return f"{qty:.8f}"
    
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
    
    def run(self):
        """Main event loop with automatic reconnection and performance monitoring"""
        logger.info("🚀 Starting optimized Talos Real-time Monitor")
        
        last_metrics_log = time.time()
        metrics_log_interval = 300  # Log metrics every 5 minutes
        
        while self.is_running:
            try:
                # Connect if not connected
                if not self.is_connected:
                    self.connect_websocket()
                
                # Receive and process messages
                if self.is_connected and self.websocket:
                    try:
                        # Set a timeout for receive to allow periodic checks
                        self.websocket.settimeout(10)
                        message = self.websocket.recv()
                        if message:
                            self.handle_message(message)
                    except Exception as recv_error:
                        if "timed out" not in str(recv_error):
                            logger.error(f"Error receiving message: {recv_error}")
                            self.is_connected = False
                
                # Periodic metrics logging
                current_time = time.time()
                if current_time - last_metrics_log > metrics_log_interval:
                    self._log_performance_metrics()
                    last_metrics_log = current_time
                    
            except Exception as e:
                logger.error(f"❌ Error in main loop: {e}")
                self.is_connected = False
                
                if self.is_running:
                    logger.info(f"⏳ Reconnecting in {self.reconnect_interval} seconds...")
                    time.sleep(self.reconnect_interval)
        
        # Cleanup
        self._shutdown_cleanup()
        logger.info("👋 Optimized Talos Monitor stopped")
    
    def _log_performance_metrics(self):
        """Log performance metrics for monitoring"""
        uptime = time.time() - self.metrics['start_time']
        cache_hit_rate = (self.metrics['cache_hits'] / 
                         max(self.metrics['cache_hits'] + self.metrics['cache_misses'], 1) * 100)
        
        logger.info(f"📊 Performance Metrics:")
        logger.info(f"   Uptime: {uptime/3600:.1f} hours")
        logger.info(f"   Orders processed: {self.metrics['orders_processed']}")
        logger.info(f"   Notifications sent: {self.metrics['notifications_sent']}")
        logger.info(f"   DB queries: {self.metrics['db_queries']}")
        logger.info(f"   Cache hit rate: {cache_hit_rate:.1f}%")
        logger.info(f"   Active orders cached: {len(self.order_cache)}")
        logger.info(f"   Monitored orders: {len(self.monitored_orders_cache)}")
        logger.info(f"   Notification queue size: {len(self.notification_queue)}")
    
    def _shutdown_cleanup(self):
        """Perform cleanup during shutdown"""
        logger.info("🧹 Performing shutdown cleanup...")
        
        # Close WebSocket
        if self.websocket:
            self.websocket.close()
        
        # Process remaining notifications
        while self.notification_queue:
            try:
                self._process_notification_batch()
                time.sleep(0.1)  # Small delay to process remaining notifications
            except Exception as e:
                logger.error(f"Error processing final notifications: {e}")
                break
        
        # Shutdown thread pool
        self.executor.shutdown(wait=True, timeout=10)
        
        # Log final metrics
        self._log_performance_metrics()
        logger.info("✅ Cleanup completed")

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