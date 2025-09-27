#!/usr/bin/env python3

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from casefy import snakecase
from scripts.core.mission import Mission
from scripts.core.renderer import JSONGenerator


def main():
    parser = argparse.ArgumentParser(
        description="Generate JSON data files for NASA missions"
    )
    parser.add_argument(
        'path',
        type=Path,
        help='Path to mission YAML file or directory containing mission files'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('site'),
        help='Output directory for generated JSON files (default: site)'
    )
    parser.add_argument(
        '--spending-dir',
        type=Path,
        default=Path('data/spending'),
        help='Directory containing spending-related CSV files (default: data/spending)'
    )
    
    args = parser.parse_args()

    # Create JSON generator
    generator = JSONGenerator()
    
    # Process missions
    missions = []
    if args.path.is_file():
        try:
            missions.append(Mission(args.path))
        except Exception as e:
            print(f"Error loading mission from {args.path}: {e}")
            sys.exit(1)
    elif args.path.is_dir():
        yaml_files = list(args.path.glob('*.yaml')) + list(args.path.glob('*.yml'))
        print(f"Found {len(yaml_files)} mission files...")
        
        for yaml_file in yaml_files:
            try:
                missions.append(Mission(yaml_file))
            except Exception as e:
                print(f"Warning: Could not load {yaml_file}: {e}")
    else:
        print(f"Error: {args.path} is not a valid file or directory")
        sys.exit(1)
    
    if not missions:
        print("No valid missions found to process")
        sys.exit(1)
    
    # Create output data directory if it doesn't exist
    data_dir = args.output_dir / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)

    # Generate JSON files for missions
    generated_count = 0
    csv_copied_count = 0

    for mission in missions:
        try:
            generator.generate_mission_json(mission, args.spending_dir, args.output_dir)
            generated_count += 1

            # Copy summary CSV files if they exist
            mission_snake = snakecase(mission.acronym)

            # Copy obligations summary CSV
            obligations_summary_csv = args.spending_dir / f"{mission_snake}_obligations_summary.csv"
            if obligations_summary_csv.exists():
                dest_path = data_dir / f"{mission_snake}_obligations_summary.csv"
                shutil.copy2(obligations_summary_csv, dest_path)
                print(f"  Copied obligations summary CSV for {mission.acronym}")
                csv_copied_count += 1

            # Copy outlays summary CSV
            outlays_summary_csv = args.spending_dir / f"{mission_snake}_outlays_summary.csv"
            if outlays_summary_csv.exists():
                dest_path = data_dir / f"{mission_snake}_outlays_summary.csv"
                shutil.copy2(outlays_summary_csv, dest_path)
                print(f"  Copied outlays summary CSV for {mission.acronym}")
                csv_copied_count += 1

        except Exception as e:
            print(f"Error generating JSON for {mission.name}: {e}")

    print(f"\nJSON generation complete!")
    print(f"Generated {generated_count} JSON files from {len(missions)} total missions")
    print(f"Copied {csv_copied_count} summary CSV files")
    print(f"Output directory: {args.output_dir / 'data'}")


if __name__ == "__main__":
    main()