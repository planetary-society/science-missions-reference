import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import pandas as pd

from scripts.core.mission import MissionStatus


class Source(ABC):
    """Abstract base class for mission data sources"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
    
    def _load_csv_from_url(self, filename: str, url: str) -> pd.DataFrame:
        """Load CSV data using pandas with local caching"""
        csv_path = self.data_dir / filename
        
        # Try to load from local file first
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path)
                print(f"Loaded existing {filename} from {csv_path}")
                return df
            except Exception as e:
                print(f"Warning: Could not load local {filename} ({e}), will download fresh copy")
        
        # Download from URL
        try:
            print(f"Downloading {filename} from {url}...")
            df = pd.read_csv(url)
            
            # Save to local file for future use
            df.to_csv(csv_path, index=False)
            print(f"{filename} downloaded and saved to {csv_path}")
            return df
            
        except Exception as e:
            print(f"Warning: Could not download {filename}: {e}")
            return pd.DataFrame()
    
    @abstractmethod
    def find(self, keyword: str) -> Optional[Dict[str, Any]]:
        """Find a mission by keyword and return raw data"""
        pass
    
    @abstractmethod
    def enrich_mission_data(self, mission_data: Dict[str, Any], raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich existing mission data with source-specific information"""
        pass


class GoogleSheetsSource(Source):
    """Primary mission data source from Google Sheets CSV"""
    
    URL = "https://docs.google.com/spreadsheets/d/1ag7otfTfElrFz-yRZEdp-sLxlwkS_p7gRvnD1tVo7fE/export?format=csv"
    CSV_FILENAME = "us_space_science_missions.csv"
    
    def __init__(self, data_dir: Path):
        super().__init__(data_dir)
        self.df = self._load_csv_from_url(self.CSV_FILENAME, self.URL)
    
    def find(self, keyword: str) -> Optional[Dict[str, Any]]:
        """Find mission by Short Title"""
        if self.df.empty:
            return None
        
        # Handle NaN values in Short Title column
        mask = self.df['Short Title'].notna() & (self.df['Short Title'].str.strip().str.lower() == keyword.lower())
        matches = self.df[mask]
        
        if matches.empty:
            return None
        
        # Convert to dict, replacing NaN with None or empty string for string fields
        row_dict = matches.iloc[0].to_dict()
        for key, value in row_dict.items():
            if pd.isna(value):
                row_dict[key] = None
        
        return row_dict
    
    def enrich_mission_data(self, mission_data: Dict[str, Any], raw_data: Dict[str, Any]) -> Dict[str, Any]:
        # Helper function to safely get string values
        def safe_get_str(key):
            value = raw_data.get(key)
            return value.strip() if value and isinstance(value, str) else None
        
        # Parse dates
        launch_date = self._parse_date(safe_get_str('Mission Launch Date'))
        primary_mission_end_date = self._parse_date(safe_get_str('Primary Mission End Date'))
        extended_mission_end_date = self._parse_date(safe_get_str('Mission End Date'))
        
        # Determine status with new Active logic
        status = self._determine_status(launch_date, primary_mission_end_date, extended_mission_end_date)
        
        # Parse spacecraft
        num_spacecraft = self._parse_spacecraft_count(safe_get_str('# of spacecraft'))
        spacecraft_list = []
        
        canonical_full_name = safe_get_str('Full Name') or 'Unknown Mission'
        mission_type = safe_get_str('Mission Type')  # Still used for spacecraft_type
        
        for i in range(num_spacecraft):
            spacecraft_name = canonical_full_name
            if num_spacecraft > 1:
                spacecraft_name = f"{canonical_full_name} - Spacecraft {i + 1}"
            
            spacecraft = {
                'name': spacecraft_name,
                'COSPAR_id': safe_get_str('COSPAR ID') if i == 0 else None,
                'launch_date': launch_date.isoformat() if launch_date else None,
                'mass': self._parse_mass(safe_get_str('Mass')),
                'launch_vehicle': safe_get_str('Launch Vehicle'),
                'spacecraft_type': mission_type  # Apply mission type to spacecraft
            }
            spacecraft_list.append(spacecraft)
        
        # Parse nations
        nation_str = safe_get_str('Nation')
        nations = [n.strip() for n in nation_str.split('/') if n.strip()] if nation_str else []
        
        # Build mission data
        mission_data.update({
            'canonical_full_name': canonical_full_name,
            'canonical_short_name': safe_get_str('Short Title') or 'Unknown',
            'nasa_mission_page_url': safe_get_str('url'),
            'image_url': safe_get_str('image_url'),
            'formulation_start_date': self._parse_date(safe_get_str('Formulation Start Date')),
            'prime_mission_end_date': primary_mission_end_date,
            'extended_mission_end_date': extended_mission_end_date,
            'status': status.value,
            'life_cycle_cost': self._parse_cost(safe_get_str('LCC (M$)')),
            'program_line': safe_get_str('Program'),
            'division': safe_get_str('Division'),
            'primary_target': safe_get_str('Mission Target'),
            'sponsor_nations': nations,
            'description': safe_get_str('Mission Objective') or "",
            'last_updated': datetime.now().strftime('%Y-%m-%d'),
            'launch_date': launch_date.isoformat() if launch_date else None,
            'spacecraft': spacecraft_list
        })
        
        return mission_data
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        if not date_str or date_str.strip() == '':
            return None
        
        try:
            return datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
        except ValueError:
            try:
                return datetime.strptime(date_str.strip(), '%m/%d/%Y').date()
            except ValueError:
                return None
    
    def _parse_cost(self, cost_str: str) -> Optional[float]:
        if not cost_str or cost_str.strip() == '':
            return None
        
        clean_str = re.sub(r'[^0-9.-]', '', cost_str)
        
        if not clean_str:
            return None
        
        try:
            cost_millions = float(clean_str)
            return cost_millions * 1_000_000
        except ValueError:
            return None
    
    def _parse_mass(self, mass_str: str) -> Optional[int]:
        if not mass_str or mass_str.strip() == '':
            return None
        
        clean_str = re.sub(r'[^0-9.]', '', mass_str)
        
        if not clean_str:
            return None
        
        try:
            return int(float(clean_str))
        except ValueError:
            return None
    
    def _parse_spacecraft_count(self, count_str: str) -> int:
        if not count_str or count_str.strip() == '':
            return 1
        
        try:
            return int(count_str.strip())
        except ValueError:
            return 1
    
    def _determine_status(self, launch_date: Optional[datetime], 
                         prime_end: Optional[datetime], 
                         extended_end: Optional[datetime]) -> MissionStatus:
        if not launch_date:
            return MissionStatus.DEVELOPMENT
        
        now = datetime.now().date()
        
        # Check if mission has ended
        if (prime_end and prime_end < now) or (extended_end and extended_end < now):
            return MissionStatus.COMPLETED
        
        # New logic: Active if launched but no end dates
        if launch_date < now and not prime_end and not extended_end:
            return MissionStatus.ACTIVE
        
        return MissionStatus.UNKNOWN


class NSSDCACatalogSource(Source):
    """NSSDCA catalog source for description and alternative names"""
    
    URL = "https://raw.githubusercontent.com/planetary-society/nssdca-catalog-scraper/3577a60c1032c2224a2ea280345b1f01548d2631/data/all_spacecraft_list.csv"
    CSV_FILENAME = "nssdca_catalog.csv"
    
    def __init__(self, data_dir: Path):
        super().__init__(data_dir)
        self.df = self._load_csv_from_url(self.CSV_FILENAME, self.URL)
    
    def find(self, keyword: str) -> Optional[Dict[str, Any]]:
        """Find by NSSDC ID, COSPAR ID, or name"""
        if self.df.empty:
            return None
        
        # Check if columns exist and search by NSSDC_ID, COSPAR_ID, or name
        conditions = []
        
        if 'nssdc_id' in self.df.columns:
            nssdc_mask = self.df['nssdc_id'].notna() & (self.df['nssdc_id'].str.strip().str.lower() == keyword.lower())
            conditions.append(nssdc_mask)
        
        if 'cospar_id' in self.df.columns:
            cospar_mask = self.df['cospar_id'].notna() & (self.df['cospar_id'].str.strip().str.lower() == keyword.lower())
            conditions.append(cospar_mask)
            
        if 'name' in self.df.columns:
            name_mask = self.df['name'].notna() & (self.df['name'].str.strip().str.lower() == keyword.lower())
            conditions.append(name_mask)
        
        if not conditions:
            return None
            
        # Combine conditions with OR
        combined_mask = conditions[0]
        for condition in conditions[1:]:
            combined_mask = combined_mask | condition
            
        matches = self.df[combined_mask]
        
        if matches.empty:
            return None
        
        # Convert to dict, replacing NaN with None
        row_dict = matches.iloc[0].to_dict()
        for key, value in row_dict.items():
            if pd.isna(value):
                row_dict[key] = None
        
        return row_dict
    
    def enrich_mission_data(self, mission_data: Dict[str, Any], raw_data: Dict[str, Any]) -> Dict[str, Any]:
        # Only enrich description if empty or missing
        if not mission_data.get('description') and raw_data.get('description'):
            mission_data['description'] = raw_data['description'].strip()
        
        # Parse and append alternative names
        if raw_data.get('alternate_names'):
            new_alt_names = [n.strip() for n in raw_data['alternate_names'].split(',') if n.strip()]
            existing_names = mission_data.get('alternative_names', [])
            
            for name in new_alt_names:
                if name not in existing_names:
                    existing_names.append(name)
            
            mission_data['alternative_names'] = existing_names
        
        # Update spacecraft NSSDCA_ID if we have a COSPAR ID match
        if raw_data.get('cospar_id') and raw_data.get('nssdc_id'):
            spacecraft_list = mission_data.get('spacecraft', [])
            for spacecraft in spacecraft_list:
                # If this spacecraft has the matching COSPAR ID and no NSSDCA_ID yet
                if (spacecraft.get('COSPAR_id') == raw_data['cospar_id'] and 
                    not spacecraft.get('NSSDCA_id')):
                    spacecraft['NSSDCA_id'] = raw_data['nssdc_id']
        
        return mission_data