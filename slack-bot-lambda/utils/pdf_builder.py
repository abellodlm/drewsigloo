"""
PDF generation for P&L reports using reportlab
Exactly matching WeeklyDeskPnL/report.py styling
"""
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from datetime import datetime
import tempfile
import os

def generate_pdf_report(metrics: dict, date_range: str, chart_paths: dict):
    """
    Generate PDF report exactly like WeeklyDeskPnL/report.py
    
    Args:
        metrics (dict): Metrics dictionary from calculations.py
        date_range (str): Date range string (e.g., "26/7/2025 - 1/8/2025")
        chart_paths (dict): Dictionary with chart file paths
        
    Returns:
        bytes: PDF content as bytes
    """
    try:
        # Create temporary file for PDF
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', prefix='hex_trust_trading_summary_')
        temp_file.close()
        
        # Replace slashes or unsafe characters in filename (exactly like report.py)
        safe_date_range = date_range.replace("/", "-")
        
        c = canvas.Canvas(temp_file.name, pagesize=landscape(A4))
        width, height = landscape(A4)
        
        # Assets paths
        background = "/var/task/assets/gradient_background.png"
        logo = "/var/task/assets/logo_hextrust.png"
        
        # === Page 1 === (exactly like report.py)
        # Draw background image (cover entire page)
        if os.path.exists(background):
            c.drawImage(background, 0, 0, width=width, height=height, mask='auto')

        # Draw logo
        if os.path.exists(logo):
            c.drawImage(logo, width - 2.5 * inch, height - 1.2 * inch,
                    width=1.8 * inch, preserveAspectRatio=True, mask='auto')

        c.setFont("Helvetica-Bold", 20)
        c.setFillColorRGB(1, 1, 1)  # White font for title
        c.drawCentredString(width / 2, height - 0.8 * inch, "TRADING DESK WEEKLY SUMMARY")
        c.setFont("Helvetica", 14)
        c.drawCentredString(width / 2, height - 1.2 * inch, f"Date Range: {date_range}")
        c.setFillColorRGB(1, 1, 1)  # White font for metrics

        # Centered Charts (exactly like report.py)
        chart_width = 4.5 * inch
        chart_height = 3.0 * inch
        left_chart_x = (width / 2) - chart_width - (0.25 * inch)
        right_chart_x = (width / 2) + (0.25 * inch)
        chart_y = height - 4.8 * inch
        
        # Draw charts if they exist
        if chart_paths.get('cumulative_daily_pnl') and os.path.exists(chart_paths['cumulative_daily_pnl']):
            c.drawImage(chart_paths['cumulative_daily_pnl'], left_chart_x, chart_y, 
                       width=chart_width, height=chart_height, preserveAspectRatio=True)
        
        if chart_paths.get('weekly_pnl_volume') and os.path.exists(chart_paths['weekly_pnl_volume']):
            c.drawImage(chart_paths['weekly_pnl_volume'], right_chart_x, chart_y, 
                       width=chart_width, height=chart_height, preserveAspectRatio=True)

        # Centered Metrics as Two Tables Side by Side (white font) (exactly like report.py)
        c.setFont("Helvetica-Bold", 12)
        items = list(metrics.items())
        half = (len(items) + 1) // 2
        left_items = items[:half]
        right_items = items[half:]
        # Align metrics tables with the images above
        table_width = 4.5 * inch  # Match chart width
        left_x = left_chart_x
        right_x = right_chart_x
        start_y = height - 5.2 * inch
        row_height = 0.45 * inch
        for i, (label, value) in enumerate(left_items):
            y = start_y - i * row_height
            c.setFont("Helvetica", 13)
            c.setFillColorRGB(1, 1, 1)
            c.drawString(left_x, y, label)
            c.setFont("Helvetica-Bold", 15)
            c.setFillColorRGB(1, 1, 1)
            c.drawString(left_x + 2.8 * inch, y, value)  # Adjusted for new width
        for i, (label, value) in enumerate(right_items):
            y = start_y - i * row_height
            c.setFont("Helvetica", 13)
            c.setFillColorRGB(1, 1, 1)
            c.drawString(right_x, y, label)
            c.setFont("Helvetica-Bold", 15)
            c.setFillColorRGB(1, 1, 1)
            c.drawString(right_x + 2.8 * inch, y, value)  # Adjusted for new width

        c.setFillColorRGB(0, 0, 0)  # Reset to black for next page
        c.showPage()

        # === Page 2 === (exactly like report.py)
        if os.path.exists(background):
            c.drawImage(background, 0, 0, width=width, height=height)
        if os.path.exists(logo):
            c.drawImage(logo, width - 2.5 * inch, height - 1.2 * inch,
                        width=1.8 * inch, preserveAspectRatio=True, mask='auto')

        c.setFont("Helvetica-Bold", 18)
        c.setFillColorRGB(1, 1, 1)
        c.drawCentredString(width / 2, height - 0.8 * inch, "Top 10 Clients and Tokens by PnL and Volume")

        # === 2x3 Grid Layout (columns left-right, rows top-bottom) === (exactly like report.py)
        img_width = 3.97 * inch
        img_height = 2.6 * inch
        cols = 3
        rows = 2

        col_gap = (width - cols * img_width) / (cols + 1)
        row_gap = 0.6 * inch
        top_y = height - 1.3 * inch

        chart_files = [
            chart_paths.get('top10_clients_pnl'),
            chart_paths.get('token_pnl_pie'),
            chart_paths.get('client_pnl_pie'),
            chart_paths.get('top10_tokens_pnl'),
            chart_paths.get('token_volume_pie'),
            chart_paths.get('client_volume_pie'),
        ]

        for i, img_path in enumerate(chart_files):
            if img_path and os.path.exists(img_path):
                row = i // cols
                col = i % cols
                x = col_gap + col * (img_width + col_gap)
                y = top_y - row * (img_height + row_gap) - img_height
                c.drawImage(img_path, x, y, width=img_width, height=img_height, preserveAspectRatio=True)

        c.save()

        # Read PDF content
        with open(temp_file.name, 'rb') as f:
            pdf_content = f.read()
        
        # Clean up temporary file
        os.unlink(temp_file.name)
        
        print("✅ PDF report generated successfully")
        return pdf_content
        
    except Exception as e:
        print(f"Error creating PDF: {e}")
        # Clean up temp file if it exists
        if 'temp_file' in locals() and os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
        raise

# PDF generation complete - exactly matching WeeklyDeskPnL/report.py