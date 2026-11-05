from pathlib import Path
import csv
import math


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
STRUCTURED_DIR = PROCESSED_DIR / "structured"

UNIFIED_IN = STRUCTURED_DIR / "unified_vle_dataset.csv"
MODEL_IN = STRUCTURED_DIR / "modeling_dataset.csv"

HARTONO_IN = (
    PROCESSED_DIR /
    "hartono_2020_amp_co2_h2o_experimental.csv"
)

DASH_IN = (
    PROCESSED_DIR /
    "dash_2011_amp_pz_co2_h2o_table7.csv"
)

UNIFIED_OUT = (
    STRUCTURED_DIR /
    "unified_vle_dataset_with_hartono_dash.csv"
)

MODEL_OUT = (
    STRUCTURED_DIR /
    "modeling_dataset_with_hartono_dash.csv"
)

HARTONO_NORMALIZED_OUT = (
    PROCESSED_DIR /
    "hartono_2020_amp_co2_h2o_normalized.csv"
)

DASH_NORMALIZED_OUT = (
    PROCESSED_DIR /
    "dash_2011_amp_pz_co2_h2o_table7_normalized.csv"
)


# ============================================================
# HELPERS
# ============================================================

def read_csv(path):

    if not path.exists():
        raise FileNotFoundError(
            f"\nFile not found:\n{path}\n"
            f"\nExpected project root:\n{PROJECT_ROOT}\n"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(rows)


def to_float(value):

    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    try:
        return float(value)

    except (ValueError, TypeError):
        return None


def fmt(value):

    if value is None:
        return ""

    if isinstance(value, float):

        if math.isnan(value):
            return ""

        return f"{value:.12g}"

    return str(value)


# ============================================================
# HARTONO SOURCE TABLE
# ============================================================

def make_source_table(source_table):

    if source_table is None:
        return "Hartono_2020_Unknown"

    value = str(source_table).strip()

    if value == "":
        return "Hartono_2020_Unknown"

    value = value.replace(" ", "_")

    if value.lower().startswith("table_"):
        value = value[6:]

    elif value.lower().startswith("table"):
        value = value[5:]

    return f"Hartono_2020_Table{value}"


# ============================================================
# HARTONO PRESSURE HANDLING
# ============================================================

def get_experimental_pressure(row):

    """
    Hartono contains two pressure conventions.

    Tables 4-6:
        pressure_type = pCO2
        -> use pCO2_kPa

    Tables 7-9:
        pressure_type = P_total
        -> use p_total_kPa

    IMPORTANT:
    We NEVER calculate/invent pCO2 from P_total.
    """

    pressure_type = str(
        row.get("pressure_type", "")
    ).strip().lower()

    pCO2 = to_float(
        row.get("pCO2_kPa")
    )

    p_total = to_float(
        row.get("p_total_kPa")
    )

    if pressure_type == "pco2":
        return pCO2

    if pressure_type in {
        "p_total",
        "ptotal",
        "p total"
    }:
        return p_total

    # --------------------------------------------------------
    # Fallback only when pressure_type is missing.
    # --------------------------------------------------------

    if pCO2 is not None:
        return pCO2

    if p_total is not None:
        return p_total

    return None


def get_pressure_source(row):

    pressure_type = str(
        row.get("pressure_type", "")
    ).strip().lower()

    if pressure_type == "pco2":
        return "pCO2_kPa"

    if pressure_type in {
        "p_total",
        "ptotal",
        "p total"
    }:
        return "p_total_kPa"

    if to_float(
        row.get("pCO2_kPa")
    ) is not None:
        return "pCO2_kPa"

    if to_float(
        row.get("p_total_kPa")
    ) is not None:
        return "p_total_kPa"

    return ""


# ============================================================
# HARTONO NORMALIZATION
# ============================================================

def normalize_hartono(rows):

    output = []

    for i, row in enumerate(rows, start=1):

        # ----------------------------------------------------
        # Temperature
        # ----------------------------------------------------

        T_K = to_float(
            row.get("temperature_K")
        )

        T_C = (
            T_K - 273.15
            if T_K is not None
            else None
        )

        # ----------------------------------------------------
        # Concentration
        # ----------------------------------------------------

        amp_M = to_float(
            row.get("amp_molarity_M")
        )

        amp_wt = to_float(
            row.get("amp_wt_pct")
        )

        pz_wt = to_float(
            row.get("pz_wt_pct")
        )

        # ----------------------------------------------------
        # Pressure
        # ----------------------------------------------------

        pCO2 = to_float(
            row.get("pCO2_kPa")
        )

        u_pCO2 = to_float(
            row.get("u_p_kPa")
        )

        p_total = to_float(
            row.get("p_total_kPa")
        )

        u_p_total = to_float(
            row.get("u_p_total_kPa")
        )

        pressure_type = str(
            row.get("pressure_type", "")
        ).strip()

        experimental_pressure = (
            get_experimental_pressure(row)
        )

        pressure_source = (
            get_pressure_source(row)
        )

        P_MPa = (
            experimental_pressure / 1000.0
            if experimental_pressure is not None
            else None
        )

        # ----------------------------------------------------
        # Loading
        # ----------------------------------------------------

        loading = to_float(
            row.get(
                "loading_molCO2_per_molamine"
            )
        )

        u_loading = to_float(
            row.get("u_loading")
        )

        # ----------------------------------------------------
        # Source table
        # ----------------------------------------------------

        table = row.get(
            "table",
            ""
        )

        source_table = make_source_table(
            table
        )

        # ----------------------------------------------------
        # Output
        # ----------------------------------------------------

        output.append({

            "measurement_id": f"HARTONO_{i}",

            "source": row.get(
                "source",
                "Hartono et al. (2020)"
            ),

            "table": table,

            "source_table": source_table,

            "system": row.get(
                "system",
                "AMP-CO2-H2O"
            ),

            "experiment": row.get(
                "experiment",
                ""
            ),

            # Temperature
            "temperature_K": fmt(T_K),
            "T_C": fmt(T_C),
            "T_K": fmt(T_K),

            # Concentration
            "amp_molarity_M": fmt(amp_M),
            "amp_wt_pct": fmt(amp_wt),
            "pz_wt_pct": fmt(pz_wt),

            # Pressure metadata
            "pressure_type": pressure_type,
            "pressure_source": pressure_source,

            # Original pCO2
            "pCO2_kPa": fmt(pCO2),
            "u_pCO2_kPa": fmt(u_pCO2),
            "pCO2_MPa": fmt(
                pCO2 / 1000.0
                if pCO2 is not None
                else None
            ),

            # Original total pressure
            "p_total_kPa": fmt(p_total),
            "u_p_total_kPa": fmt(u_p_total),
            "p_total_MPa": fmt(
                p_total / 1000.0
                if p_total is not None
                else None
            ),

            # Pressure actually used
            "P_kPa": fmt(
                experimental_pressure
            ),

            "P_MPa": fmt(
                P_MPa
            ),

            # Loading
            "loading_molCO2_per_molamine": fmt(
                loading
            ),

            "u_loading": fmt(
                u_loading
            ),

            "co2_to_amine_ratio": fmt(
                loading
            ),

            # Common names
            "wt_percent": fmt(
                amp_wt
            ),

            "molarity": fmt(
                amp_M
            ),
        })

    return output


# ============================================================
# DASH NORMALIZATION
# ============================================================

def normalize_dash(rows):

    output = []

    for i, row in enumerate(rows, start=1):

        # ----------------------------------------------------
        # Temperature
        # ----------------------------------------------------

        T_K = to_float(
            row.get("temperature_K")
        )

        T_C = (
            T_K - 273.15
            if T_K is not None
            else None
        )

        # ----------------------------------------------------
        # Concentration
        # ----------------------------------------------------

        amp_wt = to_float(
            row.get("amp_wt_pct")
        )

        pz_wt = to_float(
            row.get("pz_wt_pct")
        )

        amp_M = to_float(
            row.get("amp_molarity_M")
        )

        pz_M = to_float(
            row.get("pz_molarity_M")
        )

        # ----------------------------------------------------
        # Pressure
        # ----------------------------------------------------

        pCO2 = to_float(
            row.get("pCO2_kPa")
        )

        u_p = to_float(
            row.get("u_p_kPa")
        )

        P_MPa = (
            pCO2 / 1000.0
            if pCO2 is not None
            else None
        )

        # ----------------------------------------------------
        # Loading
        # ----------------------------------------------------

        loading = to_float(
            row.get(
                "loading_molCO2_per_molamine"
            )
        )

        u_loading = to_float(
            row.get("u_loading")
        )

        # ----------------------------------------------------
        # Total concentration
        # ----------------------------------------------------

        total_wt = None

        if (
            amp_wt is not None
            and pz_wt is not None
        ):
            total_wt = (
                amp_wt + pz_wt
            )

        total_M = None

        if (
            amp_M is not None
            and pz_M is not None
        ):
            total_M = (
                amp_M + pz_M
            )

        # ----------------------------------------------------
        # Output
        # ----------------------------------------------------

        output.append({

            "measurement_id": f"DASH_{i}",

            "source": row.get(
                "source",
                "Dash et al. (2011)"
            ),

            "table": row.get(
                "table",
                ""
            ),

            "source_table": "Dash_2011_Table7",

            "system": row.get(
                "system",
                "AMP-PZ-CO2-H2O"
            ),

            # Temperature
            "temperature_K": fmt(T_K),
            "T_C": fmt(T_C),
            "T_K": fmt(T_K),

            # Concentration
            "amp_wt_pct": fmt(amp_wt),
            "pz_wt_pct": fmt(pz_wt),

            "amp_molarity_M": fmt(amp_M),
            "pz_molarity_M": fmt(pz_M),

            # Pressure
            "pressure_type": "pCO2",
            "pressure_source": "pCO2_kPa",

            "pCO2_kPa": fmt(pCO2),
            "u_p_kPa": fmt(u_p),
            "pCO2_MPa": fmt(P_MPa),

            "P_kPa": fmt(pCO2),
            "P_MPa": fmt(P_MPa),

            # Loading
            "loading_molCO2_per_molamine": fmt(
                loading
            ),

            "u_loading": fmt(
                u_loading
            ),

            "co2_to_amine_ratio": fmt(
                loading
            ),

            # Common modeling fields
            "wt_percent": fmt(
                total_wt
            ),

            "molarity": fmt(
                total_M
            ),
        })

    return output


# ============================================================
# CONVERT TO COMMON DATASET
# ============================================================

def hartono_to_common(rows, start_id):

    output = []

    measurement_id = start_id

    for row in rows:

        output.append({

            "measurement_id": measurement_id,

            "source_table": row[
                "source_table"
            ],

            "system": row[
                "system"
            ],

            "concentration": (
                f"{row['amp_wt_pct']} wt% - "
                f"{row['amp_molarity_M']} M"
            ),

            "wt_percent": row[
                "wt_percent"
            ],

            "molarity": row[
                "molarity"
            ],

            "T_C": row[
                "T_C"
            ],

            "P_kPa": row[
                "P_kPa"
            ],

            "x1": "",
            "u_x1": "",
            "y1": "",
            "u_y1": "",

            "x2": "",
            "u_x2": "",
            "y2": "",
            "u_y2": "",

            "x3": "",
            "u_x3": "",

            "T_K": row[
                "T_K"
            ],

            "P_MPa": row[
                "P_MPa"
            ],

            "co2_to_amine_ratio": row[
                "co2_to_amine_ratio"
            ],

            # IMPORTANT:
            # Keep pressure provenance.
            "pressure_type": row[
                "pressure_type"
            ],

            "pressure_source": row[
                "pressure_source"
            ],
        })

        measurement_id += 1

    return output


def dash_to_common(rows, start_id):

    output = []

    measurement_id = start_id

    for row in rows:

        output.append({

            "measurement_id": measurement_id,

            "source_table": row[
                "source_table"
            ],

            "system": row[
                "system"
            ],

            "concentration": (
                f"{row['amp_wt_pct']} wt% AMP - "
                f"{row['pz_wt_pct']} wt% PZ"
            ),

            "wt_percent": row[
                "wt_percent"
            ],

            "molarity": row[
                "molarity"
            ],

            "T_C": row[
                "T_C"
            ],

            "P_kPa": row[
                "P_kPa"
            ],

            "x1": "",
            "u_x1": "",
            "y1": "",
            "u_y1": "",

            "x2": "",
            "u_x2": "",
            "y2": "",
            "u_y2": "",

            "x3": "",
            "u_x3": "",

            "T_K": row[
                "T_K"
            ],

            "P_MPa": row[
                "P_MPa"
            ],

            "co2_to_amine_ratio": row[
                "co2_to_amine_ratio"
            ],

            "pressure_type": row[
                "pressure_type"
            ],

            "pressure_source": row[
                "pressure_source"
            ],
        })

        measurement_id += 1

    return output


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("INTEGRATING HARTONO (2020) + DASH (2011)")
    print("=" * 70)

    print("\nProject root:")
    print(f"  {PROJECT_ROOT}")

    # --------------------------------------------------------
    # Check directories
    # --------------------------------------------------------

    for directory in [
        DATA_DIR,
        PROCESSED_DIR,
        STRUCTURED_DIR
    ]:

        if not directory.exists():

            raise FileNotFoundError(
                f"Required directory does not exist:\n"
                f"{directory}"
            )

    # --------------------------------------------------------
    # Load original datasets
    #
    # IMPORTANT:
    # We deliberately read the ORIGINAL datasets here.
    # This prevents duplicated Hartono/Dash rows if this
    # script is executed multiple times.
    # --------------------------------------------------------

    print("\nLoading original unified dataset...")

    unified_rows = read_csv(
        UNIFIED_IN
    )

    print(
        f"  Existing unified rows: "
        f"{len(unified_rows)}"
    )

    print("\nLoading original modeling dataset...")

    modeling_rows = read_csv(
        MODEL_IN
    )

    print(
        f"  Existing modeling rows: "
        f"{len(modeling_rows)}"
    )

    # --------------------------------------------------------
    # Load Hartono
    # --------------------------------------------------------

    print("\nLoading Hartono...")

    hartono_raw = read_csv(
        HARTONO_IN
    )

    print(
        f"  Hartono raw rows: "
        f"{len(hartono_raw)}"
    )

    # --------------------------------------------------------
    # Load Dash
    # --------------------------------------------------------

    print("\nLoading Dash...")

    dash_raw = read_csv(
        DASH_IN
    )

    print(
        f"  Dash raw rows: "
        f"{len(dash_raw)}"
    )

    # --------------------------------------------------------
    # Normalize
    # --------------------------------------------------------

    print("\nNormalizing Hartono...")

    hartono = normalize_hartono(
        hartono_raw
    )

    print(
        f"  Normalized Hartono rows: "
        f"{len(hartono)}"
    )

    print("\nNormalizing Dash...")

    dash = normalize_dash(
        dash_raw
    )

    print(
        f"  Normalized Dash rows: "
        f"{len(dash)}"
    )

    # ========================================================
    # SAVE NORMALIZED DATASETS
    # ========================================================

    normalized_hartono_fields = [

        "measurement_id",
        "source",
        "table",
        "source_table",
        "system",
        "experiment",

        "temperature_K",
        "T_C",
        "T_K",

        "amp_molarity_M",
        "amp_wt_pct",
        "pz_wt_pct",

        "pressure_type",
        "pressure_source",

        "pCO2_kPa",
        "u_pCO2_kPa",
        "pCO2_MPa",

        "p_total_kPa",
        "u_p_total_kPa",
        "p_total_MPa",

        "P_kPa",
        "P_MPa",

        "loading_molCO2_per_molamine",
        "u_loading",

        "wt_percent",
        "molarity",
        "co2_to_amine_ratio",
    ]

    normalized_dash_fields = [

        "measurement_id",
        "source",
        "table",
        "source_table",
        "system",

        "temperature_K",
        "T_C",
        "T_K",

        "amp_wt_pct",
        "pz_wt_pct",

        "amp_molarity_M",
        "pz_molarity_M",

        "pressure_type",
        "pressure_source",

        "pCO2_kPa",
        "u_p_kPa",
        "pCO2_MPa",

        "P_kPa",
        "P_MPa",

        "loading_molCO2_per_molamine",
        "u_loading",

        "wt_percent",
        "molarity",
        "co2_to_amine_ratio",
    ]

    write_csv(
        HARTONO_NORMALIZED_OUT,
        hartono,
        normalized_hartono_fields
    )

    write_csv(
        DASH_NORMALIZED_OUT,
        dash,
        normalized_dash_fields
    )

    print("\nSaved normalized files.")

    # ========================================================
    # DETERMINE IDs
    # ========================================================

    existing_ids = []

    for row in unified_rows:

        value = to_float(
            row.get("measurement_id")
        )

        if value is not None:
            existing_ids.append(
                int(value)
            )

    next_unified_id = (
        max(existing_ids) + 1
        if existing_ids
        else 1
    )

    existing_model_ids = []

    for row in modeling_rows:

        value = to_float(
            row.get("measurement_id")
        )

        if value is not None:
            existing_model_ids.append(
                int(value)
            )

    next_model_id = (
        max(existing_model_ids) + 1
        if existing_model_ids
        else 1
    )

    # ========================================================
    # CONVERT TO UNIFIED
    # ========================================================

    print("\nConverting Hartono -> unified...")

    hartono_unified = hartono_to_common(
        hartono,
        next_unified_id
    )

    next_unified_id += len(
        hartono_unified
    )

    print("Converting Dash -> unified...")

    dash_unified = dash_to_common(
        dash,
        next_unified_id
    )

    unified_combined = (
        unified_rows
        + hartono_unified
        + dash_unified
    )

    # ========================================================
    # CONVERT TO MODELING
    # ========================================================

    print("\nConverting Hartono -> modeling...")

    hartono_modeling = hartono_to_common(
        hartono,
        next_model_id
    )

    next_model_id += len(
        hartono_modeling
    )

    print("Converting Dash -> modeling...")

    dash_modeling = dash_to_common(
        dash,
        next_model_id
    )

    modeling_combined = (
        modeling_rows
        + hartono_modeling
        + dash_modeling
    )

    # ========================================================
    # FINAL UNIFIED SCHEMA
    # ========================================================

    unified_fields = [

        "measurement_id",

        "source_table",
        "system",
        "concentration",

        "wt_percent",
        "molarity",

        "T_C",
        "P_kPa",

        "x1",
        "u_x1",
        "y1",
        "u_y1",

        "x2",
        "u_x2",
        "y2",
        "u_y2",

        "x3",
        "u_x3",

        "T_K",
        "P_MPa",

        "co2_to_amine_ratio",

        # New metadata
        "pressure_type",
        "pressure_source",
    ]

    # ========================================================
    # FINAL MODELING SCHEMA
    # ========================================================

    modeling_fields = [

        "measurement_id",

        "source_table",
        "system",
        "concentration",

        "wt_percent",
        "molarity",

        "T_C",
        "P_kPa",

        "x1",
        "u_x1",
        "y1",
        "u_y1",

        "x2",
        "u_x2",
        "y2",
        "u_y2",

        "x3",
        "u_x3",

        "T_K",
        "P_MPa",

        "co2_to_amine_ratio",

        # CRITICAL METADATA
        "pressure_type",
        "pressure_source",
    ]

    # ========================================================
    # SAVE FINAL DATASETS
    # ========================================================

    write_csv(
        UNIFIED_OUT,
        unified_combined,
        unified_fields
    )

    write_csv(
        MODEL_OUT,
        modeling_combined,
        modeling_fields
    )

    # ========================================================
    # VALIDATION
    # ========================================================

    print("\n" + "=" * 70)
    print("VALIDATION")
    print("=" * 70)

    # --------------------------------------------------------
    # Hartono pressure validation
    # --------------------------------------------------------

    print("\nHartono pressure handling:")

    for pressure_type in [
        "pCO2",
        "P_total"
    ]:

        subset = [
            r for r in hartono
            if r["pressure_type"] == pressure_type
        ]

        pressures = [
            to_float(r["P_kPa"])
            for r in subset
            if to_float(r["P_kPa"]) is not None
        ]

        if pressures:

            print(
                f"  {pressure_type:8s}: "
                f"{len(pressures):3d} rows | "
                f"min={min(pressures):.6g} kPa | "
                f"max={max(pressures):.6g} kPa"
            )

    # --------------------------------------------------------
    # Source counts
    # --------------------------------------------------------

    print("\nFinal rows by source:")

    source_counts = {}

    for row in modeling_combined:

        source = row["source_table"]

        source_counts[source] = (
            source_counts.get(source, 0) + 1
        )

    for source, count in source_counts.items():

        print(
            f"  {source:30s} {count:4d}"
        )

    # --------------------------------------------------------
    # Pressure types in final modeling dataset
    # --------------------------------------------------------

    print("\nFinal pressure types:")

    pressure_counts = {}

    for row in modeling_combined:

        pressure_type = row.get(
            "pressure_type",
            ""
        )

        if pressure_type == "":
            pressure_type = "original_dataset"

        pressure_counts[pressure_type] = (
            pressure_counts.get(
                pressure_type,
                0
            ) + 1
        )

    for pressure_type, count in pressure_counts.items():

        print(
            f"  {pressure_type:20s} {count:4d}"
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    print("\n" + "=" * 70)
    print("INTEGRATION COMPLETE")
    print("=" * 70)

    print(
        f"\nOriginal unified rows : "
        f"{len(unified_rows)}"
    )

    print(
        f"Hartono rows added   : "
        f"{len(hartono_unified)}"
    )

    print(
        f"Dash rows added      : "
        f"{len(dash_unified)}"
    )

    print(
        f"Final unified rows   : "
        f"{len(unified_combined)}"
    )

    print()

    print(
        f"Original modeling rows: "
        f"{len(modeling_rows)}"
    )

    print(
        f"Hartono rows added    : "
        f"{len(hartono_modeling)}"
    )

    print(
        f"Dash rows added       : "
        f"{len(dash_modeling)}"
    )

    print(
        f"Final modeling rows   : "
        f"{len(modeling_combined)}"
    )

    print("\nOutput files:")

    print(
        f"\n  {UNIFIED_OUT}"
    )

    print(
        f"\n  {MODEL_OUT}"
    )

    print(
        f"\n  {HARTONO_NORMALIZED_OUT}"
    )

    print(
        f"\n  {DASH_NORMALIZED_OUT}"
    )

    print("\nDone.")


if __name__ == "__main__":
    main()