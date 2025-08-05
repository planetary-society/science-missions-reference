import pandas as pd
from typing import Optional

from usaspending.client import USASpending

from scripts.core.mission import Mission


class OutlaysCalculator:
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