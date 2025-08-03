import json
import os
import boto3
import base64
import requests
from urllib.parse import parse_qs
from datetime import datetime, timezone, timedelta
import tempfile

def lambda_handler(event, context):
    """
    Main Lambda handler for Slack slash command /flr-report
    Expected format: /flr-report orderid1,orderid2,orderid3
    
    Supports both synchronous (Slack command) and asynchronous (background processing) modes
    """
    
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
            
            # Validate command
            if command != '/flr-report':
                return {
                    'statusCode': 400,
                    'body': json.dumps({'text': 'Invalid command'})
                }
            
            # Parse order IDs from text
            if not text or text.strip() == '':
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'text': 'Please provide order IDs separated by commas. Example: /flr-report orderid1,orderid2'
                    })
                }
            
            order_ids = [order_id.strip() for order_id in text.split(',')]
            
            # Acknowledge the command immediately
            response_url = parsed_body.get('response_url', [''])[0]
            
            # Send immediate response
            immediate_response = {
                'statusCode': 200,
                'body': json.dumps({
                    'text': f'🔄 Starting FLR report generation for {len(order_ids)} order(s)...\nRetrieving complete execution data - this may take several minutes.\nYou will receive the report when processing is complete.',
                    'response_type': 'ephemeral'
                })
            }
            
            # Start asynchronous processing
            try:
                print(f"Starting async processing for order IDs: {order_ids}")
                
                # Invoke this same Lambda function asynchronously for background processing
                lambda_client = boto3.client('lambda')
                async_payload = {
                    'async_processing': True,
                    'order_ids': order_ids,
                    'channel_id': channel_id,
                    'response_url': response_url
                }
                
                lambda_client.invoke(
                    FunctionName=context.function_name,
                    InvocationType='Event',  # Asynchronous invocation
                    Payload=json.dumps(async_payload)
                )
                
                print("Async processing started successfully")
                
            except Exception as e:
                print(f"Error starting async processing: {str(e)}")
                if response_url:
                    send_follow_up_message(response_url, {
                        'text': f'Error starting report generation: {str(e)}',
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
    Handle asynchronous background processing of FLR report
    """
    try:
        order_ids = event['order_ids']
        channel_id = event['channel_id']
        response_url = event['response_url']
        
        print(f"Async processing started for order IDs: {order_ids}")
        
        # Generate the complete report with all records
        pdf_content = generate_flr_report(order_ids)
        print("PDF generated successfully")
        
        # Upload PDF (try Slack first, fallback to S3)
        filename = f"flr-report-{'-'.join(order_ids[:3])}.pdf"
        try:
            file_url = upload_pdf_to_slack(pdf_content, filename, channel_id)
            print(f"PDF uploaded successfully: {file_url}")
            
            # Send follow-up message confirming upload
            if response_url:
                print(f"Sending follow-up message to: {response_url}")
                if 's3.amazonaws.com' in file_url:
                    # S3 fallback was used
                    send_follow_up_message(response_url, {
                        'text': f'✅ **FLR Report Complete!**\nOrder IDs: {", ".join(order_ids)}\nDownload: {file_url}',
                        'response_type': 'in_channel'
                    })
                else:
                    # Slack upload succeeded
                    send_follow_up_message(response_url, {
                        'text': f'✅ **FLR Report Complete!**\nOrder IDs: {", ".join(order_ids)}\nReport has been uploaded to this channel',
                        'response_type': 'in_channel'
                    })
                print("Follow-up message sent successfully")
                
        except Exception as e:
            print(f"All upload methods failed: {e}")
            # Final fallback - just send the error message
            if response_url:
                send_follow_up_message(response_url, {
                    'text': f'❌ Report generated but upload failed. Please contact support.\nOrder IDs: {", ".join(order_ids)}',
                    'response_type': 'in_channel'
                })
        
        return {'statusCode': 200, 'body': 'Async processing completed'}
        
    except Exception as e:
        print(f"Error in async processing: {str(e)}")
        response_url = event.get('response_url')
        if response_url:
            send_follow_up_message(response_url, {
                'text': f'❌ Error generating report: {str(e)}',
                'response_type': 'in_channel'
            })
        return {'statusCode': 500, 'body': f'Async processing failed: {str(e)}'}

def generate_flr_report(order_ids, cutoff_hour=24):
    """Generate FLR report with real Talos and CoinGecko data"""
    from fpdf import FPDF
    import tempfile
    import os
    
    class PDF(FPDF):
        def __init__(self, cutoff_hour, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.cutoff_hour = cutoff_hour
        def header(self):
            self.set_font("Arial", "B", 14)
            self.cell(0, 10, "FLR Execution Report Summary", ln=True, align="C")
            self.ln(5)
        def footer(self):
            self.set_y(-25)
            self.set_font("Arial", "I", 8)
            self.set_text_color(100)
            self.cell(0, 5, f"Data aggregated using UTC day cutoff at {self.cutoff_hour:02d}:00", 0, 1, 'C')
            self.cell(0, 5, "Market data sourced from CoinGecko", 0, 1, 'C')
            self.cell(0, 5, f"Page {self.page_no()}", 0, 0, 'C')
            self.set_text_color(0)
        def table(self, data_rows, headers):
            self.set_font("Arial", "B", 11)
            col_widths = [60, 85, 85, 85, 70]
            row_height = 12
            for i, col in enumerate(headers):
                self.cell(col_widths[i], row_height, col, border=1, align="C")
            self.ln()
            self.set_font("Arial", "", 11)
            for row in data_rows:
                self.cell(col_widths[0], row_height, row['date'], border=1, align="C")
                self.cell(col_widths[1], row_height, f"{row['total_quantity']:,.2f}", border=1, align="R")
                self.cell(col_widths[2], row_height, f"{row['volume_30d']:,.2f}", border=1, align="R")
                self.cell(col_widths[3], row_height, f"{row['avg_daily_sell']:,.2f}", border=1, align="R")
                self.cell(col_widths[4], row_height, f"{row['sell_pressure']*100:.3f}%", border=1, align="R")
                self.ln()

    print(f"Processing real data for order IDs: {order_ids}")
    
    # Get real data from Talos and CoinGecko
    analytics_data = process_real_flr_data(order_ids, cutoff_hour)
    
    pdf = PDF(cutoff_hour=cutoff_hour, orientation='L', unit='mm', format='A3')
    pdf.add_page()
    
    headers = ["Trade Date", "Total Units Sold by Pantera (FLR)", "Total Units sold over 30 day period", "Daily Average Units Sold", "(%) Units Sold"]
    pdf.table(analytics_data, headers)
    
    pdf_bytes = pdf.output(dest='S')
    if isinstance(pdf_bytes, str):
        pdf_bytes = pdf_bytes.encode('latin-1')
    return pdf_bytes

def process_real_flr_data(order_ids, cutoff_hour):
    """Process real Talos execution data and CoinGecko market data"""
    import requests
    from datetime import datetime, timezone, timedelta
    from collections import defaultdict
    
    print(f"Starting real data processing for {len(order_ids)} order IDs")
    
    # Fetch CoinGecko data
    print("Fetching CoinGecko data...")
    coingecko_data = fetch_coingecko_data()
    print(f"CoinGecko data retrieved: {len(coingecko_data)} days")
    
    # Fetch Talos execution data  
    print("Fetching Talos execution data...")
    execution_data = fetch_talos_data(order_ids, cutoff_hour)
    print(f"Talos execution data retrieved: {len(execution_data)} records")
    
    # Process and combine data
    print("Combining and calculating metrics...")
    result = combine_and_calculate(execution_data, coingecko_data, cutoff_hour)
    print(f"Final result: {len(result)} analytics rows")
    return result

def fetch_coingecko_data():
    """Fetch FLR market data from CoinGecko"""
    api_key = os.environ.get('COINGECKO_API_KEY')
    url = "https://api.coingecko.com/api/v3/coins/flare-networks/market_chart?vs_currency=usd&days=90&interval=daily"
    headers = {"accept": "application/json", "x-cg-demo-api-key": api_key}
    
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()
    
    market_data = {}
    for i, price_data in enumerate(data.get('prices', [])):
        date = datetime.fromtimestamp(price_data[0] / 1000, tz=timezone.utc).date()
        price = price_data[1]
        volume = data.get('total_volumes', [])[i][1] if i < len(data.get('total_volumes', [])) else 0
        market_data[date] = {'volume_flr': volume / price if price else 0}
    
    return market_data

def fetch_talos_data(order_ids, cutoff_hour):
    """Fetch execution data from Talos API with proper pagination"""
    import hmac, hashlib, base64
    
    try:
        api_key = os.environ.get('API_KEY')
        api_secret = os.environ.get('API_SECRET')  
        host = os.environ.get('API_HOST')
        
        print(f"Talos API config - Host: {host}, API Key: {api_key[:8]}...")
        
        all_data = []
        method = "GET"
        path = "/v1/trade-analytics"
        limit = 200  # Reduced batch size for cost optimization
        
        for order_id in order_ids:
            print(f"Fetching data for Order ID: {order_id}")
            after_token = None
            seen_tokens = set()
            batch = 1
            
            while True:
                try:
                    # Build query with pagination
                    query = f"OrderID={order_id}&limit={limit}&TradedMarketOnly=True"
                    if after_token:
                        query += f"&after={after_token}"
                    
                    # Generate authentication headers
                    utc_datetime = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000000Z")
                    payload = f"{method}\n{utc_datetime}\n{host}\n{path}\n{query}"
                    signature = base64.urlsafe_b64encode(hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).digest()).decode()
                    
                    headers = {"TALOS-KEY": api_key, "TALOS-SIGN": signature, "TALOS-TS": utc_datetime}
                    
                    # Make API request
                    print(f"  Making request: https://{host}{path}?{query}")
                    response = requests.get(f"https://{host}{path}?{query}", headers=headers, timeout=15)
                    print(f"  Batch {batch} - Status: {response.status_code}")
                    
                    if response.status_code != 200:
                        print(f"  Request failed - Response: {response.text}")
                        break
                    
                    resp_json = response.json()
                    data = resp_json.get("data", [])
                    print(f"  Batch {batch} - Retrieved {len(data)} records")
                    all_data.extend(data)
                    
                    # Continue until all data is retrieved
                    
                    # Check for next page
                    after_token = resp_json.get("next")
                    print(f"  Next token: {after_token}")
                    if not after_token or after_token in seen_tokens:
                        print(f"  No more pages for {order_id}")
                        break
                    seen_tokens.add(after_token)
                    batch += 1
                    
                except Exception as e:
                    print(f"  Error in batch {batch} for {order_id}: {str(e)}")
                    break
        
        print(f"Total execution records retrieved: {len(all_data)}")
        return all_data
        
    except Exception as e:
        print(f"Fatal error in fetch_talos_data: {str(e)}")
        return []

def combine_and_calculate(execution_data, market_data, cutoff_hour):
    """Combine execution and market data to calculate final metrics"""
    from collections import defaultdict
    from datetime import datetime, timezone, timedelta
    
    daily = defaultdict(lambda: {"quantity_sum": 0.0})
    
    for row in execution_data:
        try:
            ts = row.get("Timestamp") or row.get("TransactTime")
            dt = datetime.fromisoformat(ts.replace("Z", "")).replace(tzinfo=timezone.utc)
            
            if cutoff_hour not in (0, 24):
                dt = dt - timedelta(hours=24 - cutoff_hour)
            
            date = dt.date()
            daily[date]["quantity_sum"] += float(row.get("Quantity", 0))
        except:
            continue
    
    # Calculate 30-day rolling volumes and sell pressure (optimized)
    analytics_data = []
    sorted_dates = sorted(daily.keys())
    
    # Limit to most recent 30 days for cost optimization
    if len(sorted_dates) > 30:
        sorted_dates = sorted_dates[-30:]
    
    for date in sorted_dates:
        quantity = daily[date]["quantity_sum"]
        
        # Calculate 30-day volume sum (optimized)
        volume_30d = 0
        start_date = date - timedelta(days=29)  # 30 days including today
        for check_date in market_data:
            if start_date <= check_date <= date:
                volume_30d += market_data[check_date]['volume_flr']
        
        avg_daily_sell = volume_30d / 30 if volume_30d else 0
        sell_pressure = quantity / avg_daily_sell if avg_daily_sell else 0
        
        analytics_data.append({
            'date': date.strftime("%d/%m/%Y"),
            'total_quantity': quantity,
            'volume_30d': volume_30d,
            'avg_daily_sell': avg_daily_sell,
            'sell_pressure': sell_pressure
        })
    
    # Return only the most recent 5 rows for the report
    return analytics_data[-5:] if len(analytics_data) > 5 else analytics_data

def upload_pdf_to_s3(pdf_content, filename):
    """
    Upload PDF to S3 and return public URL with proper binary handling
    """
    bucket_name = os.environ.get('S3_BUCKET_NAME', 'flr-reports-bucket')
    
    # Ensure PDF content is bytes for S3 upload
    if isinstance(pdf_content, str):
        print("S3: Converting PDF content from string to bytes")
        pdf_content = pdf_content.encode('latin-1')
    
    print(f"S3 Upload - PDF content type: {type(pdf_content)}, length: {len(pdf_content)}")
    print(f"S3 Upload - PDF header check: {pdf_content.startswith(b'%PDF')}")
    
    s3_client = boto3.client('s3')
    
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=f"reports/{filename}",
            Body=pdf_content,
            ContentType='application/pdf',
            ContentDisposition=f'attachment; filename="{filename}"'
        )
        
        # Generate presigned URL (valid for 24 hours)
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': f"reports/{filename}"},
            ExpiresIn=86400  # 24 hours
        )
        
        return url
        
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        # Fallback: return base64 encoded content (not recommended for large files)
        b64_content = base64.b64encode(pdf_content).decode('utf-8')
        return f"data:application/pdf;base64,{b64_content}"

def send_follow_up_message(response_url, message):
    """
    Send follow-up message to Slack using response_url
    """
    try:
        print(f"Sending POST to {response_url} with message: {message}")
        response = requests.post(response_url, json=message, timeout=10)
        print(f"Response status: {response.status_code}, Response: {response.text}")
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error sending follow-up message: {e}")
        return False

def upload_pdf_to_slack(pdf_content, filename, channel_id):
    """
    Upload PDF to Slack with multiple fallback approaches
    """
    bot_token = os.environ.get('SLACK_BOT_TOKEN')
    if not bot_token:
        raise Exception("SLACK_BOT_TOKEN environment variable not set")
    
    print(f"Attempting to upload PDF to Slack channel: {channel_id}")
    
    # Method 1: Try new API workflow
    try:
        return upload_via_new_api(pdf_content, filename, channel_id, bot_token)
    except Exception as e:
        print(f"New API method failed: {e}")
    
    # Method 2: Try legacy files.upload (might still work for some tokens)
    try:
        return upload_via_legacy_api(pdf_content, filename, channel_id, bot_token)
    except Exception as e:
        print(f"Legacy API method failed: {e}")
    
    # Method 3: Fallback to S3 upload with Slack message
    try:
        print("Falling back to S3 upload with Slack notification")
        s3_url = upload_pdf_to_s3(pdf_content, filename)
        return s3_url
    except Exception as e:
        print(f"S3 fallback failed: {e}")
        raise Exception("All upload methods failed")

def upload_via_new_api(pdf_content, filename, channel_id, bot_token):
    """
    Upload using the new 3-step API workflow with enhanced debugging
    """
    print(f"Bot token length: {len(bot_token) if bot_token else 'None'}")
    print(f"Channel ID: {channel_id}")
    print(f"Filename: {filename}")
    print(f"PDF content length: {len(pdf_content)}")
    print(f"PDF content type: {type(pdf_content)}")
    print(f"PDF starts with: {pdf_content[:20] if len(pdf_content) > 20 else pdf_content}")
    
    # Ensure PDF content is bytes
    if isinstance(pdf_content, str):
        print("Converting PDF content from string to bytes")
        pdf_content = pdf_content.encode('latin-1')
    
    # Verify PDF header
    if not pdf_content.startswith(b'%PDF'):
        print(f"WARNING: PDF content doesn't start with PDF header. First 20 bytes: {pdf_content[:20]}")
    else:
        print("PDF header verified")
    
    # Step 1: Get upload URL - Try both JSON and form data
    print("Step 1: Getting upload URL...")
    
    # Method A: Try with form data (application/x-www-form-urlencoded)
    try:
        print("Trying with form data...")
        headers = {
            'Authorization': f'Bearer {bot_token}',
        }
        
        data = {
            'filename': filename,
            'length': str(len(pdf_content))
        }
        
        upload_url_response = requests.post(
            'https://slack.com/api/files.getUploadURLExternal',
            headers=headers,
            data=data,
            timeout=10
        )
        
        upload_data = upload_url_response.json()
        print(f"Form data response: {upload_data}")
        
        if upload_data.get('ok'):
            upload_url = upload_data['upload_url']
            file_id = upload_data['file_id']
        else:
            raise Exception(f"Form data method failed: {upload_data.get('error')}")
            
    except Exception as e:
        print(f"Form data method failed: {e}")
        
        # Method B: Try with JSON
        print("Trying with JSON...")
        headers = {
            'Authorization': f'Bearer {bot_token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'filename': filename,
            'length': len(pdf_content)
        }
        
        upload_url_response = requests.post(
            'https://slack.com/api/files.getUploadURLExternal',
            headers=headers,
            json=payload,
            timeout=10
        )
        
        upload_data = upload_url_response.json()
        print(f"JSON response: {upload_data}")
        
        if not upload_data.get('ok'):
            raise Exception(f"Both methods failed. JSON error: {upload_data.get('error')}")
        
        upload_url = upload_data['upload_url']
        file_id = upload_data['file_id']
    
    # Step 2: Upload file
    print("Step 2: Uploading file...")
    print(f"Upload URL: {upload_url}")
    
    upload_response = requests.post(
        upload_url,
        files={'file': (filename, pdf_content, 'application/pdf')},
        timeout=30
    )
    
    print(f"Upload response status: {upload_response.status_code}")
    print(f"Upload response headers: {dict(upload_response.headers)}")
    
    if upload_response.status_code != 200:
        print(f"Upload response text: {upload_response.text}")
        raise Exception(f"File upload failed: {upload_response.status_code}")
    
    # Step 3: Complete upload
    print("Step 3: Completing upload...")
    headers = {
        'Authorization': f'Bearer {bot_token}',
        'Content-Type': 'application/json'
    }
    
    complete_response = requests.post(
        'https://slack.com/api/files.completeUploadExternal',
        headers=headers,
        json={
            'files': [{
                'id': file_id,
                'title': f'FLR Report - {filename}'
            }],
            'channel_id': channel_id,
            'initial_comment': 'Your FLR report is ready!'
        },
        timeout=10
    )
    
    complete_data = complete_response.json()
    print(f"Complete upload response: {complete_data}")
    
    if complete_data.get('ok'):
        return complete_data['files'][0]['permalink'] if complete_data.get('files') else 'Upload completed'
    else:
        raise Exception(f"Failed to complete upload: {complete_data.get('error')}")

def upload_via_legacy_api(pdf_content, filename, channel_id, bot_token):
    """
    Try the legacy files.upload API (may still work for some tokens)
    """
    print("Trying legacy files.upload API...")
    
    files = {
        'file': (filename, pdf_content, 'application/pdf')
    }
    
    data = {
        'channels': channel_id,
        'filename': filename,
        'filetype': 'pdf',
        'title': f'FLR Report - {filename}',
        'initial_comment': 'Your FLR report is ready!'
    }
    
    headers = {
        'Authorization': f'Bearer {bot_token}'
    }
    
    response = requests.post(
        'https://slack.com/api/files.upload',
        files=files,
        data=data,
        headers=headers,
        timeout=30
    )
    
    response_data = response.json()
    print(f"Legacy upload response: {response_data}")
    
    if response.status_code == 200 and response_data.get('ok'):
        return response_data['file']['permalink']
    else:
        error_msg = response_data.get('error', 'Unknown error')
        raise Exception(f"Legacy API error: {error_msg}")

# For local testing
if __name__ == "__main__":
    test_event = {
        'body': 'command=%2Fflr-report&text=87526ab1-e9a2-4d6e-920f-ab05c399ea9a&user_id=U123456&channel_id=C123456&response_url=https://hooks.slack.com/commands/test'
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))