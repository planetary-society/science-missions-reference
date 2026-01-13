#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.mission import Mission
from scripts.core.processors import OutlaysCalculator


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


def create_summary_dataframe(outlays_df):
    """Create summary DataFrame with aggregated and cumulative data for charts"""
    import pandas as pd

    # Group by fiscal year and period, sum monthly outlays
    summary_data = outlays_df.groupby(['fiscal_year', 'fiscal_period']).agg({
        'monthly_outlay': 'sum'
    }).reset_index()

    # Add fiscal period abbreviation
    summary_data['fiscal_period_abbr'] = summary_data['fiscal_period'].apply(fiscal_month_to_abbr)

    # Sort by fiscal year (descending) and fiscal period (ascending) to match chart ordering
    summary_data = summary_data.sort_values(['fiscal_year', 'fiscal_period'], ascending=[False, True])

    # Calculate cumulative sum within each fiscal year
    summary_data['cumulative_outlay'] = summary_data.groupby('fiscal_year')['monthly_outlay'].cumsum()

    # Round all calculated values to 2 decimal places
    summary_data['monthly_outlay'] = summary_data['monthly_outlay'].round(2)
    summary_data['cumulative_outlay'] = summary_data['cumulative_outlay'].round(2)

    # Reorder columns for clarity
    summary_data = summary_data[['fiscal_year', 'fiscal_period', 'fiscal_period_abbr', 'monthly_outlay', 'cumulative_outlay']]

    return summary_data


def process_mission(mission_path: Path, calculator: OutlaysCalculator, output_dir: Path) -> None:
    """Process a single mission file and save outlays data"""
    try:
        mission = Mission(mission_path)
        print(f"Processing {mission.name}...")
        
        # Calculate outlays
        outlays_df = calculator.calculate(mission)
        
        if not outlays_df.empty:
            # Create filename from mission short name
            from casefy import snakecase
            filename = f"{snakecase(mission.acronym)}_outlays.csv"
            output_file = output_dir / filename

            # Save individual mission outlays
            outlays_df.to_csv(output_file, index=False, line_terminator="\n")
            print(f"  Found {len(outlays_df)} monthly outlay records -> {output_file}")

            # Generate and save summary CSV for chart data
            summary_df = create_summary_dataframe(outlays_df)
            summary_filename = f"{snakecase(mission.acronym)}_outlays_summary.csv"
            summary_file = output_dir / summary_filename
            summary_df.to_csv(summary_file, index=False, line_terminator="\n")
            print(f"  Generated summary with {len(summary_df)} aggregated records -> {summary_file}")
        else:
            print(f"  No outlay data found")
        
    except Exception as e:
        print(f"Error processing {mission_path}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Calculate outlays for NASA missions using USAspending data"
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
    calculator = OutlaysCalculator(force_reload=args.force_reload)
    
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
