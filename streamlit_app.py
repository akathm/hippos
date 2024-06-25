import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import requests
from io import StringIO

st.set_page_config(page_title='KYC Lookup Tool', page_icon='🗝️')
st.title('🗝️ KYC Lookup Tool')

access_token = st.secrets["github"]["access_token"]
owner = "akathm"
repo = "the-trojans"
path = "grants.contributors.csv"
url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
headers = {
    "Authorization": f"token {access_token}",
    "Accept": "application/vnd.github.v3.raw"
}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    csv_content = response.content.decode('utf-8')
    df = pd.read_csv(StringIO(csv_content))
    st.write(df)
else:
    st.error(f"Failed to fetch the file: {response.status_code}")


def fetch_data(api_key, base_url):
    results = []
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"page[size]": 100}
    next_page_after = None

    while True:
        response = requests.get(base_url, headers=headers, params=params)
        response_data = response.json()
        results.extend(response_data.get('data', []))
        next_link = response_data.get('links', {}).get('next')
        if next_link:
            next_cursor = next_link.split('page%5Bafter%5D=')[-1].split('&')[0]
            params['page[after]'] = next_cursor
        else:
            break

    return results

def process_inquiries(results):
    records = {}
    for item in results:
        inquiry_id = item['id']
        attributes = item.get('attributes', {})
        name_first = attributes.get('name-first', '') or ''
        name_middle = attributes.get('name-middle', '') or ''
        name_last = attributes.get('name-last', '') or ''
        name = f"{name_first} {name_middle} {name_last}".strip()
        email_address = attributes.get('email-address', '') or ''
        updated_at = attributes.get('updated-at')
        status = attributes.get('status')
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

    return pd.DataFrame.from_dict(records.values())

def process_cases(results):
    records = {}
    for item in results:
        case_id = item['id']
        attributes = item.get('attributes', {})
        status = attributes.get('status')
        fields = attributes.get('fields', {})
        business_name = fields.get('business-name', {}).get('value', '')
        updated_at = attributes.get('updated-at')
        
        if case_id not in records:
            records[case_id] = {
                'case_id': case_id,
                'business_name': business_name,
                'email_address': '',  # Placeholder, as email address data is not provided in the JSON response
                'l2_address': '',  # Placeholder, as l2_address data is not provided in the JSON response
                'updated_at': updated_at,
                'status': status
            }
            
    return pd.DataFrame.from_dict(records.values())

def main():
    st.title('KYC Individuals Table')
    api_key = st.secrets["persona"]["api_key"]
    refresh_button = st.button("Refresh")
    
    if refresh_button:
        inquiries_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/inquiries?refresh=true")
        cases_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/cases?refresh=true")
    else:
        inquiries_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/inquiries")
        cases_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/cases")
    
    if inquiries_data and cases_data:
        inquiries_df = process_inquiries(inquiries_data)
        cases_df = process_cases(cases_data)
        
        merged_df = pd.concat([inquiries_df, cases_df], ignore_index=True)
        st.dataframe(merged_df)
        
        st.sidebar.header("Lookup Tool")
        search_type = st.sidebar.selectbox("Search by", ["Name", "L2 Address", "Email", "Business Name"])
        search_input = st.sidebar.text_input("Enter your search value")
        
        if st.sidebar.button("Search"):
            if search_type == "Name":
                results = merged_df[merged_df['name'].str.contains(search_input, case=False, na=False)]
            elif search_type == "L2 Address":
                results = merged_df[merged_df['l2_address'].str.contains(search_input, case=False, na=False)]
            elif search_type == "Email":
                results = merged_df[merged_df['email_address'].str.contains(search_input, case=False, na=False)]
            elif search_type == "Business Name":
                results = merged_df[merged_df['business_name'].str.contains(search_input, case=False, na=False)]
            
            if not results.empty:
                for _, row in results.iterrows():
                    if row['status'] == 'approved':
                        if 'inquiry_id' in row:
                            st.write(f"Email: {row['email_address']}, L2 Address: {row['l2_address']}, Message: KYC Status is Cleared")
                        elif 'case_id' in row:
                            st.write(f"Email: {row['email_address']}, L2 Address: {row['l2_address']}, Message: KYB Status is Cleared")
                    else:
                        if 'inquiry_id' in row:
                            st.write(f"Message: KYC Status is Pending")
                        elif 'case_id' in row:
                            st.write(f"Message: KYB Status is Pending")
            else:
                st.write("No results found.")
    else:
        st.error("No data retrieved.")

if __name__ == '__main__':
    main()
