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

    def check_url_exists(self, url: str) -> bool:
        """Check if a URL exists by making a HEAD request"""
        try:
            import requests
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
            f"{stem}_mobile.svg",
            f"{stem}.pptx",
            f"{stem}.csv"
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
            # Get file modification time
            mod_time = datetime.fromtimestamp(csv_path.stat().st_mtime)
            mod_date_str = mod_time.strftime("%Y-%m-%d")
            return pd.read_csv(csv_path), mod_date_str
        return None, None

    def load_obligations_summary_data(self, mission_short_name: str, obligations_dir: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Load obligations summary CSV for a specific mission and return data with last modified date"""
        filename = f"{snakecase(mission_short_name)}_obligations_summary.csv"
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

    def load_outlays_summary_data(self, mission_short_name: str, spending_dir: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Load outlays summary CSV for a specific mission and return data with last modified date"""
        filename = f"{snakecase(mission_short_name)}_outlays_summary.csv"
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
    
    def _create_cumulative_chart(self, df: pd.DataFrame, 
                                  year_col: str, period_col: str, value_col: str,
                                  chart_type: str, y_axis_title: str) -> str:
        """Generic method to create cumulative charts for fiscal data.
        
        Args:
            df: DataFrame with fiscal data
            year_col: Column name for fiscal year
            period_col: Column name for fiscal period/month
            value_col: Column name for values to sum
            chart_type: 'obligations' or 'outlays' for color selection
            y_axis_title: Title for y-axis
        """
        if df is None or df.empty:
            return ""
        
        # Group by fiscal year and period, sum values
        monthly_data = df.groupby([year_col, period_col]).agg({
            value_col: 'sum'
        }).reset_index()
        
        # Get unique years and sort in descending order
        years = sorted(monthly_data[year_col].unique(), reverse=True)
        
        if not years:
            return ""
        
        fig = go.Figure()
        annotations = []
        colors = self.chart_colors[chart_type]
        
        if len(years) >= 2:
            # Two or more years available: show current vs prior year comparison
            current_year = years[0]
            prior_year = years[1]
            
            # Filter and sort data for each year
            current_year_data = monthly_data[monthly_data[year_col] == current_year].copy()
            prior_year_data = monthly_data[monthly_data[year_col] == prior_year].copy()
            
            current_year_data = current_year_data.sort_values(period_col)
            prior_year_data = prior_year_data.sort_values(period_col)
            
            # Calculate cumulative sum
            current_year_data['cumulative_amount'] = current_year_data[value_col].cumsum()
            prior_year_data['cumulative_amount'] = prior_year_data[value_col].cumsum()
            
            # Add prior year trace (dotted line)
            if not prior_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=prior_year_data[period_col],
                    y=prior_year_data['cumulative_amount'],
                    mode='lines+markers',
                    name=f'FY {prior_year}',
                    line=dict(dash='dot', color=colors['prior']),
                    marker=dict(color=colors['prior'], size=8),
                    showlegend=False
                ))
                
                # Add annotation for prior year
                last_x = prior_year_data[period_col].iloc[-1]
                last_y = prior_year_data['cumulative_amount'].iloc[-1]
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {prior_year}</b>",
                    xanchor='center',
                    yanchor='bottom',
                    yshift=10,
                    font=dict(weight="bold"),
                    bordercolor=colors['prior']
                ))
            
            # Add current year trace (solid line)
            if not current_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=current_year_data[period_col],
                    y=current_year_data['cumulative_amount'],
                    mode='lines+markers',
                    name=f'FY {current_year}',
                    line=dict(color=colors['current'], width=4),
                    marker=dict(color=colors['current'], size=8),
                    showlegend=False
                ))
                
                # Add annotation for current year
                last_x = current_year_data[period_col].iloc[-1]
                last_y = current_year_data['cumulative_amount'].iloc[-1]
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {current_year}</b>",
                    xanchor='left',
                    yanchor='middle',
                    xshift=10,
                    font=dict(weight="bold"),
                    bordercolor=colors['current']
                ))
        else:
            # Only one year available
            current_year = years[0]
            current_year_data = monthly_data[monthly_data[year_col] == current_year].copy()
            
            current_year_data = current_year_data.sort_values(period_col)
            current_year_data['cumulative_amount'] = current_year_data[value_col].cumsum()
            
            if not current_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=current_year_data[period_col],
                    y=current_year_data['cumulative_amount'],
                    mode='lines+markers',
                    name=f'FY {current_year}',
                    line=dict(color=colors['current']),
                    marker=dict(color=colors['current'], size=8),
                    showlegend=False
                ))
                
                # Add annotation for single year
                last_x = current_year_data[period_col].iloc[-1]
                last_y = current_year_data['cumulative_amount'].iloc[-1]
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {current_year}</b>",
                    xanchor='center',
                    yanchor='bottom',
                    yshift=10,
                    font=dict(weight="bold"),
                    bordercolor=colors['current']
                ))
        
        # Configure chart layout
        month_labels = [fiscal_month_to_abbr(i) for i in range(2, 13)]
        
        fig.update_layout(
            template="tps",
            yaxis_title=dict(
                text=y_axis_title,
                font=dict(size=12, color="#414141")
            ),
            annotations=annotations
        )
        
        # Configure x-axis with custom tick labels
        fig.update_xaxes(
            range=[1.9, 12.1],
            tickvals=list(range(2, 13)),
            ticktext=month_labels,
            tickmode='array'
        )
        fig.update_yaxes(rangemode='tozero')
        
        return fig.to_html(include_plotlyjs=False, full_html=False, config={'staticPlot': True})
    
    def create_obligations_chart(self, df: pd.DataFrame) -> str:
        """Create Plotly chart for obligations data comparing current vs prior year by month"""
        return self._create_cumulative_chart(
            df=df,
            year_col='reporting_fiscal_year',
            period_col='reporting_fiscal_month',
            value_col='transaction_obligated_amount',
            chart_type='obligations',
            y_axis_title='Cumulative Obligations (USD)'
        )

    def create_obligations_chart_from_summary(self, summary_df: pd.DataFrame) -> str:
        """Create Plotly chart for obligations data using pre-aggregated summary data"""
        if summary_df is None or summary_df.empty:
            return ""

        # Get unique years and sort in descending order
        years = sorted(summary_df['reporting_fiscal_year'].unique(), reverse=True)

        if not years:
            return ""

        fig = go.Figure()
        annotations = []
        colors = self.chart_colors['obligations']

        if len(years) >= 2:
            # Two or more years available: show current vs prior year comparison
            current_year = years[0]
            prior_year = years[1]

            # Filter and sort data for each year
            current_year_data = summary_df[summary_df['reporting_fiscal_year'] == current_year].copy()
            prior_year_data = summary_df[summary_df['reporting_fiscal_year'] == prior_year].copy()

            current_year_data = current_year_data.sort_values('reporting_fiscal_month')
            prior_year_data = prior_year_data.sort_values('reporting_fiscal_month')

            # Add prior year trace (dotted line)
            if not prior_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=prior_year_data['reporting_fiscal_month'],
                    y=prior_year_data['cumulative_obligations'],
                    mode='lines+markers',
                    name=f'FY {prior_year}',
                    line=dict(dash='dot', color=colors['prior']),
                    marker=dict(color=colors['prior'], size=8),
                    showlegend=False
                ))

                # Add annotation for prior year
                last_x = prior_year_data['reporting_fiscal_month'].iloc[-1]
                last_y = prior_year_data['cumulative_obligations'].iloc[-1]
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {prior_year}</b>",
                    xanchor='center',
                    yanchor='bottom',
                    yshift=10,
                    font=dict(weight="bold"),
                    bordercolor=colors['prior']
                ))

            # Add current year trace (solid line)
            if not current_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=current_year_data['reporting_fiscal_month'],
                    y=current_year_data['cumulative_obligations'],
                    mode='lines+markers',
                    name=f'FY {current_year}',
                    line=dict(color=colors['current'], width=4),
                    marker=dict(color=colors['current'], size=8),
                    showlegend=False
                ))

                # Add annotation for current year
                last_x = current_year_data['reporting_fiscal_month'].iloc[-1]
                last_y = current_year_data['cumulative_obligations'].iloc[-1]
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {current_year}</b>",
                    xanchor='left',
                    yanchor='middle',
                    xshift=10,
                    font=dict(weight="bold"),
                    bordercolor=colors['current']
                ))
        else:
            # Only one year available
            current_year = years[0]
            current_year_data = summary_df[summary_df['reporting_fiscal_year'] == current_year].copy()

            current_year_data = current_year_data.sort_values('reporting_fiscal_month')

            if not current_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=current_year_data['reporting_fiscal_month'],
                    y=current_year_data['cumulative_obligations'],
                    mode='lines+markers',
                    name=f'FY {current_year}',
                    line=dict(color=colors['current']),
                    marker=dict(color=colors['current'], size=8),
                    showlegend=False
                ))

                # Add annotation for single year
                last_x = current_year_data['reporting_fiscal_month'].iloc[-1]
                last_y = current_year_data['cumulative_obligations'].iloc[-1]
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {current_year}</b>",
                    xanchor='center',
                    yanchor='bottom',
                    yshift=10,
                    font=dict(weight="bold"),
                    bordercolor=colors['current']
                ))

        # Configure chart layout
        month_labels = [fiscal_month_to_abbr(i) for i in range(2, 13)]

        fig.update_layout(
            template="tps",
            yaxis_title=dict(
                text='Cumulative Obligations (USD)',
                font=dict(size=12, color="#414141")
            ),
            annotations=annotations
        )

        # Configure x-axis with custom tick labels
        fig.update_xaxes(
            range=[1.9, 12.1],
            tickvals=list(range(2, 13)),
            ticktext=month_labels,
            tickmode='array'
        )
        fig.update_yaxes(rangemode='tozero')

        return fig.to_html(include_plotlyjs=False, full_html=False, config={'staticPlot': True})
    
    def create_outlays_chart(self, df: pd.DataFrame) -> str:
        """Create Plotly chart for outlays data comparing current vs prior year by fiscal period"""
        return self._create_cumulative_chart(
            df=df,
            year_col='fiscal_year',
            period_col='fiscal_period',
            value_col='monthly_outlay',
            chart_type='outlays',
            y_axis_title='Cumulative Outlays (USD)'
        )

    def create_outlays_chart_from_summary(self, summary_df: pd.DataFrame) -> str:
        """Create Plotly chart for outlays data using pre-aggregated summary data"""
        if summary_df is None or summary_df.empty:
            return ""

        # Get unique years and sort in descending order
        years = sorted(summary_df['fiscal_year'].unique(), reverse=True)

        if not years:
            return ""

        fig = go.Figure()
        annotations = []
        colors = self.chart_colors['outlays']

        if len(years) >= 2:
            # Two or more years available: show current vs prior year comparison
            current_year = years[0]
            prior_year = years[1]

            # Filter and sort data for each year
            current_year_data = summary_df[summary_df['fiscal_year'] == current_year].copy()
            prior_year_data = summary_df[summary_df['fiscal_year'] == prior_year].copy()

            current_year_data = current_year_data.sort_values('fiscal_period')
            prior_year_data = prior_year_data.sort_values('fiscal_period')

            # Add prior year trace (dotted line)
            if not prior_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=prior_year_data['fiscal_period'],
                    y=prior_year_data['cumulative_outlay'],
                    mode='lines+markers',
                    name=f'FY {prior_year}',
                    line=dict(dash='dot', color=colors['prior']),
                    marker=dict(color=colors['prior'], size=8),
                    showlegend=False
                ))

                # Add annotation for prior year
                last_x = prior_year_data['fiscal_period'].iloc[-1]
                last_y = prior_year_data['cumulative_outlay'].iloc[-1]
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {prior_year}</b>",
                    xanchor='center',
                    yanchor='bottom',
                    yshift=10,
                    font=dict(weight="bold"),
                    bordercolor=colors['prior']
                ))

            # Add current year trace (solid line)
            if not current_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=current_year_data['fiscal_period'],
                    y=current_year_data['cumulative_outlay'],
                    mode='lines+markers',
                    name=f'FY {current_year}',
                    line=dict(color=colors['current'], width=4),
                    marker=dict(color=colors['current'], size=8),
                    showlegend=False
                ))

                # Add annotation for current year
                last_x = current_year_data['fiscal_period'].iloc[-1]
                last_y = current_year_data['cumulative_outlay'].iloc[-1]
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {current_year}</b>",
                    xanchor='left',
                    yanchor='middle',
                    xshift=10,
                    font=dict(weight="bold"),
                    bordercolor=colors['current']
                ))
        else:
            # Only one year available
            current_year = years[0]
            current_year_data = summary_df[summary_df['fiscal_year'] == current_year].copy()

            current_year_data = current_year_data.sort_values('fiscal_period')

            if not current_year_data.empty:
                fig.add_trace(go.Scatter(
                    x=current_year_data['fiscal_period'],
                    y=current_year_data['cumulative_outlay'],
                    mode='lines+markers',
                    name=f'FY {current_year}',
                    line=dict(color=colors['current']),
                    marker=dict(color=colors['current'], size=8),
                    showlegend=False
                ))

                # Add annotation for single year
                last_x = current_year_data['fiscal_period'].iloc[-1]
                last_y = current_year_data['cumulative_outlay'].iloc[-1]
                annotations.append(dict(
                    x=last_x,
                    y=last_y,
                    text=f"<b>FY {current_year}</b>",
                    xanchor='center',
                    yanchor='bottom',
                    yshift=10,
                    font=dict(weight="bold"),
                    bordercolor=colors['current']
                ))

        # Configure chart layout
        month_labels = [fiscal_month_to_abbr(i) for i in range(2, 13)]

        fig.update_layout(
            template="tps",
            yaxis_title=dict(
                text='Cumulative Outlays (USD)',
                font=dict(size=12, color="#414141")
            ),
            annotations=annotations
        )

        # Configure x-axis with custom tick labels
        fig.update_xaxes(
            range=[1.9, 12.1],
            tickvals=list(range(2, 13)),
            ticktext=month_labels,
            tickmode='array'
        )
        fig.update_yaxes(rangemode='tozero')

        return fig.to_html(include_plotlyjs=False, full_html=False, config={'staticPlot': True})
    
    def _calculate_fiscal_summary(self, df: pd.DataFrame, 
                                   year_col: str, period_col: str, value_col: str,
                                   round_millions: bool = False) -> dict:
        """Generic method to calculate fiscal year summary metrics.
        
        Args:
            df: DataFrame with fiscal data
            year_col: Column name for fiscal year
            period_col: Column name for fiscal period/month
            value_col: Column name for values to sum
            round_millions: Whether to round millions values
        """
        if df is None or df.empty:
            return {}
        
        # Group by fiscal year and period, sum values
        monthly_data = df.groupby([year_col, period_col]).agg({
            value_col: 'sum'
        }).reset_index()
        
        # Get unique years and sort in descending order
        years = sorted(monthly_data[year_col].unique(), reverse=True)
        
        if len(years) < 2:
            return {}  # Need at least 2 years for comparison
        
        current_year = years[0]
        prior_year = years[1]
        
        # Filter and sort data for each year
        current_year_data = monthly_data[monthly_data[year_col] == current_year].copy()
        prior_year_data = monthly_data[monthly_data[year_col] == prior_year].copy()
        
        current_year_data = current_year_data.sort_values(period_col)
        prior_year_data = prior_year_data.sort_values(period_col)
        
        # Calculate prior fiscal year total
        prior_year_total = prior_year_data[value_col].sum()
        
        # Calculate current fiscal year running sum
        current_year_data['cumulative_amount'] = current_year_data[value_col].cumsum()
        current_year_running_sum = current_year_data['cumulative_amount'].iloc[-1] if not current_year_data.empty else 0
        
        # Find comparable period in prior year
        max_current_period = current_year_data[period_col].max() if not current_year_data.empty else 0
        prior_year_comparable = prior_year_data[
            prior_year_data[period_col] <= max_current_period
        ].copy()
        
        if not prior_year_comparable.empty:
            prior_year_comparable['cumulative_amount'] = prior_year_comparable[value_col].cumsum()
            prior_year_comparable_sum = prior_year_comparable['cumulative_amount'].iloc[-1]
            delta = current_year_running_sum - prior_year_comparable_sum
        else:
            prior_year_comparable_sum = 0
            delta = current_year_running_sum
        
        # Convert to millions
        result = {
            'prior_year_total_millions': prior_year_total / 1_000_000,
            'prior_year_comparable_sum_millions': prior_year_comparable_sum / 1_000_000,
            'current_year_running_sum_millions': current_year_running_sum / 1_000_000,
            'delta_millions': delta / 1_000_000,
            'current_year': current_year,
            'prior_year': prior_year,
            'max_current_period': max_current_period,
            'max_current_period_abbr': fiscal_month_to_abbr(max_current_period)
        }
        
        # Apply rounding if requested
        if round_millions:
            for key in ['prior_year_total_millions', 'prior_year_comparable_sum_millions', 
                        'current_year_running_sum_millions', 'delta_millions']:
                result[key] = round(result[key])
        
        return result
    
    def calculate_obligations_summary(self, obligations_df: pd.DataFrame) -> dict:
        """Calculate obligations summary metrics for current and prior fiscal years"""
        result = self._calculate_fiscal_summary(
            df=obligations_df,
            year_col='reporting_fiscal_year',
            period_col='reporting_fiscal_month',
            value_col='transaction_obligated_amount',
            round_millions=False  # Don't round for obligations
        )
        # Rename period keys to match expected format
        if result:
            result['max_current_month'] = result.pop('max_current_period')
            result['max_current_month_abbr'] = result.pop('max_current_period_abbr')
        return result

    def calculate_obligations_summary_from_summary(self, summary_df: pd.DataFrame) -> dict:
        """Calculate obligations summary metrics from pre-aggregated summary data"""
        if summary_df is None or summary_df.empty:
            return {}

        # Get unique years and sort in descending order
        years = sorted(summary_df['reporting_fiscal_year'].unique(), reverse=True)

        if len(years) < 2:
            return {}  # Need at least 2 years for comparison

        current_year = years[0]
        prior_year = years[1]

        # Filter and sort data for each year
        current_year_data = summary_df[summary_df['reporting_fiscal_year'] == current_year].copy()
        prior_year_data = summary_df[summary_df['reporting_fiscal_year'] == prior_year].copy()

        current_year_data = current_year_data.sort_values('reporting_fiscal_month')
        prior_year_data = prior_year_data.sort_values('reporting_fiscal_month')

        # Calculate prior fiscal year total
        prior_year_total = prior_year_data['transaction_obligated_amount'].sum()

        # Calculate current fiscal year running sum
        current_year_running_sum = current_year_data['cumulative_obligations'].iloc[-1] if not current_year_data.empty else 0

        # Find comparable period in prior year
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

        # Convert to millions (don't round for obligations)
        result = {
            'prior_year_total_millions': prior_year_total / 1_000_000,
            'prior_year_comparable_sum_millions': prior_year_comparable_sum / 1_000_000,
            'current_year_running_sum_millions': current_year_running_sum / 1_000_000,
            'delta_millions': delta / 1_000_000,
            'current_year': current_year,
            'prior_year': prior_year,
            'max_current_month': max_current_period,
            'max_current_month_abbr': fiscal_month_to_abbr(max_current_period)
        }

        return result
    
    def calculate_outlays_summary(self, outlays_df: pd.DataFrame) -> dict:
        """Calculate outlays summary metrics for current and prior fiscal years"""
        return self._calculate_fiscal_summary(
            df=outlays_df,
            year_col='fiscal_year',
            period_col='fiscal_period',
            value_col='monthly_outlay',
            round_millions=True  # Round for outlays
        )

    def calculate_outlays_summary_from_summary(self, summary_df: pd.DataFrame) -> dict:
        """Calculate outlays summary metrics from pre-aggregated summary data"""
        if summary_df is None or summary_df.empty:
            return {}

        # Get unique years and sort in descending order
        years = sorted(summary_df['fiscal_year'].unique(), reverse=True)

        if len(years) < 2:
            return {}  # Need at least 2 years for comparison

        current_year = years[0]
        prior_year = years[1]

        # Filter and sort data for each year
        current_year_data = summary_df[summary_df['fiscal_year'] == current_year].copy()
        prior_year_data = summary_df[summary_df['fiscal_year'] == prior_year].copy()

        current_year_data = current_year_data.sort_values('fiscal_period')
        prior_year_data = prior_year_data.sort_values('fiscal_period')

        # Calculate prior fiscal year total
        prior_year_total = prior_year_data['monthly_outlay'].sum()

        # Calculate current fiscal year running sum
        current_year_running_sum = current_year_data['cumulative_outlay'].iloc[-1] if not current_year_data.empty else 0

        # Find comparable period in prior year
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

        # Convert to millions and round
        result = {
            'prior_year_total_millions': round(prior_year_total / 1_000_000),
            'prior_year_comparable_sum_millions': round(prior_year_comparable_sum / 1_000_000),
            'current_year_running_sum_millions': round(current_year_running_sum / 1_000_000),
            'delta_millions': round(delta / 1_000_000),
            'current_year': current_year,
            'prior_year': prior_year,
            'max_current_period': max_current_period,
            'max_current_period_abbr': fiscal_month_to_abbr(max_current_period)
        }

        return result
    
    def render_mission_page(self, mission: Mission, obligations_df: Optional[pd.DataFrame], outlays_df: Optional[pd.DataFrame] = None, obligations_summary_df: Optional[pd.DataFrame] = None, outlays_summary_df: Optional[pd.DataFrame] = None, obligations_last_updated: Optional[str] = None, outlays_last_updated: Optional[str] = None) -> str:
        """Render individual mission page"""
        template = self.env.get_template('mission.html')
        
        # Create charts - prefer summary data when available
        if obligations_summary_df is not None and not obligations_summary_df.empty:
            chart_html = self.create_obligations_chart_from_summary(obligations_summary_df)
        elif obligations_df is not None:
            chart_html = self.create_obligations_chart(obligations_df)
        else:
            chart_html = ""

        # Use summary data for outlays chart if available, fallback to raw data
        if outlays_summary_df is not None and not outlays_summary_df.empty:
            outlays_chart_html = self.create_outlays_chart_from_summary(outlays_summary_df)
        elif outlays_df is not None:
            outlays_chart_html = self.create_outlays_chart(outlays_df)
        else:
            outlays_chart_html = ""
        
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
        
        # Calculate obligations summary - prefer summary data for efficiency
        if obligations_summary_df is not None and not obligations_summary_df.empty:
            obligations_summary = self.calculate_obligations_summary_from_summary(obligations_summary_df)
        elif obligations_df is not None:
            obligations_summary = self.calculate_obligations_summary(obligations_df)
        else:
            obligations_summary = {}
        
        # Calculate outlays summary - prefer summary data for efficiency
        if outlays_summary_df is not None and not outlays_summary_df.empty:
            outlays_summary = self.calculate_outlays_summary_from_summary(outlays_summary_df)
        elif outlays_df is not None:
            outlays_summary = self.calculate_outlays_summary(outlays_df)
        else:
            outlays_summary = {}
        
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

        # Try to load summary data for more efficient processing
        obligations_summary_df, _ = self.load_obligations_summary_data(mission.acronym, spending_dir)
        outlays_summary_df, _ = self.load_outlays_summary_data(mission.acronym, spending_dir)

        # Calculate summaries for inclusion in JSON - prefer summary data when available
        if obligations_summary_df is not None and not obligations_summary_df.empty:
            obligations_summary = self.calculate_obligations_summary_from_summary(obligations_summary_df)
        elif obligations_df is not None:
            obligations_summary = self.calculate_obligations_summary(obligations_df)
        else:
            obligations_summary = {}

        if outlays_summary_df is not None and not outlays_summary_df.empty:
            outlays_summary = self.calculate_outlays_summary_from_summary(outlays_summary_df)
        elif outlays_df is not None:
            outlays_summary = self.calculate_outlays_summary(outlays_df)
        else:
            outlays_summary = {}

        # Render HTML
        html_content = self.render_mission_page(mission, obligations_df, outlays_df, obligations_summary_df, outlays_summary_df, obligations_last_updated, outlays_last_updated)
        
        # Save HTML
        html_path = mission_dir / 'index.html'
        with open(html_path, 'w') as f:
            f.write(html_content)
        
        # Generate plot URLs with validation
        obligations_plot_urls = self.generate_plot_urls(mission.acronym, 'obligations')
        outlays_plot_urls = self.generate_plot_urls(mission.acronym, 'outlays')

        # Prepare comprehensive data structure with all financial data
        mission_data = {
            'mission': mission.data.model_dump(mode='json'),
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

        # Add prerendered chart URLs if any exist
        if obligations_plot_urls:
            mission_data['financial']['obligations']['prerendered_charts'] = obligations_plot_urls

        if outlays_plot_urls:
            mission_data['financial']['outlays']['prerendered_charts'] = outlays_plot_urls
        
        # Save enriched mission data as JSON
        data_path = mission_dir / f'{kebabcase(mission.acronym).lower()}.json'
        with open(data_path, 'w') as f:
            json.dump(mission_data, f, indent=2, default=str)

        # Also save a copy in the centralized data directory
        data_dir = output_dir.parent / 'data'
        data_dir.mkdir(parents=True, exist_ok=True)
        centralized_data_path = data_dir / f'{kebabcase(mission.acronym).lower()}.json'
        with open(centralized_data_path, 'w') as f:
            json.dump(mission_data, f, indent=2, default=str)

        print(f"Generated site for {mission.name} -> {mission_dir}")
        return mission_dir