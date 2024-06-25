import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import requests
from io import StringIO

st.set_page_config(page_title='KYC Lookup Tool', page_icon='🗝️')
st.title('🗝️ KYC Lookup Tool')

st.subheader ('Project Status')
with st.expander('About the Results'):
  st.markdown('**Every project must complete KYC (or KYB for businesses) in order to receive tokens.**')
  st.info('This tool can be used to lookup project status for a specific grant round or workflow. If you do not see the expected grants round here, or you see other unexpected results, please reach out to the Grant Program Manager to correct this issue.')
  st.markdown('**What should I do if a project I\'m talking to is not in *\"cleared\"* status?**')
  st.warning('If you see a project is in *\"pending\"* status, this means that we are waiting on action from that team. Please direct them to check their emails: one or more responsible parties have been emailed with a link to complete further steps in the KYC process.')


## PERSONA-------------------------------------------------------------------

@st.cache_data(ttl=600)
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
    st.title('KYC Database')
    api_key = st.secrets["persona"]["api_key"]

    if 'inquiries_data' not in st.session_state:
        st.session_state.inquiries_data = None
    if 'cases_data' not in st.session_state:
        st.session_state.cases_data = None

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
        search_input = st.sidebar.text_input("Enter the L2 address, email, or full legal name")

        if st.sidebar.button("Search") and search_input:
            results = merged_df[merged_df.apply(lambda row: any(search_input.lower() in str(row[col]).lower() for col in ['name', 'l2_address', 'email_address']), axis=1)]

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


if __name__ == '__main__':
    main()


## REPORT LOOKUP-----------------------------------------------------

st.subheader('Active Grants Rounds')

access_token = st.secrets["github"]["access_token"]
owner = "akathm"
repo = "the-trojans"
path = "grants.projects.csv"
url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
headers = {
    "Authorization": f"token {access_token}",
    "Accept": "application/vnd.github.v3.raw"
}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    csv_content = response.content.decode('utf-8')
    df = pd.read_csv(StringIO(csv_content))
    rounds_list = df.round_id.unique()
    rounds_selection = st.multiselect('Select the Grant Round', rounds_list, ['rpgf2', 'rpgf3', 'season5-builders-19', 'season5-growth-19']) ##['Marketing', 'Token House - S4', 'Token House - S5', 'WLTA', 'RPGF3', 'RPGF2'])
    st.write(df)
else:
    st.error(f"Failed to fetch the file: {response.status_code}")

st.subheader ('Individual Contributors')

def fetch_csv(owner, repo, path, access_token):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {access_token}",
        "Accept": "application/vnd.github.v3.raw"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        csv_content = response.content.decode('utf-8')
        df = pd.read_csv(StringIO(csv_content))
        return df
    else:
        st.error(f"Failed to fetch the file from {path}: {response.status_code}")
        return None

access_token = st.secrets["github"]["access_token"]
owner = "akathm"
repo = "the-trojans"
contributors_path = "grants.contributors.csv"
contributors_df = fetch_csv(owner, repo, contributors_path, access_token)
persons_path = "legacy.persons.csv"
persons_df = fetch_csv(owner, repo, persons_path, access_token)

if contributors_df is not None and persons_df is not None:
    persons_df['status'] = persons_df.sort_values('updated_at').groupby('email')['status'].transform('last')
  
    merged_df = contributors_df.merge(persons_df[['email', 'status']], on='email', how='left')
    merged_df['status'].fillna('not started', inplace=True)
    merged_df = merged_df[~(merged_df['email'].isnull() & merged_df['contributor_id'].isnull())]
    merged_df.drop_duplicates(subset=['email', 'round_id', 'op_amt'], inplace=True)

    projects_list = ['Ambassadors', 'NumbaNERDs', 'SupportNERDs', 'Translators', 'Badgeholders']
    projects_selection = st.multiselect('Select the Contributor Path', projects_list + ['Other'], ['Ambassadors', 'NumbaNERDs', 'SupportNERDs', 'Translators', 'Badgeholders', 'Other'])
##    projects_selection = st.multiselect('Select the Contributor Path', projects_list + ['Other'])    
  
    if 'Other' in projects_selection:
        filtered_df = merged_df[~merged_df['project_name'].isin(projects_list)]
        if set(projects_selection) - {'Other'}:
            filtered_df = pd.concat([filtered_df, merged_df[merged_df['project_name'].isin(set(projects_selection) - {'Other'})]])
    else:
        filtered_df = merged_df[merged_df['project_name'].isin(projects_selection)] if projects_selection else merged_df
   
    st.write(filtered_df)

