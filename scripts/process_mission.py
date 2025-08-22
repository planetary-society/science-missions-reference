#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from casefy import kebabcase, snakecase

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.mission import Mission
from scripts.core.processors import ObligationsCalculator, OutlaysCalculator
from scripts.core.renderer import SiteGenerator
from scripts.ingest_data import MissionImporter


class MissionProcessor:
    """Unified processor for mission data pipeline"""
    
    def __init__(self, data_dir: Path, verbose: bool = False):
        self.data_dir = data_dir
        self.missions_dir = data_dir / "missions"
        self.spending_dir = data_dir / "spending"
        self.site_dir = Path("site")
        self.templates_dir = Path(__file__).parent.parent / "templates"
        self.verbose = verbose
        
        # Initialize components
        self.importer = MissionImporter(data_dir)
        self.obligations_calc = ObligationsCalculator()
        self.outlays_calc = OutlaysCalculator()
        self.site_generator = SiteGenerator(self.templates_dir)
        
        # Track results
        self.results = {
            'import': None,
            'obligations': None,
            'outlays': None,
            'site': None
        }
    
    def _log(self, message: str, level: str = "INFO"):
        """Log message with optional verbosity"""
        if level == "ERROR" or level == "SUCCESS" or self.verbose:
            prefix = {
                "INFO": "ℹ️ ",
                "SUCCESS": "✅",
                "ERROR": "❌",
                "WARNING": "⚠️ "
            }.get(level, "")
            print(f"{prefix} {message}")
    
    def import_mission(self, mission_name: str, force_overwrite: bool = False) -> Optional[Mission]:
        """Import or update mission data"""
        self._log(f"Importing mission: {mission_name}", "INFO")
        
        try:
            # Import mission data
            mission_data = self.importer.import_mission(mission_name)
            
            yaml_filename = kebabcase(mission_data.canonical_short_name) + ".yaml"
            yaml_path = self.missions_dir / yaml_filename
            
            # Check if YAML exists and merge if not forcing overwrite
            if yaml_path.exists() and not force_overwrite:
                self._log("Existing YAML found, merging with new data...", "INFO")
                
                # Load existing mission
                existing_mission = Mission(yaml_path)
                existing_mission.load()
                existing_raw_data = existing_mission._raw_data
                
                # Convert mission_data to dict
                new_data_dict = mission_data.model_dump(mode='json')
                
                # Convert HttpUrl objects to strings
                for key, value in new_data_dict.items():
                    if value and isinstance(value, str) and value.startswith('http'):
                        new_data_dict[key] = str(value)
                
                # Merge preserving existing fields
                merged_data = self.importer.merge_mission_data(existing_raw_data, new_data_dict)
                
                # Update and save
                existing_mission._raw_data = merged_data
                with open(yaml_path, 'w') as f:
                    existing_mission._yaml.dump(merged_data, f)
                
                self._log(f"Successfully updated mission: {mission_data.canonical_full_name}", "SUCCESS")
                self.results['import'] = 'updated'
                return existing_mission
            else:
                # New file or force overwrite
                if force_overwrite:
                    self._log("Force overwrite mode - replacing entire YAML file...", "INFO")
                
                mission = Mission.from_dict(mission_data.model_dump(), yaml_path)
                mission.save()
                
                self._log(f"Successfully imported mission: {mission_data.canonical_full_name}", "SUCCESS")
                self.results['import'] = 'created'
                return mission
                
        except Exception as e:
            self._log(f"Failed to import mission: {e}", "ERROR")
            self.results['import'] = f'failed: {e}'
            return None
    
    def calculate_obligations(self, mission: Mission) -> bool:
        """Calculate obligations for the mission"""
        self._log(f"Calculating obligations for {mission.name}...", "INFO")
        
        try:
            obligations_df = self.obligations_calc.calculate(mission)
            
            if not obligations_df.empty:
                filename = f"{snakecase(mission.acronym)}_obligations.csv"
                output_file = self.spending_dir / filename
                
                # Ensure spending directory exists
                self.spending_dir.mkdir(parents=True, exist_ok=True)
                
                obligations_df.to_csv(output_file, index=False)
                self._log(f"Found {len(obligations_df)} funding records -> {output_file}", "SUCCESS")
                self.results['obligations'] = f'{len(obligations_df)} records'
                return True
            else:
                self._log("No obligations data found", "WARNING")
                self.results['obligations'] = 'no data'
                return True
                
        except Exception as e:
            self._log(f"Failed to calculate obligations: {e}", "ERROR")
            self.results['obligations'] = f'failed: {e}'
            return False
    
    def calculate_outlays(self, mission: Mission) -> bool:
        """Calculate outlays for the mission"""
        self._log(f"Calculating outlays for {mission.name}...", "INFO")
        
        try:
            outlays_df = self.outlays_calc.calculate(mission)
            
            if not outlays_df.empty:
                filename = f"{snakecase(mission.acronym)}_outlays.csv"
                output_file = self.spending_dir / filename
                
                # Ensure spending directory exists
                self.spending_dir.mkdir(parents=True, exist_ok=True)
                
                outlays_df.to_csv(output_file, index=False)
                self._log(f"Found {len(outlays_df)} monthly outlay records -> {output_file}", "SUCCESS")
                self.results['outlays'] = f'{len(outlays_df)} records'
                return True
            else:
                self._log("No outlays data found", "WARNING")
                self.results['outlays'] = 'no data'
                return True
                
        except Exception as e:
            self._log(f"Failed to calculate outlays: {e}", "ERROR")
            self.results['outlays'] = f'failed: {e}'
            return False
    
    def generate_site(self, mission: Mission) -> bool:
        """Generate site for the mission"""
        self._log(f"Generating site for {mission.name}...", "INFO")
        
        try:
            missions_output_dir = self.site_dir / 'missions'
            self.site_generator.generate_mission_site(mission, self.spending_dir, missions_output_dir)
            
            self._log(f"Generated site -> {missions_output_dir / kebabcase(mission.acronym)}", "SUCCESS")
            self.results['site'] = 'generated'
            return True
            
        except Exception as e:
            self._log(f"Failed to generate site: {e}", "ERROR")
            self.results['site'] = f'failed: {e}'
            return False
    
    def process(self, mission_name: str, 
                skip_import: bool = False,
                skip_spending: bool = False,
                force_overwrite: bool = False) -> Dict[str, Any]:
        """Process complete pipeline for a mission"""
        
        print(f"\n{'='*60}")
        print(f"Processing Mission: {mission_name}")
        print(f"{'='*60}\n")
        
        mission = None
        
        # Step 1: Import/Load mission
        if not skip_import:
            mission = self.import_mission(mission_name, force_overwrite)
            if not mission:
                # Try to load existing if import failed
                self._log("Import failed, attempting to load existing mission...", "WARNING")
                try:
                    # Find mission file
                    for yaml_file in self.missions_dir.glob("*.yaml"):
                        test_mission = Mission(yaml_file)
                        if test_mission.data.canonical_short_name.lower() == mission_name.lower():
                            mission = test_mission
                            self._log(f"Loaded existing mission from {yaml_file}", "SUCCESS")
                            break
                except Exception as e:
                    self._log(f"Could not load existing mission: {e}", "ERROR")
        else:
            # Load existing mission
            self._log("Skipping import, loading existing mission...", "INFO")
            try:
                # Find mission file
                found = False
                for yaml_file in self.missions_dir.glob("*.yaml"):
                    test_mission = Mission(yaml_file)
                    if test_mission.data.canonical_short_name.lower() == mission_name.lower():
                        mission = test_mission
                        self._log(f"Loaded existing mission from {yaml_file}", "SUCCESS")
                        self.results['import'] = 'skipped'
                        found = True
                        break
                
                if not found:
                    self._log(f"Mission '{mission_name}' not found in {self.missions_dir}", "ERROR")
                    
            except Exception as e:
                self._log(f"Could not load mission: {e}", "ERROR")
        
        if not mission:
            self._log("Cannot proceed without mission data", "ERROR")
            return self.results
        
        # Step 2 & 3: Calculate spending (if not skipped)
        if not skip_spending:
            self.calculate_obligations(mission)
            self.calculate_outlays(mission)
        else:
            self._log("Skipping spending calculations", "INFO")
            self.results['obligations'] = 'skipped'
            self.results['outlays'] = 'skipped'
        
        # Step 4: Generate site (always runs)
        self.generate_site(mission)
        
        # Print summary
        print(f"\n{'='*60}")
        print("Processing Summary:")
        print(f"{'='*60}")
        for step, result in self.results.items():
            status_icon = "✅" if result and not str(result).startswith('failed') else "❌"
            if result and str(result).startswith('skipped'):
                status_icon = "⏭️ "
            print(f"  {step.capitalize():15} {status_icon} {result or 'not run'}")
        print(f"{'='*60}\n")
        
        return self.results


def main():
    parser = argparse.ArgumentParser(
        description="Unified mission processing pipeline: import, calculate spending, and generate site"
    )
    parser.add_argument(
        "--mission",
        required=True,
        help="Name of the mission to process (matches 'Short Title' in source data)"
    )
    parser.add_argument(
        "--skip-import",
        action="store_true",
        help="Skip import step and use existing YAML data"
    )
    parser.add_argument(
        "--skip-spending",
        action="store_true",
        help="Skip obligations and outlays calculations"
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Force overwrite existing YAML during import (loses manual edits)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    # Set up paths
    data_dir = Path(__file__).parent.parent / "data"
    
    # Create processor and run
    processor = MissionProcessor(data_dir, verbose=args.verbose)
    
    results = processor.process(
        mission_name=args.mission,
        skip_import=args.skip_import,
        skip_spending=args.skip_spending,
        force_overwrite=args.force_overwrite
    )
    
    # Exit with error if any step failed
    if any(str(r).startswith('failed') for r in results.values() if r):
        sys.exit(1)


if __name__ == "__main__":
    main()