#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.mission import Mission
from scripts.core.processors import ObligationsCalculator


def fiscal_month_to_abbr(fiscal_month):
    """Convert fiscal month number (1-12) to calendar month abbreviation.

    Fiscal year starts in October: 1=Oct, 2=Oct/Nov, ..., 12=Sep
    Special case: fiscal month 2 shows as Oct/Nov since USA Spending
    doesn't report October data separately, combining it with November.
    """
    if not fiscal_month or fiscal_month < 1 or fiscal_month > 12:
        return ""

    # Direct mapping for fiscal months to display labels
    # Fiscal month 2 is special case showing Oct/Nov combined data
    fiscal_month_abbrs = {
        1: 'Oct',
        2: 'Oct/Nov',
        3: 'Dec',
        4: 'Jan',
        5: 'Feb',
        6: 'Mar',
        7: 'Apr',
        8: 'May',
        9: 'Jun',
        10: 'Jul',
        11: 'Aug',
        12: 'Sep'
    }

    return fiscal_month_abbrs.get(fiscal_month, "")


def create_summary_dataframe(obligations_df):
    """Create summary DataFrame with aggregated and cumulative data for charts"""
    import pandas as pd

    # Convert transaction_obligated_amount to float to handle Decimal types
    obligations_df = obligations_df.copy()
    obligations_df['transaction_obligated_amount'] = pd.to_numeric(obligations_df['transaction_obligated_amount'], errors='coerce')

    # Group by fiscal year and month, sum transaction obligations
    summary_data = obligations_df.groupby(['reporting_fiscal_year', 'reporting_fiscal_month']).agg({
        'transaction_obligated_amount': 'sum'
    }).reset_index()

    # Add fiscal month abbreviation
    summary_data['fiscal_month_abbr'] = summary_data['reporting_fiscal_month'].apply(fiscal_month_to_abbr)

    # Sort by fiscal year (descending) and fiscal month (ascending) to match chart ordering
    summary_data = summary_data.sort_values(['reporting_fiscal_year', 'reporting_fiscal_month'], ascending=[False, True])

    # Calculate cumulative sum within each fiscal year
    summary_data['cumulative_obligations'] = summary_data.groupby('reporting_fiscal_year')['transaction_obligated_amount'].cumsum()

    # Round all calculated values to 2 decimal places
    summary_data['transaction_obligated_amount'] = summary_data['transaction_obligated_amount'].round(2)
    summary_data['cumulative_obligations'] = summary_data['cumulative_obligations'].round(2)

    # Reorder columns for clarity
    summary_data = summary_data[['reporting_fiscal_year', 'reporting_fiscal_month', 'fiscal_month_abbr', 'transaction_obligated_amount', 'cumulative_obligations']]

    return summary_data


def process_mission(mission_path: Path, calculator: ObligationsCalculator, output_dir: Path) -> None:
    """Process a single mission file and save obligations data"""
    try:
        mission = Mission(mission_path)
        print(f"Processing {mission.name}...")
        
        # Calculate obligations
        obligations_df = calculator.calculate(mission)
        
        if not obligations_df.empty:
            # Create filename from mission short name
            from casefy import snakecase
            filename = f"{snakecase(mission.acronym)}_obligations.csv"
            output_file = output_dir / filename

            # Save individual mission obligations
            obligations_df.to_csv(output_file, index=False, line_terminator="\n")
            print(f"  Found {len(obligations_df)} funding records -> {output_file}")

            # Generate and save summary CSV for chart data
            summary_df = create_summary_dataframe(obligations_df)
            summary_filename = f"{snakecase(mission.acronym)}_obligations_summary.csv"
            summary_file = output_dir / summary_filename
            summary_df.to_csv(summary_file, index=False, line_terminator="\n")
            print(f"  Generated summary with {len(summary_df)} aggregated records -> {summary_file}")
        else:
            print(f"  No funding data found")
        
    except Exception as e:
        print(f"Error processing {mission_path}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Calculate obligations for NASA missions using USAspending data"
    )
    parser.add_argument(
        'path',
        type=Path,
        help='Path to mission YAML file or directory containing mission files'
    )
    parser.add_argument(
        '--force-reload',
        action='store_true',
        help='Force re-download of fresh data, ignoring cached files'
    )
    
    args = parser.parse_args()
    
    # Create calculator instance
    calculator = ObligationsCalculator(force_reload=args.force_reload)
    
    # Determine the base directory for missions
    if args.path.is_file():
        missions_base_dir = args.path.parent
    elif args.path.is_dir():
        missions_base_dir = args.path
    else:
        print(f"Error: {args.path} is not a valid file or directory")
        sys.exit(1)
    
    # Create spending directory
    output_dir = missions_base_dir / '..' / 'spending'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process missions
    processed_count = 0
    if args.path.is_file():
        process_mission(args.path, calculator, output_dir)
        processed_count = 1
    elif args.path.is_dir():
        yaml_files = list(args.path.glob('*.yaml')) + list(args.path.glob('*.yml'))
        print(f"Found {len(yaml_files)} mission files...\n")
        
        for mission_file in yaml_files:
            process_mission(mission_file, calculator, output_dir)
        processed_count = len(yaml_files)
    
    print(f"\nProcessed {processed_count} mission files. Output saved to {output_dir}/")


if __name__ == "__main__":
    main()
