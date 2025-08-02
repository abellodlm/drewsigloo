import pandas as pd
from fpdf import FPDF

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

        self.set_text_color(0)  # Reset for any future content

    def table(self, dataframe):
        self.set_font("Arial", "B", 11)
        col_widths = [60, 85, 85, 85, 70]
        row_height = 12

        # Header
        for i, col in enumerate(dataframe.columns):
            self.cell(col_widths[i], row_height, col, border=1, align="C")
        self.ln()

        # Rows
        self.set_font("Arial", "", 11)
        for _, row in dataframe.iterrows():
            self.cell(col_widths[0], row_height, row.iloc[0].strftime("%d/%m/%Y"), border=1, align="C")
            self.cell(col_widths[1], row_height, f'{row.iloc[1]:,.2f}', border=1, align="R")
            self.cell(col_widths[2], row_height, f'{row.iloc[2]:,.2f}', border=1, align="R")
            self.cell(col_widths[3], row_height, f'{row.iloc[3]:,.2f}', border=1, align="R")
            self.cell(col_widths[4], row_height, f'{row.iloc[4]*100:.3f}%', border=1, align="R")
            self.ln()

def generate_pdf_report(csv_file="daily_summary_enriched.csv", output_pdf="summary_report.pdf", cutoff_hour=16):
    df = pd.read_csv(csv_file, parse_dates=["Date"])

    # Filter and rename columns
    df = df[["Date", "Total Quantity", "30D Volume Sum", "30D Avg Daily Sell", "Sell Pressure Ratio"]].copy()
    df.columns = [
        "Trade Date",
        "Total Units Sold by Pantera (FLR)",
        "Total Units sold over 30 day period",
        "Daily Average Units Sold",
        "(%) Units Sold"
    ]

    pdf = PDF(cutoff_hour=cutoff_hour, orientation='L', unit='mm', format='A3')
    pdf.add_page()
    pdf.table(df)
    pdf.output(output_pdf)

    print(f"PDF report saved to {output_pdf}")

if __name__ == "__main__":
    generate_pdf_report(cutoff_hour=24)