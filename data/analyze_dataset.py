import openpyxl, os, sys
sys.stdout.reconfigure(encoding='utf-8')

base_dir = r'c:\Users\JOEL\OneDrive\Desktop\Lightweighting Agent\data\mendeley_mirror_deformation'

print('=== DATASET ANALYSIS & PROFILE ===\n')
for root, dirs, files in os.walk(base_dir):
    for f in sorted(files):
        if f.endswith('.xlsx'):
            fp = os.path.join(root, f)
            sz_mb = os.path.getsize(fp) / (1024*1024)
            wb = openpyxl.load_workbook(fp, read_only=True)
            print(f'File: {f} ({sz_mb:.2f} MB)')
            for sname in wb.sheetnames[:4]:
                ws = wb[sname]
                rows = ws.max_row
                cols = ws.max_column
                try:
                    headers = [str(cell.value) for cell in next(ws.iter_rows(max_row=1))]
                except:
                    headers = []
                print(f'   -> Sheet "{sname}": {rows} rows x {cols} cols | Sample Headers: {headers[:5]}')
            print()
