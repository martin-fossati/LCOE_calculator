# import package

import streamlit as st
import pandas as pd

# import calculation engine

from LCOE_model import model_runner


#.................
# Page Title
#................



st.title("LCOE Calculator for a solar plant")

st.write("Key modelling assumptions")

#.................
# User input
#................

capacity = st.number_input(
    "Plant Capacity (MW)",
    value=60.0
)

yield_per_mw = st.number_input(
    "Yield (MWh/MWp)",
    value=1100.0
)

capex = st.number_input(
    "CAPEX (£/MW)",
    value=850.0
)

opex = st.number_input(
    "OPEX (£/MW/year)",
    value=25.0
)

discount_rate = st.number_input(
    "Discount Rate (%)",
    value=8.0
)



#.................
# Add variables into a dictionary
#................


params = {
    "MW_capacity": capacity,
    "p_yield": yield_per_mw,
    "CAPEX_MW": capex,
    "OPEX_MW": opex,
    "discount_rate": discount_rate / 100
}

#.................
# Run model
#................


calculate = st.button("Calculate LCOE")


if calculate:

    results, results_table, sensitivity_df = model_runner(params)

    st.success("Calculation completed")

    st.metric(
        "LCOE",
        f"£{results['LCOE']:.1f}/MWh"
    )

    st.subheader("Model Outputs")
    st.dataframe(results_table, hide_index=True)

    st.subheader("Sensitivity Analysis")
    st.dataframe(sensitivity_df)

    st.caption(
    """
    Implicit assumptions:
    
    • Degradation rate: 0.30%
    • Curtailment: 0.00%
    • Inflation: 2.00%
    • Tax rate: 25.00%
    • Asset life: 25 years
    • Construction length: 9 months
    • Construction spending profile: S-Curve
    • Operation start date: 01-2027
    • Operation end date: 12-2051
    """)