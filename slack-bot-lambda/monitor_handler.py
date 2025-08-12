import json
import os
import boto3
import base64
import requests
from urllib.parse import parse_qs
from datetime import datetime, timezone, timedelta
import hmac
import hashlib
from decimal import Decimal

# Cache environment variables at module level for better performance
CONFIG = {
    'API_KEY': os.environ.get('API_KEY'),
    'API_SECRET': os.environ.get('API_SECRET'),
    'API_HOST': os.environ.get('API_HOST'),
    'SLACK_BOT_TOKEN': os.environ.get('SLACK_BOT_TOKEN'),
    'DYNAMODB_TABLE': os.environ.get('DYNAMODB_TABLE', 'order-monitoring'),
    'ALLOWED_CHANNELS': os.environ.get('ALLOWED_CHANNELS', '').split(',') if os.environ.get('ALLOWED_CHANNELS') else []
}

# Create reusable AWS clients
DYNAMODB = boto3.resource('dynamodb')
try:
    MONITOR_TABLE = DYNAMODB.Table(CONFIG['DYNAMODB_TABLE'] or 'monitor-bot-dev')
except Exception as e:
    print(f"Warning: DynamoDB not available: {e}")
    MONITOR_TABLE = None

# Real-time monitoring now handled by EC2 service
LAMBDA_CLIENT = boto3.client('lambda')

# Connection pooling for requests
SESSION = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_maxsize=10, pool_connections=10)
SESSION.mount('https://', adapter)
SESSION.mount('http://', adapter)

def is_channel_allowed(channel_id):
    """
    Check if the channel is allowed to use the monitor command
    """
    allowed_channels = CONFIG['ALLOWED_CHANNELS']
    
    # If no channels specified, allow all (backward compatibility)
    if not allowed_channels or not allowed_channels[0]:
        return True
    
    # Check if current channel is in allowed list
    return channel_id in allowed_channels

def lambda_handler(event, context):
    """
    Main Lambda handler for /monitor command and scheduled checks
    """
    
    # Check if this is a scheduled monitoring check
    if event.get('scheduled_check'):
        return handle_scheduled_check(event, context)
    
    # Check if this is an async processing request  
    if event.get('async_processing'):
        return handle_async_processing(event)
    
    # Parse the Slack slash command payload
    try:
        if 'body' in event:
            # Parse URL-encoded body from Slack
            body = base64.b64decode(event['body']).decode('utf-8') if event.get('isBase64Encoded') else event['body']
            parsed_body = parse_qs(body)
            
            command = parsed_body.get('command', [''])[0]
            text = parsed_body.get('text', [''])[0]
            user_id = parsed_body.get('user_id', [''])[0]
            channel_id = parsed_body.get('channel_id', [''])[0]
            channel_name = parsed_body.get('channel_name', [''])[0]
            
            # Validate command
            if command != '/monitor':
                return {
                    'statusCode': 400,
                    'body': json.dumps({'text': 'Invalid command'})
                }
            
            # Check channel permissions
            if not is_channel_allowed(channel_id):
                print(f"Unauthorized channel access attempt: {channel_id} ({channel_name})")
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'text': '🔒 The /monitor command is restricted to authorized channels only.',
                        'response_type': 'ephemeral'
                    })
                }
            
            # Parse order ID from text (single order for now)
            if not text or text.strip() == '':
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'text': 'Please provide an order ID. Example: /monitor 87526ab1-e9a2-4d6e-920f-ab05c399ea9a'
                    })
                }
            
            order_id = text.strip()
            response_url = parsed_body.get('response_url', [''])[0]
            
            # Send immediate response
            immediate_response = {
                'statusCode': 200,
                'body': json.dumps({
                    'text': f'🔍 Starting monitoring for order {order_id}...\nChecking current execution status and setting up 8-hour monitoring.',
                    'response_type': 'ephemeral'
                })
            }
            
            # Start asynchronous processing for initial report and monitoring setup
            try:
                async_payload = {
                    'async_processing': True,
                    'order_id': order_id,
                    'channel_id': channel_id,
                    'user_id': user_id,
                    'response_url': response_url,
                    'initial_setup': True
                }
                
                LAMBDA_CLIENT.invoke(
                    FunctionName=context.function_name,
                    InvocationType='Event',
                    Payload=json.dumps(async_payload)
                )
                
            except Exception as e:
                print(f"Error starting async processing: {str(e)}")
                if response_url:
                    send_follow_up_message(response_url, {
                        'text': f'Error starting monitoring: {str(e)}',
                        'response_type': 'ephemeral'
                    })
            
            return immediate_response
            
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'text': f'Error processing request: {str(e)}'
            })
        }

def handle_async_processing(event):
    """
    Handle initial monitoring setup and first execution report
    """
    try:
        order_id = event['order_id']
        channel_id = event['channel_id']
        user_id = event['user_id']
        response_url = event['response_url']
        
        print(f"Starting monitoring for order ID: {order_id}")
        
        # Fetch current execution status
        execution_status = fetch_order_execution_status(order_id)
        
        if not execution_status:
            if response_url:
                send_follow_up_message(response_url, {
                    'text': f'❌ Could not retrieve execution data for order {order_id}',
                    'response_type': 'ephemeral'
                })
            return {'statusCode': 500, 'body': 'Failed to fetch execution data'}
        
        # Check if order is already being monitored (before generating report)
        already_monitored = check_if_already_monitored(order_id)
        
        # Generate initial execution report
        report_message = generate_execution_report(order_id, execution_status)
        
        if already_monitored:
            # Order is already being monitored
            duplicate_message = f"⚠️ **Order Already Monitored**: {order_id}\n{report_message}\n\n_This order is already in the monitoring batch. You'll receive updates at 11:00 AM & 11:00 PM UTC._"
            
            if response_url:
                send_follow_up_message(response_url, {
                    'text': duplicate_message,
                    'response_type': 'ephemeral'
                })
            
            print(f"Order {order_id} is already being monitored")
            return {'statusCode': 200, 'body': 'Order already monitored'}
        
        # Try to store monitoring job in DynamoDB
        stored = store_monitoring_job(order_id, channel_id, user_id, execution_status['is_complete'])
        
        # Real-time monitoring is now handled automatically by EC2 service
        # No additional registration needed - EC2 monitors all orders in DynamoDB
        
        # Send initial report with batch monitoring info
        if execution_status['is_complete']:
            final_message = f"{report_message}\n\n_Order is complete - no monitoring needed._"
        else:
            final_message = f"{report_message}\n\n✅ **Real-time monitoring activated**\n_• Live updates on status changes & significant fills_\n_• Batch updates: 10:30 AM & 10:30 PM UTC_"
        
        if response_url:
            send_follow_up_message(response_url, {
                'text': final_message,
                'response_type': 'in_channel'
            })
        
        # If already complete, don't start monitoring
        if execution_status['is_complete']:
            print(f"Order {order_id} is already complete ({execution_status['order_status']}), not starting monitoring")
        else:
            print(f"Order {order_id} added to monitoring batch - {execution_status['fill_percentage']}% filled")
        
        return {'statusCode': 200, 'body': 'Monitoring setup complete'}
        
    except Exception as e:
        print(f"Error in async processing: {str(e)}")
        if event.get('response_url'):
            send_follow_up_message(event['response_url'], {
                'text': f'Error setting up monitoring: {str(e)}',
                'response_type': 'ephemeral'
            })
        return {'statusCode': 500, 'body': str(e)}

def handle_scheduled_check(event, context):
    """
    Handle scheduled batch monitoring checks at 11:00 AM and 11:00 PM UTC
    """
    try:
        current_time = datetime.now(timezone.utc)
        
        print(f"Running batch monitoring check at {current_time.strftime('%H:%M')} UTC")
        
        if not MONITOR_TABLE:
            print("Warning: DynamoDB table not available, no scheduled monitoring")
            return {'statusCode': 200, 'body': 'No monitoring table available'}
        
        # Get all active monitoring jobs
        response = MONITOR_TABLE.scan(
            FilterExpression='#status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': 'active'}
        )
        
        active_jobs = response['Items']
        print(f"Found {len(active_jobs)} active monitoring jobs")
        
        if not active_jobs:
            print("No active orders to monitor")
            return {'statusCode': 200, 'body': 'No active orders to monitor'}
        
        # Group jobs by channel to send batch updates
        jobs_by_channel = {}
        for job in active_jobs:
            channel_id = job['channel_id']
            if channel_id not in jobs_by_channel:
                jobs_by_channel[channel_id] = []
            jobs_by_channel[channel_id].append(job)
        
        # Process each channel
        for channel_id, channel_jobs in jobs_by_channel.items():
            try:
                batch_reports = []
                completed_orders = []
                
                for job in channel_jobs:
                    order_id = job['order_id']
                    
                    try:
                        # Fetch current execution status
                        execution_status = fetch_order_execution_status(order_id)
                        
                        if execution_status:
                            # Generate status report
                            report = generate_execution_report(order_id, execution_status)
                            batch_reports.append(f"• {report}")
                            
                            if execution_status['is_complete']:
                                # Mark as completed in DynamoDB
                                MONITOR_TABLE.update_item(
                                    Key={'order_id': order_id},
                                    UpdateExpression='SET #status = :status, completion_time = :completion_time',
                                    ExpressionAttributeNames={'#status': 'status'},
                                    ExpressionAttributeValues={
                                        ':status': 'completed',
                                        ':completion_time': datetime.now(timezone.utc).isoformat()
                                    }
                                )
                                completed_orders.append(order_id)
                                print(f"Order {order_id} completed ({execution_status['order_status']}) - stopping monitoring")
                            else:
                                # Update last check time
                                MONITOR_TABLE.update_item(
                                    Key={'order_id': order_id},
                                    UpdateExpression='SET last_check = :last_check',
                                    ExpressionAttributeValues={
                                        ':last_check': datetime.now(timezone.utc).isoformat()
                                    }
                                )
                        else:
                            batch_reports.append(f"• ❌ {order_id}: Unable to fetch status")
                            print(f"Failed to fetch status for order {order_id}")
                            
                    except Exception as e:
                        batch_reports.append(f"• ⚠️ {order_id}: Error - {str(e)}")
                        print(f"Error checking order {order_id}: {str(e)}")
                
                # Send batch update to Slack channel
                if batch_reports:
                    time_period = "Morning" if current_time.hour == 11 else "Evening"
                    batch_message = f"📊 **{time_period} Order Monitoring Update** ({current_time.strftime('%H:%M')} UTC)\n\n" + "\n".join(batch_reports)
                    
                    if completed_orders:
                        batch_message += f"\n\n✅ **Completed orders removed from monitoring**: {len(completed_orders)}"
                    
                    remaining_active = len(channel_jobs) - len(completed_orders)
                    if remaining_active > 0:
                        next_time = "11:00 UTC" if current_time.hour == 23 else "23:00 UTC"
                        batch_message += f"\n\n📅 **Next update**: {next_time} ({remaining_active} orders)"
                    
                    send_slack_message(channel_id, batch_message)
                    
            except Exception as e:
                print(f"Error processing channel {channel_id}: {str(e)}")
                continue
        
        total_processed = sum(len(jobs) for jobs in jobs_by_channel.values())
        return {'statusCode': 200, 'body': f'Processed {total_processed} orders across {len(jobs_by_channel)} channels'}
        
    except Exception as e:
        print(f"Error in scheduled check: {str(e)}")
        return {'statusCode': 500, 'body': str(e)}

def fetch_order_execution_status(order_id):
    """
    Fetch current execution status for a specific order using Talos /v1/orders API
    """
    try:
        api_key = CONFIG['API_KEY']
        api_secret = CONFIG['API_SECRET']
        host = CONFIG['API_HOST']
        
        if not all([api_key, api_secret, host]):
            raise Exception("Missing Talos API credentials")
        
        method = "GET"
        path = "/v1/orders"
        query = f"OrderID={order_id}"
        
        # Generate authentication headers
        utc_datetime = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000000Z")
        payload = f"{method}\n{utc_datetime}\n{host}\n{path}\n{query}"
        signature = base64.urlsafe_b64encode(
            hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).digest()
        ).decode()
        
        headers = {
            "TALOS-KEY": api_key,
            "TALOS-SIGN": signature,
            "TALOS-TS": utc_datetime
        }
        
        # Make API request
        response = SESSION.get(f"https://{host}{path}?{query}", headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"API request failed: {response.status_code} - {response.text}")
            return None
        
        json_data = response.json()
        data = json_data.get("data", [])
        
        if not data:
            return None
        
        # Get the first (and should be only) order
        order = data[0]
        
        # Extract order information
        symbol = order.get("Symbol", "UNKNOWN")
        cum_qty = float(order.get("CumQty", 0))
        order_qty = float(order.get("OrderQty", 0))
        leaves_qty = float(order.get("LeavesQty", 0))
        avg_price = float(order.get("AvgPx", 0))
        avg_price_all_in = float(order.get("AvgPxAllIn", avg_price))  # Use all-in price, fallback to regular
        ord_status = order.get("OrdStatus", "Unknown")
        
        # Calculate fill percentage
        fill_percentage = (cum_qty / order_qty * 100) if order_qty > 0 else 0
        
        # Count executed markets/trades
        markets = order.get("Markets", [])
        filled_markets = len([m for m in markets if float(m.get("CumQty", 0)) > 0])
        
        return {
            'asset': symbol,
            'total_quantity': cum_qty,
            'order_quantity': order_qty,
            'remaining_quantity': leaves_qty,
            'avg_price': avg_price,
            'avg_price_all_in': avg_price_all_in,
            'fill_percentage': round(fill_percentage, 2),
            'order_status': ord_status,
            'market_count': filled_markets,
            'is_complete': ord_status in ['Filled', 'DoneForDay']
        }
        
    except Exception as e:
        print(f"Error fetching order execution status: {str(e)}")
        return None

def format_quantity(qty):
    """
    Format quantity with K/M suffixes and appropriate decimals
    """
    if qty >= 1_000_000:
        # Millions
        formatted = qty / 1_000_000
        if formatted >= 100:
            return f"{formatted:.0f}M"
        elif formatted >= 10:
            return f"{formatted:.1f}M"
        else:
            return f"{formatted:.2f}M"
    elif qty >= 1_000:
        # Thousands
        formatted = qty / 1_000
        if formatted >= 100:
            return f"{formatted:.0f}K"
        elif formatted >= 10:
            return f"{formatted:.1f}K"
        else:
            return f"{formatted:.2f}K"
    else:
        # Less than 1000, show decimals based on magnitude
        if qty >= 100:
            return f"{qty:.0f}"
        elif qty >= 10:
            return f"{qty:.1f}"
        else:
            return f"{qty:.2f}"

def format_price(price):
    """
    Format price with appropriate decimal places based on magnitude
    """
    if price >= 1000:
        return f"{price:.2f}"
    elif price >= 100:
        return f"{price:.3f}"
    elif price >= 10:
        return f"{price:.4f}"
    elif price >= 1:
        return f"{price:.5f}"
    else:
        return f"{price:.6f}"

def generate_execution_report(order_id, execution_status):
    """
    Generate execution report message in format: ~7M FLR filled (70%) at average net price of $0.0227
    """
    # Extract asset name (remove pair suffix like -USDT)
    symbol = execution_status['asset']
    asset = symbol.split('-')[0] if '-' in symbol else symbol
    
    filled_qty = execution_status['total_quantity']
    avg_price_all_in = execution_status['avg_price_all_in']
    fill_percentage = execution_status['fill_percentage']
    status = execution_status['order_status']
    
    # Format quantities and price
    formatted_qty = format_quantity(filled_qty)
    formatted_price = format_price(avg_price_all_in)
    
    # Generate appropriate message based on completion status
    if execution_status['is_complete']:
        return f"✅ {formatted_qty} {asset} filled (100%) at final average net price of ${formatted_price}"
    else:
        return f"📊 ~{formatted_qty} {asset} filled ({fill_percentage}%) at average net price of ${formatted_price}"

def check_if_already_monitored(order_id):
    """
    Check if an order is already being monitored
    """
    if not MONITOR_TABLE:
        return False
    
    try:
        response = MONITOR_TABLE.get_item(Key={'order_id': order_id})
        
        if 'Item' in response:
            status = response['Item'].get('status', 'unknown')
            return status == 'active'
        
        return False
    except Exception as e:
        print(f"Error checking monitoring status: {str(e)}")
        return False

def store_monitoring_job(order_id, channel_id, user_id, is_complete):
    """
    Store monitoring job in DynamoDB (if available)
    """
    if not MONITOR_TABLE:
        print("Warning: DynamoDB table not available, monitoring job not stored")
        return False
    
    try:
        # Check for duplicates first
        if check_if_already_monitored(order_id):
            print(f"Order {order_id} is already being monitored")
            return False
        
        current_time = datetime.now(timezone.utc).isoformat()
        
        # Only store if not already complete
        status = 'completed' if is_complete else 'active'
        
        item = {
            'order_id': order_id,
            'channel_id': channel_id,
            'user_id': user_id,
            'start_time': current_time,
            'last_check': current_time,
            'status': status
        }
        
        if status == 'completed':
            item['completion_time'] = current_time
        
        MONITOR_TABLE.put_item(Item=item)
        print(f"Monitoring job stored for order {order_id}")
        return True
    except Exception as e:
        print(f"Error storing monitoring job: {str(e)}")
        return False

# Real-time monitoring registration removed - EC2 service handles all monitoring automatically

def send_follow_up_message(response_url, message):
    """
    Send follow-up message to Slack response URL
    """
    try:
        response = SESSION.post(response_url, json=message, timeout=10)
        if response.status_code == 200:
            print("Follow-up message sent successfully")
        else:
            print(f"Failed to send follow-up message: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error sending follow-up message: {str(e)}")

def send_slack_message(channel_id, text):
    """
    Send message to Slack channel using Bot Token
    """
    try:
        bot_token = CONFIG['SLACK_BOT_TOKEN']
        if not bot_token:
            print("No Slack bot token available")
            return
        
        url = "https://slack.com/api/chat.postMessage"
        headers = {
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "channel": channel_id,
            "text": text
        }
        
        response = SESSION.post(url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200 and response.json().get("ok"):
            print("Slack message sent successfully")
        else:
            print(f"Failed to send Slack message: {response.text}")
            
    except Exception as e:
        print(f"Error sending Slack message: {str(e)}")