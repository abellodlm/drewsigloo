"""
Google Sheets integration for P&L data retrieval
Based on WeeklyDeskPnL/extract.py and auth.py
"""
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import pandas as pd
import tempfile

def get_google_sheets_client():
    """
    Initialize Google Sheets client using service account credentials from SSM
    """
    try:
        # Get credentials from environment variables (stored in SSM)
        service_account_email = os.environ.get('GOOGLE_SERVICE_ACCOUNT_EMAIL')
        private_key = os.environ.get('GOOGLE_PRIVATE_KEY')
        project_id = os.environ.get('GOOGLE_PROJECT_ID', 'htmdrew')
        private_key_id = os.environ.get('GOOGLE_PRIVATE_KEY_ID', '73d8bc647c51')
        client_id = os.environ.get('GOOGLE_CLIENT_ID', '')
        
        if not service_account_email or not private_key:
            raise Exception("Google service account credentials not found in environment variables")
        
        # Create credentials object
        credentials_dict = {
            "type": "service_account",
            "project_id": project_id,
            "private_key_id": private_key_id,
            "private_key": private_key.replace('\\n', '\n'),
            "client_email": service_account_email,
            "client_id": client_id,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{service_account_email}"
        }
        
        # Define the scope
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # Authorize the client
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
        client = gspread.authorize(credentials)
        
        return client
        
    except Exception as e:
        print(f"Error creating Google Sheets client: {e}")
        raise

def extract_pnl_data(cutoff_date):
    """
    Extract P&L data from Google Sheets following WeeklyDeskPnL/extract.py logic
    
    Args:
        cutoff_date (pd.Timestamp): Cutoff date for data extraction
        
    Returns:
        pd.DataFrame: Cleaned P&L data
    """
    try:
        client = get_google_sheets_client()
        
        # Get the sheet ID from environment (same as WeeklyDeskPnL)
        spreadsheet_id = os.environ.get('GOOGLE_SHEET_ID')
        if not spreadsheet_id:
            raise Exception("GOOGLE_SHEET_ID environment variable not set")
        
        worksheet_name = "P&L Calculation"
        
        # Open spreadsheet and get data (exactly like extract.py)
        sheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
        data = sheet.get("A1:AD")
        
        # Convert to DataFrame
        df = pd.DataFrame(data[1:], columns=data[0])
        df["Client Name"] = df["Client Name"].astype(str).str.strip()
        
        # Filter out blank rows and required columns (exactly like extract.py)
        df = df[
            (df.iloc[:, 0].fillna('').str.strip() != '') &
            (df["Total P&L (USD) "].fillna('').str.strip() != '') &
            (df["Revenue Received from Counterparty (USD)"].fillna('').str.strip() != '')
        ]
        
        # Select relevant columns (exactly like extract.py)
        df = df[[
            "Order ID",
            "Client Name", 
            "Booking Date",
            "Client Leg 1",
            "Total P&L (USD) ",
            "Revenue Received from Counterparty (USD)"
        ]]
        
        # Type conversions (exactly like extract.py)
        df["Order ID"] = pd.to_numeric(df["Order ID"], errors="coerce")
        df["Total P&L (USD) "] = pd.to_numeric(
            df["Total P&L (USD) "].astype(str).str.replace(",", ""), errors="coerce"
        )
        df["Revenue Received from Counterparty (USD)"] = pd.to_numeric(
            df["Revenue Received from Counterparty (USD)"].astype(str).str.replace(",", ""), errors="coerce"
        )
        df["Booking Date"] = pd.to_datetime(df["Booking Date"], format="%d-%b-%Y", errors="coerce")
        
        # Drop rows with bad data
        df.dropna(subset=["Order ID", "Booking Date"], inplace=True)
        
        # Filter by cutoff (exactly like extract.py)
        df = df[df["Booking Date"] <= cutoff_date]
        
        print(f"Extracted {len(df)} P&L records from Google Sheets")
        return df
        
    except Exception as e:
        print(f"Error extracting P&L data: {e}")
        raise

def save_pnl_export(df):
    """
    Save P&L data to temporary CSV file for processing
    """
    try:
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', prefix='WeeklyDeskPnL_Export_')
        df.to_csv(temp_file.name, index=False)
        temp_file.close()
        
        print(f"P&L data saved to: {temp_file.name}")
        return temp_file.name
        
    except Exception as e:
        print(f"Error saving P&L export: {e}")
        raise

def process_pnl_dataframe(df, start_date, end_date):
    """
    Process the raw P&L DataFrame into a structured format for reporting
    
    Args:
        df (DataFrame): Raw P&L data from Google Sheets
        start_date (str): Start date
        end_date (str): End date
        
    Returns:
        dict: Structured P&L data
    """
    try:
        # This is a template structure - adjust based on your actual sheet structure
        pnl_data = {
            'period': {
                'start_date': start_date,
                'end_date': end_date,
                'total_days': len(df) if 'Date' in df.columns else 1
            },
            'summary': {
                'total_pnl': 0,
                'total_revenue': 0,
                'total_costs': 0,
                'daily_average': 0
            },
            'daily_data': [],
            'categories': {},
            'raw_data': df.to_dict('records') if not df.empty else []
        }
        
        # Calculate summary metrics
        # Adjust these column names based on your actual sheet structure
        if not df.empty:
            if 'P&L' in df.columns:
                pnl_data['summary']['total_pnl'] = df['P&L'].sum()
                pnl_data['summary']['daily_average'] = df['P&L'].mean()
            
            if 'Revenue' in df.columns:
                pnl_data['summary']['total_revenue'] = df['Revenue'].sum()
                
            if 'Costs' in df.columns:
                pnl_data['summary']['total_costs'] = df['Costs'].sum()
            
            # Process daily data if Date column exists
            if 'Date' in df.columns:
                for _, row in df.iterrows():
                    daily_entry = {
                        'date': row['Date'].strftime('%Y-%m-%d') if pd.notna(row['Date']) else '',
                        'pnl': row.get('P&L', 0),
                        'revenue': row.get('Revenue', 0),
                        'costs': row.get('Costs', 0)
                    }
                    pnl_data['daily_data'].append(daily_entry)
            
            # Group by categories if category column exists
            category_columns = [col for col in df.columns if 'category' in col.lower() or 'type' in col.lower()]
            if category_columns and 'P&L' in df.columns:
                category_col = category_columns[0]
                category_summary = df.groupby(category_col)['P&L'].sum().to_dict()
                pnl_data['categories'] = category_summary
        
        return pnl_data
        
    except Exception as e:
        print(f"Error processing P&L DataFrame: {e}")
        # Return minimal structure even if processing fails
        return {
            'period': {'start_date': start_date, 'end_date': end_date, 'total_days': 0},
            'summary': {'total_pnl': 0, 'total_revenue': 0, 'total_costs': 0, 'daily_average': 0},
            'daily_data': [],
            'categories': {},
            'raw_data': []
        }

def test_google_sheets_connection():
    """
    Test function to verify Google Sheets connection
    """
    try:
        client = get_google_sheets_client()
        sheet_id = os.environ.get('GOOGLE_SHEET_ID')
        
        if sheet_id:
            spreadsheet = client.open_by_key(sheet_id)
            worksheets = spreadsheet.worksheets()
            print(f"Successfully connected to Google Sheets. Found {len(worksheets)} worksheets:")
            for ws in worksheets:
                print(f"  - {ws.title}")
            return True
        else:
            print("GOOGLE_SHEET_ID not set")
            return False
            
    except Exception as e:
        print(f"Google Sheets connection test failed: {e}")
        return False