"""
Kinetics Analyzer core calculations.

Pure functions with no Streamlit dependency, so they can be tested directly.
"""

import io
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

SESSION_FORMAT_VERSION = "1.1"

ABSORBANCE_WORDS = {'ua', 'au', 'od', 'abs', 'absorbance', 'absorbancia', 'absorbância',
                    'concentration', 'conc', 'product', 'producto', 'signal'}
TIME_WORDS = {'time', 'tiempo', 't', 'sec', 'secs', 'second', 'seconds', 'segundos', 's'}

CONC_TO_MM = {'mM': 1.0, 'uM': 1e-3}
TIME_TO_MIN = {'s': 60.0, 'min': 1.0}


def _header_words(column) -> set:
    return set(re.findall(r'[^\W\d_]+', str(column).lower()))


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with numeric 'time' and 'product' columns.

    Headers are matched on whole words, so 'Absorbance' is never mistaken for time
    and 'Temperature' is never mistaken for anything.
    """
    columns = list(df.columns)
    conc_col = next((c for c in columns if _header_words(c) & ABSORBANCE_WORDS), None)
    time_col = next((c for c in columns if c != conc_col and _header_words(c) & TIME_WORDS), None)

    numeric_cols = [c for c in df.select_dtypes(include=[np.number]).columns]
    if time_col is None:
        time_col = next((c for c in numeric_cols if c != conc_col), None)
    if conc_col is None:
        conc_col = next((c for c in numeric_cols if c != time_col), None)
    if time_col is None or conc_col is None:
        raise ValueError("Could not identify time and absorbance columns")

    result_df = pd.DataFrame({
        'time': pd.to_numeric(df[time_col], errors='coerce'),
        'product': pd.to_numeric(df[conc_col], errors='coerce'),
    })
    return result_df.dropna().reset_index(drop=True)


def decode_text(raw: bytes) -> str:
    """Decode an uploaded text file, falling back to Latin-1 for Windows instrument exports."""
    for encoding in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode file")


def _is_number(field: str) -> bool:
    try:
        float(field.strip().replace(',', '.'))
        return True
    except ValueError:
        return False


def read_text_table(text: str) -> pd.DataFrame:
    """Read a TXT/CSV table with any common layout into time/product columns.

    Handles '#' or '%' comment lines, tab / semicolon / comma / whitespace separators,
    decimal commas (e.g. Spanish-locale Excel CSV) and files without a header row.
    """
    lines = [line for line in text.splitlines()
             if line.strip() and not line.lstrip().startswith(('#', '%'))]
    if not lines:
        raise ValueError("No data found in file")

    sample = lines[1] if len(lines) > 1 else lines[0]
    separator = next((sep for sep in ('\t', ';', ',') if sep in sample), r'\s+')
    decimal = ',' if separator != ',' and re.search(r'\d,\d', sample) else '.'

    first_fields = re.split(separator, lines[0].strip())
    has_header = not all(_is_number(field) for field in first_fields if field.strip())

    df = pd.read_csv(io.StringIO('\n'.join(lines)), sep=separator, decimal=decimal,
                     engine='python', header=0 if has_header else None)
    if not has_header:
        df.columns = [f'column_{i + 1}' for i in range(len(df.columns))]
    return standardize_columns(df)


def avaspec_txt(data: pd.DataFrame, original_name: str, experiment_date=None) -> str:
    """Tab-separated TXT (with a provenance header) for converted AvaSpec data."""
    header = [
        "##################################################",
        "# DATA EXPORT AND TRANSFORMATION REPORT",
        "#",
        f"# Original File: {original_name}",
        *([f"# Experiment Start Date/Time: {experiment_date}"] if experiment_date is not None else []),
        f"# Processing Date: {datetime.now()}",
        "#",
        "# Operations Performed:",
        "# - Column 1 (Time): Read from Excel Column B (milliseconds), divided by 1000.",
        "# - Column 2 (Absorbance): Read from Excel Column C, comma decimal converted to dot decimal.",
        "##################################################",
        "",
        "Time (s)\tUA",
    ]
    rows = (f"{time}\t{product}" for time, product in zip(data['time'], data['product']))
    return '\n'.join([*header, *rows]) + '\n'


def parse_avaspec_rows(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Convert AvaSpec rows (column B = time in ms, column C = absorbance) to time (s) / product."""
    valid_rows = []
    for _, row in raw_df.iterrows():
        raw_time_ms, raw_absorbance = row.iloc[1], row.iloc[2]
        if pd.isna(raw_time_ms) or pd.isna(raw_absorbance):
            continue
        try:
            time_sec = float(raw_time_ms) / 1000.0
            absorbance = float(str(raw_absorbance).replace(',', '.'))
        except (ValueError, TypeError):
            continue
        valid_rows.append([time_sec, absorbance])
    return pd.DataFrame(valid_rows, columns=['time', 'product'])


def fit_region(data: pd.DataFrame, start_time: float, end_time: float) -> Optional[Dict]:
    """Linear regression of product vs time within [start_time, end_time]."""
    region = data[(data['time'] >= start_time) & (data['time'] <= end_time)]
    if len(region) < 2:
        return None

    slope, intercept, r_value, _, std_err = stats.linregress(region['time'], region['product'])
    residuals = region['product'] - (slope * region['time'] + intercept)
    return {
        'slope': float(slope),
        'intercept': float(intercept),
        'r_squared': float(r_value ** 2),
        'std_error': float(std_err),
        'n_points': int(len(region)),
        'rmse': float(np.sqrt(np.mean(residuals ** 2))),
        'mean_absorbance': float(np.mean(region['product'])),
        'absorbance_std_dev': float(np.std(region['product'], ddof=1)),
    }


def convert_slope(slope: float, std_err: float, extinction_coeff: Optional[float],
                  conc_unit: str = 'UA', time_unit: str = 's',
                  path_length_cm: float = 1.0) -> Tuple[float, float, str]:
    """Convert an absorbance slope (UA/s) to concentration/time via Beer-Lambert.

    extinction_coeff is in mM⁻¹·cm⁻¹, so rate (mM/s) = slope / (ε · l).
    """
    converted_slope, converted_std_err, units = slope, std_err, 'UA/s'

    if extinction_coeff and extinction_coeff > 0 and path_length_cm and path_length_cm > 0 \
            and conc_unit in CONC_TO_MM:
        to_target = 1.0 / (extinction_coeff * path_length_cm) / CONC_TO_MM[conc_unit]
        converted_slope *= to_target
        converted_std_err *= to_target
        units = 'mM/s' if conc_unit == 'mM' else 'μM/s'

    if time_unit == 'min':
        converted_slope *= 60
        converted_std_err *= 60
        units = units.replace('/s', '/min')

    return converted_slope, converted_std_err, units


def enzyme_activity(rate: float, conc_unit: str, time_unit: str, reaction_volume_ml: float,
                    unit_type: str = 'U/mL', enzyme_volume_ml: Optional[float] = None,
                    enzyme_mass_mg: Optional[float] = None) -> Optional[Tuple[float, str]]:
    """Convert a concentration rate into enzyme activity (1 U = 1 µmol/min).

    mM · mL = µmol, so µmol/min = rate (mM/min) × reaction volume (mL).
    Returns None when the rate is not a concentration rate.
    """
    if conc_unit not in CONC_TO_MM or time_unit not in TIME_TO_MIN:
        return None

    rate_mm_per_min = rate * CONC_TO_MM[conc_unit] * TIME_TO_MIN[time_unit]
    umol_per_min = rate_mm_per_min * reaction_volume_ml

    if unit_type == 'U/mL':
        if not enzyme_volume_ml:
            return None
        return umol_per_min / enzyme_volume_ml, 'U/mL'
    if not enzyme_mass_mg:
        return None
    return umol_per_min / enzyme_mass_mg, 'U/mg'


def analyze_region(data: pd.DataFrame, start_time: float, end_time: float,
                   extinction_coeff: Optional[float] = None, conc_unit: str = 'UA',
                   time_unit: str = 's', path_length_cm: float = 1.0,
                   enzyme_units: Optional[Dict] = None) -> Optional[Dict]:
    """Fit a region and apply unit and enzyme-activity conversions."""
    fit = fit_region(data, start_time, end_time)
    if fit is None:
        return None

    converted_slope, converted_std_err, slope_units = convert_slope(
        fit['slope'], fit['std_error'], extinction_coeff, conc_unit, time_unit, path_length_cm)
    effective_conc_unit = conc_unit if slope_units.split('/')[0] != 'UA' else 'UA'

    activity, activity_units, activity_std_err = None, None, None
    if enzyme_units and enzyme_units.get('use_enzyme_units'):
        params = dict(conc_unit=effective_conc_unit, time_unit=time_unit,
                      reaction_volume_ml=enzyme_units['reaction_volume'],
                      unit_type=enzyme_units.get('enzyme_unit_type', 'U/mL'),
                      enzyme_volume_ml=enzyme_units.get('enzyme_volume'),
                      enzyme_mass_mg=enzyme_units.get('enzyme_mass'))
        result = enzyme_activity(converted_slope, **params)
        if result is not None:
            activity, activity_units = result
            activity_std_err = enzyme_activity(converted_std_err, **params)[0]

    return {
        **fit,
        'start': float(start_time),
        'end': float(end_time),
        'converted_slope': converted_slope,
        'converted_std_error': converted_std_err,
        'slope_units': slope_units,
        'extinction_coeff': extinction_coeff,
        'path_length_cm': path_length_cm if extinction_coeff else None,
        'enzyme_activity': activity,
        'enzyme_activity_std_error': activity_std_err,
        'enzyme_activity_units': activity_units,
    }


def _json_default(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def session_to_json(data_sets: Dict[str, pd.DataFrame], regions: Dict[str, Dict],
                    settings: Optional[Dict] = None) -> str:
    """Serialize datasets, regions and settings to a JSON string."""
    payload = {
        'format_version': SESSION_FORMAT_VERSION,
        'saved_at': datetime.now().isoformat(timespec='seconds'),
        'data_sets': {name: {'time': df['time'].tolist(), 'product': df['product'].tolist()}
                      for name, df in data_sets.items()},
        'regions': regions,
        'settings': settings or {},
    }
    return json.dumps(payload, default=_json_default, indent=1)


def session_from_json(text: str) -> Tuple[Dict[str, pd.DataFrame], Dict[str, Dict], Dict]:
    """Parse a session JSON string. Raises ValueError for files that are not sessions."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Not a valid JSON file: {error}") from error

    if not isinstance(payload, dict) or 'format_version' not in payload:
        raise ValueError("This file is not a Kinetics Analyzer session")
    if payload['format_version'] != SESSION_FORMAT_VERSION:
        raise ValueError(f"Unsupported session version {payload['format_version']!r} "
                         f"(expected {SESSION_FORMAT_VERSION})")

    data_sets = {name: pd.DataFrame({'time': values['time'], 'product': values['product']})
                 for name, values in payload.get('data_sets', {}).items()}
    return data_sets, payload.get('regions', {}), payload.get('settings', {})


def results_table(regions: List[Dict]) -> pd.DataFrame:
    """Numeric results table (one row per region) for display and export."""
    rows = []
    for region in regions:
        row = {
            'Dataset': region.get('dataset'),
            'Region': region.get('region_name'),
            'Start_Time': region['start'],
            'End_Time': region['end'],
            'Slope': region.get('converted_slope', region['slope']),
            'Slope_Units': region.get('slope_units', 'UA/s'),
            'Std_Error_Converted': region.get('converted_std_error', region['std_error']),
            'Original_Slope_UA_s': region['slope'],
            'Original_Std_Error': region['std_error'],
            'Extinction_Coeff': region.get('extinction_coeff'),
            'Path_Length_cm': region.get('path_length_cm'),
            'R_Squared': region['r_squared'],
            'Number_of_Points': region['n_points'],
            'RMSE': region['rmse'],
            'Mean_Absorbance': region.get('mean_absorbance'),
            'Absorbance_Std_Dev': region.get('absorbance_std_dev'),
        }
        if region.get('enzyme_activity') is not None:
            row['Enzyme_Activity'] = region['enzyme_activity']
            row['Enzyme_Activity_Units'] = region['enzyme_activity_units']
            row['Enzyme_Activity_Std_Error'] = region.get('enzyme_activity_std_error')
        rows.append(row)
    return pd.DataFrame(rows)


# Shown in the app header and at the end of the AvaSpec converter
QUOTES = [
    'The only way to make sense out of change is to plunge into it, move with it, and join the dance - Watts',
    'What we observe is not nature itself, but nature exposed to our method of questioning - Heisenberg',
    'Kinetics tells us how fast, thermodynamics tells us how far',
    'Every reaction has its optimal path - trust the data to show you',
    'R² > 0.99: Excellent fit. R² < 0.98: Time for coffee and reconsideration',
    'The enzyme knows chemistry better than the chemist',
    'Linear kinetics: when enzymes behave like good students',
    "Why don't enzymes ever get tired? They have infinite turnover rates in their dreams",
    'Enzymes are like good friends: they lower your activation energy for getting things done',
    'What did the substrate say to the enzyme? You complete me... by breaking me apart',
    'Allosteric enzymes: proof that proteins have mood swings',
    "Fact: Some enzymes are so efficient they approach the diffusion limit - nature's speed demons",
    'Enzymes: billions of years of R&D, no patents required',
    "DNA: the world's most successful backup system (with occasional corrupted files)",
    'RNA: Jack of all trades, master of everything - sorry proteins!',
    "Ribozymes proved that RNA doesn't need protein chaperones to get things done",
    "DNA polymerase has 3' to 5' exonuclease activity because even evolution believes in proofreading",
    'Why did the ribosome break up with the polysome? Too much translation drama',
    'Fact: Your DNA contains the instructions for about 20,000-25,000 proteins (assembly required)',
    'Telomerase: the enzyme trying to make you immortal (aging has entered the chat)',
    "DNA repair mechanisms: your genome's personal IT department working 24/7",
    "Why don't DNA strands ever get lost? They always know their 5' from their 3' end",
    'LUCA (Last Universal Common Ancestor): the ultimate single parent raising 4 billion years of offspring',
    'RNA World hypothesis: back when RNA was CEO, CFO, and the entire workforce',
    "Primordial soup: Earth's first attempt at molecular cuisine (no recipe book included)",
    'Iron-sulfur clusters: the original catalysts, still going strong after 3.8 billion years',
    'Miller-Urey experiment: proof that you can make amino acids from lightning and patience',
    'Fact: Cyanobacteria invented photosynthesis and accidentally created the oxygen apocalypse',
    "Hydrothermal vents: where life possibly started in nature's pressure cookers",
    'Self-replication: the ultimate mystery - how did molecules learn to copy themselves?',
    'From chemistry to biology: the greatest startup story never fully documented',
    'Autocatalytic networks: when molecules formed the first self-sustaining businesses',
    'Evolution: 4 billion years of A/B testing with no rollback option',
    'Endosymbiotic theory: the first successful corporate merger in cellular history',
    'In God we trust, all others must bring data - Deming',
    "The best thing about being a statistician is that you get to play in everyone's backyard - Tukey",
    "Without data, you're just another person with an opinion - Edwards",
    'Correlation does not imply causation, but it does waggle its eyebrows suggestively',
    'A good plot is worth a thousand p-values',
    'Caffeine: the molecule that powers science',
    'Good coffee, good data, good science',
    'Lab rule #1: Never trust data collected before the first cup of coffee',
    'Science runs on coffee and curiosity',
    'The universal solvent for scientific problems: coffee',
    'Fact: Your morning coffee contains over 1000 different chemical compounds',
    'Fact: Ribozymes can cut and paste RNA like molecular scissors and glue',
    'Fact: The ribosome is a ribozyme - your protein factory is made of RNA',
    'Fact: Some RNA molecules can evolve in test tubes in just hours',
    'Fact: DNA repair enzymes fix about 1000 DNA damages per cell per day - busy little workers',
    'Science is not only compatible with spirituality; it is a profound source of spirituality - Sagan',
    'Fact: If you stretched out all the DNA in your body, it would reach the sun and back 300 times',
    'RNA splicing: where introns go to disappear and exons get their moment to shine',
    'Fact: All life shares the same genetic code because we all descended from one successful experiment',
    'Fact: The Michaelis-Menten equation was derived in 1913 - still going strong!',
    'Fact: Data conversion is the bridge between raw measurements and scientific insights',
]
