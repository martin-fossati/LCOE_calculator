# import packages

import pandas as pd # pandas package
import numpy as np # numpy pacakge
import matplotlib.pyplot as plt # excel editor
import openpyxl

from scipy.stats import norm # package needed to S-Curve for construcion
from openpyxl.styles import Alignment, Font, Border, Side   # package to format file when exporting to Excel
from openpyxl.utils import get_column_letter

# Default inputs

## model timeline

start_timeline = pd.Timestamp('2026-01-01') # starting date for timeline
length_timeline = 30  # timeline length in number of years

## construction timeline

con_start=pd.Timestamp('2026-04-01')
con_length= 9 # construction duration in number of months

# plant operations

asset_life= 25 # asset life in years
curtailment= 0.0 # curtailment rate
degradation_rate= 0.003 # panel degradation rate
seasonality_profile = {
    1: 0.035, 2: 0.050, 3: 0.085, 4: 0.105, 5: 0.125, 6: 0.140,
    7: 0.135, 8: 0.115, 9: 0.090, 10: 0.065, 11: 0.035, 12: 0.020}

# Macro variables

inflation_rate=0.02 # inflation rate
tax_rate=0.25 # tax rate
price_base=2026 # price base for the calculations

# Other parameters
integrity=0.01
thousand=1000.0

# Input consolidation



# Functions to use for the LCOE calculation

## Model timeline function

def model_timeline_func(p):
    # set up the model timeline
    timeline=pd.date_range(start=p['start_timeline'], periods= p['length_timeline'] *12, freq="MS")
    # add the timeline to a data framework [table]
    df=pd.DataFrame(index=timeline)
    return timeline, df



## Construction


def construction_func(df,p):
    
    # Determine construction end date
    con_end = p['con_start'] + pd.DateOffset(months=p['con_length']-1) 
    
    # Create construciton timeline
    df["construction_timeline"]= np.where((df.index>=p['con_start'])& (df.index<=con_end),1,0)
    
    # calculate construction period
    df["construction_period"]= df["construction_timeline"].cumsum() * df["construction_timeline"]
    
    # S-Curve calculations
    elapsed_months= df["construction_period"]
    progress_ratio = elapsed_months / p['con_length']
    df["s_curve"] = norm.cdf(progress_ratio * 4 - 2)
    s_min= df.loc[df["construction_timeline"] == 1, "s_curve"].min() 
    s_max= df.loc[df["construction_timeline"] == 1, "s_curve"].max()
    df["s_curve"] = np.where(df["construction_timeline"] == 1, (df["s_curve"] - s_min) / (s_max - s_min), 0)

    # calculate CAPEX costs 
    total_CAPEX= p['CAPEX_MW'] * p['MW_capacity']
    df["CAPEX_spending"]= total_CAPEX * df["s_curve"].diff().fillna(df["s_curve"]) * df["construction_timeline"]
                                                                                      
    # integratity check
    allocated_CAPEX=df["CAPEX_spending"].sum()
    if not np.isclose(allocated_CAPEX, total_CAPEX, atol=p['integrity']):
        print(f"ERROR: CAPEX Mismatch! Total: {total_CAPEX:,.2f}, Allocated: {allocated_CAPEX:,.2f}")
    else:
        print("Success: Total CAPEX successfully allocated across the S-curve.")

    # catch outputs
    results_con={"con_end":con_end,"total_CAPEX":total_CAPEX}
    
    return results_con
    


## Operation timeline

def operations_timeline_func (df, p, output):
    
    # Operations start and end dates
    operations_start = output['con_end'] + pd.DateOffset(months=1)
    operations_end= operations_start + pd.DateOffset(years= p['asset_life']) - pd.DateOffset(months=1)
    
    # operation_timeline
    df["operational_timeline"]=np.where(((df.index>=operations_start)& (df.index<=operations_end)),1,0)
    
    # operational periods
    df["operational_period"]=df["operational_timeline"].cumsum() * df["operational_timeline"]
    df["operational_year"]=((df["operational_period"]-1)//12+1)* df["operational_timeline"]

    # catch results
    results_ops={"operations_start":operations_start,"operations_end":operations_end}
    
    return results_ops, df



## Electricity production

def electricity_production_func(df,p):
    
    # degradation set up as scalar using np.where
    degradation= np.where(df["operational_timeline"]== 1,  1 / ((1+ p['degradation_rate'])**(df["operational_year"]-1)) , 1 )
    
    # degradation set up added a a column to the df 
    df["degradation"]=1.0
    df.loc[df["operational_timeline"]== 1 , "degradation"] =  1 / ((1+ p['degradation_rate'])**(df["operational_year"]-1))
    
    # seasonality
    df["seasonality"]=df.index.month.map(p['seasonality_profile'])
    
    # electricity production
    df["electricity_exports"] = 0.0
    df.loc[df["operational_timeline"]==1, "electricity_exports"]=  p['p_yield'] *  p['MW_capacity'] * df["degradation"] * (1 - p['curtailment']) * df["seasonality"]

    # integrity check

    annual_seasonality= df["seasonality"].sum()/ p['length_timeline']

    if not np.isclose(annual_seasonality, 1, atol=p['integrity']):
        print(f"ERROR: Annual seasonality allocation is different to 100%! Total: {annual_seasonality:,.2f}")
  

    
    # catch results
    results_elec={"degradation":degradation}
    
    return df,degradation




## Inflation assumption

def inflation_func(df,p):
    df["indexation_period"]= df.index.year- p['price_base']   
    df["inflation"]= ( 1 + p['inflation_rate']) ** df[ "indexation_period" ]
    return df
    



## Discount factor

def discount_factor_func(df,p,output):
    # Days until or from COD
    df["days_from_COD"]= (df.index- output['operations_start']).days
    # Discount factor calculation
    df["discount_factor"]=  1 / ( (1+p['discount_rate']) ** (df["days_from_COD"] / 365.25))
    return df




## OPEX


def OPEX_func(df,p):
    df["OPEX"]=0.0
    df.loc[df["operational_timeline"]== 1,"OPEX"]= p['OPEX_MW'] * df["inflation"] * p['MW_capacity'] /12 
    return df



## LCOE calculations

def LCOE_calculation_func(df):
    
    # Numenator- total costs
    df["total_costs"]= df["CAPEX_spending"]+ df["OPEX"]
    df["discounted_total_costs"]= df["total_costs"] * df["discount_factor"]
    sum_total_costs= df["total_costs"].sum()
    
    # deonominator- electricity exports
    df["discounted_electricity_exports"]= df["electricity_exports"] * df["discount_factor"]
    sum_electricity= df["electricity_exports"].sum()
    
    # NPV calculations
    NPV_sum_total_costs= df["discounted_total_costs"].sum()
    NPV_sum_electricity= df["discounted_electricity_exports"].sum()

    # LCOE
    LCOE= NPV_sum_total_costs/ NPV_sum_electricity * 1000

    # catch results
    results_LCOE={'sum_total_costs':sum_total_costs, 
                  'sum_electricity':sum_electricity,
                  'NPV_sum_total_costs':NPV_sum_total_costs,
                  'NPV_sum_electricity':NPV_sum_electricity,
                  'LCOE':LCOE}
    
    return  df, results_LCOE


## Sensitivities

# function to update the discount rates used for the sensitivities

def re_run_variables(df, p,output):

    temp_df=df.copy()
    temp_df = discount_factor_func(temp_df, p, output)
    temp_df,degradation= electricity_production_func(temp_df,p)
    temp_df, results_LCOE = LCOE_calculation_func(temp_df)
    return results_LCOE['LCOE']
    
# sensitivity fuction

def sensitivity_func(df, p, output, LCOE_recalculation):
    
    # Define the "delta" steps
    
    dr_steps = [-0.01, -0.005, 0, 0.005, 0.01]  # -100bps, -50bps, base, +50bps, +100bps
    yield_steps = [-200, -100, 0, 100, 200]    # -200, -100, base, +100, +200

    results_matrix = []

    for dr_delta in dr_steps:
        row_data = []
        for y_delta in yield_steps:
            # 1. Clone the master dictionary
            temp_p = p.copy()
            temp_df=df.copy() 
            
            # 2. Inject the variation
            temp_p['discount_rate'] = p['discount_rate'] + dr_delta
            temp_p['p_yield'] = p['p_yield'] + y_delta
            
            # 3. Run the calculation (using your LCOE logic function)
            
            # This function should contain all the logic that produces results_LCOE['LCOE']
            
            new_lcoe = LCOE_recalculation(temp_df, temp_p,output)
            
            row_data.append(new_lcoe)
       
        results_matrix.append(row_data)

    # Create the final Sensitivity DataFrame
    sensitivity_df = pd.DataFrame(results_matrix, index=[f"DR: {(p['discount_rate'] + d)*100:.1f}%" for d in dr_steps],
        columns=[f"Yield: {p['p_yield'] + y}" for y in yield_steps])
    sensitivity_df.index.name = "Discount rate | electricity yield" 
    
    sensitivity_df = sensitivity_df.round(1)
    
    return sensitivity_df



## Run model 

def model_runner(params):
    
    params.update({
        "start_timeline":start_timeline,
        "length_timeline":length_timeline,
        "con_start": con_start,
        "con_length":con_length, 
        "asset_life":asset_life,
        "curtailment":curtailment,
        "degradation_rate":degradation_rate,
        "seasonality_profile": seasonality_profile,
        "inflation_rate": inflation_rate,
        "tax_rate": tax_rate,
   	"price_base": price_base,
        "integrity": integrity,
        "thousand": thousand
       })

    # set up timeline and model framework
    timeline, df = model_timeline_func(params)
    
    # construction calculations
    results_con= construction_func(df,params)
    
    # operations timeline
    results_ops, df= operations_timeline_func (df,params,results_con)
    
    # electricity calculations
    df, degradation =electricity_production_func(df, params)
    
    # inflation and discount factor
    df= inflation_func(df,params)
    df=discount_factor_func(df,params,results_ops)

    # OPEX
    df= OPEX_func(df,params)

    #LCOE
    df, results_LCOE = LCOE_calculation_func(df)

    # sensitivity 

    sensitivity_df=sensitivity_func(df, params,results_ops, re_run_variables)

    # Format result table

    results_table = pd.DataFrame({
    "Metric": [
        "Total Costs (£000s)",
        "Total Electricity (MWh)",
        "NPV Costs (£000s)",
        "NPV Electricity (£000s)",
        "LCOE (£/ MWh)" ],
    "Value": [
        results_LCOE["sum_total_costs"],
        results_LCOE["sum_electricity"],
        results_LCOE["NPV_sum_total_costs"],
        results_LCOE["NPV_sum_electricity"],
        results_LCOE["LCOE"]  ]
     })

    results_table["Value"] = results_table["Value"].map(lambda x: f"{x:,.1f}")
    
    return results_LCOE, results_table, sensitivity_df




