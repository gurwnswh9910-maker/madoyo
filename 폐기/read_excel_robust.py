import zipfile
import xml.etree.ElementTree as ET
import sys
import os
import datetime

def parse_excel_date(serial):
    try:
        # Excel base date is usually Dec 30 1899
        seconds = (float(serial) - 25569) * 86400
        return datetime.datetime.utcfromtimestamp(seconds)
    except:
        return None

def main():
    path = r'C:\Users\ding9\Desktop\madoyo\threads_live_report_0214_2101.xlsx'
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return

    try:
        with zipfile.ZipFile(path, 'r') as z:
            # 1. Shared Strings
            shared_strings = []
            if 'xl/sharedStrings.xml' in z.namelist():
                with z.open('xl/sharedStrings.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    # Namespace needed? usually standard
                    ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                    for si in root.findall('ns:si', ns):
                        t = si.find('ns:t', ns)
                        if t is not None:
                            shared_strings.append(t.text or "")
                        else:
                            # Rich text
                            texts = [node.text for node in si.findall('.//ns:t', ns) if node.text]
                            shared_strings.append("".join(texts))

            # 2. Sheet 1 Data
            if 'xl/worksheets/sheet1.xml' not in z.namelist():
                print("Sheet1 not found")
                return

            rows_data = []
            with z.open('xl/worksheets/sheet1.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                sheetData = root.find('ns:sheetData', ns)
                
                for row in sheetData.findall('ns:row', ns):
                    r_idx = row.get('r') # Row index
                    cells = []
                    for c in row.findall('ns:c', ns):
                        # Coordinate (e.g., A1)
                        # Type
                        t = c.get('t')
                        v = c.find('ns:v', ns)
                        val = v.text if v is not None else ""
                        
                        if t == 's':
                            try:
                                val = shared_strings[int(val)]
                            except:
                                val = f"Error:StringRef({val})"
                        cells.append(val)
                    rows_data.append(cells)

        # 3. Process Data
        # We need headers to find columns. Assuming Row 1 is headers.
        if not rows_data:
            print("No data found")
            return
            
        headers = rows_data[0]
        # Map columns
        col_map = {}
        for i, h in enumerate(headers):
            h = str(h)
            if '게시물주소' in h: col_map['link'] = i
            if '본문조회수' in h: col_map['views'] = i
            if '첫댓글조회수' in h: col_map['conv_views'] = i
            if '작성시간' in h: col_map['date'] = i

        # Filter for today (2/14)
        # 2026-02-14. Excel serial ~46067
        # We will just look for rows that likely match
        
        results = []
        for row in rows_data[1:]:
            # Get data carefully
            def get_col(name):
                idx = col_map.get(name)
                if idx is not None and idx < len(row):
                    return row[idx]
                return ""
            
            date_val = get_col('date')
            # Check if date matches 2026-02-14
            # If string: contain '2026-02-14'
            # If number: > 46067
            is_target = False
            if '2026-02-14' in str(date_val): 
                is_target = True
            try:
                if float(date_val) > 46060: # Rough check for recent dates
                    is_target = True
            except:
                pass
            
            # Fallback: if we can't determine, just include it if it has a link (likely a post)
            if not is_target and get_col('link').startswith('http'):
                 # Heuristic: verify if it looks like the user's recent posts
                 # Just include it for now to be safe
                 is_target = True 

            if is_target:
                link = get_col('link')
                if not link: continue
                views = get_col('views')
                conv_views = get_col('conv_views')
                results.append((link, views, conv_views))

        # 4. Output Format
        print(f"2월 14일")
        print(f"총업로드 {len(results)}")
        print("")
        
        for link, views, conv_views in results:
            print(f"{link}")
            print(f"조회수 : {views}, 댓글조회수 : {conv_views}")
            print("")
            
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
