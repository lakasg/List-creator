"""
legacy_reference.py - a frozen copy of the ORIGINAL bay-range code.

Pulled verbatim from list-4-3.py. Nothing here is used by the running app.
It exists only so verify_configs.py can prove that the database-driven
version still answers exactly the same for every vessel and every bay.

Do not edit. If you change a vessel, change it in the app, then run
verify_configs.py and expect the two to differ for that vessel only.
"""


class LegacyLogic:

    def get_custom_bay_range(self, bay, out_stow_loc, config):
        predefined_ranges = ['SP2', 'SP1', 'SQ1', 'SQ2', 'TA1','F','TA5','SSS']

        if str(bay) in predefined_ranges:
            return f"Bay {str(bay)}"

        config_to_function = {
            'RACHEL BORCHARD': self.get_bay_range_config_rachel_borchard,
            'KATHERINE BORCHARD': self.get_bay_range_config_katherine_borchard,
            'LOUISE BORCHARD': self.get_bay_range_config_louise_borchard,
            'LUCY BORCHARD': self.get_bay_range_config_lucy_borchard,
            'AMELIE BORCHARD': self.get_bay_range_config_amelie_borchard,
            'PENGALIA': self.get_bay_range_config_pengalia,
            'MEL SPIRIT': self.get_bay_range_config_mel_spirit,
            'MAUREN': self.get_bay_range_config_mauren,
            '1-3, 5-7, Generic': self.get_bay_range_config_1,
            '1, 3-5': self.get_bay_range_config_2,
            '4-6, 8-10': self.get_bay_range_config_3,
            'MSC GIANNA III': self.get_bay_range_config_msc_gianna_iii,
            'MSC ANTWERP III': self.get_bay_range_config_msc_antwerp_iii,
            'MSC PAMIRA III': self.get_bay_range_config_msc_pamira_iii,
            'MSC CHARLOTTE': self.get_bay_range_config_msc_charlotte,
            'CMA CGM MONTREAL': self.get_bay_range_config_cma_cgm_montreal,
            'MSC MATILDE V': self.get_bay_range_config_msc_matilde_v,
            'CMA CGM LOUGA': self.get_bay_range_config_cma_cgm_louga,
            'BG BLUE': self.get_bay_range_config_bg_blue,
            'CONTSHIP VOW': self.get_bay_range_config_contship_vow,
            'MEDKON ONO': self.get_bay_range_config_medkon_ono,
            'CHS ALPHA': self.get_bay_range_config_chs_alpha,
        }

        if config in config_to_function:
            bay_range = config_to_function[config](bay)
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
        if config.startswith('1-3, 5-7'):
            return self.get_bay_range_config_1(bay)
        elif config.startswith('1, 3-5'):
            return self.get_bay_range_config_2(bay)
        elif config.startswith('4-6, 8-10'):
            return self.get_bay_range_config_3(bay)
        return 'Other'

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

    # --------- Fixed ship configs ---------

    def get_bay_range_config_rachel_borchard(self, bay):
        return self.get_bay_range(bay, [(1, 3), (5, 7), (9, 11), (13, 15), (17, 19), (21, 23), (25, 27), (29, 31), (33, 33)])

    def get_bay_range_config_louise_borchard(self, bay):
        return self.get_bay_range(bay, [(1, 1), (3, 5), (7, 9), (11, 13), (15, 17), (19, 19), (21, 23), (25, 27), (29, 31)])

    def get_bay_range_config_lucy_borchard(self, bay):
        return self.get_bay_range(bay, [(1, 1), (3, 5), (7, 9), (11, 13), (15, 17), (19, 19), (21, 23), (25, 27), (29, 31)])

    def get_bay_range_config_amelie_borchard(self, bay):
        return self.get_bay_range(bay, [(1, 1), (3, 5), (7, 9), (11, 13), (15, 17), (19, 21), (23, 25), (27, 29), (31, 31)])

    def get_bay_range_config_katherine_borchard(self, bay):
        return self.get_bay_range(bay, [(1, 1), (3, 5), (7, 9), (11, 13), (15, 17), (19, 21), (23, 25), (27, 29), (31, 31)])

    def get_bay_range_config_pengalia(self, bay):
        return self.get_bay_range(bay, [(1, 3), (5, 7), (9, 11), (13, 15), (17, 17), (19, 21), (23, 25), (27, 29)])

    def get_bay_range_config_1(self, bay):
        ranges = [(1, 3), (5, 7), (9, 11), (13, 15), (17, 19), (21, 23), (25, 27), (29, 31), (33, 35), (37, 39),
                  (41, 43), (45, 47), (49, 51), (53, 55), (57, 59), (61, 63), (65, 67), (69, 71)]
        return self.get_bay_range(bay, ranges)

    def get_bay_range_config_2(self, bay):
        ranges = [(1, 1), (3, 5), (7, 9), (11, 13), (15, 17), (19, 21), (23, 25), (27, 29), (31, 33), (35, 37),
                  (39, 41), (43, 45), (47, 49), (51, 53), (55, 57), (59, 61), (63, 65), (67, 69), (71, 73)]
        return self.get_bay_range(bay, ranges)

    def get_bay_range_config_3(self, bay):
        ranges = [(4, 6), (8, 10), (12, 14), (16, 18), (20, 22), (24, 26), (28, 30), (32, 34), (36, 38), (40, 42),
                  (44, 46), (48, 50), (52, 54), (56, 58), (60, 62), (64, 66), (68, 70)]
        return self.get_bay_range(bay, ranges)

    def get_bay_range_config_mel_spirit(self, bay):
        return self.get_bay_range(bay, [(1, 1), (3, 5), (7, 9), (11, 13), (15, 17), (19, 21), (23, 25), (27, 29), (31, 31)])

    def get_bay_range_config_mauren(self, bay):
        return self.get_bay_range(bay, [(1, 3), (5, 7), (9, 9), (11, 13), (15, 17), (19, 21), (23, 25), (27, 27), (29, 31), (33, 35)])

    def get_bay_range_config_msc_gianna_iii(self, bay):
        return self.get_bay_range(bay, [(1, 3), (5, 7), (9, 11), (13, 15), (17, 19), (21, 23), (25, 27), (29, 31), (33, 35), (37, 37), (39, 41), (43, 45)])

    def get_bay_range_config_msc_antwerp_iii(self, bay):
        return self.get_bay_range(bay, [(1, 3), (5, 7), (9, 11), (13, 15), (17, 19), (21, 23), (25, 27), (29, 31), (33, 35), (37, 39), (41, 41), (43, 45)])

    def get_bay_range_config_msc_pamira_iii(self, bay):
        return self.get_bay_range(bay, [(1, 3), (5, 7), (9, 11), (13, 15), (17, 19), (21, 23), (25, 27), (29, 31), (33, 35), (37, 39), (41, 41), (43, 45)])

    def get_bay_range_config_msc_charlotte(self, bay):
        return self.get_bay_range(bay, [(1, 3), (5, 7), (9, 9), (11, 13), (15, 17), (19, 21), (23, 25), (27, 27), (29, 31), (33, 35)])

    def get_bay_range_config_cma_cgm_montreal(self, bay):
        return self.get_bay_range(bay, [(1, 3), (5, 7), (9, 11), (13, 15), (17, 19), (21, 23), (25, 27), (29, 31), (33, 35), (37, 37), (39, 41), (43, 45)])

    def get_bay_range_config_msc_matilde_v(self, bay):
        return self.get_bay_range(bay, [(1, 3), (5, 7), (9, 11), (13, 15), (17, 19), (21, 23), (25, 27), (29, 31), (33, 35), (37, 39), (41, 43), (45, 47), (49, 51), (53, 53), (55, 57), (59, 61), (63, 65), (67, 69)])

    def get_bay_range_config_cma_cgm_louga(self, bay):
        return self.get_bay_range(bay, [(1, 3), (5, 7), (9, 11), (13, 15), (17, 19), (21, 23), (25, 27), (29, 31), (33, 35), (37, 37), (39, 41), (43, 45)])

    def get_bay_range_config_bg_blue(self, bay):
        return self.get_bay_range(bay, [(1, 3), (5, 7), (9, 11), (13, 15), (17, 19), (21, 21), (23, 25), (27, 29), (31, 33)])

    def get_bay_range_config_contship_vow(self, bay):
        return self.get_bay_range(bay, [(1, 3), (5, 7), (9, 9), (11, 13), (15, 17), (19, 21), (23, 25), (27, 27), (29, 31), (33, 35)])

    def get_bay_range_config_medkon_ono(self, bay):
        return self.get_bay_range(bay, [(1, 3), (5, 7), (9, 9), (11, 13), (15, 17), (19, 21), (23, 25), (27, 27), (29, 31), (33, 35)])

    def get_bay_range_config_chs_alpha(self, bay):
        return self.get_bay_range(bay, [(1, 3), (4, 4), (5, 7), (9, 11), (12, 12), (13, 15), (17, 17), (19, 21), (22, 22), (23, 25), (27, 29), (31, 33)])
        
if __name__ == '__main__':
    root = Tk()
    app = ContainerAnalysisApp(root)
    root.mainloop()
