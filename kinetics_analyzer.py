#!/usr/bin/env python3
"""
Enzyme Kinetics Analyzer v1.1 - Streamlit Web Application
Interactive web-based tool for progress curves analysis with AvaSpec integration.
Uses Streamlit for the web interface and Plotly for interactive plotting.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
import io
import zipfile
from typing import Dict, Tuple, List, Optional
import random
import logging
from datetime import datetime
import warnings

import kinetics_core

APP_VERSION = "1.1"

# Configure logging for debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore", category=UserWarning)

st.set_page_config(
    page_title=f"Kinetics Analyzer v{APP_VERSION}",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded"
)

def _clamp(value: float, low: float, high: float) -> float:
    """Keep a plot selection inside the data range (box selections can overshoot the axes)."""
    return float(min(max(value, low), high))


class ColorPalette:
    """Centralized color management for consistent styling across the application."""
    
    def __init__(self):
        self.viridis_colors = [
            '#440154', '#482777', '#3f4a8a', '#31678e', '#26838f',
            '#1f9d8a', '#6cce5a', '#b6de2b', '#fee825', '#f0f921',
            # Extended viridis-like colors for more datasets
            '#4c0c72', '#5a187b', '#682681', '#753581', '#824381',
            '#8e5181', '#9a5f81', '#a66c82', '#b17a83', '#bc8785'
        ]
        
        self.nostalgic_colors = [
            '#000000', '#FF0000', '#0000FF', '#00FF00', '#00FFFF',
            '#FF00FF', '#FFFF00', '#FF8000', '#8000FF', '#00FF80',
            # Extended nostalgic colors for more datasets
            '#800000', '#000080', '#008000', '#008080', '#800080',
            '#808000', '#804000', '#400080', '#008040', '#800040'
        ]
        
        # Names for the first ten colors, shown in manual color selection
        self.color_names = {
            'viridis': ['Dark Purple', 'Deep Violet', 'Royal Blue', 'Ocean Blue', 'Teal Blue',
                        'Forest Green', 'Lime Green', 'Yellow Green', 'Golden Yellow', 'Bright Yellow'],
            'nostalgic': ['Black', 'Red', 'Blue', 'Green', 'Cyan', 'Magenta', 'Yellow', 'Orange',
                          'Purple', 'Spring Green'],
        }
    
    def get_colors(self, palette_type: str = 'viridis') -> List[str]:
        """Get color list for specified palette type."""
        if palette_type == 'nostalgic':
            return self.nostalgic_colors
        return self.viridis_colors
    
    def get_palette(self, palette_type: str = 'viridis') -> List[Tuple[str, str]]:
        """Get palette with color names for UI selection."""
        names = self.color_names['nostalgic' if palette_type == 'nostalgic' else 'viridis']
        return list(zip(self.get_colors(palette_type), names))
    
    def select_colors(self, n_datasets: int, palette_type: str = 'viridis', dark: bool = False) -> List[str]:
        """Select colors with maximum contrast for given number of datasets."""
        full_colors = self.get_colors(palette_type)
        if dark:
            # Skip colors that disappear on a dark background (black, deep purples)
            full_colors = full_colors[1:10] if palette_type == 'nostalgic' else full_colors[3:10]
        
        if palette_type == 'nostalgic':
            # For nostalgic palette, use sequential order
            if n_datasets <= 1:
                return [full_colors[0]]  # Black for single dataset
            else:
                return [full_colors[i % len(full_colors)] for i in range(n_datasets)]
        else:
            # Viridis logic - evenly spaced colors for maximum contrast
            if n_datasets <= 1:
                return [full_colors[len(full_colors)//2]]  # Middle color for single
            else:
                if n_datasets >= len(full_colors):
                    return [full_colors[i % len(full_colors)] for i in range(n_datasets)]
                else:
                    # Evenly distribute across spectrum
                    step = (len(full_colors) - 1) / (n_datasets - 1) if n_datasets > 1 else 0
                    indices = [int(i * step) for i in range(n_datasets)]
                    return [full_colors[i] for i in indices]

class AvaSpecIntegration:
    """Handle AvaSpec Excel file detection and conversion."""
    
    def is_avaspec_excel(self, uploaded_file) -> bool:
        """
        Detect if an Excel file is from AvaSpec spectrometer.
        Checks for characteristic patterns in the data structure.
        """
        try:
            # Read first few rows to check structure
            df = pd.read_excel(uploaded_file, sheet_name=0, nrows=10, header=None)
            
            # Reset file position for subsequent reads
            uploaded_file.seek(0)
            
            # AvaSpec files typically have:
            # - Timestamp in first column
            # - Time in milliseconds in second column (column B)
            # - Absorbance data in third column (column C)
            # - Data starts around row 4
            
            if len(df.columns) >= 3:
                # Check if column B contains time-like data (milliseconds, large numbers)
                col_b_data = df.iloc[3:, 1].dropna()  # Skip header rows
                if not col_b_data.empty:
                    try:
                        # Check if values look like milliseconds (typically > 1000)
                        numeric_data = pd.to_numeric(col_b_data, errors='coerce').dropna()
                        if len(numeric_data) > 0:
                            avg_value = numeric_data.mean()
                            # AvaSpec time data is typically in milliseconds
                            if avg_value > 1000 and avg_value < 1000000:  # Reasonable range
                                logger.info("Detected potential AvaSpec Excel file")
                                return True
                    except Exception:
                        pass
            
            return False
        except Exception as e:
            logger.warning(f"Error checking if file is AvaSpec Excel: {str(e)}")
            return False
    
    def convert_avaspec_excel(self, uploaded_file) -> Optional[pd.DataFrame]:
        """
        Convert AvaSpec Excel file to standard format.
        Returns converted DataFrame or None if conversion fails.
        """
        try:
            uploaded_file.seek(0)
            df = pd.read_excel(io.BytesIO(uploaded_file.getvalue()), sheet_name=0, skiprows=3, header=None)

            if df.empty or len(df.columns) < 3:
                logger.error("AvaSpec Excel file doesn't have expected structure")
                return None

            result_df = kinetics_core.parse_avaspec_rows(df)
            if result_df.empty:
                logger.error("No valid data found in AvaSpec Excel file")
                return None

            logger.info(f"Successfully converted AvaSpec Excel file: {len(result_df)} data points")
            return result_df
            
        except Exception as e:
            logger.error(f"Error converting AvaSpec Excel file: {str(e)}")
            return None

class MemoryManager:
    """Handle memory management and session state cleanup."""
    
    @staticmethod
    def cleanup_removed_datasets(current_filenames: set):
        """Clean up session state for datasets that are no longer uploaded."""
        if not hasattr(st.session_state, 'data_sets'):
            return
        
        session_loaded = st.session_state.get('session_loaded_datasets', set())
        datasets_to_remove = [name for name in st.session_state.data_sets.keys()
                              if name not in current_filenames and name not in session_loaded]
        
        for dataset_name in datasets_to_remove:
            # Remove from data_sets
            if dataset_name in st.session_state.data_sets:
                del st.session_state.data_sets[dataset_name]
                logger.info(f"Cleaned up dataset: {dataset_name}")
            
            # Remove from regions
            if hasattr(st.session_state, 'regions') and dataset_name in st.session_state.regions:
                del st.session_state.regions[dataset_name]
                logger.info(f"Cleaned up regions for dataset: {dataset_name}")
            
            # Remove from manual colors
            if (hasattr(st.session_state, 'manual_colors') and 
                st.session_state.manual_colors and 
                dataset_name in st.session_state.manual_colors):
                del st.session_state.manual_colors[dataset_name]
                logger.info(f"Cleaned up manual colors for dataset: {dataset_name}")
            
            # Remove from AvaSpec converted files tracking
            if (hasattr(st.session_state, 'avaspec_converted_files') and 
                st.session_state.avaspec_converted_files and 
                dataset_name in st.session_state.avaspec_converted_files):
                del st.session_state.avaspec_converted_files[dataset_name]
                logger.info(f"Cleaned up AvaSpec converted file tracking for dataset: {dataset_name}")

class BatchAnalyzer:
    """Analyze the same time window across several datasets."""

    def __init__(self, main_app):
        self.main_app = main_app

    def perform_batch_analysis(self, datasets: List[str], time_frame: Tuple[float, float],
                               analysis_params: Dict) -> Dict[str, Dict]:
        """Fit the window in every dataset; datasets without data in it are skipped, not fatal.

        Stores a summary in st.session_state.batch_summary so it survives the rerun that follows.
        """
        start_time, end_time = time_frame
        # Next number after any existing batch (also ones restored from a session file)
        existing = [int(name.split('_')[1]) for regions in st.session_state.regions.values() for name in regions
                    if name.startswith('Batch_') and name.split('_')[1].isdigit()]
        batch_number = max([st.session_state.get('batch_counter', 0), *existing]) + 1
        results, skipped = {}, []

        for dataset_name in datasets:
            region_name = f"Batch_{batch_number}_{dataset_name}"
            try:
                result = self.main_app._calculate_slope(
                    dataset_name, start_time, end_time, region_name,
                    analysis_params.get('extinction_coeff'),
                    analysis_params.get('target_conc_unit', 'UA'),
                    analysis_params.get('target_time_unit', 's'),
                    analysis_params.get('enzyme_units'),
                    analysis_params.get('path_length_cm', 1.0)
                )
            except Exception as error:
                logger.error(f"Batch analysis failed for {dataset_name}: {error}")
                result = None
            if result:
                st.session_state.regions.setdefault(dataset_name, {})[region_name] = result
                results[dataset_name] = result
            else:
                skipped.append(dataset_name)

        if results:
            st.session_state.batch_counter = batch_number
        st.session_state.batch_summary = {
            'batch': batch_number, 'ok': len(results), 'total': len(datasets),
            'skipped': skipped, 'start': start_time, 'end': end_time,
        }
        logger.info(f"Batch {batch_number}: {len(results)}/{len(datasets)} datasets analyzed")
        return results

class ErrorHandler:
    """Centralized error handling with user-friendly messages."""
    
    @staticmethod
    def handle_file_load_error(filename: str, error: Exception) -> None:
        """Handle file loading errors with helpful suggestions."""
        error_msg = str(error).lower()
        
        if "permission" in error_msg:
            st.error(f"❌ **Permission Error**: Cannot access file '{filename}'. "
                    "Please check file permissions or try saving the file in a different location.")
        elif "memory" in error_msg or "size" in error_msg:
            st.error(f"❌ **Memory Error**: File '{filename}' is too large. "
                    "Try reducing the data size or splitting into smaller files.")
        elif "format" in error_msg or "excel" in error_msg:
            st.error(f"❌ **Format Error**: Cannot read file '{filename}'. "
                    "Please ensure it's a valid Excel, CSV, or TXT file.")
        else:
            st.error(f"❌ **Error loading '{filename}'**: {str(error)}")
            st.info("💡 **Suggestions**: \n"
                   "- Check that the file contains time and absorbance columns\n"
                   "- Ensure the file isn't corrupted or password-protected\n"
                   "- Try converting to a different format (CSV or TXT)")
    
    @staticmethod
    def handle_conversion_error(filename: str, error: Exception) -> None:
        """Handle AvaSpec conversion errors."""
        st.error(f"❌ **Conversion Error**: Could not convert AvaSpec file '{filename}'. "
                f"Error: {str(error)}")
        st.info("💡 **Suggestions**: \n"
               "- Ensure the file is a genuine AvaSpec export\n"
               "- Try opening the file in Excel to verify its contents")

class EnzymeKineticsStreamlit:
    """
    Main application class for enzyme kinetics analysis v1.
    """
    
    def __init__(self):
        # Initialize enhanced components
        self.color_palette = ColorPalette()
        self.avaspec_integration = AvaSpecIntegration()
        self.memory_manager = MemoryManager()
        self.error_handler = ErrorHandler()
        self.batch_analyzer = BatchAnalyzer(self)
        
        # Initialize session state
        if 'data_sets' not in st.session_state:
            st.session_state.data_sets = {}
        if 'regions' not in st.session_state:
            st.session_state.regions = {}
        if 'region_counter' not in st.session_state:
            st.session_state.region_counter = 0
        if 'avaspec_converted_files' not in st.session_state:
            st.session_state.avaspec_converted_files = {}  # Track converted AvaSpec files
        
    
    def _get_plot_width(self) -> int:
        """Get plot width based on user selection."""
        width_mode = st.session_state.get('plot_width_mode', 'container')
        
        width_mapping = {
            'container': None,
            'small': 600,
            'medium': 800, 
            'large': 1000,
            'xlarge': 1200
        }
        
        return width_mapping.get(width_mode, None)
    
    def _load_data_file(self, uploaded_file) -> Optional[pd.DataFrame]:
        """
        Load data from uploaded file with enhanced AvaSpec integration.
        Phase 1 improvement: Automatic AvaSpec detection and conversion.
        """
        try:
            file_extension = Path(uploaded_file.name).suffix.lower()
            
            # Phase 1: AvaSpec Excel Integration
            if file_extension in ['.xlsx', '.xls']:
                # Check if this is an AvaSpec Excel file
                if self.avaspec_integration.is_avaspec_excel(uploaded_file):
                    # Show user prompt for AvaSpec conversion
                    if f"avaspec_prompt_{uploaded_file.name}" not in st.session_state:
                        st.session_state[f"avaspec_prompt_{uploaded_file.name}"] = "pending"
                    
                    if st.session_state[f"avaspec_prompt_{uploaded_file.name}"] == "pending":
                        st.info(f"🔬 **Excel File Detection**: {uploaded_file.name}")
                        st.write("**Is this Excel file exported directly from AvaSpec spectrometer?**")
                        st.caption("AvaSpec files need special processing to convert time units and decimal formats.")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Yes, convert.", key=f"convert_{uploaded_file.name}"):
                                st.session_state[f"avaspec_prompt_{uploaded_file.name}"] = "convert"
                                st.rerun()
                        with col2:
                            if st.button("No.", key=f"standard_{uploaded_file.name}"):
                                st.session_state[f"avaspec_prompt_{uploaded_file.name}"] = "standard"
                                st.rerun()
                        
                        # Don't process the file yet, wait for user decision
                        return None
                    
                    elif st.session_state[f"avaspec_prompt_{uploaded_file.name}"] == "convert":
                        # User chose to convert AvaSpec file
                        with st.spinner(f"🔄 Converting AvaSpec file: {uploaded_file.name}..."):
                            converted_data = self.avaspec_integration.convert_avaspec_excel(uploaded_file)
                            if converted_data is not None:
                                # Track converted file for download option
                                st.session_state.avaspec_converted_files[uploaded_file.name] = uploaded_file.name
                                st.success(f"✅ **AvaSpec Conversion Successful**: {uploaded_file.name} "
                                         f"({len(converted_data)} data points)")
                                logger.info(f"Successfully converted AvaSpec file: {uploaded_file.name}")
                                return converted_data
                            else:
                                self.error_handler.handle_conversion_error(uploaded_file.name, 
                                                                         Exception("Conversion failed"))
                                return None
                    
                    elif st.session_state[f"avaspec_prompt_{uploaded_file.name}"] == "standard":
                        # User chose to load as standard Excel
                        return self._load_excel_file(uploaded_file)
                else:
                    # Regular Excel file, load normally
                    return self._load_excel_file(uploaded_file)
            
            # Handle other file types
            elif file_extension in ('.txt', '.csv'):
                return self._load_text_file(uploaded_file)
            else:
                st.error(f"Unsupported file format: {file_extension}")
                return None
                
        except Exception as e:
            self.error_handler.handle_file_load_error(uploaded_file.name, e)
            return None
    
    def _load_text_file(self, uploaded_file) -> pd.DataFrame:
        """TXT or CSV with any common separator, comment lines or decimal commas."""
        return kinetics_core.read_text_table(kinetics_core.decode_text(uploaded_file.getvalue()))
    
    def _load_excel_file(self, uploaded_file) -> pd.DataFrame:
        return kinetics_core.standardize_columns(pd.read_excel(uploaded_file))
    
    def _create_interactive_plot(self, dataset_name: str = None, show_regions: bool = True, overlay_datasets: List[str] = None) -> go.Figure:
        """Create interactive Plotly figure with enhanced color management."""
        fig = go.Figure()
        
        # Get current color palette
        current_palette_type = st.session_state.get('color_palette_type', 'viridis')
        
        # Theme-aware styling
        if self._is_dark_theme():
            plot_bg = '#0e1117'
            paper_bg = '#0e1117'
            text_color = '#ffffff'
            line_color = '#4a5568'
        else:
            plot_bg = 'white'
            paper_bg = 'white' 
            text_color = '#2d3748'
            line_color = '#cbd5e0'
        
        # Determine which datasets to plot
        datasets_to_plot = []
        if overlay_datasets:
            datasets_to_plot = [ds for ds in overlay_datasets if ds in st.session_state.data_sets]
        elif dataset_name and dataset_name in st.session_state.data_sets:
            datasets_to_plot = [dataset_name]
        elif dataset_name is None:
            datasets_to_plot = list(st.session_state.data_sets.keys())
        
        # Use enhanced color selection
        if st.session_state.get('color_mode', 'auto') == 'manual' and 'manual_colors' in st.session_state:
            # Get manual colors from palette
            palette = self.color_palette.get_palette(current_palette_type)
            colors = []
            for ds_name in datasets_to_plot:
                color_idx = st.session_state.manual_colors.get(ds_name, 0)
                colors.append(palette[color_idx][0])  # Get hex color
        else:
            # Use automatic color selection
            colors = self.color_palette.select_colors(len(datasets_to_plot), current_palette_type,
                                                      dark=self._is_dark_theme())
        
        # Add data traces
        for i, ds_name in enumerate(datasets_to_plot):
            data = st.session_state.data_sets[ds_name]
            color = colors[i % len(colors)]
            
            # WebGL keeps zoom/pan smooth with thousands of points per dataset
            fig.add_trace(go.Scattergl(
                x=data['time'],
                y=data['product'],
                mode='markers',
                name=ds_name,
                marker=dict(
                    size=st.session_state.get('plot_marker_size', 3), 
                    color=color, 
                    opacity=st.session_state.get('plot_marker_opacity', 0.5)
                ),
                # Same look for selected/unselected points: no costly restyle while selecting
                selected=dict(marker=dict(opacity=st.session_state.get('plot_marker_opacity', 0.5))),
                unselected=dict(marker=dict(opacity=st.session_state.get('plot_marker_opacity', 0.5))),
                hovertemplate=f'{ds_name}: %{{x:.1f}}s, %{{y:.3f}} UA<extra></extra>',
                showlegend=False,
                legendgroup=ds_name,
            ))
            
            # Add invisible trace for legend with full opacity
            fig.add_trace(go.Scatter(
                x=[None], y=[None],
                mode='markers',
                name=ds_name,
                marker=dict(size=8, color=color, opacity=1.0),
                showlegend=True,
                legendgroup=ds_name,
                hoverinfo='skip'
            ))
        
        # Add region highlights if available
        if show_regions and datasets_to_plot:
            if dataset_name:
                # Single dataset mode: shaded regions plus fitted lines
                shade_min, shade_max = self._padded_y_range(datasets_to_plot, 0.02)
                dataset_color = colors[datasets_to_plot.index(dataset_name)] if dataset_name in datasets_to_plot else colors[0]
                for region_name, region_data in st.session_state.regions.get(dataset_name, {}).items():
                    fig.add_shape(
                        type="rect",
                        x0=region_data['start'], x1=region_data['end'],
                        y0=shade_min, y1=shade_max,
                        fillcolor='rgba(128, 128, 128, 0.1)',
                        line_width=0,
                    )
                    self._add_fit_line(fig, dataset_name, region_name, region_data, dataset_color)
            else:
                # Overlay mode: fitted lines only, coloured like their dataset
                for dataset_idx, ds_name in enumerate(datasets_to_plot):
                    dataset_color = colors[dataset_idx % len(colors)]
                    for region_name, region_data in st.session_state.regions.get(ds_name, {}).items():
                        self._add_fit_line(fig, ds_name, region_name, region_data, dataset_color,
                                           label=f"{ds_name} fit")
        
        layout_config = dict(
            xaxis=dict(
                title="Time (s)",
                showgrid=False,
                showline=True,
                linecolor=line_color,
                linewidth=1,
                ticks='outside',
                tickcolor=line_color,
                tickfont=dict(size=14, color=text_color),
                title_font=dict(size=16, color=text_color)
            ),
            yaxis=dict(
                title="Absorbance (UA)",
                showgrid=False,
                showline=True,
                linecolor=line_color,
                linewidth=1,
                ticks='outside',
                tickcolor=line_color,
                tickfont=dict(size=14, color=text_color),
                title_font=dict(size=16, color=text_color)
            ),
            plot_bgcolor=plot_bg,
            paper_bgcolor=paper_bg,
            showlegend=len(datasets_to_plot) > 1,
            legend=dict(
                x=1.02, y=1,
                bgcolor=paper_bg,
                bordercolor=line_color,
                borderwidth=1,
                font=dict(size=10, color=text_color)
            ),
            height=st.session_state.get('plot_height', 500),
            width=self._get_plot_width(),
            margin=dict(l=60, r=100, t=40, b=60),
            font=dict(family="Arial", color=text_color),
            hovermode='closest',
            # Keep the user's zoom when the page reruns (e.g. after adding a region)
            uirevision='|'.join(datasets_to_plot)
        )
        
        # Enable selection tools
        layout_config.update({
            'dragmode': 'select',
            'selectdirection': 'h',
            'newselection_mode': 'immediate',
            'activeselection_fillcolor': 'rgba(0, 255, 0, 0.3)',
            'activeselection_opacity': 0.3
        })
        
        fig.update_layout(layout_config)
        return fig
    
    def _is_dark_theme(self) -> bool:
        """Dark when chosen explicitly, or when 'auto' and the browser/Streamlit theme is dark."""
        theme = st.session_state.get('theme', 'auto')
        if theme != 'auto':
            return theme == 'dark'
        try:
            return st.context.theme.type == 'dark'
        except AttributeError:
            return False

    def _padded_y_range(self, dataset_names: List[str], fraction: float) -> Tuple[float, float]:
        """Y range covering all plotted data, padded by a fraction of its span (works for negative values)."""
        y_min = min(st.session_state.data_sets[ds]['product'].min() for ds in dataset_names)
        y_max = max(st.session_state.data_sets[ds]['product'].max() for ds in dataset_names)
        padding = (y_max - y_min) * fraction or abs(y_max) * fraction or fraction
        return y_min - padding, y_max + padding

    @staticmethod
    def _clear_selection() -> None:
        """Forget the current selection and remove the drawn box from the chart."""
        st.session_state.pop('selected_start', None)
        st.session_state.pop('selected_end', None)
        st.session_state.pop('last_box_range', None)
        st.session_state.chart_revision = st.session_state.get('chart_revision', 0) + 1

    def _add_fit_line(self, fig: go.Figure, dataset_name: str, region_name: str, region_data: dict,
                      color: str, label: str = "Fit") -> None:
        """Draw a region's regression line. Two end points are enough for a straight line."""
        times = st.session_state.data_sets[dataset_name]['time']
        in_region = times[(times >= region_data['start']) & (times <= region_data['end'])]
        if in_region.empty:
            return
        x_ends = [float(in_region.min()), float(in_region.max())]
        fig.add_trace(go.Scatter(
            x=x_ends, y=[region_data['slope'] * x + region_data['intercept'] for x in x_ends],
            mode='lines',
            name=f'{dataset_name} - {region_name} fit',
            line=dict(width=st.session_state.get('plot_line_width', 5), color=color),
            opacity=st.session_state.get('plot_line_opacity', 1.0),
            hovertemplate=f'{label}: %{{y:.3f}}<extra></extra>',
            showlegend=False, legendgroup=dataset_name
        ))

    def _calculate_slope(self, dataset_name: str, start_time: float, end_time: float, region_name: str,
                        extinction_coeff: float = None, target_conc_unit: str = 'UA',
                        target_time_unit: str = 's', enzyme_units: Dict = None,
                        path_length_cm: float = 1.0) -> Dict:
        """Calculate slope, unit conversions and enzyme activity for a region."""
        if dataset_name not in st.session_state.data_sets:
            return {}
        result = kinetics_core.analyze_region(
            st.session_state.data_sets[dataset_name], start_time, end_time,
            extinction_coeff, target_conc_unit, target_time_unit, path_length_cm, enzyme_units)
        if result is None:
            return {}
        return {'region_name': region_name, 'dataset': dataset_name, **result}
    
    def _format_region_for_display(self, region_data: dict) -> dict:
        """Format region data for consistent display across individual and batch results."""
        # Slope formatting
        if 'converted_slope' in region_data and 'slope_units' in region_data:
            slope_display = f"{region_data['converted_slope']:.4g}"
            slope_units = region_data['slope_units']
        else:
            slope_display = f"{region_data['slope']:.4g}"
            slope_units = 'UA/s'

        r_squared = region_data['r_squared']

        # Standard error formatting
        if 'converted_std_error' in region_data and region_data.get('converted_std_error') is not None:
            std_err_display = f"{region_data['converted_std_error']:.3g}"
        else:
            std_err_display = f"{region_data.get('std_error', 0):.3g}"

        return {
            'slope_display': slope_display,
            'slope_units': slope_units,
            'slope_with_units': f"{slope_display} {slope_units}",
            'r_squared': f"{r_squared:.4f}",
            'time_range': self._format_time_range(region_data),
            'n_points': region_data['n_points'],
            'std_error': std_err_display,
            'mean_abs': f"{region_data.get('mean_absorbance', 0):.4f}",
            'abs_std': f"{region_data.get('absorbance_std_dev', 0):.4f}",
            'enzyme_activity': region_data.get('enzyme_activity'),
            'enzyme_units': region_data.get('enzyme_activity_units'),
            'enzyme_activity_std_error': region_data.get('enzyme_activity_std_error')
        }

    @staticmethod
    def _format_time_range(region_data: dict) -> str:
        """Region time window in the same time unit as its slope."""
        if region_data.get('slope_units', '').endswith('/min'):
            return f"{region_data['start'] / 60:.2f}–{region_data['end'] / 60:.2f} min"
        return f"{region_data['start']:.2f}–{region_data['end']:.2f} s"

    def _display_region_result(self, region_name: str, region_data: dict,
                                delete_key: str, show_dataset: bool = False,
                                dataset_name: str = None) -> bool:
        """Display a single region result as a structured card. Returns True if delete was clicked."""
        formatted = self._format_region_for_display(region_data)

        with st.container(border=True):
            # Header row with region name, time range, and delete button
            header_col, delete_col = st.columns([6, 1])
            with header_col:
                title = f"**{region_name}**"
                if show_dataset and dataset_name:
                    title += f" ({dataset_name})"
                st.markdown(title)
                st.caption(f"{formatted['time_range']} | {formatted['n_points']} points")

            with delete_col:
                delete_clicked = st.button("🗑️", key=delete_key, help=f"Delete {region_name}", type="secondary")

            # Metrics row
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric(f"Slope ({formatted['slope_units']})", formatted['slope_display'],
                          help=f"± {formatted['std_error']} {formatted['slope_units']} (standard error)")

            with col2:
                r_val = region_data['r_squared']
                if r_val >= 0.99:
                    delta = "Excellent"
                    delta_color = "normal"
                elif r_val < 0.98:
                    delta = "Poor"
                    delta_color = "inverse"
                else:
                    delta = None
                    delta_color = "off"
                st.metric("R²", formatted['r_squared'], delta=delta, delta_color=delta_color)

            with col3:
                st.metric("Mean Abs. (UA)", formatted['mean_abs'], help=f"± {formatted['abs_std']} UA (SD)")

            with col4:
                if formatted['enzyme_activity'] is not None:
                    activity_help = formatted['enzyme_units']
                    if formatted['enzyme_activity_std_error'] is not None:
                        activity_help += f" (± {formatted['enzyme_activity_std_error']:.4f} SE)"
                    st.metric(f"Activity ({formatted['enzyme_units']})",
                              f"{formatted['enzyme_activity']:.4f}", help=activity_help)
                else:
                    st.metric(f"Std Error ({formatted['slope_units']})", formatted['std_error'])


        return delete_clicked

    def _generate_txt_content(self, dataset_name: str, original_filename: str) -> str:
        """TXT file content for converted AvaSpec data."""
        if dataset_name not in st.session_state.data_sets:
            return ""
        return kinetics_core.avaspec_txt(st.session_state.data_sets[dataset_name], original_filename)
    
    def _create_zip_download(self, converted_files: Dict[str, str], filename: str = "avaspec_converted_files.zip") -> bytes:
        """Create a ZIP file containing all converted TXT files."""
        
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for dataset_name, original_filename in converted_files.items():
                # Generate TXT content
                txt_content = self._generate_txt_content(dataset_name, original_filename)
                
                # Create filename for TXT file (replace .xlsx/.xls with .txt)
                txt_filename = Path(dataset_name).stem + '.txt'
                
                # Add to ZIP
                zip_file.writestr(txt_filename, txt_content)
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    
    def _render_conversion_controls(self, key_prefix: str) -> Dict:
        """Unit-conversion and enzyme-unit inputs, shared by single-region and batch analysis."""
        st.markdown("**Unit Conversions (Optional)**")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            use_extinction = st.checkbox(
                "Use Extinction Coefficient", value=False, key=f"{key_prefix}use_extinction",
                help="Convert absorbance slope to concentration slope (Beer-Lambert)")
        with col2:
            extinction_coeff = st.number_input(
                "ε (mM⁻¹cm⁻¹)", min_value=0.0, value=1.0, step=0.1, format="%.3f",
                disabled=not use_extinction, key=f"{key_prefix}extinction_coeff",
                help="Extinction coefficient in mM⁻¹cm⁻¹ (e.g. NADH at 340 nm: 6.22)")
        with col3:
            path_length_cm = st.number_input(
                "Path length (cm)", min_value=0.001, value=1.0, step=0.1, format="%.3f",
                disabled=not use_extinction, key=f"{key_prefix}path_length",
                help="Optical path length of the cuvette or well")
        with col4:
            target_conc_unit = st.selectbox(
                "Concentration Unit", ["mM", "uM"], index=1,
                disabled=not use_extinction, key=f"{key_prefix}conc_unit",
                help="Target concentration unit for the slope")
        with col5:
            target_time_unit = st.selectbox(
                "Time Unit", ["s", "min"], index=0, key=f"{key_prefix}time_unit",
                help="Time unit for the slope")

        st.markdown("**Enzyme Unit Conversion**")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            use_enzyme_units = st.checkbox(
                "Convert to Enzyme Units", value=False, key=f"{key_prefix}use_enzyme_units",
                help="Convert the concentration rate to enzyme activity (1 U = 1 µmol/min)")
        with col2:
            enzyme_unit_type = st.selectbox(
                "Enzyme Unit Type", ["U/mL", "U/mg"], index=0,
                disabled=not use_enzyme_units, key=f"{key_prefix}enzyme_unit_type")
        with col3:
            reaction_volume = st.number_input(
                "Reaction Volume (mL)", min_value=0.001, value=1.0, step=0.001, format="%.3f",
                disabled=not use_enzyme_units, key=f"{key_prefix}reaction_volume",
                help="Total reaction volume in mL")
        with col4:
            if enzyme_unit_type == "U/mL":
                enzyme_amount = st.number_input(
                    "Enzyme Volume (mL)", min_value=0.001, value=0.010, step=0.001, format="%.3f",
                    disabled=not use_enzyme_units, key=f"{key_prefix}enzyme_volume",
                    help="Volume of enzyme solution added, in mL")
            else:
                enzyme_amount = st.number_input(
                    "Enzyme Mass (mg)", min_value=0.001, value=1.0, step=0.001, format="%.3f",
                    disabled=not use_enzyme_units, key=f"{key_prefix}enzyme_mass",
                    help="Mass of enzyme in the reaction, in mg")

        if use_enzyme_units and not use_extinction:
            st.info("ℹ️ Enzyme units need a concentration rate: turn on the extinction coefficient "
                    "so the absorbance slope can be converted to mM or µM first.")

        enzyme_units = None
        if use_enzyme_units and use_extinction:
            enzyme_units = {
                'use_enzyme_units': True,
                'enzyme_unit_type': enzyme_unit_type,
                'reaction_volume': reaction_volume,
                'enzyme_volume' if enzyme_unit_type == "U/mL" else 'enzyme_mass': enzyme_amount,
            }

        return {
            'extinction_coeff': extinction_coeff if use_extinction else None,
            'target_conc_unit': target_conc_unit if use_extinction else 'UA',
            'target_time_unit': target_time_unit,
            'path_length_cm': path_length_cm,
            'enzyme_units': enzyme_units,
        }

    @st.fragment
    def _analysis_panel(self, selected_dataset: str, overlay_datasets: List[str]) -> None:
        """Selection row plus single-region or batch analysis.

        Runs as a fragment, so typing values or ticking boxes here doesn't redraw the chart.
        Actions that change results call st.rerun() to refresh the whole app.
        """
        st.subheader("Analysis")
        multiple = len(st.session_state.data_sets) > 1
        modes = ["Single region", "Batch (several datasets)"] if multiple else ["Single region"]
        if st.session_state.get('analysis_mode') not in modes:
            st.session_state.analysis_mode = modes[0]
        if multiple:
            st.radio("Analyze", modes, key="analysis_mode", horizontal=True, label_visibility="collapsed")
        batch_mode = st.session_state.analysis_mode == modes[-1] and multiple

        # Current selection, with a one-click way to analyze it
        quick_run = False
        if 'selected_start' in st.session_state and 'selected_end' in st.session_state:
            target_dataset = st.session_state.get('selected_for_dataset', 'Unknown')
            if target_dataset == selected_dataset or batch_mode:
                info_col, add_col, clear_col = st.columns([3, 1.4, 1], vertical_alignment="center")
                with info_col:
                    st.info(f"Selected: {st.session_state.selected_start:.2f} s to {st.session_state.selected_end:.2f} s")
                with add_col:
                    label = "▶ Run batch on selection" if batch_mode else "➕ Add region from selection"
                    quick_run = st.button(label, type="primary", width="stretch",
                                          help="Analyze the selection now, using the settings below")
            else:
                info_col, clear_col = st.columns([4.4, 1], vertical_alignment="center")
                with info_col:
                    st.warning(f"Selection is for {target_dataset}, currently viewing {selected_dataset}. Switch datasets to use selection.")
            with clear_col:
                if st.button("✖ Clear", key="clear_selection", width="stretch", help="Remove the current selection"):
                    self._clear_selection()
                    st.rerun()

        if batch_mode:
            self._render_batch_form(overlay_datasets, quick_run)
        else:
            self._render_region_form(selected_dataset, quick_run)

    def _render_region_form(self, selected_dataset: str, quick_add: bool) -> None:
        """Inputs and button to analyze one region of the selected dataset."""
        # Add new region section (keeping same interface as original)
        with st.expander("Add New Region", expanded=True):
            # Time range selection
            col1, col2, col3 = st.columns([2, 2, 2])

            with col1:
                data_min = float(st.session_state.data_sets[selected_dataset]['time'].min())
                data_max = float(st.session_state.data_sets[selected_dataset]['time'].max())

                selection_counter = st.session_state.get('selection_counter', 0)
                has_selection = ('selected_start' in st.session_state and 
                               st.session_state.get('selected_for_dataset') == selected_dataset)

                if has_selection:
                    default_start = _clamp(st.session_state.selected_start, data_min, data_max)
                else:
                    default_start = data_min

                new_start = st.number_input(
                    "Start (s)",
                    min_value=data_min,
                    max_value=data_max,
                    value=float(default_start),
                    step=0.1,
                    format="%.2f",
                    key=f"start_time_{selection_counter}",
                    help="Start time of the region (auto-filled from plot selection)"
                )

            with col2:
                if has_selection:
                    default_end = _clamp(st.session_state.selected_end, new_start, data_max)
                else:
                    default_end = data_max

                new_end = st.number_input(
                    "End (s)",
                    min_value=new_start,
                    max_value=data_max,
                    value=float(default_end),
                    step=0.1,
                    format="%.2f",
                    key=f"end_time_{selection_counter}",
                    help="End time of the region (auto-filled from plot selection)"
                )

            with col3:
                existing_names = st.session_state.regions[selected_dataset]
                next_number = st.session_state.region_counter + 1
                while f"Region_{next_number}" in existing_names:
                    next_number += 1
                region_name = st.text_input(
                    "Region Name", 
                    value=f"Region_{next_number}",
                    key=f"new_region_name_{st.session_state.region_counter}"
                )

            conversion = self._render_conversion_controls(key_prefix="region_")

            # Add region button
            if st.button("Add Region", type="primary", width="stretch") or quick_add:
                if region_name and region_name not in st.session_state.regions[selected_dataset]:
                    with st.spinner('☕ Analyzing kinetics...'):
                        result = self._calculate_slope(
                            selected_dataset, new_start, new_end, region_name,
                            conversion['extinction_coeff'], conversion['target_conc_unit'],
                            conversion['target_time_unit'], conversion['enzyme_units'],
                            conversion['path_length_cm']
                        )

                    if result:
                        st.session_state.regions[selected_dataset][region_name] = result
                        st.session_state.region_counter += 1

                        # Clear the selection after successful region addition
                        self._clear_selection()

                        st.success(f"✅ Added region: {region_name}")
                        st.rerun()
                else:
                    st.error("Region name already exists or is empty")

    def _render_batch_form(self, overlay_datasets: List[str], quick_run: bool) -> None:
        """Analyze the same time window in several datasets at once."""
        names = list(st.session_state.data_sets)
        if 'batch_datasets' not in st.session_state:
            st.session_state.batch_datasets = [n for n in overlay_datasets if n in names] or names
        else:
            st.session_state.batch_datasets = [n for n in st.session_state.batch_datasets if n in names]

        summary = st.session_state.get('batch_summary')
        if summary:
            message = (f"Batch {summary['batch']}: analyzed {summary['ok']} of {summary['total']} datasets "
                       f"({summary['start']:.2f}–{summary['end']:.2f} s). Results are listed below.")
            if not summary['ok']:
                st.error(f"Batch failed: no dataset has data between {summary['start']:.2f} and {summary['end']:.2f} s.")
            elif summary['skipped']:
                st.warning(message + f" Skipped (no data in that window): {', '.join(summary['skipped'])}")
            else:
                st.success(message)

        pick_col, all_col = st.columns([4, 1], vertical_alignment="bottom")
        with all_col:
            st.button("Select all", key="batch_select_all", width="stretch",
                      on_click=lambda: st.session_state.update(batch_datasets=list(names)))
        with pick_col:
            chosen = st.multiselect("Datasets", names, key="batch_datasets")
        if not chosen:
            st.info("Choose at least one dataset.")
            return

        starts = [float(st.session_state.data_sets[n]['time'].min()) for n in chosen]
        ends = [float(st.session_state.data_sets[n]['time'].max()) for n in chosen]
        overall = (min(starts), max(ends))
        common = (max(starts), min(ends))
        if 'selected_start' in st.session_state:
            default = (_clamp(st.session_state.selected_start, *overall), _clamp(st.session_state.selected_end, *overall))
            source = "from the plot selection"
        else:
            default = common if common[0] < common[1] else overall
            source = "the time range shared by the chosen datasets (draw a box on the plot to change it)"

        counter = st.session_state.get('selection_counter', 0)
        start_col, end_col = st.columns(2)
        with start_col:
            batch_start = st.number_input("Start (s)", value=default[0], step=0.1, format="%.2f",
                                          key=f"batch_start_{counter}")
        with end_col:
            batch_end = st.number_input("End (s)", value=default[1], step=0.1, format="%.2f",
                                        key=f"batch_end_{counter}")
        st.caption(f"Window: {source}.")

        conversion = self._render_conversion_controls(key_prefix="batch_")

        if st.button("▶ Run Batch Analysis", type="primary", width="stretch") or quick_run:
            if batch_end <= batch_start:
                st.error("End time must be after start time.")
                return
            with st.spinner('☕ Analyzing datasets...'):
                self.batch_analyzer.perform_batch_analysis(chosen, (batch_start, batch_end), conversion)
            self._clear_selection()
            st.rerun()

    def _render_batch_results(self) -> None:
        """One compact table per batch, with a delete button for each batch."""
        batches: Dict[int, List[Tuple[str, str]]] = {}
        for dataset_name, regions_dict in st.session_state.regions.items():
            for region_name, region_data in regions_dict.items():
                parts = region_name.split('_')
                if region_name.startswith('Batch_') and len(parts) >= 2 and parts[1].isdigit():
                    batches.setdefault(int(parts[1]), []).append((dataset_name, region_name))
        if not batches:
            return

        title_col, clear_col = st.columns([3, 1], vertical_alignment="bottom")
        with title_col:
            st.subheader("Batch Analysis Results")
        with clear_col:
            if st.button("🗑️ Clear all", key="clear_batch_results", width="stretch", help="Delete every batch result"):
                for members in batches.values():
                    for dataset_name, region_name in members:
                        del st.session_state.regions[dataset_name][region_name]
                st.session_state.pop('batch_summary', None)
                st.rerun()

        for batch_number in sorted(batches):
            members = batches[batch_number]
            regions = [st.session_state.regions[ds][name] for ds, name in members]
            table = kinetics_core.results_table(regions)
            columns = [c for c in ['Dataset', 'Slope', 'Slope_Units', 'Std_Error_Converted', 'R_Squared',
                                   'Number_of_Points', 'Enzyme_Activity', 'Enzyme_Activity_Units']
                       if c in table.columns]
            head_col, delete_col = st.columns([5, 1], vertical_alignment="center")
            with head_col:
                first = regions[0]
                st.markdown(f"**Batch {batch_number}** · {len(members)} datasets · {self._format_time_range(first)}")
            with delete_col:
                if st.button("🗑️", key=f"delete_batch_{batch_number}", help=f"Delete batch {batch_number}"):
                    for dataset_name, region_name in members:
                        del st.session_state.regions[dataset_name][region_name]
                    st.rerun()
            st.dataframe(table[columns], hide_index=True, width="stretch", column_config={
                'Slope': st.column_config.NumberColumn(format="%.4g"),
                'Std_Error_Converted': st.column_config.NumberColumn("Std Error", format="%.3g"),
                'R_Squared': st.column_config.NumberColumn("R²", format="%.4f"),
                'Number_of_Points': st.column_config.NumberColumn("Points"),
                'Enzyme_Activity': st.column_config.NumberColumn("Activity", format="%.4g"),
                'Enzyme_Activity_Units': "Activity units",
                'Slope_Units': "Units",
            })

    @st.fragment
    def _export_section(self, all_regions: List[Dict]) -> None:
        """Results table and download. A fragment, so export options don't redraw the chart."""
        if all_regions:
            st.divider()
            st.subheader("Export All Results")
            
            results_df = kinetics_core.results_table(all_regions)
            if not results_df.empty:
                scientific = st.column_config.NumberColumn(format="%.3e")
                st.dataframe(results_df, width="stretch", hide_index=True, column_config={
                    'Start_Time': st.column_config.NumberColumn(format="%.2f"),
                    'End_Time': st.column_config.NumberColumn(format="%.2f"),
                    'Slope': scientific, 'Std_Error_Converted': scientific,
                    'Original_Slope_UA_s': scientific, 'Original_Std_Error': scientific,
                    'R_Squared': st.column_config.NumberColumn(format="%.4f"),
                    'RMSE': scientific,
                    'Mean_Absorbance': st.column_config.NumberColumn(format="%.4f"),
                    'Absorbance_Std_Dev': st.column_config.NumberColumn(format="%.4f"),
                    'Enzyme_Activity': st.column_config.NumberColumn(format="%.4f"),
                    'Enzyme_Activity_Std_Error': st.column_config.NumberColumn(format="%.4f"),
                })
                
                # Export options
                st.subheader("Export Options")
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.write("**Select optional data to export:**")
                    st.caption("Basic information, statistical data (R², Number of Points), and RMSE are always included")
                    
                    available_columns = list(results_df.columns)
                    mandatory_columns = {
                        'Dataset', 'Region', 'Start_Time', 'End_Time', 
                        'R_Squared', 'Number_of_Points', 'RMSE'
                    }
                    
                    export_cols = {}
                    col_a, col_b = st.columns(2)
                    
                    with col_a:
                        export_cols['Slope'] = st.checkbox(
                            "Transformed Slope",
                            value=True,
                            key="export_transformed_slope",
                            help="Includes slope values, units, and standard error"
                        )
                        
                        export_cols['Original_Slope_UA_s'] = st.checkbox(
                            "Original Slope",
                            value=True,
                            key="export_original_slope",
                            help="Includes original slope (UA/s) and standard error"
                        )
                    
                    with col_b:
                        export_cols['Mean_Absorbance'] = st.checkbox(
                            "Mean Absorbance",
                            value=True,
                            key="export_mean_absorbance",
                            help="Mean absorbance value and standard deviation for each region"
                        )
                        
                        export_cols['Extinction_Coeff'] = st.checkbox(
                            "Extinction Coefficient",
                            value=False,
                            key="export_extinction_coeff",
                            help="Extinction coefficient used in calculations"
                        )
                        
                        if 'Enzyme_Activity' in available_columns:
                            export_cols['Enzyme_Activity'] = st.checkbox(
                                "Enzyme Activity",
                                value=True,
                                key="export_enzyme_activity",
                                help="Includes enzyme activity values and units"
                            )
                
                with col2:
                    st.write("**Export Settings:**")
                    
                    custom_filename = st.text_input(
                        "Filename (without extension)",
                        value="kinetics_analysis_results",
                        help="Enter filename without extension"
                    )
                    
                    export_format = st.selectbox(
                        "Export Format",
                        ["Excel (.xlsx)", "CSV (.csv)"],
                        index=0,
                        help="File format for export"
                    )
                
                # Handle column dependencies and create download
                selected_columns = [col for col, selected in export_cols.items() if selected]
                final_columns = set(mandatory_columns.intersection(available_columns))
                
                # Add selected columns and dependencies
                for col in selected_columns:
                    final_columns.add(col)
                    
                    if col == 'Slope':
                        if 'Slope_Units' in available_columns:
                            final_columns.add('Slope_Units')
                        if 'Std_Error_Converted' in available_columns:
                            final_columns.add('Std_Error_Converted')
                    elif col == 'Original_Slope_UA_s':
                        if 'Original_Std_Error' in available_columns:
                            final_columns.add('Original_Std_Error')
                    elif col == 'Mean_Absorbance':
                        if 'Absorbance_Std_Dev' in available_columns:
                            final_columns.add('Absorbance_Std_Dev')
                    elif col == 'Enzyme_Activity':
                        if 'Enzyme_Activity_Units' in available_columns:
                            final_columns.add('Enzyme_Activity_Units')
                        if 'Enzyme_Activity_Std_Error' in available_columns:
                            final_columns.add('Enzyme_Activity_Std_Error')
                    elif col == 'Extinction_Coeff':
                        if 'Path_Length_cm' in available_columns:
                            final_columns.add('Path_Length_cm')
                
                final_columns_list = [col for col in available_columns if col in final_columns]
                
                if final_columns_list:
                    filtered_df = results_df[final_columns_list]
                    
                    # Create file data based on format
                    if export_format == "CSV (.csv)":
                        file_extension = ".csv"
                        mime_type = "text/csv"
                    else:  # Excel
                        file_extension = ".xlsx"
                        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    
                    filename = f"{custom_filename}{file_extension}"
                    
                    output = io.BytesIO()
                    if export_format == "CSV (.csv)":
                        # BOM so Excel opens µ and other symbols correctly
                        output.write(filtered_df.to_csv(index=False).encode('utf-8-sig'))
                    else:  # Excel
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            filtered_df.to_excel(writer, index=False, sheet_name='Results')
                    
                    output.seek(0)
                    
                    st.download_button(
                        label="📥 Download Results",
                        data=output.getvalue(),
                        file_name=filename,
                        mime=mime_type,
                        width="stretch",
                        type="primary"
                    )
                    
                    # Show auto-included columns info
                    auto_included = [col for col in final_columns_list if col not in selected_columns]
                    if auto_included:
                        st.info(f"Auto-included: {', '.join(auto_included)}")
                    
                    st.success(f"Ready to download {len(filtered_df)} rows with {len(final_columns_list)} columns")
                else:
                    st.warning("Please select at least one optional column to export")

    SESSION_SETTING_KEYS = ['theme', 'color_palette_type', 'color_mode', 'plot_marker_size',
                            'plot_marker_opacity', 'plot_line_width', 'plot_line_opacity',
                            'plot_height', 'plot_width_mode', 'plot_image_format']

    def _render_session_controls(self) -> None:
        """Sidebar controls to save the whole analysis to JSON and restore it later."""

        if st.session_state.data_sets:
            settings = {key: st.session_state[key] for key in self.SESSION_SETTING_KEYS
                        if key in st.session_state}
            settings['region_counter'] = st.session_state.get('region_counter', 0)
            session_json = kinetics_core.session_to_json(
                st.session_state.data_sets, st.session_state.regions, settings)
            st.download_button(
                "💾 Save session",
                data=session_json,
                file_name=f"kinetics_session_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json",
                width="stretch",
                help="Download all datasets, regions and settings as a JSON file"
            )

        session_file = st.file_uploader(
            "📂 Load session", type=['json'], key="session_uploader",
            help="Restore a session saved with 'Save session'")
        if session_file is None:
            return

        file_id = (session_file.name, session_file.size)
        if st.session_state.get('loaded_session_file') == file_id:
            return

        try:
            data_sets, regions, settings = kinetics_core.session_from_json(
                session_file.getvalue().decode('utf-8'))
        except (ValueError, UnicodeDecodeError) as error:
            st.error(f"❌ **Could not load session**: {error}")
            return

        st.session_state.data_sets.update(data_sets)
        st.session_state.regions.update(regions)
        st.session_state.session_loaded_datasets = (
            st.session_state.get('session_loaded_datasets', set()) | set(data_sets))
        for key, value in settings.items():
            if key in self.SESSION_SETTING_KEYS:
                st.session_state[key] = value
        # New widget keys make the plot sliders pick up the restored values
        st.session_state.plot_widgets_epoch = st.session_state.get('plot_widgets_epoch', 0) + 1
        st.session_state.region_counter = max(st.session_state.get('region_counter', 0),
                                              settings.get('region_counter', 0))
        st.session_state.loaded_session_file = file_id
        logger.info(f"Loaded session {session_file.name}: {len(data_sets)} datasets")
        st.rerun()

    def run(self):
        """Main application interface with Phase 1 improvements."""
        # ====================
        # SECTION 1: Theme & CSS Setup
        # ====================
        # Initialize theme preference
        if 'theme' not in st.session_state:
            st.session_state.theme = 'auto'
        
        # Theme-aware CSS
        if st.session_state.theme == 'dark':
            theme_vars = {
                'bg_primary': '#0e1117',
                'bg_secondary': '#262730',
                'text_primary': '#ffffff',
                'text_secondary': '#a3a8b8',
                'border_color': '#464853',
                'accent_color': '#ff6b6b'
            }
        elif st.session_state.theme == 'light':
            theme_vars = {
                'bg_primary': '#ffffff',
                'bg_secondary': '#f0f2f6',
                'text_primary': '#262730',
                'text_secondary': '#6c757d',
                'border_color': '#d1d5db',
                'accent_color': '#1f77b4'
            }
        else:  # auto/system
            theme_vars = {
                'bg_primary': 'var(--background-color)',
                'bg_secondary': 'var(--secondary-background-color)',
                'text_primary': 'var(--text-color)',
                'text_secondary': 'var(--text-color-secondary)',
                'border_color': 'var(--border-color)',
                'accent_color': 'var(--primary-color)'
            }
        
        # Apply theme CSS
        st.markdown(f"""
        <style>
        .main-header {{
            background: {theme_vars['bg_secondary']};
            color: {theme_vars['text_primary']};
            padding: 2rem;
            border-radius: 8px;
            margin-bottom: 2rem;
            text-align: center;
            border: 1px solid {theme_vars['border_color']};
        }}
        .main-header h1 {{
            margin: 0;
            font-size: 2.5rem;
            font-weight: 600;
        }}
        .main-header p {{
            margin: 0.5rem 0 0 0;
            font-size: 1.1rem;
            opacity: 0.8;
        }}
        
        /* Subtle hover effects and animations */
        .stButton > button {{
            transition: all 0.2s ease-in-out;
        }}
        .stButton > button:hover {{
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }}
        
        /* Viridis gradient accent */
        .viridis-accent {{
            background: linear-gradient(45deg, #440154, #21908c, #fde725);
            height: 3px;
            border-radius: 1.5px;
            margin: 0.5rem 0;
        }}
        
        /* Keep result numbers readable in narrow columns */
        [data-testid="stMetricValue"] {{
            font-size: 1.6rem;
        }}
        </style>
        """, unsafe_allow_html=True)

        # ====================
        # SECTION 2: Header & Sidebar
        # ====================
        # Professional header with same styling as original
        if 'header_quote' not in st.session_state:
            st.session_state.header_quote = random.choice(kinetics_core.QUOTES)
        selected_quote = st.session_state.header_quote
        st.markdown(f"""
        <div class="main-header">
            <h1>☕ Kinetics Analyzer</h1>
            <p>Interactive enzyme kinetics data analysis · v{APP_VERSION}</p>
            <div class="viridis-accent"></div>
            <div style="font-style: italic; opacity: 0.7; font-size: 0.9rem; margin-top: 0.5rem;">
                "{selected_quote}"
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Sidebar configuration
        with st.sidebar:
            with st.expander("🎨 Appearance", expanded=False):
            
                # Theme selection
                theme_option = st.selectbox(
                    "Theme",
                    ["auto", "light", "dark"],
                    index=0 if st.session_state.theme == 'auto' else (1 if st.session_state.theme == 'light' else 2),
                    help="Choose interface theme"
                )
            
                if theme_option != st.session_state.theme:
                    st.session_state.theme = theme_option
                    st.rerun()
            
                # Enhanced color palette management with v1 improvements
                st.markdown("**Color Settings**")
            
                # Color palette mode selection
                color_palette_type = st.radio(
                    "Color Palette",
                    ["Viridis", "Nostalgic"],
                    index=0 if st.session_state.get('color_palette_type', 'viridis') == 'viridis' else 1,
                    help="Choose color palette style"
                )
            
                # Store palette type
                st.session_state.color_palette_type = 'viridis' if color_palette_type == "Viridis" else 'nostalgic'
            
                # Get current palette using enhanced color management
                current_palette = self.color_palette.get_palette(st.session_state.color_palette_type)
            
                # Color selection mode
                color_mode = st.radio(
                    "Color Selection Mode",
                    ["Automatic (Dynamic)", "Manual Selection"],
                    index=0 if st.session_state.get('color_mode', 'auto') == 'auto' else 1,
                    help="Choose automatic color selection or manually pick colors"
                )
            
                # Store color mode and track changes
                new_color_mode = 'auto' if color_mode == "Automatic (Dynamic)" else 'manual'
            
                # Track mode changes for color preservation
                if 'color_mode' in st.session_state and st.session_state.color_mode != new_color_mode:
                    st.session_state.color_mode_previous = st.session_state.color_mode
            
                st.session_state.color_mode = new_color_mode
            
                # Manual color selection with enhanced palette management
                if st.session_state.color_mode == 'manual' and st.session_state.data_sets:
                    st.write("**Select colors for each dataset:**")
                
                    # Initialize manual colors if not exists
                    if 'manual_colors' not in st.session_state:
                        st.session_state.manual_colors = {}
                
                    # Simple color selector for each dataset
                    for i, dataset_name in enumerate(st.session_state.data_sets.keys()):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            # Display color options with descriptive names from current palette
                            selected_color_idx = st.selectbox(
                                f"{dataset_name}:",
                                range(len(current_palette)),
                                index=st.session_state.manual_colors.get(dataset_name, i % len(current_palette)),
                                format_func=lambda x: current_palette[x][1],  # Use descriptive name
                                key=f"color_select_{dataset_name}_{st.session_state.color_palette_type}"
                            )
                            st.session_state.manual_colors[dataset_name] = selected_color_idx
                    
                        with col2:
                            # Show color preview
                            color_hex = current_palette[selected_color_idx][0]  # Get hex color
                            st.markdown(f"""
                            <div style="
                                width: 30px; 
                                height: 30px; 
                                background-color: {color_hex}; 
                                border-radius: 4px; 
                                border: 1px solid #ccc;
                                margin-top: 24px;
                            "></div>
                            """, unsafe_allow_html=True)
            
            st.divider()

            # ====================
            # SECTION 3: File Upload & Processing
            # ====================
            st.header("Data Upload")
            
            uploaded_files = st.file_uploader(
                "Select data files",
                type=['txt', 'csv', 'xlsx', 'xls'],
                accept_multiple_files=True,
                help="Data must contain time (seconds) and absorbance (UA) columns. Supports automatic AvaSpec Excel conversion."
            )
            
            # Enhanced memory management with batch AvaSpec detection
            if uploaded_files:
                uploaded_filenames = {uploaded_file.name for uploaded_file in uploaded_files}
                # Clean up removed datasets
                self.memory_manager.cleanup_removed_datasets(uploaded_filenames)
                
                # Batch AvaSpec detection for multiple Excel files
                new_files = [f for f in uploaded_files if f.name not in st.session_state.data_sets]
                excel_files = [f for f in new_files if Path(f.name).suffix.lower() in ['.xlsx', '.xls']]
                
                if len(excel_files) > 1:
                    # Check if ALL Excel files are AvaSpec
                    all_avaspec = all(self.avaspec_integration.is_avaspec_excel(f) for f in excel_files)
                    
                    if all_avaspec:
                        # Batch AvaSpec prompt for multiple files
                        batch_key = f"batch_avaspec_{hash(tuple(f.name for f in excel_files))}"
                        if batch_key not in st.session_state:
                            st.session_state[batch_key] = "pending"
                        
                        if st.session_state[batch_key] == "pending":
                            st.info(f"🔬 **Excel Files Detected**: {len(excel_files)} files")
                            st.write("**Are ALL these Excel files directly exported from AvaSpec spectrometer?**")
                            st.caption(f"Files: {', '.join([f.name for f in excel_files])}")
                            
                            col1, col2, col3 = st.columns([2, 2, 1])
                            with col1:
                                if st.button("Yes, convert.", key=f"batch_convert_{batch_key}"):
                                    st.session_state[batch_key] = "convert_all"
                                    st.rerun()
                            with col2:
                                if st.button("No", key=f"batch_standard_{batch_key}"):
                                    st.session_state[batch_key] = "standard_all"
                                    st.rerun()
                            with col3:
                                if st.button("🔍", key=f"batch_individual_{batch_key}"):
                                    st.session_state[batch_key] = "individual"
                                    st.rerun()
                            
                            # Don't process files yet, wait for user decision
                            return
                        
                        elif st.session_state[batch_key] == "convert_all":
                            # Batch convert all AvaSpec files
                            st.subheader("Loading Files")
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            
                            for i, uploaded_file in enumerate(excel_files):
                                progress = (i + 1) / len(excel_files)
                                progress_bar.progress(progress)
                                status_text.text(f"Converting AvaSpec file {i + 1} of {len(excel_files)}: {uploaded_file.name}")
                                
                                with st.spinner(f"Converting {uploaded_file.name}..."):
                                    data = self.avaspec_integration.convert_avaspec_excel(uploaded_file)
                                    if data is not None:
                                        st.session_state.data_sets[uploaded_file.name] = data
                                        # Track converted file for download option
                                        st.session_state.avaspec_converted_files[uploaded_file.name] = uploaded_file.name
                                        st.success(f"✅ **AvaSpec Converted**: {uploaded_file.name} ({len(data)} points)")
                            
                            progress_bar.empty()
                            status_text.empty()
                            st.success(f"🎉 **Batch Conversion Complete**: {len(excel_files)} AvaSpec files processed")
                            
                        elif st.session_state[batch_key] == "standard_all":
                            # Load all as standard Excel
                            st.subheader("Loading Files")
                            for uploaded_file in excel_files:
                                with st.spinner(f"Loading {uploaded_file.name}..."):
                                    data = self._load_excel_file(uploaded_file)
                                    if data is not None:
                                        st.session_state.data_sets[uploaded_file.name] = data
                                        st.success(f"📁 Loaded: {uploaded_file.name}")
                
                # Process remaining files (non-Excel and individual handling)
                for uploaded_file in uploaded_files:
                    if uploaded_file.name not in st.session_state.data_sets:
                        # Skip Excel files that are part of batch processing (unless individual handling)
                        if (len(excel_files) > 1 and uploaded_file in excel_files and 
                            f"batch_avaspec_{hash(tuple(f.name for f in excel_files))}" in st.session_state and
                            st.session_state[f"batch_avaspec_{hash(tuple(f.name for f in excel_files))}"] != "individual"):
                            continue
                        
                        with st.spinner(f"Loading {uploaded_file.name}..."):
                            data = self._load_data_file(uploaded_file)
                            if data is not None:
                                st.session_state.data_sets[uploaded_file.name] = data
                                st.success(f"📁 Loaded: {uploaded_file.name}")
                            # Error already handled by error handler if data is None
                loaded_names = [f.name for f in uploaded_files if f.name in st.session_state.data_sets]
                if loaded_names:
                    st.caption(f"✅ {len(loaded_names)} file(s) loaded: {', '.join(loaded_names)}")
            else:
                # No files in the uploader: drop uploaded datasets, keep ones restored from a session file
                self.memory_manager.cleanup_removed_datasets(set())

            with st.expander("💾 Session", expanded=False):
                self._render_session_controls()

            st.divider()
            
            # Plot customization section (same as original)
            with st.expander("📈 Plot Appearance", expanded=False):
            
                # Initialize plot customization settings in session state
                if 'plot_marker_size' not in st.session_state:
                    st.session_state.plot_marker_size = 3
                if 'plot_marker_opacity' not in st.session_state:
                    st.session_state.plot_marker_opacity = 1.0
                if 'plot_line_width' not in st.session_state:
                    st.session_state.plot_line_width = 5
                if 'plot_line_opacity' not in st.session_state:
                    st.session_state.plot_line_opacity = 0.7
                if 'plot_height' not in st.session_state:
                    st.session_state.plot_height = 500
                if 'plot_width_mode' not in st.session_state:
                    st.session_state.plot_width_mode = 'container'
            
                plot_widgets_epoch = st.session_state.get('plot_widgets_epoch', 0)
            
                # Data points customization
                st.write("**Data Points:**")
                col1, col2 = st.columns(2)
                with col1:
                    st.session_state.plot_marker_size = st.slider(
                        "Thickness",
                        min_value=1,
                        max_value=10,
                        value=st.session_state.plot_marker_size,
                        step=1,
                        key=f"marker_size_slider_{plot_widgets_epoch}",
                        help="Size of data point markers"
                    )
                with col2:
                    st.session_state.plot_marker_opacity = st.slider(
                        "Opacity",
                        min_value=0.1,
                        max_value=1.0,
                        value=st.session_state.plot_marker_opacity,
                        step=0.1,
                        key=f"marker_opacity_slider_{plot_widgets_epoch}",
                        help="Opacity of data points (1.0 = opaque, 0.1 = very transparent)"
                    )
            
                # Fitted lines customization
                st.write("**Fitted Lines:**")
                col1, col2 = st.columns(2)
                with col1:
                    st.session_state.plot_line_width = st.slider(
                        "Thickness",
                        min_value=1,
                        max_value=10,
                        value=st.session_state.plot_line_width,
                        step=1,
                        key=f"line_width_slider_{plot_widgets_epoch}",
                        help="Width of fitted regression lines"
                    )
                with col2:
                    st.session_state.plot_line_opacity = st.slider(
                        "Opacity",
                        min_value=0.1,
                        max_value=1.0,
                        value=st.session_state.plot_line_opacity,
                        step=0.1,
                        key=f"line_opacity_slider_{plot_widgets_epoch}",
                        help="Opacity of fitted lines (1.0 = opaque, 0.1 = very transparent)"
                    )
            
                # Plot size customization
                st.write("**Plot Size:**")
                col1, col2 = st.columns(2)
                with col1:
                    st.session_state.plot_height = st.slider(
                        "Height (px)",
                        min_value=300,
                        max_value=1000,
                        value=st.session_state.plot_height,
                        step=50,
                        key=f"plot_height_slider_{plot_widgets_epoch}",
                        help="Height of the plot in pixels"
                    )
                with col2:
                    plot_width_options = ["Container Width", "Small (600px)", "Medium (800px)", "Large (1000px)", "Extra Large (1200px)"]
                    width_mode_index = ["container", "small", "medium", "large", "xlarge"].index(st.session_state.plot_width_mode)
                
                    selected_width = st.selectbox(
                        "Width",
                        plot_width_options,
                        index=width_mode_index,
                        key=f"plot_width_selector_{plot_widgets_epoch}",
                        help="Width of the plot"
                    )
                
                    # Update session state based on selection
                    width_mapping = {
                        "Container Width": "container",
                        "Small (600px)": "small", 
                        "Medium (800px)": "medium",
                        "Large (1000px)": "large",
                        "Extra Large (1200px)": "xlarge"
                    }
                    st.session_state.plot_width_mode = width_mapping[selected_width]
            
                st.session_state.plot_image_format = st.selectbox(
                    "Image download (📷 button)",
                    ["png", "svg"],
                    index=["png", "svg"].index(st.session_state.get('plot_image_format', 'png')),
                    format_func=lambda fmt: {"png": "PNG (high resolution)", "svg": "SVG (vector)"}[fmt],
                    key=f"plot_image_format_{plot_widgets_epoch}",
                    help="Format used by the camera button in the plot toolbar"
                )
                
                # Reset to defaults button
                if st.button("Reset to Defaults", type="secondary", width="stretch"):
                    st.session_state.plot_marker_size = 3
                    st.session_state.plot_marker_opacity = 1.0
                    st.session_state.plot_line_width = 5
                    st.session_state.plot_line_opacity = 0.7
                    st.session_state.plot_height = 500
                    st.session_state.plot_width_mode = 'container'
                    st.session_state.plot_widgets_epoch = plot_widgets_epoch + 1
                    st.rerun()
            
            st.divider()
            
            # Statistics section
            if st.session_state.data_sets:
                st.header("Dataset Statistics")
                st.metric("Datasets loaded", len(st.session_state.data_sets))
                total_regions = sum(len(regions) for regions in st.session_state.regions.values())
                if total_regions > 0:
                    st.metric("Regions analyzed", total_regions)
            
            st.divider()
            
            # AvaSpec converted files download section
            if (hasattr(st.session_state, 'avaspec_converted_files') and 
                st.session_state.avaspec_converted_files):
                st.header("🔬 AvaSpec Downloads")
                
                converted_count = len(st.session_state.avaspec_converted_files)
                st.metric("AvaSpec files converted", converted_count)
                
                st.write("**Download converted TXT files:**")
                st.caption("Get all converted AvaSpec files as TXT format in a ZIP archive.")
                
                # Single consolidated download button
                try:
                    # Create ZIP file
                    zip_data = self._create_zip_download(st.session_state.avaspec_converted_files)
                    
                    # Provide direct download
                    st.download_button(
                        label="📥 Download All as TXT Files (ZIP)",
                        data=zip_data,
                        file_name="avaspec_converted_files.zip",
                        mime="application/zip",
                        width="stretch",
                        type="primary",
                        help=f"Download {converted_count} converted AvaSpec files as TXT format in a ZIP file"
                    )
                    
                except Exception as e:
                    st.error(f"❌ **Download Error**: {str(e)}")
                    logger.error(f"Error creating AvaSpec download ZIP: {str(e)}")
                
                # Show list of converted files
                with st.expander("📋 View Converted Files", expanded=False):
                    for i, (dataset_name, original_name) in enumerate(st.session_state.avaspec_converted_files.items(), 1):
                        txt_filename = Path(dataset_name).stem + '.txt'
                        st.write(f"{i}. **{original_name}** → `{txt_filename}`")
            
        # Main content area
        if not st.session_state.data_sets:
            st.markdown("### Welcome")
            st.info("Upload your kinetics data (TXT, CSV, or Excel) using the sidebar to get started.")
            return

        # ====================
        # SECTION 4: Dataset Selection & Overlay
        # ====================
        st.subheader("Dataset Analysis")
        
        selected_dataset = st.selectbox(
            "Select Dataset for Analysis",
            list(st.session_state.data_sets.keys()),
            help="Choose a dataset to analyze and visualize"
        )
        
        # Overlay selection section
        st.subheader("Overlay Options")
        col1, col2 = st.columns([1, 2])
        with col1:
            enable_overlay = st.checkbox(
                "Enable Overlay Mode",
                value=False,
                help="Show multiple datasets on the same plot for comparison"
            )
        
        # Initialize overlay_datasets based on enable_overlay
        if enable_overlay:
            with col2:
                overlay_datasets = st.multiselect(
                    "Select Datasets to Overlay",
                    options=list(st.session_state.data_sets.keys()),
                    default=list(st.session_state.data_sets.keys()),
                    help="Choose which datasets to display on the overlay plot"
                )
            show_overlay = len(overlay_datasets) > 0
        else:
            overlay_datasets = []
            show_overlay = False
        
        # ====================
        # SECTION 5: Interactive Plot
        # ====================
        if selected_dataset:
            st.subheader("Interactive Data Visualization")
            
            # Nothing above the chart may appear or disappear between reruns:
            # Streamlit would rebuild the chart and the user's zoom would be lost.
            
            # Configure plot toolbar
            config = {
                'modeBarButtonsToRemove': ['lasso2d'],
                'displayModeBar': True,
                'toImageButtonOptions': {
                    'format': st.session_state.get('plot_image_format', 'png'),
                    'filename': Path(selected_dataset).stem if not (show_overlay and overlay_datasets) else 'kinetics_overlay',
                    'scale': 3,
                },
                'displaylogo': False,
                'modeBarButtonsToAdd': ['select2d'],
                'showTips': True,
                'scrollZoom': True
            }
            
            # Create interactive plot with enhanced color management
            if show_overlay and overlay_datasets:
                fig = self._create_interactive_plot(show_regions=True, overlay_datasets=overlay_datasets)
                plot_key = "overlay_plot"
            else:
                fig = self._create_interactive_plot(selected_dataset, show_regions=True)
                plot_key = "single_plot"
            
            # Use selection events for both single and overlay modes
            if show_overlay and overlay_datasets:
                datasets_hash = hash(tuple(sorted(overlay_datasets)))
                unique_plot_key = f"{plot_key}_{datasets_hash}"
            else:
                unique_plot_key = f"{plot_key}_{selected_dataset}"
            unique_plot_key += f"_{st.session_state.get('chart_revision', 0)}"
            
            # Determine if we should use container width or fixed width
            chart_width = "stretch" if st.session_state.get('plot_width_mode', 'container') == 'container' else "content"
            
            plot_selection = st.plotly_chart(fig, width=chart_width, key=unique_plot_key, on_select="rerun",
                                             selection_mode="box", config=config)
            
            # Handle a new box selection in this same run. The chart keeps showing
            # Plotly's own selection box, so the figure doesn't change and isn't rebuilt.
            boxes = ((plot_selection or {}).get('selection') or {}).get('box') or []
            if boxes and len(boxes[0].get('x', [])) >= 2:
                box_range = (float(min(boxes[0]['x'])), float(max(boxes[0]['x'])))
                if box_range != st.session_state.get('last_box_range'):
                    st.session_state.last_box_range = box_range
                    st.session_state.selected_start, st.session_state.selected_end = box_range
                    st.session_state.selected_for_dataset = selected_dataset
                    st.session_state.selection_counter = st.session_state.get('selection_counter', 0) + 1
            
            # ====================
            # SECTION 6: Analysis (a fragment: changing its inputs doesn't redraw the chart)
            # ====================
            if selected_dataset not in st.session_state.regions:
                st.session_state.regions[selected_dataset] = {}
            self._analysis_panel(selected_dataset, overlay_datasets if show_overlay else [])
            
            # ====================
            # SECTION 7: Results Display
            # ====================
            individual_regions = {name: data for name, data in st.session_state.regions[selected_dataset].items()
                                  if not name.startswith('Batch_')}
            if individual_regions:
                title_col, clear_col = st.columns([3, 1], vertical_alignment="bottom")
                with title_col:
                    st.subheader("📊 Analysis Results")
                with clear_col:
                    if st.button("🗑️ Clear all", key=f"clear_regions_{selected_dataset}", width="stretch",
                                 help=f"Delete every region of {selected_dataset} (batch results are kept)"):
                        for name in individual_regions:
                            del st.session_state.regions[selected_dataset][name]
                        st.rerun()

                # Display regions using helper method
                for region_name, region_data in individual_regions.items():
                    delete_key = f"delete_{selected_dataset}_{region_name}"
                    if self._display_region_result(region_name, region_data, delete_key):
                        del st.session_state.regions[selected_dataset][region_name]
                        st.success(f"Deleted region: {region_name}")
                        st.rerun()
        
        self._render_batch_results()
        
        # ====================
        # SECTION 8: Export
        # ====================
        all_regions = []
        for dataset_name, regions_dict in st.session_state.regions.items():
            for region_name, region_data in regions_dict.items():
                all_regions.append(region_data)

        self._export_section(all_regions)

# Run the application
if __name__ == "__main__":
    app = EnzymeKineticsStreamlit()
    app.run()
