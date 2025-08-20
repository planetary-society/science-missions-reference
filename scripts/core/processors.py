import pandas as pd
import os
import sys
import shutil
from typing import Optional, List
from pathlib import Path
from casefy import snakecase

from usaspending.client import USASpending
from usaspending.exceptions import DownloadError
import logging

from scripts.core.mission import Mission


class ObligationsCalculator:
    def __init__(self, client: Optional[USASpending] = None):
        self.client = client or USASpending()
    
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
            return df
        else:
            # Return empty DataFrame
            return pd.DataFrame()


class OutlaysCalculator:
    def __init__(self, client: Optional[USASpending] = None):
        self.client = client or USASpending()
        self.logger = logging.getLogger(__name__)
    
    def calculate(self, mission: Mission) -> pd.DataFrame:
        """
        Download and process outlay data for each award_id in the mission.
        Returns DataFrame with columns: month_date, monthly_outlay
        """
        # Create base directory for mission outlays data
        mission_dir = Path(f"data/spending/{snakecase(mission.acronym)}/outlays")
        mission_dir.mkdir(parents=True, exist_ok=True)
        
        all_outlays_data = []
        
        for award_id in mission.data.award_ids:
            try:
                # Check if FederalAccountFunding CSV already exists
                csv_file = self._find_federal_account_funding_csv(mission_dir, award_id)
                
                if not csv_file:
                    # Download award data if CSV doesn't exist
                    csv_file = self._download_award_data(award_id, mission_dir)
                
                if csv_file:
                    # Process the CSV file to calculate outlays
                    outlays_data = self._process_federal_account_funding(csv_file, award_id)
                    all_outlays_data.extend(outlays_data)
                    
            except Exception as e:
                self.logger.error(f"Error processing award {award_id}: {e}")
                continue
        
        # Create DataFrame and sort by date
        if all_outlays_data:
            df = pd.DataFrame(all_outlays_data)
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
            
            # Queue download job
            job = award.download(file_format="csv", destination_dir=str(mission_dir))
            
            self.logger.info(f"Job successfully queued. Tracking File: {job.file_name}")
            
            # Wait for completion with timeout
            extracted_files: List[str] = job.wait_for_completion(
                timeout=300,  # 5 minutes
                poll_interval=10,  # Check every 10 seconds
                cleanup_zip=True  # Clean up ZIP after extraction
            )
            
            self.logger.info("Download and extraction complete")
            self.logger.info(f"Total files extracted: {len(extracted_files)}")
            
            # Find the FederalAccountFunding CSV file
            federal_account_file = None
            for file_path in extracted_files:
                if "FederalAccountFunding" in file_path and file_path.endswith('.csv'):
                    federal_account_file = Path(file_path)
                    break
            
            if not federal_account_file:
                self.logger.error("No FederalAccountFunding CSV file found in extraction")
                return None
            
            # Move and rename the file to a consistent location
            target_file = mission_dir / f"{award_id}_FederalAccountFunding.csv"
            shutil.move(str(federal_account_file), str(target_file))
            self.logger.info(f"Moved FederalAccountFunding CSV to: {target_file}")
            
            # Clean up the timestamped subdirectory and any other extracted files
            subdirectory = federal_account_file.parent
            if subdirectory != mission_dir and subdirectory.exists():
                shutil.rmtree(subdirectory)
                self.logger.info(f"Cleaned up temporary directory: {subdirectory}")
            
            return target_file
            
        except DownloadError as e:
            self.logger.error(f"Download failed for {award_id}. Status: {e.status}. Message: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error downloading {award_id}: {e}")
            return None
    
    def _parse_submission_period(self, period_str):
        """Converts a USASpending submission period string (e.g., 'FY2025P09') 
        into a sortable datetime object representing the start of that fiscal month."""
        if not isinstance(period_str, str) or 'P' not in period_str:
            return None
        try:
            year_str, month_str = period_str.split('P')
            # Get the fiscal year number (e.g., 2025)
            fiscal_year = int(year_str[2:])
            period = int(month_str)
            
            # Fiscal year starts in October. P01 is October, P12 is September.
            month = ((period + 8) % 12) + 1
            # The calendar year for P01, P02, P03 is the fiscal year minus 1.
            calendar_year = fiscal_year - 1 if month >= 10 else fiscal_year
                
            return pd.to_datetime(f"{calendar_year}-{month}-01")
        except (ValueError, IndexError):
            return None
    
    def _process_federal_account_funding(self, csv_file: Path, award_id: str) -> List[dict]:
        """Process FederalAccountFunding CSV to calculate monthly outlays"""
        try:
            df = pd.read_csv(csv_file)
            self.logger.info(f"Processing {len(df)} records from {csv_file.name}")
            
            # Clean and prepare data
            df.columns = df.columns.str.lower().str.replace(' ', '_')
            
            required_cols = ['submission_period', 'beginning_period_of_availability', 'gross_outlay_amount_fyb_to_period_end']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                self.logger.error(f"Missing required columns: {missing_cols}")
                return []
            
            df['gross_outlay_amount_fyb_to_period_end'] = pd.to_numeric(
                df['gross_outlay_amount_fyb_to_period_end'], errors='coerce'
            ).fillna(0)
            
            # Parse submission period to extract FY and Period
            df['fiscal_year'] = df['submission_period'].str.extract(r'FY(\d{4})')[0].astype('Int64')
            df['fiscal_period'] = df['submission_period'].str.extract(r'P(\d{2})')[0].astype('Int64')
            
            # Convert to calendar date
            df['month_date'] = df['submission_period'].apply(self._parse_submission_period)
            df.dropna(subset=['month_date'], inplace=True)
            
            if df.empty:
                self.logger.warning("No valid submission periods found")
                return []
            
            # Sort by funding source, fiscal year, and date to prepare for calculation
            df = df.sort_values(by=['beginning_period_of_availability', 'fiscal_year', 'month_date'])
            
            # Calculate monthly delta per funding source AND fiscal year to ensure reset at FY boundaries
            df['monthly_outlay'] = df.groupby(['beginning_period_of_availability', 'fiscal_year'])['gross_outlay_amount_fyb_to_period_end'].diff().fillna(df['gross_outlay_amount_fyb_to_period_end'])
            
            # Aggregate by submission_period (not just month_date) to preserve FY/Period
            monthly_totals = df.groupby(['submission_period', 'fiscal_year', 'fiscal_period', 'month_date']).agg({
                'monthly_outlay': 'sum'
            }).reset_index()
            monthly_totals = monthly_totals.sort_values('month_date')
            
            # Convert to list of dictionaries for return
            outlays_data = []
            for _, row in monthly_totals.iterrows():
                outlays_data.append({
                    'award_id': award_id,
                    'fiscal_year': row['fiscal_year'],
                    'fiscal_period': row['fiscal_period'],
                    'submission_period': row['submission_period'],
                    'month_date': row['month_date'],
                    'monthly_outlay': row['monthly_outlay']
                })
            
            self.logger.info(f"Calculated {len(outlays_data)} monthly outlay records")
            return outlays_data
            
        except Exception as e:
            self.logger.error(f"Error processing CSV {csv_file}: {e}")
            return []