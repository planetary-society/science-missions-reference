import json
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from jinja2 import Environment, FileSystemLoader
from casefy import kebabcase, snakecase
from markdown_it import MarkdownIt

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


def fiscal_month_to_abbr(fiscal_month):
    """Convert fiscal month number (1-12) to calendar month abbreviation.
    
    Fiscal year starts in October: 1=Oct, 2=Oct/Nov, ..., 12=Sep
    Special case: fiscal month 2 shows as Oct/Nov since USA Spending
    doesn't report October data separately, combining it with November.
    """
    if not fiscal_month or fiscal_month < 1 or fiscal_month > 12:
        return ""
    
    # Direct mapping for fiscal months to display labels
    # Fiscal month 2 is special case showing Oct/Nov combined data
    fiscal_month_abbrs = {
        1: 'Oct',
        2: 'Oct/Nov', 
        3: 'Dec',
        4: 'Jan',
        5: 'Feb',
        6: 'Mar',
        7: 'Apr',
        8: 'May',
        9: 'Jun',
        10: 'Jul',
        11: 'Aug',
        12: 'Sep'
    }
    
    return fiscal_month_abbrs.get(fiscal_month, "")


class SiteGenerator:
    def __init__(self, templates_dir: Path):
        self.templates_dir = Path(templates_dir)
        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=True  # Enable auto-escaping for security against XSS
        )
        # Initialize markdown parser
        self.md = MarkdownIt()
        
        # Register custom filters
        self.env.filters['strftime'] = format_date_month_year
        self.env.filters['markdown'] = self._render_markdown
        
        # Define organization brand colors
        self.brand_colors = [
            "#037CC2",  # Primary blue
            "#643788",  # Purple
            "#FF5D47",  # Red
            "#80BDE0",  # Light blue
            "#B19BC3",  # Light purple
            "#414141"   # Dark gray
        ]
        
        # Define color mappings for different chart types
        self.chart_colors = {
            'obligations': {
                'current': self.brand_colors[0],  # Blue
                'prior': self.brand_colors[1]      # Purple
            },
            'outlays': {
                'current': self.brand_colors[0],
                'prior': self.brand_colors[1]
            }
        }
        
        # Create TPS brand template
        self.tps_template = go.layout.Template()
        
        # Configure layout defaults
        self.tps_template.layout = go.Layout(
            font=dict(
                family="Poppins, Arial, sans-serif",
                color="#414141"
            ),
            plot_bgcolor="#F5F5F5",
            paper_bgcolor="#F5F5F5",
            xaxis=dict(
                showgrid=True,
                gridwidth=0.6,
                gridcolor="rgba(65, 65, 65, 0.5)",
                linecolor="#414141",
                linewidth=2,
                tickcolor="#414141",
                tickmode='linear',
                tick0=1,
                dtick=1,
                showline=True,
                mirror=False,
                zeroline=False
            ),
            yaxis=dict(
                showgrid=True,
                gridwidth=0.6,
                gridcolor="rgba(65, 65, 65, 0.5)",
                linecolor="#414141",
                linewidth=0,  # Hide left spine
                tickcolor="#414141",
                showline=False,
                mirror=False,
                zeroline=False,
                rangemode='tozero'  # Always start at 0
            ),
            margin=dict(t=20, b=60, l=60, r=30),
            showlegend=False,
            hovermode='x unified',
            autosize=True  # Responsive sizing
        )
        
        # Configure annotation defaults
        self.tps_template.layout.annotationdefaults = dict(
            font=dict(
                family="Poppins, Arial, sans-serif",
                size=12,
                color="#414141"
            ),
            bgcolor="#FFFFFF",
            borderwidth=2,
            borderpad=4,
            showarrow=False
        )
        
        # Configure default scatter/line trace styles
        self.tps_template.data.scatter = [
            go.Scatter(
                marker=dict(size=8),
                line=dict(width=4),
                mode='lines+markers'
            )
        ]
        
        self.tps_template.layout.shapes = [{'line': {'width': 4}}]
        
        # Register the template
        pio.templates["tps"] = self.tps_template
    
    def _render_markdown(self, text: str) -> str:
        """Render markdown text to HTML"""
        if not text:
            return ""
        return self.md.render(text)
        
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
        annotations = []  # List to store annotations
        
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
                    line=dict(dash='dot', color=self.chart_colors['obligations']['prior']),
                    marker=dict(color=self.chart_colors['obligations']['prior'], size=8),
                    showlegend=False
                ))
                
                # Add annotation for prior year at the last point
                last_x = prior_year_data['reporting_fiscal_month'].iloc[-1]
                last_y = prior_year_data['cumulative_amount'].iloc[-1]
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {prior_year}</b>",
                    xanchor='center',
                    yanchor='bottom',
                    yshift=10,
                    font=dict(weight="bold"),
                    bordercolor=self.chart_colors['obligations']['prior']
                ))
            
            # Step 7: Add current year trace (solid line)
            if not current_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=current_year_data['reporting_fiscal_month'],
                    y=current_year_data['cumulative_amount'],  # Use cumulative amount
                    mode='lines+markers',
                    name=f'FY {current_year}',
                    line=dict(color=self.chart_colors['obligations']['current'], width=4),
                    marker=dict(color=self.chart_colors['obligations']['current'], size=8),
                    showlegend=False
                ))
                
                # Add annotation for current year at the last point
                last_x = current_year_data['reporting_fiscal_month'].iloc[-1]
                last_y = current_year_data['cumulative_amount'].iloc[-1]
                
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {current_year}</b>",
                    xanchor='left',
                    yanchor='middle',
                    xshift=10,
                    font=dict(weight="bold"),
                    bordercolor=self.chart_colors['obligations']['current']
                ))
            
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
                    line=dict(color=self.chart_colors['obligations']['current']),
                    marker=dict(color=self.chart_colors['obligations']['current'], size=8),
                    showlegend=False
                ))
                
                # Add annotation for single year at the last point
                last_x = current_year_data['reporting_fiscal_month'].iloc[-1]
                last_y = current_year_data['cumulative_amount'].iloc[-1]
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {current_year}</b>",
                    xanchor='center',
                    yanchor='bottom',
                    yshift=10,
                    font=dict(weight="bold"),
                    bordercolor=self.chart_colors['obligations']['current']
                ))
                    
        # Step 8: Configure chart layout using TPS template
        # Generate month abbreviations for x-axis labels
        month_labels = [fiscal_month_to_abbr(i) for i in range(2, 13)]
        
        fig.update_layout(
            template="tps",
            yaxis_title=dict(
                text='Cumulative Obligations (USD)',
                font=dict(size=12, color="#414141")
            ),
            annotations=annotations
        )
        
        # Configure x-axis with custom tick labels for month abbreviations
        fig.update_xaxes(
            range=[1.9, 12.1],  # Extra space on both sides for annotations
            tickvals=list(range(2, 13)),  # Tick positions (2-12)
            ticktext=month_labels,  # Month abbreviations (Oct-Sep)
            tickmode='array'  # Use custom tick positions and labels
        )
        fig.update_yaxes(rangemode='tozero')  # Always start at 0
        
        return fig.to_html(include_plotlyjs=False, full_html=False, config={'staticPlot': True})
    
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
        annotations = []  # List to store annotations
        
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
                    line=dict(dash='dot', color=self.chart_colors['outlays']['prior']),
                    marker=dict(color=self.chart_colors['outlays']['prior'], size=8),
                    showlegend=False
                ))
                
                # Add annotation for prior year at the last point
                last_x = prior_year_data['fiscal_period'].iloc[-1]
                last_y = prior_year_data['cumulative_amount'].iloc[-1]
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {prior_year}</b>",
                    xanchor='center',
                    yanchor='bottom',
                    yshift=10,
                    font=dict(weight="bold"),
                    bordercolor=self.chart_colors['outlays']['prior']
                ))
            
            # Step 7: Add current year trace (solid line)
            if not current_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=current_year_data['fiscal_period'],
                    y=current_year_data['cumulative_amount'],  # Use cumulative amount
                    mode='lines+markers',
                    name=f'FY {current_year}',
                    line=dict(color=self.chart_colors['outlays']['current']),
                    marker=dict(color=self.chart_colors['outlays']['current'], size=8),
                    showlegend=False
                ))
                
                # Add annotation for current year at the last point
                last_x = current_year_data['fiscal_period'].iloc[-1]
                last_y = current_year_data['cumulative_amount'].iloc[-1]
                
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {current_year}</b>",
                    xanchor='left',
                    yanchor='middle',
                    xshift=10,
                    font=dict(weight="bold"),
                    bordercolor=self.chart_colors['outlays']['current']
                ))
            
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
                    line=dict(color=self.chart_colors['outlays']['current']),
                    marker=dict(color=self.chart_colors['outlays']['current'], size=8),
                    showlegend=False
                ))
                
                # Add annotation for single year at the last point
                last_x = current_year_data['fiscal_period'].iloc[-1]
                last_y = current_year_data['cumulative_amount'].iloc[-1]
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {current_year}</b>",
                    xanchor='center',
                    yanchor='bottom',
                    yshift=10,
                    font=dict(weight="bold"),
                    bordercolor=self.chart_colors['outlays']['current']
                ))
            

        
        # Step 8: Configure chart layout using TPS template
        # Generate month abbreviations for x-axis labels
        month_labels = [fiscal_month_to_abbr(i) for i in range(2, 13)]
        
        fig.update_layout(
            template="tps",
            yaxis_title=dict(
                text='Cumulative Outlays (USD)',
                font=dict(size=12, color="#414141")
            ),
            annotations=annotations
        )
        
        # Configure x-axis with custom tick labels for month abbreviations
        fig.update_xaxes(
            range=[1.9, 12.1],  # Extra space on both sides for annotations
            tickvals=list(range(2, 13)),  # Tick positions (1-12)
            ticktext=month_labels,  # Month abbreviations (Oct-Sep)
            tickmode='array'  # Use custom tick positions and labels
        )
        fig.update_yaxes(rangemode='tozero')  # Always start at 0
        
        return fig.to_html(include_plotlyjs=False, full_html=False, config={'staticPlot': True})
    
    def calculate_obligations_summary(self, obligations_df: pd.DataFrame) -> dict:
        """Calculate obligations summary metrics for current and prior fiscal years"""
        if obligations_df is None or obligations_df.empty:
            return {}
        
        # Group by fiscal year and month, sum obligations
        monthly_data = obligations_df.groupby(['reporting_fiscal_year', 'reporting_fiscal_month']).agg({
            'transaction_obligated_amount': 'sum'
        }).reset_index()
        
        # Get unique years and sort in descending order
        years = sorted(monthly_data['reporting_fiscal_year'].unique(), reverse=True)
        
        if len(years) < 2:
            # Need at least 2 years for comparison
            return {}
        
        current_year = years[0]  # Most recent fiscal year
        prior_year = years[1]    # Second most recent fiscal year
        
        # Filter data for each year
        current_year_data = monthly_data[monthly_data['reporting_fiscal_year'] == current_year].copy()
        prior_year_data = monthly_data[monthly_data['reporting_fiscal_year'] == prior_year].copy()
        
        # Sort by month
        current_year_data = current_year_data.sort_values('reporting_fiscal_month')
        prior_year_data = prior_year_data.sort_values('reporting_fiscal_month')
        
        # Calculate prior fiscal year total
        prior_year_total = prior_year_data['transaction_obligated_amount'].sum()
        
        # Calculate current fiscal year running sum
        current_year_data['cumulative_amount'] = current_year_data['transaction_obligated_amount'].cumsum()
        current_year_running_sum = current_year_data['cumulative_amount'].iloc[-1] if not current_year_data.empty else 0
        
        # Find comparable period in prior year (same month range)
        max_current_month = current_year_data['reporting_fiscal_month'].max() if not current_year_data.empty else 0
        prior_year_comparable = prior_year_data[
            prior_year_data['reporting_fiscal_month'] <= max_current_month
        ].copy()
        
        if not prior_year_comparable.empty:
            prior_year_comparable['cumulative_amount'] = prior_year_comparable['transaction_obligated_amount'].cumsum()
            prior_year_comparable_sum = prior_year_comparable['cumulative_amount'].iloc[-1]
            delta = current_year_running_sum - prior_year_comparable_sum
        else:
            prior_year_comparable_sum = 0
            delta = current_year_running_sum
        
        # Convert to millions and round
        return {
            'prior_year_total_millions': (prior_year_total / 1_000_000),
            'prior_year_comparable_sum_millions': (prior_year_comparable_sum / 1_000_000),
            'current_year_running_sum_millions': (current_year_running_sum / 1_000_000),
            'delta_millions': (delta / 1_000_000),
            'current_year': current_year,
            'prior_year': prior_year,
            'max_current_month': max_current_month,
            'max_current_month_abbr': fiscal_month_to_abbr(max_current_month)
        }
    
    def calculate_outlays_summary(self, outlays_df: pd.DataFrame) -> dict:
        """Calculate outlays summary metrics for current and prior fiscal years"""
        if outlays_df is None or outlays_df.empty:
            return {}
        
        # Group by fiscal year and fiscal period, sum monthly_outlay
        monthly_data = outlays_df.groupby(['fiscal_year', 'fiscal_period']).agg({
            'monthly_outlay': 'sum'
        }).reset_index()
        
        # Get unique years and sort in descending order
        years = sorted(monthly_data['fiscal_year'].unique(), reverse=True)
        
        if len(years) < 2:
            # Need at least 2 years for comparison
            return {}
        
        current_year = years[0]  # Most recent fiscal year
        prior_year = years[1]    # Second most recent fiscal year
        
        # Filter data for each year
        current_year_data = monthly_data[monthly_data['fiscal_year'] == current_year].copy()
        prior_year_data = monthly_data[monthly_data['fiscal_year'] == prior_year].copy()
        
        # Sort by fiscal period
        current_year_data = current_year_data.sort_values('fiscal_period')
        prior_year_data = prior_year_data.sort_values('fiscal_period')
        
        # Calculate prior fiscal year total
        prior_year_total = prior_year_data['monthly_outlay'].sum()
        
        # Calculate current fiscal year running sum
        current_year_data['cumulative_amount'] = current_year_data['monthly_outlay'].cumsum()
        current_year_running_sum = current_year_data['cumulative_amount'].iloc[-1] if not current_year_data.empty else 0
        
        # Find comparable period in prior year (same fiscal period range)
        max_current_period = current_year_data['fiscal_period'].max() if not current_year_data.empty else 0
        prior_year_comparable = prior_year_data[
            prior_year_data['fiscal_period'] <= max_current_period
        ].copy()
        
        if not prior_year_comparable.empty:
            prior_year_comparable['cumulative_amount'] = prior_year_comparable['monthly_outlay'].cumsum()
            prior_year_comparable_sum = prior_year_comparable['cumulative_amount'].iloc[-1]
            delta = current_year_running_sum - prior_year_comparable_sum
        else:
            prior_year_comparable_sum = 0
            delta = current_year_running_sum
        
        # Convert to millions and round
        return {
            'prior_year_total_millions': round(prior_year_total / 1_000_000),
            'prior_year_comparable_sum_millions': round(prior_year_comparable_sum / 1_000_000),
            'current_year_running_sum_millions': round(current_year_running_sum / 1_000_000),
            'delta_millions': round(delta / 1_000_000),
            'current_year': current_year,
            'prior_year': prior_year,
            'max_current_period': max_current_period,
            'max_current_period_abbr': fiscal_month_to_abbr(max_current_period)
        }
    
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
        
        # Calculate obligations summary
        obligations_summary = self.calculate_obligations_summary(obligations_df) if obligations_df is not None else {}
        
        # Calculate outlays summary
        outlays_summary = self.calculate_outlays_summary(outlays_df) if outlays_df is not None else {}
        
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
            outlays_last_updated=outlays_last_updated,
            obligations_summary=obligations_summary,
            outlays_summary=outlays_summary
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