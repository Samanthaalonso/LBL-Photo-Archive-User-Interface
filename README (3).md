# LBNL Photo Archive Reviewer

Streamlit app to browse, review, and correct CLIP predictions on archival images.
Reads xlsx files and images directly from Google Drive — no uploads needed.

## Setup

```bash
pip install -r requirements.txt
```

## Configure credentials

1. Open `.streamlit/secrets.toml`
2. Copy all fields from your `lbl-photo-archive-2b5b9282cca1.json` into the `[gcp_service_account]` section
3. Share your Drive folders with the service account email

## Share Drive folders with service account

In Google Drive, share these folders with your service account email
(found in the JSON as `client_email`), with **Viewer** access:

- `Box 1-5 results` folder (xlsx files)
- `LBNLPhotosCooler/224x224/Box_001` through `Box_005`

## Run locally

```bash
streamlit run app.py
# → http://localhost:8501
```

## Deploy to Streamlit Community Cloud (free, shareable URL)

1. Push this folder to a GitHub repo (do NOT commit secrets.toml)
2. Go to share.streamlit.io → New app → connect your repo
3. In app settings → Secrets → paste the contents of secrets.toml
4. Deploy → get a public URL to share with stakeholders

## Adding predictions

If you have a `predictions.json` from your Lawrencium inference run,
the app will automatically show confidence scores, class score bars,
and enable correction workflow. Without predictions, it shows
metadata-only browse mode (caption + image).

To add predictions, load your JSON and merge with the xlsx data:

```python
import pandas as pd, json
with open("predictions.json") as f:
    preds = json.load(f)
df_preds = pd.DataFrame(preds)
# then join on file_name
```
