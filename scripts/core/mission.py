from datetime import date
from typing import List, Optional
from pathlib import Path
from enum import Enum

from pydantic import BaseModel, HttpUrl, field_validator
from ruamel.yaml import YAML


class MissionStatus(str, Enum):
    PRIME_MISSION = "Prime Mission"
    LAUNCH_FAILURE = "Launch Failure"
    ACTIVE = "Active"
    EXTENDED_MISSION = "Extended Mission"
    COMPLETED = "Completed"
    CANCELED = "Canceled"
    DEVELOPMENT = "In Development"
    UNKNOWN = "Unknown"


class Spacecraft(BaseModel):
    name: str
    short_name: Optional[str] = None
    COSPAR_id: Optional[str] = None
    NSSDCA_id: Optional[str] = None
    spacecraft_type: Optional[str] = None
    launch_date: Optional[date] = None
    mission_end_date: Optional[date] = None
    mass: Optional[int] = None  # in kg
    launch_vehicle: Optional[str] = None


class MissionData(BaseModel):
    canonical_full_name: str
    canonical_short_name: str # Usually an acronym
    
    alternative_names: List[str] = []
    alternative_short_names: List[str] = []
    
    nasa_mission_page_url: Optional[HttpUrl] = None
    wikipedia_url: Optional[HttpUrl] = None
    image_url: Optional[HttpUrl] = None
    
    funding_chart_url: Optional[HttpUrl] = None
    funding_reference_data_url: Optional[HttpUrl] = None
    
    formulation_start_date: Optional[date] = None
    development_start_date: Optional[date] = None
    prime_mission_end_date: Optional[date] = None
    mission_end_date: Optional[date] = None
    
    status: MissionStatus
    life_cycle_cost: Optional[float] = None # in thousands of USD
    program_line: Optional[str] = None
    division: Optional[str] = None
    primary_target: Optional[str] = None
    sponsor_nations: List[str] = []
    description: str = ""
    last_updated: str  # YYYY-MM-DD format
    
    award_ids: List[str] = []
    
    # Launch Date of the mission, or first spacecraft if multiple
    launch_date: Optional[date] = None
    
    spacecraft: List[Spacecraft] = []
    
    @field_validator('life_cycle_cost')
    @classmethod
    def validate_cost(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("Life cycle cost must be non-negative")
        return v
    
    @field_validator('spacecraft')
    @classmethod
    def validate_spacecraft(cls, v: List[Spacecraft]) -> List[Spacecraft]:
        if not v:
            raise ValueError("Mission must have at least one spacecraft")
        return v


class Mission:
    def __init__(self, yaml_path: Path):
        self.path = Path(yaml_path)
        self._data: Optional[MissionData] = None
        self._raw_data: Optional[dict] = None
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._yaml.width = 120
        
    def load(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"Mission file not found: {self.path}")
        
        if self.path.suffix not in ['.yaml', '.yml']:
            raise ValueError(f"Mission file must be YAML: {self.path}")
            
        try:
            with open(self.path, 'r') as f:
                raw_yaml = self._yaml.load(f)
                
            if not raw_yaml:
                raise ValueError(f"Empty YAML file: {self.path}")
            
            # Use YAML content directly (no parent structure required)
            self._raw_data = raw_yaml
                
            self._data = MissionData(**self._raw_data)
            
        except Exception as e:
            raise ValueError(f"Failed to load mission from {self.path}: {e}")
    
    @property
    def data(self) -> MissionData:
        if self._data is None:
            self.load()
        return self._data
    
    @property
    def name(self) -> str:
        return self.data.canonical_full_name
    
    @property
    def acronym(self) -> str:
        return self.data.canonical_short_name
    
    def save(self, path: Optional[Path] = None) -> None:
        if self._data is None:
            raise ValueError("No mission data to save")
            
        save_path = path or self.path
        save_path = Path(save_path)
        
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        data_dict = self._data.model_dump(mode='json')
        
        for key, value in data_dict.items():
            if isinstance(value, str) and value.startswith('http'):
                data_dict[key] = str(value)
        
        for spacecraft in data_dict.get('spacecraft', []):
            for date_field in ['launch_date', 'end_date']:
                if date_field in spacecraft and spacecraft[date_field]:
                    spacecraft[date_field] = spacecraft[date_field]
        
        for date_field in ['formulation_start_date', 'development_start_date', 
                          'prime_mission_end_date', 'mission_end_date']:
            if date_field in data_dict and data_dict[date_field]:
                data_dict[date_field] = data_dict[date_field]
        
        # Save data directly (no parent key wrapper)
        with open(save_path, 'w') as f:
            self._yaml.dump(data_dict, f)
    
    @classmethod
    def from_dict(cls, data: dict, yaml_path: Path) -> 'Mission':
        mission = cls(yaml_path)
        mission._raw_data = data
        mission._data = MissionData(**data)
        return mission