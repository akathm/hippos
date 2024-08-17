import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import requests
from io import StringIO
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title='KYC Lookup Tool', page_icon='🗝️')
st.title('🗝️ KYC Lookup Tool')

st.subheader('Project Status')
with st.expander('About the Results'):
    st.markdown('**Every project must complete KYC (or KYB for businesses) in order to receive tokens.**')
    st.info('This tool can be used to lookup project status for a specific grant round or workflow. If you do not see the expected grants round here, or you see other unexpected results, please reach out to the Grant Program Manager to correct this issue.')
    st.markdown('**What should I do if a project I\'m talking to is not in *\"cleared\"* status?**')
    st.warning('🌕 *\"retry\"* means that the individual will need to re-attempt their KYC. They did not submit all documents, and should start over at kyc.optimism.io/  \n  \n 🔵 *\"incomplete\"* means we are waiting for 1+ business controllers to finish uploading their documents. Please direct them to check their emails.  \n  \n 🟠  *\"in review\"* means that this team or individual is waiting on a compliance review. Please let them know it may be up to 72 hours before a final decision is reached.    \n  \n 🛑 *\"rejected\"* teams will not be able to move forward with us. We cannot deliver tokens, and any signed agreements may be null and void. Reach out to compliance@optimism.io if you have any questions or suspect this decision may have been reached in error.')

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
        if 'data' in response_data:
            filtered_inquiries = [inquiry for inquiry in response_data['data'] if inquiry['attributes']['status'] not in ['created', 'open']]
            results.extend(filtered_inquiries)
        next_link = response_data.get('links', {}).get('next')
        if next_link:
            next_cursor = next_link.split('page%5Bafter%5D=')[-1].split('&')[0]
            params['page[after]'] = next_cursor
        else:
            break

    return results

def process_inquiries(results):
    records = []
    for item in results:
        inquiry_id = item['id']
        attributes = item.get('attributes', {})
        name_first = attributes.get('name-first', '') or ''
        name_middle = attributes.get('name-middle', '') or ''
        name_last = attributes.get('name-last', '') or ''
        name = f"{name_first} {name_middle} {name_last}".strip()
        email = attributes.get('email-address', '') or ''
        email = email.lower().strip()
        updated_at = attributes.get('updated-at')
        status = attributes.get('status')
        l2_address = attributes.get('fields', {}).get('l-2-address', {}).get('value', np.nan)

        if pd.notna(l2_address) and l2_address.lower().strip().startswith('0x'):
            l2_address = l2_address.lower().strip()
        else:
            l2_address = np.nan

        if '@' not in email:
            email = ''
        
        if status == 'approved':
            status = '🟢 cleared'
        if status in ['expired', 'pending', 'created']:
            status = '🌕 retry'
        if status == 'declined':
            status = '🛑 rejected'
        if status == 'needs_review':
            status = '🟠 in review'

        records.append({
            'inquiry_id': inquiry_id,
            'name': name,
            'email': email,
            'l2_address': l2_address,
            'updated_at': updated_at,
            'status': status
        })

    return pd.DataFrame(records)

def process_cases(results):
    records = []
    for item in results:
        case_id = item['id']
        inquiries = item.get('relationships', {}).get('inquiries', {}).get('data', [])
        inquiry_id = inquiries[0]['id'] if inquiries else np.nan
        attributes = item.get('attributes', {})
        status = attributes.get('status')
        fields = attributes.get('fields', {})
        business_name = fields.get('business-name', {}).get('value', '')
        email = fields.get('form-filler-email-address', {}).get('value', np.nan)
        email = str(email).lower().strip() if pd.notna(email) else ''
        updated_at = attributes.get('updated-at')
        l2_address = fields.get('l-2-address', {}).get('value', np.nan)

        if pd.notna(l2_address) and l2_address.lower().strip().startswith('0x'):
            l2_address = l2_address.lower().strip()
        else:
            l2_address = np.nan
        
        if status == 'approved':
            status = 'cleared'
            
        if status == 'approved':
            status = '🟢 cleared'
        if status in ['expired', 'pending', 'created', 'Waiting on UBOs']:
            status = '🔵 incomplete'
        if status == 'declined':
            status = '🛑 rejected'
        if status in ['Ready for Review']:
            status = '🟠 in review'
        
        if business_name:
            records.append({
                'case_id': case_id,
                'business_name': business_name,
                'email': email,
                'l2_address': l2_address,
                'updated_at': updated_at,
                'status': status
            })
            
    return pd.DataFrame(records)


def typeform_to_dataframe(response_data):
    form_entries = []

    for item in response_data.get('items', []):
        entry = {
            'form_id': item.get('response_id'),
            'project_id': item['hidden'].get('project_id', np.nan),
            'grant_id': item['hidden'].get('grant_id', np.nan),
            'l2_address': item['hidden'].get('l2_address', np.nan)
        }
        
        kyc_emails = []
        kyb_emails = []
        kyb_started = False
        l2_address_fallback = None
        
        for answer in item.get('answers', []):
            field_id = answer['field']['id']
            field_type = answer['field']['type']

            if field_id == 'ECV4jrkAuE1D' and field_type == 'short_text':
                l2_address_fallback = answer.get('text', np.nan)

            elif field_type == 'email':
                if kyb_started:
                    kyb_emails.append(answer.get('email'))
                else:
                    kyc_emails.append(answer.get('email'))

            elif field_id == 'hhURZ3ovgZ9V' and field_type == 'number' and answer.get('number', 0) > 0:
                kyb_started = True

        for i in range(10):
            entry[f'kyc_email{i}'] = kyc_emails[i] if i < len(kyc_emails) else np.nan
        
        for i in range(5):
            entry[f'kyb_email{i}'] = kyb_emails[i] if i < len(kyb_emails) else np.nan

        if pd.isna(entry['l2_address']) and l2_address_fallback:
            entry['l2_address'] = l2_address_fallback

        form_entries.append(entry)

    df = pd.DataFrame(form_entries)
    return df

# Example usage with the provided data
response_data = {
    "items": [
        {
            "landing_id": "ejumz2xqu1ukog354o4ejumzlwpgxxqu",
            "token": "ejumz2xqu1ukog354o4ejumzlwpgxxqu",
            "response_id": "ejumz2xqu1ukog354o4ejumzlwpgxxqu",
            "response_type": "completed",
            "landed_at": "2024-08-17T04:36:37Z",
            "submitted_at": "2024-08-17T04:42:47Z",
            "metadata": {
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "platform": "other",
                "referer": "https://superchain.typeform.com/to/KoPTjofd?typeform-source=kyc.optimism.io",
                "network_id": "fd6c80bdd7",
                "browser": "default"
            },
            "hidden": {
                "grant_id": "",
                "l2_address": "",
                "project_id": ""
            },
            "calculated": {
                "score": 0
            },
            "answers": [
                {
                    "field": {
                        "id": "h6tGJD5KheC7",
                        "type": "multiple_choice",
                        "ref": "01HE9NFKP0ZVJAV80N5ZYG1SW8"
                    },
                    "type": "choice",
                    "choice": {
                        "id": "5Oj5WDPYWur7",
                        "ref": "2beca08f-dc3b-49ec-9017-47e672f01eca",
                        "label": "I understand"
                    }
                },
                {
                    "field": {
                        "id": "bYoUc6UdwZR6",
                        "type": "multiple_choice",
                        "ref": "74507394-11ca-478d-919c-0c1f32cc9def"
                    },
                    "type": "choice",
                    "choice": {
                        "id": "7BBPk6B21QvJ",
                        "ref": "73a6ac75-1713-4c5c-9979-0662145b3773",
                        "label": "I understand, and I consent to this policy."
                    }
                },
                {
                    "field": {
                        "id": "tDuxkbqxD1QC",
                        "type": "dropdown",
                        "ref": "31d38431-5f52-4918-a814-4f5652f577ee"
                    },
                    "type": "text",
                    "text": "Mission Request (RFP)"
                },
                {
                    "field": {
                        "id": "ECV4jrkAuE1D",
                        "type": "short_text",
                        "ref": "a5ea065b-9e62-41f5-9460-43e438aa4cb4"
                    },
                    "type": "text",
                    "text": "0x4732A5a6174Ee1C808F35c252f05e9887Cf70B"
                },
                {
                    "field": {
                        "id": "TMcViWGwqtFH",
                        "type": "multiple_choice",
                        "ref": "4af410f1-a7b3-4b95-a16a-436fe75f2548"
                    },
                    "type": "choice",
                    "choice": {
                        "id": "FuJmtXc5hnK3",
                        "ref": "635c1430-e5d0-472f-b3d9-87f21263789f",
                        "label": "Yes, I am one of 2+ signers for this wallet."
                    }
                },
                {
                    "field": {
                        "id": "4n1QG7StRZ2i",
                        "type": "short_text",
                        "ref": "c6a71b6d-90aa-459e-b611-5bd50165bc64"
                    },
                    "type": "text",
                    "text": "Jozef"
                },
                {
                    "field": {
                        "id": "8S1bTgmfbhJh",
                        "type": "short_text",
                        "ref": "6f37560b-6459-467c-a07e-f75b12697d94"
                    },
                    "type": "text",
                    "text": "Vogel"
                },
                {
                    "field": {
                        "id": "dwwMSpm5L2E1",
                        "type": "email",
                        "ref": "cfc77049-e804-4157-8e79-05060135cc19"
                    },
                    "type": "email",
                    "email": "jozef@ether.fi"
                },
                {
                    "field": {
                        "id": "qzyk8htiXYsz",
                        "type": "short_text",
                        "ref": "46afb743-da37-4bb3-926c-b160289c7b83"
                    },
                    "type": "text",
                    "text": "Ether.Fi SEZC"
                },
                {
                    "field": {
                        "id": "hhURZ3ovgZ9V",
                        "type": "number",
                        "ref": "e0cf35fc-5711-4f34-83ec-489d2b81af79"
                    },
                    "type": "number",
                    "number": 2
                },
                {
                    "field": {
                        "id": "f0b6nFjKbocW",
                        "type": "short_text",
                        "ref": "acb00032-e92b-4cc4-84ea-f0cf89169d6f"
                    },
                    "type": "text",
                    "text": "Jozef"
                },
                {
                    "field": {
                        "id": "BClUdIP3ROJh",
                        "type": "short_text",
                        "ref": "0d61f84c-7d27-406d-a690-ffad3bf34db4"
                    },
                    "type": "text",
                    "text": "Vogel"
                },
                {
                    "field": {
                        "id": "HlepCgtwq06f",
                        "type": "email",
                        "ref": "513d9170-d694-456b-a059-40f975c32c4c"
                    },
                    "type": "email",
                    "email": "jozef@ether.fi"
                },
                {
                    "field": {
                        "id": "66z0y0Ykl9qJ",
                        "type": "short_text",
                        "ref": "07a8b945-ee7b-4230-92df-0ab28e88cecf"
                    },
                    "type": "text",
                    "text": "Ether.Fi SEZC"
                },
                {
                    "field": {
                        "id": "v8dfrNJiIQaZ",
                        "type": "number",
                        "ref": "42f5e257-80b7-4b2a-b7b9-624c612d77bf"
                    },
                    "type": "number",
                    "number": 1
                },
                {
                    "field": {
                        "id": "dvSDGhFyLipR",
                        "type": "short_text",
                        "ref": "b5d3ebce-b530-4cd8-939f-c994a166dbce"
                    },
                    "type": "text",
                    "text": "Jozef"
                },
                {
                    "field": {
                        "id": "UWIf8mwKMeeF",
                        "type": "short_text",
                        "ref": "118bfad5-ffed-4649-b239-f518ff6a7da0"
                    },
                    "type": "text",
                    "text": "Vogel"
                },
                {
                    "field": {
                        "id": "VBSpY6rpRHvq",
                        "type": "email",
                        "ref": "ee81d4d3-cc9b-42bd-815c-690c2e618f5f"
                    },
                    "type": "email",
                    "email": "jozef@ether.fi"
                },
                {
                    "field": {
                        "id": "BT77VTGscSDW",
                        "type": "multiple_choice",
                        "ref": "58cb0f5c-d8cd-4375-878d-a3576f108346"
                    },
                    "type": "choices",
                    "choices": {
                        "ids": [
                            "PY5t6aBJ48jN"
                        ],
                        "refs": [
                            "f1ecb29b-8bfc-40b7-baa3-a18c6e5cdc1c"
                        ],
                        "labels": [
                            "I confirm"
                        ]
                    }
                },
                {
                    "field": {
                        "id": "P0adzSGCC2LC",
                        "type": "multiple_choice",
                        "ref": "41cdabcb-499f-463d-951a-01c2ec823669"
                    },
                    "type": "choices",
                    "choices": {
                        "ids": [
                            "Jy85yLl9usf5"
                        ],
                        "refs": [
                            "77802905-32c4-4bd6-9708-9ec6a723ec9e"
                        ],
                        "labels": [
                            "I confirm"
                        ]
                    }
                },
                {
                    "field": {
                        "id": "ZiRprkGJl4J1",
                        "type": "multiple_choice",
                        "ref": "4b8cc5a7-1253-4ef3-98b1-a7fb04bbd757"
                    },
                    "type": "choices",
                    "choices": {
                        "ids": [
                            "VM9Xs2IVeAY7"
                        ],
                        "refs": [
                            "8e3b5f32-c1ff-443d-bd5e-0123bc1ae65b"
                        ],
                        "labels": [
                            "I confirm"
                        ]
                    }
                },
                {
                    "field": {
                        "id": "pMiIUKwCJBlp",
                        "type": "multiple_choice",
                        "ref": "916c13db-a154-4513-b447-30454b14a63c"
                    },
                    "type": "choices",
                    "choices": {
                        "ids": [
                            "AhvnyYWIxb1e"
                        ],
                        "refs": [
                            "5fd59b68-9f43-44c2-9d5b-0ef0fd4b7454"
                        ],
                        "labels": [
                            "I confirm"
                        ]
                    }
                },
                {
                    "field": {
                        "id": "QigyrEHgFiN1",
                        "type": "multiple_choice",
                        "ref": "8da580f8-b5d5-4454-a407-411bf80dfac5"
                    },
                    "type": "choices",
                    "choices": {
                        "ids": [
                            "9MbF8puaNNcv"
                        ],
                        "refs": [
                            "816935f8-94cd-4135-880d-f17bd29f5842"
                        ],
                        "labels": [
                            "I confirm"
                        ]
                    }
                },
                {
                    "field": {
                        "id": "uKFm8EqsnGJU",
                        "type": "multiple_choice",
                        "ref": "b9f85c41-3869-44af-8d1a-64acdc3c948f"
                    },
                    "type": "choices",
                    "choices": {
                        "ids": [
                            "R76QQT31HWQW"
                        ],
                        "refs": [
                            "31484be4-e238-4007-94ba-eb6b9cb063c8"
                        ],
                        "labels": [
                            "I confirm"
                        ]
                    }
                },
                {
                    "field": {
                        "id": "1E9Qrr1PGio6",
                        "type": "multiple_choice",
                        "ref": "2d1d7858-20f9-4c9b-8a07-2af74691aec9"
                    },
                    "type": "choice",
                    "choice": {
                        "id": "uSAhplAFVJwx",
                        "ref": "0f8065b8-eb39-4464-a2cc-ce4245298ed9",
                        "label": "Take me to KYB"
                    }
                }
            ]
        }
    ]
}

example_df = typeform_to_dataframe(response_data)
st.write('example')
st.write(example_df)


## LEGACY DATA -------------------------------------------------------------------

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


def main():
    st.title('KYC Database')

    api_key = st.secrets["persona"]["api_key"]
    access_token = st.secrets["github"]["access_token"]
    owner = "akathm"
    repo = "the-trojans"

    if 'inquiries_data' not in st.session_state:
        st.session_state.inquiries_data = None
    if 'cases_data' not in st.session_state:
        st.session_state.cases_data = None

    refresh_button = st.button("Refresh")

    if refresh_button:
        inquiries_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/inquiries?refresh=true")
        cases_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/cases?refresh=true")
        st.session_state.inquiries_data = inquiries_data
        st.session_state.cases_data = cases_data
    else:
        if st.session_state.inquiries_data is None:
            inquiries_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/inquiries")
            st.session_state.inquiries_data = inquiries_data
        else:
            inquiries_data = st.session_state.inquiries_data

        if st.session_state.cases_data is None:
            cases_data = fetch_data(api_key, "https://app.withpersona.com/api/v1/cases")
            st.session_state.cases_data = cases_data
        else:
            cases_data = st.session_state.cases_data

    option = st.sidebar.selectbox('Select an Option', ['Contribution Path', 'Superchain', 'Vendor', 'Grants Round'])
    search_term = st.sidebar.text_input('Enter search term (name, l2_address, or email)')

    inquiries_df = process_inquiries(inquiries_data)
    cases_df = process_cases(cases_data)

    contributors_path = "grants.contributors.csv"
    projects_path = "grants.projects.csv"
    persons_path = "legacy.persons.csv"
    businesses_path = "legacy.businesses.csv"
    form_path = "legacy.form.csv"

    contributors_df = fetch_csv(owner, repo, contributors_path, access_token)
    projects_df = fetch_csv(owner, repo, projects_path, access_token)
    persons_df = fetch_csv(owner, repo, persons_path, access_token)
    businesses_df = fetch_csv(owner, repo, businesses_path, access_token)
    form_df = fetch_csv(owner, repo, form_path, access_token)
    form_df['updated_at'] = pd.to_datetime(form_df['updated_at'])
    form_df['updated_at'] = form_df['updated_at'].dt.tz_localize('UTC')

    if persons_df is not None and 'updated_at' in persons_df.columns:
        try:
            persons_df['updated_at'] = pd.to_datetime(persons_df['updated_at'], utc=True)
        except Exception as e:
            st.error(f"Error converting 'updated_at' to datetime: {e}")
            st.stop()

    if businesses_df is not None and 'updated_at' in businesses_df.columns:
        try:
            businesses_df['updated_at'] = pd.to_datetime(businesses_df['updated_at'], utc=True)
        except Exception as e:
            st.error(f"Error converting 'updated_at' to datetime: {e}")
            st.stop()

    if inquiries_df is not None and 'updated_at' in inquiries_df.columns:
        inquiries_df['updated_at'] = pd.to_datetime(inquiries_df['updated_at'], utc=True)

    if cases_df is not None and 'updated_at' in cases_df.columns:
        cases_df['updated_at'] = pd.to_datetime(cases_df['updated_at'], utc=True)

    if persons_df is not None and inquiries_df is not None:
        current_date_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
        one_year_ago_utc = current_date_utc - timedelta(days=365)

    if businesses_df is not None and cases_df is not None:
        current_date_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
        one_year_ago_utc = current_date_utc - timedelta(days=365)

    if form_df is not None: ## and typeform_df is not None:
        current_date_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
        one_year_ago_utc = current_date_utc - timedelta(days=365)

    def display_results(df, columns, message, status_column='status', date_column='updated_at'):
        if df.empty:
            st.write("No matching results found.")
            return
        st.write(df[columns])

        if date_column in df.columns and not df[date_column].isnull().all():
            most_recent_status = df.loc[df[date_column].idxmax(), status_column]
            st.write(f"### {message.format(status=most_recent_status)}")
        else:
            empty_row = {col: '' for col in columns}
            empty_row[date_column] = ''
            empty_row[status_column] = 'not started'
            df = pd.DataFrame([empty_row])
            st.write(f"### {message.format(status='not clear')}")

    def search_and_display(df, search_term, columns_to_display, message, status_column='status', date_column='updated_at'):
        df['updated_at'] = pd.to_datetime(df['updated_at'], errors='coerce')
        df['status'] = df['status'].fillna('not started')
        name_search = df.get('name', pd.Series([''] * len(df))).str.contains(search_term, case=False, na=False)
        business_name_search = df.get('business_name', pd.Series([''] * len(df))).str.contains(search_term, case=False, na=False)
        email_search = df['email'].str.contains(search_term, case=False, na=False)
        l2_address_search = df['l2_address'].str.contains(search_term, case=False, na=False)
        filtered_df = df[name_search | business_name_search | email_search | l2_address_search]

        display_results(filtered_df, columns_to_display, message, status_column)
        

    all_persons_df = pd.concat([persons_df, inquiries_df], ignore_index=True)
    all_persons_df['status'] = all_persons_df.sort_values('updated_at').groupby('email')['status'].transform('last')
    all_persons_df['l2_address'] = all_persons_df.sort_values('updated_at').groupby('email')['l2_address'].transform('last')
    all_persons_df['updated_at'] = all_persons_df.sort_values('updated_at').groupby('email')['updated_at'].transform('last')
    all_persons_df['name'] = all_persons_df.sort_values('updated_at').groupby('email')['name'].transform('last')
    all_persons_df.loc[(all_persons_df['status'] == 'cleared') & (all_persons_df['updated_at'] < one_year_ago_utc), 'status'] = 'expired'
    all_contributors = contributors_df.merge(all_persons_df[['email', 'name', 'status', 'l2_address', 'updated_at']], on='email', how='outer')
    all_contributors['status'] = all_contributors['status'].fillna('not started')
    all_contributors['l2_address'] = all_contributors['l2_address_x'].combine_first(all_contributors['l2_address_y'])
    all_contributors['l2_address'] = all_contributors.apply(lambda row: row['l2_address_x'] if pd.notna(row['l2_address_x']) else row['l2_address_y'], axis=1)
    all_contributors = all_contributors.drop(columns=['l2_address_x', 'l2_address_y'])
    all_contributors = all_contributors[~(all_contributors['email'].isnull() & all_contributors['avatar'].isnull())]
    all_contributors.drop_duplicates(subset=['email', 'round_id', 'op_amt'], inplace=True)

    all_businesses = pd.concat([businesses_df, cases_df], ignore_index=True)
    all_businesses = all_businesses.sort_values('updated_at')
    all_businesses['status'] = all_businesses.groupby(['email', 'business_name'])['status'].transform('last')
    all_businesses['l2_address'] = all_businesses.groupby(['email', 'business_name'])['l2_address'].transform('last')
    all_businesses['updated_at'] = all_businesses.groupby(['email', 'business_name'])['updated_at'].transform('last')
    all_businesses.loc[(all_businesses['status'] == 'cleared') & (all_businesses['updated_at'] < one_year_ago_utc), 'status'] = 'expired'
    all_businesses = all_businesses[~(all_businesses['email'].isnull())]
    all_businesses.drop_duplicates(subset=['email', 'business_name'], inplace=True)
    
    if option in ['Superchain', 'Vendor']:
        search_and_display(all_businesses, search_term, ['business_name', 'email', 'l2_address', 'updated_at', 'status'], 
                       "This team is {status} for KYB.")
    elif option == 'Contribution Path':
        if 'avatar' not in all_contributors.columns:
            all_contributors['avatar'] = ''
        if search_term:
            search_and_display(all_contributors, search_term, ['avatar', 'email', 'l2_address', 'updated_at', 'status'], 
                       "This contributor is {status} for KYC.")
    elif option == 'Grants Round':
        form_df['grant_id'] = form_df['grant_id'].astype(str)
        projects_df['grant_id'] = projects_df['grant_id'].astype(str)
        
        ##merged_email = pd.merge(form_df, projects_df, on='email', how='outer', indicator=True, suffixes=('_form', '_proj'))
        ##merged_l2 = pd.merge(form_df, projects_df, on='l2_address', how='outer', indicator=True, suffixes=('_form', '_proj'))
        ##merged_all = pd.concat([merged_email, merged_l2], ignore_index=True).drop_duplicates()
        merged_email = pd.merge(form_df, projects_df, on='email', how='outer', suffixes=('_form', '_proj'))
        merged_l2 = pd.merge(form_df, projects_df, on='l2_address', how='outer', suffixes=('_form', '_proj'))
        merged_all = pd.concat([merged_email, merged_l2], ignore_index=True).drop_duplicates()

        merged_all['l2_address'] = merged_all['l2_address_form'].combine_first(merged_all['l2_address_proj'])
        merged_all.drop(columns=['l2_address_form', 'l2_address_proj'], inplace=True)
        ##merged_all['status'] = pd.to_numeric(merged_all['status'], errors='coerce')
        ##merged_all['status'] = merged_all['status_form'].combine_first(merged_all['status_proj'])
    
        required_columns = ['project_name', 'email', 'l2_address', 'round_id', 'grant_id', 'status']
        for col in required_columns:
            if col not in merged_all.columns:
                merged_all[col] = ''

        merged_all = merged_all[~(merged_all['email'].isnull() & merged_all['l2_address'].isnull())]
    
        if search_term:
            filtered_df = merged_all[
                merged_df['name'].str.contains(search_term, case=False, na=False) |
                merged_df['email'].str.contains(search_term, case=False, na=False) |
                merged_df['l2_address'].str.contains(search_term, case=False, na=False)
            ]
    
        else:
            filtered_df = pd.DataFrame()
            st.write('*Use the search tool on the left hand side to input an L2 address, project name, or admin email* 💬')
            

        display_results(filtered_df, ['project_name', 'email', 'l2_address', 'round_id', 'grant_id', 'status'], 
                "This project is {status} for KYC.")

## TESTING--------------------------------------------------
    
## Contributors-------------------------------------------------------

    st.header('______________________________')
    st.header('Individual Contributors')

    all_persons_df = pd.concat([persons_df, inquiries_df], ignore_index=True)
    all_persons_df['status'] = all_persons_df.sort_values('updated_at').groupby('email')['status'].transform('last')
    all_persons_df['l2_address'] = all_persons_df.sort_values('updated_at').groupby('email')['l2_address'].transform('last')
    all_persons_df.loc[(all_persons_df['status'] == 'cleared') & (all_persons_df['updated_at'] < one_year_ago_utc), 'status'] = 'expired'

    merged_df = contributors_df.merge(all_persons_df[['email', 'status', 'l2_address']], on='email', how='left')
    merged_df['status'] = merged_df['status'].fillna('not started')
    merged_df['l2_address'] = merged_df['l2_address_x'].combine_first(merged_df['l2_address_y'])
    merged_df['l2_address'] = merged_df.apply(lambda row: row['l2_address_x'] if pd.notna(row['l2_address_x']) else row['l2_address_y'], axis=1)
    merged_df = merged_df.drop(columns=['l2_address_x', 'l2_address_y'])
    merged_df = merged_df[~(merged_df['email'].isnull() & merged_df['avatar'].isnull())]
    merged_df.drop_duplicates(subset=['email', 'round_id', 'op_amt'], inplace=True)

    projects_list = ['Ambassadors', 'NumbaNERDs', 'SupportNERDs', 'Translators', 'Badgeholders', 'WLTA', 'WLTA Judge']
    projects_selection = st.multiselect('Select the Contributor Path', projects_list + ['Other'], projects_list + ['Other'])

    if 'Other' in projects_selection:
        filtered_df = merged_df[~merged_df['project_name'].isin(projects_list)]
        if set(projects_selection) - {'Other'}:
            filtered_df = pd.concat([filtered_df, merged_df[merged_df['project_name'].isin(set(projects_selection) - {'Other'})]])
    else:
        filtered_df = merged_df[merged_df['project_name'].isin(projects_selection)] if projects_selection else merged_df

    st.write(filtered_df)
        
## Grants Rounds--------------------------------------------
        
    st.header('Active Grants Rounds')
    
    url = "https://api.github.com/repos/akathm/the-trojans/contents/grants.projects.csv"

    headers = {
        "Authorization": f"token {st.secrets['github']['access_token']}",
        "Accept": "application/vnd.github.v3.raw"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        csv_content = response.content.decode('utf-8')
        df = pd.read_csv(StringIO(csv_content))
        rounds_list = df.round_id.unique()
        rounds_selection = st.multiselect('Select the Grant Round', list(rounds_list), ['rpgf2', 'rpgf3', 'season5-builders-19', 'season5-growth-19'])
        
        if 'Other' in rounds_selection:
            filtered_df = df[~df['round_id'].isin(['rpgf2', 'rpgf3', 'season5-builders-19', 'season5-growth-19'])]
            if set(rounds_selection) - {'Other'}:
                filtered_df = pd.concat([filtered_df, df[df['round_id'].isin(set(rounds_selection) - {'Other'})]])
        else:
            filtered_df = df[df['round_id'].isin(rounds_selection)] if rounds_selection else df
            
        st.write(filtered_df)
    else:
        st.error(f"Failed to fetch the file: {response.status_code}")



if __name__ == '__main__':
    main()
