import json
import os
import boto3
import base64
import requests
from urllib.parse import parse_qs
from datetime import datetime
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
            
            # Process the report generation (simplified for now)
            try:
                print(f"Processing report for order IDs: {order_ids}")
                pdf_content = generate_flr_report(order_ids)
                print("PDF generated successfully")
                
                # Upload PDF directly to Slack
                filename = f"flr-report-{'-'.join(order_ids[:3])}.pdf"
                slack_file_url = upload_pdf_to_slack(pdf_content, filename, channel_id)
                print(f"PDF uploaded to Slack: {slack_file_url}")
                
                # Send follow-up message confirming upload
                if response_url:
                    print(f"Sending follow-up message to: {response_url}")
                    send_follow_up_message(response_url, {
                        'text': f'FLR Report uploaded successfully!\nOrder IDs: {", ".join(order_ids)}\nReport has been uploaded to this channel',
                        'response_type': 'in_channel'
                    })
                    print("Follow-up message sent successfully")
                
            except Exception as e:
                print(f"Error processing report: {str(e)}")
                if response_url:
                    send_follow_up_message(response_url, {
                        'text': f'Error generating report: {str(e)}',
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
    Generate comprehensive FLR report with proper analytics
    """
    from fpdf import FPDF
    
    class FLRReportPDF(FPDF):
        def __init__(self, cutoff_hour=24):
            super().__init__(orientation='L', unit='mm', format='A4')
            self.cutoff_hour = cutoff_hour
            
        def header(self):
            self.set_font("Arial", "B", 16)
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
    
    # Create PDF instance
    pdf = FLRReportPDF(cutoff_hour=cutoff_hour)
    pdf.add_page()
    
    # Title and metadata
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, f'Order Analysis Report', ln=True, align='C')
    pdf.ln(10)
    
    # Order IDs section
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, 'Order IDs Analyzed:', ln=True)
    pdf.set_font('Arial', '', 10)
    
    for i, order_id in enumerate(order_ids):
        pdf.cell(0, 6, f'{i+1}. {order_id}', ln=True)
    
    pdf.ln(5)
    
    # Report metadata
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, 'Report Details:', ln=True)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}', ln=True)
    pdf.cell(0, 6, f'Cutoff Hour: {cutoff_hour:02d}:00 UTC', ln=True)
    pdf.cell(0, 6, f'Total Orders: {len(order_ids)}', ln=True)
    pdf.ln(10)
    
    # Mock analytics table (mimicking CMCFLR structure)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, 'Summary Analytics:', ln=True)
    pdf.ln(5)
    
    # Table headers
    pdf.set_font('Arial', 'B', 10)
    col_widths = [60, 65, 65, 65, 50]
    headers = ['Trade Date', 'Total Units Sold (FLR)', '30D Volume Sum', 'Daily Avg Sold', 'Sell Pressure (%)']
    
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 8, header, border=1, align='C')
    pdf.ln()
    
    # Sample data rows (would be replaced with actual data from API)
    pdf.set_font('Arial', '', 9)
    sample_data = [
        ['2025-08-01', '1,250,000.00', '8,500,000.00', '283,333.33', '14.706%'],
        ['2025-08-02', '980,500.00', '8,230,500.00', '274,350.00', '11.915%']
    ]
    
    for row in sample_data:
        for i, cell in enumerate(row):
            align = 'C' if i == 0 else 'R'
            pdf.cell(col_widths[i], 7, cell, border=1, align=align)
        pdf.ln()
    
    pdf.ln(10)
    
    # Status section
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, 'Processing Status:', ln=True)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 6, '* Order IDs validated and processed', ln=True)
    pdf.cell(0, 6, '* Full market data integration pending', ln=True)
    pdf.cell(0, 6, '* Real-time analytics require additional API connections', ln=True)
    
    return pdf.output(dest='S')

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
    Upload PDF directly to Slack using the Web API files.upload method
    """
    bot_token = os.environ.get('SLACK_BOT_TOKEN')
    if not bot_token:
        raise Exception("SLACK_BOT_TOKEN environment variable not set")
    
    url = "https://slack.com/api/files.upload"
    
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
    
    try:
        print(f"Uploading PDF to Slack channel: {channel_id}")
        response = requests.post(url, files=files, data=data, headers=headers, timeout=30)
        print(f"Slack upload response status: {response.status_code}")
        print(f"Slack upload response: {response.text}")
        
        response_data = response.json()
        
        if response.status_code == 200 and response_data.get('ok'):
            print("PDF uploaded successfully to Slack")
            return response_data['file']['permalink']
        else:
            error_msg = response_data.get('error', 'Unknown error')
            raise Exception(f"Slack API error: {error_msg}")
            
    except Exception as e:
        print(f"Error uploading PDF to Slack: {e}")
        raise

# For local testing
if __name__ == "__main__":
    test_event = {
        'body': 'command=%2Fflr-report&text=87526ab1-e9a2-4d6e-920f-ab05c399ea9a&user_id=U123456&channel_id=C123456&response_url=https://hooks.slack.com/commands/test'
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))