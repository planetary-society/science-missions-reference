#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

import pandas as pd
from casefy import kebabcase

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.mission import Mission, MissionData
from scripts.core.sources import GoogleSheetsSource, NSSDCACatalogSource


class MissionImporter:
    """Object-oriented mission importer using multiple data sources"""
    
    # Fields managed by GoogleSheetsSource (always updated from CSV)
    GOOGLE_SHEETS_MANAGED_FIELDS = {
        'canonical_full_name', 'canonical_short_name', 'nasa_mission_page_url', 
        'image_url', 'formulation_start_date', 'prime_mission_end_date', 
        'mission_end_date', 'status', 'life_cycle_cost', 'program_line', 
        'division', 'primary_target', 'sponsor_nations', 'launch_date', 'last_updated',
        'wikipedia_url', 'development_start_date'
    }
    
    # Fields managed by NSSDCACatalogSource (only updated if empty in existing)
    NSSDCA_MANAGED_FIELDS = {
        'description', 'alternative_names'
    }
    
    # Spacecraft fields managed by sources
    SPACECRAFT_MANAGED_FIELDS = {
        'name', 'COSPAR_id', 'launch_date', 'mass', 'launch_vehicle', 'spacecraft_type', 'NSSDCA_id'
    }
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.sources = [
            GoogleSheetsSource(data_dir),
            NSSDCACatalogSource(data_dir)
        ]
    
    def import_mission(self, mission_name: str) -> MissionData:
        """Import mission using all sources with precedence"""
        # Start with Google Sheets as primary source
        primary_source = self.sources[0]
        raw_data = primary_source.find(mission_name)
        
        if not raw_data:
            self._print_available_missions(primary_source)
            raise ValueError(f"Mission '{mission_name}' not found")
        
        # Build initial mission data
        mission_dict = primary_source.enrich_mission_data({}, raw_data)
        
        # Enrich with additional sources
        for source in self.sources[1:]:
            enrichment_data = None
            
            # Try to find by COSPAR ID first, then by mission name
            cospar_id = None
            if mission_dict.get('spacecraft'):
                cospar_id = mission_dict['spacecraft'][0].get('COSPAR_id')
            
            if cospar_id:
                enrichment_data = source.find(cospar_id)
            
            if not enrichment_data:
                enrichment_data = source.find(mission_name)
            
            if enrichment_data:
                mission_dict = source.enrich_mission_data(mission_dict, enrichment_data)
                print(f"Enriched from {source.__class__.__name__}")
        
        return MissionData(**mission_dict)
    
    def merge_spacecraft_data(self, existing_spacecraft: list, new_spacecraft: list) -> list:
        """Merge spacecraft data, preserving existing fields not managed by sources"""
        if not existing_spacecraft:
            return new_spacecraft
        
        if not new_spacecraft:
            return existing_spacecraft
        
        merged_spacecraft = []
        
        # Create lookup by COSPAR_id for existing spacecraft
        existing_by_cospar = {}
        for sc in existing_spacecraft:
            cospar_id = sc.get('COSPAR_id')
            if cospar_id:
                existing_by_cospar[cospar_id] = sc
        
        # Process new spacecraft
        for new_sc in new_spacecraft:
            cospar_id = new_sc.get('COSPAR_id')
            
            if cospar_id and cospar_id in existing_by_cospar:
                # Merge with existing spacecraft
                existing_sc = existing_by_cospar[cospar_id].copy()
                
                # Update only source-managed fields
                for field in self.SPACECRAFT_MANAGED_FIELDS:
                    if field in new_sc:
                        existing_sc[field] = new_sc[field]
                
                merged_spacecraft.append(existing_sc)
                # Remove from lookup so we don't add it again
                del existing_by_cospar[cospar_id]
            else:
                # New spacecraft, add as-is
                merged_spacecraft.append(new_sc)
        
        # Add any remaining existing spacecraft that weren't matched
        for remaining_sc in existing_by_cospar.values():
            merged_spacecraft.append(remaining_sc)
        
        return merged_spacecraft
    
    def merge_mission_data(self, existing_data: dict, new_data: dict) -> dict:
        """Merge mission data, preserving existing fields not managed by sources"""
        merged = existing_data.copy()
        
        # Always update Google Sheets managed fields
        for field in self.GOOGLE_SHEETS_MANAGED_FIELDS:
            if field in new_data:
                merged[field] = new_data[field]
        
        # Update NSSDCA fields only if empty/missing in existing
        for field in self.NSSDCA_MANAGED_FIELDS:
            if field in new_data:
                if field == 'description' and not merged.get(field):
                    merged[field] = new_data[field]
                elif field == 'alternative_names':
                    # For alternative names, merge lists avoiding duplicates
                    existing_names = merged.get(field, [])
                    new_names = new_data[field] if new_data[field] else []
                    
                    # Combine and deduplicate
                    all_names = existing_names + [name for name in new_names if name not in existing_names]
                    merged[field] = all_names
        
        # Handle spacecraft data specially
        merged['spacecraft'] = self.merge_spacecraft_data(
            existing_data.get('spacecraft', []), 
            new_data.get('spacecraft', [])
        )
        
        return merged
    
    def _print_available_missions(self, primary_source: GoogleSheetsSource):
        """Print available missions from primary source"""
        if primary_source.df.empty:
            print("\nNo missions available (data not loaded)")
            return
            
        print("\nAvailable missions:")
        for _, row in primary_source.df.iterrows():
            if pd.notna(row['Short Title']) and row['Short Title'].strip():
                print(f"  - {row['Short Title']}")


def main():
    parser = argparse.ArgumentParser(
        description="Import mission data using multiple sources"
    )
    parser.add_argument(
        "--import",
        dest="mission_name",
        required=True,
        help="Name of the mission to import (matches 'Short Title' in primary source)"
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Overwrite entire YAML file instead of preserving existing fields"
    )
    
    args = parser.parse_args()
    
    data_dir = Path(__file__).parent.parent / "data"
    missions_dir = data_dir / "missions"
    missions_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        importer = MissionImporter(data_dir)
        
        # Import new mission data
        mission_data = importer.import_mission(args.mission_name)
        
        yaml_filename = kebabcase(mission_data.canonical_short_name) + ".yaml"
        yaml_path = missions_dir / yaml_filename
        
        # Check if YAML exists and merge if not forcing overwrite
        if yaml_path.exists() and not args.force_overwrite:
            print("Existing YAML found, merging with new data...")
            
            # Load existing mission using Mission class (with proper Pydantic validation)
            existing_mission = Mission(yaml_path)
            existing_mission.load()
            existing_raw_data = existing_mission._raw_data
            
            # Convert mission_data to dict and handle URL serialization
            new_data_dict = mission_data.model_dump(mode='json')
            
            # Convert HttpUrl objects to strings for YAML serialization
            for key, value in new_data_dict.items():
                if value and isinstance(value, str) and value.startswith('http'):
                    new_data_dict[key] = str(value)
            
            # Merge preserving existing fields not managed by sources
            merged_data = importer.merge_mission_data(existing_raw_data, new_data_dict)
            
            # Update the existing mission and save using ruamel.yaml
            existing_mission._raw_data = merged_data
            with open(yaml_path, 'w') as f:
                existing_mission._yaml.dump(merged_data, f)
            
            print(f"Successfully updated mission: {mission_data.canonical_full_name}")
            print("Preserved existing fields while updating source-managed fields")
        else:
            # New file or force overwrite - use standard import
            if args.force_overwrite:
                print("Force overwrite mode - replacing entire YAML file...")
            
            mission = Mission.from_dict(mission_data.model_dump(), yaml_path)
            mission.save()
            
            print(f"\nSuccessfully imported mission: {mission_data.canonical_full_name}")
        
        print(f"Saved to: {yaml_path}")
        print(f"  - Status: {mission_data.status}")
        print(f"  - Spacecraft: {len(mission_data.spacecraft)}")
        if mission_data.life_cycle_cost:
            print(f"  - Cost: ${mission_data.life_cycle_cost:,.0f}")
        
        # Show alternative names if enriched
        if mission_data.alternative_names:
            print(f"  - Alternative names: {', '.join(mission_data.alternative_names)}")
        
    except Exception as e:
        print(f"\nError importing mission: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()