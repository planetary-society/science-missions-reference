import json
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime

import pandas as pd
import requests
from casefy import kebabcase, snakecase

from scripts.core.mission import Mission


class JSONGenerator:
    def __init__(self):
        pass

    def check_url_exists(self, url: str) -> bool:
        """Check if a URL exists by making a HEAD request"""
        try:
            response = requests.head(url, timeout=2, allow_redirects=True)
            return response.status_code == 200
        except:
            return False

    def generate_plot_urls(self, mission_short_name: str, chart_type: str) -> list:
        """Generate validated plot URLs for a given mission and chart type (obligations/outlays)"""
        base_url = "https://planetary.s3.amazonaws.com/assets/charts/"
        stem = f"{snakecase(mission_short_name)}_{chart_type}_fy2025_vs_fy2024"

        formats = [
            f"{stem}_desktop.png",
            f"{stem}_mobile.png",
            f"{stem}_desktop.svg",
            f"{stem}_mobile.svg"
        ]

        validated_urls = []
        for filename in formats:
            url = f"{base_url}{filename}"
            if self.check_url_exists(url):
                validated_urls.append(url)

        return validated_urls

    def load_obligations_data(self, mission_short_name: str, obligations_dir: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Load obligations CSV for a specific mission and return data with last modified date"""
        filename = f"{snakecase(mission_short_name)}_obligations.csv"
        csv_path = obligations_dir / filename

        if csv_path.exists():
            mod_time = datetime.fromtimestamp(csv_path.stat().st_mtime)
            mod_date_str = mod_time.strftime("%Y-%m-%d")
            return pd.read_csv(csv_path), mod_date_str
        return None, None

    def load_obligations_summary_data(self, mission_short_name: str, obligations_dir: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Load obligations summary CSV for a specific mission and return data with last modified date"""
        filename = f"{snakecase(mission_short_name)}_obligations_summary.csv"
        csv_path = obligations_dir / filename

        if csv_path.exists():
            mod_time = datetime.fromtimestamp(csv_path.stat().st_mtime)
            mod_date_str = mod_time.strftime("%Y-%m-%d")
            return pd.read_csv(csv_path), mod_date_str
        return None, None

    def load_outlays_data(self, mission_short_name: str, spending_dir: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Load outlays CSV for a specific mission and return data with last modified date"""
        filename = f"{snakecase(mission_short_name)}_outlays.csv"
        csv_path = spending_dir / filename

        if csv_path.exists():
            mod_time = datetime.fromtimestamp(csv_path.stat().st_mtime)
            mod_date_str = mod_time.strftime("%Y-%m-%d")
            return pd.read_csv(csv_path), mod_date_str
        return None, None

    def load_outlays_summary_data(self, mission_short_name: str, spending_dir: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Load outlays summary CSV for a specific mission and return data with last modified date"""
        filename = f"{snakecase(mission_short_name)}_outlays_summary.csv"
        csv_path = spending_dir / filename

        if csv_path.exists():
            mod_time = datetime.fromtimestamp(csv_path.stat().st_mtime)
            mod_date_str = mod_time.strftime("%Y-%m-%d")
            return pd.read_csv(csv_path), mod_date_str
        return None, None

    def calculate_obligations_summary_from_summary(self, summary_df: pd.DataFrame) -> dict:
        """Calculate obligations summary metrics from pre-aggregated summary data"""
        if summary_df is None or summary_df.empty:
            return {}

        years = sorted(summary_df['reporting_fiscal_year'].unique(), reverse=True)

        if len(years) < 2:
            return {}

        current_year = years[0]
        prior_year = years[1]

        current_year_data = summary_df[summary_df['reporting_fiscal_year'] == current_year].copy()
        prior_year_data = summary_df[summary_df['reporting_fiscal_year'] == prior_year].copy()

        current_year_data = current_year_data.sort_values('reporting_fiscal_month')
        prior_year_data = prior_year_data.sort_values('reporting_fiscal_month')

        prior_year_total = prior_year_data['transaction_obligated_amount'].sum()
        current_year_running_sum = current_year_data['cumulative_obligations'].iloc[-1] if not current_year_data.empty else 0

        max_current_period = current_year_data['reporting_fiscal_month'].max() if not current_year_data.empty else 0
        prior_year_comparable = prior_year_data[
            prior_year_data['reporting_fiscal_month'] <= max_current_period
        ].copy()

        if not prior_year_comparable.empty:
            prior_year_comparable_sum = prior_year_comparable['cumulative_obligations'].iloc[-1]
            delta = current_year_running_sum - prior_year_comparable_sum
        else:
            prior_year_comparable_sum = 0
            delta = current_year_running_sum

        result = {
            'prior_year_total_millions': prior_year_total / 1_000_000,
            'prior_year_comparable_sum_millions': prior_year_comparable_sum / 1_000_000,
            'current_year_running_sum_millions': current_year_running_sum / 1_000_000,
            'delta_millions': delta / 1_000_000,
            'current_year': current_year,
            'prior_year': prior_year,
            'max_current_month': max_current_period
        }

        return result

    def calculate_outlays_summary_from_summary(self, summary_df: pd.DataFrame) -> dict:
        """Calculate outlays summary metrics from pre-aggregated summary data"""
        if summary_df is None or summary_df.empty:
            return {}

        years = sorted(summary_df['fiscal_year'].unique(), reverse=True)

        if len(years) < 2:
            return {}

        current_year = years[0]
        prior_year = years[1]

        current_year_data = summary_df[summary_df['fiscal_year'] == current_year].copy()
        prior_year_data = summary_df[summary_df['fiscal_year'] == prior_year].copy()

        current_year_data = current_year_data.sort_values('fiscal_period')
        prior_year_data = prior_year_data.sort_values('fiscal_period')

        prior_year_total = prior_year_data['cumulative_outlay'].iloc[-1] if not prior_year_data.empty else 0
        current_year_running_sum = current_year_data['cumulative_outlay'].iloc[-1] if not current_year_data.empty else 0

        max_current_period = current_year_data['fiscal_period'].max() if not current_year_data.empty else 0
        prior_year_comparable = prior_year_data[
            prior_year_data['fiscal_period'] <= max_current_period
        ].copy()

        if not prior_year_comparable.empty:
            prior_year_comparable_sum = prior_year_comparable['cumulative_outlay'].iloc[-1]
            delta = current_year_running_sum - prior_year_comparable_sum
        else:
            prior_year_comparable_sum = 0
            delta = current_year_running_sum

        result = {
            'prior_year_total_millions': round(prior_year_total / 1_000_000),
            'prior_year_comparable_sum_millions': round(prior_year_comparable_sum / 1_000_000),
            'current_year_running_sum_millions': round(current_year_running_sum / 1_000_000),
            'delta_millions': round(delta / 1_000_000),
            'current_year': current_year,
            'prior_year': prior_year,
            'max_current_period': max_current_period
        }

        return result

    def get_mission_last_updated(self, mission: Mission, spending_dir: Path) -> str:
        """Determine the most recent modification date from mission YAML and related CSV files"""
        modification_times = []

        # Get YAML file modification time
        if mission.path and mission.path.exists():
            yaml_mod_time = datetime.fromtimestamp(mission.path.stat().st_mtime)
            modification_times.append(yaml_mod_time)

        # Get CSV file modification times
        mission_snake = snakecase(mission.acronym)
        csv_files = [
            spending_dir / f"{mission_snake}_obligations.csv",
            spending_dir / f"{mission_snake}_obligations_summary.csv",
            spending_dir / f"{mission_snake}_outlays.csv",
            spending_dir / f"{mission_snake}_outlays_summary.csv"
        ]

        for csv_path in csv_files:
            if csv_path.exists():
                csv_mod_time = datetime.fromtimestamp(csv_path.stat().st_mtime)
                modification_times.append(csv_mod_time)

        # Return the most recent date, or today if no files found
        if modification_times:
            latest_time = max(modification_times)
            return latest_time.strftime('%Y-%m-%d')
        else:
            return datetime.now().strftime('%Y-%m-%d')

    def generate_mission_json(self, mission: Mission, spending_dir: Path, output_dir: Path):
        """Generate JSON data file for a single mission in site/data/ directory"""
        # Create data directory
        data_dir = output_dir / 'data'
        data_dir.mkdir(parents=True, exist_ok=True)

        # Load data
        obligations_df, obligations_last_updated = self.load_obligations_data(mission.acronym, spending_dir)
        outlays_df, outlays_last_updated = self.load_outlays_data(mission.acronym, spending_dir)
        obligations_summary_df, _ = self.load_obligations_summary_data(mission.acronym, spending_dir)
        outlays_summary_df, _ = self.load_outlays_summary_data(mission.acronym, spending_dir)

        # Calculate summaries
        if obligations_summary_df is not None and not obligations_summary_df.empty:
            obligations_summary = self.calculate_obligations_summary_from_summary(obligations_summary_df)
        else:
            obligations_summary = {}

        if outlays_summary_df is not None and not outlays_summary_df.empty:
            outlays_summary = self.calculate_outlays_summary_from_summary(outlays_summary_df)
        else:
            outlays_summary = {}

        # Get the actual last updated date based on file modification times
        actual_last_updated = self.get_mission_last_updated(mission, spending_dir)

        # Prepare mission data and override last_updated with calculated value
        mission_dict = mission.data.model_dump(mode='json')
        mission_dict['last_updated'] = actual_last_updated

        # Prepare comprehensive data structure with all financial data
        mission_data = {
            'mission': mission_dict,
            'financial': {
                'obligations': {
                    'data': obligations_df.to_dict('records') if obligations_df is not None else [],
                    'summary': obligations_summary,
                    'last_updated': obligations_last_updated
                },
                'outlays': {
                    'data': outlays_df.to_dict('records') if outlays_df is not None else [],
                    'summary': outlays_summary,
                    'last_updated': outlays_last_updated
                }
            }
        }

        # Generate plot URLs with validation
        obligations_plot_urls = self.generate_plot_urls(mission.acronym, 'obligations')
        outlays_plot_urls = self.generate_plot_urls(mission.acronym, 'outlays')

        # Add prerendered chart URLs if any exist
        if obligations_plot_urls:
            mission_data['financial']['obligations']['prerendered_charts'] = obligations_plot_urls

        if outlays_plot_urls:
            mission_data['financial']['outlays']['prerendered_charts'] = outlays_plot_urls

        # Save mission data as JSON in centralized data directory
        json_path = data_dir / f'{kebabcase(mission.acronym).lower()}.json'
        with open(json_path, 'w') as f:
            json.dump(mission_data, f, indent=2, default=str)

        print(f"Generated JSON data for {mission.name} -> {json_path}")
        return json_path
