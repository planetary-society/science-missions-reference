import pandas as pd
import os
import sys
import shutil
from typing import Optional, List
from pathlib import Path
from casefy import snakecase

from usaspending import USASpendingClient
from usaspending.exceptions import DownloadError
import logging

from scripts.core.mission import Mission


class ObligationsCalculator:
    def __init__(self, client: Optional[USASpendingClient] = None, force_reload: bool = False):
        self.client = client or USASpendingClient()
        self.force_reload = force_reload
    
    def calculate(self, mission: Mission) -> pd.DataFrame:
        """
        Fetch funding data for each award_id in the mission.
        Returns DataFrame with columns: reporting_fiscal_year, reporting_fiscal_month, 
        gross_outlay_amount, transaction_obligated_amount
        """
        all_funding_data = []
        
        for award_id in mission.data.award_ids:
            try:
                # Find award by ID
                award = self.client.awards.find_by_award_id(award_id)
                
                if award:
                    # Iterate through funding records for this award
                    print(f"  Found award: {award_id}")
                    funding_count = 0
                    for funding in award.funding:
                        funding_data = {
                            'award_id': award_id,
                            'reporting_fiscal_year': funding.reporting_fiscal_year,
                            'reporting_fiscal_month': funding.reporting_fiscal_month,
                            'gross_outlay_amount': funding.gross_outlay_amount or 0.0,
                            'transaction_obligated_amount': funding.transaction_obligated_amount or 0.0,
                            'is_quarterly_submission': funding.is_quarterly_submission,
                            'federal_account': funding.federal_account,
                            'account_title': funding.account_title,
                            'recipient_name': award.recipient.name,
                            'recipient_id': award.recipient.recipient_id,
                            'award_description': award.description if isinstance(award.description,str) else '',
                            'award_usaspending_url': award.usa_spending_url
                        }
                        all_funding_data.append(funding_data)
                        funding_count += 1
                    print(f"    Found {funding_count} funding records")
                else:
                    print(f"  Award not found: {award_id}")
                    
            except Exception as e:
                print(f"Error fetching funding for award {award_id}: {e}")
                continue
        
        # Create DataFrame and sort by year/month descending
        if all_funding_data:
            df = pd.DataFrame(all_funding_data)
            df = df.sort_values(
                by=['award_id','reporting_fiscal_year', 'reporting_fiscal_month'], 
                ascending=[True,False, False]
            )
            self.client.close()
            return df
        else:
            # Return empty DataFrame
            self.client.close()
            return pd.DataFrame()


class OutlaysCalculator:
    def __init__(self, client: Optional[USASpendingClient] = None, force_reload: bool = False):
        self.client = client or USASpendingClient()
        self.force_reload = force_reload
        self.logger = logging.getLogger(__name__)
    
    def calculate(self, mission: Mission) -> pd.DataFrame:
        """
        Download and process outlay data for each award_id in the mission.
        Returns DataFrame with columns: submission_period, fiscal_year, fiscal_period, month_date, cumulative_outlay
        """
        # Create base directory for mission outlays data
        mission_dir = Path(f"data/spending/{snakecase(mission.acronym)}/outlays")
        mission_dir.mkdir(parents=True, exist_ok=True)
        
        all_outlays_data = []
        
        for award_id in mission.data.award_ids:
            try:
                # Check if FederalAccountFunding CSV already exists (unless force_reload)
                csv_file = None if self.force_reload else self._find_federal_account_funding_csv(mission_dir, award_id)
                
                if not csv_file:
                    # Download award data if CSV doesn't exist or force_reload is True
                    if self.force_reload:
                        # Remove existing cached file if it exists
                        existing_file = mission_dir / f"{award_id}_FederalAccountFunding.csv"
                        if existing_file.exists():
                            existing_file.unlink()
                            self.logger.info(f"Removed cached file for fresh download: {existing_file}")
                    csv_file = self._download_award_data(award_id, mission_dir)
                
                if csv_file:
                    # Process the CSV file to calculate outlays
                    outlays_data = self._process_federal_account_funding(csv_file, award_id)
                    all_outlays_data.extend(outlays_data)
                    
            except Exception as e:
                self.logger.error(f"Error processing award {award_id}: {e}")
                continue
        
        if all_outlays_data:
            df = pd.DataFrame(all_outlays_data)
            # Aggregate across awards if mission has multiple award_ids
            df = df.groupby(['submission_period', 'fiscal_year', 'fiscal_period', 'month_date']).agg({
                'cumulative_outlay': 'sum'
            }).reset_index()
            df = df.sort_values('month_date')
            return df
        else:
            return pd.DataFrame()
    
    def _find_federal_account_funding_csv(self, mission_dir: Path, award_id: str) -> Optional[Path]:
        """Check if FederalAccountFunding CSV exists for this award"""
        # Look for the consistently named CSV file
        target_file = mission_dir / f"{award_id}_FederalAccountFunding.csv"
        
        if target_file.exists():
            self.logger.info(f"Found existing FederalAccountFunding CSV: {target_file}")
            return target_file
        
        return None
    
    def _download_award_data(self, award_id: str, mission_dir: Path) -> Optional[Path]:
        """Download award data and extract FederalAccountFunding CSV"""
        try:
            # Get award data
            award = self.client.awards.find_by_award_id(award_id)
            
            if not award:
                self.logger.warning(f"Award not found: {award_id}")
                return None
            
            self.logger.info(f"Starting download for Award ID: {award_id}")
            self.logger.info(f"Award Type: {award.category}")
            
            # Log expected download endpoint based on award category
            if hasattr(award, 'category') and award.category:
                endpoint_map = {
                    'contract': 'contract',
                    'grant': 'assistance',
                    'direct_payment': 'assistance',
                    'loans': 'assistance',
                    'other': 'assistance'
                }
                endpoint = endpoint_map.get(award.category.lower(), award.category.lower())
                expected_url = f"https://api.usaspending.gov/api/v2/download/{endpoint}/"
                self.logger.info(f"Expected download endpoint: {expected_url}")
            
            # Queue download job
            job = award.download(file_format="csv", destination_dir=str(mission_dir))
            
            self.logger.info(f"Job successfully queued. Tracking File: {job.file_name}")
            
            # Wait for completion with timeout
            extracted_files: List[str] = job.wait_for_completion(
                timeout=300,
                poll_interval=10,
                cleanup_zip=True
            )
            
            self.logger.info("Download and extraction complete")
            self.logger.info(f"Total files extracted: {len(extracted_files)}")
            
            federal_account_file = None
            for file_path in extracted_files:
                if "FederalAccountFunding" in file_path and file_path.endswith('.csv'):
                    federal_account_file = Path(file_path)
                    break
            
            if not federal_account_file:
                self.logger.error("No FederalAccountFunding CSV file found in extraction")
                return None
            
            target_file = mission_dir / f"{award_id}_FederalAccountFunding.csv"
            shutil.move(str(federal_account_file), str(target_file))
            self.logger.info(f"Moved FederalAccountFunding CSV to: {target_file}")
            
            subdirectory = federal_account_file.parent
            if subdirectory != mission_dir and subdirectory.exists():
                shutil.rmtree(subdirectory)
                self.logger.info(f"Cleaned up temporary directory: {subdirectory}")
            
            return target_file
            
        except DownloadError as e:
            self.logger.error(f"Download failed for Award ID: {award_id}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error downloading Award ID: {award_id}: {e}")
            return None
    
    def _parse_submission_period(self, period_str: str) -> Optional[pd.Timestamp]:
        """Converts a USASpending submission period string (e.g., 'FY2025P09') 
        into a datetime object representing the start of that fiscal month."""
        if not isinstance(period_str, str) or 'P' not in period_str:
            return None
        try:
            year_str, month_str = period_str.split('P')
            fiscal_year = int(year_str[2:])
            period = int(month_str)
            
            # Fiscal year starts in October. P01 is October, P12 is September.
            month = ((period + 8) % 12) + 1
            calendar_year = fiscal_year - 1 if month >= 10 else fiscal_year
                
            return pd.to_datetime(f"{calendar_year}-{month}-01")
        except (ValueError, IndexError):
            return None
    
    def _process_federal_account_funding(self, csv_file: Path, award_id: str) -> List[dict]:
        """Process FederalAccountFunding CSV to calculate cumulative outlays per period."""
        try:
            df = pd.read_csv(csv_file)
            self.logger.info(f"Processing {len(df)} records from {csv_file.name}")
            
            df.columns = df.columns.str.lower().str.replace(' ', '_')
            
            required_cols = ['submission_period', 'gross_outlay_amount_fyb_to_period_end']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                self.logger.error(f"Missing required columns: {missing_cols}")
                return []
            
            # Convert to numeric, keeping NaN for missing values
            df['gross_outlay_amount_fyb_to_period_end'] = pd.to_numeric(
                df['gross_outlay_amount_fyb_to_period_end'], errors='coerce'
            )
            
            # Filter to only rows with actual outlay data (exclude obligation-only rows)
            df = df[df['gross_outlay_amount_fyb_to_period_end'].notna()]
            
            if df.empty:
                self.logger.warning("No outlay data found after filtering")
                return []
            
            # Parse submission period metadata
            df['fiscal_year'] = df['submission_period'].str.extract(r'FY(\d{4})')[0].astype('Int64')
            df['fiscal_period'] = df['submission_period'].str.extract(r'P(\d{2})')[0].astype('Int64')
            df['month_date'] = df['submission_period'].apply(self._parse_submission_period)
            df = df.dropna(subset=['month_date'])
            
            if df.empty:
                self.logger.warning("No valid submission periods found")
                return []
            
            # Sum across all appropriation years for each submission period
            # This combines e.g. 2024/2025 and 2025/2026 outlays in FY2025
            cumulative = df.groupby(['submission_period', 'fiscal_year', 'fiscal_period', 'month_date']).agg({
                'gross_outlay_amount_fyb_to_period_end': 'sum'
            }).reset_index()
            cumulative = cumulative.rename(columns={'gross_outlay_amount_fyb_to_period_end': 'cumulative_outlay'})
            cumulative = cumulative.sort_values('month_date')
            
            outlays_data = []
            for _, row in cumulative.iterrows():
                outlays_data.append({
                    'award_id': award_id,
                    'fiscal_year': row['fiscal_year'],
                    'fiscal_period': row['fiscal_period'],
                    'submission_period': row['submission_period'],
                    'month_date': row['month_date'],
                    'cumulative_outlay': row['cumulative_outlay']
                })
            
            self.logger.info(f"Calculated {len(outlays_data)} cumulative outlay records")
            return outlays_data
            
        except Exception as e:
            self.logger.error(f"Error processing CSV {csv_file}: {e}")
            return []