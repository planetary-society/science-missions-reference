#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.mission import Mission
from scripts.core.processors import OutlaysCalculator


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
            outlays_df.to_csv(output_file, index=False)
            print(f"  Found {len(outlays_df)} funding records -> {output_file}")
        else:
            print(f"  No funding data found")
        
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
    
    args = parser.parse_args()
    
    # Create calculator instance
    calculator = OutlaysCalculator()
    
    # Determine the base directory for missions
    if args.path.is_file():
        missions_base_dir = args.path.parent
    elif args.path.is_dir():
        missions_base_dir = args.path
    else:
        print(f"Error: {args.path} is not a valid file or directory")
        sys.exit(1)
    
    # Create outlays directory
    output_dir = missions_base_dir / '..' / 'outlays'
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