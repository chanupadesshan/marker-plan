import json
from pathlib import Path
import openpyxl

root = Path(__file__).resolve().parents[2]
job = json.loads((root/'output/optimization-benchmark/saved-plan.json').read_text())
sheet = openpyxl.load_workbook('C:/Users/chanupa.d/Downloads/358449-359259-1530-1310.xlsx',data_only=True).worksheets[0]
sizes=['C44','C46','C48','C50','C52','C54','C56','C58','D92','D100','D104','D108','D112','C148','C154']
required=dict(zip([s.lstrip('-') for s in job['sizes']],job['quantities']))
patterns=[]
for row in range(14,23):
    counts=[int(sheet.cell(row,col).value or 0) for col in range(6,21)]
    total=sheet.cell(row,61).value
    patterns.append({'counts':dict(zip(sizes,counts)),'total_plies':total,'length_cm':sheet.cell(row,3).value})
known={s:sum(p['counts'][s]*p['total_plies'] for p in patterns if isinstance(p['total_plies'],(int,float))) for s in sizes}
missing=patterns[2]
reconciled={(required[s]-known[s])/c for s,c in missing['counts'].items() if c}
assert reconciled=={90}
missing['source_total_plies']=missing['total_plies']
missing['total_plies']=90
made={s:sum(p['counts'][s]*p['total_plies'] for p in patterns) for s in sizes}
assert made==required
assert all(p['length_cm']<=800 for p in patterns)
small=[p['total_plies'] for p in patterns if p['total_plies']<10]
assert small==[9,9,6]
report={'table_length_m':8,'quantity':2625,'manual':{'markers':9,'production_exact':True,
 'third_marker_plies_reconciled':90,'third_marker_printed_total':missing['source_total_plies'],
 'four_set_markers_fit_verified_lengths':True,'plies_groups_below_minimum':small,
 'satisfies_confirmed_minimum_and_only_final_exception':False},
 'previous_generated':{'main_markers':14,'main_lays':43},
 'improved':{'id':job['id'],'main_markers':job['materials'][0]['result']['marker_count'],
 'main_lays':job['materials'][0]['result']['lay_count'],'validated':True,'minimum_proven':False},
 'notes':['Manual total reconciled from remaining quantities without editing source.',
 'Manual uses three distinct marker groups below minimum10; only one final lay exception is allowed.',
 'New plan uses unchanged estimated capacity3. Actual four-set nesting may be entered and verified separately.']}
(root/'output/optimization-benchmark/comparison.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
