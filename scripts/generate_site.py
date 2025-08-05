#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.mission import Mission
from scripts.core.renderer import SiteGenerator


def main():
    parser = argparse.ArgumentParser(
        description="Generate static site for NASA missions"
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
        help='Output directory for generated site (default: site)'
    )
    parser.add_argument(
        '--outlays-dir',
        type=Path,
        default=Path('data/outlays'),
        help='Directory containing outlays CSV files (default: data/outlays)'
    )
    
    args = parser.parse_args()
    
    # Set up paths
    templates_dir = Path(__file__).parent.parent / 'templates'
    
    if not templates_dir.exists():
        print(f"Error: Templates directory not found at {templates_dir}")
        sys.exit(1)
    
    # Create generator
    generator = SiteGenerator(templates_dir)
    
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
    
    # Generate individual mission pages
    missions_output_dir = args.output_dir / 'missions'
    generated_count = 0
    
    for mission in missions:
        try:
            generator.generate_mission_site(mission, args.outlays_dir, missions_output_dir)
            generated_count += 1
        except Exception as e:
            print(f"Error generating site for {mission.name}: {e}")
    
    # Generate index page
    try:
        index_html = generator.render_index_page(missions)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        
        index_path = args.output_dir / 'index.html'
        with open(index_path, 'w') as f:
            f.write(index_html)
        
        print(f"Generated index page -> {index_path}")
        
    except Exception as e:
        print(f"Error generating index page: {e}")
    
    print(f"\nSite generation complete!")
    print(f"Generated {generated_count} mission pages from {len(missions)} total missions")
    print(f"Output directory: {args.output_dir}")


if __name__ == "__main__":
    main()