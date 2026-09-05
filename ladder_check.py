import csv,glob,os
from collections import defaultdict

IDS={'5388944','5153608','5472408','5472409','5130776',
     '5201458','5130768','5130772','5522345','5201465','5192197'}

fs=sorted(glob.glob(os.path.expanduser('~/odds_data/snapshots/*.csv')))
for f in fs:
    d=defaultdict(list)
    with open(f,encoding='utf-8-sig') as x:
        for r in csv.DictReader(x):
            if r['match_id'] in IDS and r['mty']=='1000':
                d[r['market_id']].append(r)
    for mid,rs in d.items():
        if len(rs)>=2:
            print(os.path.basename(f)[:15],rs[0]['match_id'],
                  '|',mid,'|',
                  ','.join(r['option']+':'+r['line']+':'+r['odds'] for r in rs))
