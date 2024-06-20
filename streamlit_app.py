import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import requests

st.set_page_config(page_title='KYC Lookup Tool', page_icon='🗝️')
st.title('🗝️ KYC Lookup Tool')

@st.cache
def fetch_data(api_key, endpoint_url):
    data = []
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"page[limit]": 100}

    try:
        while True:
            response = requests.get(endpoint_url, headers=headers, params=params)
            if response.status_code == 200:
                response_data = response.json()
                if 'data' in response_data:
                    for item in response_data['data']:
                        attributes = item.get('attributes', {})
                        status = attributes.get('status')
                        if status not in ['created', 'completed']:
                            data.append(item)
                if 'links' in response_data and 'next' in response_data['links']:
                    next_page_url = response_data['links']['next']
                    params = dict([param.split('=') for param in next_page_url.split('?')[1].split('&')])
                else:
                    break
            else:
                st.error(f"Error fetching data (Status Code: {response.status_code})")
                break
    except Exception as e:
        st.error(f"Error fetching data: {e}")

    return data

def process_data(data):
    records = []
    for item in data:
        inquiry_id = item.get('id', '')
        attributes = item.get('attributes', {})
        name_first = attributes.get('name-first', '') or ''
        name_middle = attributes.get('name-middle', '') or ''
        name_last = attributes.get('name-last', '') or ''
        name = f"{name_first} {name_middle} {name_last}".strip()
        email_address = attributes.get('email-address', '') or ''
        updated_at = attributes.get('updated-at', '')
        status = attributes.get('status', '')
        l2_address = attributes.get('fields', {}).get('l-2-address', {}).get('value', '')

        if inquiry_id not in records:
            records[inquiry_id] = {
                'inquiry_id': inquiry_id,
                'name': name,
                'email_address': email_address,
                'l2_address': l2_address,
                'updated_at': updated_at,
                'status': status
             }
    return pd.DataFrame(records)


def main():
    st.title('KYC Individuals Table')
    api_key = st.secrets["persona"]["api_key"]
    refresh_button = st.button("Refresh")
    
    if refresh_button:
        inquiries_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/inquiries?refresh=true")
        ## cases_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/cases?refresh=true")
    else:
        inquiries_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/inquiries")
        ## cases_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/cases")
    
    if inquiries_data: ## and cases_data:
        df = process_data(inquiries_data) ## + cases_data)
        st.dataframe(df)
    else:
        st.error("No data retrieved.")

if __name__ == '__main__':
    main()
