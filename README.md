# Kinetics Data Analysis v1.1 - Progress curves analysis with AvaSpec-NEXOS integration
[![Version](https://img.shields.io/badge/version-v1.1-brightgreen)](https://github.com/username/kinetics-analyzer/releases)  [![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)  [![Streamlit](https://img.shields.io/badge/streamlit-1.51%2B-orange)](https://streamlit.io/)  [![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A user-friendly web application for analyzing enzyme kinetics progress curves. It enables interactive visualization, region selection, and statistical analysis of time-course absorbance data. The tool specializes in linear regression of selected regions and supports unit conversions.

## 🌐 Online Access

**Try it now without installation**: [https://kinetics-analyzer.streamlit.app/](https://kinetics-analyzer.streamlit.app/)

The web application is freely available online and provides full functionality without requiring local installation. For users who prefer local deployment or need offline access, installation instructions are provided below.

## Features

### **Data Analysis**
- **Interactive Region Selection**: Direct box selection from plots using selection tools
- **Extinction Coefficient Support**: Convert absorbance slopes to concentration units
- **Statistical Validation**: R², RMSE, and standard error calculations
- **Multiple Dataset Overlay**: Compare multiple experiments simultaneously
- **Enzyme Activity Calculations**: Convert rates to U/mL or U/mg with volume/mass parameters, in single-region and batch analysis
- **Batch Analysis**: Apply the same time window and conversions to many datasets at once
- **Save / Load Session**: Store all datasets, regions and settings in a JSON file and restore them later

### **Visualization**
- **Interactive Tools**: Zoom, pan, hover, and direct region selection
- **Customizable Plot Appearance**: Adjustable point size, opacity, and line thickness
- **Multi-dataset Comparison**: Dynamic color coding for overlay mode

### **Robust Unit Management**
- **Extinction Coefficient Integration**: Automatic absorbance-to-concentration conversion
- **Enzyme Units**: Calculate specific activity (U/mL, U/mg)

### **Data Import & Export**
- **Multiple Formats**: TXT, CSV, Excel (.xlsx, .xls) support
- **Standard Input Units**: Time in seconds, absorbance in UA (absorbance units)
- **Smart Column Detection**: Automatic identification of time and absorbance columns
- **Customizable Export**: Excel files with selectable columns and professional formatting
- **AvaSpec Integration**: Direct conversion from spectrometer Excel output to analysis-ready format

## AvaSpec-NEXOS Integration

This tool provides native support for **AvaSpec-NEXOS spectrometer** data, offering seamless integration from raw measurements to kinetics analysis.

### **Two Usage Approaches**

**Integrated Workflow**: Use the main web application to directly upload AvaSpec Excel files - the tool automatically detects the format and converts the data.

**Standalone Script**: Use the dedicated `avaspec_excel_to_txt.py` converter for batch processing or preprocessing:

```bash
python avaspec_excel_to_txt.py
```

- **Automatically identifies AvaSpec Excel format**
- **Handles multiple files with interactive menu selection**

## Installation

### Method 1: Using Conda (Recommended)

```bash
# Create a new conda environment
conda create -n kinetics python=3.10

# Activate the environment
conda activate kinetics

# Install dependencies (choose one):
pip install streamlit plotly pandas numpy scipy openpyxl matplotlib
# OR use requirements file:
pip install -r requirements.txt

# Run the application
streamlit run kinetics_analyzer.py
```

### Method 2: Direct Installation (Global Environment)

```bash
# Install dependencies (choose one):
pip install streamlit plotly pandas numpy scipy openpyxl matplotlib
# OR use requirements file:
pip install -r requirements.txt

# Run the web application
streamlit run kinetics_analyzer.py
```

The application will automatically open in your web browser at `http://localhost:8501`

### Note for Windows Users

If you're using **Windows** and have Python installed via the **Microsoft Store**, it's recommended to **uninstall that version** before proceeding, as it may cause issues with PATH configuration and package execution.

#### Recommended Installation on Windows

1. Download and install Python from the official website: [https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/)
2. During installation, make sure to **check the box** that says **"Add Python to PATH"**


### Troubleshooting Installation

**Virtual environment not activating:**
- Ensure you're in the correct directory
- On Windows, try using `kinetics_env\Scripts\activate.bat` instead
- For PowerShell on Windows, use `kinetics_env\Scripts\Activate.ps1`

**Package installation issues:**
- Update pip: `python -m pip install --upgrade pip`
- If you encounter permission errors, ensure the virtual environment is activated
- For conda users, try: `conda install pandas numpy scipy` before pip installing other packages



## Usage

### 1. **Data Preparation**

#### **For AvaSpec-NEXOS Spectrometer Users**
If you have raw Excel files from the AvaSpec-NEXOS spectrometer, use the provided conversion tool first:

```bash
# Run the conversion script in the folder that holds your Excel files
python avaspec_excel_to_txt.py
```

The `avaspec_excel_to_txt.py` script is specifically designed for AvaSpec-NEXOS spectrometer output

The script will:
- Scan for all Excel files in the folder
- Present an menu to process all files or select specific ones
- Convert time from milliseconds to seconds
- Extract absorbance data with proper decimal formatting
- Generate tab-separated text files

#### **General Data Preparation**
- Prepare files with time (seconds) and absorbance (UA) columns
- Supported formats: TXT, CSV, Excel
- Use descriptive filenames for experimental conditions
- Data input is standardized: time in seconds, absorbance in UA

### 2. **Analysis Workflow**
1. **Upload Data**: Use sidebar file uploader for multiple datasets
2. **Select Dataset**: Choose from dropdown (or enable overlay mode)
3. **Interactive Selection**: 
   - Use box select tool in plot toolbar
   - Drag across desired time range
   - Selected region appears highlighted in green
   - Click **➕ Add region from selection** to analyze it straight away
4. **Configure Analysis**:
   - Set extinction coefficient and path length for concentration conversions
   - Choose target units (mM, μM, per second/minute)
   - Optionally enable enzyme units (needs the extinction coefficient)
5. **Add Region**: Click "Add Region" to perform analysis
6. **Export Results**: Download Excel or CSV reports
7. **Save Session**: Use "💾 Save session" in the sidebar to keep your work; load it later with "📂 Load session"

### 3. **Features**
- **Multiple Regions**: Analyze different phases of the same experiment
- **Unit Conversions**: Transform slopes using extinction coefficients
- **Enzyme Activity**: Calculate specific activity with volume/mass parameters
- **Statistical Validation**: View R², RMSE, and standard errors
- **Multi-dataset Comparison**: Overlay multiple experiments for comparison
- **Plot Customization**: Adjust point size, opacity, and line thickness


## Example Data Format

Final input data format for kinetics analysis (always in seconds and UA):
```
# Time (s)    Absorbance (UA)
0.0          0.000
1.0          0.015
2.0          0.032
3.0          0.048
...
```

## Example Files

The repository includes example datasets for testing and demonstration:

**AvaSpec Sample Data**: [`original_data/`](original_data/) contains 11 example Excel files (1.xlsx - 11.xlsx) from AvaSpec-NEXOS spectrometer in the standard format.

**Processed Examples**: [`processed_data/`](processed_data/) contains the corresponding converted text files (1.txt - 11.txt) showing the expected output format after conversion.


## Authors

- **Ignacio Aravena Valenzuela**
- **Felipe González Ordenes**

*Facultad de Ciencias, Universidad de Chile*

## Acknowledgments

This project was supported by project FONDECYT Postdoctorado N° 3205890 awarded to Felipe González Ordenes.
