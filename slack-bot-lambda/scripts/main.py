from coingecko_flr import get_flr_volume_data
from execution_report import generate_execution_report
from final_calc import enrich_with_sell_pressure
from pdf_report import generate_pdf_report

def main():
    try:
        cutoff_hour = 24  # UTC cutoff hour for data aggregation

        print("Fetching FLR market data...")
        get_flr_volume_data()

        print("\nGenerating execution report...")
        generate_execution_report(
            order_ids=[
                "87526ab1-e9a2-4d6e-920f-ab05c399ea9a"],
            cutoff_hour=cutoff_hour
        )

        print("\nEnriching report with sell pressure...")
        enrich_with_sell_pressure()

        print("\nGenerating PDF summary...")
        generate_pdf_report(cutoff_hour=cutoff_hour)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()

