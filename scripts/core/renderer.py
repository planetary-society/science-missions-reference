import json
from pathlib import Path
from typing import Optional, List

import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader
from casefy import snakecase

from scripts.core.mission import Mission


class SiteGenerator:
    def __init__(self, templates_dir: Path):
        self.templates_dir = Path(templates_dir)
        self.env = Environment(loader=FileSystemLoader(self.templates_dir))
        
    def load_outlays_data(self, mission_short_name: str, outlays_dir: Path) -> Optional[pd.DataFrame]:
        """Load outlays CSV for a specific mission"""
        filename = f"{snakecase(mission_short_name)}_outlays.csv"
        csv_path = outlays_dir / filename
        
        if csv_path.exists():
            return pd.read_csv(csv_path)
        return None
    
    def load_awards_data(self, outlays_df: Optional[pd.DataFrame]) -> List[dict]:
        """Extract unique award information from outlays DataFrame"""
        if outlays_df is None or outlays_df.empty:
            return []
        
        # Check if required columns exist
        required_cols = ['award_id', 'recipient_name', 'award_description', 'award_usaspending_url']
        if not all(col in outlays_df.columns for col in required_cols):
            return []
        
        # Get unique awards
        unique_awards = outlays_df.drop_duplicates(['award_id'])[required_cols]
        
        awards_data = []
        for _, row in unique_awards.iterrows():
            description = row['award_description']
            # Truncate description to 100 characters with ellipsis if needed
            if len(description) > 100:
                description = description[:100] + '...'
            
            awards_data.append({
                'award_id': row['award_id'],
                'recipient_name': row['recipient_name'],
                'description': description,
                'award_usaspending_url': row['award_usaspending_url']
            })
        
        return awards_data
    
    def create_outlays_chart(self, df: pd.DataFrame) -> str:
        """Create Plotly chart for outlays data comparing current vs prior year by month"""
        if df is None or df.empty:
            return ""
        
        # Step 1: Group by fiscal year and month, sum gross_outlay_amount
        # This aggregates multiple transactions within the same month into a single total
        monthly_data = df.groupby(['reporting_fiscal_year', 'reporting_fiscal_month']).agg({
            'gross_outlay_amount': 'sum'
        }).reset_index()
        # Step 2: Get unique years and sort in descending order
        # This ensures we identify the most recent year as "current" and second-most recent as "prior"
        years = sorted(monthly_data['reporting_fiscal_year'].unique(), reverse=True)
        
        if not years:
            return ""
        
        fig = go.Figure()
        
        if len(years) >= 2:
            # Two or more years available: show current vs prior year comparison
            current_year = years[0]  # Most recent fiscal year
            prior_year = years[1]    # Second most recent fiscal year
            
            # Step 3: Filter data for each year
            # Use .copy() to avoid pandas SettingWithCopyWarning
            current_year_data = monthly_data[monthly_data['reporting_fiscal_year'] == current_year].copy()
            prior_year_data = monthly_data[monthly_data['reporting_fiscal_year'] == prior_year].copy()
            
            # Step 4: Sort by month to ensure chronological order
            # This is critical for cumulative sum to work correctly
            current_year_data = current_year_data.sort_values('reporting_fiscal_month')
            prior_year_data = prior_year_data.sort_values('reporting_fiscal_month')
            
            # Step 5: Calculate cumulative sum for each year
            # This creates a running total that shows how outlays accumulate over the fiscal year
            # For example: if monthly outlays are [100, 200, 150], cumsum gives [100, 300, 450]
            current_year_data['cumulative_amount'] = current_year_data['gross_outlay_amount'].cumsum()
            prior_year_data['cumulative_amount'] = prior_year_data['gross_outlay_amount'].cumsum()
            
            # Step 6: Add prior year trace (dotted line)
            if not prior_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=prior_year_data['reporting_fiscal_month'],
                    y=prior_year_data['cumulative_amount'],  # Use cumulative amount
                    mode='lines+markers',
                    name=f'FY {prior_year}',
                    line=dict(dash='dot', color='#3273dc'),  # Dotted line for prior year
                    marker=dict(color='#3273dc')
                ))
            
            # Step 7: Add current year trace (solid line)
            if not current_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=current_year_data['reporting_fiscal_month'],
                    y=current_year_data['cumulative_amount'],  # Use cumulative amount
                    mode='lines+markers',
                    name=f'FY {current_year}',
                    line=dict(color='#00d1b2'),  # Solid line for current year
                    marker=dict(color='#00d1b2')
                ))
            
            title = 'Cumulative Outlays: Current vs Prior Year'
        else:
            # Only one year available: show just that year's cumulative data
            current_year = years[0]
            current_year_data = monthly_data[monthly_data['reporting_fiscal_year'] == current_year].copy()
            
            # Sort and calculate cumulative sum for single year
            current_year_data = current_year_data.sort_values('reporting_fiscal_month')
            current_year_data['cumulative_amount'] = current_year_data['gross_outlay_amount'].cumsum()
            
            if not current_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=current_year_data['reporting_fiscal_month'],
                    y=current_year_data['cumulative_amount'],
                    mode='lines+markers',
                    name=f'FY {current_year}',
                    line=dict(color='#00d1b2'),
                    marker=dict(color='#00d1b2')
                ))
            
            title = f'Cumulative Outlays for FY {current_year}'
        
        # Step 8: Configure chart layout
        fig.update_layout(
            title=title,
            xaxis_title='Month',
            yaxis_title='Cumulative Amount (USD)',  # Updated to reflect cumulative nature
            template='plotly_white',
            height=400,
            xaxis=dict(
                tickmode='linear',
                tick0=1,
                dtick=1,
                range=[0.5, 12.5]  # Show all 12 months with padding
            )
        )
        
        return fig.to_html(include_plotlyjs=False, full_html=False)
    
    def render_mission_page(self, mission: Mission, outlays_df: Optional[pd.DataFrame]) -> str:
        """Render individual mission page"""
        template = self.env.get_template('mission.html')
        
        # Create chart
        chart_html = self.create_outlays_chart(outlays_df) if outlays_df is not None else ""
        
        # Calculate summary statistics
        total_outlays = 0
        total_obligations = 0
        if outlays_df is not None and not outlays_df.empty:
            total_outlays = outlays_df['gross_outlay_amount'].sum()
            total_obligations = outlays_df['transaction_obligated_amount'].sum()
        
        # Get awards data
        awards_data = self.load_awards_data(outlays_df)
        
        return template.render(
            mission=mission.data,
            chart_html=chart_html,
            total_outlays=total_outlays,
            total_obligations=total_obligations,
            has_funding_data=(outlays_df is not None and not outlays_df.empty),
            awards_data=awards_data
        )
    
    def render_index_page(self, missions: List[Mission]) -> str:
        """Render main index page listing all missions"""
        template = self.env.get_template('index.html')
        return template.render(missions=missions)
    
    def generate_mission_site(self, mission: Mission, outlays_dir: Path, output_dir: Path):
        """Generate site files for a single mission"""
        mission_dir = output_dir / snakecase(mission.acronym)
        mission_dir.mkdir(parents=True, exist_ok=True)
        
        # Load outlays data
        outlays_df = self.load_outlays_data(mission.acronym, outlays_dir)
        
        # Render HTML
        html_content = self.render_mission_page(mission, outlays_df)
        
        # Save HTML
        html_path = mission_dir / 'index.html'
        with open(html_path, 'w') as f:
            f.write(html_content)
        
        # Save mission data as JSON
        data_path = mission_dir / 'data.json'
        with open(data_path, 'w') as f:
            json.dump(mission.data.model_dump(mode='json'), f, indent=2, default=str)
        
        print(f"Generated site for {mission.name} -> {mission_dir}")
        return mission_dir