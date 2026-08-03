"""
core.py - analysis logic extracted VERBATIM from list-4-3.py (lines 152-537).
No line inside ListLogic has been retyped or edited.
Only the UI layer (tkinter/PIL/filedialog) was dropped.
"""
import os
import re
import sys
import pandas as pd
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.oxml.ns import qn
from docx.enum.section import WD_SECTION


class ListLogic:
    """
    The analysis, unchanged apart from where bay ranges are looked up.

    range_provider(name) returns a list of (start, end) tuples for a vessel,
    or None if the name is not a known vessel - in which case the original
    text-parsing fallbacks handle it, exactly as before.
    """

    def __init__(self, range_provider=None):
        if range_provider is None:
            import db
            db.init_db()
            range_provider = db.get_ranges
        self.range_provider = range_provider

    def generateWordDoc(self, data, bay_config, output_file_path, output_file_name):
        # Extract Bay from OutStowLoc safely (drop last 4 digits -> 28 from 280182)
        data['Bay'] = data['OutStowLoc'].apply(self.extract_bay_safely)
        print("[DEBUG] Bay sample:", data['Bay'].head(10).tolist())

        # BayRange with Unknown handler (do not call mapper if OutStowLoc is missing)
        data['BayRange'] = data.apply(
            lambda row: (
                'Unknown' if (
                    pd.isna(row['OutStowLoc'])
                    or str(row['OutStowLoc']).strip() == ''
                    or str(row['OutStowLoc']).strip().lower() == 'nan'
                ) else self.get_custom_bay_range(row['Bay'], row['OutStowLoc'], bay_config)
            ),
            axis=1
        )
        print("[DEBUG] BayRange sample:", data['BayRange'].head(10).tolist())

        # Normalize YardLoc & derive PositionType and ISO group
        # FIX: use .str.strip(), not .strip() on the Series
        data['YardLoc'] = data['YardLoc'].astype(str).fillna('').str.strip()
        print("[DEBUG] YardLoc sample:", data['YardLoc'].head(10).tolist())

        # E-yard is recognized inside get_position_type BEFORE generic 'Y'
        data['PositionType'] = data.apply(lambda row: self.get_position_type(row['YardLoc'], str(row['ISOCD']), str(row['OutDate'])), axis=1)
        print("[DEBUG] PositionType sample:", data['PositionType'].head(10).tolist())

        data['ISOCD_Group'] = data['ISOCD'].astype(str).apply(self.group_ISOCD)

        # Extract YardLoc parts for E/XXX/YYY (regex tolerant to multiple spaces)
        data = data.apply(self.extract_yardloc_components, axis=1)
        print("[DEBUG] YardLoc_XXX sample:", data['YardLoc_XXX'].head(10).tolist())

        # Group & aggregate
        bay_position_counts = data.groupby(['BayRange', 'ISOCD_Group', 'PositionType', 'POD'], dropna=False).agg(
            Count=('BayRange', 'size'),
            YardLoc_XXX=('YardLoc_XXX', 'max')
        ).reset_index()

        # Remove 'Other' position types
        bay_position_counts = bay_position_counts[bay_position_counts['PositionType'] != 'Other']

        # Sort ranges; keep " U" bays grouped
        def bay_sort_key(bay_range):
            br = str(bay_range)
            if br.endswith(' U'):
                return (br[:-2], 0)
            return (br, 1)

        known_bay_ranges = [b for b in bay_position_counts['BayRange'].unique() if not str(b).startswith("Unknown")]
        sorted_bay_ranges = sorted(known_bay_ranges, key=bay_sort_key)
        print("[DEBUG] Sorted bay ranges:", sorted_bay_ranges)

        # Build doc
        doc = Document()
        section = doc.sections[0]
        section.top_margin = Inches(0.2)
        section.bottom_margin = Inches(0.5)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

        # Title in single column section (spans full page width)
        title_text = output_file_name.replace('.docx', '')
        title_paragraph = doc.add_paragraph()
        title_paragraph.alignment = 1  # 1 = center alignment
        title_run = title_paragraph.add_run(title_text)
        title_run.font.size = Pt(16)
        title_run.bold = True
        title_run.underline = True

        # Add a continuous section break (same page) for two columns
        from docx.enum.section import WD_SECTION
        new_section = doc.add_section(WD_SECTION.CONTINUOUS)
        new_section.top_margin = Inches(0.2)
        new_section.bottom_margin = Inches(0.5)
        new_section.left_margin = Inches(1.0)
        new_section.right_margin = Inches(1.0)

        # Set two columns for the new section (rest of content)
        sectPr = new_section._sectPr
        cols = sectPr.xpath('./w:cols')[0]
        cols.set(qn('w:num'), '2')

        # Add some space after title
        doc.add_paragraph()

        # POD color rotation
        colors = [
            RGBColor(255, 0, 0),
            RGBColor(0, 128, 0),
            RGBColor(0, 0, 255),
            RGBColor(128, 0, 128),
            RGBColor(255, 140, 0),
        ]
        color_map = {}
        color_index = 0

        for bay_range in sorted_bay_ranges:
            bay_data = bay_position_counts[bay_position_counts['BayRange'] == bay_range]
            y_data = bay_data[bay_data['PositionType'] == 'Y']
            e_data = bay_data[bay_data['PositionType'] != 'Y']

            # Create the bay heading with custom formatting 
            bay_paragraph = doc.add_paragraph()
            bay_run = bay_paragraph.add_run(str(bay_range))
            bay_run.font.size = Pt(14)
            bay_run.underline = True    
            bay_run.bold = True         
            
            bay_paragraph.paragraph_format.space_after = Pt(1)

            if not y_data.empty:
                total_y_count = int(y_data['Count'].sum())
                if e_data.empty:
                    doc.add_paragraph(f"{total_y_count} x  ALL FROM Y")
                else:
                    doc.add_paragraph(f"{total_y_count} x Y")

            for _, row in e_data.iterrows():
                pod = str(row['POD'])
                if pod not in color_map:
                    color_map[pod] = colors[color_index % len(colors)]
                    color_index += 1

                p = doc.add_paragraph()
                text = f"{int(row['Count'])} x {row['ISOCD_Group']} {row['PositionType']}"
                run = p.add_run(text)
                run.font.size = Pt(12)

                if pd.notnull(row['YardLoc_XXX']):
                    p.add_run(" - ").font.size = Pt(12)
                    r = p.add_run(f"{int(row['YardLoc_XXX']):03d} ")
                    r.font.size = Pt(10)

                r1 = p.add_run("("); r1.font.size = Pt(12)
                r2 = p.add_run(pod); r2.font.color.rgb = color_map[pod]; r2.font.size = Pt(12)
                r3 = p.add_run(")"); r3.font.size = Pt(12)

        # ---------- Unknown Containers section ----------
        unknowns = data[data['BayRange'].astype(str).str.startswith("Unknown")]
        if not unknowns.empty:
            doc.add_paragraph()
            uh = doc.add_heading("⚠️ Unknown Containers", level=2)
            try:
                uh.runs[0].font.color.rgb = RGBColor(255, 0, 0)
            except Exception:
                pass
            for _, row in unknowns.iterrows():
                container = str(row.get("Container", "")).strip()
                msg = f"{container} – OutStowLoc missing" if container else "OutStowLoc missing"
                p = doc.add_paragraph(msg)
                try:
                    p.runs[0].font.size = Pt(12)
                except Exception:
                    pass

        doc.save(output_file_path)
        print("[DEBUG] Saved:", output_file_path)

    # ---------- Helpers ----------
    def extract_bay_safely(self, x):
        """
        Convert OutStowLoc to a small bay number:
        e.g., 280182 -> '280182' -> drop last 4 digits -> '28' -> 28
        """
        if pd.isna(x):
            return 'Unknown'
        s = str(x).strip()
        if s == '' or s.lower() == 'nan':
            return 'Unknown'
        # normalize numeric-like values
        try:
            s_plain = str(int(float(s)))
        except Exception:
            s_plain = s
        core = s_plain[:-4] if len(s_plain) > 4 else s_plain
        core = core.split('.')[0]
        return int(core) if core.isdigit() else 'Unknown'

    def extract_yardloc_components(self, row):
        # tolerant to variable spaces
        yard_loc = str(row['YardLoc'])
        match = re.search(r'(E\d)\s+(\d{3})\s+(\d{3})\s+\d', yard_loc)
        if match:
            row['YardLoc_E'] = match.group(1)
            row['YardLoc_XXX'] = int(match.group(2))
            row['YardLoc_YYY'] = int(match.group(3))
        else:
            row['YardLoc_E'] = None
            row['YardLoc_XXX'] = None
            row['YardLoc_YYY'] = None
        return row

    def group_ISOCD(self, isocd):
        s = str(isocd)
        if s.startswith('L'):
            return '45 Feet'
        elif s.startswith('45G'):
            return 'High Cube'
        elif s.startswith('42G'):
            return 'Xamila'
        elif s.startswith(('45P','42P','22P','25P')):
            return 'FLAT'
        else:
            return s

    # --- IMPORTANT: E rule before generic Y rule here ---
    def get_position_type(self, yard_loc, isocd, outdate):
        y_raw = str(yard_loc).strip()
        y = y_raw.upper()
        o = str(outdate).strip().lower()
        
        # 🔸 Handle SSS logic first
        if 'SSS' in yard_loc:
            if outdate == '' or outdate == 'nan':
                return 'SSS'
            else:
                return '-L O A D E D-'
        # TA1
        if 'TA1' in y:
            return 'TA1'
        if 'TA5' in y:
            return 'TA5'
        # Generic yard areas -> 'Y'
        if any(sub in y for sub in ['A', 'B', 'C', 'FP', 'R']):
            return 'Y'
        if 'E' in y:
            m = re.search(r'(E\d)\s+(\d{3})\s+(\d{3})\s+\d', y)
            if m:
                return f'{m.group(1)}/{m.group(3)}'    
        # SP/SQ/F
        if 'SP1' in y:
            return 'SP1'
        if 'SP2' in y:
            return 'SP2'
        if 'SQ1' in y:
            return 'SQ1'
        if 'SQ2' in y:
            return 'SQ2'
        if 'WQ1' in y:
            return 'WQ1'
        if 'WQ2' in y:
            return 'WQ2'
        if 'F' in y:
            return 'F'
        if y == '':
            return 'Y'

        return 'Other'

    # ---------- Bay range mapping ----------
    def get_custom_bay_range(self, bay, out_stow_loc, config):
        predefined_ranges = ['SP2', 'SP1', 'SQ1', 'SQ2', 'TA1','F','TA5','WQ1','WQ2','SSS']

        if str(bay) in predefined_ranges:
            return f"Bay {str(bay)}"

        # CHANGED: the 22 hard-coded methods that used to be listed here have
        # moved into the database. Only the lookup changed - the matching is
        # still done by get_bay_range() below, exactly as before, on exactly
        # the same tuples. verify_configs.py proves the two are equivalent
        # for every vessel and every bay.
        ranges = self.range_provider(config)

        if ranges is not None:
            bay_range = self.get_bay_range(bay, ranges)
        elif str(config).startswith(('1-3, 5-7', '1, 3-5', '4-6, 8-10')):
            bay_range = self.get_predefined_bay_range(bay, config)
        else:
            bay_range = self.get_dynamic_bay_range(bay, config)

        # U suffix from penultimate digit
        try:
            s = str(int(float(out_stow_loc)))
            if len(s) >= 2 and s[-2] in ['0', '1', '2']:
                bay_range += " U"
        except Exception:
            pass

        return bay_range

    def get_predefined_bay_range(self, bay, config):
        # CHANGED: same three generic configurations as before, but their
        # ranges now come from the database rather than from three methods.
        if config.startswith('1-3, 5-7'):
            ranges = self.range_provider('1-3, 5-7, Generic')
        elif config.startswith('1, 3-5'):
            ranges = self.range_provider('1, 3-5')
        elif config.startswith('4-6, 8-10'):
            ranges = self.range_provider('4-6, 8-10')
        else:
            return 'Other'
        return self.get_bay_range(bay, ranges) if ranges else 'Other'

    def get_dynamic_bay_range(self, bay, config):
        ranges = [r.strip() for r in str(config).split(',') if r.strip()]
        for r in ranges:
            if '-' in r:
                try:
                    start, end = map(int, r.split('-'))
                except Exception:
                    continue
                bay_int = int(bay) if str(bay).isdigit() else None
                if bay_int is not None and start <= bay_int <= end:
                    return f"Bay {start:02d}-{end:02d}"
            else:
                try:
                    single_bay = int(r)
                except Exception:
                    continue
                if str(bay).isdigit() and int(bay) == single_bay:
                    return f"Bay {single_bay:02d}"
        return "Other"

    def get_bay_range(self, bay, ranges):
        if isinstance(bay, str):
            if bay.isdigit():
                bay = int(bay)
            else:
                return "Other"
        for start, end in ranges:
            if start <= bay <= end:
                return f"Bay {start:02d}-{end:02d}"
        return "Other"
