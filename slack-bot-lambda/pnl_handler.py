import json
import os
import boto3
import base64
import requests
from urllib.parse import parse_qs
from datetime import datetime, timezone, timedelta
import tempfile
import pandas as pd
import gc
from utils.google_sheets import extract_pnl_data, save_pnl_export
from utils.calculations import run_calculations, get_client_data
from utils.chart_generator import generate_pnl_charts, cleanup_chart_files
from utils.pdf_builder import generate_pdf_report

# Cache environment variables at module level for better performance
CONFIG = {
    'SLACK_BOT_TOKEN': os.environ.get('SLACK_BOT_TOKEN'),
    'S3_BUCKET_NAME': os.environ.get('S3_BUCKET_NAME')
}

# Create reusable AWS clients to avoid recreating them
S3_CLIENT = boto3.client('s3')
LAMBDA_CLIENT = boto3.client('lambda', config=boto3.session.Config(
    connect_timeout=2,  # 2 second connection timeout
    read_timeout=3      # 3 second read timeout 
))

# Connection pooling for requests - reuse connections for better performance
SESSION = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_maxsize=10, pool_connections=10)
SESSION.mount('https://', adapter)
SESSION.mount('http://', adapter)

def lambda_handler(event, context):
    """
    Main Lambda handler for Slack slash command /pnl-report
    Expected format: /pnl-report last
    
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
            text = parsed_body.get('text', [''])[0].strip().lower()
            user_id = parsed_body.get('user_id', [''])[0]
            channel_id = parsed_body.get('channel_id', [''])[0]
            response_url = parsed_body.get('response_url', [''])[0]
            
            # Validate command
            if command != '/pnl-report':
                return {
                    'statusCode': 400,
                    'body': json.dumps({'text': 'Invalid command'})
                }
            
            # Handle help command
            if text == 'help' or text == '':
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'text': '📊 **P&L Report Commands**\n\n`/pnl-report last` - Generate report for last completed week (Saturday-Friday)\n`/pnl-report help` - Show this help message',
                        'response_type': 'ephemeral'
                    })
                }
            
            # Validate channel - only allow in specific channels  
            if channel_id not in ['C09DM91PG7L', 'C07KJV25M0X']:
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'text': '❌ This command can only be used in the designated P&L channel. Please use the command in the correct channel or DM.',
                        'response_type': 'ephemeral'
                    })
                }
            
            # Validate parameters
            if text != 'last':
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'text': '❌ Invalid parameter. Use `/pnl-report last` or `/pnl-report help`',
                        'response_type': 'ephemeral'
                    })
                }
            
            # Start async processing in background (don't wait for result)
            async_payload = {
                'async_processing': True,
                'report_type': text,
                'user_id': user_id,
                'channel_id': channel_id,
                'response_url': response_url
            }
            
            # Fire and forget - start async processing without waiting
            try:
                LAMBDA_CLIENT.invoke(
                    FunctionName=context.function_name,
                    InvocationType='Event',
                    Payload=json.dumps(async_payload)
                )
                print("Async P&L processing started successfully")
            except Exception as e:
                print(f"Error starting async processing: {str(e)}")
                # Don't send follow-up error here to avoid blocking the immediate response
            
            # Always return immediate response to Slack (regardless of async start status)
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'text': '🔄 Generating P&L report for last week... This may take up to 2 minutes.',
                    'response_type': 'ephemeral'
                })
            }
            
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'text': f'Error processing request: {str(e)}'
            })
        }

def handle_async_processing(event):
    """
    Handle asynchronous background processing of P&L report
    Following WeeklyDeskPnL/main.py workflow exactly
    """
    try:
        report_type = event.get('report_type', 'last')
        user_id = event.get('user_id')
        channel_id = event.get('channel_id')
        response_url = event.get('response_url')
        
        print("=== Running WeeklyDeskPnL Dashboard ===\n")
        print(f"Async P&L processing started for type: {report_type}")
        
        # Calculate cutoff date (exactly like WeeklyDeskPnL/main.py)
        cutoff_date = calculate_cutoff_date()
        start_of_week = (cutoff_date - pd.Timedelta(days=6)).strftime("%-d/%-m/%Y") 
        end_of_week = cutoff_date.strftime("%-d/%-m/%Y")
        date_range = f"{start_of_week} - {end_of_week}"
        
        print(f"P&L report date range: {date_range}")
        print(f"Cutoff date: {cutoff_date}")
        
        # Step 1: Fetch & clean data (exactly like main.py)
        df = extract_pnl_data(cutoff_date)
        csv_file_path = save_pnl_export(df)
        print("✅ Data extracted and saved.")
        
        # Step 2: Run calculations (exactly like main.py)
        metrics = run_calculations(cutoff_date, csv_file_path)
        print("✅ Calculations complete.")
        
        # Step 3: Charts (exactly like main.py)
        chart_paths = generate_pnl_charts(cutoff_date, csv_file_path)
        print("✅ All charts generated.")
        
        # Step 4: Generate PDF report (exactly like main.py)
        print("\n🏁 Report Generated")
        pdf_content = generate_pdf_report(metrics, date_range, chart_paths)
        print(f"PDF generated successfully. Size: {len(pdf_content)} bytes")
        
        # Upload PDF
        filename = f"Hex Trust Trading Summary {date_range.replace('/', '-')}.pdf"
        try:
            file_url = upload_pdf_to_slack(pdf_content, filename, channel_id, user_id)
            print(f"PDF uploaded successfully: {file_url}")
            
            # Send follow-up message confirming upload
            if response_url:
                print(f"Sending follow-up message to: {response_url}")
                # Extract key metrics for display
                weekly_pnl = metrics.get("Weekly PnL", "N/A")
                weekly_volume = metrics.get("Client Volume", "N/A") 
                weekly_margin = metrics.get("Weekly Margin", "N/A")
                
                # Get top 5 clients data
                try:
                    client_data, _ = get_client_data(cutoff_date, csv_file_path)
                    if not client_data.empty:
                        # Calculate total P&L for percentage calculation
                        total_pnl = client_data["Total P&L (USD)"].sum()
                        
                        # Sort by P&L and get top 5
                        top_clients = client_data.sort_values("Total P&L (USD)", ascending=False).head(5)
                        
                        # Format top 5 clients with percentages
                        top_clients_text = "\n\nTop 5 Clients by P&L:"
                        for _, row in top_clients.iterrows():
                            client_name = row["Client Name"]
                            client_pnl = row["Total P&L (USD)"]
                            pnl_percentage = (client_pnl / total_pnl * 100) if total_pnl != 0 else 0
                            top_clients_text += f"\n• {client_name}: {pnl_percentage:.1f}%"
                    else:
                        top_clients_text = "\n\nTop 5 Clients: No data available"
                except Exception as e:
                    print(f"Error getting top 5 clients: {e}")
                    top_clients_text = "\n\nTop 5 Clients: Unable to retrieve data"
                
                # Format date range for cleaner display (remove leading zeros and year)
                clean_date_range = date_range.replace('/2025', '').replace('/', '/')
                # Format P&L value without dollar sign for consistency
                clean_pnl = weekly_pnl.replace('$', '') if isinstance(weekly_pnl, str) else weekly_pnl
                
                # Enhanced message with top 5 clients
                send_follow_up_message(response_url, {
                    'text': f'Attached is the weekly trading summary for {clean_date_range}\nWeekly P&L: {clean_pnl}\nWeekly Volume: {weekly_volume}\nWeekly Margin: {weekly_margin}{top_clients_text}',
                    'response_type': 'ephemeral'
                })
                print("Follow-up message sent successfully")
                
        except Exception as e:
            print(f"Upload failed: {e}")
            # Final fallback - just send the error message
            if response_url:
                send_follow_up_message(response_url, {
                    'text': f'❌ P&L report generated but upload failed. Please contact support.\nPeriod: {date_range}',
                    'response_type': 'ephemeral'
                })
        finally:
            # Cleanup temporary files
            cleanup_files = []
            
            # Clean up CSV file
            if csv_file_path and os.path.exists(csv_file_path):
                cleanup_files.append(csv_file_path)
            
            # Clean up chart files (import already done at module level)
            if 'chart_paths' in locals():
                try:
                    cleanup_chart_files(chart_paths)
                except Exception as e:
                    print(f"Error cleaning up chart files: {e}")
            
            # Clean up individual files
            for file_path in cleanup_files:
                try:
                    os.unlink(file_path)
                    print(f"Cleaned up file: {file_path}")
                except Exception as e:
                    print(f"Error cleaning up {file_path}: {e}")
            
            # Force cleanup of large objects to free memory
            large_objects = ['pdf_content', 'df', 'metrics', 'chart_paths']
            for obj_name in large_objects:
                if obj_name in locals():
                    try:
                        del locals()[obj_name]
                    except:
                        pass
            
            # Force garbage collection
            gc.collect()
        
        return {'statusCode': 200, 'body': 'Async processing completed'}
        
    except Exception as e:
        print(f"Error in async processing: {str(e)}")
        response_url = event.get('response_url')
        if response_url:
            send_follow_up_message(response_url, {
                'text': f'❌ Error generating P&L report: {str(e)}',
                'response_type': 'ephemeral'
            })
        return {'statusCode': 500, 'body': f'Async processing failed: {str(e)}'}

def calculate_cutoff_date():
    """
    Calculate cutoff date exactly like WeeklyDeskPnL/main.py
    Returns pd.Timestamp for last Friday (or current Friday if late enough)
    """
    today = pd.to_datetime("today").normalize()  # Get today as pandas Timestamp
    
    # Find the most recent Friday
    days_since_friday = (today.weekday() + 3) % 7  # Monday=0, Friday=4
    if days_since_friday == 0:  # Today is Friday
        # Use today if it's late enough in the day, otherwise use last Friday
        current_hour = datetime.now().hour
        if current_hour >= 18:  # After 6 PM on Friday
            cutoff_date = today
        else:
            cutoff_date = today - pd.Timedelta(days=7)  # Use last Friday
    else:
        cutoff_date = today - pd.Timedelta(days=days_since_friday)
    
    # Convert to match WeeklyDeskPnL format (exactly like main.py line 13)
    # cutoff_date = pd.to_datetime("01-Aug-2025")  # This was hardcoded in main.py
    # For production, we use the calculated date:
    return cutoff_date

def upload_pdf_to_slack(pdf_content, filename, channel_id, user_id=None):
    """
    Upload PDF to Slack with multiple fallback approaches
    """
    bot_token = CONFIG['SLACK_BOT_TOKEN']
    if not bot_token:
        raise Exception("SLACK_BOT_TOKEN environment variable not set")
    
    print(f"Attempting to upload PDF to Slack channel: {channel_id}")
    
    # Channel-specific Slack upload only
    print(f"Uploading PDF directly to channel: {channel_id}")
    try:
        return upload_via_new_api(pdf_content, filename, channel_id, bot_token, user_id)
    except Exception as e:
        print(f"Slack upload failed: {e}")
        raise Exception(f"Failed to upload to Slack: {e}")

def upload_via_new_api(pdf_content, filename, channel_id, bot_token, user_id=None):
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
        
        upload_url_response = SESSION.post(
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
        
        upload_url_response = SESSION.post(
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
    
    upload_response = SESSION.post(
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
    
    complete_response = SESSION.post(
        'https://slack.com/api/files.completeUploadExternal',
        headers=headers,
        json={
            'files': [{
                'id': file_id,
                'title': f'P&L Report - {filename}'
            }],
            'channel_id': channel_id,
            'initial_comment': 'Your P&L Trading Summary report is ready! 📊'
        },
        timeout=10
    )
    
    complete_data = complete_response.json()
    print(f"Complete upload response: {complete_data}")
    
    if complete_data.get('ok'):
        if complete_data.get('files'):
            file_info = complete_data['files'][0]
            # Prefer public URL or direct download URL over permalink
            return (file_info.get('url_private_download') or 
                   file_info.get('permalink_public') or 
                   file_info.get('permalink') or 
                   'Upload completed')
        return 'Upload completed'
    else:
        raise Exception(f"Failed to complete upload: {complete_data.get('error')}")

def upload_pdf_to_s3(pdf_content, filename):
    """
    Upload PDF to S3 and return presigned URL
    """
    bucket_name = CONFIG['S3_BUCKET_NAME']
    
    if not bucket_name:
        raise Exception("S3_BUCKET_NAME environment variable not set")
    
    try:
        # Upload to S3
        s3_key = f"pnl-reports/{filename}"
        S3_CLIENT.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=pdf_content,
            ContentType='application/pdf'
        )
        
        # Generate presigned URL (24 hours)
        url = S3_CLIENT.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': s3_key},
            ExpiresIn=86400  # 24 hours
        )
        
        return url
        
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        raise

def send_follow_up_message(response_url, message):
    """
    Send follow-up message to Slack using response_url
    """
    try:
        print(f"Sending POST to {response_url} with message: {message}")
        response = SESSION.post(response_url, json=message, timeout=10)
        print(f"Response status: {response.status_code}, Response: {response.text}")
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error sending follow-up message: {e}")
        return False