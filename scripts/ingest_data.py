#!/usr/bin/env python3

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

import requests
from casefy import kebabcase

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.core.mission import Mission, MissionData, Spacecraft, MissionStatus


GOOGLE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1ag7otfTfElrFz-yRZEdp-sLxlwkS_p7gRvnD1tVo7fE/export?format=csv"
CSV_FILENAME = "us_space_science_missions.csv"


def download_csv(data_dir: Path) -> Path:
    csv_path = data_dir / CSV_FILENAME
    
    print(f"Downloading CSV from Google Sheets...")
    response = requests.get(GOOGLE_SHEETS_URL)
    response.raise_for_status()
    
    with open(csv_path, 'w', encoding='utf-8') as f:
        f.write(response.text)
    
    print(f"CSV downloaded to {csv_path}")
    return csv_path


def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str or date_str.strip() == '':
        return None
    
    try:
        return datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
    except ValueError:
        try:
            return datetime.strptime(date_str.strip(), '%m/%d/%Y').date()
        except ValueError:
            print(f"Warning: Could not parse date '{date_str}'")
            return None


def parse_cost(cost_str: str) -> Optional[float]:
    if not cost_str or cost_str.strip() == '':
        return None
    
    clean_str = re.sub(r'[^0-9.-]', '', cost_str)
    
    if not clean_str:
        return None
    
    try:
        cost_millions = float(clean_str)
        return cost_millions * 1_000_000
    except ValueError:
        print(f"Warning: Could not parse cost '{cost_str}'")
        return None


def parse_mass(mass_str: str) -> Optional[int]:
    if not mass_str or mass_str.strip() == '':
        return None
    
    clean_str = re.sub(r'[^0-9.]', '', mass_str)
    
    if not clean_str:
        return None
    
    try:
        return int(float(clean_str))
    except ValueError:
        print(f"Warning: Could not parse mass '{mass_str}'")
        return None


def parse_spacecraft_count(count_str: str) -> int:
    if not count_str or count_str.strip() == '':
        return 1
    
    try:
        return int(count_str.strip())
    except ValueError:
        return 1


def determine_status(launch_date: Optional[datetime], end_date: Optional[datetime]) -> MissionStatus:
    if end_date and end_date < datetime.now().date():
        return MissionStatus.COMPLETED
    elif not launch_date:
        return MissionStatus.DEVELOPMENT
    else:
        return MissionStatus.UNKNOWN


def create_mission_from_row(row: Dict[str, str]) -> MissionData:
    canonical_full_name = row['Full Name'].strip()
    canonical_short_name = row['Short Title'].strip()
    
    launch_date = parse_date(row['Mission Launch Date'])
    primary_mission_end_date = parse_date(row['Primary Mission End Date'])
    mission_end_date = parse_date(row['Mission End Date'])
    
    num_spacecraft = parse_spacecraft_count(row['# of spacecraft'])
    
    spacecraft_list = []
    for i in range(num_spacecraft):
        spacecraft_name = canonical_full_name
        if num_spacecraft > 1:
            spacecraft_name = f"{canonical_full_name} - Spacecraft {i + 1}"
        
        spacecraft = Spacecraft(
            name=spacecraft_name,
            cospar_id=row['COSPAR ID'].strip() if i == 0 and row['COSPAR ID'] else None,
            launch_date=launch_date,
            mass=parse_mass(row['Mass']),
            launch_vehicle=row['Launch Vehicle'].strip() if row['Launch Vehicle'] else None
        )
        spacecraft_list.append(spacecraft)
    
    nations = [n.strip() for n in row['Nation'].split('/') if n.strip()] if row['Nation'] else []
    # TODO: Use COSPAR ID to fetch description from NSSDCA or similar source
    
    mission_data = MissionData(
        canonical_full_name=canonical_full_name,
        canonical_short_name=canonical_short_name,
        nasa_mission_page_url=row['url'].strip() if row['url'] else None,
        image_url=None,
        formulation_start_date=parse_date(row['Formulation Start Date']),
        development_start_date=None,
        prime_mission_end_date=primary_mission_end_date,
        extended_mission_end_date=mission_end_date,
        status=determine_status(launch_date, mission_end_date),
        life_cycle_cost=parse_cost(row['LCC (M$)']),
        program_line=row['Program'].strip() if row['Program'] else None,
        mission_type=row['Mission Type'].strip() if row['Mission Type'] else None,
        primary_target=row['Mission Target'].strip() if row['Mission Target'] else None,
        sponsor_nations=nations,
        description=row['Mission Objective'].strip() if row['Mission Objective'] else "",
        launch_date=launch_date,
        spacecraft=spacecraft_list
    )
    
    return mission_data


def find_mission_in_csv(csv_path: Path, mission_name: str) -> Optional[Dict[str, str]]:
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    for row in rows:
        if row['Short Title'].strip().lower() == mission_name.lower():
            return row
    
    print(f"\nMission '{mission_name}' not found.")
    print("\nAvailable missions:")
    for row in rows:
        if row['Short Title'].strip():
            print(f"  - {row['Short Title']}")
    
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Import mission data from CSV into YAML format"
    )
    parser.add_argument(
        "--import",
        dest="mission_name",
        required=True,
        help="Name of the mission to import (matches 'Short Title' in CSV)"
    )
    
    args = parser.parse_args()
    
    data_dir = Path(__file__).parent.parent / "data"
    missions_dir = data_dir / "missions"
    missions_dir.mkdir(parents=True, exist_ok=True)
    
    csv_path = data_dir / CSV_FILENAME
    if not csv_path.exists():
        csv_path = download_csv(data_dir)
    
    row = find_mission_in_csv(csv_path, args.mission_name)
    if not row:
        sys.exit(1)
    
    try:
        mission_data = create_mission_from_row(row)
        
        yaml_filename = kebabcase(mission_data.canonical_short_name) + ".yaml"
        yaml_path = missions_dir / yaml_filename
        
        mission = Mission.from_dict(mission_data.model_dump(), yaml_path)
        mission.save()
        
        print(f"\nSuccessfully imported mission: {mission_data.canonical_full_name}")
        print(f"Saved to: {yaml_path}")
        print(f"  - Status: {mission_data.status.value}")
        print(f"  - Spacecraft: {len(mission_data.spacecraft)}")
        if mission_data.life_cycle_cost:
            print(f"  - Cost: ${mission_data.life_cycle_cost:,.0f}")
        
    except Exception as e:
        print(f"\nError importing mission: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()