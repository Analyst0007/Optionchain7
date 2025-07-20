import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# Function to round to nearest strike price
def round_nearest_strike(x, num):
    return int(np.ceil(float(x) / num) * num)

# Function to calculate weighted average price
def calculate_weighted_avg_price(df, atm_strike, price_col, strike_interval):
    # Calculate weights: Inverse distance from ATM strike
    df['distance'] = abs(df['strikePrice'] - atm_strike)
    df['weight'] = 1 / (1 + df['distance'] / strike_interval)  # Weight formula
    # Calculate weighted price
    df['weighted_price'] = df[price_col] * df['weight']
    weighted_avg_price = df['weighted_price'].sum() / df['weight'].sum()
    return weighted_avg_price

# Headers for NSE API request
headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36',
    'accept-language': 'en,gu;q=0.9,hi;q=0.8',
    'accept-encoding': 'gzip, deflate, br'
}

# Initialize session
session = requests.Session()

# Function to set cookies
def set_cookie():
    url_oc = "https://www.nseindia.com/option-chain"
    response = session.get(url_oc, headers=headers, timeout=5)
    return dict(response.cookies)

# Function to fetch option chain data
def get_option_chain(symbol, expiry_date):
    url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
    cookies = set_cookie()
    response = session.get(url, headers=headers, cookies=cookies, timeout=5)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to fetch data: {response.status_code}")

# Main function to process option chain
def process_option_chain(symbol="NIFTY", expiry_date=None, underlying_price=None, strike_interval=50):
    # Fetch option chain data
    data = get_option_chain(symbol, expiry_date)
    
    # Use provided underlying price or fetch from data
    if underlying_price is None:
        underlying_price = data['records']['underlyingValue']
    
    # Get all expiry dates and select the nearest one if not provided
    expiry_dates = data['records']['expiryDates']
    if not expiry_date:
        expiry_date = expiry_dates[0]  # Select nearest expiry
    
    # Filter data for the selected expiry
    filtered_data = [d for d in data['records']['data'] if d['expiryDate'] == expiry_date]
    
    # Create DataFrame
    df = pd.DataFrame(filtered_data)
    
    # Initialize lists for CE and PE data
    ce_data = []
    pe_data = []
    
    for index, row in df.iterrows():
        strike = row['strikePrice']
        if 'CE' in row:
            ce_data.append({
                'strikePrice': strike,
                'lastPrice': row['CE']['lastPrice'],
                'openInterest': row['CE']['openInterest'],
                'changeinOpenInterest': row['CE']['changeinOpenInterest'],
                'impliedVolatility': row['CE']['impliedVolatility']
            })
        if 'PE' in row:
            pe_data.append({
                'strikePrice': strike,
                'lastPrice': row['PE']['lastPrice'],
                'openInterest': row['PE']['openInterest'],
                'changeinOpenInterest': row['PE']['changeinOpenInterest'],
                'impliedVolatility': row['PE']['impliedVolatility']
            })
    
    ce_df = pd.DataFrame(ce_data)
    pe_df = pd.DataFrame(pe_data)
    
    # Find ATM strike
    atm_strike = round_nearest_strike(underlying_price, strike_interval)
    
    # Filter for 10 strikes above and below ATM
    strike_range = 10 * strike_interval
    ce_filtered = ce_df[(ce_df['strikePrice'] >= atm_strike - strike_range) & 
                       (ce_df['strikePrice'] <= atm_strike + strike_range)]
    pe_filtered = pe_df[(ce_df['strikePrice'] >= atm_strike - strike_range) & 
                       (ce_df['strikePrice'] <= atm_strike + strike_range)]
    
    # Sort by strike price
    ce_filtered = ce_filtered.sort_values('strikePrice')
    pe_filtered = pe_filtered.sort_values('strikePrice')
    
    # Calculate weighted average prices
    ce_weighted_avg = calculate_weighted_avg_price(ce_filtered, atm_strike, 'lastPrice', strike_interval)
    pe_weighted_avg = calculate_weighted_avg_price(pe_filtered, atm_strike, 'lastPrice', strike_interval)
    
    # Merge CE and PE data
    option_chain = ce_filtered.merge(pe_filtered, on='strikePrice', suffixes=('_CE', '_PE'), how='outer')
    
    return option_chain, atm_strike, underlying_price, ce_weighted_avg, pe_weighted_avg

# Streamlit app
st.title("NIFTY Option Chain Analyzer")

# User inputs
st.sidebar.header("Input Parameters")
symbol = st.sidebar.text_input("Ticker Symbol (e.g., NIFTY, BANKNIFTY)", value="NIFTY").strip().upper()
underlying_price = st.sidebar.number_input("Underlying Price (leave as 0 to fetch from NSE)", min_value=0.0, value=0.0, step=0.01)
strike_interval = st.sidebar.number_input("Strike Price Interval (e.g., 50 for NIFTY)", min_value=1.0, value=50.0, step=1.0)
fetch_data = st.sidebar.button("Fetch Option Chain")

# Initialize session state for results
if 'option_chain_df' not in st.session_state:
    st.session_state.option_chain_df = None
    st.session_state.atm_strike = None
    st.session_state.underlying_price = None
    st.session_state.ce_weighted_avg = None
    st.session_state.pe_weighted_avg = None

# Fetch and display data when button is clicked
if fetch_data:
    try:
        with st.spinner("Fetching option chain data..."):
            # Set underlying_price to None if 0 (to fetch from NSE)
            underlying_price = None if underlying_price == 0 else underlying_price
            option_chain_df, atm_strike, underlying_price, ce_weighted_avg, pe_weighted_avg = process_option_chain(
                symbol=symbol, 
                underlying_price=underlying_price, 
                strike_interval=strike_interval
            )
            
            # Store results in session state
            st.session_state.option_chain_df = option_chain_df
            st.session_state.atm_strike = atm_strike
            st.session_state.underlying_price = underlying_price
            st.session_state.ce_weighted_avg = ce_weighted_avg
            st.session_state.pe_weighted_avg = pe_weighted_avg
            
            st.success(f"Data fetched successfully for {symbol}!")
            
    except Exception as e:
        st.error(f"Error: {str(e)}")

# Display results if available
if st.session_state.option_chain_df is not None:
    st.write(f"**Underlying Price ({symbol})**: {st.session_state.underlying_price:.2f}")
    st.write(f"**ATM Strike**: {st.session_state.atm_strike:.2f}")
    st.write(f"**Weighted Average Price (CE)**: {st.session_state.ce_weighted_avg:.2f}")
    st.write(f"**Weighted Average Price (PE)**: {st.session_state.pe_weighted_avg:.2f}")
    
    st.subheader(f"Option Chain Data for {symbol} (10 strikes above and below ATM)")
    display_df = st.session_state.option_chain_df[[
        'strikePrice', 
        'lastPrice_CE', 'openInterest_CE', 'impliedVolatility_CE',
        'lastPrice_PE', 'openInterest_PE', 'impliedVolatility_PE'
    ]]
    st.dataframe(display_df)
    
    # Download button for CSV
    csv = st.session_state.option_chain_df.to_csv(index=False)
    st.download_button(
        label=f"Download {symbol} Option Chain as CSV",
        data=csv,
        file_name=f"{symbol.lower()}_option_chain.csv",
        mime="text/csv"
    )
