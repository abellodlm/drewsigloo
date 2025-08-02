import json
import os
import boto3
import base64
from urllib.parse import parse_qs
from scripts.coingecko_flr import get_flr_volume_data
from scripts.execution_report import generate_execution_report
from scripts.final_calc import enrich_with_sell_pressure
from scripts.pdf_report import generate_pdf_report
import tempfile

def lambda_handler(event, context):
    """
    Main Lambda handler for Slack slash command /flr-report
    Expected format: /flr-report orderid1,orderid2,orderid3
    """
    
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
                    'text': f'Processing FLR report for {len(order_ids)} order(s)... This may take a few minutes.',
                    'response_type': 'ephemeral'
                })
            }
            
            # Process the report generation asynchronously
            try:
                pdf_content = generate_flr_report(order_ids)
                
                # Upload PDF to S3 or return as base64 (depending on your setup)
                s3_url = upload_pdf_to_s3(pdf_content, f"flr-report-{'-'.join(order_ids[:3])}.pdf")
                
                # Send follow-up message with PDF link
                send_follow_up_message(response_url, {
                    'text': f'✅ FLR Report generated successfully!\n📊 Order IDs: {", ".join(order_ids)}\n📄 Download: {s3_url}',
                    'response_type': 'in_channel'
                })
                
            except Exception as e:
                send_follow_up_message(response_url, {
                    'text': f'❌ Error generating report: {str(e)}',
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

def generate_flr_report(order_ids, cutoff_hour=24):
    """
    Generate FLR report using the existing scripts
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        os.chdir(temp_dir)
        
        # Step 1: Fetch FLR market data
        print("Fetching FLR market data...")
        get_flr_volume_data()
        
        # Step 2: Generate execution report
        print(f"Generating execution report for orders: {order_ids}")
        generate_execution_report(order_ids=order_ids, cutoff_hour=cutoff_hour)
        
        # Step 3: Enrich with sell pressure
        print("Enriching report with sell pressure...")
        enrich_with_sell_pressure()
        
        # Step 4: Generate PDF
        print("Generating PDF summary...")
        pdf_filename = "summary_report.pdf"
        generate_pdf_report(cutoff_hour=cutoff_hour, output_pdf=pdf_filename)
        
        # Read PDF content
        with open(pdf_filename, 'rb') as f:
            pdf_content = f.read()
        
        return pdf_content

def upload_pdf_to_s3(pdf_content, filename):
    """
    Upload PDF to S3 and return public URL
    """
    bucket_name = os.environ.get('S3_BUCKET_NAME', 'flr-reports-bucket')
    
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
    import requests
    
    try:
        response = requests.post(response_url, json=message)
        response.raise_for_status()
    except Exception as e:
        print(f"Error sending follow-up message: {e}")

# For local testing
if __name__ == "__main__":
    test_event = {
        'body': 'command=%2Fflr-report&text=87526ab1-e9a2-4d6e-920f-ab05c399ea9a&user_id=U123456&channel_id=C123456&response_url=https://hooks.slack.com/commands/test'
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))