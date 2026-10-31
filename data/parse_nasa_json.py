import json, csv, os

p_json = 'data/nasa_real_api_downloads/nasa_ntrs_mirror_cryo_testing_records.json'
p_csv = 'data/nasa_real_api_downloads/nasa_ntrs_mirror_cryo_testing_records.csv'

with open(p_json, 'r', encoding='utf-8') as f:
    data = json.load(f)

results = data.get('results', [])
rows = []
for item in results:
    doc_id = str(item.get('id', ''))
    has_dl = len(item.get('downloads', [])) > 0
    rows.append({
        'NASA_Document_ID': doc_id,
        'Title': item.get('title', ''),
        'Publication_Date': item.get('publicationDate', ''),
        'Document_Type': item.get('documentType', ''),
        'Center': item.get('center', {}).get('name', ''),
        'Subject_Category': ', '.join([c if isinstance(c, str) else c.get('name', '') for c in item.get('subjectCategories', [])]),
        'Direct_NASA_PDF_Download': f"https://ntrs.nasa.gov/api/citations/{doc_id}/downloads/{doc_id}.pdf" if has_dl else 'N/A'
    })

with open(p_csv, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

print(f"Converted {len(rows)} real NASA API records to CSV: {p_csv} ({os.path.getsize(p_csv):,} bytes)")
