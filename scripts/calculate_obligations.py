#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.mission import Mission
from scripts.core.processors import ObligationsCalculator


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
            obligations_df.to_csv(output_file, index=False)
            print(f"  Found {len(obligations_df)} funding records -> {output_file}")
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