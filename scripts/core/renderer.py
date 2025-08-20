import json
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader
from casefy import kebabcase, snakecase

from scripts.core.mission import Mission


def format_date_month_year(date_str, format_str='%b %Y'):
    """Convert YYYY-MM-DD date string to 'Mon YYYY' format"""
    if not date_str:
        return date_str
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime(format_str)
    except (ValueError, TypeError):
        return date_str


class SiteGenerator:
    def __init__(self, templates_dir: Path):
        self.templates_dir = Path(templates_dir)
        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=True  # Enable auto-escaping for security against XSS
        )
        # Register custom filters
        self.env.filters['strftime'] = format_date_month_year
        
    def load_obligations_data(self, mission_short_name: str, obligations_dir: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Load obligations CSV for a specific mission and return data with last modified date"""
        filename = f"{snakecase(mission_short_name)}_obligations.csv"
        csv_path = obligations_dir / filename
        
        if csv_path.exists():
            # Get file modification time
            mod_time = datetime.fromtimestamp(csv_path.stat().st_mtime)
            mod_date_str = mod_time.strftime("%Y-%m-%d")
            return pd.read_csv(csv_path), mod_date_str
        return None, None
    
    def load_outlays_data(self, mission_short_name: str, spending_dir: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Load outlays CSV for a specific mission and return data with last modified date"""
        filename = f"{snakecase(mission_short_name)}_outlays.csv"
        csv_path = spending_dir / filename
        
        if csv_path.exists():
            # Get file modification time
            mod_time = datetime.fromtimestamp(csv_path.stat().st_mtime)
            mod_date_str = mod_time.strftime("%Y-%m-%d")
            return pd.read_csv(csv_path), mod_date_str
        return None, None
    
    def load_awards_data(self, obligations_df: Optional[pd.DataFrame]) -> List[dict]:
        """Extract unique award information from obligations DataFrame"""
        if obligations_df is None or obligations_df.empty:
            return []
        
        # Check if required columns exist
        required_cols = ['award_id', 'recipient_name', 'award_description', 'award_usaspending_url']
        if not all(col in obligations_df.columns for col in required_cols):
            return []
        
        # Get unique awards
        unique_awards = obligations_df.drop_duplicates(['award_id'])[required_cols]
        
        awards_data = []
        for _, row in unique_awards.iterrows():
            description = row['award_description']
            short_description = description
            # Truncate description to 300 characters with ellipsis if needed
            if len(description) > 300:
                short_description = description[:300] + '...'
            
            awards_data.append({
                'award_id': row['award_id'],
                'recipient_name': row['recipient_name'],
                'description': short_description,
                'full_description': description,
                'award_usaspending_url': row['award_usaspending_url']
            })
        
        return awards_data
    
    def create_obligations_chart(self, df: pd.DataFrame) -> str:
        """Create Plotly chart for obligations data comparing current vs prior year by month"""
        if df is None or df.empty:
            return ""
        
        # Step 1: Group by fiscal year and month, sum transaction_obligated_amount
        # This aggregates multiple transactions within the same month into a single total
        monthly_data = df.groupby(['reporting_fiscal_year', 'reporting_fiscal_month']).agg({
            'transaction_obligated_amount': 'sum'
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
            # This creates a running total that shows how obligations accumulate over the fiscal year
            # For example: if monthly obligations are [100, 200, 150], cumsum gives [100, 300, 450]
            current_year_data['cumulative_amount'] = current_year_data['transaction_obligated_amount'].cumsum()
            prior_year_data['cumulative_amount'] = prior_year_data['transaction_obligated_amount'].cumsum()
            
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
            
            title = 'Cumulative Obligations: Current vs Prior Year'
        else:
            # Only one year available: show just that year's cumulative data
            current_year = years[0]
            current_year_data = monthly_data[monthly_data['reporting_fiscal_year'] == current_year].copy()
            
            # Sort and calculate cumulative sum for single year
            current_year_data = current_year_data.sort_values('reporting_fiscal_month')
            current_year_data['cumulative_amount'] = current_year_data['transaction_obligated_amount'].cumsum()
            
            if not current_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=current_year_data['reporting_fiscal_month'],
                    y=current_year_data['cumulative_amount'],
                    mode='lines+markers',
                    name=f'FY {current_year}',
                    line=dict(color='#00d1b2'),
                    marker=dict(color='#00d1b2')
                ))
            
            title = f'Cumulative Obligations for FY {current_year}'
        
        # Step 8: Configure chart layout
        fig.update_layout(
            title=title,
            xaxis_title='Month',
            yaxis_title='Cumulative Obligations (USD)',  # Updated to reflect cumulative nature
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
    
    def create_outlays_chart(self, df: pd.DataFrame) -> str:
        """Create Plotly chart for outlays data comparing current vs prior year by fiscal period"""
        if df is None or df.empty:
            return ""
        
        # Step 1: Group by fiscal year and fiscal period, sum monthly_outlay
        # This aggregates multiple outlays within the same fiscal period into a single total
        monthly_data = df.groupby(['fiscal_year', 'fiscal_period']).agg({
            'monthly_outlay': 'sum'
        }).reset_index()
        
        # Step 2: Get unique years and sort in descending order
        # This ensures we identify the most recent year as "current" and second-most recent as "prior"
        years = sorted(monthly_data['fiscal_year'].unique(), reverse=True)
        
        if not years:
            return ""
        
        fig = go.Figure()
        
        if len(years) >= 2:
            # Two or more years available: show current vs prior year comparison
            current_year = years[0]  # Most recent fiscal year
            prior_year = years[1]    # Second most recent fiscal year
            
            # Step 3: Filter data for each year
            # Use .copy() to avoid pandas SettingWithCopyWarning
            current_year_data = monthly_data[monthly_data['fiscal_year'] == current_year].copy()
            prior_year_data = monthly_data[monthly_data['fiscal_year'] == prior_year].copy()
            
            # Step 4: Sort by fiscal period to ensure chronological order
            # This is critical for cumulative sum to work correctly
            current_year_data = current_year_data.sort_values('fiscal_period')
            prior_year_data = prior_year_data.sort_values('fiscal_period')
            
            # Step 5: Calculate cumulative sum for each year
            # This creates a running total that shows how outlays accumulate over the fiscal year
            current_year_data['cumulative_amount'] = current_year_data['monthly_outlay'].cumsum()
            prior_year_data['cumulative_amount'] = prior_year_data['monthly_outlay'].cumsum()
            
            # Step 6: Add prior year trace (dotted line)
            if not prior_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=prior_year_data['fiscal_period'],
                    y=prior_year_data['cumulative_amount'],  # Use cumulative amount
                    mode='lines+markers',
                    name=f'FY {prior_year}',
                    line=dict(dash='dot', color='#3273dc'),  # Dotted line for prior year
                    marker=dict(color='#3273dc')
                ))
            
            # Step 7: Add current year trace (solid line)
            if not current_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=current_year_data['fiscal_period'],
                    y=current_year_data['cumulative_amount'],  # Use cumulative amount
                    mode='lines+markers',
                    name=f'FY {current_year}',
                    line=dict(color='#ff3860'),  # Red solid line for current year outlays
                    marker=dict(color='#ff3860')
                ))
            
            title = 'Cumulative Outlays: Current vs Prior Year'
        else:
            # Only one year available: show just that year's cumulative data
            current_year = years[0]
            current_year_data = monthly_data[monthly_data['fiscal_year'] == current_year].copy()
            
            # Sort and calculate cumulative sum for single year
            current_year_data = current_year_data.sort_values('fiscal_period')
            current_year_data['cumulative_amount'] = current_year_data['monthly_outlay'].cumsum()
            
            if not current_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=current_year_data['fiscal_period'],
                    y=current_year_data['cumulative_amount'],
                    mode='lines+markers',
                    name=f'FY {current_year}',
                    line=dict(color='#ff3860'),  # Red for outlays
                    marker=dict(color='#ff3860')
                ))
            
            title = f'Cumulative Outlays for FY {current_year}'
        
        # Step 8: Configure chart layout
        fig.update_layout(
            title=title,
            xaxis_title='Fiscal Period',
            yaxis_title='Cumulative Outlays (USD)',  # Updated to reflect cumulative nature
            template='plotly_white',
            height=400,
            xaxis=dict(
                tickmode='linear',
                tick0=1,
                dtick=1,
                range=[0.5, 12.5]  # Show all 12 periods with padding
            )
        )
        
        return fig.to_html(include_plotlyjs=False, full_html=False)
    
    def render_mission_page(self, mission: Mission, obligations_df: Optional[pd.DataFrame], outlays_df: Optional[pd.DataFrame] = None, obligations_last_updated: Optional[str] = None, outlays_last_updated: Optional[str] = None) -> str:
        """Render individual mission page"""
        template = self.env.get_template('mission.html')
        
        # Create charts
        chart_html = self.create_obligations_chart(obligations_df) if obligations_df is not None else ""
        outlays_chart_html = self.create_outlays_chart(outlays_df) if outlays_df is not None else ""
        
        # Calculate summary statistics
        total_obligations = 0
        if obligations_df is not None and not obligations_df.empty:
            total_obligations = obligations_df['transaction_obligated_amount'].sum()
            
        total_outlays = 0
        outlays_award_count = 0
        if outlays_df is not None and not outlays_df.empty:
            total_outlays = outlays_df['monthly_outlay'].sum()
            # Count unique awards in outlays data
            outlays_award_count = outlays_df['award_id'].nunique()
        
        # Get awards data
        awards_data = self.load_awards_data(obligations_df)
        
        return template.render(
            mission=mission.data.model_dump(mode='json'),
            chart_html=chart_html,
            outlays_chart_html=outlays_chart_html,
            total_obligations=total_obligations,
            total_outlays=total_outlays,
            has_funding_data=(obligations_df is not None and not obligations_df.empty),
            has_outlays_data=(outlays_df is not None and not outlays_df.empty),
            outlays_award_count=outlays_award_count,
            awards_data=awards_data,
            obligations_last_updated=obligations_last_updated,
            outlays_last_updated=outlays_last_updated
        )
    
    def render_index_page(self, missions: List[Mission]) -> str:
        """Render main index page listing all missions"""
        template = self.env.get_template('index.html')
        # Convert mission data to serializable format for template
        missions_data = []
        for mission in missions:
            missions_data.append({
                'name': mission.name,
                'acronym': mission.acronym,
                'data': mission.data.model_dump(mode='json')
            })
        return template.render(missions=missions_data)
    
    def generate_mission_site(self, mission: Mission, spending_dir: Path, output_dir: Path):
        """Generate site files for a single mission"""
        mission_dir = output_dir / kebabcase(mission.acronym)
        mission_dir.mkdir(parents=True, exist_ok=True)
        
        # Load data
        obligations_df, obligations_last_updated = self.load_obligations_data(mission.acronym, spending_dir)
        outlays_df, outlays_last_updated = self.load_outlays_data(mission.acronym, spending_dir)
        
        # Render HTML
        html_content = self.render_mission_page(mission, obligations_df, outlays_df, obligations_last_updated, outlays_last_updated)
        
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